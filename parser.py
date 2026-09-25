"""Parser das mensagens recebidas pelo rádio."""

from __future__ import annotations

from typing import Any
import re

from config import MAX_MENSAGEM
from utilitarios import (
    criar_resultado_parser,
    normalizar_id,
    normalizar_nome,
    normalizar_som,
    normalizar_status,
)


def extrair_dados_mensagem(
    linha: Any,
) -> dict[str, Any]:

    """Interpreta uma mensagem recebida pela central."""

    raw = (
        ""
        if linha is None
        else str(linha).strip()
    )

    # ========================================================
    # VALIDAÇÃO BÁSICA
    # ========================================================

    if (
        not raw
        or len(raw) > MAX_MENSAGEM
    ):
        return criar_resultado_parser(raw)

    # Formatos emitidos pelos firmwares: cada mensagem identifica a estação.
    # ACK/RETURN são respostas da Central, nunca prova de vida da estação.
    campos = raw.replace(":", "|").split("|")
    cmd = campos[0].upper()
    estritos = {"ID", "NOME", "NAME", "STATUS", "ESTADO", "SOM", "SOUND", "SOUND_LEVEL", "HEARTBEAT"}
    if cmd in {"ACK", "RETURN"}:
        return criar_resultado_parser(raw)
    if cmd == "RADIO" and "=" not in raw:
        info = criar_resultado_parser(raw, cmd)
        if len(campos) < 3 or not re.fullmatch(r"[A-Za-z0-9_-]{2,32}", campos[1]) or not campos[2].strip():
            return info
        info.update(id=campos[1].upper(), name=normalizar_nome(campos[2]))
        i = 3
        while i < len(campos):
            status = normalizar_status(campos[i])
            if status:
                info["status"] = status
                i += 1
            elif campos[i].upper() in {"SOM", "SOUND", "SOUND_LEVEL"} and i + 1 < len(campos):
                som = normalizar_som(campos[i + 1])
                if som is None:
                    return criar_resultado_parser(raw)
                info["sound"] = som
                i += 2
            else:
                return criar_resultado_parser(raw)
        info["valid"] = True
        return info
    if cmd in {"R", "RELAY"}:
        if len(campos) < 4 or not re.fullmatch(r"[0-9]{1,2}", campos[1]):
            return criar_resultado_parser(raw)
        if int(campos[1]) > 15:
            return criar_resultado_parser(raw)
        tipo = {"H": "HEARTBEAT", "S": "SOM", "I": "ID", "N": "NOME", "T": "STATUS"}.get(campos[2].upper())
        if not tipo:
            return criar_resultado_parser(raw)
        info = extrair_dados_mensagem("|".join([tipo] + campos[3:]))
        info["raw"] = raw
        info["extra"].update(protocol=cmd, hops=int(campos[1]))
        return info
    if cmd in estritos and "=" not in raw:
        info = criar_resultado_parser(raw, cmd)
        if len(campos) < 2 or not re.fullmatch(r"[A-Za-z0-9_-]{2,32}", campos[1]):
            return info
        info["id"] = campos[1].upper()
        if cmd == "ID":
            info["valid"] = len(campos) == 2
        elif cmd == "HEARTBEAT":
            info["valid"] = len(campos) in {2, 3} and (len(campos) == 2 or bool(campos[2].strip()))
            info["status"] = "ONLINE"
            if len(campos) == 3:
                info["name"] = normalizar_nome(campos[2])
        elif cmd in {"NOME", "NAME"}:
            if len(campos) == 3:
                info["name"] = normalizar_nome(campos[2])
                info["valid"] = info["name"] is not None
        elif cmd in {"STATUS", "ESTADO"}:
            if len(campos) == 3:
                info["status"] = normalizar_status(campos[2])
                info["valid"] = info["status"] is not None
        else:
            if len(campos) in {3, 4}:
                info["sound"] = normalizar_som(campos[-1])
                info["valid"] = info["sound"] is not None
                if len(campos) == 4:
                    info["name"] = normalizar_nome(campos[2])
        return info

    partes = [
        parte.strip()
        for parte in raw
        .replace(":", "|")
        .split("|")
    ]

    while (
        partes
        and not partes[-1]
    ):
        partes.pop()

    resultado = criar_resultado_parser(raw)

    if not partes:
        return resultado

    # ========================================================
    # FORMATOS LEGADOS
    # ========================================================

    aliases = {
        "id": "id",
        "identificador": "id",
        "station": "id",
        "station_id": "id",

        "nome": "name",
        "name": "name",
        "estacao": "name",
        "station_name": "name",

        "status": "status",
        "estado": "status",

        "som": "sound",
        "sound": "sound",
        "sound_level": "sound",

        "nivel_som": "sound",
        "nivel": "sound",
    }

    posicionais: list[str] = []

    def atribuir(
        campo: str,
        valor: Any,
    ) -> bool:

        atual = resultado[campo]

        if (
            atual is not None
            and valor is not None
            and atual != valor
        ):
            return False

        resultado[campo] = valor

        return True

    # ========================================================
    # CAMPOS
    # ========================================================

    for parte in partes:

        if "=" not in parte:

            posicionais.append(
                parte
            )

            continue

        chave, valor = (
            item.strip()
            for item in parte.split(
                "=",
                1,
            )
        )

        campo = aliases.get(
            chave.lower()
        )

        if campo == "id":

            if not atribuir(
                "id",
                normalizar_id(
                    valor
                ),
            ):
                return criar_resultado_parser(
                    raw
                )

        elif campo == "name":

            if not atribuir(
                "name",
                normalizar_nome(
                    valor
                ),
            ):
                return criar_resultado_parser(
                    raw
                )

        elif campo == "status":

            if not atribuir(
                "status",
                normalizar_status(
                    valor
                ),
            ):
                return criar_resultado_parser(
                    raw
                )

        elif campo == "sound":

            if not atribuir(
                "sound",
                normalizar_som(
                    valor
                ),
            ):
                return criar_resultado_parser(
                    raw
                )

        elif chave:

            resultado["extra"][
                chave.lower()
            ] = valor

    # Não aceitar um campo conhecido inválido só porque havia ID válido.
    for parte in partes:
        if "=" in parte:
            chave, valor = (item.strip() for item in parte.split("=", 1))
            campo = aliases.get(chave.lower())
            if campo and resultado[campo] is None:
                return criar_resultado_parser(raw)

    # ========================================================
    # SEM CAMPOS POSICIONAIS
    # ========================================================

    if not posicionais:

        resultado["valid"] = resultado["id"] is not None

        return resultado

    # Mixed legacy lines retain explicit IDs; never inherit a previous station.
    if "=" not in raw:
        return criar_resultado_parser(raw)
    campo = aliases.get(posicionais[0].lower())
    conversores = {"id": normalizar_id, "name": normalizar_nome,
                   "status": normalizar_status, "sound": normalizar_som}
    if len(posicionais) == 2 and campo in conversores and resultado["id"]:
        valor = conversores[campo](posicionais[1])
        if valor is None or not atribuir(campo, valor):
            return criar_resultado_parser(raw)
    else:
        posicional = extrair_dados_mensagem("|".join(posicionais))
        if not posicional["valid"]:
            return criar_resultado_parser(raw)
        for campo in ("id", "name", "status", "sound"):
            valor = posicional[campo]
            if valor is not None and not atribuir(campo, valor):
                return criar_resultado_parser(raw)
    resultado["command"] = posicionais[0].upper()
    resultado["valid"] = resultado["id"] is not None
    return resultado
