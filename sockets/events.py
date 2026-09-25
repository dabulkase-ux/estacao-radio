"""Eventos Socket.IO do MicroSerial."""

from __future__ import annotations

import logging

from flask import request

from estado import obter_estado
from serial_manager import enviar_ping

logger = logging.getLogger(
    "microserial.sockets"
)


def registrar_eventos(
    socketio,
) -> None:
    """Registra os eventos Socket.IO."""

    @socketio.on("connect")
    def cliente_conectou():
        logger.info(
            "Navegador conectado: %s",
            request.sid,
        )

        socketio.emit(
            "radio_data",
            obter_estado(),
            to=request.sid,
        )

    @socketio.on("disconnect")
    def cliente_desconectou(reason=None):
        logger.info(
            "Navegador desconectado: %s",
            request.sid,
        )

    @socketio.on("radio_ping")
    def testar_estacao(dados):
        if not isinstance(dados, dict):
            return {"ok": False, "status": "INVALID_ID"}
        return enviar_ping(dados.get("id"))
