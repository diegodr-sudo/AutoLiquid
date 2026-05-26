"""
Consulta de CNPJ e Simples Nacional via BrasilAPI.

Usa exclusivamente a BrasilAPI (brasilapi.com.br) que é a fonte mais
rápida e confiável para o campo opcao_pelo_simples.
Resultados bem-sucedidos ficam em cache de memória (TTL 1 h).
"""
from __future__ import annotations

import logging
import time
import threading

import requests

log = logging.getLogger(__name__)

_TIMEOUT = 4   # segundos — BrasilAPI costuma responder em <1 s
_URL = "https://brasilapi.com.br/api/cnpj/v1/{}"

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


# ── Consulta BrasilAPI ────────────────────────────────────────────────────────

def _consultar_brasilapi(cnpj: str) -> dict:
    """
    Chama a BrasilAPI e retorna dict com razao_social, optante_simples e nao_encontrado.
    Nunca lança exceção.
    """
    try:
        r = requests.get(_URL.format(cnpj), timeout=_TIMEOUT, headers=_HEADERS)
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
      2. BrasilAPI → retorna em ~1 s para a maioria das empresas
         opcao_pelo_simples: True = optante, False = não optante, None = sem info

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

    # 2. BrasilAPI
    dados = _consultar_brasilapi(cnpj_limpo)

    if dados.get("nao_encontrado"):
        log.debug("CNPJ %s: não encontrado na BrasilAPI", cnpj_limpo)
        return dados

    simples = dados.get("optante_simples")
    razao   = dados.get("razao_social") or ""

    if simples is not None:
        _cache_set(cnpj_limpo, dados)
        log.debug("CNPJ %s: %s — Simples=%s", cnpj_limpo, razao, simples)
    else:
        log.debug("CNPJ %s: %s — Simples=indisponível na BrasilAPI", cnpj_limpo, razao)

    return dados


def verificar_simples_nacional(cnpj_limpo: str) -> bool | None:
    """Retorna True / False / None (falha)."""
    return obter_dados_empresa(cnpj_limpo).get("optante_simples")


if __name__ == "__main__":
    import json
    import sys
    cnpj = sys.argv[1] if len(sys.argv) > 1 else "49161411000158"
    print(json.dumps(obter_dados_empresa(cnpj), ensure_ascii=False, indent=2))
