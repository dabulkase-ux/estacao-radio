"""Backend de demonstração: uma Central/gateway, estado atual somente em RAM."""
import copy
import hmac
import math
import os
import re
import threading
import time

from flask import Flask, jsonify, request
from flask_socketio import SocketIO

from config import TIMEOUT_ESTACAO


def numero(valor, minimo, maximo):
    return type(valor) in {int, float} and math.isfinite(valor) and minimo <= valor <= maximo


class EstadoAtual:
    def __init__(self, clock=time.monotonic, gateway_timeout=10, station_timeout=TIMEOUT_ESTACAO):
        self.clock = clock
        self.gateway_timeout = gateway_timeout
        self.station_timeout = station_timeout
        self.lock = threading.RLock()
        self.recebido = None
        self.connected = False
        self.transport = "serial"
        self.stations = {}

    def receber(self, payload):
        if not isinstance(payload, dict) or type(payload.get("connected")) is not bool:
            raise ValueError("connected deve ser booleano")
        if payload.get("transport") not in {"serial", "bluetooth"}:
            raise ValueError("transport inválido")
        stations = payload.get("stations")
        if not isinstance(stations, dict) or len(stations) > 64:
            raise ValueError("stations deve conter no máximo 64 estações")
        agora = self.clock()
        novas = {}
        for id_, s in stations.items():
            if not re.fullmatch(r"[A-Z0-9_-]{2,8}", id_) or not isinstance(s, dict):
                raise ValueError("estação inválida")
            nome = s.get("name", id_)
            if not isinstance(nome, str) or not 1 <= len(nome) <= 48 or any(ord(c) < 32 for c in nome):
                raise ValueError("nome inválido")
            if type(s.get("connected")) is not bool or not numero(s.get("age"), 0, 86400):
                raise ValueError("connected/age inválidos")
            som, intervalo = s.get("sound"), s.get("interval")
            if som is not None and not numero(som, 0, 255):
                raise ValueError("sound inválido")
            if intervalo is not None and not numero(intervalo, 0, 86400):
                raise ValueError("interval inválido")
            novas[id_] = dict(id=id_, name=nome, sound=som, interval=intervalo,
                              connected=s["connected"], last_seen=agora - s["age"])
        with self.lock:
            self.recebido = agora
            self.connected = payload["connected"]
            self.transport = payload["transport"]
            self.stations = novas  # Substituição, nunca append de histórico.

    def obter(self):
        with self.lock:
            agora = self.clock()
            gateway = self.recebido is not None and agora - self.recebido < self.gateway_timeout
            connected = gateway and self.connected
            stations = copy.deepcopy(self.stations)
            for s in stations.values():
                last_seen = s.pop("last_seen")
                s["connected"] = bool(connected and s["connected"] and agora - last_seen <= self.station_timeout)
                s["status"] = "ONLINE" if s["connected"] else "OFFLINE"
            return dict(connected=bool(connected), gateway_connected=gateway,
                        communication_status="connected" if connected else "disconnected",
                        transport=self.transport, read_only=True, stations=stations)


def criar_backend(token=None, origins=None, iniciar_monitor=True, estado=None):
    token = token if token is not None else os.getenv("GATEWAY_TOKEN", "")
    if len(token) < 32 or not token.isascii() or any(c.isspace() for c in token):
        raise ValueError("Defina GATEWAY_TOKEN com ao menos 32 caracteres ASCII sem espaços")
    origins = origins if origins is not None else [x.strip() for x in os.getenv("FRONTEND_ORIGINS", "").split(",") if x.strip()]
    if "*" in origins:
        raise ValueError("FRONTEND_ORIGINS deve listar as origens exatas, sem wildcard")
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024
    socketio = SocketIO(app, async_mode="threading", cors_allowed_origins=origins or None,
                        max_http_buffer_size=64 * 1024, ping_interval=10, ping_timeout=10)
    atual = estado or EstadoAtual()

    @app.after_request
    def cabecalhos(resposta):
        resposta.headers["Cache-Control"] = "no-store"
        # Escrita é server-to-server; nunca habilitar CORS para Authorization.
        if request.path == "/api/data" and request.headers.get("Origin") in origins:
            resposta.headers["Access-Control-Allow-Origin"] = request.headers["Origin"]
            resposta.headers["Vary"] = "Origin"
        return resposta

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/api/data")
    def dados():
        return jsonify(atual.obter())

    @app.post("/api/gateway/state")
    def receber():
        inicio = time.perf_counter()
        esperado = ("Bearer " + token).encode()
        if not hmac.compare_digest(request.headers.get("Authorization", "").encode(), esperado):
            return {"error": "unauthorized"}, 401
        try:
            atual.receber(request.get_json(silent=True))
        except (ValueError, TypeError):
            return {"error": "invalid state"}, 400
        socketio.emit("radio_data", atual.obter())
        if os.getenv("MICROSERIAL_LATENCY_DEBUG", "") == "1":
            app.logger.warning("[LATENCIA] POST recebido -> emit=%.2f ms",
                               (time.perf_counter() - inicio) * 1000)
        return "", 204

    @socketio.on("connect")
    def conectar(auth=None):
        socketio.emit("radio_data", atual.obter(), to=request.sid)

    @socketio.on("radio_ping")
    def sem_escrita_publica(data=None):
        return {"ok": False, "status": "READ_ONLY"}

    # Nenhum handler de escrita Socket.IO. Só o POST autenticado muda o estado.
    stop = threading.Event()

    def monitorar():
        while not stop.wait(1):
            socketio.emit("radio_data", atual.obter())

    if iniciar_monitor:
        socketio.start_background_task(monitorar)
    app.extensions["radio_online"] = dict(estado=atual, stop=stop)
    return app, socketio


if __name__ == "__main__":
    app, socketio = criar_backend()
    # Para teste local no Windows. Render usa Gunicorn (um worker).
    socketio.run(app, host="127.0.0.1", port=int(os.getenv("PORT", "5001")),
                 allow_unsafe_werkzeug=True, use_reloader=False)
