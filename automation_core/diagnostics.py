from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .playwright_protocols import PageLike


_JS_VISIBLE_FIELDS = """
() => {
  const visible = (el) => {
    if (!el) return false;
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return rect.width > 0 && rect.height > 0
      && style.visibility !== "hidden"
      && style.display !== "none";
  };
  return Array.from(document.querySelectorAll("input, select, textarea, button"))
    .filter(visible)
    .map((el) => ({
      tag: el.tagName.toLowerCase(),
      id: el.id || "",
      name: el.getAttribute("name") || "",
      type: el.getAttribute("type") || "",
      text: (el.innerText || el.value || el.getAttribute("aria-label") || "").slice(0, 160),
      disabled: !!el.disabled,
      readonly: !!el.readOnly,
    }));
}
"""

_JS_PCO_FIELDS = """
() => {
  const visible = (el) => {
    if (!el) return false;
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return rect.width > 0 && rect.height > 0
      && style.visibility !== "hidden"
      && style.display !== "none";
  };
  const read = (el) => ({
    id: el.id || "",
    name: el.getAttribute("name") || "",
    tag: el.tagName.toLowerCase(),
    value: el.tagName === "SELECT"
      ? (el.options?.[el.selectedIndex]?.textContent || el.value || "")
      : (el.value || ""),
    visible: visible(el),
    dataMascara: el.getAttribute("data-mascara") || "",
    dataRotulo: el.getAttribute("data-rotulo") || "",
  });
  const prefixes = ["codsit", "indrtemcontrato", "numempe", "numclassa", "numclassb", "numclassc", "numclassd", "txtinscrd", "txtinscre"];
  const fields = Array.from(document.querySelectorAll("input, select, textarea"))
    .filter((el) => prefixes.some((prefix) => String(el.id || "").startsWith(prefix)))
    .map(read);
  const bars = Array.from(document.querySelectorAll(".count-pco-item, [data-count-pco-item], .box.box-solid"))
    .filter((el) => String(el.innerText || el.textContent || "").toUpperCase().includes("EMPENHO"))
    .map((el) => {
      const id = el.id || "";
      const collapse = id ? document.getElementById(`collapse${id}`) : null;
      return {
        id,
        text: String(el.innerText || el.textContent || "").replace(/\\s+/g, " ").trim().slice(0, 300),
        visible: visible(el),
        collapseId: collapse?.id || "",
        collapseVisible: visible(collapse),
        className: String(el.className || ""),
      };
    });
  return {
    situacaoSufixo: document.body.getAttribute("data-autoliquid-situacao-sufixo") || "",
    empenhoSufixo: document.body.getAttribute("data-autoliquid-empenho-sufixo") || "",
    empenhoItemId: document.body.getAttribute("data-autoliquid-empenho-item-id") || "",
    fields,
    bars,
  };
}
"""


@dataclass(frozen=True)
class FailureArtifact:
    directory: str
    metadata_path: str
    screenshot_path: str | None = None
    html_path: str | None = None


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value).strip("-") or "step"


def capture_failure_context(page: PageLike, artifact_dir: str, step_name: str) -> FailureArtifact:
    root = Path(artifact_dir)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = root / f"{stamp}-{_safe_name(step_name)}"
    out_dir.mkdir(parents=True, exist_ok=True)

    screenshot_path: str | None = None
    html_path: str | None = None
    try:
        screenshot_path = str(out_dir / "screenshot.png")
        page.screenshot(path=screenshot_path, full_page=True)
    except Exception:
        screenshot_path = None

    try:
        html_path = str(out_dir / "page.html")
        html = page.evaluate("() => document.documentElement.outerHTML")
        Path(html_path).write_text(str(html or ""), encoding="utf-8")
    except Exception:
        html_path = None

    metadata: dict[str, Any] = {
        "step": step_name,
        "capturedAt": datetime.now().isoformat(timespec="seconds"),
        "url": getattr(page, "url", ""),
        "visibleFields": [],
    }
    try:
        metadata["visibleFields"] = page.evaluate(_JS_VISIBLE_FIELDS)
    except Exception as exc:
        metadata["visibleFieldsError"] = str(exc)
    try:
        metadata["pcoFields"] = page.evaluate(_JS_PCO_FIELDS)
    except Exception as exc:
        metadata["pcoFieldsError"] = str(exc)

    metadata_path = str(out_dir / "metadata.json")
    Path(metadata_path).write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return FailureArtifact(
        directory=str(out_dir),
        metadata_path=metadata_path,
        screenshot_path=screenshot_path,
        html_path=html_path,
    )
