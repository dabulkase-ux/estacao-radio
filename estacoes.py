"""Gerenciamento das estações MicroSerial."""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Any, Optional

from config import HISTORICO_LIMITE
from estado import (
    CAMPOS_RESERVADOS_ESTACAO,
    dados,
    lock_dados,
)
from utilitarios import (
    iso,
    normalizar_id,
    normalizar_nome,
)

logger = logging.getLogger("microserial.estacoes")


def _nova_estacao(
    identificador: str,
    agora: float,
) -> dict[str, Any]:
    return {
        "id": identificador,
        "name": identificador,
        "status": "ONLINE",
        "connected": True,
        "first_seen": agora,
        "last_seen": agora,
        "last_signal": agora,
        "last_seen_iso": iso(agora),
        "interval": None,
        "average_interval": None,
        "min_interval": None,
        "max_interval": None,
        "signals_received": 0,
        "intervals_received": 0,
        "sound": None,
        "sound_level": None,
        "last_message": None,
        "last_raw_message": None,
        "was_offline": False,
        "history": deque(
            maxlen=HISTORICO_LIMITE
        ),
        "extra": {},
    }


def _atualizar_intervalo(
    estacao: dict[str, Any],
    agora: float,
    recuperando: bool,
) -> None:
    anterior = estacao.get("last_signal")

    if anterior is None or recuperando:
        estacao["interval"] = None
        return

    intervalo = round(
        agora - anterior,
        3,
    )

    quantidade = estacao.get(
        "intervals_received",
        0,
    )

    media = estacao.get(
        "average_interval"
    )

    estacao["interval"] = intervalo

    estacao["average_interval"] = round(
        intervalo
        if media is None
        else (
            media * quantidade + intervalo
        ) / (quantidade + 1),
        3,
    )

    estacao["min_interval"] = (
        intervalo
        if estacao.get("min_interval") is None
        else min(
            estacao["min_interval"],
            intervalo,
        )
    )

    estacao["max_interval"] = (
        intervalo
        if estacao.get("max_interval") is None
        else max(
            estacao["max_interval"],
            intervalo,
        )
    )

    estacao["intervals_received"] = (
        quantidade + 1
    )


def atualizar_estacao(
    info: Optional[dict[str, Any]],
    agora: Optional[float] = None,
) -> bool:
    """
    Atualiza uma estação a partir dos dados produzidos pelo parser.
    """

    if not info or not info.get("valid"):
        return False

    agora = (
        time.time()
        if agora is None
        else agora
    )

    identificador = normalizar_id(
        info.get("id")
    )

    if not identificador:
        logger.warning(
            "Mensagem válida sem identificador de estação: %s",
            info.get("raw"),
        )
        return False

    with lock_dados:
        estacao = dados["stations"].get(
            identificador
        )

        nova = estacao is None

        if nova:
            estacao = _nova_estacao(
                identificador,
                agora,
            )

            dados["stations"][
                identificador
            ] = estacao

        if not isinstance(
            estacao.get("history"),
            deque,
        ):
            logger.error(
                "Histórico inválido de %s restaurado.",
                identificador,
            )

            estacao["history"] = deque(
                maxlen=HISTORICO_LIMITE
            )

        if not isinstance(
            estacao.get("extra"),
            dict,
        ):
            estacao["extra"] = {}

        status = info.get("status")

        recuperando = (
            not nova
            and (
                estacao.get(
                    "was_offline",
                    False,
                )
                or not estacao.get(
                    "connected",
                    False,
                )
            )
            and status != "OFFLINE"
        )

        _atualizar_intervalo(
            estacao,
            agora,
            recuperando or nova,
        )

        nome = normalizar_nome(
            info.get("name")
        )

        som = info.get("sound")

        esta_offline = (
            status == "OFFLINE"
        )

        estacao.update({
            "last_seen": agora,
            "last_signal": agora,
            "last_seen_iso": iso(agora),
            "signals_received": (
                estacao["signals_received"] + 1
            ),
            "connected": not esta_offline,
            "status": (
                status
                or "ONLINE"
            ),
            "last_message": info.get(
                "command"
            ),
            "last_raw_message": info.get(
                "raw"
            ),
            "was_offline": esta_offline,
        })

        if nome:
            estacao["name"] = nome

        if som is not None:
            estacao["sound"] = som
            estacao["sound_level"] = som

        extras = info.get("extra") or {}

        seguros = {
            chave: valor
            for chave, valor in extras.items()
            if chave not in CAMPOS_RESERVADOS_ESTACAO
        }

        estacao["extra"].update(seguros)

        for chave, valor in seguros.items():
            estacao[chave] = valor

        estacao["history"].append({
            "timestamp": agora,
            "timestamp_iso": iso(agora),
            "status": estacao["status"],
            "sound": estacao["sound"],
            "raw": info.get("raw"),
        })

    if nova:
        logger.info(
            "Estação encontrada: %s",
            identificador,
        )

    elif recuperando:
        logger.info(
            "Estação voltou online: %s",
            identificador,
        )

    else:
        logger.debug(
            "Estação atualizada: %s",
            identificador,
        )

    return True