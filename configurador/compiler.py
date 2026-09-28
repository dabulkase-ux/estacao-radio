"""Interface com o compilador oficial; nenhuma instalação automática."""
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def compile_project(project: Path, source_only=False):
    node = shutil.which('node')
    if not node:
        raise RuntimeError('Node.js não encontrado. Consulte CONFIGURADOR.md (preparação).')
    modules = ROOT / '.makecode-check/node_modules'
    for name, version in (('pxt-microbit', '9.1.1'), ('pxt-core', '13.0.1')):
        try:
            actual = json.loads((modules / name / 'package.json').read_text(encoding='utf-8'))['version']
        except (OSError, ValueError, KeyError):
            raise RuntimeError('Compilador não instalado. Execute a preparação de CONFIGURADOR.md.') from None
        if actual != version:
            raise RuntimeError(f'{name}: esperado {version}, encontrado {actual}.')
    command = [node, str(ROOT / 'tools/compilar_configurado.js'), str(project)]
    if source_only:
        command.append('--source-only')
    try:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=300,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except subprocess.TimeoutExpired:
        raise RuntimeError('Compilação excedeu 5 minutos. Verifique internet/cache e tente novamente.') from None
    if result.returncode:
        # Erros técnicos ficam no projeto temporário durante a execução; nenhuma configuração privada é usada.
        detail = (result.stderr or result.stdout)[-3000:]
        raise RuntimeError('Falha do MakeCode/PXT:\n' + detail)


def validate_hex(data: bytes):
    """Intel HEX universal MakeCode: aceita extensões 0A..0E e exige EOF final."""
    try:
        lines = data.decode('ascii').splitlines()
        records = []
        for line in lines:
            if not line:
                continue
            if not re.fullmatch(r':[0-9a-fA-F]+', line):
                raise ValueError()
            b = bytes.fromhex(line[1:])
            if len(b) < 5 or len(b) != b[0] + 5 or sum(b) % 256:
                raise ValueError()
            if b[3] not in (0, 1, 2, 3, 4, 5, 10, 11, 12, 13, 14):
                raise ValueError()
            if b[3] in (2, 3, 4, 5) and (b[0] != {2:2, 3:4, 4:2, 5:4}[b[3]] or b[1:3] != b'\x00\x00'):
                raise ValueError()
            if records and records[-1][3] == 1:
                raise ValueError()
            if b[3] == 1 and b != bytes.fromhex('00000001ff'):
                raise ValueError()
            records.append(b)
        if not records or records[-1][3] != 1 or not any(b[3] == 0 and b[0] for b in records):
            raise ValueError()
    except (ValueError, UnicodeError, IndexError):
        raise ValueError('Firmware HEX inválido: estrutura/checksum/EOF.') from None
