"""Estado compartilhado da central MicroSerial."""

from __future__ import annotations

import copy
import threading
from collections import deque
from typing import Any, Optional

from config import HISTORICO_LIMITE


lock_dados = threading.RLock()


dados: dict[str, Any] = {
    "connected": False,
    "central_port": None,
    "last_known_port": None,
    "communication_status": "disconnected",
    "central_last_signal": None,
    "central_last_signal_iso": None,
    "stations": {},
}


ultima_estacao_id: Optional[str] = None


CAMPOS_RESERVADOS_ESTACAO = frozenset({
    "id",
    "name",
    "status",
    "connected",
    "first_seen",
    "last_seen",
    "last_signal",
    "last_seen_iso",
    "interval",
    "average_interval",
    "min_interval",
    "max_interval",
    "signals_received",
    "sound",
    "sound_level",
    "history",
    "extra",
    "last_message",
    "last_raw_message",
    "was_offline",
    "intervals_received",
})


def obter_estado() -> dict[str, Any]:
    """Retorna uma cópia segura do estado atual."""

    with lock_dados:
        estado = copy.deepcopy(dados)

    for estacao in estado["stations"].values():
        if isinstance(
            estacao.get("history"),
            deque,
        ):
            estacao["history"] = list(
                estacao["history"]
            )

    return estado


def atualizar_central(
    **campos: Any,
) -> bool:
    """Atualiza dados da central e informa se houve mudança."""

    with lock_dados:
        mudou = any(
            dados.get(chave) != valor
            for chave, valor in campos.items()
        )

        if mudou:
            dados.update(campos)

        return mudou