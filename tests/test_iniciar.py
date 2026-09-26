import contextlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import iniciar

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "launcher-test-only-0123456789!%=$#abcd"


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="microserial launcher ")
        self.root = Path(self.temp.name)
        self.cwd, self.argv, self.path = Path.cwd(), sys.argv[:], sys.path[:]
        self.env = patch.dict(os.environ)
        self.env.start()

    def tearDown(self):
        os.chdir(self.cwd)
        sys.argv, sys.path = self.argv, self.path
        self.env.stop()
        self.temp.cleanup()

    def config(self, token=TOKEN, url="https://estacao-radio-backend.onrender.com"):
        (self.root / ".env").write_text(
            f'# comentario\n MICROSERIAL_BACKEND_URL = "{url}" # comentario\n'
            f"MICROSERIAL_GATEWAY_TOKEN = '{token}'\nPATH=nao-alterar\n", encoding="utf-8-sig")

    def fake_python(self):
        python = self.root / ".venv/Scripts/python.exe"
        python.parent.mkdir(parents=True)
        python.touch()
        return python

    def test_sem_env_nao_cria_ambiente(self):
        with patch.object(iniciar.subprocess, "run") as run:
            with self.assertRaisesRegex(iniciar.ErroInicializacao, "env nao encontrado"):
                iniciar.executar(self.root)
            run.assert_not_called()

    def test_config_aspas_comentarios_bom_e_caracteres_literais(self):
        self.config(token=TOKEN + "${SEM_INTERPOLACAO}")
        path = os.environ["PATH"]
        with contextlib.redirect_stdout(io.StringIO()) as out:
            iniciar.carregar_configuracao(self.root)
        self.assertEqual(os.environ["MICROSERIAL_GATEWAY_TOKEN"], TOKEN + "${SEM_INTERPOLACAO}")
        self.assertEqual(os.environ["PATH"], path)
        self.assertNotIn(TOKEN, out.getvalue())

    def test_token_ausente_vazio_placeholder_e_url_invalida(self):
        for token in ("", "COLOQUE_SEU_TOKEN_AQUI", "<TOKEN_PRIVADO>", "curto"):
            self.config(token)
            with self.assertRaises(iniciar.ErroInicializacao):
                iniciar.carregar_configuracao(self.root)
        for url in ("", "https://SEU-BACKEND.onrender.com", "http://servidor.com", "https://usuario:senha@host.com"):
            self.config(url=url)
            with self.assertRaises(iniciar.ErroInicializacao):
                iniciar.carregar_configuracao(self.root)
        (self.root / ".env").write_text("MICROSERIAL_BACKEND_URL=https://host.com", encoding="utf-8")
        with self.assertRaises(iniciar.ErroInicializacao):
            iniciar.carregar_configuracao(self.root)

    def test_venv_pronto_sem_instalacao_e_argumentos(self):
        self.config()
        python = self.fake_python()
        for local in (False, True):
            with patch.object(sys, "executable", str(python)), patch.object(iniciar, "dependencias_prontas", return_value=True), patch.object(iniciar.subprocess, "run") as install, patch.object(iniciar.runpy, "run_path") as app:
                self.assertEqual(iniciar.executar(self.root, local), 0)
                install.assert_not_called()
                app.assert_called_once_with(str(self.root / "app_radio.py"), run_name="__main__" if local else "microserial_gateway")
                self.assertEqual(sys.argv[1:], [] if local else ["--gateway-only"])

    def test_reentrada_usa_python_do_venv(self):
        self.config()
        python = self.fake_python()
        with patch.object(iniciar.subprocess, "call", return_value=0) as call:
            iniciar.executar(self.root)
        self.assertEqual(call.call_args.args[0][0], str(python))

    def test_navegador_uma_vez_apos_sinal_e_falha_nao_interrompe(self):
        self.config()
        python = self.fake_python()
        for falha in (None, OSError("falha simulada")):
            with patch.object(sys, "executable", str(python)), patch.object(iniciar, "dependencias_prontas", return_value=True), patch.object(iniciar.os, "startfile", create=True, side_effect=falha) as browser:
                def main(on_started):
                    browser.assert_not_called()
                    on_started()
                    on_started()  # Proteção mesmo se alguém repetir o aviso.
                    browser.assert_called_once_with(iniciar.FRONTEND_URL)
                with patch.object(iniciar.runpy, "run_path", return_value={"main": main}):
                    self.assertEqual(iniciar.executar(self.root), 0)

    def test_navegador_nao_abre_sem_config_ou_antes_de_main_pronto(self):
        with patch.object(iniciar.os, "startfile", create=True) as browser:
            with self.assertRaises(iniciar.ErroInicializacao):
                iniciar.executar(self.root)
            self.config("COLOQUE_SEU_TOKEN_AQUI")
            python = self.fake_python()
            with patch.object(sys, "executable", str(python)), patch.object(iniciar, "dependencias_prontas", return_value=True):
                with self.assertRaises(iniciar.ErroInicializacao):
                    iniciar.executar(self.root)
                self.config()
                def main(on_started):
                    raise RuntimeError("falha antes de iniciar")
                with patch.object(iniciar.runpy, "run_path", return_value={"main": main}):
                    with self.assertRaises(RuntimeError):
                        iniciar.executar(self.root)
                with patch.object(iniciar.runpy, "run_path"):
                    self.assertEqual(iniciar.executar(self.root, local=True), 0)
            browser.assert_not_called()

    def test_main_real_sinaliza_somente_apos_threads_iniciarem(self):
        import app_radio
        with patch.object(sys, "argv", ["app_radio.py", "--gateway-only"]), patch("gateway_remote.configurar_publicador"), patch.object(app_radio.threading, "Thread") as thread, patch.object(app_radio.threading, "Event") as event:
            event.return_value.wait.return_value = True
            chamadas = []
            def pronto():
                self.assertEqual(thread.return_value.start.call_count, 3)
                chamadas.append(True)
            app_radio.main(on_started=pronto)
            self.assertEqual(chamadas, [True])
            event.return_value.set.assert_called_once()

    def test_main_real_nao_sinaliza_quando_thread_falha(self):
        import app_radio
        from unittest.mock import Mock
        pronto = Mock()
        with patch.object(sys, "argv", ["app_radio.py", "--gateway-only"]), patch("gateway_remote.configurar_publicador"), patch.object(app_radio.threading, "Thread") as thread:
            thread.return_value.start.side_effect = RuntimeError("falha simulada")
            with self.assertRaises(RuntimeError):
                app_radio.main(on_started=pronto)
            pronto.assert_not_called()

    def test_falhas_setup_nao_executam_app(self):
        self.config()
        with patch.object(iniciar.subprocess, "run", side_effect=OSError), patch.object(iniciar.runpy, "run_path") as app:
            with self.assertRaisesRegex(iniciar.ErroInicializacao, "criar .venv"):
                iniciar.executar(self.root)
            app.assert_not_called()
        python = self.fake_python()
        with patch.object(sys, "executable", str(python)), patch.object(iniciar, "dependencias_prontas", return_value=False), patch.object(iniciar.subprocess, "run", side_effect=[None, OSError()]), patch.object(iniciar.runpy, "run_path") as app:
            with self.assertRaisesRegex(iniciar.ErroInicializacao, "instalar dependencias"):
                iniciar.executar(self.root)
            app.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "cmd.exe requer Windows")
    def test_bat_real_venv_caminho_com_espacos_e_sem_env(self):
        for filename in ("iniciar.bat", "iniciar-local.bat", "gateway_remote.py", "estado.py", "config.py", "requirements.txt"):
            shutil.copy2(ROOT / filename, self.root / filename)
        (self.root / "tools").mkdir()
        shutil.copy2(ROOT / "tools/iniciar.py", self.root / "tools/iniciar.py")
        def run(name):
            return subprocess.run(["cmd.exe", "/d", "/c", name], cwd=self.root,
                                  input="\n", capture_output=True, text=True, timeout=40)
        missing = run("iniciar.bat")
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("env nao encontrado", missing.stdout)
        self.config()
        unavailable = subprocess.run([os.environ["COMSPEC"], "/d", "/c", "iniciar.bat"],
                                     cwd=self.root, env={**os.environ, "PATH": ""},
                                     input="\n", capture_output=True, text=True, timeout=10)
        self.assertNotEqual(unavailable.returncode, 0)
        self.assertIn("Python nao encontrado", unavailable.stdout)
        subprocess.run([sys.executable, "-m", "venv", "--system-site-packages", str(self.root / ".venv")], check=True, capture_output=True)
        (self.root / "app_radio.py").write_text(
            "import sys, os\nfrom pathlib import Path\n"
            "assert Path(sys.executable).parent.parent == Path.cwd() / '.venv'\n"
            "assert os.environ['MICROSERIAL_GATEWAY_TOKEN']\n"
            "print('APP_ARGS=' + repr(sys.argv[1:]))\n"
            "def main(on_started=None): pass\n", encoding="utf-8")
        for bat, args in (("iniciar.bat", "['--gateway-only']"), ("iniciar-local.bat", "[]")):
            result = run(bat)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("APP_ARGS=" + args, result.stdout)
            self.assertNotIn(TOKEN, result.stdout + result.stderr)
            self.assertNotIn("Instalando dependencias", result.stdout)
        self.config("COLOQUE_SEU_TOKEN_AQUI")
        invalid = run("iniciar.bat")
        self.assertNotEqual(invalid.returncode, 0)
        self.assertNotIn("APP_ARGS", invalid.stdout)


if __name__ == "__main__":
    unittest.main()
