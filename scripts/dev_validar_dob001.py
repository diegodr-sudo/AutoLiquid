#!/usr/bin/env python3
"""
dev_validar_dob001.py — Modo dev: valida a lógica de preenchimento DOB001.

Lê um JSON capturado pelo inspecionar_dob001.py e verifica se os valores
que a automação COMPUTARIA coincidem com os valores CAPTURADOS no DOM.
Roda sem abrir o browser — pura lógica Python.

Uso rápido (infere tudo do JSON):
  python scripts/dev_validar_dob001.py <arquivo.json>

Uso com overrides (sobrescreve parâmetros de entrada):
  python scripts/dev_validar_dob001.py <arquivo.json> \\
    --cod-mun 8093 \\
    --lf-numero 123 \\
    --processo "23080.025919/2026-14" \\
    --cnpj "01.567.432/0001-41" \\
    --valor "2.584,16" \\
    --data-venc "19/06/2026"

Sem argumento, usa o JSON mais recente em ~/Documents/AutoLiquid/falhas-automacao/dob001-dom/.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES (espelho das constantes em comprasnet/deducao.py)
# ─────────────────────────────────────────────────────────────────────────────

_MUNICIPIO_NOME = {
    "8105": "Florianópolis",
    "8047": "Blumenau",
    "8179": "Joinville",
    "8093": "Curitibanos",
    "8027": "Araranguá",
    "5549": "Barra do Sul",
    "8465": "Gov. Celso Ramos",
    "8327": "São José",
}

# Mapa reverso: nome → código
_NOME_MUNICIPIO = {v.lower(): k for k, v in _MUNICIPIO_NOME.items()}

_DOB001_TIPO_OB = {
    "8027": "OB Fatura",
    "8093": "OB Fatura",
    "8179": "OB Crédito",
    "5549": "OB Fatura",
    "8465": "OB Fatura",
}

_DOB001_FAVORECIDO = {
    "OB Fatura": {
        "cnpj_raw": "00000000000191",
        "cnpj_fmt": "00.000.000/0001-91",
        "banco_favorecido": "001",
        "agencia_favorecido": "3582",
        "conta_favorecido": "FATURA",
    },
    "OB Crédito": {
        "cnpj_raw": "83169623000110",
        "cnpj_fmt": "83.169.623/0001-10",
        "banco_favorecido": "001",
        "agencia_favorecido": "3155",
        "conta_favorecido": "17001145",
    },
}

_UG_TOMADORA = "153163"
_BANCO_PAGADOR = "001"

# ─────────────────────────────────────────────────────────────────────────────
# CORES ANSI
# ─────────────────────────────────────────────────────────────────────────────

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

def ok(msg: str) -> str:  return f"{GREEN}✓{RESET} {msg}"
def fail(msg: str) -> str: return f"{RED}✗{RESET} {msg}"
def warn(msg: str) -> str: return f"{YELLOW}⚠{RESET} {msg}"
def info(msg: str) -> str: return f"{CYAN}·{RESET} {msg}"


# ─────────────────────────────────────────────────────────────────────────────
# LÓGICA PURA (sem Playwright) — espelho de comprasnet/deducao.py
# ─────────────────────────────────────────────────────────────────────────────

def formatar_cnpj(cnpj: str) -> str:
    d = re.sub(r"\D", "", str(cnpj))
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return cnpj


def formatar_valor_br(valor_str: str) -> str:
    """Valor numérico → formato BR (ponto milhar, vírgula decimal)."""
    try:
        normalizado = re.sub(r"[^\d,.]", "", str(valor_str))
        if "," in normalizado and "." in normalizado:
            # Decide qual é separador decimal (o último)
            if normalizado.rfind(",") > normalizado.rfind("."):
                normalizado = normalizado.replace(".", "").replace(",", ".")
            else:
                normalizado = normalizado.replace(",", "")
        elif "," in normalizado:
            normalizado = normalizado.replace(",", ".")
        v = float(normalizado)
        return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(valor_str)


def calcular_dv_nup(base15: str) -> str:
    """Módulo 11 — dois dígitos verificadores do NUP-17."""
    d = re.sub(r"\D", "", str(base15))
    if len(d) != 15:
        raise ValueError(f"NUP base deve ter 15 dígitos; recebido {len(d)}")
    s1 = sum(int(d[i]) * (16 - i) for i in range(15))
    dv1 = (11 - s1 % 11) % 10
    d2 = d + str(dv1)
    s2 = sum(int(d2[i]) * (17 - i) for i in range(16))
    dv2 = (11 - s2 % 11) % 10
    return f"{dv1}{dv2}"


def formatar_processo_nup(processo: str) -> str:
    """Normaliza para NUP-17 pontuado (NNNNN.NNNNNN/AAAA-DD)."""
    bruto = str(processo or "").strip()
    d = re.sub(r"\D", "", bruto)
    if len(d) == 15:
        try:
            d = d + calcular_dv_nup(d)
        except Exception:
            return bruto
    if len(d) != 17:
        return bruto
    return f"{d[0:5]}.{d[5:11]}/{d[11:15]}-{d[15:17]}"


def data_iso_para_br(data_iso: str) -> str:
    """YYYY-MM-DD → DD/MM/YYYY."""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(data_iso).strip())
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else data_iso


def data_br_para_iso(data_br: str) -> str:
    """DD/MM/YYYY → YYYY-MM-DD."""
    m = re.match(r"(\d{2})[/-](\d{2})[/-](\d{4})", str(data_br).strip())
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else data_br


# ─────────────────────────────────────────────────────────────────────────────
# EXTRATOR DE CAMPOS DO JSON CAPTURADO
# ─────────────────────────────────────────────────────────────────────────────

def campo_por_prefixo(campos: list[dict], prefixo: str) -> dict | None:
    """Retorna o primeiro campo cujo id começa com `prefixo`."""
    for c in campos:
        if str(c.get("id", "")).startswith(prefixo):
            return c
    return None


def valor_campo(campos: list[dict], prefixo: str, default: str = "") -> str:
    c = campo_por_prefixo(campos, prefixo)
    return str(c["value"]) if c else default


def valor_select(campos: list[dict], prefixo: str) -> tuple[str, str]:
    """Retorna (value_selecionado, text_selecionado) de um select."""
    c = campo_por_prefixo(campos, prefixo)
    if not c:
        return ("", "")
    for opt in c.get("options", []):
        if opt.get("selected"):
            return (opt["value"], opt["text"])
    return (str(c.get("value", "")), str(c.get("value", "")))


# ─────────────────────────────────────────────────────────────────────────────
# INFERÊNCIA DE PARÂMETROS A PARTIR DO JSON CAPTURADO
# ─────────────────────────────────────────────────────────────────────────────

def inferir_cod_mun(campos: list[dict]) -> str:
    """Tenta inferir cod_mun a partir da observação capturada."""
    obser = valor_campo(campos, "obser").lower()
    for nome, cod in _NOME_MUNICIPIO.items():
        if nome.lower() in obser:
            return cod
    return ""


def inferir_tipo_ob(campos: list[dict]) -> str:
    """Retorna o text do Tipo de OB selecionado."""
    _, text = valor_select(campos, "codtipoob")
    return text or "OB Fatura"


# ─────────────────────────────────────────────────────────────────────────────
# VALIDAÇÃO DE UMA DEDUÇÃO DOB001
# ─────────────────────────────────────────────────────────────────────────────

def validar_deducao(
    did: str,
    campos: list[dict],
    *,
    cod_mun: str = "",
    lf_numero: str = "",
    processo: str = "",
    cnpj_fornecedor: str = "",
    valor: str = "",
    data_venc_br: str = "",
) -> list[tuple[str, str, str, bool]]:
    """
    Compara valores CAPTURADOS no DOM com o que a automação COMPUTARIA.
    Retorna lista de (campo, capturado, esperado, ok).
    """
    resultados: list[tuple[str, str, str, bool]] = []

    # ── Infere parâmetros não fornecidos a partir do próprio JSON ──────────
    if not cod_mun:
        cod_mun = inferir_cod_mun(campos)
    tipo_ob_capturado = inferir_tipo_ob(campos)
    tipo_ob = _DOB001_TIPO_OB.get(cod_mun, "OB Fatura")
    favorecido = _DOB001_FAVORECIDO.get(tipo_ob, _DOB001_FAVORECIDO["OB Fatura"])

    if not lf_numero:
        lf_numero = valor_campo(campos, "codnumlista")
    if not processo:
        processo = valor_campo(campos, "txtprocesso")
    if not valor:
        valor = valor_campo(campos, "sfdeducaovlr")
    if not data_venc_br:
        data_iso = valor_campo(campos, "sfdeducaodtvenc")
        data_venc_br = data_iso_para_br(data_iso) if data_iso else ""

    # ── Verifica cada campo ────────────────────────────────────────────────

    def chk(label: str, capturado: str, esperado: str, fuzzy: bool = False) -> None:
        cap = str(capturado).strip()
        esp = str(esperado).strip()
        if fuzzy:
            passou = cap.lower() == esp.lower()
        else:
            passou = cap == esp
        resultados.append((label, cap, esp, passou))

    # 1. Situação
    sit_val, sit_text = valor_select(campos, "sfdeducaocodsit")
    chk("Situação (select value)", sit_val, "DOB001")

    # 2. UG Pagadora
    chk("UG Pagadora", valor_campo(campos, "sfdeducaocodugpgto"), _UG_TOMADORA)

    # 3. Data Vencimento (capturada em YYYY-MM-DD → convertida para BR para comparar)
    data_iso_cap = valor_campo(campos, "sfdeducaodtvenc")
    chk("Data Vencimento (ISO)", data_iso_cap, data_br_para_iso(data_venc_br))

    # 4. Data Pagamento (igual ao vencimento no DOB001)
    data_pgto_iso = valor_campo(campos, "sfdeducaodtpgtoreceb")
    chk("Data Pagamento (ISO)", data_pgto_iso, data_iso_cap)

    # 5. Valor
    valor_cap = valor_campo(campos, "sfdeducaovlr")
    valor_esp = formatar_valor_br(valor)
    chk("Valor do Item (BR)", valor_cap, valor_esp)

    # 6. Possui Acréscimo
    ac_val, ac_text = valor_select(campos, "sfdeducaopossui_acrescimo")
    chk("Possui Acréscimo", ac_val, "0")  # "0" = NÃO

    # 7. Tipo de OB
    ob_val, ob_text = valor_select(campos, "codtipoob")
    tipo_ob_opcao = {"OB Fatura": "OBD", "OB Crédito": "OBC"}.get(tipo_ob, "OBD")
    chk("Tipo de OB (value)", ob_val, tipo_ob_opcao)
    chk("Tipo de OB (text)", ob_text, tipo_ob, fuzzy=True)

    # 8. CNPJ Favorecido
    cnpj_cap = valor_campo(campos, "codcredordevedorpredoc")
    chk("CNPJ Favorecido", cnpj_cap, favorecido["cnpj_fmt"])

    # 9. Processo (NUP-17)
    proc_cap = valor_campo(campos, "txtprocesso")
    proc_esp = formatar_processo_nup(processo)
    chk("Processo (NUP-17)", proc_cap, proc_esp)

    # 10. Taxa de Câmbio
    taxa_cap = valor_campo(campos, "taxacambio")
    taxa_norm = re.sub(r"\.?0+$", "", taxa_cap.replace(",", ".")) if taxa_cap else "0"
    chk("Taxa de Câmbio", taxa_norm, "0")

    # 11. Número da Lista (LF)
    chk("Número da Lista (LF)", valor_campo(campos, "codnumlista"), lf_numero)

    # 12. Banco Favorecido
    chk("Banco Favorecido", valor_campo(campos, "bancoFavorecido"), favorecido["banco_favorecido"])

    # 13. Agência Favorecido
    chk("Agência Favorecido", valor_campo(campos, "agenciaFavorecido"), favorecido["agencia_favorecido"])

    # 14. Conta Favorecido
    chk("Conta Favorecido", valor_campo(campos, "contaFavorecido"), favorecido["conta_favorecido"])

    # 15. Banco Pagador
    chk("Banco Pagador", valor_campo(campos, "bancoPagador"), _BANCO_PAGADOR)

    # 16. Observação (valida estrutura mínima)
    obser_cap = valor_campo(campos, "obser")
    tem_iss = "ISS" in obser_cap.upper()
    tem_cidade = _MUNICIPIO_NOME.get(cod_mun, "").lower() in obser_cap.lower() if cod_mun else True
    tem_cnpj = re.search(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", obser_cap) is not None
    obser_ok = tem_iss and tem_cidade and tem_cnpj
    resultados.append((
        "Observação (estrutura)",
        f"{'ISS✓' if tem_iss else 'ISS✗'} {'Cidade✓' if tem_cidade else 'Cidade✗'} {'CNPJ✓' if tem_cnpj else 'CNPJ✗'}",
        "ISS + Cidade + CNPJ presentes",
        obser_ok,
    ))

    return resultados


# ─────────────────────────────────────────────────────────────────────────────
# IMPRESSÃO DO RELATÓRIO
# ─────────────────────────────────────────────────────────────────────────────

def imprimir_relatorio(did: str, campos: list[dict], resultados: list[tuple]) -> int:
    """Imprime o relatório de validação e retorna nº de falhas."""
    tipo_ob = inferir_tipo_ob(campos)
    cod_mun = inferir_cod_mun(campos)
    nome_mun = _MUNICIPIO_NOME.get(cod_mun, cod_mun or "desconhecido")
    valor = valor_campo(campos, "sfdeducaovlr")

    print(f"\n{BOLD}{'═'*68}{RESET}")
    print(f"{BOLD}  DOB001  ·  did={did}  ·  {nome_mun} ({cod_mun})  ·  Valor: {valor}{RESET}")
    print(f"{BOLD}{'═'*68}{RESET}")
    print(f"  {'Campo':<30} {'Capturado':<25} {'Esperado':<25}")
    print(f"  {'-'*28} {'-'*23} {'-'*23}")

    falhas = 0
    for campo, capturado, esperado, passou in resultados:
        simbolo = ok("") if passou else fail("")
        cap_fmt = (capturado[:22] + "…") if len(capturado) > 23 else capturado
        esp_fmt = (esperado[:22] + "…") if len(esperado) > 23 else esperado
        print(f"  {simbolo} {campo:<28} {cap_fmt:<25} {esp_fmt}")
        if not passou:
            falhas += 1

    print()

    # Observação completa
    obser = valor_campo(campos, "obser")
    if obser:
        print(f"  {DIM}Obs:{RESET} {obser[:120]}{'…' if len(obser)>120 else ''}")

    # Campos DOB001-específicos presentes
    dob001_fields = [c for c in campos if any(
        c.get("id","").startswith(p)
        for p in ["codtipoob", "codcredordevedorpredoc", "codnumlista",
                  "bancoFavorecido", "agenciaFavorecido", "contaFavorecido", "bancoPagador", "obser"]
    )]
    print(f"\n  {DIM}Campos DOB001-específicos visíveis: {len(dob001_fields)}{RESET}")
    print(f"  {DIM}Tipo de OB detectado: {tipo_ob}{RESET}")

    print()
    if falhas == 0:
        print(f"  {GREEN}{BOLD}RESULTADO: TUDO OK — {len(resultados)} verificações passaram.{RESET}")
    else:
        print(f"  {RED}{BOLD}RESULTADO: {falhas} FALHA(S) em {len(resultados)} verificações.{RESET}")
    print(f"  {'═'*66}\n")

    return falhas


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_OUT_DIR = Path.home() / "Documents" / "AutoLiquid" / "falhas-automacao" / "dob001-dom"


def encontrar_json_mais_recente(out_dir: Path) -> Path | None:
    jsons = sorted(out_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return jsons[0] if jsons else None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dev mode: valida lógica DOB001 contra JSON capturado.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "json_path", nargs="?",
        help="Caminho do JSON capturado (padrão: mais recente em falhas-automacao/dob001-dom/).",
    )
    parser.add_argument("--cod-mun",  default="", help="Código do município (ex: 8093)")
    parser.add_argument("--lf-numero", default="", help="Número da Lista de Faturas")
    parser.add_argument("--processo",  default="", help="NUP do processo (15 ou 17 dígitos)")
    parser.add_argument("--cnpj",      default="", help="CNPJ do fornecedor (para observação)")
    parser.add_argument("--valor",     default="", help="Valor BR (ex: 2.584,16)")
    parser.add_argument("--data-venc", default="", help="Data de vencimento DD/MM/AAAA")
    parser.add_argument("--all-dids",  action="store_true",
                        help="Valida todos os dids no JSON (inclui DDF050, DDF055 etc.)")
    args = parser.parse_args()

    # ── Localiza o JSON ────────────────────────────────────────────────────
    if args.json_path:
        json_path = Path(args.json_path).expanduser()
    else:
        json_path = encontrar_json_mais_recente(DEFAULT_OUT_DIR)
        if not json_path:
            print(fail(f"Nenhum JSON encontrado em {DEFAULT_OUT_DIR}"))
            return 1

    if not json_path.exists():
        print(fail(f"Arquivo não encontrado: {json_path}"))
        return 1

    print(f"\n{BOLD}dev_validar_dob001.py{RESET}")
    print(f"{DIM}JSON: {json_path}{RESET}")

    with open(json_path, encoding="utf-8") as f:
        snapshot = json.load(f)

    by_did: dict[str, list[dict]] = snapshot.get("byDeducaoId", {})
    if not by_did:
        print(warn("byDeducaoId vazio — JSON sem dados de dedução."))
        return 1

    print(f"{DIM}URL:  {snapshot.get('url','')}{RESET}")
    print(f"{DIM}Data: {snapshot.get('capturedAt','')}{RESET}")
    print(f"\n{info(f'{len(by_did)} grupo(s) de campos encontrados: {list(by_did.keys())}')}")

    # ── Seleciona os dids DOB001 ───────────────────────────────────────────
    dids_dob001: list[str] = []
    for did, campos in by_did.items():
        sit_val, _ = valor_select(campos, "sfdeducaocodsit")
        if sit_val == "DOB001" or args.all_dids:
            dids_dob001.append(did)

    if not dids_dob001:
        print(warn("Nenhum campo com Situação=DOB001 encontrado."))
        print(info("Use --all-dids para validar todos os grupos."))
        # Mostra situações encontradas
        for did, campos in by_did.items():
            sit_val, sit_text = valor_select(campos, "sfdeducaocodsit")
            if sit_val:
                print(f"  {DIM}did={did}: Situação={sit_val} ({sit_text}){RESET}")
        return 0

    # ── Valida cada DOB001 ─────────────────────────────────────────────────
    total_falhas = 0
    for did in dids_dob001:
        campos = by_did[did]
        resultados = validar_deducao(
            did, campos,
            cod_mun=args.cod_mun,
            lf_numero=args.lf_numero,
            processo=args.processo,
            cnpj_fornecedor=args.cnpj,
            valor=args.valor,
            data_venc_br=args.data_venc,
        )
        total_falhas += imprimir_relatorio(did, campos, resultados)

    if len(dids_dob001) > 1:
        print(f"{BOLD}Total geral: {total_falhas} falha(s) em {len(dids_dob001)} dedução(ões) DOB001.{RESET}\n")

    return 0 if total_falhas == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
