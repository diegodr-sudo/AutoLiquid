"""Bootstrap enxuto da interface gráfica."""

from PyQt6.QtWidgets import QApplication

from interface_main import AplicativoPrincipal


def criar_aplicacao(argv):
    app = QApplication(argv)
    janela = AplicativoPrincipal()
    janela.show()
    return app, janela
