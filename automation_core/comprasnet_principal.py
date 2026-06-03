from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from comprasnet.base import config_situacao, extrair_codigo_situacao, extrair_siafi_completo
from comprasnet.principal_helpers import (
    _capturar_empenhos_web,
    _comparar_empenhos_pdf_web,
    _buscar_vpd,
    _valor_conta_estoque_formatado,
    _valor_contas_a_pagar_formatado,
)
from core.de_para_contratos import buscar_ig, formatar_sarf

from .diagnostics import capture_failure_context
from .manifest import capture_page_manifest
from .models import FieldSpec, FieldType, StepResult, StepSpec
from .playwright_protocols import LocatorLike, PageLike
from .runner import run_step


DEFAULT_ARTIFACT_DIR = str(Path.home() / "Documents" / "AutoLiquid" / "falhas-automacao")


@dataclass(frozen=True)
class PrincipalPilotOptions:
    dry_run: bool = True
    artifact_dir: str = DEFAULT_ARTIFACT_DIR
    confirm_selector: str = "button[name='confirma-dados-pco']"
    capture_manifest: bool = True
    validar_empenhos_web: bool = True


def _digits(value: str) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def _format_empenho(value: str) -> str:
    raw = str(value or "").strip()
    return re.sub(r"^(\d{4})(\d{6})$", r"\1NE\2", raw)


def _normalizar_situacao(raw: str) -> str:
    return extrair_siafi_completo(raw) or extrair_codigo_situacao(raw)


def _resolver_por_prefixo(prefixo: str):
    def _resolver(page: PageLike, _spec: FieldSpec) -> LocatorLike:
        sufixo = str(page.evaluate("() => document.body.getAttribute('data-autoliquid-empenho-sufixo') || ''") or "")
        if sufixo:
            locator = page.locator(f"#{prefixo}{sufixo}").first
            if locator.count() > 0:
                return locator
        return page.locator(f"[data-autoliquid-empenho-atual='1'] input[id^='{prefixo}']").first

    return _resolver


def _resolver_por_prefixo_situacao(prefixo: str):
    def _resolver(page: PageLike, _spec: FieldSpec) -> LocatorLike:
        sufixo = str(page.evaluate("() => document.body.getAttribute('data-autoliquid-situacao-sufixo') || ''") or "")
        if sufixo:
            locator = page.locator(f"#{prefixo}{sufixo}").first
            if locator.count() > 0:
                return locator
        return page.locator(f"input[id^='{prefixo}']:visible").first

    return _resolver


def _resolver_ig_contrato(dados: dict[str, Any]) -> str:
    ig = str(dados.get("IG") or "").strip()
    if ig:
        return ig
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
    return ig


def _equivalente_digitos(observed: str, expected: str) -> bool:
    esperado = _digits(expected)
    atual = _digits(observed)
    if not esperado or not atual:
        return False
    if esperado in atual:
        return True
    esperado_sem_zero = esperado.lstrip("0")
    atual_sem_zero = atual.lstrip("0")
    if esperado_sem_zero and atual_sem_zero and esperado_sem_zero in atual_sem_zero:
        return True
    if len(esperado) >= 11 and len(atual) >= 11:
        return esperado.replace("0", "") == atual.replace("0", "")
    return False


def _equivalente_contas_a_pagar(_locator: Any, expected: str) -> bool:
    try:
        observed = _locator.input_value()
    except Exception:
        observed = ""
    atual = _digits(observed)
    esperado = _digits(expected)
    if atual == esperado:
        return True
    equivalencias = {
        "104": {"213110400"},
        "1104": {"213111000", "213110400"},
    }
    return atual in equivalencias.get(esperado, set())


def _campo_tem_valor(locator: Any, _expected: str) -> bool:
    try:
        return bool(str(locator.input_value() or "").strip())
    except Exception:
        return False


def _normalizar_vpd_para_campo(vpd: str) -> str:
    return re.sub(r"(?i)x", "1", str(vpd or "").strip())


def abrir_aba_principal(page: PageLike) -> None:
    """Best-effort navigation to the Principal com Orçamento tab."""

    ready_selectors = [
        "button[name='confirma-dados-pco']",
        "#pco-situacao",
        "select[name='pco-situacao']",
        "[id*='situacao'][id*='pco'], [name*='situacao'][name*='pco']",
    ]
    for selector in ready_selectors:
        try:
            locator = page.locator(selector)
            if locator.count() > 0:
                return
        except Exception:
            pass

    clicked = page.evaluate(
        """
        () => {
          const visible = (el) => {
            if (!el) return false;
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 && rect.height > 0
              && style.visibility !== "hidden"
              && style.display !== "none";
          };
          const exactTexts = [
            "Principal Com Orçamento",
            "Principal com Orçamento",
            "Principal Com Orcamento",
            "Principal com Orcamento"
          ];
          const nodes = Array.from(document.querySelectorAll("a, button, [role='tab'], li"));
          for (const text of exactTexts) {
            const node = nodes.find((el) => visible(el) && String(el.textContent || "").trim() === text);
            if (node) {
              node.click();
              return text;
            }
          }
          return "";
        }
        """
    )
    if clicked:
        page.wait_for_timeout(500)
        return
    raise RuntimeError("Aba Principal com Orçamento não encontrada.")


def selecionar_situacao(page: PageLike, situacao: str) -> None:
    sufixo_existente = page.evaluate(
        """
        (situacao) => {
          const norm = (txt) => String(txt || "").trim().toUpperCase();
          const visible = (el) => {
            if (!el) return false;
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 && rect.height > 0
              && style.visibility !== "hidden"
              && style.display !== "none";
          };
          const select = Array.from(document.querySelectorAll("select[id^='codsit']"))
            .find((el) => visible(el) && norm(el.options?.[el.selectedIndex]?.textContent || el.value).includes(norm(situacao)));
          const suffix = String(select?.id || "").match(/^codsit(.+)$/)?.[1] || "";
          if (suffix) document.body.setAttribute("data-autoliquid-situacao-sufixo", suffix);
          return suffix;
        }
        """,
        situacao,
    )
    if sufixo_existente:
        return

    selector = FieldSpec(
        name="situacao",
        value=situacao,
        label="Situação:",
        selectors=(
            "#pco-situacao",
            "select[name='pco-situacao']",
            "xpath=//*[normalize-space(text())='Situação:']/following::select[1]",
        ),
        field_type=FieldType.SELECT,
        metadata={"option_text_contains": situacao},
        retries=2,
        settle_ms=1200,
    )
    result = run_step(page, StepSpec(name=f"selecionar-situacao-{situacao}", fields=(selector,)))
    if not result.ok:
        raise RuntimeError(result.message or f"Não foi possível selecionar situação {situacao}.")
    sufixo = page.evaluate(
        """
        (situacao) => {
          const norm = (txt) => String(txt || "").trim().toUpperCase();
          const visible = (el) => {
            if (!el) return false;
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 && rect.height > 0
              && style.visibility !== "hidden"
              && style.display !== "none";
          };
          const selects = Array.from(document.querySelectorAll("select[id^='codsit']"))
            .filter((el) => visible(el) && norm(el.options?.[el.selectedIndex]?.textContent || el.value).includes(norm(situacao)));
          const select = selects[0] || Array.from(document.querySelectorAll("select[id^='codsit']")).find((el) => visible(el));
          const suffix = String(select?.id || "").match(/^codsit(.+)$/)?.[1] || "";
          if (suffix) document.body.setAttribute("data-autoliquid-situacao-sufixo", suffix);
          return suffix;
        }
        """,
        situacao,
    )
    if not sufixo:
        raise RuntimeError(f"Não foi possível identificar o sufixo da situação {situacao}.")


def marcar_empenho_atual(page: PageLike, numero_empenho: str) -> None:
    numero = _format_empenho(numero_empenho)
    ok = page.evaluate(
        r"""
        (numEmp) => {
          const normalize = (txt) => String(txt || "").replace(/\s+/g, "").toUpperCase();
          const target = normalize(numEmp);
          const visible = (el) => {
            if (!el) return false;
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 && rect.height > 0
              && style.visibility !== "hidden"
              && style.display !== "none";
          };
          document.querySelectorAll('[data-autoliquid-empenho-atual="1"]')
            .forEach((el) => el.removeAttribute("data-autoliquid-empenho-atual"));
          document.body.removeAttribute("data-autoliquid-empenho-sufixo");
          document.body.removeAttribute("data-autoliquid-empenho-item-id");
          const inputs = Array.from(document.querySelectorAll('input[id^="numempe"]'))
            .filter((el) => normalize(el.value).includes(target));
          for (const input of inputs) {
            let panel = input.closest('.count-pco-item, .count-poo-item, [data-count-pco-item], [data-count-poo-item], .box.box-solid, .box, .panel, .card');
            if (!panel) panel = input.parentElement || input;
            panel.setAttribute("data-autoliquid-empenho-atual", "1");
            const suffix = String(input.id || "").match(/^numempe(.+)$/)?.[1] || "";
            if (suffix) document.body.setAttribute("data-autoliquid-empenho-sufixo", suffix);
            const itemId = String(panel.id || "").trim();
            if (itemId) document.body.setAttribute("data-autoliquid-empenho-item-id", itemId);
            panel.scrollIntoView({ block: "nearest", inline: "nearest" });
            return true;
          }
          return false;
        }
        """,
        numero,
    )
    if not ok:
        raise RuntimeError(f"Empenho {numero} não encontrado/expandido na página.")
    page.wait_for_timeout(800)


def _montar_valores_pco(dados: dict[str, Any], empenho: dict[str, Any]) -> dict[str, str]:
    situacao = _normalizar_situacao(str((empenho or {}).get("Situação") or ""))
    cfg = config_situacao(situacao) or {}
    natureza = str(dados.get("Natureza") or "").strip()
    vpd_manual = str(dados.get("VPD_MANUAL") or "").strip()
    valores: dict[str, str] = {}

    if situacao == "DSP001":
        if str(dados.get("Tem Contrato?", dados.get("Tem Contrato", "Não")) or "") == "Sim":
            valores["indrtemcontrato"] = "SIM"
            valores["numclassd"] = "8.1.2.3.1.02.01"
            ig = _resolver_ig_contrato(dados)
            if ig:
                valores["txtinscre"] = ig
        vpd = vpd_manual or _buscar_vpd(natureza, "DSP001")
        if vpd and "De acordo" not in vpd:
            valores["numclassa"] = _normalizar_vpd_para_campo(vpd)
        valores["numclassb"] = _valor_contas_a_pagar_formatado(str(cfg.get("contas_a_pagar") or "1104"))
        return valores

    if situacao in {"DSP101", "DSP102"}:
        if situacao == "DSP102":
            vpd = vpd_manual or _buscar_vpd(natureza, "DSP101/102")
            if vpd and "De acordo" not in vpd:
                valores["numclassa"] = _normalizar_vpd_para_campo(vpd)
            valores["numclassc"] = _valor_conta_estoque_formatado(str(cfg.get("conta_estoque") or "60100"))
        else:
            valores["numclassa"] = _valor_conta_estoque_formatado(str(cfg.get("conta_estoque") or "60100"))
        valores["numclassb"] = _valor_contas_a_pagar_formatado(str(cfg.get("contas_a_pagar") or "1104"))
        return valores

    if situacao in {"DSP201", "201"}:
        valores["numclassa"] = "1.2.3.1.1.08.01"
        valores["numclassb"] = _valor_contas_a_pagar_formatado(str(cfg.get("contas_a_pagar") or "104"))
        return valores

    valores["numclassb"] = _valor_contas_a_pagar_formatado(str(cfg.get("contas_a_pagar") or ""))
    return {key: value for key, value in valores.items() if value}


def preencher_pco_direto(page: PageLike, dados: dict[str, Any], empenho: dict[str, Any]) -> None:
    valores = _montar_valores_pco(dados, empenho)
    if not valores:
        return

    resultado = None
    for tentativa in range(1, 4):
        resultado = page.evaluate(
            """
            (valores) => {
              const situacaoSufixo = document.body.getAttribute("data-autoliquid-situacao-sufixo") || "";
              const empenhoSufixo = document.body.getAttribute("data-autoliquid-empenho-sufixo") || "";
              const digits = (value) => String(value || "").replace(/\\D/g, "");
              const equivalentDigits = (observed, expected) => {
                const expectedDigits = digits(expected);
                const observedDigits = digits(observed);
                if (!expectedDigits || !observedDigits) return false;
                if (observedDigits.includes(expectedDigits)) return true;
                const trimZeros = (value) => String(value || "").replace(/^0+/, "");
                const expectedTrimmed = trimZeros(expectedDigits);
                const observedTrimmed = trimZeros(observedDigits);
                if (expectedTrimmed && observedTrimmed && observedTrimmed.includes(expectedTrimmed)) return true;
                if (expectedDigits.length >= 11 && observedDigits.length >= 11) {
                  return expectedDigits.replaceAll("0", "") === observedDigits.replaceAll("0", "");
                }
                return false;
              };
              const setValue = (id, value) => {
                const el = document.getElementById(id);
                if (!el) return { id, ok: false, reason: "not_found", expected: value };
                const proto = el instanceof HTMLTextAreaElement
                  ? HTMLTextAreaElement.prototype
                  : HTMLInputElement.prototype;
                const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
                el.focus();
                if (window.$ && $(el).inputmask) {
                  try { $(el).inputmask("setvalue", value); } catch (e) {}
                }
                if (!el.value || !equivalentDigits(el.value, value)) {
                  if (setter) setter.call(el, value);
                  else el.value = value;
                }
                el.defaultValue = el.value || value;
                el.setAttribute("value", el.value || value);
                el.dispatchEvent(new InputEvent("input", { bubbles: true, cancelable: true }));
                el.dispatchEvent(new Event("blur", { bubbles: true }));
                return { id, ok: true, expected: value };
              };
              const setSelectNoChange = (id, wantedText) => {
                const el = document.getElementById(id);
                if (!el) return { id, ok: false, reason: "not_found", expected: wantedText };
                const wanted = String(wantedText || "").toUpperCase();
                const option = Array.from(el.options || []).find((item) =>
                  String(item.textContent || item.value || "").toUpperCase().includes(wanted)
                );
                if (option) el.value = option.value;
                return { id, ok: true, expected: wantedText };
              };
              const out = [];
              if (valores.indrtemcontrato && situacaoSufixo) {
                out.push(setSelectNoChange(`indrtemcontrato${situacaoSufixo}`, valores.indrtemcontrato));
              }
              if (valores.numclassd && situacaoSufixo) out.push(setValue(`numclassd${situacaoSufixo}`, valores.numclassd));
              if (valores.txtinscre && situacaoSufixo) out.push(setValue(`txtinscre${situacaoSufixo}`, valores.txtinscre));
              for (const prefix of ["numclassa", "numclassb", "numclassc"]) {
                if (valores[prefix] && empenhoSufixo) out.push(setValue(`${prefix}${empenhoSufixo}`, valores[prefix]));
              }
              if (document.activeElement && typeof document.activeElement.blur === "function") document.activeElement.blur();
              return out;
            }
            """,
            valores,
        )
        page.wait_for_timeout(900)
        resultado = page.evaluate(
            """
            (items) => {
              const digits = (value) => String(value || "").replace(/\\D/g, "");
              const equivalentDigits = (observed, expected) => {
                const expectedDigits = digits(expected);
                const observedDigits = digits(observed);
                if (!expectedDigits || !observedDigits) return false;
                if (observedDigits.includes(expectedDigits)) return true;
                const trimZeros = (value) => String(value || "").replace(/^0+/, "");
                const expectedTrimmed = trimZeros(expectedDigits);
                const observedTrimmed = trimZeros(observedDigits);
                if (expectedTrimmed && observedTrimmed && observedTrimmed.includes(expectedTrimmed)) return true;
                if (expectedDigits.length >= 11 && observedDigits.length >= 11) {
                  return expectedDigits.replaceAll("0", "") === observedDigits.replaceAll("0", "");
                }
                return false;
              };
              return (items || []).map((item) => {
                const el = document.getElementById(item.id);
                const after = el?.value || "";
                const stable = String(item.id || "").startsWith("indrtemcontrato")
                  || equivalentDigits(after, item.expected || "");
                return { ...item, after, stable };
              });
            }
            """,
            resultado,
        )
        instaveis = [
            item for item in (resultado or [])
            if item.get("ok") and not item.get("stable")
        ]
        if not instaveis:
            page.evaluate(
                """
                () => {
                  const itemId = document.body.getAttribute("data-autoliquid-empenho-item-id") || "";
                  const panel = itemId ? document.getElementById(itemId) : null;
                  const collapse = itemId ? document.getElementById(`collapse${itemId}`) : null;
                  try {
                    if (window.$ && collapse) $(collapse).collapse("hide");
                  } catch (e) {}
                  if (panel) panel.classList.add("collapsed-box");
                  if (collapse) {
                    collapse.classList.remove("in");
                    collapse.style.display = "";
                    collapse.style.height = "0px";
                    collapse.setAttribute("aria-expanded", "false");
                  }
                }
                """
            )
            break
        if tentativa < 3:
            page.wait_for_timeout(500)

    falhas = [item for item in (resultado or []) if not item.get("ok")]
    if falhas:
        raise RuntimeError(f"Preenchimento direto PCO falhou: {falhas}")
    divergentes = [
        item for item in (resultado or [])
        if item.get("ok") and not item.get("stable")
    ]
    if divergentes:
        raise RuntimeError(f"Preenchimento direto PCO não estabilizou: {divergentes}")


def build_fields_for_empenho(dados: dict[str, Any], empenho: dict[str, Any]) -> tuple[FieldSpec, ...]:
    raw_situacao = str(empenho.get("Situação") or "")
    situacao = _normalizar_situacao(raw_situacao)
    cfg = config_situacao(situacao) or {}
    natureza = str(dados.get("Natureza") or "").strip()
    vpd_manual = str(dados.get("VPD_MANUAL") or "").strip()
    fields: list[FieldSpec] = []

    if situacao == "DSP001":
        tem_contrato = str(dados.get("Tem Contrato?", dados.get("Tem Contrato", "Não")) or "")
        opcao = "SIM" if tem_contrato == "Sim" else "NÃO"
        fields.append(
            FieldSpec(
                name="tem_contrato",
                value=opcao,
                selectors=("xpath=//*[normalize-space(text())='Tem Contrato?']/following::select[1]",),
                field_type=FieldType.SELECT,
                metadata={"option_text_contains": opcao},
                settle_ms=1200,
            )
        )
        if tem_contrato == "Sim":
            fields.append(
                FieldSpec(
                    name="conta_contrato",
                    value="8.1.2.3.1.02.01",
                    field_type=FieldType.JS_VALUE,
                    resolver=_resolver_por_prefixo_situacao("numclassd"),
                    validator=lambda locator, expected: _equivalente_digitos(locator.input_value(), expected),
                    settle_ms=900,
                )
            )
            ig = _resolver_ig_contrato(dados)
            if ig:
                fields.append(
                    FieldSpec(
                        name="favorecido_contrato",
                        value=ig,
                        field_type=FieldType.JS_VALUE,
                        resolver=_resolver_por_prefixo_situacao("txtinscre"),
                        retries=3,
                        settle_ms=1000,
                    )
                )
        vpd = vpd_manual or _buscar_vpd(natureza, "DSP001")
        if vpd and "De acordo" not in vpd:
            fields.append(_vpd_field(vpd, prefixo="numclassa"))
        fields.append(_contas_a_pagar_field(str(cfg.get("contas_a_pagar") or "1104")))
        return tuple(fields)

    if situacao in {"DSP101", "DSP102"}:
        if situacao == "DSP102":
            vpd = vpd_manual or _buscar_vpd(natureza, "DSP101/102")
            if vpd and "De acordo" not in vpd:
                fields.append(_vpd_field(vpd))
        conta_estoque = str(cfg.get("conta_estoque") or "60100")
        fields.append(
            FieldSpec(
                name="conta_estoque",
                value=_valor_conta_estoque_formatado(conta_estoque),
                field_type=FieldType.MASKED,
                resolver=_resolver_por_prefixo("numclassa"),
                validator=lambda locator, expected: _equivalente_digitos(locator.input_value(), expected),
                retries=3,
                settle_ms=900,
            )
        )
        fields.append(_contas_a_pagar_field(str(cfg.get("contas_a_pagar") or "1104")))
        return tuple(fields)

    if situacao in {"DSP201", "201"}:
        vpd = vpd_manual or _buscar_vpd(natureza, "DSP201")
        if vpd and "De acordo" not in vpd:
            fields.append(_vpd_field(vpd))
        fields.append(
            FieldSpec(
                name="conta_bens_moveis",
                value="",
                field_type=FieldType.JS_VALUE,
                resolver=_resolver_por_prefixo("numclassa"),
                required=False,
                validator=_campo_tem_valor,
                retries=2,
                settle_ms=1000,
            )
        )
        fields.append(_contas_a_pagar_field(str(cfg.get("contas_a_pagar") or "104")))
        return tuple(fields)

    if situacao in {"BPV001", "001"}:
        fields.append(_contas_a_pagar_field(str(cfg.get("contas_a_pagar") or "104")))
        return tuple(fields)

    fields.append(_contas_a_pagar_field(str(cfg.get("contas_a_pagar") or "")))
    return tuple(field for field in fields if field.value)


def _vpd_field(vpd: str, prefixo: str = "numclassc") -> FieldSpec:
    return FieldSpec(
        name="vpd",
        value=vpd,
        field_type=FieldType.JS_VALUE,
        resolver=_resolver_por_prefixo(prefixo),
        validator=lambda locator, expected: _equivalente_digitos(locator.input_value(), expected.replace("X", "1").replace("x", "1")),
        retries=3,
        settle_ms=900,
    )


def _contas_a_pagar_field(codigo: str) -> FieldSpec:
    return FieldSpec(
        name="contas_a_pagar",
        value=_valor_contas_a_pagar_formatado(codigo),
        field_type=FieldType.JS_VALUE,
        resolver=_resolver_por_prefixo("numclassb"),
        validator=_equivalente_contas_a_pagar,
        retries=3,
        settle_ms=900,
    )


def build_principal_steps(dados: dict[str, Any]) -> tuple[StepSpec, ...]:
    steps: list[StepSpec] = []
    for index, empenho in enumerate(dados.get("Empenhos") or [], start=1):
        numero = str((empenho or {}).get("Empenho") or "")
        situacao = _normalizar_situacao(str((empenho or {}).get("Situação") or ""))
        steps.append(
            StepSpec(
                name=f"principal-orcamento-{index}-{_format_empenho(numero)}-{situacao}",
                preconditions=(
                    abrir_aba_principal,
                    lambda page, situacao=situacao: selecionar_situacao(page, situacao),
                    lambda page, numero=numero: marcar_empenho_atual(page, numero),
                    lambda page, dados=dados, empenho=empenho or {}: preencher_pco_direto(page, dados, empenho),
                ),
                fields=(),
            )
        )
    return tuple(steps)


def comparar_empenhos_pdf_web(page: PageLike, dados: dict[str, Any]) -> list[str]:
    """Return divergence lines in the same format used by the legacy UI renderer."""

    empenhos_pdf = list((dados or {}).get("Empenhos") or [])
    empenhos_web = _capturar_empenhos_web(page)
    return _comparar_empenhos_pdf_web(empenhos_pdf, empenhos_web)


def montar_mensagem_conferencia_manual(
    page: PageLike,
    dados: dict[str, Any],
    motivos_tecnicos: list[str] | tuple[str, ...] | None = None,
) -> str:
    linhas_cmp: list[str] = []
    try:
        linhas_cmp = comparar_empenhos_pdf_web(page, dados)
    except Exception:
        linhas_cmp = []

    partes: list[str] = ["Principal com Orçamento requer conferência manual:"]
    if linhas_cmp:
        partes.extend(linhas_cmp)
    else:
        partes.append("Não foi possível montar o comparativo PDF × IC automaticamente.")

    motivos = [str(item).strip() for item in (motivos_tecnicos or []) if str(item).strip()]
    if motivos:
        partes.append("")
        partes.append("Motivo técnico:")
        partes.extend(motivos)
    return "\n".join(partes)


def run_principal_orcamento_pilot(
    page: PageLike,
    dados: dict[str, Any],
    options: PrincipalPilotOptions | None = None,
    deve_parar: Callable[[], bool] | None = None,
) -> tuple[StepResult, ...]:
    """Run the PCO pilot automation without touching the existing production flow."""

    opts = options or PrincipalPilotOptions()
    results: list[StepResult] = []
    if opts.capture_manifest:
        try:
            capture_page_manifest(page)
        except Exception:
            pass

    for step in build_principal_steps(dados):
        if deve_parar and deve_parar():
            break
        result = run_step(page, step, artifact_dir=opts.artifact_dir)
        results.append(result)
        if not result.ok:
            try:
                capture_failure_context(page, opts.artifact_dir, step.name)
            except Exception:
                pass
            break

    if results and all(result.ok for result in results) and opts.validar_empenhos_web:
        try:
            mensagem_conferencia = montar_mensagem_conferencia_manual(page, dados)
            if "Empenho " in mensagem_conferencia or "Empenho ausente" in mensagem_conferencia or "Empenho exclusivo" in mensagem_conferencia:
                results.append(
                    StepResult(
                        "principal-orcamento-conferencia",
                        False,
                        message=mensagem_conferencia,
                    )
                )
        except Exception:
            pass

    if results and all(result.ok for result in results) and not opts.dry_run:
        if deve_parar and deve_parar():
            return tuple(results)
        button = page.locator(opts.confirm_selector).first
        button.wait_for(state="visible", timeout=8000)
        button.click()

    return tuple(results)
