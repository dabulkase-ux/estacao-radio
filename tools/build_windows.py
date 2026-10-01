"""Build Windows onedir. Não instala dependências nem modifica a distribuição anterior."""
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
NAME = 'Dualkase MicroSerial Configurator'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def excluded(folder, names):
    return [n for n in names if n in ('.git','.bin','__pycache__','test','tests','__tests__','example','examples','.github','coverage') or n.startswith('.env') or n.endswith('.log')]


def prune_runtime(app):
    runtime=(app/'_internal/resources/.makecode-check/node_modules').resolve()
    assert runtime.is_relative_to((ROOT/'dist').resolve())
    for folder, dirs, names in os.walk(runtime):
        for name in excluded(folder, dirs + names):
            target=Path(folder)/name
            assert target.resolve().is_relative_to(runtime)
            if target.is_dir():
                shutil.rmtree(target)
                dirs.remove(name)
            else:
                target.unlink()


def main():
    if os.name != 'nt' or sys.maxsize <= 2**32:
        raise SystemExit('Build requer Windows x64 com Python x64.')
    pack = ROOT/'.makecode-check/packaging-venv/Scripts/python.exe'
    if not pack.is_file():
        raise SystemExit('Prepare o ambiente de build conforme DISTRIBUICAO_WINDOWS.md.')
    if subprocess.check_output([str(pack),'-c','import platform; print(platform.python_version())'],text=True).strip() != '3.13.12':
        raise SystemExit('Build fixada em Python 3.13.12 x64.')
    node = shutil.which('node')
    if not node or subprocess.check_output([node,'--version'],text=True).strip() != 'v24.18.0':
        raise SystemExit('Build requer Node.js 24.18.0 x64.')
    if subprocess.check_output([node,'-p','process.arch'],text=True).strip() != 'x64':
        raise SystemExit('Node deve ser x64.')
    modules = ROOT/'.makecode-check/node_modules'
    lock = json.loads((ROOT/'packaging/package-lock.json').read_text())
    for relative, meta in lock['packages'].items():
        if not relative:
            continue
        if meta.get('os') and 'win32' not in meta['os']:
            continue  # Dependências opcionais de outras plataformas (ex.: fsevents).
        package = ROOT/'.makecode-check'/relative/'package.json'
        if not package.is_file() or json.loads(package.read_text(encoding='utf-8'))['version'] != meta['version']:
            raise SystemExit('Dependências npm diferem do lock: '+relative)
    # Dependências de build fixadas, sem capturar pacotes do Python global.
    versions = json.loads(subprocess.check_output([str(pack),'-m','pip','list','--format=json'],text=True))
    installed = {p['name'].lower():p['version'] for p in versions}
    for line in (ROOT/'packaging/requirements-build.txt').read_text(encoding='utf-8-sig').splitlines():
        name, version = line.split('==')
        if installed.get(name.lower()) != version:
            raise SystemExit('Dependência de build incorreta: '+name)
    output = ROOT/'dist'/('windows-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    output.mkdir(parents=True,exist_ok=False)
    workspace = ROOT/'.makecode-check'
    with tempfile.TemporaryDirectory(prefix='package ',dir=workspace) as temporary:
        work = Path(temporary)
        # Só o entrypoint e módulos importados; não coleta o repositório como dados.
        command=[str(pack),'-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed','--noupx',
                 '--name',NAME,'--paths',str(ROOT),'--distpath',str(output),'--workpath',str(work/'build'),
                 '--specpath',str(work),str(ROOT/'packaging/entry.py')]
        subprocess.run(command,cwd=ROOT,check=True)
    app = output/NAME
    resources = app/'_internal/resources'
    resources.mkdir()
    runtime = resources/'runtime';runtime.mkdir()
    shutil.copyfile(node,runtime/'node.exe')
    for folder, names in {'tools':['compilar_configurado.js','gerar_makecode.js','offline_guard.js'],
                          'microbit':['protocolo.ts','central.ts','estacao.ts','ponte.ts']}.items():
        (resources/folder).mkdir()
        for name in names:
            shutil.copyfile(ROOT/folder/name,resources/folder/name)
    shutil.copytree(modules,resources/'.makecode-check/node_modules',ignore=excluded)
    # Cache de projeto não é necessário: alvo oficial contém bundledpkgs e hexcache.
    expected={role:json.loads((ROOT/f'microbit/firmware/{role}.json').read_text())['hexSha256'] for role in ('central','estacao','ponte')}
    (resources/'expected-firmware.json').write_text(json.dumps(expected,indent=2),encoding='utf-8')
    licenses=app/'LICENSES';licenses.mkdir()
    shutil.copyfile(Path(sys.base_prefix)/'LICENSE.txt',licenses/'Python.txt')
    node_license=ROOT/'packaging/Node-LICENSE.txt'
    if not node_license.is_file():
        raise SystemExit('Falta packaging/Node-LICENSE.txt da versão fixada.')
    shutil.copyfile(node_license,licenses/'Node.txt')
    shutil.copyfile(pack.parents[1]/'Lib/site-packages/pyinstaller-6.22.0.dist-info/licenses/COPYING.txt',licenses/'PyInstaller.txt')
    (app/'LEIA-ME.txt').write_text('Dualkase Technologies\nAbra Dualkase MicroSerial Configurator.exe.\nMantenha toda esta pasta junto; não copie só o EXE.\nNão requer Python/Node/npm instalados. Compilação offline.\nGerar HEX salva um arquivo. Gerar e gravar usa temporários.\nFeche o gateway antes de gravar.\nBuild não assinada; valide a procedência antes de executar.\n',encoding='utf-8')
    audit(app)
    print('Distribuição criada: '+str(app))
    subprocess.run([sys.executable, str(ROOT/'tools/test_windows_distribution.py'), str(app)], check=True)
    print('Validação isolada aprovada. Ainda requer teste USB e outro Windows limpo.')


def audit(app):
    files=[p for p in app.rglob('*') if p.is_file() and p != app/'manifest.json']
    forbidden=[]
    private=os.fsencode(str(Path.home()))
    sizes={}
    hashes={}
    for p in files:
        if p.name.startswith('.env') or '.git' in p.parts or p.suffix=='.log':
            forbidden.append(str(p.relative_to(app)))
        data=p.read_bytes()
        if re.search(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----\s+[A-Za-z0-9+/=\r\n]{80,}',data):
            forbidden.append(str(p.relative_to(app))+' (chave privada)')
        if b'MICROSERIAL_GATEWAY_TOKEN' in data or b'GATEWAY_TOKEN=' in data:
            forbidden.append(str(p.relative_to(app))+' (configuração gateway inesperada)')
        if private.lower() in data.lower() or str(Path.home()).encode('utf-16-le').lower() in data.lower():
            forbidden.append(str(p.relative_to(app))+' (caminho privado)')
        hashes[str(p.relative_to(app))]=hashlib.sha256(data).hexdigest()
        key='Python/Tk/app'
        if '/resources/runtime/' in p.as_posix():key='Node'
        if '/node_modules/' in p.as_posix():key='PXT/dependências'
        sizes[key]=sizes.get(key,0)+p.stat().st_size
    if forbidden:
        raise RuntimeError('Auditoria recusou distribuição: '+str(forbidden[:20]))
    manifest={'sizes_bytes':sizes,'total_bytes':sum(sizes.values()),'files':hashes}
    (app/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
