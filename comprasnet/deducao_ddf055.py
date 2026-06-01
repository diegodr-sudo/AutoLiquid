"""
comprasnet_deducao_ddf055.py
DDF055 — IRRF apurado conforme IN 1234/12 (DARF).

Importado e chamado por comprasnet_deducao.executar().
As funções auxiliares são importadas de comprasnet_deducao com import tardio (lazy)
para evitar importação circular.

NOTA IMPORTANTE — transição DDF050 → DDF055
--------------------------------------------
Quando ambos os tipos estão presentes no mesmo documento, o DDF050 é sempre
executado primeiro. Antes de chamar este módulo, comprasnet_deducao.executar()
invoca _aguardar_portal_limpo_entre_tipos() para garantir que o portal está
completamente livre (nenhum formulário aberto, overlay ausente, botão '+' visível).
Só então este módulo clica no '+' e preenche o DDF055.
"""
import logging
from core.datas_impostos import calcular_datas

log = logging.getLogger(__name__)


def executar_ddf055(
    pagina,
    ddf055_list: list,
    *,
    data_vencimento_processo: str = "",
    apuracao_usuario: str = "",
    processo: str = "",
    cnpj_fmt: str = "",
    dados_extraidos: dict,
    erros: list,
    recurso_darf: str = "1",
    deve_parar=None,
) -> bool:
    """
    Processa todas as deduções DDF055 (IRRF IN 1234/12 — DARF).

    Ao contrário do DDF050, a data de vencimento é informada diretamente pelo
    usuário (data_vencimento_processo) — não é calculada a partir das NFs.

    Parâmetros
    ----------
    pagina                   : instância Playwright da página atual
    ddf055_list              : lista de dicts de dedução do tipo DDF055
    data_vencimento_processo : data de vencimento informada pelo usuário
    apuracao_usuario         : data de apuração informada pelo usuário
    processo                 : número do processo (para pré-doc)
    cnpj_fmt                 : CNPJ do fornecedor já formatado
    dados_extraidos          : dicionário completo do PDF
    erros                    : lista mutável onde erros são acumulados
    recurso_darf             : código de recurso (do empenho)
    deve_parar               : callable opcional de interrupção cooperativa

    Retorna
    -------
    bool  True se todas as deduções foram concluídas sem erro crítico.
    """
    # Import tardio — evita circular com comprasnet_deducao
    from comprasnet.deducao import (
        _verificar_interrupcao,
        _aguardar_portal_limpo_entre_tipos,
        _preencher_deducao_darf_total,
    )

    if not ddf055_list:
        return True

    tipos_siafi = sorted({
        str(ded.get("Situação SIAFI") or "DDF055").strip().upper()
        for ded in ddf055_list
        if str(ded.get("Situação SIAFI") or "DDF055").strip()
    })
    label_siafi = "/".join(tipos_siafi) or "DDF055"
    print(
        f"\n  ══ {label_siafi} ({len(ddf055_list)} retenção/ões · DARF) ══════"
    )

    # A regra salva decide se usa data do usuário ou cálculo pela emissão das NFs.
    data_venc_padrao = str(data_vencimento_processo or "").strip()
    data_apuracao_padrao = str(apuracao_usuario or "").strip()
    datas_emissao = [
        str(nf.get("Data de Emissão", "") or nf.get("Data de EmissÃ£o", "") or "").strip()
        for nf in (dados_extraidos.get("Notas Fiscais", []) or [])
    ]

    todos_ok = True

    for idx, ded in enumerate(ddf055_list):
        _verificar_interrupcao(deve_parar)
        if idx > 0:
            _aguardar_portal_limpo_entre_tipos(pagina, timeout_ms=30000)

        siafi = str(ded.get("Situação SIAFI") or "DDF055").strip().upper()
        codigo_ref = str(ded.get("Código") or ded.get("CÃ³digo") or "").strip()
        datas_calc = calcular_datas(
            codigo_ref,
            datas_emissao,
            vencimento_usuario=data_venc_padrao,
            apuracao_usuario=data_apuracao_padrao,
        )
        data_venc = str(datas_calc.get("vencimento") or data_venc_padrao).strip()
        data_apuracao = str(datas_calc.get("apuracao") or data_apuracao_padrao).strip()
        if not data_venc:
            erros.append(f"{siafi}: data de vencimento não informada nem calculada pela regra de dedução.")
            todos_ok = False
            break

        erros_antes = len(erros)
        ok = _preencher_deducao_darf_total(
            pagina,
            ded,
            idx,
            len(ddf055_list),
            siafi,
            data_venc=data_venc,
            data_apuracao=data_apuracao,
            processo=processo,
            cnpj_fmt=cnpj_fmt,
            dados=dados_extraidos,
            erros=erros,
            recurso=recurso_darf,
            deve_parar=deve_parar,
        )

        if not ok or len(erros) > erros_antes:
            print(f"  ✗ {siafi} [{idx+1}/{len(ddf055_list)}]: erro — parando este bloco.")
            todos_ok = False
            break

    if todos_ok:
        print(f"  ✓ {label_siafi} concluído ({len(ddf055_list)} lançamento/s).")

    return todos_ok
