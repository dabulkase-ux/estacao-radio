import hashlib
import json
import shutil
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from configurador.model import DeviceConfig
from configurador.builder import build
from configurador.compiler import ROOT, compile_project, validate_hex
from configurador.devices import detect, flash, Device

HEX = b':0100000001FE\n:00000001FF\n'
UID = '9904' + '1' * 44


class ConfigTests(unittest.TestCase):
    def test_id_normalizado(self):
        self.assertEqual(DeviceConfig('estacao', station_id='sala_1').validated().station_id, 'SALA_1')

    def test_ids_invalidos(self):
        for value in ('A', 'NOVELETRA', 'sala x', 'ÁREA', 'AA|B', '../x', 'ßa', ''):
            with self.subTest(value=value), self.assertRaises(ValueError):
                DeviceConfig('estacao', station_id=value).validated()

    def test_grupos_invalidos(self):
        for value in (-1, 256, True, 1.5, '42'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                DeviceConfig('ponte', value).validated()
        for group in (0, 42, 255):
            self.assertEqual(DeviceConfig('central', group).validated().group, group)

    def test_nome_utf16_e_injecao(self):
        self.assertEqual(DeviceConfig('estacao', name='😀'*12).validated().name, '😀'*12)
        for value in ('', '😀'*13, 'a|b', 'a:b', 'a\nb', '\ud800'):
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                DeviceConfig('estacao', name=value).validated()
        DeviceConfig('estacao', name='Aspas " e \\ acentuação').validated()

    def test_campos_por_papel(self):
        self.assertEqual(DeviceConfig('central', name='ignorado').filename, 'central-rede42.hex')
        self.assertEqual(DeviceConfig('ponte',255).filename, 'ponte-rede255.hex')
        self.assertEqual(DeviceConfig('estacao').filename, 'estacao-QUARTO-rede42.hex')
        with self.assertRaises(ValueError):
            DeviceConfig('outro').validated()

    def test_hex_checksum_estrutura(self):
        validate_hex(HEX)
        for data in (b'', HEX.replace(b'FE',b'FF'), HEX[:-12], b'abc', b':00000001FF\n'):
            with self.subTest(data=data), self.assertRaises(ValueError):
                validate_hex(data)

    def test_falha_compilacao_sem_destino(self):
        with tempfile.TemporaryDirectory() as folder:
            dest=Path(folder)/'saida.hex'
            def fail(project):
                raise RuntimeError('compilação falhou')
            with self.assertRaises(RuntimeError):
                build(DeviceConfig('central'),dest,compiler=fail)
            self.assertFalse(dest.exists())

    def test_destino_existente_nao_compila(self):
        with tempfile.TemporaryDirectory() as folder:
            dest=Path(folder)/'saida.hex';dest.write_bytes(b'original')
            with patch('configurador.builder.compile_project') as compiler, self.assertRaises(FileExistsError):
                build(DeviceConfig('central'),dest,compiler=compiler)
            compiler.assert_not_called()
            self.assertEqual(dest.read_bytes(),b'original')

    def test_compilador_ausente_e_timeout(self):
        with patch('configurador.compiler.shutil.which',return_value=None), self.assertRaises(RuntimeError):
            compile_project(ROOT)
        import subprocess
        with patch('configurador.compiler.subprocess.run',side_effect=subprocess.TimeoutExpired('node',300)), self.assertRaises(RuntimeError):
            compile_project(ROOT)


class UsbTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.hex=self.root/'test.hex';self.hex.write_bytes(HEX)

    def volume(self,name='drive',uid=UID):
        root=self.root/name;root.mkdir()
        (root/'DETAILS.TXT').write_text(f'# DAPLink Firmware\nUnique ID: {uid}\nDaplink Mode: Interface\nInterface Version: 0255\n')
        return root,'MICROBIT',123

    def test_zero(self):
        self.assertEqual(detect([]),[])

    def test_um(self):
        self.assertEqual(len(detect([self.volume()])),1)

    def test_multiplos(self):
        self.assertEqual(len(detect([self.volume(),self.volume('outro','9905'+'2'*44)])),2)

    def test_volume_falso(self):
        v=self.volume();(v[0]/'DETAILS.TXT').write_text('not microbit')
        self.assertEqual(detect([v]),[])

    def test_v1_maintenance_e_label(self):
        v=self.volume(uid='9901'+'1'*44)
        self.assertEqual(detect([v]),[])
        v=self.volume('v2')
        self.assertEqual(detect([(v[0],'MAINTENANCE',123)]),[])
        f=v[0]/'DETAILS.TXT';f.write_text(f.read_text().replace('Interface\n','Bootloader\n'))
        self.assertEqual(detect([v]),[])

    def test_desconectado_antes(self):
        device=detect([self.volume()])[0]
        with self.assertRaises(RuntimeError):
            flash(self.hex,device,scanner=lambda:[],wait=lambda _:None)
        self.assertFalse((device.root/'microserial.hex').exists())

    def test_troca_identidade(self):
        device=detect([self.volume()])[0]
        other=Device(device.root,'9906'+'2'*44,456)
        with self.assertRaises(RuntimeError):
            flash(self.hex,device,scanner=lambda:[other],wait=lambda _:None)

    def test_copia_sem_alterar_outros_arquivos(self):
        device=detect([self.volume()])[0]
        before=(device.root/'DETAILS.TXT').read_bytes()
        result=flash(self.hex,device,scanner=lambda:[device],wait=lambda _:None)
        self.assertIn('Boot e comunicação precisam',result)
        self.assertEqual((device.root/'microserial.hex').read_bytes(),HEX)
        self.assertEqual((device.root/'DETAILS.TXT').read_bytes(),before)

    def test_desconexao_durante_copia(self):
        device=detect([self.volume()])[0]
        original=Path.open
        def opened(path,*args,**kwargs):
            if path.name=='microserial.hex':
                raise OSError('device disconnected')
            return original(path,*args,**kwargs)
        with patch.object(Path,'open',opened), self.assertRaisesRegex(RuntimeError,'interrompida'):
            flash(self.hex,device,scanner=lambda:[device],wait=lambda _:None)

    def test_reconecta_mesmo_id_ou_ausente(self):
        for returns in (True,False):
            with self.subTest(returns=returns):
                device=detect([self.volume(str(returns))])[0]
                calls=iter([[device],[],[device] if returns else []])
                result=flash(self.hex,device,scanner=lambda:next(calls),wait=lambda _:None,checks=2)
                self.assertIn('sem FAIL' if returns else 'não reapareceu',result)

    def test_fail_txt(self):
        device=detect([self.volume()])[0]
        (device.root/'FAIL.TXT').write_text('error')
        with self.assertRaisesRegex(RuntimeError,'FAIL.TXT'):
            flash(self.hex,device,scanner=lambda:[device],wait=lambda _:None)

    def test_nao_sobrescreve_hex_usb(self):
        device=detect([self.volume()])[0];target=device.root/'microserial.hex';target.write_bytes(b'old')
        with self.assertRaises(RuntimeError):
            flash(self.hex,device,scanner=lambda:[device],wait=lambda _:None)
        self.assertEqual(target.read_bytes(),b'old')


@unittest.skipUnless(shutil.which('node') and (ROOT/'.makecode-check/node_modules/pxt-core').exists(), 'requer preparação PXT oficial')
class OfficialBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='config teste com espacos ')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.folder=Path(cls.temp.name)
        cls.before={p:p.read_bytes() for p in (ROOT/'microbit').rglob('*') if p.is_file()}
        cls.outputs={}
        configs=[DeviceConfig('central'),DeviceConfig('ponte'),DeviceConfig('estacao'),
                 DeviceConfig('estacao',42,'SALA','Sala'),DeviceConfig('estacao',43,'SALA','Sala'),
                 DeviceConfig('central',0),DeviceConfig('ponte',255)]
        for c in configs:
            cls.outputs[c.filename]=build(c,cls.folder/c.filename).read_bytes()

    def test_defaults_identicos_checkpoint(self):
        for role in ('central','ponte','estacao'):
            c=DeviceConfig(role)
            self.assertEqual(self.outputs[c.filename],(ROOT/f'microbit/firmware/{role}.hex').read_bytes())

    def test_duas_estacoes(self):
        self.assertNotEqual(self.outputs['estacao-QUARTO-rede42.hex'],self.outputs['estacao-SALA-rede42.hex'])

    def test_duas_redes(self):
        self.assertNotEqual(self.outputs['estacao-SALA-rede42.hex'],self.outputs['estacao-SALA-rede43.hex'])
        self.assertNotEqual(self.outputs['central-rede0.hex'],self.outputs['central-rede42.hex'])
        self.assertNotEqual(self.outputs['ponte-rede255.hex'],self.outputs['ponte-rede42.hex'])

    def test_hex_oficiais(self):
        for data in self.outputs.values():
            validate_hex(data)

    def test_repetida(self):
        data=build(DeviceConfig('estacao'),self.folder/'repetido.hex').read_bytes()
        self.assertEqual(data,self.outputs['estacao-QUARTO-rede42.hex'])

    def test_fontes_inalterados(self):
        self.assertEqual(self.before,{p:p.read_bytes() for p in (ROOT/'microbit').rglob('*') if p.is_file()})

    def test_aspas_em_nome_e_ast(self):
        project=self.folder/'fonte';project.mkdir()
        c=DeviceConfig('estacao',42,'SALA','Aspas " e \\').validated()
        (project/'config.json').write_text(json.dumps(asdict(c)),encoding='utf-8')
        compile_project(project,source_only=True)
        text=(project/'main.ts').read_text(encoding='utf-8')
        self.assertIn('let NOME_ESTACAO = '+json.dumps(c.name),text)
        self.assertIn('let INTERVALO_SOM = 200',text)
        self.assertIn('let picoSom = -1',text)


class GuiTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from configurador.gui import App
        self.root=tk.Tk();self.root.withdraw()
        self.addCleanup(self.root.destroy)
        with patch('configurador.gui.detect',return_value=[]):
            self.app=App(self.root)

    def test_campos_e_sem_dispositivo(self):
        self.assertEqual(self.app.device_box.current(),-1)
        self.app.role.set('central');self.app.fields()
        self.assertEqual(self.app.station.winfo_manager(),'')
        self.app.role.set('estacao');self.app.fields()
        self.assertEqual(self.app.station.winfo_manager(),'pack')

    def test_multiplos_sem_escolha_silenciosa(self):
        devices=[Device(Path('E:/'),UID,1),Device(Path('F:/'),'9905'+'2'*44,2)]
        with patch('configurador.gui.detect',return_value=devices):
            self.app.refresh()
        self.assertEqual(self.app.device_box.current(),-1)
        with patch('configurador.gui.messagebox.showerror') as error, patch('configurador.gui.build') as builder:
            self.app.start(True)
        error.assert_called_once();builder.assert_not_called()

    def test_invalido_nao_compila(self):
        self.app.group.set('256')
        with patch('configurador.gui.messagebox.showerror') as error, patch('configurador.gui.build') as builder:
            self.app.start(False)
        error.assert_called_once();builder.assert_not_called()

    def test_gui_despacha_configuracao_para_worker(self):
        import time
        self.app.station_id.set('sala')
        self.app.name.set('Sala')
        with tempfile.TemporaryDirectory() as folder:
            destination=Path(folder)/'sala.hex'
            with patch('configurador.gui.filedialog.asksaveasfilename',return_value=str(destination)), \
                 patch('configurador.gui.build',return_value=destination) as builder, \
                 patch('configurador.gui.messagebox.showinfo') as info:
                self.app.start(False)
                deadline=time.monotonic()+2
                while self.app.results.empty() and time.monotonic()<deadline:
                    time.sleep(.01)
                self.app.poll()
                builder.assert_called_once_with(DeviceConfig('estacao',42,'SALA','Sala'),destination)
                info.assert_called_once()
                self.assertFalse(self.app.busy)


if __name__=='__main__':
    unittest.main()
