"""Diagnóstico opt-in da distribuição. Não grava USB; produz relatório e HEXs de teste."""
import hashlib
import json
from pathlib import Path
import tkinter as tk
from .builder import build, build_and_flash
from .model import DeviceConfig
from .resources import resource_root, node_runtime
from .gui import App


def run(directory):
    output = Path(directory).absolute()
    output.mkdir(parents=True, exist_ok=False)
    report = {'ok': False, 'checks': []}
    try:
        root = tk.Tk()
        root.withdraw()
        try:
            app = App(root)
            root.update()
            assert app.generate_button.winfo_exists()
            # Campo de escolha continua vazio quando há mais de um dispositivo.
            from .devices import Device
            import configurador.gui as gui
            original = gui.detect
            try:
                gui.detect = lambda: [Device(Path('E:/'), '9904'+'1'*44, 1), Device(Path('F:/'), '9905'+'2'*44, 2)]
                app.refresh()
                assert app.device_box.current() == -1
            finally:
                gui.detect = original
        finally:
            root.destroy()
        report['checks'].append('Tk GUI / seleção múltipla')
        expected = json.loads((resource_root()/'expected-firmware.json').read_text())
        configs = [DeviceConfig(r) for r in ('central','estacao','ponte')]
        configs += [DeviceConfig('estacao',42,'SALA','Sala'),DeviceConfig('estacao',43,'LAB01','Laboratório')]
        hashes = {}
        for config in configs:
            firmware = build(config, output/config.filename)
            digest = hashlib.sha256(firmware.read_bytes()).hexdigest()
            hashes[config.filename] = digest
            if config in configs[:3]:
                assert digest == expected[config.role], 'Firmware padrão diferente: '+config.role
            report['checks'].append(config.filename)
        assert len(set(hashes.values())) == len(configs)
        temporary = []
        def inspect(firmware, selected):
            temporary.append(firmware.parents[1])
            assert firmware.is_file()
            return 'USB simulado'
        for config in configs[:2]:
            assert build_and_flash(config, None, flasher=inspect) == 'USB simulado'
            assert all(not p.exists() for p in temporary)
        report['checks'].append('gravações temporárias consecutivas e limpeza (USB simulado)')
        try:
            build(configs[0], output/configs[0].filename)
            raise AssertionError('sobrescrita permitida')
        except FileExistsError:
            pass
        report.update(ok=True, firmware_sha256=hashes, private_node=Path(node_runtime()).name)
    except Exception as error:
        report['error'] = str(error)
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if report['ok'] else 1
