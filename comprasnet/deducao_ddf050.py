"""
comprasnet_deducao_ddf050.py
DDF050 — IRRF apurado conforme IN 2110/22 (DARF).

Importado e chamado por comprasnet_deducao.executar().
As funções auxiliares são importadas de comprasnet_deducao com import tardio (lazy)
para evitar importação circular.
"""
import logging
from core.datas_impostos import calcular_datas

log = logging.getLogger(__name__)


def executar_ddf050(
    pagina,
    ddf050_list: list,
    *,
    datas_emissao: list,
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
    Processa todas as deduções DDF050 (IRRF IN 2110/22 — DARF).

    Cada DDF050 gera um único lançamento; a data de vencimento é calculada
    pela função calcular_datas() a partir das datas de emissão das NFs.

    Parâmetros
    ----------
    pagina                   : instância Playwright da página atual
    ddf050_list              : lista de dicts de dedução do tipo DDF050
    datas_emissao            : lista de datas de emissão das NFs (DD/MM/AAAA)
    data_vencimento_processo : data fallback quando calcular_datas retorna vazio
    apuracao_usuario         : data de apuração informada pelo usuário (fallback)
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
        _ded_codigo,
        _preencher_deducao_darf_total,
    )

    if not ddf050_list:
        return True

    print(
        f"\n  ══ DDF050 ({len(ddf050_list)} retenção/ões · IRRF IN 2110/22) ══════"
    )

    todos_ok = True

    for idx, ded in enumerate(ddf050_list):
        _verificar_interrupcao(deve_parar)

        # Calcula datas pela tabela de ISS/IR com base nas emissões das NFs
        codigo_ref   = _ded_codigo(ded) or "1162"
        datas_calc   = calcular_datas(codigo_ref, datas_emissao)
        data_venc    = datas_calc.get("vencimento", "") or str(data_vencimento_processo or "").strip()
        data_apuracao = datas_calc.get("apuracao", "") or str(apuracao_usuario or "").strip()

        if not data_venc:
            print(
                f"  [AVISO] DDF050 [{idx+1}/{len(ddf050_list)}]: data de vencimento não "
                f"calculada (NFs sem 'Data de Emissão'?). Informe a data na tela inicial."
            )

        erros_antes = len(erros)
        ok = _preencher_deducao_darf_total(
            pagina,
            ded,
            idx,
            len(ddf050_list),
            "DDF050",
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
            print(f"  ✗ DDF050 [{idx+1}/{len(ddf050_list)}]: erro — parando este bloco.")
            todos_ok = False
            break

    if todos_ok:
        print(f"  ✓ DDF050 concluído ({len(ddf050_list)} lançamento/s).")

    return todos_ok
