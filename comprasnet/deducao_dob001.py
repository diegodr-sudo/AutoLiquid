"""
comprasnet_deducao_dob001.py
DOB001 — Ordem Bancária (OB Fatura / OB Crédito).

Importado e chamado por comprasnet_deducao.executar().
As funções auxiliares são importadas de comprasnet_deducao com import tardio (lazy)
para evitar importação circular.
"""
import logging
from core.datas_impostos import calcular_datas

log = logging.getLogger(__name__)


def executar_dob001(
    pagina,
    dob001_list: list,
    *,
    lf_numero: str,
    datas_emissao: list,
    data_vencimento_processo: str = "",
    processo: str = "",
    cnpj_fmt: str = "",
    dados_extraidos: dict,
    erros: list,
    deve_parar=None,
) -> bool:
    """
    Processa todas as deduções DOB001 (Ordem Bancária).

    São ignorados automaticamente os municípios de código "8327" (São José),
    conforme regra do processo.

    Parâmetros
    ----------
    pagina                   : instância Playwright da página atual
    dob001_list              : lista de dicts de dedução do tipo DOB001
    lf_numero                : número da Lista de Faturas (obrigatório para DOB001)
    datas_emissao            : lista de datas de emissão das NFs (DD/MM/AAAA)
    data_vencimento_processo : data fallback quando calcular_datas retorna vazio
    processo                 : número do processo (para pré-doc)
    cnpj_fmt                 : CNPJ do fornecedor já formatado
    dados_extraidos          : dicionário completo do PDF
    erros                    : lista mutável onde erros são acumulados
    deve_parar               : callable opcional de interrupção cooperativa

    Retorna
    -------
    bool  True se todas as deduções foram concluídas sem erro crítico.
    """
    # Import tardio — evita circular com comprasnet_deducao
    from comprasnet.deducao import (
        _verificar_interrupcao,
        _codigo_municipio_deducao,
        _preencher_dob001_total,
        _MUNICIPIO_NOME,
    )

    if not dob001_list:
        return True

    if not lf_numero:
        erros.append("DOB001: número da LF não informado para este processo.")
        return False

    print(
        f"\n  ══ DOB001 ({len(dob001_list)} retenção/ões · Ordem Bancária) ════════"
    )

    todos_ok = True

    for idx, ded in enumerate(dob001_list):
        _verificar_interrupcao(deve_parar)

        cod_mun = _codigo_municipio_deducao(ded)

        # São José (8327) é sempre ignorado conforme regra do processo
        if cod_mun == "8327":
            nome_mun = _MUNICIPIO_NOME.get(cod_mun, cod_mun)
            print(f"  → DOB001 {nome_mun} ({cod_mun}): ignorado conforme regra do processo.")
            continue

        datas_calc = calcular_datas(cod_mun, datas_emissao)
        data_venc  = datas_calc.get("vencimento", "") or str(data_vencimento_processo or "").strip()
        if not data_venc:
            print(
                f"  [AVISO] DOB001 {cod_mun}: data de vencimento não calculada. "
                f"datas_emissao={datas_emissao}"
            )

        erros_antes = len(erros)
        ok = _preencher_dob001_total(
            pagina,
            ded,
            idx,
            len(dob001_list),
            cod_mun=cod_mun,
            data_venc=data_venc,
            processo=processo,
            cnpj_fmt=cnpj_fmt,
            lf_numero=lf_numero,
            dados=dados_extraidos,
            erros=erros,
            deve_parar=deve_parar,
        )

        if not ok or len(erros) > erros_antes:
            print(f"  ✗ DOB001 [{idx+1}/{len(dob001_list)}]: erro — parando este bloco.")
            todos_ok = False
            break

    if todos_ok:
        print(f"  ✓ DOB001 concluído.")

    return todos_ok
