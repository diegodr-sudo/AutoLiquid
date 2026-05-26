"""
comprasnet_deducao_ddr001.py
DDR001 — ISS (Imposto Sobre Serviços) — uma entrada por Nota Fiscal.

Importado e chamado por comprasnet_deducao.executar().
As funções auxiliares (_fill, _select, etc.) são importadas de comprasnet_deducao
com import tardio (lazy) para evitar importação circular.
"""
import re
import logging
from comprasnet.base import normalizar_valor
from core.datas_impostos import calcular_datas

log = logging.getLogger(__name__)


def executar_ddr001(
    pagina,
    ddr001_list: list,
    notas: list,
    *,
    cnpj_fmt: str,
    dados_extraidos: dict,
    data_vencimento_processo: str = "",
    erros: list,
    deve_parar=None,
) -> bool:
    """
    Processa todas as deduções DDR001 (ISS), criando uma entrada por Nota Fiscal.

    Parâmetros
    ----------
    pagina               : instância Playwright da página atual
    ddr001_list          : lista de dicts de dedução (tipo DDR001)
    notas                : lista de NFs do documento de liquidação
    cnpj_fmt             : CNPJ do fornecedor já formatado
    dados_extraidos      : dicionário completo do PDF
    data_vencimento_processo : data de vencimento informada pelo usuário (fallback)
    erros                : lista mutável onde erros são acumulados
    deve_parar           : callable opcional de interrupção cooperativa

    Retorna
    -------
    bool  True se todas as deduções foram concluídas sem erro crítico.
    """
    # Import tardio — evita circular com comprasnet_deducao
    from comprasnet.deducao import (
        _verificar_interrupcao,
        _normalizar_data,
        _formatar_valor_br,
        _codigo_municipio_deducao,
        _ded_valor,
        _ded_base_calculo,
        _preencher_ddr001_nf,
        _aguardar_portal_limpo_entre_tipos,
        _MUNICIPIO_NOME,
        _MUNICIPIO_COD_RECEITA,
    )

    if not ddr001_list:
        return True

    if not notas:
        erros.append("DDR001: nenhuma Nota Fiscal encontrada no PDF para lançar.")
        return False

    print(f"\n  ══ DDR001 ({len(ddr001_list)} situação/ões · ISS) ══════════════════")

    emps    = dados_extraidos.get("Empenhos", [])
    recurso = str((emps[0].get("Recurso") if emps else "1") or "1").strip()
    datas_emissao = [_normalizar_data(n.get("Data de Emissão", "")) for n in notas]

    # Ordena NFs por número crescente
    def _num_nf_sort(n):
        try:
            return int(re.sub(r"\D", "", n.get("Número da Nota", "0")) or "0")
        except Exception:
            return 0

    notas_ord = sorted(notas, key=_num_nf_sort)

    todos_ok = True

    for ded in ddr001_list:
        _verificar_interrupcao(deve_parar)

        cod_mun     = _codigo_municipio_deducao(ded)
        nome_mun    = _MUNICIPIO_NOME.get(cod_mun, cod_mun)
        cod_receita = _MUNICIPIO_COD_RECEITA.get(cod_mun, "")

        datas_calc = calcular_datas(cod_mun, datas_emissao)
        data_venc  = datas_calc.get("vencimento", "") or str(data_vencimento_processo or "").strip()
        if cod_mun == "8105" and data_vencimento_processo:
            data_venc = str(data_vencimento_processo).strip()
        if not data_venc:
            print(f"  [AVISO] DDR001 {cod_mun}: data de vencimento não calculada. "
                  f"datas_emissao={datas_emissao}")

        try:
            total_iss = float(normalizar_valor(_ded_valor(ded)))
        except Exception:
            total_iss = 0.0

        # Alíquota = valor_deducao / soma_total_das_NFs * 100
        # NÃO usar "Base Cálculo" da dedução — ela é a base do rateio parcial
        # (ex: R$ 19.232,59), não o total das NFs (ex: R$ 119.232,59).
        # Usar a base errada resulta em alíquota ~15,5% em vez dos 2,5% corretos.
        try:
            total_nf_val = sum(
                float(normalizar_valor(n.get("Valor", "0") or "0"))
                for n in notas
            )
            aliquota_pct = (total_iss / total_nf_val * 100) if total_nf_val > 0 else 0.0
        except Exception:
            aliquota_pct = 0.0

        print(
            f"  Município: {cod_mun} ({nome_mun})  "
            f"Receita: {cod_receita}  Alíquota: {aliquota_pct:.4f}%  "
            f"Total ISS: {_formatar_valor_br(str(total_iss))}"
        )

        acum = 0.0
        for i, nf in enumerate(notas_ord):
            _verificar_interrupcao(deve_parar)
            # Barreira aplicada SEMPRE — independente do índice da NF.
            # Garante comportamento idêntico para 1ª, 2ª, 3ª, 4ª... NF:
            # sem AJAX residual, sem overlay, botão '+' disponível + buffer 1.5s.
            # Para a 1ª NF o portal já está limpo; a função retorna rapidamente.
            _aguardar_portal_limpo_entre_tipos(pagina)
            try:
                nf_val = float(normalizar_valor(nf.get("Valor", "0")))
            except Exception:
                nf_val = 0.0

            if i < len(notas_ord) - 1:
                iss_nf = round(nf_val * aliquota_pct / 100, 2)
            else:
                iss_nf = round(total_iss - acum, 2)  # Última NF: usa o restante
            acum += iss_nf

            erros_antes = len(erros)
            ok = _preencher_ddr001_nf(
                pagina, nf, i, len(notas_ord),
                cod_mun, nome_mun, cod_receita,
                data_venc, recurso, aliquota_pct,
                iss_nf, cnpj_fmt, dados_extraidos, erros,
                deve_parar=deve_parar,
            )
            if not ok or len(erros) > erros_antes:
                print(f"  ✗ DDR001 NF {i+1}/{len(notas_ord)}: erro — parando este município.")
                todos_ok = False
                break

    return todos_ok
