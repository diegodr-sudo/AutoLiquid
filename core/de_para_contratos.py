"""
de_para_contratos.py
Tabela de/para: SARF (código do contrato reformatado) → IG (código destino).

Formato SARF:  contrato "00160/2020"  →  "202000160"  (ano + número 5 dígitos)
O CSV contratos_de_para.csv deve ter pelo menos as colunas: SARF, IG
"""
import csv
import logging
import re
import shutil

from core.app_paths import CAMINHO_CONTRATOS, caminho_recurso

_ARQUIVO = CAMINHO_CONTRATOS
_cache = None   # type: dict | None  — compatível com Python 3.8+
log = logging.getLogger(__name__)


# ─── Formatação de código ─────────────────────────────────────────────────────

def formatar_sarf(numero_contrato: str) -> str:
    """
    Converte número do contrato no padrão SARF.
    Ex.: '00160/2020' → '202000160'
         '160/2020'   → '202000160'
    Regra: ano (4 dígitos) + número zero-preenchido (5 dígitos) = 9 dígitos
    """
    s = numero_contrato.strip()
    m = re.match(r"(\d+)/(\d{4})$", s)
    if m:
        num = m.group(1).zfill(5)
        ano = m.group(2)
        return ano + num
    # Já no formato SARF (9 dígitos numéricos)?
    if re.match(r"^\d{9}$", s):
        return s
    return s


# ─── Cache / carregamento ─────────────────────────────────────────────────────

def _garantir_arquivo_contratos() -> None:
    if _ARQUIVO.exists():
        return

    candidatos = [
        caminho_recurso(_ARQUIVO.name),
        caminho_recurso("contratos_de_para.csv"),
    ]
    for recurso_padrao in candidatos:
        if recurso_padrao.exists():
            _ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(recurso_padrao, _ARQUIVO)
            return

def _carregar() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    _cache = {}
    try:
        from services.postgres_service import obter_tabela_operacional, postgres_habilitado

        if postgres_habilitado():
            rows = obter_tabela_operacional("contratos")
            if rows is not None:
                for row in rows:
                    sarf = str((row or {}).get("sarf", "")).strip()
                    ig = str((row or {}).get("ig", "")).strip()
                    if sarf and re.match(r"^\d{9}$", sarf):
                        _cache[sarf] = ig
                return _cache
    except Exception as e:
        log.warning("Falha ao carregar contratos do PostgreSQL: %s", e)

    _garantir_arquivo_contratos()
    if not _ARQUIVO.exists():
        return _cache
    try:
        with _ARQUIVO.open(encoding="utf-8-sig", newline="") as f:
            # Linha 0 é instrução administrativa — pular antes de usar DictReader
            primeira = f.readline()
            # Se a primeira linha não contiver "SARF" como cabeçalho, ela é
            # a linha de instrução e o DictReader usará a próxima como header.
            # Se já for o cabeçalho (SARF presente), voltar ao início.
            if "SARF" in primeira.upper():
                f.seek(0)
            reader = csv.DictReader(f)
            for row in reader:
                sarf = str(row.get("SARF", "")).strip()
                ig   = str(row.get("IG",   "")).strip()
                if sarf and re.match(r"^\d{9}$", sarf):
                    _cache[sarf] = ig
        if not _cache:
            for nome_fallback in ("DCF - CONTRATOS.csv", "contratos_de_para.csv"):
                recurso_fallback = caminho_recurso(nome_fallback)
                if not recurso_fallback.exists() or recurso_fallback == _ARQUIVO:
                    continue
                try:
                    with recurso_fallback.open(encoding="utf-8-sig", newline="") as f:
                        primeira = f.readline()
                        if "SARF" in primeira.upper():
                            f.seek(0)
                        reader = csv.DictReader(f)
                        for row in reader:
                            sarf = str(row.get("SARF", "")).strip()
                            ig = str(row.get("IG", "")).strip()
                            if sarf and re.match(r"^\d{9}$", sarf):
                                _cache[sarf] = ig
                    if _cache:
                        _ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(recurso_fallback, _ARQUIVO)
                        break
                except Exception:
                    continue
    except Exception as e:
        log.exception("Erro ao carregar CSV de contratos: %s", e)
    return _cache


def recarregar():
    """Invalida cache para forçar releitura do CSV."""
    global _cache
    _cache = None


def obter_arquivo_contratos() -> str:
    _garantir_arquivo_contratos()
    return str(_ARQUIVO)


# ─── Consulta pública ─────────────────────────────────────────────────────────

def buscar_ig(sarf_code: str) -> str:
    """
    Retorna o código IG correspondente ao SARF.
    Retorna '' se não encontrado.
    """
    tabela = _carregar()
    return tabela.get(str(sarf_code).strip(), "")


def buscar_ig_por_contrato(numero_contrato: str):
    """
    Recebe o número do contrato como extraído do PDF (ex.: '00160/2020')
    e retorna (sarf_code, ig_code).
    """
    sarf = formatar_sarf(numero_contrato)
    ig   = buscar_ig(sarf)
    return sarf, ig


# ─── CLI de teste ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    contrato = sys.argv[1] if len(sys.argv) > 1 else "00160/2020"
    sarf, ig = buscar_ig_por_contrato(contrato)
    print(f"Contrato : {contrato}")
    print(f"SARF (DE): {sarf}")
    print(f"IG   (PARA): {ig if ig else '— não encontrado no CSV —'}")
