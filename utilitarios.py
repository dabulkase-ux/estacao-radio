"""Funções utilitárias do MicroSerial."""

from __future__ import annotations

import time
from typing import Any, Optional


def iso(timestamp: float) -> str:
    """Converte timestamp Unix para ISO UTC."""

    return time.strftime(
        "%Y-%m-%dT%H:%M:%SZ",
        time.gmtime(timestamp),
    )


def converter_numero(
    valor: Any,
) -> Optional[int | float]:
    """Tenta converter um valor para inteiro ou float."""

    if valor is None or isinstance(
        valor,
        bool,
    ):
        return None

    texto = str(valor).strip()

    if not texto:
        return None

    try:
        return int(texto)

    except ValueError:
        try:
            return float(texto)

        except ValueError:
            return None


def normalizar_status(
    valor: Any,
) -> Optional[str]:
    """Normaliza estados recebidos pelo rádio."""

    if valor is None:
        return None

    status = str(
        valor
    ).strip().upper()

    status = {
        "CONNECTED": "ONLINE",
        "DISCONNECTED": "OFFLINE",
        "ON": "ONLINE",
        "OFF": "OFFLINE",
    }.get(
        status,
        status,
    )

    return (
        status
        if status in {
            "ONLINE",
            "OFFLINE",
        }
        else None
    )


def normalizar_id(
    valor: Any,
    permitir_unico: bool = False,
) -> Optional[str]:
    """Normaliza identificadores de estação."""

    identificador = " ".join(
        str(valor or "")
        .strip()
        .split()
    ).upper()

    if not identificador:
        return None

    if (
        len(identificador) < 2
        and not permitir_unico
    ):
        return None

    return identificador


def normalizar_nome(
    valor: Any,
) -> Optional[str]:
    """Normaliza nome de estação."""

    nome = " ".join(
        str(valor or "")
        .strip()
        .split()
    )

    return nome or None


def normalizar_som(
    valor: Any,
) -> Optional[int | float]:
    """Normaliza nível de som entre 0 e 255."""

    numero = converter_numero(valor)

    return (
        numero
        if (
            numero is not None
            and 0 <= numero <= 255
        )
        else None
    )


def criar_resultado_parser(
    raw: str,
    command: Optional[str] = None,
) -> dict[str, Any]:
    """Cria a estrutura padrão de resultado do parser."""

    return {
        "raw": raw,
        "command": command,
        "id": None,
        "name": None,
        "status": None,
        "sound": None,
        "extra": {},
        "valid": False,
    }