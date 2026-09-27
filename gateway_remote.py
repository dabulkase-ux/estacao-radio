"""Publica somente o estado atual. Não lê serial nem interpreta o protocolo."""
import json
import logging
import os
import time
import http.client
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

from estado import dados, lock_dados, mudanca_remota

logger = logging.getLogger("microserial.gateway")


def estado_publicavel():
    agora = time.time()
    # Copiar só os campos enviados, sem copiar histórico/extras sob o lock serial.
    with lock_dados:
        return {
            "connected": bool(dados["connected"]),
            "transport": "serial",
            "stations": {
                id_: {
                    "name": s["name"], "sound": s["sound"],
                    "connected": bool(s["connected"]), "interval": s["interval"],
                    # Reenviar não transforma uma leitura velha em heartbeat novo.
                    "age": min(86400, max(0, agora - s["last_seen"])),
                }
                for id_, s in dados["stations"].items()
            }
        }


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
        self.conexao = None
        self.partes = partes
        self.mudanca = mudanca_remota
        self.intervalo_minimo = 0.1  # Máximo 10 POST/s no total, não por estação.
        self.diagnostico = os.getenv("MICROSERIAL_LATENCY_DEBUG", "") == "1"

    def enviar(self, offline=False):
        estado = self.obter()
        if offline:
            estado["connected"] = False
        inicio = time.perf_counter()
        if self.conexao is None:
            classe = http.client.HTTPSConnection if self.partes.scheme == "https" else http.client.HTTPConnection
            self.conexao = classe(self.partes.hostname, self.partes.port, timeout=5)
        try:
            self.conexao.request("POST", "/api/gateway/state",
                                 body=json.dumps(estado, allow_nan=False).encode(),
                                 headers={"Authorization": "Bearer " + self.token,
                                          "Content-Type": "application/json"})
            resposta = self.conexao.getresponse()
            if resposta.status != 204:
                # Nunca seguir redirects nem retransmitir automaticamente um snapshot velho.
                raise HTTPError(self.url, resposta.status, "Publicacao recusada", {}, None)
            resposta.read()
        except Exception:
            self.fechar()
            raise
        if self.diagnostico:
            logger.info("[LATENCIA] POST ida/volta=%.1f ms; estacoes=%d",
                        (time.perf_counter() - inicio) * 1000, len(estado["stations"]))

    def fechar(self):
        if self.conexao is not None:
            self.conexao.close()
            self.conexao = None

    def executar(self, stop):
        espera = 1
        try:
            while not stop.is_set():
                self.mudanca.clear()  # Alterações durante HTTP permanecem pendentes.
                try:
                    self.enviar()
                    espera = 1
                except (OSError, URLError, HTTPError, ValueError, http.client.HTTPException):
                    # Não registrar URL, headers nem token secreto.
                    logger.warning("Backend remoto indisponível ou publicação recusada; nova tentativa automática")
                    espera = min(10, espera * 2)
                    stop.wait(espera)  # Mudanças não furam o backoff em falhas.
                    continue
                # Uma única requisição em voo. Coalesce todos os eventos nesse intervalo.
                if stop.wait(self.intervalo_minimo):
                    break
                self.mudanca.wait(max(0, 1 - self.intervalo_minimo))
        finally:
            try:
                self.enviar(offline=True)
            except (OSError, URLError, HTTPError, ValueError, http.client.HTTPException):
                pass  # O timeout no backend cobre desligamento abrupto.
            self.fechar()


def configurar_publicador():
    url = os.getenv("MICROSERIAL_BACKEND_URL", "").strip()
    token = os.getenv("MICROSERIAL_GATEWAY_TOKEN", "").strip()
    if not url and not token:
        return None
    if not url or not token:
        raise ValueError("Configure MICROSERIAL_BACKEND_URL e MICROSERIAL_GATEWAY_TOKEN juntos")
    return PublicadorRemoto(url, token)
