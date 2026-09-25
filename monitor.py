"""Monitoramento das estações MicroSerial."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

from config import TIMEOUT_ESTACAO
from estado import dados, lock_dados

logger = logging.getLogger("microserial.monitor")


INTERVALO_MONITORAMENTO = 1.0


def monitorar_estacoes(
    stop_event: Optional[threading.Event] = None,
    enviar_dados: Optional[Callable[[], bool]] = None,
) -> None:
    """
    Monitora a comunicação das estações MicroSerial.

    Regras:
    - A estação é considerada ONLINE enquanto estiver recebendo dados.
    - Qualquer pacote válido recebido pela estação deve atualizar
      o campo `last_seen`.
    - Se o tempo desde `last_seen` ultrapassar TIMEOUT_ESTACAO,
      a estação passa para OFFLINE.
    - A mudança para OFFLINE só é processada uma vez.
    - Quando a estação voltar a enviar dados, ela pode ser marcada
      novamente como ONLINE pelo módulo responsável pelo recebimento.
    """

    while stop_event is None or not stop_event.is_set():
        agora = time.time()
        ficaram_offline: list[str] = []

        with lock_dados:
            stations = dados.get("stations", {})

            for identificador, estacao in stations.items():
                if not isinstance(estacao, dict):
                    logger.warning(
                        "Dados inválidos para estação %s: %r",
                        identificador,
                        estacao,
                    )
                    continue

                last_seen = estacao.get("last_seen")

                # Sem last_seen não temos como determinar timeout.
                if last_seen is None:
                    continue

                try:
                    tempo_sem_sinal = agora - float(last_seen)
                except (TypeError, ValueError):
                    logger.warning(
                        "last_seen inválido para estação %s: %r",
                        identificador,
                        last_seen,
                    )
                    continue

                conectada = bool(estacao.get("connected"))
                status = estacao.get("status")

                if tempo_sem_sinal > TIMEOUT_ESTACAO:
                    # Evita processar a mesma estação repetidamente
                    # enquanto ela continuar offline.
                    if conectada or status != "OFFLINE":
                        estacao.update(
                            {
                                "connected": False,
                                "status": "OFFLINE",
                                "was_offline": True,
                            }
                        )

                        ficaram_offline.append(identificador)

        for identificador in ficaram_offline:
            logger.warning(
                "Estação ficou OFFLINE por falta de sinal: %s",
                identificador,
            )

        if ficaram_offline and enviar_dados:
            try:
                enviar_dados()
            except Exception:
                logger.exception(
                    "Falha ao publicar estado após "
                    "estação ficar offline."
                )

        if stop_event is None:
            time.sleep(INTERVALO_MONITORAMENTO)
        else:
            stop_event.wait(INTERVALO_MONITORAMENTO)