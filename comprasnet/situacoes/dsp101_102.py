"""
situacoes/dsp101_102.py
Handler para DSP101 / DSP102 — Material de Consumo (Almoxarifado / Entrega Direta).

Fluxo após seleção da situação:
    1. Expande barra do empenho
    2. Preenche VPD somente para DSP102 (lookup por natureza)
    3. Preenche Conta de Estoque = "60100" → 1.1.5.6.1.01.00
    4. Preenche Contas a Pagar  = "1104"  → 2.1.3.1.1.04.00
"""
import re
import time

from comprasnet.principal_helpers import (
    _buscar_vpd,
    _expandir_barra_empenho,
    _verificar_empenho,
    _verificar_interrupcao,
    _preencher_contas_a_pagar,
    _preencher_vpd,
    _aguardar_mascara_campo,
    _JS_POSICIONAR_MASCARA,
)


def _preencher_conta_estoque(pagina, codigo: str, erros: list):
    """Preenche o campo 'Conta de Estoque' (ex: '60100' → 1.1.5.6.1.01.00).

    Usa a mesma estratégia de máscara: foco, aguarda '_', posiciona cursor,
    digita somente os dígitos editáveis — nunca usa fill("") que corrompe a máscara.
    """
    try:
        campo = pagina.locator(
            "xpath=//*[normalize-space(text())='Conta de Estoque']"
            "/following::input[1]"
        ).first
        campo.wait_for(state="visible", timeout=5000)
        codigo_digitos = re.sub(r"\D+", "", str(codigo or ""))

        # Foco → espera template → posiciona → digita
        campo.click()
        time.sleep(0.15)
        _aguardar_mascara_campo(campo)
        campo.evaluate(_JS_POSICIONAR_MASCARA)
        campo.press_sequentially(codigo_digitos, delay=80)
        pagina.keyboard.press("Tab")
        time.sleep(0.8)
        val = campo.input_value().strip()
        print(f"    Conta de Estoque: '{val}' (digitado: '{codigo_digitos}')")
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

    # DSP101 não possui campo VPD no portal. DSP102 mantém lookup por natureza.
    situacao_norm = dados.get("_SITUACAO_NORM", "").strip().upper()
    if not situacao_norm:
        descricao = str(cfg.get("descricao", "") or "").upper()
        if "ENTREGA DIRETA" in descricao:
            situacao_norm = "DSP102"
        elif "ALMOXARIFADO" in descricao:
            situacao_norm = "DSP101"

    if situacao_norm == "DSP102":
        vpd_manual = dados.get("VPD_MANUAL", "").strip()
        vpd = vpd_manual or _buscar_vpd(natureza, "DSP101/102")
        if vpd:
            origem = " (informado manualmente)" if vpd_manual else ""
            print(f"    VPD para natureza '{natureza}': {vpd}{origem}")
        else:
            print(f"    VPD nao encontrado para natureza '{natureza}' — preencher manualmente.")
        _preencher_vpd(pagina, vpd, erros)
    else:
        print("    DSP101: VPD não aplicável — preenchimento ignorado.")
    _verificar_interrupcao(deve_parar)

    _preencher_conta_estoque(pagina, cfg.get("conta_estoque", "60100"), erros)
    _preencher_contas_a_pagar(pagina, cfg["contas_a_pagar"], erros)
