from __future__ import annotations

from .models import FieldSpec
from .playwright_protocols import LocatorLike, PageLike


_JS_FIND_BY_LABEL = """
({ label }) => {
  const visible = (el) => {
    if (!el) return false;
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return rect.width > 0 && rect.height > 0
      && style.visibility !== "hidden"
      && style.display !== "none";
  };
  const inputs = "input, select, textarea, [contenteditable='true']";
  const candidates = Array.from(document.querySelectorAll("*"))
    .filter((el) => visible(el) && (el.textContent || "").trim() === label);
  for (const el of candidates) {
    const scopes = [
      el.nextElementSibling,
      el.parentElement,
      el.parentElement?.nextElementSibling,
      el.parentElement?.parentElement,
    ].filter(Boolean);
    for (const scope of scopes) {
      const found = Array.from(scope.querySelectorAll(inputs)).find(visible);
      if (found) return { id: found.id || "", name: found.getAttribute("name") || "" };
    }
  }
  return null;
}
"""


def resolve_locator(page: PageLike, spec: FieldSpec) -> LocatorLike:
    """Resolve a field locator using explicit selectors first, then label lookup."""

    if spec.resolver is not None:
        return spec.resolver(page, spec)

    errors: list[str] = []
    for selector in spec.selectors:
        try:
            locator = page.locator(selector)
            if locator.count() > 0:
                return locator.first
        except Exception as exc:
            errors.append(f"{selector}: {exc}")

    if spec.label:
        match = page.evaluate(_JS_FIND_BY_LABEL, {"label": spec.label})
        if isinstance(match, dict):
            element_id = str(match.get("id") or "")
            element_name = str(match.get("name") or "")
            if element_id:
                return page.locator(f"#{element_id}").first
            if element_name:
                return page.locator(f"[name='{element_name}']").first

    detail = f" Tried: {', '.join(errors)}" if errors else ""
    raise RuntimeError(f"Field locator not found: {spec.name}.{detail}")
