"""Configurações centrais do MicroSerial."""

from __future__ import annotations

import logging
import os


def _env_int(
    name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    try:
        value = int(
            os.getenv(
                name,
                str(default),
            ).strip()
        )
    except (AttributeError, ValueError):
        return default

    return (
        value
        if minimum <= value <= maximum
        else default
    )


def _env_float(
    name: str,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    try:
        value = float(
            os.getenv(
                name,
                str(default),
            ).strip()
        )
    except (AttributeError, ValueError):
        return default

    return (
        value
        if minimum <= value <= maximum
        else default
    )


BAUDRATE = _env_int(
    "MICROSERIAL_BAUDRATE",
    115200,
    300,
    2_000_000,
)

TEMPO_RECONEXAO = _env_float(
    "MICROSERIAL_RECONNECT_SECONDS",
    2,
    0.1,
    3600,
)

TIMEOUT_ESTACAO = _env_float(
    "MICROSERIAL_STATION_TIMEOUT",
    5,
    0.1,
    86400,
)

HISTORICO_LIMITE = _env_int(
    "MICROSERIAL_HISTORY_LIMIT",
    100,
    1,
    10_000,
)

SERIAL_TIMEOUT = _env_float(
    "MICROSERIAL_SERIAL_TIMEOUT",
    0.5,
    0.05,
    60,
)

TESTE_TIMEOUT = _env_float(
    "MICROSERIAL_PROBE_TIMEOUT",
    1.5,
    0.1,
    30,
)

MAX_MENSAGEM = _env_int(
    "MICROSERIAL_MAX_MESSAGE_LENGTH",
    512,
    1,
    4096,
)


_NIVEIS_LOG = {
    "CRITICAL",
    "ERROR",
    "WARNING",
    "INFO",
    "DEBUG",
}

NIVEL_LOG = os.getenv(
    "MICROSERIAL_LOG_LEVEL",
    "INFO",
).upper()

if NIVEL_LOG not in _NIVEIS_LOG:
    NIVEL_LOG = "INFO"


logging.basicConfig(
    level=getattr(
        logging,
        NIVEL_LOG,
    ),
    format=(
        "%(asctime)s "
        "%(levelname)-8s "
        "%(name)s: %(message)s"
    ),
)

logger = logging.getLogger("microserial")