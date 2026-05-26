"""
comprasnet_principal_orcamento.py
Preenche a aba Principal Com Orçamento.

Situações implementadas: DSP001, DSP101, DSP102, DSP201, BPV001, 201, 101, 102, 001 (legado).

Para adicionar uma nova situação:
    1. Crie (ou edite) o arquivo em situacoes/
    2. Importe o handler aqui
    3. Adicione a chave em _HANDLERS
"""
import re
import time
import logging

from comprasnet.base import (
    conectar,
    achar_elemento,
    extrair_codigo_situacao,
    extrair_siafi_completo,
    config_situacao,
    _PREFERENCIA_SITUACAO,
    clicar_aba_generica,
    aguardar_aba_ativa,
)
from comprasnet.principal_helpers import (
    ExecucaoInterrompida,
    _verificar_interrupcao,
    _preencher_campo_com_retry,
)

# Handlers por situação
from comprasnet.situacoes.dsp001 import _preencher_situacao_DSP001
from comprasnet.situacoes.dsp101_102 import _preencher_situacao_DSP101_102
from comprasnet.situacoes.dsp201 import _preencher_situacao_DSP201
from comprasnet.situacoes.legado import (
    _preencher_situacao_201,
    _preencher_situacao_001_bpv,
    _preencher_situacao_101_102,
)

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# TABELA DE DESPACHO
# ─────────────────────────────────────────────────────────────────────────────

_HANDLERS = {
    "DSP001": _preencher_situacao_DSP001,
    "DSP101": _preencher_situacao_DSP101_102,
    "DSP102": _preencher_situacao_DSP101_102,
    "DSP201": _preencher_situacao_DSP201,
    "BPV001": _preencher_situacao_001_bpv,
    "201":    _preencher_situacao_201,        # legado numérico (sem prefixo DSP)
    "101":    _preencher_situacao_101_102,
    "102":    _preencher_situacao_101_102,
    "001":    _preencher_situacao_001_bpv,    # legado
}


# ─────────────────────────────────────────────────────────────────────────────
# SELEÇÃO DE SITUAÇÃO NO DROPDOWN
# ─────────────────────────────────────────────────────────────────────────────

def _selecionar_situacao_dropdown(pagina, cod_completo: str, cod_numerico: str) -> bool:
    """
    Seleciona a situação no dropdown da aba Principal Com Orçamento.
    Tenta primeiro pelo código completo (ex: 'DSP001'), depois pelo numérico ('001').
    """
    sel = achar_elemento(pagina, "Situação:")

    if cod_completo:
        valor = pagina.evaluate(
            """([el, txt]) => {
                const op = Array.from(el.options).find(
                    o => o.text.toUpperCase().includes(txt.toUpperCase())
                );
                return op ? op.value : null;
            }""",
            [sel.element_handle(), cod_completo],
        )
        if valor:
            sel.select_option(value=valor)
            time.sleep(1.5)
            print(f"    Situação selecionada: {cod_completo}")
            return True

    if cod_numerico:
        preferido = _PREFERENCIA_SITUACAO.get(cod_numerico, cod_numerico)
        for buscar in ([preferido, cod_numerico] if preferido != cod_numerico else [cod_numerico]):
            valor = pagina.evaluate(
                """([el, txt]) => {
                    const op = Array.from(el.options).find(
                        o => o.text.toUpperCase().includes(txt.toUpperCase())
                    );
                    return op ? op.value : null;
                }""",
                [sel.element_handle(), buscar],
            )
            if valor:
                sel.select_option(value=valor)
                time.sleep(1.5)
                print(f"    Situação selecionada (fallback numérico): {buscar}")
                return True

    return False


# ─────────────────────────────────────────────────────────────────────────────
# UTILITÁRIOS DA ABA PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def _revalidar_favorecido_contrato(pagina, ig_code: str, erros: list) -> None:
    ig_esperado = str(ig_code or "").strip()
    if not ig_esperado:
        return
    try:
        campo_fav = pagina.locator(
            "xpath=//*[normalize-space(text())='Favorecido do Contrato']"
            "/following::input[1]"
        ).first
        valor_atual = ""
        try:
            valor_atual = campo_fav.input_value().strip()
        except Exception:
            pass

        if valor_atual == ig_esperado:
            return

        print(
            f"    Favorecido do Contrato divergente antes da confirmação "
            f"(atual: '{valor_atual or 'vazio'}', esperado: '{ig_esperado}'). Repreenchendo..."
        )
        _preencher_campo_com_retry(
            pagina,
            campo_fav,
            ig_esperado,
            erros,
            descricao="Favorecido do Contrato",
            tentativas=3,
            delay_entre=1.0,
        )
    except Exception as e:
        erros.append(f"Erro ao revalidar 'Favorecido do Contrato': {e}")


def _abrir_aba_principal_orcamento(pagina, timeout_ms: int = 10000) -> None:
    """Navega para a aba Principal Com Orçamento de forma resiliente."""
    import time as _time

    seletores_conteudo = [
        "button[name='confirma-dados-pco']",
        "#pco-situacao",
        "select[name='pco-situacao']",
        "[id*='situacao'][id*='pco'], [name*='situacao'][name*='pco']",
    ]
    if aguardar_aba_ativa(pagina, seletores_conteudo, timeout_ms=800):
        return

    textos = [
        "Principal Com Orçamento",
        "Principal com Orçamento",
        "Principal Com Orcamento",
        "Principal com Orcamento",
        "Principal",
    ]

    css_candidatos = [
        "#principal-com-orcamento-tab",
        "#pco-tab",
        "a[href='#principal-com-orcamento']",
        "a[href='#pco']",
        "a[data-target='#principal-com-orcamento']",
        "button[aria-controls='principal-com-orcamento']",
        "a[aria-controls='pco']",
    ]
    clicou = pagina.evaluate(
        """(candidatos) => {
            const visivel = (el) => {
                if (!el) return false;
                const r = el.getBoundingClientRect();
                const s = window.getComputedStyle(el);
                return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
            };
            for (const sel of candidatos) {
                try {
                    const el = document.querySelector(sel);
                    if (visivel(el)) { el.click(); return sel; }
                } catch {}
            }
            return '';
        }""",
        css_candidatos,
    )
    if clicou and aguardar_aba_ativa(pagina, seletores_conteudo, timeout_ms=3000):
        return

    for texto in textos:
        if clicar_aba_generica(pagina, texto, timeout_ms=3000):
            _time.sleep(0.4)
            if aguardar_aba_ativa(pagina, seletores_conteudo, timeout_ms=3000):
                return

    try:
        pagina.locator("text=Principal Com Orçamento").first.click(timeout=5000)
        _time.sleep(0.8)
        return
    except Exception:
        pass

    raise RuntimeError(
        "Aba Principal Com Orçamento não encontrada. "
        "Verifique se o documento está aberto no portal Comprasnet."
    )


# ─────────────────────────────────────────────────────────────────────────────
# ENTRADA PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def executar(dados_extraidos, deve_parar=None, *, pagina=None, playwright=None):
    sessao_propria = pagina is None
    if sessao_propria:
        playwright, pagina = conectar()

    try:
        print("=== PRINCIPAL COM ORÇAMENTO ===")
        erros = []

        _abrir_aba_principal_orcamento(pagina)
        time.sleep(0.3)

        for idx, emp in enumerate(dados_extraidos.get("Empenhos", [])):
            _verificar_interrupcao(deve_parar)
            num = emp.get("Empenho", "")
            raw = emp.get("Situação", "")

            cod_completo = extrair_siafi_completo(raw)
            cod_numerico = extrair_codigo_situacao(raw)
            chave = cod_completo if cod_completo else cod_numerico
            cfg   = config_situacao(chave)

            print(
                f"\n  [{idx+1}] Empenho: {num} | raw: '{raw}' "
                f"| completo: '{cod_completo}' | numérico: '{cod_numerico}'"
            )

            if cfg is None:
                erros.append(
                    f"Situação '{chave}' (raw: '{raw}') ainda não implementada. "
                    "Preencha manualmente."
                )
                continue

            ok = _selecionar_situacao_dropdown(pagina, cod_completo, cod_numerico)
            if not ok:
                erros.append(f"Empenho {num}: não foi possível selecionar situação '{chave}'.")
                continue

            handler = _HANDLERS.get(cod_completo) or _HANDLERS.get(cod_numerico)
            if handler:
                handler(
                    pagina,
                    num,
                    cfg,
                    erros,
                    dados_extraidos=dados_extraidos,
                    deve_parar=deve_parar,
                )
            else:
                erros.append(f"Handler para situação '{chave}' não implementado.")

        # Confirma aba (somente sem erros)
        if not erros:
            try:
                _revalidar_favorecido_contrato(pagina, dados_extraidos.get("IG", ""), erros)
                btn = pagina.locator("button[name='confirma-dados-pco']").first
                btn.wait_for(state="visible", timeout=5000)
                btn.click()
                time.sleep(2.0)
                print("\n  Confirmado.")
            except Exception as e:
                erros.append(f"Erro ao confirmar Principal Com Orçamento: {e}")

        if erros:
            return {"status": "alerta", "mensagem": "\n".join(erros)}
        return {"status": "sucesso", "mensagem": "Principal Com Orçamento preenchido!"}

    except ExecucaoInterrompida as e:
        return {"status": "interrompido", "mensagem": str(e)}
    except Exception as e:
        return {"status": "erro", "mensagem": str(e)}
    finally:
        if sessao_propria and playwright is not None:
            playwright.stop()
