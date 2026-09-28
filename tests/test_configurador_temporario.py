"""Artefatos por operação; USB simulado, compilador real em um ensaio separado."""
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from configurador.builder import build, build_and_flash
from configurador.compiler import compile_project
from configurador.model import DeviceConfig
from configurador.devices import Device, flash

HEX=b':0100000001FE\n:00000001FF\n'


class TemporaryTests(unittest.TestCase):
    def setUp(self):
        self.projects=[]
        self.device=Device(Path('E:/'),'9904'+'1'*44,123)

    def compiler(self, project):
        self.projects.append(project)
        self.assertIn(' ', str(project))
        self.assertEqual(project.parent,Path(tempfile.gettempdir()))
        (project/'built').mkdir()
        (project/'built/binary.hex').write_bytes(HEX)
        (project/'built/mbcodal-binary.hex').write_bytes(HEX)

    def check_flash(self, firmware, selected):
        self.assertEqual(firmware.read_bytes(),HEX)
        self.assertEqual(selected,self.device)
        self.assertTrue(self.projects[-1].exists())
        return 'Boot não confirmado'

    def assert_clean(self):
        self.assertTrue(self.projects)
        self.assertTrue(all(not p.exists() for p in self.projects))

    def test_sucesso_limpa_apos_uso(self):
        result=build_and_flash(DeviceConfig('estacao'),self.device,self.compiler,self.check_flash)
        self.assertEqual(result,'Boot não confirmado')
        self.assert_clean()

    def test_consecutivas_sem_acumulo(self):
        configs=[DeviceConfig('central'),DeviceConfig('estacao'),DeviceConfig('estacao',42,'SALA','Sala'),DeviceConfig('ponte'),DeviceConfig('estacao',43,'LAB01','Lab')]
        seen=[]
        def flashed(firmware, selected):
            seen.append(json.loads((firmware.parents[1]/'config.json').read_text()))
            return self.check_flash(firmware, selected)
        for config in configs:
            build_and_flash(config,self.device,self.compiler,flashed)
            self.assert_clean()
        self.assertEqual([c['role'] for c in seen],[c.role for c in configs])
        self.assertEqual(seen[-1]['group'],43)
        self.assertEqual(len(set(self.projects)),len(configs))

    def test_falha_compilacao(self):
        def fail(project):
            self.compiler(project)
            raise RuntimeError('falha de compilação')
        with self.assertRaisesRegex(RuntimeError,'compilação'):
            build_and_flash(DeviceConfig('central'),self.device,fail,self.check_flash)
        self.assert_clean()

    def test_falha_gravacao(self):
        def fail(firmware, selected):
            self.check_flash(firmware,selected)
            raise OSError('desconectado durante escrita')
        with self.assertRaises(OSError):
            build_and_flash(DeviceConfig('ponte'),self.device,self.compiler,fail)
        self.assert_clean()

    def test_dispositivo_desconectado_revalidacao_real(self):
        def disconnected(firmware, selected):
            return flash(firmware,selected,scanner=lambda:[])
        with self.assertRaisesRegex(RuntimeError,'ausente'):
            build_and_flash(DeviceConfig('estacao'),self.device,self.compiler,disconnected)
        self.assert_clean()

    def test_remontagem_nao_confirmada_limpa(self):
        with tempfile.TemporaryDirectory() as folder:
            device=Device(Path(folder),'9904'+'1'*44,123)
            scans=iter([[device],[]])
            def disconnected(firmware, selected):
                return flash(firmware,selected,scanner=lambda:next(scans),wait=lambda _:None,checks=1)
            result=build_and_flash(DeviceConfig('central'),device,self.compiler,disconnected)
            self.assertIn('não reapareceu',result)
            self.assert_clean()
            self.assertTrue((device.root/'microserial.hex').exists(),'limpeza não pode apagar arquivo no USB')

    def test_hex_invalido_limpa_sem_flash(self):
        def invalid(project):
            self.compiler(project)
            (project/'built/binary.hex').write_bytes(b'invalido')
        with patch('configurador.devices.flash') as flasher, self.assertRaises(ValueError):
            build_and_flash(DeviceConfig('central'),self.device,invalid,flasher)
        flasher.assert_not_called()
        self.assert_clean()

    def test_permanente_e_cache_alheio_preservados(self):
        with tempfile.TemporaryDirectory(prefix='destino com espacos ') as folder:
            destination=Path(folder)/'guardar.hex'
            cache=Path(folder)/'cache compartilhado';cache.mkdir()
            sentinel=cache/'arquivo';sentinel.write_bytes(b'preservar')
            build(DeviceConfig('estacao'),destination,self.compiler)
            self.assert_clean()
            build_and_flash(DeviceConfig('ponte'),self.device,self.compiler,self.check_flash)
            self.assert_clean()
            self.assertEqual(destination.read_bytes(),HEX)
            self.assertEqual(sentinel.read_bytes(),b'preservar')
            with self.assertRaises(FileExistsError):
                build(DeviceConfig('central'),destination,self.compiler)

    def test_compilacao_oficial_temporaria(self):
        def real(project):
            self.projects.append(project)
            compile_project(project)
        def verify(firmware, selected):
            expected=Path(__file__).resolve().parents[1]/'microbit/firmware/estacao.hex'
            self.assertEqual(firmware.read_bytes(),expected.read_bytes())
            return 'verificado sem USB'
        self.assertEqual(build_and_flash(DeviceConfig('estacao'),self.device,real,verify),'verificado sem USB')
        self.assert_clean()


class DirectGuiTests(unittest.TestCase):
    def test_direto_nao_abre_dialogo_salvar(self):
        import tkinter as tk
        from configurador.gui import App
        root=tk.Tk();root.withdraw();self.addCleanup(root.destroy)
        device=Device(Path('E:/'),'9904'+'1'*44,123)
        with patch('configurador.gui.detect',return_value=[device]):
            app=App(root)
        with patch('configurador.gui.filedialog.asksaveasfilename') as save, \
             patch('configurador.gui.messagebox.askyesno',return_value=True), \
             patch('configurador.gui.build_and_flash',return_value='Boot não confirmado') as direct, \
             patch('configurador.gui.build') as permanent, \
             patch('configurador.gui.messagebox.showinfo'):
            app.start(True)
            deadline=time.monotonic()+2
            while app.results.empty() and time.monotonic()<deadline:
                time.sleep(.01)
            app.poll()
            direct.assert_called_once_with(DeviceConfig('estacao'),device)
            save.assert_not_called();permanent.assert_not_called()
            self.assertEqual(app.status.get(),'Boot não confirmado')
            self.assertFalse(app.busy)


if __name__=='__main__':
    unittest.main()
