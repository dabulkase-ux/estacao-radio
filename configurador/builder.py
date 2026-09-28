"""Gera em diretório isolado, publica somente o HEX validado, sem sobrescrever."""
from dataclasses import asdict
from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
from .compiler import compile_project, validate_hex
from .model import DeviceConfig
from .devices import flash


@contextmanager
def temporary_firmware(config: DeviceConfig, compiler=compile_project):
    """O consumidor mantém o contexto aberto até terminar de usar o HEX."""
    config = config.validated()
    with tempfile.TemporaryDirectory(prefix='microserial firmware ') as folder:
        project = Path(folder)
        (project / 'config.json').write_text(json.dumps(asdict(config), ensure_ascii=True), encoding='utf-8')
        compiler(project)
        firmware = project / 'built/binary.hex'
        validate_hex(firmware.read_bytes())
        if not (project / 'built/mbcodal-binary.hex').is_file():
            raise RuntimeError('Compilação sem variante micro:bit V2.')
        yield firmware


def build_and_flash(config, selected, compiler=compile_project, flasher=flash):
    """Não publica arquivo local: limpa após flash/observação, inclusive em exceções."""
    with temporary_firmware(config, compiler) as firmware:
        return flasher(firmware, selected)


def build(config: DeviceConfig, destination: Path, compiler=compile_project):
    config = config.validated()
    destination = Path(destination).absolute()
    if destination.suffix.lower() != '.hex':
        raise ValueError('Selecione um arquivo com extensão .hex.')
    if destination.exists():
        raise FileExistsError('Arquivo já existe. Escolha outro nome; nada foi sobrescrito.')
    if os.name == 'nt':
        import ctypes
        if ctypes.windll.kernel32.GetDriveTypeW(str(destination.anchor)) == 2:
            raise ValueError('Salve no computador. Para USB use Gerar e gravar, com verificação do dispositivo.')
    with temporary_firmware(config, compiler) as firmware:
        data = firmware.read_bytes()
        # Criação exclusiva inclusive se outro processo criou o destino durante o build.
        with destination.open('xb') as output:
            try:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            except OSError:
                output.close()
                destination.unlink(missing_ok=True)  # Somente arquivo criado por esta chamada.
                raise
    return destination
