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
    _capturar_empenhos_web,
    _comparar_empenhos_pdf_web,
)
from core.de_para_contratos import formatar_sarf, buscar_ig

# ─────────────────────────────────────────────────────────────────────────────
# UTILITÁRIO: aguardar recarga do formulário de situação
# ─────────────────────────────────────────────────────────────────────────────

def _aguardar_formulario_situacao(pagina, timeout_s: float = 6.0) -> bool:
    """Aguarda o formulário recarregar após seleção da situação via AJAX.

    Estratégia: após o select_option, o servidor devolve campos mascarados
    (ex: VPD, Conta Estoque, Contas a Pagar) com placeholder '_'.
    Assim que qualquer input visível do formulário exibir '_' no valor,
    o template da máscara está pronto para receber digitação.

    Retorna True quando pronto, False se expirou o timeout.
    """
    import time as _time
    inicio = _time.time()
    while _time.time() - inicio < timeout_s:
        try:
            tem_mascara = pagina.evaluate("""() => {
                const inputs = Array.from(document.querySelectorAll('input[type="text"], input:not([type])'));
                return inputs.some(el => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0 && (el.value || '').includes('_');
                });
            }""")
            if tem_mascara:
                return True
        except Exception:
            pass
        _time.sleep(0.15)
    return False

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
            if not _aguardar_formulario_situacao(pagina):
                time.sleep(1.0)   # fallback se a situação não tiver campos mascarados
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
                if not _aguardar_formulario_situacao(pagina):
                    time.sleep(1.0)   # fallback se a situação não tiver campos mascarados
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
        campo_fav = _localizar_campo_contrato(pagina)
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


def _localizar_campo_contrato(pagina):
    rotulos = [
        "Favorecido do Contrato",
        "Código do Contrato",
        "Codigo do Contrato",
        "Código de Contrato",
        "Codigo de Contrato",
    ]
    for rotulo in rotulos:
        campo = pagina.locator(
            f"xpath=//*[normalize-space(text())='{rotulo}']"
            "/following::input[1]"
        ).first
        try:
            campo.wait_for(state="visible", timeout=1200)
            return campo
        except Exception:
            continue
    raise RuntimeError("campo de contrato não encontrado")


def _resolver_ig_contrato(dados: dict, erros: list | None = None) -> str:
    ig_atual = str(dados.get("IG") or "").strip()
    if ig_atual:
        return ig_atual

    contrato = str(
        dados.get("Número do Contrato")
        or dados.get("Numero do Contrato")
        or dados.get("Contrato")
        or ""
    ).strip()
    sarf = str(dados.get("SARF") or "").strip()
    if not sarf and contrato:
        sarf = formatar_sarf(contrato)
        dados["SARF"] = sarf

    if not sarf:
        return ""

    ig = buscar_ig(sarf)
    if ig:
        dados["IG"] = ig
        print(f"    Contrato {contrato or sarf}: IC/IG resolvido pelo de/para ({ig}).")
        return ig

    if erros is not None:
        erros.append(
            f"Contrato {contrato or sarf}: IC/IG não encontrado no de/para de contratos."
        )
    return ""


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
        _resolver_ig_contrato(dados_extraidos)

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
                # Injeta o código da situação no dict de dados para que os
                # handlers possam adaptar o comportamento por situação.
                _resolver_ig_contrato(dados_extraidos)
                dados_handler = {**(dados_extraidos or {}), "_SITUACAO_NORM": cod_completo}
                handler(
                    pagina,
                    num,
                    cfg,
                    erros,
                    dados_extraidos=dados_handler,
                    deve_parar=deve_parar,
                )
            else:
                erros.append(f"Handler para situação '{chave}' não implementado.")

        # Confirma aba (somente sem erros)
        if not erros:
            try:
                ig_contrato = _resolver_ig_contrato(dados_extraidos, erros)
                _revalidar_favorecido_contrato(pagina, ig_contrato, erros)
                btn = pagina.locator("button[name='confirma-dados-pco']").first
                btn.wait_for(state="visible", timeout=5000)
                btn.click()
                time.sleep(2.0)
                print("\n  Confirmado.")
            except Exception as e:
                erros.append(f"Erro ao confirmar Principal Com Orçamento: {e}")

        if erros:
            # Ao falhar, monta um comparativo PDF × IC de cada empenho (capturando
            # o valor de cada barra na web) para que o painel exiba o quadro de
            # "Conferência manual necessária", em vez de só a mensagem técnica.
            try:
                empenhos_pdf = dados_extraidos.get("Empenhos", [])
                empenhos_web = _capturar_empenhos_web(pagina)
                linhas_cmp = _comparar_empenhos_pdf_web(empenhos_pdf, empenhos_web)
            except Exception as exc:
                print(f"  Aviso: comparativo de empenhos falhou ({exc}).")
                linhas_cmp = []

            # status "alerta": sinaliza divergência SEM parar a automação. A
            # etapa é marcada como "divergencia" (nem concluída, nem erro) e o
            # quadro de conferência manual aparece nas pendências.
            if linhas_cmp:
                partes = ["Principal com Orçamento requer conferência manual:"]
                partes.extend(linhas_cmp)
                partes.append("")
                partes.append("Motivo técnico:")
                partes.extend(erros)
                return {"status": "alerta", "mensagem": "\n".join(partes)}

            return {"status": "alerta", "mensagem": "\n".join(erros)}
        return {"status": "sucesso", "mensagem": "Principal Com Orçamento preenchido!"}

    except ExecucaoInterrompida as e:
        return {"status": "interrompido", "mensagem": str(e)}
    except Exception as e:
        return {"status": "erro", "mensagem": str(e)}
    finally:
        if sessao_propria and playwright is not None:
            playwright.stop()
