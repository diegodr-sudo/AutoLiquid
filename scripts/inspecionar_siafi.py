#!/usr/bin/env python3
"""Captura um mapa detalhado da aba SIAFI aberta no Chrome.

Uso:
  python3 scripts/inspecionar_siafi.py --prefix dados-basicos

Deixe o Chrome da automação aberto na tela SIAFI que precisa ser mapeada.
O script não preenche nem confirma nada; ele só lê o DOM e salva
JSON/HTML/screenshot em falhas-automacao/siafi-dom.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from services.chrome_service import chrome_esta_pronto, obter_porta_chrome


DEFAULT_OUT_DIR = Path.home() / "Documents" / "AutoLiquid" / "falhas-automacao" / "siafi-dom"
SIAFI_DOMINIOS = ("siafi.tesouro.gov.br", "siafi", "serpro.gov.br")


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
    if (!el || !el.getBoundingClientRect) return { x: 0, y: 0, width: 0, height: 0 };
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
    while (node && node.nodeType === 1 && node !== document.body && parts.length < 8) {
      let part = node.tagName.toLowerCase();
      const name = node.getAttribute("name");
      if (name) part += `[name="${CSS.escape(name)}"]`;
      const cls = String(node.className || "").trim().split(/\s+/).filter(Boolean).slice(0, 3);
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
    const aria = el.getAttribute("aria-label") || el.getAttribute("title") || "";
    if (clean(aria)) return clean(aria);
    const labelledBy = el.getAttribute("aria-labelledby");
    if (labelledBy) {
      const label = labelledBy.split(/\s+/).map((id) => document.getElementById(id)?.textContent || "").join(" ");
      if (clean(label)) return clean(label);
    }
    const wrapping = el.closest("label");
    if (wrapping && clean(wrapping.textContent)) return clean(wrapping.textContent).slice(0, 180);
    const root = el.closest(".row, tr, .form-group, .control-group, .field, .ui-field, li, p, div");
    if (root) {
      const texts = Array.from(root.querySelectorAll("label, strong, b, span, td, th"))
        .filter((node) => !node.contains(el))
        .map((node) => clean(node.textContent))
        .filter(Boolean);
      if (texts.length) return texts[0].slice(0, 180);
    }
    let node = el;
    for (let depth = 0; node && depth < 4; depth += 1, node = node.parentElement) {
      let prev = node.previousElementSibling;
      for (let i = 0; prev && i < 3; i += 1, prev = prev.previousElementSibling) {
        const text = clean(prev.textContent);
        if (text) return text.slice(0, 180);
      }
    }
    return "";
  };
  const nearbyText = (el) => {
    const root = el.closest(".row, tr, .form-group, .control-group, fieldset, form, section, article, div")
      || el.parentElement;
    return clean(root?.innerText || root?.textContent || "").slice(0, 500);
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
    })).slice(0, 200);
  };
  const attrsOf = (el) => {
    const attrs = {};
    for (const attr of Array.from(el.attributes || [])) {
      if (attr.name === "style") continue;
      attrs[attr.name] = String(attr.value || "").slice(0, 300);
    }
    return attrs;
  };
  const fields = Array.from(document.querySelectorAll("input, select, textarea"))
    .map((el, index) => ({
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
      attributes: attrsOf(el),
    }));
  const buttons = Array.from(document.querySelectorAll("button, input[type='button'], input[type='submit'], a, [role='button']"))
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
      attributes: attrsOf(el),
    }))
    .filter((item) => item.visible && (item.text || item.id || item.name || item.href));
  const forms = Array.from(document.querySelectorAll("form")).map((form, index) => ({
    index,
    id: form.id || "",
    name: form.getAttribute("name") || "",
    action: form.getAttribute("action") || "",
    method: form.getAttribute("method") || "",
    visible: visible(form),
    selector: cssPath(form),
    fieldIds: Array.from(form.querySelectorAll("input, select, textarea")).map((el) => el.id || el.getAttribute("name") || "").filter(Boolean),
  }));
  const tables = Array.from(document.querySelectorAll("table")).map((table, index) => {
    const headers = Array.from(table.querySelectorAll("th")).map((th) => clean(th.textContent)).filter(Boolean);
    const rows = Array.from(table.querySelectorAll("tr")).slice(0, 12).map((tr) =>
      Array.from(tr.querySelectorAll("th,td")).map((cell) => clean(cell.textContent)).filter(Boolean)
    ).filter((row) => row.length);
    return {
      index,
      id: table.id || "",
      className: String(table.className || ""),
      visible: visible(table),
      rect: rectOf(table),
      selector: cssPath(table),
      headers,
      sampleRows: rows,
    };
  });
  const iframes = Array.from(document.querySelectorAll("iframe, frame")).map((frame, index) => ({
    index,
    id: frame.id || "",
    name: frame.getAttribute("name") || "",
    src: frame.getAttribute("src") || "",
    title: frame.getAttribute("title") || "",
    visible: visible(frame),
    rect: rectOf(frame),
    selector: cssPath(frame),
  }));
  const ids = Array.from(document.querySelectorAll("[id]")).map((el) => ({
    id: el.id,
    tag: el.tagName.toLowerCase(),
    className: String(el.className || ""),
    text: clean(el.textContent).slice(0, 160),
    visible: visible(el),
    selector: cssPath(el),
  }));
  const active = document.activeElement;
  return {
    capturedAt: new Date().toISOString(),
    url: window.location.href,
    title: document.title,
    viewport: { width: window.innerWidth, height: window.innerHeight },
    activeElement: active ? {
      tag: active.tagName?.toLowerCase() || "",
      id: active.id || "",
      name: active.getAttribute?.("name") || "",
      className: String(active.className || ""),
      value: active.value || "",
      text: clean(active.textContent),
      selector: cssPath(active),
    } : null,
    bodyTextSample: clean(document.body?.innerText || document.body?.textContent || "").slice(0, 3000),
    counts: {
      fields: fields.length,
      visibleFields: fields.filter((item) => item.visible).length,
      buttons: buttons.length,
      forms: forms.length,
      tables: tables.length,
      iframes: iframes.length,
      ids: ids.length,
    },
    fields,
    buttons,
    forms,
    tables,
    iframes,
    ids,
  };
}
"""


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_prefix(prefix: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in str(prefix or "").strip("- "))


def _screenshot_path_for(base: Path) -> Path:
    return base.with_suffix(".png")


def _encontrar_pagina_siafi(navegador_cdp: Any) -> Any:
    paginas = [pagina for contexto in navegador_cdp.contexts for pagina in contexto.pages]
    for pagina in paginas:
        url = str(pagina.url or "").lower()
        if any(dominio in url for dominio in SIAFI_DOMINIOS):
            return pagina
    if paginas:
        return paginas[0]
    raise RuntimeError("Nenhuma aba encontrada no Chrome da automação.")


def conectar_siafi_page() -> tuple[Any, Any]:
    import asyncio
    from playwright.sync_api import sync_playwright

    try:
        asyncio.set_event_loop(None)
    except Exception:
        pass

    porta = obter_porta_chrome()
    if not chrome_esta_pronto(porta):
        raise RuntimeError("Chrome da automação não está pronto. Abra o SIAFI antes de capturar.")

    playwright = sync_playwright().start()
    try:
        navegador_cdp = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{porta}")
        pagina = _encontrar_pagina_siafi(navegador_cdp)
        return playwright, pagina
    except Exception:
        playwright.stop()
        raise


def capture_siafi_snapshot(page: Any, out_dir: str | Path = DEFAULT_OUT_DIR, prefix: str = "") -> dict[str, Any]:
    output_dir = Path(out_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_prefix = _safe_prefix(prefix)
    file_prefix = f"{safe_prefix}-" if safe_prefix else ""
    base = output_dir / f"{file_prefix}siafi-dom-{timestamp}"

    snapshot = page.evaluate(JS_SNAPSHOT)
    frame_snapshots: list[dict[str, Any]] = []
    for frame in page.frames:
        if frame == page.main_frame:
            continue
        try:
            frame_snapshots.append({
                "url": frame.url,
                "name": frame.name,
                "snapshot": frame.evaluate(JS_SNAPSHOT),
            })
        except Exception as exc:
            frame_snapshots.append({"url": frame.url, "name": frame.name, "error": str(exc)})
    snapshot["frames"] = frame_snapshots

    screenshot_path = _screenshot_path_for(base)
    try:
        page.screenshot(path=str(screenshot_path), full_page=True)
        snapshot["screenshotPath"] = str(screenshot_path)
    except Exception as exc:
        snapshot["screenshotError"] = str(exc)

    html_path = base.with_suffix(".html")
    json_path = base.with_suffix(".json")
    try:
        html_path.write_text(page.content(), encoding="utf-8")
    except Exception as exc:
        snapshot["htmlError"] = str(exc)
    _write_json(json_path, snapshot)

    snapshot["jsonPath"] = str(json_path)
    snapshot["htmlPath"] = str(html_path)
    snapshot["outputDir"] = str(output_dir)
    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspeciona a aba SIAFI aberta no Chrome.")
    parser.add_argument("--out", default=str(DEFAULT_OUT_DIR), help="Diretório de saída dos artefatos.")
    parser.add_argument("--prefix", default="", help="Prefixo opcional para o nome dos arquivos.")
    args = parser.parse_args()

    playwright = None
    try:
        playwright, page = conectar_siafi_page()
        snapshot = capture_siafi_snapshot(page, args.out, args.prefix)
        print(f"JSON: {snapshot['jsonPath']}")
        print(f"HTML: {snapshot.get('htmlPath', '')}")
        if snapshot.get("screenshotPath"):
            print(f"Screenshot: {snapshot['screenshotPath']}")
        counts = snapshot.get("counts") or {}
        print(
            "Resumo: "
            f"{counts.get('visibleFields', 0)} campos visíveis, "
            f"{counts.get('buttons', 0)} botões/links, "
            f"{counts.get('iframes', 0)} iframe(s)."
        )
        return 0
    finally:
        if playwright is not None:
            playwright.stop()


if __name__ == "__main__":
    raise SystemExit(main())
