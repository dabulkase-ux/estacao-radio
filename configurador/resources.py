"""Recursos imutáveis: repositório em desenvolvimento, _internal/resources no exe."""
from pathlib import Path
import sys
import shutil


def resource_root():
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / 'resources'
    return Path(__file__).resolve().parents[1]


def node_runtime():
    if getattr(sys, 'frozen', False):
        node = resource_root() / 'runtime/node.exe'
        return str(node) if node.is_file() else None
    return shutil.which('node')
