"""
situacoes/legado.py
Handlers para situações numéricas (sem prefixo DSP/BPV) — compatibilidade com
documentos mais antigos onde o código SIAFI ainda não inclui a letra.

Situações cobertas: 201, 101, 102, 001, BPV001
"""
import time

from comprasnet.principal_helpers import (
    _expandir_barra_empenho,
    _verificar_empenho,
    _verificar_interrupcao,
    _preencher_contas_a_pagar,
    _campo_empenho_atual,
    _preencher_campo_empenho_por_prefixo,
)


def _preencher_situacao_201(
    pagina, num_empenho_pdf, cfg, erros, dados_extraidos=None, deve_parar=None
):
    """Situação 201 — Material Permanente (Bens Móveis), legado numérico."""
    print("    [201] Expandindo barra do empenho...")
    if not _expandir_barra_empenho(pagina, num_empenho_pdf, erros):
        return
    _verificar_interrupcao(deve_parar)
    _verificar_empenho(pagina, num_empenho_pdf, erros)

    try:
        campo_cbm = _campo_empenho_atual(pagina, "Conta de Bens")
        try:
            campo_cbm.wait_for(state="visible", timeout=1200)
        except Exception:
            campo_cbm = pagina.locator(
                "xpath=//*[contains(normalize-space(text()),'Conta de Bens')]"
                "/following::input[1]"
            ).first
        val = campo_cbm.input_value().strip()
        if not val:
            val = _preencher_campo_empenho_por_prefixo(pagina, "numclassa", "1.2.3.1.1.08.01")
        if not val:
            val = campo_cbm.input_value().strip()
        if not val:
            campo_cbm.click()
            time.sleep(0.5)
            pagina.keyboard.press("Tab")
            time.sleep(1.5)
            val = campo_cbm.input_value().strip()
        print(f"    Conta de Bens Móveis auto-preenchida: '{val}'")
    except Exception as e:
        erros.append(f"Erro ao acionar Conta de Bens Móveis (201): {e}")

    _preencher_contas_a_pagar(pagina, cfg["contas_a_pagar"], erros)


def _preencher_situacao_001_bpv(
    pagina, num_empenho_pdf, cfg, erros, dados_extraidos=None, deve_parar=None
):
    """Situação 001 / BPV001 — Serviços de Terceiros (sem contrato)."""
    print("    [BPV001/001] Expandindo barra do empenho...")
    if not _expandir_barra_empenho(pagina, num_empenho_pdf, erros):
        return
    _verificar_interrupcao(deve_parar)
    _verificar_empenho(pagina, num_empenho_pdf, erros)
    _preencher_contas_a_pagar(pagina, cfg["contas_a_pagar"], erros)


def _preencher_situacao_101_102(
    pagina, num_empenho_pdf, cfg, erros, dados_extraidos=None, deve_parar=None
):
    """Situação 101 / 102 — Material de Consumo, legado numérico."""
    print("    [101/102] Expandindo barra do empenho...")
    if not _expandir_barra_empenho(pagina, num_empenho_pdf, erros):
        return
    _verificar_interrupcao(deve_parar)
    _verificar_empenho(pagina, num_empenho_pdf, erros)
    _preencher_contas_a_pagar(pagina, cfg["contas_a_pagar"], erros)
