"""
Consulta de CNPJ e Simples Nacional em fontes públicas externas.

O badge da fila não usa histórico local como fonte de verdade: consulta APIs
públicas e mantém apenas um cache curto em memória para evitar repetição.
"""
from __future__ import annotations

import logging
import time
import threading

import requests

log = logging.getLogger(__name__)

_TIMEOUT = 6
_BRASILAPI_URL = "https://brasilapi.com.br/api/cnpj/v1/{}"
_OPENCNPJ_URL = "https://kitana.opencnpj.com/cnpj/{}"
_CNPJA_OPEN_URL = "https://open.cnpja.com/office/{}"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AutoLiquid/1.0)",
    "Accept": "application/json",
}

# ── Cache em memória (TTL de 1 hora) ─────────────────────────────────────────
_CACHE: dict[str, tuple[dict, float]] = {}
_CACHE_TTL = 3600  # segundos
_cache_lock = threading.Lock()


def _cache_get(cnpj: str) -> dict | None:
    with _cache_lock:
        entry = _CACHE.get(cnpj)
        if entry and (time.time() - entry[1]) < _CACHE_TTL:
            return entry[0]
    return None


def _cache_set(cnpj: str, dados: dict) -> None:
    """Só armazena quando optante_simples é definitivo (True ou False)."""
    if dados.get("optante_simples") is not None:
        with _cache_lock:
            _CACHE[cnpj] = (dados, time.time())


def _sim_nao_para_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    texto = str(value).strip().casefold()
    if texto in {"s", "sim", "true", "1", "optante"}:
        return True
    if texto in {"n", "nao", "não", "false", "0", "nao optante", "não optante"}:
        return False
    return None


def _consultar_opencnpj(cnpj: str) -> dict:
    """
    Chama o OpenCNPJ e retorna dict com razao_social, optante_simples e nao_encontrado.
    """
    try:
        r = requests.get(_OPENCNPJ_URL.format(cnpj), timeout=_TIMEOUT, headers=_HEADERS)
        if r.status_code == 404:
            return {"razao_social": "", "optante_simples": None, "nao_encontrado": True}
        if r.status_code == 200:
            payload = r.json()
            d = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(d, dict):
                d = payload if isinstance(payload, dict) else {}
            return {
                "razao_social": str(d.get("razaoSocial") or d.get("razao_social") or "").strip(),
                "optante_simples": _sim_nao_para_bool(d.get("opcaoSimples")),
                "nao_encontrado": False,
            }
    except Exception:
        pass
    return {"razao_social": "", "optante_simples": None, "nao_encontrado": False}


def _consultar_cnpja_open(cnpj: str) -> dict:
    """
    Chama a API pública do CNPJá. Boa como fallback, mas tem limite público baixo.
    """
    try:
        r = requests.get(_CNPJA_OPEN_URL.format(cnpj), timeout=_TIMEOUT, headers=_HEADERS)
        if r.status_code == 404:
            return {"razao_social": "", "optante_simples": None, "nao_encontrado": True}
        if r.status_code == 200:
            d = r.json()
            company = d.get("company") if isinstance(d, dict) else {}
            simples = company.get("simples") if isinstance(company, dict) else {}
            return {
                "razao_social": str(company.get("name") or "").strip() if isinstance(company, dict) else "",
                "optante_simples": simples.get("optant") if isinstance(simples, dict) else None,
                "nao_encontrado": False,
            }
    except Exception:
        pass
    return {"razao_social": "", "optante_simples": None, "nao_encontrado": False}


# ── Consultas externas ───────────────────────────────────────────────────────

def _consultar_brasilapi(cnpj: str) -> dict:
    """
    Chama a BrasilAPI e retorna dict com razao_social, optante_simples e nao_encontrado.
    Nunca lança exceção.
    """
    try:
        r = requests.get(_BRASILAPI_URL.format(cnpj), timeout=_TIMEOUT, headers=_HEADERS)
        if r.status_code == 404:
            return {"razao_social": "", "optante_simples": None, "nao_encontrado": True}
        if r.status_code == 200:
            d = r.json()
            return {
                "razao_social":    str(d.get("razao_social") or "").strip(),
                "optante_simples": d.get("opcao_pelo_simples"),  # True / False / None
                "nao_encontrado":  False,
            }
    except Exception:
        pass
    return {"razao_social": "", "optante_simples": None, "nao_encontrado": False}


# ── Função pública ────────────────────────────────────────────────────────────

def obter_dados_empresa(cnpj_limpo: str) -> dict:
    """
    Retorna dados de CNPJ e status Simples Nacional.

    Fluxo:
      1. Cache em memória (TTL 1 h) → retorno instantâneo
      2. OpenCNPJ → limite público maior e campo opcaoSimples
      3. BrasilAPI/CNPJá Open → fallbacks quando a fonte principal falha

    Retorna dict com:
      razao_social     str
      optante_simples  True | False | None
      nao_encontrado   bool
    """
    # 1. Cache em memória
    cached = _cache_get(cnpj_limpo)
    if cached is not None:
        log.debug("CNPJ %s: cache hit — Simples=%s", cnpj_limpo, cached["optante_simples"])
        return cached

    dados = {"razao_social": "", "optante_simples": None, "nao_encontrado": False}
    fonte_usada = ""
    for fonte, consultar in (
        ("OpenCNPJ", _consultar_opencnpj),
        ("BrasilAPI", _consultar_brasilapi),
        ("CNPJa Open", _consultar_cnpja_open),
    ):
        dados = consultar(cnpj_limpo)
        fonte_usada = fonte
        if dados.get("nao_encontrado") or dados.get("optante_simples") is not None:
            break

    if dados.get("nao_encontrado"):
        log.debug("CNPJ %s: não encontrado em %s", cnpj_limpo, fonte_usada)
        return dados

    simples = dados.get("optante_simples")
    razao   = dados.get("razao_social") or ""

    if simples is not None:
        _cache_set(cnpj_limpo, dados)
        log.debug("CNPJ %s: %s — Simples=%s via %s", cnpj_limpo, razao, simples, fonte_usada)
    else:
        log.debug("CNPJ %s: %s — Simples=indisponível nas fontes externas", cnpj_limpo, razao)

    return dados


def verificar_simples_nacional(cnpj_limpo: str) -> bool | None:
    """Retorna True / False / None (falha)."""
    return obter_dados_empresa(cnpj_limpo).get("optante_simples")


if __name__ == "__main__":
    import json
    import sys
    cnpj = sys.argv[1] if len(sys.argv) > 1 else "49161411000158"
    print(json.dumps(obter_dados_empresa(cnpj), ensure_ascii=False, indent=2))
