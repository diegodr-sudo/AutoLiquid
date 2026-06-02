#!/usr/bin/env python3
"""Captura um mapa detalhado da aba Principal com Orçamento aberta no Chrome.

Uso:
  python3 scripts/inspecionar_pco.py

Antes de rodar, deixe o Chrome da automação aberto exatamente na tela do
Principal com Orçamento que precisa ser mapeada. O script não preenche nem
clica em confirmar; ele só lê o DOM e salva JSON/HTML/screenshot.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from comprasnet.base import conectar


DEFAULT_OUT_DIR = Path.home() / "Documents" / "AutoLiquid" / "falhas-automacao" / "pco-dom"


JS_SNAPSHOT = r"""
() => {
  const clean = (value) => String(value ?? "").replace(/\s+/g, " ").trim();
  const visible = (el) => {
    if (!el || !el.getBoundingClientRect) return false;
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return rect.width > 0 && rect.height > 0
      && style.display !== "none"
      && style.visibility !== "hidden";
  };
  const rectOf = (el) => {
    const rect = el.getBoundingClientRect();
    return {
      x: Math.round(rect.x),
      y: Math.round(rect.y),
      width: Math.round(rect.width),
      height: Math.round(rect.height),
    };
  };
  const cssPath = (el) => {
    if (!el || !el.tagName) return "";
    if (el.id) return `#${CSS.escape(el.id)}`;
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1 && node !== document.body && parts.length < 7) {
      let part = node.tagName.toLowerCase();
      const name = node.getAttribute("name");
      if (name) part += `[name="${CSS.escape(name)}"]`;
      const cls = String(node.className || "").trim().split(/\s+/).filter(Boolean).slice(0, 2);
      if (cls.length) part += "." + cls.map((item) => CSS.escape(item)).join(".");
      const parent = node.parentElement;
      if (parent) {
        const siblings = Array.from(parent.children).filter((item) => item.tagName === node.tagName);
        if (siblings.length > 1) part += `:nth-of-type(${siblings.indexOf(node) + 1})`;
      }
      parts.unshift(part);
      node = parent;
    }
    return parts.join(" > ");
  };
  const labelFor = (el) => {
    if (el.id) {
      const label = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (label && clean(label.textContent)) return clean(label.textContent);
    }
    const wrapping = el.closest("label");
    if (wrapping && clean(wrapping.textContent)) {
      return clean(wrapping.textContent).replace(clean(el.value), "").trim();
    }
    const row = el.closest(".row, tr, .form-group, .control-group, .col-md-6, .col-sm-6");
    if (row) {
      const texts = Array.from(row.querySelectorAll("label, strong, b, span, td, th"))
        .filter((node) => !node.contains(el))
        .map((node) => clean(node.textContent))
        .filter(Boolean);
      if (texts.length) return texts[0].slice(0, 140);
    }
    let node = el;
    for (let depth = 0; node && depth < 4; depth += 1, node = node.parentElement) {
      let prev = node.previousElementSibling;
      for (let i = 0; prev && i < 3; i += 1, prev = prev.previousElementSibling) {
        const text = clean(prev.textContent);
        if (text) return text.slice(0, 140);
      }
    }
    return "";
  };
  const nearbyText = (el) => {
    const root = el.closest(".row, tr, .form-group, .control-group, .col-md-6, .col-sm-6, fieldset, .box-body")
      || el.parentElement;
    return clean(root?.innerText || root?.textContent || "").slice(0, 300);
  };
  const valueOf = (el) => {
    if (el.tagName === "SELECT") {
      return Array.from(el.selectedOptions || []).map((opt) => clean(opt.textContent) || opt.value).join(" | ");
    }
    if (el.type === "checkbox" || el.type === "radio") return el.checked ? "checked" : "";
    return clean(el.value);
  };
  const optionsOf = (el) => {
    if (el.tagName !== "SELECT") return [];
    return Array.from(el.options || []).map((opt) => ({
      value: opt.value,
      text: clean(opt.textContent),
      selected: opt.selected,
    }));
  };
  const fieldElements = Array.from(document.querySelectorAll("input, select, textarea"));
  const fields = fieldElements.map((el, index) => ({
    index,
    tag: el.tagName.toLowerCase(),
    type: el.getAttribute("type") || "",
    id: el.id || "",
    name: el.getAttribute("name") || "",
    className: String(el.className || ""),
    label: labelFor(el),
    placeholder: el.getAttribute("placeholder") || "",
    value: valueOf(el),
    disabled: Boolean(el.disabled),
    readOnly: Boolean(el.readOnly),
    visible: visible(el),
    rect: rectOf(el),
    selector: cssPath(el),
    nearbyText: nearbyText(el),
    options: optionsOf(el),
  }));

  const buttons = Array.from(document.querySelectorAll("button, input[type='button'], input[type='submit'], a"))
    .map((el, index) => ({
      index,
      tag: el.tagName.toLowerCase(),
      id: el.id || "",
      name: el.getAttribute("name") || "",
      className: String(el.className || ""),
      text: clean(el.textContent || el.value || el.title || el.getAttribute("aria-label")),
      href: el.getAttribute("href") || "",
      visible: visible(el),
      rect: rectOf(el),
      selector: cssPath(el),
    }))
    .filter((item) => item.visible && (item.text || item.id || item.name || item.href));

  const blueBars = Array.from(document.querySelectorAll("div, section, article, li, tr"))
    .map((el, index) => {
      const text = clean(el.innerText || el.textContent);
      const upper = text.toUpperCase();
      const looksLikeBar = upper.includes("EMPENHO") && (upper.includes("SUBELEMENTO") || upper.includes("LIQUIDADO") || upper.includes("R$"));
      if (!looksLikeBar || !visible(el)) return null;
      const matchEmpenho = upper.match(/(\d{4}NE\d{6})/);
      const matchSub = text.match(/Subelemento:\s*(\d+)/i);
      const matchLiquidado = text.match(/Liquidado:\s*([A-Za-zÇÃ]+)/i);
      const matchValor = text.match(/R\$\s*:?\s*([\d.]+,\d{2})/i);
      const container = el.closest(".count-poo-item, [data-count-poo-item], .box.box-solid, .box, .panel, .card") || el;
      const inputs = Array.from(container.querySelectorAll("input,select,textarea"));
      const visibleInputs = inputs.filter(visible);
      return {
        index,
        text: text.slice(0, 500),
        empenho: matchEmpenho ? matchEmpenho[1] : "",
        subelemento: matchSub ? matchSub[1] : "",
        liquidado: matchLiquidado ? matchLiquidado[1] : "",
        valor: matchValor ? matchValor[1] : "",
        visible: true,
        expanded: visibleInputs.length > 0,
        rect: rectOf(el),
        selector: cssPath(el),
        containerSelector: cssPath(container),
        inputIds: inputs.map((input) => input.id || input.getAttribute("name") || "").filter(Boolean),
      };
    })
    .filter(Boolean);

  const byPrefix = {};
  for (const prefix of ["numempe", "numclassa", "numclassb", "numclassc"]) {
    byPrefix[prefix] = fields
      .filter((field) => field.id.startsWith(prefix) || field.name.startsWith(prefix))
      .map((field) => ({
        id: field.id,
        name: field.name,
        label: field.label,
        value: field.value,
        visible: field.visible,
        selector: field.selector,
        nearbyText: field.nearbyText,
      }));
  }

  const importantLabels = [
    "Situação",
    "Tem Contrato?",
    "Conta de Contrato",
    "Favorecido do Contrato",
    "Código de Recolhimento de GRU",
    "Conta de Bens",
    "Conta de Estoque",
    "Contas a Pagar",
    "Variação Patrimonial",
    "Observação",
  ];
  const labelMatches = importantLabels.map((label) => ({
    label,
    fields: fields.filter((field) =>
      field.label.toUpperCase().includes(label.toUpperCase())
      || field.nearbyText.toUpperCase().includes(label.toUpperCase())
    ),
  }));

  const pcoStructure = Array.from(document.querySelectorAll("select[id^='codsit']")).map((select) => {
    const situacaoId = select.id || "";
    const situacaoSufixo = situacaoId.replace(/^codsit/, "");
    const situacaoTexto = clean(select.options?.[select.selectedIndex]?.textContent || select.value || "");
    const root =
      document.getElementById(`${situacaoTexto}_${situacaoSufixo}`)
      || select.closest(".tab-pane, form, #pco")
      || document;
    const situacaoFields = Array.from(root.querySelectorAll("input, select, textarea"))
      .filter((el) => {
        const id = String(el.id || "");
        return id.endsWith(situacaoSufixo)
          && /^(codsit|codugempe|repetircontaempenho|indrtemcontrato|despesaantecipada|numclassd|txtinscrd|txtinscre)/.test(id);
      })
      .map((el) => ({
        id: el.id || "",
        name: el.getAttribute("name") || "",
        label: labelFor(el),
        value: valueOf(el),
        visible: visible(el),
        dataMascara: el.getAttribute("data-mascara") || "",
        dataRotulo: el.getAttribute("data-rotulo") || "",
      }));
    const itens = Array.from(root.querySelectorAll(".count-pco-item, [data-count-pco-item]")).map((item) => {
      const itemId = item.id || "";
      const collapse = itemId ? document.getElementById(`collapse${itemId}`) : null;
      const itemSuffix = `${itemId}${situacaoSufixo}`;
      const itemFields = Array.from(root.querySelectorAll("input, select, textarea"))
        .filter((el) => String(el.id || "").endsWith(itemSuffix))
        .map((el) => ({
          id: el.id || "",
          name: el.getAttribute("name") || "",
          label: labelFor(el),
          value: valueOf(el),
          visible: visible(el),
          dataMascara: el.getAttribute("data-mascara") || "",
          dataRotulo: el.getAttribute("data-rotulo") || "",
        }));
      return {
        itemId,
        text: clean(item.innerText || item.textContent).slice(0, 500),
        visible: visible(item),
        expanded: visible(collapse),
        collapseId: collapse?.id || "",
        fields: itemFields,
      };
    });
    return {
      situacaoId,
      situacaoSufixo,
      situacaoTexto,
      situacaoFields,
      itens,
    };
  });

  return {
    capturedAt: new Date().toISOString(),
    url: location.href,
    title: document.title,
    viewport: { width: innerWidth, height: innerHeight },
    activeElement: document.activeElement ? cssPath(document.activeElement) : "",
    bodyTextSample: clean(document.body.innerText).slice(0, 3000),
    counts: {
      fields: fields.length,
      visibleFields: fields.filter((field) => field.visible).length,
      buttons: buttons.length,
      blueBars: blueBars.length,
    },
    fields,
    buttons,
    blueBars,
    byPrefix,
    labelMatches,
    pcoStructure,
  };
}
"""


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def capture_pco_snapshot(page: Any, out_dir: str | Path = DEFAULT_OUT_DIR, prefix: str = "") -> dict[str, Any]:
    """Captura JSON focado, HTML e screenshot da pagina atual do PCO."""

    output_dir = Path(out_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_prefix = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in str(prefix or "").strip("- "))
    file_prefix = f"{safe_prefix}-" if safe_prefix else ""
    base = output_dir / f"{file_prefix}pco-dom-{timestamp}"

    snapshot = page.evaluate(JS_SNAPSHOT)
    html = page.content()
    screenshot_path = base.with_suffix(".png")
    try:
        page.screenshot(path=str(screenshot_path), full_page=True)
        snapshot["screenshotPath"] = str(screenshot_path)
    except Exception as exc:
        snapshot["screenshotError"] = str(exc)

    json_path = base.with_suffix(".json")
    html_path = base.with_suffix(".html")
    _write_json(json_path, snapshot)
    html_path.write_text(html, encoding="utf-8")

    snapshot["jsonPath"] = str(json_path)
    snapshot["htmlPath"] = str(html_path)
    snapshot["outputDir"] = str(output_dir)
    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspeciona a aba Principal com Orçamento aberta no Chrome.")
    parser.add_argument("--out", default=str(DEFAULT_OUT_DIR), help="Diretório de saída dos artefatos.")
    parser.add_argument("--prefix", default="", help="Prefixo opcional para o nome dos arquivos.")
    args = parser.parse_args()

    out_dir = Path(args.out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    playwright = None
    try:
        playwright, page = conectar(abrir_se_fechado=False)
        snapshot = capture_pco_snapshot(page, out_dir, args.prefix)

        print(f"JSON: {snapshot['jsonPath']}")
        print(f"HTML: {snapshot['htmlPath']}")
        if snapshot.get("screenshotPath"):
            print(f"Screenshot: {snapshot['screenshotPath']}")
        print(
            "Resumo: "
            f"{snapshot['counts']['visibleFields']} campos visíveis, "
            f"{snapshot['counts']['blueBars']} barras de empenho, "
            f"{snapshot['counts']['buttons']} botões/links visíveis."
        )
        return 0
    finally:
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
