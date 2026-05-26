"""
situacoes/dsp001.py
Handler para DSP001 — Aquisição de Serviços Pessoas Jurídicas (com contrato).

Fluxo após seleção da situação:
    1. Preenche Tem Contrato? (SIM/NÃO)
    2. Se SIM: Conta de Contrato = "02" + Favorecido do Contrato = IG
    3. Expande barra do empenho
    4. Preenche VPD (lookup por natureza)
    5. Preenche Contas a Pagar = "1104" → 2.1.3.1.1.04.00
"""
import time

from comprasnet.principal_helpers import (
    _buscar_vpd,
    _expandir_barra_empenho,
    _verificar_empenho,
    _verificar_interrupcao,
    _preencher_campo_com_retry,
    _preencher_contas_a_pagar,
    _preencher_vpd,
)


def _preencher_situacao_DSP001(
    pagina, num_empenho_pdf, cfg, erros, dados_extraidos=None, deve_parar=None
):
    print("    [DSP001] Preenchendo campos de contrato...")
    _verificar_interrupcao(deve_parar)
    dados = dados_extraidos or {}

    tem_contrato = dados.get("Tem Contrato?", dados.get("Tem Contrato", "Não"))
    ig_code      = dados.get("IG", "").strip()
    natureza     = dados.get("Natureza", "").strip()

    # 1. Tem Contrato?
    try:
        sel_tc = pagina.locator(
            "xpath=//*[normalize-space(text())='Tem Contrato?']"
            "/following::select[1]"
        ).first
        opcao_tc = "SIM" if tem_contrato == "Sim" else "NÃO"
        sel_tc.select_option(label=opcao_tc)
        time.sleep(1.2)
        print(f"    Tem Contrato? → {opcao_tc}")
    except Exception as e:
        erros.append(f"Erro ao preencher 'Tem Contrato?' (DSP001): {e}")

    # 2. Conta de Contrato e Favorecido do Contrato (só se SIM)
    if tem_contrato == "Sim":
        _verificar_interrupcao(deve_parar)
        conta_contrato = cfg.get("conta_contrato", "02")
        try:
            campo_cc = pagina.locator(
                "xpath=//*[normalize-space(text())='Conta de Contrato']"
                "/following::input[1]"
            ).first
            _preencher_campo_com_retry(
                pagina, campo_cc, conta_contrato, erros,
                descricao="Conta de Contrato",
                tentativas=3,
                delay_entre=1.2,
            )
        except Exception as e:
            erros.append(f"Erro ao localizar 'Conta de Contrato' (DSP001): {e}")

        if ig_code:
            try:
                campo_fav = pagina.locator(
                    "xpath=//*[normalize-space(text())='Favorecido do Contrato']"
                    "/following::input[1]"
                ).first
                _preencher_campo_com_retry(
                    pagina, campo_fav, ig_code, erros,
                    descricao="Favorecido do Contrato",
                    tentativas=3,
                    delay_entre=1.0,
                )
            except Exception as e:
                erros.append(f"Erro ao localizar 'Favorecido do Contrato' (DSP001): {e}")
        else:
            erros.append("IG não disponível — preencha 'Favorecido do Contrato' manualmente.")

    # 3. Expande barra do empenho
    if not _expandir_barra_empenho(pagina, num_empenho_pdf, erros):
        return
    _verificar_interrupcao(deve_parar)
    _verificar_empenho(pagina, num_empenho_pdf, erros)

    # 4. VPD — preferência para valor informado manualmente
    vpd_manual = dados.get("VPD_MANUAL", "").strip()
    vpd = vpd_manual or _buscar_vpd(natureza, "DSP001")
    if vpd:
        origem = " (informado manualmente)" if vpd_manual else ""
        print(f"    VPD para natureza '{natureza}': {vpd}{origem}")
    else:
        print(f"    VPD não encontrado para natureza '{natureza}' — preencher manualmente.")
    _preencher_vpd(pagina, vpd, erros)
    _verificar_interrupcao(deve_parar)

    # 5. Contas a Pagar → "1104"
    _preencher_contas_a_pagar(pagina, cfg["contas_a_pagar"], erros)
