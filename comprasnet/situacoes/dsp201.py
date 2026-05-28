"""
situacoes/dsp201.py
Handler para DSP201 — Material Permanente / Bens Móveis (DSP).

Fluxo após seleção da situação:
    1. Expande barra do empenho
    2. Preenche VPD (lookup por natureza de despesa)
    3. Clica em Conta de Bens Móveis para disparar auto-preenchimento
    4. Preenche Contas a Pagar = "104" → 2.1.3.1.1.04.00 (máscara já tem o "1" fixo)

Telas do SIAFI que podem exigir preenchimento manual caso a automação falhe:
    - IMB050: Conta de Bens Móveis (campo auto-preenchido pelo portal)
    - IMB050: VPD conforme natureza de despesa
    - IMB050: Contas a Pagar = 2.1.3.1.1.04.00 (digitar apenas "104" — máscara já tem o "1")
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


def _preencher_situacao_DSP201(
    pagina, num_empenho_pdf, cfg, erros, dados_extraidos=None, deve_parar=None
):
    cod = "DSP201"
    print(f"    [{cod}] Expandindo barra do empenho...")
    dados = dados_extraidos or {}
    natureza = dados.get("Natureza", "").strip()

    if not _expandir_barra_empenho(pagina, num_empenho_pdf, erros):
        erros.append(
            f"[DSP201] Não foi possível expandir o empenho {num_empenho_pdf}. "
            "Preencha manualmente no SIAFI — IMB050: Conta de Bens Móveis, "
            "Contas a Pagar = 2.1.3.1.1.04.00 e VPD conforme natureza."
        )
        return
    _verificar_interrupcao(deve_parar)
    _verificar_empenho(pagina, num_empenho_pdf, erros)

    # VPD — preferência para valor informado manualmente
    vpd_manual = dados.get("VPD_MANUAL", "").strip()
    vpd = vpd_manual or _buscar_vpd(natureza, "DSP201")
    if vpd:
        origem = " (informado manualmente)" if vpd_manual else ""
        print(f"    [{cod}] VPD para natureza '{natureza}': {vpd}{origem}")
    else:
        print(f"    [{cod}] VPD não encontrado para natureza '{natureza}' — preencher manualmente.")
        erros.append(
            f"[DSP201] VPD não encontrado para natureza '{natureza}'. "
            "Preencha manualmente no SIAFI (IMB050 — campo VPD)."
        )
    _preencher_vpd(pagina, vpd, erros)
    _verificar_interrupcao(deve_parar)

    # Conta de Bens Móveis — clica para disparar auto-preenchimento do portal
    conta_bens_ok = False
    try:
        campo_cbm = pagina.locator(
            "xpath=//*[contains(normalize-space(text()),'Conta de Bens')]"
            "/following::input[1]"
        ).first
        val = campo_cbm.input_value().strip()
        if not val:
            campo_cbm.click()
            time.sleep(0.5)
            pagina.keyboard.press("Tab")
            time.sleep(1.5)
            val = campo_cbm.input_value().strip()
        if val:
            conta_bens_ok = True
        print(f"    [{cod}] Conta de Bens Móveis auto-preenchida: '{val}'")
    except Exception as e:
        erros.append(
            f"[DSP201] Erro ao acionar Conta de Bens Móveis: {e}. "
            "Preencha manualmente no SIAFI (IMB050 — Conta de Bens Móveis)."
        )

    if not conta_bens_ok:
        erros.append(
            "[DSP201] Campo 'Conta de Bens Móveis' ficou vazio após o clique. "
            "Verifique manualmente no SIAFI (IMB050)."
        )

    _preencher_contas_a_pagar(pagina, cfg["contas_a_pagar"], erros)
