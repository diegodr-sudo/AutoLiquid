from __future__ import annotations

from typing import Any

from .playwright_protocols import PageLike


_JS_PAGE_MANIFEST = """
() => {
  const visible = (el) => {
    if (!el) return false;
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return rect.width > 0 && rect.height > 0
      && style.visibility !== "hidden"
      && style.display !== "none";
  };
  const labelFor = (el) => {
    if (el.id) {
      const label = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (label) return (label.textContent || "").trim();
    }
    const parentLabel = el.closest("label");
    if (parentLabel) return (parentLabel.textContent || "").trim();
    return "";
  };
  return {
    title: document.title,
    url: location.href,
    fields: Array.from(document.querySelectorAll("input, select, textarea"))
      .filter(visible)
      .map((el) => ({
        tag: el.tagName.toLowerCase(),
        id: el.id || "",
        name: el.getAttribute("name") || "",
        type: el.getAttribute("type") || "",
        label: labelFor(el),
        value: el.value || "",
        placeholder: el.getAttribute("placeholder") || "",
        autocomplete: el.getAttribute("autocomplete") || "",
      })),
    buttons: Array.from(document.querySelectorAll("button, input[type='button'], input[type='submit']"))
      .filter(visible)
      .map((el) => ({
        tag: el.tagName.toLowerCase(),
        id: el.id || "",
        name: el.getAttribute("name") || "",
        text: (el.innerText || el.value || "").trim(),
      })),
  };
}
"""


def capture_page_manifest(page: PageLike) -> dict[str, Any]:
    """Capture a lightweight manifest of the current page DOM."""

    manifest = page.evaluate(_JS_PAGE_MANIFEST)
    return manifest if isinstance(manifest, dict) else {}
