"""Configuração central de logging."""

import logging

from core.app_paths import CAMINHO_LOG


def configurar_logging() -> None:
    logging.basicConfig(
        filename=str(CAMINHO_LOG),
        level=logging.ERROR,
        format="%(asctime)s  %(levelname)s  %(message)s",
        encoding="utf-8",
    )
