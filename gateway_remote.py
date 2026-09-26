"""Publica somente o estado atual. Não lê serial nem interpreta o protocolo."""
import json
import logging
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from estado import obter_estado

logger = logging.getLogger("microserial.gateway")


def estado_publicavel():
    estado = obter_estado()
    agora = time.time()
    return {
        "connected": bool(estado["connected"]),
        "transport": "serial",
        "stations": {
            id_: {
                "name": s["name"], "sound": s["sound"],
                "connected": bool(s["connected"]), "interval": s["interval"],
                # Reenviar snapshot não transforma uma leitura velha em heartbeat novo.
                "age": min(86400, max(0, agora - s["last_seen"])),
            }
            for id_, s in estado["stations"].items()
        },
    }


class SemRedirecionamento(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Nunca encaminhar Authorization a outro endereço por redirect.
        return None


class PublicadorRemoto:
    def __init__(self, url, token, obter=estado_publicavel):
        partes = urlsplit(url)
        if (partes.scheme not in {"https", "http"} or not partes.hostname
                or partes.username or partes.password or partes.query or partes.fragment
                or partes.path not in {"", "/"}
                or (partes.scheme == "http" and partes.hostname not in {"localhost", "127.0.0.1", "::1"})):
            raise ValueError("MICROSERIAL_BACKEND_URL deve ser uma origem HTTPS (HTTP só no localhost)")
        if len(token) < 32 or not token.isascii() or any(c.isspace() for c in token):
            raise ValueError("MICROSERIAL_GATEWAY_TOKEN deve conter ao menos 32 caracteres ASCII sem espaços")
        self.url = url.rstrip("/") + "/api/gateway/state"
        self.token = token
        self.obter = obter
        self.http = build_opener(SemRedirecionamento())

    def enviar(self, offline=False):
        estado = self.obter()
        if offline:
            estado["connected"] = False
        request = Request(self.url, data=json.dumps(estado, allow_nan=False).encode(),
                          headers={"Authorization": "Bearer " + self.token,
                                   "Content-Type": "application/json"}, method="POST")
        with self.http.open(request, timeout=5) as resposta:
            if resposta.status != 204:
                raise ValueError("Resposta inesperada do backend")

    def executar(self, stop):
        espera = 1
        try:
            while not stop.is_set():
                try:
                    self.enviar()
                    espera = 1
                except (OSError, URLError, HTTPError, ValueError):
                    # Não registrar URL, headers nem token secreto.
                    logger.warning("Backend remoto indisponível ou publicação recusada; nova tentativa automática")
                    espera = min(10, espera * 2)
                stop.wait(espera)
        finally:
            try:
                self.enviar(offline=True)
            except (OSError, URLError, HTTPError, ValueError):
                pass  # O timeout no backend cobre desligamento abrupto.


def configurar_publicador():
    url = os.getenv("MICROSERIAL_BACKEND_URL", "").strip()
    token = os.getenv("MICROSERIAL_GATEWAY_TOKEN", "").strip()
    if not url and not token:
        return None
    if not url or not token:
        raise ValueError("Configure MICROSERIAL_BACKEND_URL e MICROSERIAL_GATEWAY_TOKEN juntos")
    return PublicadorRemoto(url, token)
