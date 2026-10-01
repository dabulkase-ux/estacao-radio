import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
from configurador import resources
from configurador.compiler import compile_project, ROOT


class DistributionTests(unittest.TestCase):
    def test_recursos_congelados_sem_cwd(self):
        with patch.object(sys,'frozen',True,create=True), patch.object(sys,'_MEIPASS','C:/Aplicativo á/_internal',create=True):
            self.assertEqual(resources.resource_root(),Path('C:/Aplicativo á/_internal/resources'))

    def test_node_privado_sem_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(sys,'frozen',True,create=True), patch.object(sys,'_MEIPASS',folder,create=True), patch('shutil.which') as which:
                self.assertIsNone(resources.node_runtime())
                node=Path(folder)/'resources/runtime/node.exe';node.parent.mkdir(parents=True);node.write_bytes(b'test')
                self.assertEqual(resources.node_runtime(),str(node))
                which.assert_not_called()

    def test_subprocesso_isolado_guard_offline(self):
        with tempfile.TemporaryDirectory() as folder:
            project=Path(folder)
            with patch('configurador.compiler.subprocess.run') as run:
                run.return_value.returncode=0
                compile_project(project)
                args,kw=run.call_args
                self.assertIn('--no-global-search-paths',args[0])
                self.assertIn(str(ROOT/'tools/offline_guard.js'),args[0])
                self.assertEqual(kw['cwd'],project)
                self.assertNotIn('NODE_OPTIONS',kw['env'])
                self.assertNotIn('PXT_ACCESS_TOKEN',kw['env'])
                self.assertEqual(kw['env']['USERPROFILE'],str(project/'profile'))

    def test_guard_recusa_rede_e_processos(self):
        import subprocess
        node=shutil.which('node')
        for expression in ["require('https').get('https://example.com')", "require('net').connect(80,'127.0.0.1')", "require('child_process').spawn('npm')"]:
            result=subprocess.run([node,'--require',str(ROOT/'tools/offline_guard.js'),'-e',expression],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('offline',result.stderr)


if __name__=='__main__':
    unittest.main()
