"""Valida uma cópia fora do repo, sem ferramentas globais no PATH e com perfil vazio."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile


def main():
    app = Path(sys.argv[1]).resolve()
    manifest = json.loads((app/'manifest.json').read_text(encoding='utf-8'))
    for relative, expected in manifest['files'].items():
        assert hashlib.sha256((app/relative).read_bytes()).hexdigest()==expected, relative
    with tempfile.TemporaryDirectory(prefix='Dualkase Estação teste limpo ') as folder:
        base=Path(folder)
        copied=base/'Aplicativo com acentuação e espaços'
        shutil.copytree(app,copied)
        before={str(p.relative_to(copied)):hashlib.sha256(p.read_bytes()).hexdigest() for p in copied.rglob('*') if p.is_file()}
        profile=base/'perfil vazio';profile.mkdir()
        scratch=base/'temporários';scratch.mkdir()
        cwd=base/'fora do aplicativo';cwd.mkdir()
        output=base/'resultados'
        env={k:os.environ[k] for k in ('SystemRoot','WINDIR') if k in os.environ}
        env.update(PATH='', USERPROFILE=str(profile), APPDATA=str(profile), LOCALAPPDATA=str(profile), TEMP=str(scratch), TMP=str(scratch))
        exe=copied/'Dualkase MicroSerial Configurator.exe'
        process=subprocess.run([str(exe),'--self-test',str(output)],cwd=cwd,env=env,timeout=300)
        report=json.loads((output/'report.json').read_text(encoding='utf-8'))
        assert process.returncode==0 and report['ok'], report
        # Prova negativa: sem o cache embarcado não pode recorrer à rede/cache global.
        cache=copied/'_internal/resources/.makecode-check/node_modules/pxt-microbit/built/hexcache'
        hidden=cache.with_name('hexcache-test-disabled')
        assert cache.resolve().is_relative_to(base.resolve()) and hidden.resolve().is_relative_to(base.resolve())
        cache.rename(hidden)
        try:
            negative=base/'sem cache'
            failed=subprocess.run([str(exe),'--self-test',str(negative)],cwd=cwd,env=env,timeout=120)
            failure=json.loads((negative/'report.json').read_text(encoding='utf-8'))
            assert failed.returncode!=0 and not failure['ok'],failure
        finally:
            hidden.rename(cache)
        after={str(p.relative_to(copied)):hashlib.sha256(p.read_bytes()).hexdigest() for p in copied.rglob('*') if p.is_file()}
        assert before==after,'Aplicativo escreveu na pasta de instalação'
        assert not list(scratch.glob('microserial firmware *')),'Temporários residuais'
        report.update(path_empty=True, fresh_profile=True, outside_repository=True, accented_path=True,
                      missing_native_cache_refused=True,
                      installation_unchanged=True, temporary_cleanup=True,
                      network='Node com bloqueio fail-closed; não é VM/Windows limpo físico',
                      usb='simulado; detecção real somente leitura')
        destination=app.parent/'standalone-validation.json'
        destination.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False,indent=2))
        print('Relatório: '+str(destination))


if __name__=='__main__':
    main()
