"""
situacoes/dsp101_102.py
Handler para DSP101 / DSP102 — Material de Consumo (Almoxarifado / Entrega Direta).

Fluxo após seleção da situação:
    1. Expande barra do empenho
    2. Preenche VPD (lookup por natureza)
    3. Preenche Conta de Estoque = "60100" → 1.1.5.6.1.01.00
    4. Preenche Contas a Pagar  = "1104"  → 2.1.3.1.1.04.00
"""
import time

from comprasnet.principal_helpers import (
    _buscar_vpd,
    _expandir_barra_empenho,
    _verificar_empenho,
    _verificar_interrupcao,
    _preencher_contas_a_pagar,
    _preencher_vpd,
)


def _preencher_conta_estoque(pagina, codigo: str, erros: list):
    """Preenche o campo 'Conta de Estoque' com o código informado (ex: '60100' → 1.1.5.6.1.01.00)."""
    try:
        campo = pagina.locator(
            "xpath=//*[normalize-space(text())='Conta de Estoque']"
            "/following::input[1]"
        ).first
        campo.click(click_count=3)
        campo.fill("")
        campo.press_sequentially(codigo, delay=80)
        pagina.keyboard.press("Tab")
        time.sleep(0.8)
        val = campo.input_value().strip()
        print(f"    Conta de Estoque: '{val}' (digitado: '{codigo}')")
    except Exception as e:
        erros.append(f"Erro ao preencher Conta de Estoque ({codigo}): {e}")


def _preencher_situacao_DSP101_102(
    pagina, num_empenho_pdf, cfg, erros, dados_extraidos=None, deve_parar=None
):
    cod = "DSP101/102"
    print(f"    [{cod}] Expandindo barra do empenho...")
    dados = dados_extraidos or {}
    natureza = dados.get("Natureza", "").strip()

    if not _expandir_barra_empenho(pagina, num_empenho_pdf, erros):
        return
    _verificar_interrupcao(deve_parar)
    _verificar_empenho(pagina, num_empenho_pdf, erros)

    # VPD — preferência para valor informado manualmente
    vpd_manual = dados.get("VPD_MANUAL", "").strip()
    vpd = vpd_manual or _buscar_vpd(natureza, "DSP101/102")
    if vpd:
        origem = " (informado manualmente)" if vpd_manual else ""
        print(f"    VPD para natureza '{natureza}': {vpd}{origem}")
    else:
        print(f"    VPD não encontrado para natureza '{natureza}' — preencher manualmente.")
    _preencher_vpd(pagina, vpd, erros)
    _verificar_interrupcao(deve_parar)

    _preencher_conta_estoque(pagina, cfg.get("conta_estoque", "60100"), erros)
    _preencher_contas_a_pagar(pagina, cfg["contas_a_pagar"], erros)
