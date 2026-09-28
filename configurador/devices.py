"""Detecção conservadora de volumes DAPLink V2. Sem comandos de formatação."""
from dataclasses import dataclass
from pathlib import Path
import ctypes
import os
import re
import time
from .compiler import validate_hex


@dataclass(frozen=True)
class Device:
    root: Path
    unique_id: str
    volume_serial: int

    @property
    def label(self):
        return f'MICROBIT ({self.root}) — {self.unique_id[:4]}…{self.unique_id[-8:]}'


def windows_volumes():
    if os.name != 'nt':
        return []
    k = ctypes.windll.kernel32
    mask = k.GetLogicalDrives()
    result = []
    for i in range(26):
        if not mask & (1 << i):
            continue
        root = f'{chr(65+i)}:\\'
        if k.GetDriveTypeW(root) != 2:  # Apenas volume removível, não diretório/compartilhamento.
            continue
        label = ctypes.create_unicode_buffer(261)
        serial = ctypes.c_ulong()
        if k.GetVolumeInformationW(root, label, len(label), ctypes.byref(serial), None, None, None, 0):
            result.append((Path(root), label.value, serial.value))
    return result


def identify(root, label, serial):
    if label.upper() != 'MICROBIT':
        return None
    try:
        with (root / 'DETAILS.TXT').open('r', encoding='ascii', errors='replace') as f:
            details = f.read(8193)
        if len(details) > 8192 or 'DAPLink' not in details:
            return None
        fields = dict(re.findall(r'^([^:\r\n]+):\s*([^\r\n]+)', details, re.M))
        uid = fields.get('Unique ID', '').strip()
        if (not re.fullmatch(r'99(?:03|04|05|06)[0-9a-fA-F]{44}', uid)
                or fields.get('Daplink Mode', '').strip().lower() != 'interface'
                or not re.fullmatch(r'\d{4}', fields.get('Interface Version', '').strip())):
            return None
        return Device(root, uid.lower(), serial)
    except OSError:
        return None


def detect(volumes=None):
    return [d for root, label, serial in (windows_volumes() if volumes is None else volumes)
            if (d := identify(root, label, serial)) is not None]


def flash(firmware: Path, selected: Device, scanner=detect, wait=time.sleep, checks=10):
    data = Path(firmware).read_bytes()
    validate_hex(data)
    # Revalida identidade + volume imediatamente antes da escrita, não aceita letra manual.
    if selected not in scanner():
        raise RuntimeError('Micro:bit selecionado ausente ou identidade mudou. Atualize a lista.')
    target = selected.root / 'microserial.hex'
    if target.exists():
        raise RuntimeError('microserial.hex já existe na unidade; reconecte e verifique antes de tentar.')
    try:
        with target.open('xb') as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
    except OSError:
        raise RuntimeError('Cópia interrompida/recusada. Resultado não confirmado; reconecte e tente novamente. Não houve retry automático.') from None
    # DAPLink pode desmontar/remontar. Não repetir a gravação automaticamente.
    present = False
    for _ in range(checks):
        wait(1)
        matches = [d for d in scanner() if d.unique_id == selected.unique_id]
        present = len(matches) == 1
        if present:
            for name in ('FAIL.TXT', 'ASSERT.TXT'):
                if (matches[0].root / name).exists():
                    raise RuntimeError(f'DAPLink reportou {name}. Inspecione o arquivo; gravação não confirmada.')
    if not present:
        return 'Cópia concluída, mas o dispositivo não reapareceu. Boot não confirmado; reconecte e teste.'
    return 'Cópia concluída; dispositivo presente e sem FAIL.TXT/ASSERT.TXT observado. Boot e comunicação precisam de teste físico.'
