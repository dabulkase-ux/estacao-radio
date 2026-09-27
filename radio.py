"""Processamento das mensagens recebidas pelo rádio MicroSerial."""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from estacoes import atualizar_estacao
from estado import atualizar_central
from parser import extrair_dados_mensagem
from utilitarios import iso


logger = logging.getLogger("microserial.radio")


def processar_radio(
    linha: Any,
) -> bool:
    """
    Processa uma mensagem recebida pela central.

    Fluxo:

        mensagem serial
            ↓
        parser.py
            ↓
        estacoes.py
            ↓
        estado compartilhado
    """

    if linha is None:
        logger.warning(
            "Mensagem recebida como None."
        )
        return False

    texto = str(linha).strip()

    if not texto:
        return False

    logger.debug(
        "Rádio recebeu: %r",
        texto,
    )

    # ========================================================
    # SINAIS ESPECIAIS DA CENTRAL
    # ========================================================

    if texto.upper() in {"CENTRAL_ONLINE", "CENTRAL_ONLINE|1"}:
        agora = time.time()

        atualizar_central(
            connected=True,
            communication_status="connected",
            central_last_signal=agora,
            central_last_signal_iso=iso(agora),
        )

        logger.info(
            "Sinal CENTRAL_ONLINE recebido."
        )

        return True

    # ========================================================
    # PARSER
    # ========================================================

    info = extrair_dados_mensagem(
        texto
    )

    logger.debug(
        "Mensagem interpretada: %s",
        info,
    )

    if not info.get("valid"):
        logger.warning("[PARSER] Mensagem descartada: %r", texto)
        logger.warning(
            "Mensagem inválida ignorada: %r",
            texto,
        )
        return False

    # ========================================================
    # ESTAÇÃO
    # ========================================================

    atualizada = atualizar_estacao(
        info
    )

    if not atualizada:
        logger.warning("[PARSER] Estação não atualizada: %r", texto)
        logger.warning(
            "Não foi possível atualizar estação "
            "para mensagem: %r",
            texto,
        )
        return False

    # ========================================================
    # CENTRAL
    # ========================================================

    agora = time.time()

    atualizar_central(
        central_last_signal=agora,
        central_last_signal_iso=iso(agora),
    )

    # ========================================================
    # DEBUG DO SOM
    # ========================================================

    if info.get("sound") is not None:
        logger.debug(
            "Som recebido | estação=%s | som=%s | raw=%r",
            info.get("id"),
            info.get("sound"),
            texto,
        )

    return True
