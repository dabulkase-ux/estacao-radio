"""Entrada do executável; diagnóstico explícito não grava USB."""
import sys
from configurador.gui import main

if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--self-test':
        from configurador.standalone_check import run
        sys.exit(run(sys.argv[2]))
    main()
