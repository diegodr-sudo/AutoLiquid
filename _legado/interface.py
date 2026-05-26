"""
interface.py — ponto de entrada mínimo da aplicação.
Mantém o bootstrap enxuto para reduzir imports desnecessários no início.
"""

import sys

from ui.bootstrap import criar_aplicacao


def main():
    app, _janela = criar_aplicacao(sys.argv)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
