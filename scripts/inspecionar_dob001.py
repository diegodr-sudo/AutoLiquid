#!/usr/bin/env python3
"""Captura um mapa detalhado da aba Dedução/DOB001 aberta no Chrome."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from comprasnet.base import conectar


DEFAULT_OUT_DIR = Path.home() / "Documents" / "AutoLiquid" / "falhas-automacao" / "dob001-dom"


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
    const row = el.closest(".row, tr, .form-group, .control-group, .col-md-6, .col-sm-6, .col-lg-6, .modal-body");
    if (row) {
      const texts = Array.from(row.querySelectorAll("label, strong, b, span, td, th"))
        .filter((node) => !node.contains(el))
        .map((node) => clean(node.textContent))
        .filter(Boolean);
      if (texts.length) return texts[0].slice(0, 160);
    }
    return "";
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
  const prefixes = [
    "sfdeducaocodsit", "sfdeducaodtvenc", "sfdeducaodtpgtoreceb", "sfdeducaovlr",
    "sfdeducaocodugpgto", "sfdeducaopossui_acrescimo", "sfdeducaoconfirma_dados",
    "municipioDeducao", "municipioDeducaoPreDoc", "txtinscra", "txtinscrb",
    "codcredordevedorpredoc", "txtprocesso", "taxacambio", "codnumlista",
    "bancoFavorecido", "agenciaFavorecido", "contaFavorecido", "bancoPagador",
    "codtipoob", "obser", "confirma-dados-deducao-",
  ];
  const isDob001Field = (el) => {
    const id = String(el.id || "");
    const name = String(el.getAttribute("name") || "");
    return prefixes.some((prefix) => id.startsWith(prefix) || name.startsWith(prefix));
  };
  const nearbyText = (el) => {
    const root = el.closest(".row, tr, .form-group, .control-group, .col-md-6, .col-sm-6, .modal-body, .tab-pane")
      || el.parentElement;
    return clean(root?.innerText || root?.textContent || "").slice(0, 360);
  };
  const fields = Array.from(document.querySelectorAll("input, select, textarea"))
    .filter((el) => isDob001Field(el) || nearbyText(el).toLowerCase().includes("dob001"))
    .map((el, index) => ({
      index,
      tag: el.tagName.toLowerCase(),
      type: el.getAttribute("type") || "",
      id: el.id || "",
      name: el.getAttribute("name") || "",
      label: labelFor(el),
      value: valueOf(el),
      visible: visible(el),
      disabled: !!el.disabled,
      readonly: !!el.readOnly,
      rect: visible(el) ? rectOf(el) : null,
      cssPath: cssPath(el),
      nearbyText: nearbyText(el),
      options: optionsOf(el),
    }));
  const buttons = Array.from(document.querySelectorAll("button, a, input[type='button'], input[type='submit']"))
    .filter((el) => {
      const text = clean(el.textContent || el.value || el.getAttribute("title") || "");
      const id = String(el.id || "");
      return visible(el) && (
        id.startsWith("confirma-dados-deducao-")
        || id.includes("nova-aba-situacao-deducao")
        || /confirmar|dedu[cç][aã]o|pr[eé]-?doc|\+/.test(text.toLowerCase())
      );
    })
    .map((el, index) => ({
      index,
      tag: el.tagName.toLowerCase(),
      id: el.id || "",
      text: clean(el.textContent || el.value || el.getAttribute("title") || ""),
      onclick: String(el.getAttribute("onclick") || "").slice(0, 300),
      disabled: !!el.disabled,
      rect: rectOf(el),
      cssPath: cssPath(el),
      nearbyText: nearbyText(el),
    }));
  const deducaoIds = Array.from(new Set(fields.map((field) => {
    const match = String(field.id || field.name || "").match(/(\d+)$/);
    return match ? match[1] : "";
  }).filter(Boolean))).sort((a, b) => Number(a) - Number(b));
  const byDeducaoId = {};
  for (const did of deducaoIds) {
    byDeducaoId[did] = fields.filter((field) => String(field.id || field.name || "").endsWith(did));
  }
  const activePanel = Array.from(document.querySelectorAll(".tab-pane.active, .tab-pane.show, [role='tabpanel']"))
    .map((el) => ({ id: el.id || "", text: clean(el.innerText || el.textContent).slice(0, 800), visible: visible(el) }))
    .filter((item) => item.visible);
  return {
    capturedAt: new Date().toISOString(),
    url: location.href,
    title: document.title,
    counts: {
      fields: fields.length,
      visibleFields: fields.filter((field) => field.visible).length,
      buttons: buttons.length,
      deducoes: deducaoIds.length,
    },
    fields,
    buttons,
    deducaoIds,
    byDeducaoId,
    activePanel,
  };
}
"""


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def capture_dob001_snapshot(page: Any, out_dir: str | Path = DEFAULT_OUT_DIR, prefix: str = "") -> dict[str, Any]:
    """Captura JSON focado, HTML e screenshot da pagina atual de Dedução/DOB001."""

    output_dir = Path(out_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_prefix = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in str(prefix or "").strip("- "))
    file_prefix = f"{safe_prefix}-" if safe_prefix else ""
    base = output_dir / f"{file_prefix}dob001-dom-{timestamp}"

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
    parser = argparse.ArgumentParser(description="Inspeciona a aba Dedução/DOB001 aberta no Chrome.")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--prefix", default="")
    args = parser.parse_args()

    playwright, page = conectar(abrir_se_fechado=False)
    try:
        snapshot = capture_dob001_snapshot(page, args.out_dir, args.prefix)
        print(f"JSON: {snapshot['jsonPath']}")
        print(f"HTML: {snapshot['htmlPath']}")
        if snapshot.get("screenshotPath"):
            print(f"Screenshot: {snapshot['screenshotPath']}")
        print(
            f"{snapshot['counts']['visibleFields']} campos visíveis, "
            f"{snapshot['counts']['deducoes']} dedução(ões), "
            f"{snapshot['counts']['buttons']} botões/links visíveis."
        )
        return 0
    finally:
        playwright.stop()


if __name__ == "__main__":
    raise SystemExit(main())
