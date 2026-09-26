"""Aplicação principal do MicroSerial."""

from __future__ import annotations

import logging
import argparse
import threading
import time
from typing import Optional

import serial

from flask import Flask
from flask_socketio import SocketIO

from config import (
    BAUDRATE,
    TEMPO_RECONEXAO,
    TIMEOUT_ESTACAO,
    MAX_MENSAGEM,
)
from estado import atualizar_central
from monitor import monitorar_estacoes
from radio import processar_radio as processar_mensagem
from protocolo_serial import LinhasSerial, NomesFragmentados
from routes.web import registrar_rotas
from serial_manager import (
    abrir_microbit,
    encontrar_microbit,
    registrar_conexao,
    receber_resultado,
)
from sockets.events import registrar_eventos
from utilitarios import iso


logger = logging.getLogger(
    "microserial.app"
)


# ============================================================
# FLASK / SOCKET.IO
# ============================================================

app = Flask(__name__)

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading",
)


registrar_rotas(app)
registrar_eventos(socketio)


# ============================================================
# EMISSÃO DE DADOS
# ============================================================

def enviar_dados(
    destinatario: Optional[str] = None,
) -> bool:

    from estado import obter_estado

    estado = obter_estado()

    try:

        if destinatario:

            socketio.emit(
                "radio_data",
                estado,
                to=destinatario,
            )

        else:

            socketio.emit(
                "radio_data",
                estado,
            )

        logger.debug(
            "[SOCKET] radio_data emitido; central=%s; estacoes=%s",
            estado.get("communication_status"),
            list(estado.get("stations", {})),
        )

        return True

    except Exception:

        logger.exception(
            "Falha ao emitir atualização Socket.IO."
        )

        return False


# ============================================================
# PROCESSAMENTO DO RÁDIO
# ============================================================

def processar_radio(linha: str) -> bool:
    if not processar_mensagem(linha):
        return False
    enviar_dados()
    return True


def desconectar_central() -> bool:

    mudou = atualizar_central(
        connected=False,
        central_port=None,
        communication_status="disconnected",
    )

    if mudou:
        enviar_dados()

    return mudou


# ============================================================
# LEITOR SERIAL
# ============================================================

def ler_microbit(stop_event: Optional[threading.Event] = None) -> None:
    while stop_event is None or not stop_event.is_set():
        conexao = None
        try:
            if atualizar_central(communication_status="connecting"):
                enviar_dados()
            porta = encontrar_microbit()
            if porta is None:
                desconectar_central()
            else:
                conexao = abrir_microbit(porta)
                registrar_conexao(conexao)
                atualizar_central(
                    connected=True, central_port=porta, last_known_port=porta,
                    communication_status="connected",
                )
                enviar_dados()
                leitor = LinhasSerial(MAX_MENSAGEM)
                nomes = NomesFragmentados()
                ultimo_sinal = time.monotonic()
                while stop_event is None or not stop_event.is_set():
                    dados = conexao.readline(MAX_MENSAGEM + 1)
                    for linha in leitor.alimentar(dados):
                        logger.debug("[SERIAL RX] %r", linha)
                        if linha.strip() == "CENTRAL_ONLINE|1":
                            logger.info("[SERIAL RX] CENTRAL_ONLINE|1")
                            ultimo_sinal = time.monotonic()
                            agora = time.time()
                            atualizar_central(central_last_signal=agora,
                                              central_last_signal_iso=iso(agora))
                            enviar_dados()
                        elif linha.startswith("CMD|"):
                            receber_resultado(linha)
                        elif linha.startswith("NPART|"):
                            completa = nomes.receber(linha)
                            if completa:
                                processar_radio(completa)
                        else:
                            processar_radio(linha)
                    if time.monotonic() - ultimo_sinal > 5:
                        raise serial.SerialException("Central deixou de responder")
        except (serial.SerialException, OSError) as erro:
            logger.warning("Conexão com a Central perdida: %s", erro)
        except Exception:
            logger.exception("Erro no leitor serial")
        finally:
            registrar_conexao(None)
            if conexao is not None:
                try:
                    conexao.close()
                except (serial.SerialException, OSError):
                    logger.debug("Falha ao fechar serial", exc_info=True)
            desconectar_central()
        if stop_event is None:
            time.sleep(TEMPO_RECONEXAO)
        else:
            stop_event.wait(TEMPO_RECONEXAO)


def main() -> None:

    from gateway_remote import configurar_publicador

    argumentos = argparse.ArgumentParser(description="MicroSerial: interface local e gateway remoto opcional")
    argumentos.add_argument("--gateway-only", action="store_true", help="Ler serial e publicar sem iniciar o servidor local")
    opcoes = argumentos.parse_args()
    publicador = configurar_publicador()
    if opcoes.gateway_only and publicador is None:
        argumentos.error("--gateway-only exige MICROSERIAL_BACKEND_URL e MICROSERIAL_GATEWAY_TOKEN")
    stop = threading.Event()
    thread_publicador = None
    if publicador is not None:
        thread_publicador = threading.Thread(target=publicador.executar, args=(stop,), daemon=True, name="remote-publisher")
        thread_publicador.start()

    logger.info(
        "========================================"
    )

    logger.info(
        "MICROSERIAL INICIADO"
    )

    logger.info(
        "Baudrate: %s",
        BAUDRATE,
    )

    logger.info(
        "Timeout estação: %ss",
        TIMEOUT_ESTACAO,
    )

    logger.info(
        "========================================"
    )

    threading.Thread(
        target=ler_microbit,
        kwargs={"stop_event": stop},
        daemon=True,
        name="serial-reader",
    ).start()

    threading.Thread(
        target=monitorar_estacoes,
        kwargs={
            "enviar_dados": enviar_dados,
            "stop_event": stop,
        },
        daemon=True,
        name="station-monitor",
    ).start()

    try:
        if opcoes.gateway_only:
            logger.info("Gateway remoto ativo; nenhum frontend é hospedado por este processo")
            while not stop.wait(1):
                pass
        else:
            logger.info("Servidor iniciado em http://127.0.0.1:5000")
            socketio.run(
                app, host="127.0.0.1", port=5000, debug=False,
                allow_unsafe_werkzeug=True,
            )
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        if thread_publicador is not None:
            thread_publicador.join(timeout=6)


if __name__ == "__main__":
    main()
