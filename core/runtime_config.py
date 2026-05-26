"""Funções leves de runtime compartilhadas pela interface."""

from core.app_paths import PORTA_CHROME
from services.config_service import carregar_config_app, salvar_config_app


def _normalizar_porta_chrome(porta) -> int:
    try:
        porta_int = int(str(porta).strip())
    except (TypeError, ValueError):
        return PORTA_CHROME
    return porta_int if 1 <= porta_int <= 65535 else PORTA_CHROME


def obter_config_runtime():
    config = carregar_config_app()
    config["chrome_porta"] = _normalizar_porta_chrome(config.get("chrome_porta"))
    return config


def obter_datas_salvas():
    return obter_config_runtime()


def obter_porta_chrome() -> int:
    return obter_config_runtime()["chrome_porta"]


def obter_preferencia_alerta_inicio_mes() -> bool:
    return bool(obter_config_runtime().get("perguntar_limpar_mes", True))


def salvar_datas_processo(apuracao: str, vencimento: str):
    dados = {
        "apuracao": apuracao,
        "vencimento": vencimento,
    }
    salvar_config_app(dados)
    return obter_config_runtime()


def salvar_porta_chrome(porta) -> int:
    porta_normalizada = _normalizar_porta_chrome(porta)
    salvar_config_app({"chrome_porta": porta_normalizada})
    return porta_normalizada


def salvar_preferencia_alerta_inicio_mes(ativo: bool) -> bool:
    valor = bool(ativo)
    salvar_config_app({"perguntar_limpar_mes": valor})
    return valor
