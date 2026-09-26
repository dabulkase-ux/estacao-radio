"""Launcher Windows; não altera a inicialização direta de app_radio.py."""
import argparse
import importlib.metadata
import os
from pathlib import Path
import runpy
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_URL = "https://estacao-radio-gules.vercel.app/"


def abertura_unica():
    solicitada = False

    def abrir():
        nonlocal solicitada
        if solicitada:
            return
        solicitada = True
        try:
            # ShellExecute abre a URL no navegador padrão sem esperar seu fechamento.
            os.startfile(FRONTEND_URL)
        except Exception:
            print("[AVISO] Nao foi possivel abrir o navegador. Acesse " + FRONTEND_URL)

    return abrir


class ErroInicializacao(Exception):
    """Mensagem fixa e segura para o usuário, sem valores de configuração."""


def dependencias_prontas(root):
    # requirements.txt deste projeto contém versões fixas, uma por linha.
    for linha in (root / "requirements.txt").read_text(encoding="utf-8").splitlines():
        linha = linha.split("#", 1)[0].strip()
        if not linha:
            continue
        nome, versao = linha.split("==", 1)
        try:
            if importlib.metadata.version(nome.strip()) != versao.strip():
                return False
        except importlib.metadata.PackageNotFoundError:
            return False
    return True


def carregar_configuracao(root):
    from dotenv import dotenv_values

    # Sem interpolação: ${...}, %, !, = e outros caracteres são dados, não código.
    valores = dotenv_values(root / ".env", encoding="utf-8-sig", interpolate=False)
    url = (valores.get("MICROSERIAL_BACKEND_URL") or "").strip()
    token = (valores.get("MICROSERIAL_GATEWAY_TOKEN") or "").strip()
    placeholders = ("COLOQUE", "SUBSTITUA", "SEU-TOKEN", "SEU_TOKEN", "TOKEN_PRIVADO", "COLE-O")
    if not token or any(p in token.upper() for p in placeholders):
        raise ErroInicializacao("Configure um token privado valido em MICROSERIAL_GATEWAY_TOKEN no .env.")
    if not url or any(p in url.upper() for p in ("SEU-BACKEND", "URL-DO", "EXAMPLE", "COLOQUE")):
        raise ErroInicializacao("Configure a URL real em MICROSERIAL_BACKEND_URL no .env.")
    for nome, valor in valores.items():
        if nome.startswith("MICROSERIAL_") and valor is not None:
            os.environ[nome] = valor
    os.environ["MICROSERIAL_BACKEND_URL"] = url
    os.environ["MICROSERIAL_GATEWAY_TOKEN"] = token
    from gateway_remote import PublicadorRemoto
    try:
        PublicadorRemoto(url, token)  # Só valida; não conecta.
    except (ValueError, TypeError):
        raise ErroInicializacao("URL ou token invalidos no .env. Use origem HTTPS e token ASCII de 32+ caracteres sem espacos.") from None


def executar(root=ROOT, local=False):
    os.chdir(root)
    if not (root / ".env").is_file():
        raise ErroInicializacao("Arquivo .env nao encontrado. Copie .env.example para .env e configure o token privado.")
    python = root / ".venv" / "Scripts" / "python.exe"
    if not python.is_file():
        print("[INFO] Criando ambiente .venv...", flush=True)
        try:
            subprocess.run([sys.executable, "-m", "venv", str(root / ".venv")], check=True)
        except (OSError, subprocess.CalledProcessError):
            raise ErroInicializacao("Falha ao criar .venv. Confira a instalacao do Python e permissoes da pasta.") from None
    if Path(sys.executable).resolve() != python.resolve():
        return subprocess.call([str(python), str(root / "tools" / "iniciar.py"), *(["--local"] if local else [])])
    if sys.version_info < (3, 10):
        raise ErroInicializacao("Use Python 3.10 ou superior; recrie .venv com essa versao.")
    print("[OK] Ambiente Python encontrado.", flush=True)
    if not dependencias_prontas(root):
        print("[INFO] Instalando dependencias em .venv...", flush=True)
        try:
            subprocess.run([str(python), "-m", "ensurepip"], check=True)
            subprocess.run([str(python), "-m", "pip", "install", "-r", str(root / "requirements.txt")], check=True)
        except (OSError, subprocess.CalledProcessError):
            raise ErroInicializacao("Falha ao instalar dependencias. Confira internet/permissoes e execute iniciar.bat novamente.") from None
    sys.path.insert(0, str(root))
    carregar_configuracao(root)
    print("[OK] Configuracao carregada.", flush=True)
    print("[INFO] Procurando Central micro:bit...", flush=True)
    print("[INFO] Iniciando gateway remoto...", flush=True)
    if local:
        print("[INFO] Interface local: http://127.0.0.1:5000", flush=True)
    sys.argv = [str(root / "app_radio.py"), *([] if local else ["--gateway-only"])]
    if local:
        runpy.run_path(str(root / "app_radio.py"), run_name="__main__")
    else:
        app = runpy.run_path(str(root / "app_radio.py"), run_name="microserial_gateway")
        app["main"](on_started=abertura_unica())
    return 0


def main():
    parser = argparse.ArgumentParser(description="Inicializacao Windows MicroSerial")
    parser.add_argument("--local", action="store_true")
    args = parser.parse_args()
    try:
        return executar(local=args.local)
    except KeyboardInterrupt:
        print("\n[INFO] Encerrado pelo usuario.")
        return 0
    except ErroInicializacao as erro:
        print("[ERRO] " + str(erro))
        return 1
    except Exception:
        print("[ERRO] Nao foi possivel iniciar. Confira .env, .venv e requirements.txt.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
