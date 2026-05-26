"""
comprasnet_centro_custo.py
Preenche a aba Centro de Custo no Contratos.gov.br.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime

from comprasnet.base import (
    conectar,
    extrair_codigo_situacao,
    extrair_siafi_completo,
)
from services.web_config_service import carregar_tabela_web

log = logging.getLogger(__name__)

_CC_GENERICO = "cc-generico"
_UG_BENEFICIADA = "153163"
_SITUACOES_SEM_CC = {"101", "201", "DSP101", "DSP201"}
_MAPA_CAMPOS_CC = {
    "Centro de Custo:": "input[name='codcentrocusto[]']",
    "Mês:": "input[name='mesreferencia[]']",
    "Ano:": "input[name='anoreferencia[]']",
    "Código SIORG:": "input[name='codsiorg[]']",
    "UG Beneficiada:": "input[name='codugbenef[]']",
}

_ERRO_SEM_ITENS_CC = (
    "não existem itens de principal com orçamento",
    "nao existem itens de principal com orcamento",
    "er0642",
)


class CentroCustoNaoAplicavel(RuntimeError):
    """SIAFI informou que nao ha itens para Centro de Custo neste documento."""


def _texto_pagina_normalizado(pagina) -> str:
    try:
        texto = pagina.locator("body").inner_text(timeout=300)
    except Exception:
        try:
            texto = pagina.evaluate("() => document.body ? document.body.innerText : ''")
        except Exception:
            texto = ""
    return (
        str(texto or "")
        .replace("ã", "a")
        .replace("á", "a")
        .replace("â", "a")
        .replace("à", "a")
        .replace("é", "e")
        .replace("ê", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ô", "o")
        .replace("õ", "o")
        .replace("ú", "u")
        .replace("ç", "c")
        .lower()
    )


def _verificar_sem_itens_centro_custo(pagina) -> None:
    texto = _texto_pagina_normalizado(pagina)
    if any(marcador in texto for marcador in _ERRO_SEM_ITENS_CC):
        raise CentroCustoNaoAplicavel(
            "Centro de Custo não aplicável: o SIAFI informou que não existem "
            "itens de Principal com Orçamento, Principal sem Orçamento, Outros "
            "Lançamentos ou Encargos para esta aba."
        )


def _normalizar_codigo_situacao(raw: str) -> str:
    texto = str(raw or "").strip().upper()
    if not texto:
        return ""
    siafi = extrair_siafi_completo(texto)
    if siafi:
        return siafi
    return extrair_codigo_situacao(texto).upper()


def _codigos_documento(dados_extraidos: dict) -> list[str]:
    empenhos = dados_extraidos.get("Empenhos", []) or []
    return [
        codigo
        for codigo in (
            _normalizar_codigo_situacao(empenho.get("Situação", ""))
            for empenho in empenhos
        )
        if codigo
    ]


def requer_centro_custo(dados_extraidos: dict) -> bool:
    codigos = _codigos_documento(dados_extraidos)
    if not codigos:
        return False
    return any(codigo not in _SITUACOES_SEM_CC for codigo in codigos)


def _parse_data_nf(data_str: str) -> date | None:
    texto = str(data_str or "").strip()
    if not texto:
        return None
    for formato in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


def _data_mais_recente_nf(dados_extraidos: dict) -> date | None:
    notas = dados_extraidos.get("Notas Fiscais", []) or []
    datas = [
        data
        for data in (
            _parse_data_nf(nota.get("Data de Emissão", ""))
            for nota in notas
        )
        if data
    ]
    if not datas:
        return None
    return max(datas)


def _meses_de_distancia(mais_recente: date, hoje: date) -> int:
    meses = (hoje.year - mais_recente.year) * 12 + (hoje.month - mais_recente.month)
    return max(meses, 0)


def _mes_ano_centro_custo(dados_extraidos: dict, hoje: date | None = None) -> tuple[int, int]:
    hoje = hoje or date.today()
    referencia_nf = _data_mais_recente_nf(dados_extraidos)
    if referencia_nf and _meses_de_distancia(referencia_nf, hoje) <= 6:
        return referencia_nf.month, referencia_nf.year
    return hoje.month, hoje.year


def _apenas_digitos(valor: str) -> str:
    return "".join(ch for ch in str(valor or "") if ch.isdigit())


def _resolver_siorg_por_ugr(ugr: str) -> str:
    ugr_digitos = _apenas_digitos(ugr)
    if not ugr_digitos:
        return ""
    tabela = carregar_tabela_web("uorg")
    for row in tabela.get("rows", []):
        if _apenas_digitos(row.get("ugr", "")) == ugr_digitos:
            return str(row.get("uorg", "")).strip()
    return ""


def _abrir_aba_centro_custo(pagina) -> None:
    candidatos = [
        pagina.locator("#centro-custo-tab"),
        pagina.locator("a[href='#centro-custo'], a[data-target='#centro-custo']"),
        pagina.locator("button[aria-controls='centro-custo'], a[aria-controls='centro-custo']"),
        pagina.get_by_role("tab", name="Centro de Custo"),
        pagina.locator("text=Centro de Custo").first,
    ]

    ultimo_erro = None
    for candidato in candidatos:
        try:
            candidato.first.click(timeout=3000)
            time.sleep(0.2)
            _verificar_sem_itens_centro_custo(pagina)
            pagina.wait_for_function(
                """() => {
                    const visivel = (el) => {
                        if (!el) return false;
                        const rect = el.getBoundingClientRect();
                        const estilo = window.getComputedStyle(el);
                        return rect.width > 0
                            && rect.height > 0
                            && estilo.visibility !== 'hidden'
                            && estilo.display !== 'none';
                    };

                    const abas = Array.from(document.querySelectorAll(
                        "[id*='centro'][id*='custo'], [aria-controls*='centro'], [href*='centro'], a, button"
                    ));
                    const abaAtiva = abas.some((el) => {
                        const texto = String(el.textContent || '').trim().toLowerCase();
                        const ativa = el.classList.contains('active') || el.getAttribute('aria-selected') === 'true';
                        return texto.includes('centro de custo') && ativa;
                    });

                    const painel = document.querySelector(
                        "#centro-custo, [id*='centro'][id*='custo'], [class*='centro'][class*='custo']"
                    );
                    return abaAtiva || visivel(painel);
                }""",
                timeout=5000,
            )
            time.sleep(0.6)
            return
        except CentroCustoNaoAplicavel:
            raise
        except Exception as exc:
            ultimo_erro = exc

    raise RuntimeError(f"Aba Centro de Custo não encontrada ou não abriu corretamente: {ultimo_erro}")


def _aguardar_grade_centro_custo(pagina, timeout_ms: int = 20000) -> None:
    fim = time.monotonic() + (timeout_ms / 1000)
    ultimo_erro = None
    while time.monotonic() < fim:
        _verificar_sem_itens_centro_custo(pagina)
        try:
            ok = pagina.evaluate(
                """() => {
            const visivel = (el) => !!el && el.offsetParent !== null;
            const seletores = [
                "input[name=\'codcentrocusto[]\']",
                "input[name=\'mesreferencia[]\']",
                "input[name=\'anoreferencia[]\']",
                "input[name=\'codsiorg[]\']",
                "input[name=\'codugbenef[]\']",
            ];
            return seletores.every((sel) => Array.from(document.querySelectorAll(sel)).some(visivel));
        }"""
            )
            if ok:
                return
        except Exception as exc:
            ultimo_erro = exc
        time.sleep(0.25)
    _verificar_sem_itens_centro_custo(pagina)
    raise RuntimeError(f"Centro de Custo: grade não carregou no prazo. {ultimo_erro or ''}".strip())


def _set_valor_centro_custo(pagina, coluna: str, valor: str) -> None:
    ultimo_erro = None
    seletor = _MAPA_CAMPOS_CC.get(coluna)
    if not seletor:
        raise RuntimeError(f"Campo nao mapeado no Centro de Custo: '{coluna}'")
    for _ in range(4):
        try:
            _aguardar_grade_centro_custo(pagina)
            campos = pagina.locator(f"{seletor}:visible")
            total = campos.count()
            if total == 0:
                raise RuntimeError(f"Centro de Custo: campo '{coluna}' nao esta visivel.")

            pendentes = []
            for indice in range(total):
                campo = campos.nth(indice)
                campo.wait_for(state="visible", timeout=5000)
                campo.click(click_count=3)
                try:
                    campo.fill("")
                except Exception:
                    pass
                campo.fill(str(valor))
                pagina.keyboard.press("Tab")
                valor_final = campo.input_value().strip()
                if valor_final != str(valor):
                    pendentes.append(f"{indice + 1}:{valor_final or 'vazio'}")

            if not pendentes:
                time.sleep(0.2)
                return
            ultimo_erro = RuntimeError(
                f"Centro de Custo: campo '{coluna}' ficou divergente em {', '.join(pendentes)}"
            )
        except CentroCustoNaoAplicavel:
            raise
        except Exception as exc:
            ultimo_erro = exc
        time.sleep(0.5)
    raise RuntimeError(str(ultimo_erro or f"Campo nao encontrado no Centro de Custo: '{coluna}'"))


def _marcar_linha_centro_custo(pagina) -> None:
    ultimo_erro = None
    for _ in range(4):
        try:
            _aguardar_grade_centro_custo(pagina)
            checks = pagina.locator("input[type='checkbox'][name^='numseqpai_checkbox']:visible")
            total = checks.count()
            if total == 0:
                checks = pagina.locator("input[type='checkbox']:visible")
                total = checks.count()
            if total == 0:
                raise RuntimeError("Centro de Custo: nenhuma caixa de sele??o vis?vel.")

            faltantes = 0
            for indice in range(total):
                check = checks.nth(indice)
                check.wait_for(state="visible", timeout=5000)
                try:
                    if not check.is_checked():
                        check.check(timeout=3000)
                except Exception:
                    check.click()
                if not check.is_checked():
                    faltantes += 1

            if faltantes == 0:
                time.sleep(0.2)
                return
            ultimo_erro = RuntimeError("Centro de Custo: nao foi possivel marcar todas as caixas de selecao.")
        except CentroCustoNaoAplicavel:
            raise
        except Exception as exc:
            ultimo_erro = exc
        time.sleep(0.5)
    raise RuntimeError(str(ultimo_erro or "Centro de Custo: nao foi possivel marcar as caixas de selecao."))


def _set_valor_por_label(pagina, label: str, valor: str) -> None:
    _set_valor_centro_custo(pagina, label, valor)


def _confirmar_centro_custo(pagina) -> None:
    _aguardar_grade_centro_custo(pagina)
    try:
        btn = pagina.locator("#confirma-dados-centro-custo:visible").first
        btn.wait_for(state="visible", timeout=5000)
        btn.scroll_into_view_if_needed()
        btn.click()
        pagina.wait_for_timeout(400)
        return
    except Exception:
        pass

    try:
        pagina.locator("button:visible").filter(has_text="Confirmar Dados Centro de Custo").first.click()
        pagina.wait_for_timeout(400)
        return
    except Exception:
        pass

    ok = pagina.evaluate(
        """() => {
            const visivel = (el) => !!el && el.offsetParent !== null;
            const botao = document.querySelector('#confirma-dados-centro-custo')
                || Array.from(document.querySelectorAll('button')).find((el) =>
                    visivel(el) && String(el.textContent || '').includes('Confirmar Dados Centro de Custo')
                );
            if (!botao) return false;
            botao.scrollIntoView({ behavior: 'instant', block: 'center' });
            botao.click();
            return true;
        }"""
    )
    if not ok:
        raise RuntimeError("Centro de Custo: botao de confirmacao nao encontrado.")
    pagina.wait_for_timeout(400)


def executar(
    dados_extraidos: dict,
    ugr_numero: str = "",
    deve_parar=None,
    *,
    pagina=None,
    playwright=None,
):
    if not requer_centro_custo(dados_extraidos):
        print("=== CENTRO DE CUSTO === [PULADA — não aplicável para esta situação]")
        return {
            "status": "pulado",
            "mensagem": "Centro de Custo não aplicável para esta situação.",
        }

    ugr_limpa = _apenas_digitos(ugr_numero)
    if not ugr_limpa:
        return {
            "status": "erro",
            "mensagem": "Centro de Custo: informe a UGR antes de executar esta etapa.",
        }

    siorg = _resolver_siorg_por_ugr(ugr_limpa)
    if not siorg:
        return {
            "status": "erro",
            "mensagem": f"Centro de Custo: a UGR {ugr_limpa} não foi encontrada na tabela UORG.",
        }

    mes_cc, ano_cc = _mes_ano_centro_custo(dados_extraidos)

    if deve_parar and deve_parar():
        return {"status": "pulado", "mensagem": "Execução interrompida antes do Centro de Custo."}

    sessao_propria = pagina is None
    if sessao_propria:
        playwright, pagina = conectar()
    try:
        print("=== CENTRO DE CUSTO ===")
        print(f"  Centro de Custo: {_CC_GENERICO}")
        print(f"  Mês/Ano: {mes_cc}/{ano_cc}")
        print(f"  Código SIORG: {siorg}")
        print(f"  UG Beneficiada: {_UG_BENEFICIADA}")

        _abrir_aba_centro_custo(pagina)
        _verificar_sem_itens_centro_custo(pagina)
        _set_valor_centro_custo(pagina, "Centro de Custo:", _CC_GENERICO)
        _set_valor_por_label(pagina, "Mês:", str(mes_cc))
        _set_valor_centro_custo(pagina, "Ano:", str(ano_cc))
        _set_valor_por_label(pagina, "Código SIORG:", str(siorg))
        _set_valor_centro_custo(pagina, "UG Beneficiada:", _UG_BENEFICIADA)
        _marcar_linha_centro_custo(pagina)

        if deve_parar and deve_parar():
            return {"status": "pulado", "mensagem": "Execução interrompida antes da confirmação do Centro de Custo."}

        _confirmar_centro_custo(pagina)
        return {"status": "sucesso", "mensagem": "Centro de Custo confirmado!"}
    except CentroCustoNaoAplicavel as exc:
        print(f"=== CENTRO DE CUSTO === [PULADA — {exc}]")
        return {"status": "pulado", "mensagem": str(exc)}
    except Exception as exc:
        log.error("Erro geral em Centro de Custo: %s", exc)
        return {"status": "erro", "mensagem": str(exc)}
    finally:
        if sessao_propria and playwright is not None:
            playwright.stop()
