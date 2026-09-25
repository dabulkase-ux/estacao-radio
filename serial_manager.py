"""Descoberta por assinatura da Central e comandos seriais correlacionados."""
from __future__ import annotations

import logging
import os
import re
import secrets
import threading
import time

import serial
import serial.tools.list_ports

from config import BAUDRATE, SERIAL_TIMEOUT, TESTE_TIMEOUT, MAX_MENSAGEM
from estado import obter_estado
from protocolo_serial import LinhasSerial

logger = logging.getLogger("microserial.serial_manager")
_lock = threading.RLock()
_conexao = None
_pendente = None


def _texto_porta(porta):
    return " ".join(str(getattr(porta, k, "") or "") for k in
                    ("description", "manufacturer", "product", "hwid")).lower()


def _porta_parece_microbit(porta):
    texto = _texto_porta(porta)
    return (any(p in texto for p in ("micro:bit", "microbit", "mbed", "daplink", "cmsis-dap"))
            or (getattr(porta, "vid", None), getattr(porta, "pid", None))
            in {(0x0D28, 0x0204), (0x0D28, 0x0200)})


def abrir_microbit(porta):
    logger.info("[SERIAL] Abrindo %s em %s baud", porta, BAUDRATE)
    conexao = serial.Serial(port=porta, baudrate=BAUDRATE,
                            timeout=SERIAL_TIMEOUT, write_timeout=1)
    try:
        logger.info("[SERIAL] Porta aberta: %s", porta)
        conexao.write(b"HELLO\n")
        logger.debug("[SERIAL TX] HELLO")
        leitor = LinhasSerial(MAX_MENSAGEM)
        prazo = time.monotonic() + TESTE_TIMEOUT
        while time.monotonic() < prazo:
            for linha in leitor.alimentar(conexao.readline(MAX_MENSAGEM + 1)):
                logger.debug("[SERIAL RX] %r", linha)
                if linha.strip() == "CENTRAL_ONLINE|1":
                    logger.info("[SERIAL] Central confirmada em %s", porta)
                    return conexao
        raise serial.SerialException(f"{porta}: assinatura da Central V1 não recebida")
    except Exception:
        conexao.close()
        raise


def encontrar_microbit(ultima_porta=None):
    portas = list(serial.tools.list_ports.comports())
    explicita = os.getenv("MICROSERIAL_PORT", "").strip()
    conhecida = ultima_porta or obter_estado().get("last_known_port")
    logger.info("[SERIAL] Procurando Central; baud=%s; portas=%s", BAUDRATE,
                [getattr(porta, "device", "?") for porta in portas])
    candidatos = [p.device for p in portas if _porta_parece_microbit(p)]
    if explicita:
        candidatos = [explicita]
    elif conhecida in candidatos:
        candidatos.remove(conhecida)
        candidatos.insert(0, conhecida)
    for porta in candidatos:
        try:
            conexao = abrir_microbit(porta)
            conexao.close()
            return porta
        except (serial.SerialException, OSError) as erro:
            logger.warning("[SERIAL] Porta não confirmou Central: %s (%s)",
                           porta, erro)
    logger.warning("[SERIAL] Nenhuma Central encontrada; candidatos=%s", candidatos)
    return None


def registrar_conexao(conexao):
    global _conexao
    with _lock:
        _conexao = conexao
        if conexao is None and _pendente is not None:
            _pendente["status"] = "DISCONNECTED"
            _pendente["evento"].set()


def receber_resultado(linha):
    match = re.fullmatch(r"CMD\|([A-Z0-9_-]{2,8})\|([0-9]{1,10})\|(OK|TIMEOUT|BUSY)", linha)
    if not match:
        return False
    id_, token, status = match.groups()
    with _lock:
        if _pendente and _pendente["id"] == id_ and _pendente["token"] == int(token):
            _pendente["status"] = status
            _pendente["evento"].set()
    return True


def enviar_ping(id_):
    global _pendente
    if not isinstance(id_, str) or not re.fullmatch(r"[A-Z0-9_-]{2,8}", id_):
        return {"ok": False, "status": "INVALID_ID"}
    pedido = {"id": id_, "token": secrets.randbits(32), "evento": threading.Event(),
              "status": "TIMEOUT"}
    with _lock:
        if _conexao is None:
            return {"ok": False, "status": "DISCONNECTED"}
        if _pendente is not None:
            return {"ok": False, "status": "BUSY"}
        _pendente = pedido
        try:
            mensagem = f"PING|{id_}|{pedido['token']}\n".encode("ascii")
            if _conexao.write(mensagem) != len(mensagem):
                raise serial.SerialException("Escrita serial parcial")
        except (serial.SerialException, OSError):
            _pendente = None
            return {"ok": False, "status": "DISCONNECTED"}
    try:
        pedido["evento"].wait(9)
        return {"ok": pedido["status"] == "OK", "status": pedido["status"], "id": id_}
    finally:
        with _lock:
            _pendente = None
