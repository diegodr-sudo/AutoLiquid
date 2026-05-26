"""Serviços de carregamento e persistência de configuração."""

import json
import shutil
from typing import Any

from core.app_paths import (
    CAMINHO_CONFIG,
    CAMINHO_TABELAS,
    PORTA_CHROME,
    caminho_recurso,
)


CONFIG_APP_PADRAO = {
    "apuracao": "",
    "vencimento": "",
    "chrome_porta": PORTA_CHROME,
    "navegador": "chrome",
    "fechar_aba_fila": False,
    "perguntar_limpar_mes": True,
    "tema_web": "light",
    "nivel_log": "desenvolvedor",
    "database_url": "",
    "turso_database_url": "",
    "turso_auth_token": "",
    "database_mode": "turso",
    "nome_usuario": "",
    "nf_servico_alerta_dias_uteis": 3,
    "rocket_chat_url": "https://chat.ufsc.br",
    "rocket_chat_user_id": "",
    "rocket_chat_auth_token": "",
    "rocket_chat_contar": "tudo",
    "data_sources": {
        "fila_processos_atual": {"supabase": False, "turso": True},
        "fila_processos_alertas": {"supabase": False, "turso": True},
        "fila_processos_edicoes": {"supabase": False, "turso": True},
        "servidores_config": {"supabase": False, "turso": True},
        "tabelas_operacionais": {"supabase": False, "turso": True},
        "datas_globais": {"supabase": False, "turso": True},
        "processos": {"supabase": False, "turso": True},
        "execucoes": {"supabase": False, "turso": True},
        "empenhos": {"supabase": False, "turso": True},
        "notas_fiscais_execucao": {"supabase": False, "turso": True},
        "deducoes_execucao": {"supabase": False, "turso": True},
        "execucao_pendencias": {"supabase": False, "turso": True},
        "ausencias": {"supabase": False, "turso": True},
    },
}


def carregar_json(caminho, padrao: Any):
    if not caminho.exists():
        recurso_padrao = caminho_recurso(caminho.name)
        if recurso_padrao.exists():
            caminho.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(recurso_padrao, caminho)

    if caminho.exists():
        with open(caminho, encoding="utf-8") as arquivo:
            return json.load(arquivo)
    return padrao


def salvar_json(caminho, dados: Any) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, indent=2, ensure_ascii=False)


def carregar_config_app():
    dados = carregar_json(CAMINHO_CONFIG, dict(CONFIG_APP_PADRAO))
    if not isinstance(dados, dict):
        dados = {}

    config = {**CONFIG_APP_PADRAO, **dados}
    recurso_padrao = caminho_recurso(CAMINHO_CONFIG.name)
    if recurso_padrao.exists() and recurso_padrao != CAMINHO_CONFIG:
        try:
            with open(recurso_padrao, encoding="utf-8") as arquivo:
                recurso = json.load(arquivo)
        except Exception:
            recurso = {}
        if isinstance(recurso, dict):
            # A release oficial carrega estes dados via GitHub Secrets. Se o
            # Windows ja criou uma configuracao local vazia ou incorreta, use a
            # config embutida para recuperar o login sem intervencao manual.
            campos_release = (
                "turso_database_url",
                "turso_auth_token",
                "database_mode",
            )
            campos_opcionais = (
                "rocket_chat_url",
                "rocket_chat_user_id",
                "rocket_chat_auth_token",
                "rocket_chat_contar",
                "data_sources",
            )
            alterado = False
            for campo in campos_release:
                valor_recurso = recurso.get(campo)
                if valor_recurso not in ("", None, {}, []) and config.get(campo) != valor_recurso:
                    config[campo] = valor_recurso
                    alterado = True
            for campo in campos_opcionais:
                atual = config.get(campo)
                valor_recurso = recurso.get(campo)
                if atual in ("", None, {}, []) and valor_recurso not in ("", None, {}, []):
                    config[campo] = valor_recurso
                    alterado = True
            if alterado:
                salvar_json(CAMINHO_CONFIG, config)
    return config


def salvar_config_app(dados):
    atual = carregar_config_app()
    atual.update(dados)
    salvar_json(CAMINHO_CONFIG, atual)


def carregar_tabelas_config():
    dados = carregar_json(CAMINHO_TABELAS, {})
    if not isinstance(dados, dict):
        dados = {}

    recurso_padrao = caminho_recurso(CAMINHO_TABELAS.name)
    if not recurso_padrao.exists():
        return dados

    try:
        with open(recurso_padrao, encoding="utf-8") as arquivo:
            padrao = json.load(arquivo)
    except Exception:
        return dados

    if not isinstance(padrao, dict):
        return dados

    alterado = False
    for chave, valor in padrao.items():
        atual = dados.get(chave)
        if atual in (None, [], {}):
            dados[chave] = valor
            alterado = True

    if alterado:
        salvar_json(CAMINHO_TABELAS, dados)

    return dados


def salvar_tabelas_config(dados):
    salvar_json(CAMINHO_TABELAS, dados)
