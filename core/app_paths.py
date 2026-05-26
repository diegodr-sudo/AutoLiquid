"""Caminhos e constantes base da aplicação."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ARQUIVO_CONFIG = "configuracoes.json"
ARQUIVO_TABELAS = "tabelas_config.json"
ARQUIVO_CONTRATOS = "DCF - CONTRATOS.csv"
PORTA_CHROME = 9222
URL_INICIAL = "https://contratos.comprasnet.gov.br/gescon/fatura"


def _resolver_base_recursos() -> Path:
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _resolver_base_dados() -> Path:
    home = Path.home()

    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "AutoLiquid"
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else home / "AppData" / "Roaming"
        return base / "AutoLiquid"
    return home / ".config" / "autoliquid"


DIR_APP = _resolver_base_recursos()
DIR_DADOS = _resolver_base_dados()
DIR_DADOS.mkdir(parents=True, exist_ok=True)

DIR_PERFIL = str(DIR_DADOS / "chrome-profile")
CAMINHO_CONFIG = DIR_DADOS / ARQUIVO_CONFIG
CAMINHO_TABELAS = DIR_DADOS / ARQUIVO_TABELAS
CAMINHO_CONTRATOS = DIR_DADOS / ARQUIVO_CONTRATOS
CAMINHO_LOG = DIR_DADOS / "erros.log"


def caminho_recurso(nome_arquivo: str) -> Path:
    return DIR_APP / nome_arquivo
