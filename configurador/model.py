from dataclasses import dataclass
import re


@dataclass(frozen=True)
class DeviceConfig:
    role: str
    group: int = 42
    station_id: str = 'QUARTO'
    name: str = 'Quarto'

    def validated(self):
        if self.role not in ('central', 'estacao', 'ponte'):
            raise ValueError('Selecione Central, Estação ou Ponte.')
        if type(self.group) is not int or not 0 <= self.group <= 255:
            raise ValueError('Rede deve ser um número inteiro entre 0 e 255.')
        if self.role != 'estacao':
            return DeviceConfig(self.role, self.group)
        # Uppercase ASCII apenas: não transformar caracteres Unicode em IDs válidos.
        if not isinstance(self.station_id, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{2,8}', self.station_id):
            raise ValueError('ID: use 2–8 caracteres A-Z, 0-9, _ ou - (sem espaços).')
        try:
            units = len(self.name.encode('utf-16-le')) // 2
        except (AttributeError, UnicodeError):
            raise ValueError('Nome contém caracteres Unicode inválidos.') from None
        if not 1 <= units <= 24 or any(ord(c) < 32 or c in '|:' for c in self.name):
            raise ValueError('Nome: 1–24 unidades UTF-16; sem |, : ou controles abaixo de U+0020.')
        return DeviceConfig(self.role, self.group, self.station_id.upper(), self.name)

    @property
    def filename(self):
        c = self.validated()
        return f'{c.role}{"-" + c.station_id if c.role == "estacao" else ""}-rede{c.group}.hex'
