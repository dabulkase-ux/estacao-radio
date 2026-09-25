"""Enquadramento serial e remontagem limitada dos nomes do protocolo V1."""
import re
import time
from collections import OrderedDict


class LinhasSerial:
    def __init__(self, limite=512):
        self.limite = limite
        self.buffer = bytearray()
        self.descartar = False

    def alimentar(self, dados):
        linhas = []
        for byte in dados:
            if byte == 10:
                if not self.descartar:
                    try:
                        linhas.append(self.buffer.decode("utf-8").rstrip("\r"))
                    except UnicodeDecodeError:
                        pass
                self.buffer.clear()
                self.descartar = False
            elif not self.descartar:
                self.buffer.append(byte)
                if len(self.buffer) > self.limite:
                    self.buffer.clear()
                    self.descartar = True
        return linhas


class NomesFragmentados:
    def __init__(self):
        self.pendentes = OrderedDict()

    def receber(self, linha):
        agora = time.monotonic()
        for chave, valor in list(self.pendentes.items()):
            if agora - valor[0] > 10:
                del self.pendentes[chave]
        match = re.fullmatch(r"NPART\|([A-Z0-9_-]{2,8})\|([0-9]{1,10})\|([0-9]{1,2})\|([0-9]{1,2})\|([0-9a-fA-F]{2,18})", linha)
        if not match:
            return None
        id_, token, indice, total, hexadecimal = match.groups()
        token, indice, total = int(token), int(indice), int(total)
        if not (token <= 0xFFFFFFFF and 1 <= total <= 16 and 0 <= indice < total) or len(hexadecimal) % 2:
            return None
        parte = bytes.fromhex(hexadecimal)
        capacidade = 11 - len(id_)
        if len(parte) > capacidade or (indice < total - 1 and len(parte) != capacidade):
            return None
        chave = (id_, token)
        if chave not in self.pendentes:
            if len(self.pendentes) >= 32:
                self.pendentes.popitem(last=False)
            self.pendentes[chave] = (agora, total, {})
        _, esperado, partes = self.pendentes[chave]
        if esperado != total or (indice in partes and partes[indice] != parte):
            del self.pendentes[chave]
            return None
        partes[indice] = parte
        if len(partes) != total:
            return None
        del self.pendentes[chave]
        dados = b"".join(partes[i] for i in range(total))
        if len(dados) > 48:
            return None
        try:
            nome = dados.decode("utf-16-le")
        except UnicodeDecodeError:
            return None
        if not nome.strip() or any(ord(c) < 32 or c in "|:" for c in nome):
            return None
        return f"NOME|{id_}|{nome}"
