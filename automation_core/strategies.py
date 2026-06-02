from __future__ import annotations

import re
from typing import Any

from .locators import resolve_locator
from .models import FieldSpec, FieldType, FillAttempt, FillResult
from .playwright_protocols import LocatorLike, PageLike


_JS_SET_NATIVE_VALUE = """
(el, { value }) => {
  const proto = el instanceof HTMLTextAreaElement
    ? HTMLTextAreaElement.prototype
    : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
  const fire = () => {
    el.dispatchEvent(new InputEvent("input", { bubbles: true, cancelable: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    el.dispatchEvent(new Event("blur", { bubbles: true }));
  };
  const setNative = (nextValue) => {
    el.focus();
    if (setter) setter.call(el, nextValue);
    else el.value = nextValue;
    el.defaultValue = nextValue;
    el.setAttribute("value", nextValue);
    fire();
    return el.value || "";
  };
  if (window.$ && $(el).inputmask) {
    try {
      $(el).inputmask("setvalue", value);
      fire();
      if (String(el.value || "").replace(/\\D/g, "") === String(value || "").replace(/\\D/g, "")) {
        return el.value || "";
      }
    } catch (e) {}
  }
  return setNative(value);
}
"""

_JS_IS_INTERACTIVE = """
(el) => {
  const rect = el.getBoundingClientRect();
  const style = window.getComputedStyle(el);
  return rect.width > 0 && rect.height > 0
    && style.visibility !== "hidden"
    && style.display !== "none"
    && !el.disabled
    && !el.readOnly;
}
"""


def _read_value(locator: LocatorLike) -> str:
    try:
        return locator.input_value()
    except Exception:
        try:
            return locator.inner_text()
        except Exception:
            return ""


def _default_validate(observed: str, expected: str, field_type: FieldType) -> bool:
    if field_type in {FieldType.MASKED, FieldType.DATE}:
        expected_digits = re.sub(r"\D+", "", expected)
        observed_digits = re.sub(r"\D+", "", observed)
        return bool(expected_digits) and expected_digits in observed_digits
    return observed.strip() == expected.strip()


def _wait_interactive(locator: LocatorLike, timeout_ms: int) -> None:
    locator.wait_for(state="visible", timeout=timeout_ms)
    try:
        locator.evaluate(_JS_IS_INTERACTIVE)
    except Exception:
        pass


def _blur(page: PageLike) -> None:
    try:
        page.keyboard.press("Tab")
    except Exception:
        pass


def _fill_text(locator: LocatorLike, page: PageLike, value: str, spec: FieldSpec) -> None:
    locator.click(click_count=3)
    locator.fill(value)
    if spec.trigger_blur:
        _blur(page)


def _fill_masked(locator: LocatorLike, page: PageLike, value: str, spec: FieldSpec) -> None:
    digits = re.sub(r"\D+", "", value)
    text = digits or value
    locator.click()
    try:
        locator.evaluate("""
          (el) => {
            const value = el.value || "";
            const pos = Math.max(0, value.indexOf("_"));
            if (typeof el.setSelectionRange === "function") el.setSelectionRange(pos, pos);
          }
        """)
    except Exception:
        pass
    locator.press_sequentially(text, delay=spec.metadata.get("delay_ms", 70))
    if spec.trigger_blur:
        _blur(page)


def _fill_select(locator: LocatorLike, page: PageLike, value: str, spec: FieldSpec) -> None:
    option_text = str(spec.metadata.get("option_text_contains") or "").strip()
    if option_text:
        selected = locator.evaluate(
            """
            (el, { text }) => {
              const option = Array.from(el.options || []).find((item) =>
                String(item.textContent || "").toUpperCase().includes(String(text || "").toUpperCase())
              );
              if (!option) return "";
              el.value = option.value;
              el.dispatchEvent(new Event("input", { bubbles: true }));
              el.dispatchEvent(new Event("change", { bubbles: true }));
              return option.value;
            }
            """,
            {"text": option_text},
        )
        if not selected:
            raise RuntimeError(f"Option containing '{option_text}' not found.")
    else:
        locator.select_option(value)
    if spec.trigger_blur:
        _blur(page)


def _fill_js(locator: LocatorLike, page: PageLike, value: str, spec: FieldSpec) -> None:
    locator.evaluate(_JS_SET_NATIVE_VALUE, {"value": value})
    if spec.trigger_blur:
        _blur(page)


def _apply_strategy(locator: LocatorLike, page: PageLike, spec: FieldSpec) -> None:
    if spec.field_type in {FieldType.TEXT, FieldType.TEXTAREA, FieldType.DATE}:
        _fill_text(locator, page, spec.value, spec)
    elif spec.field_type == FieldType.MASKED:
        _fill_masked(locator, page, spec.value, spec)
    elif spec.field_type in {FieldType.SELECT, FieldType.PRIMEFACES_SELECT}:
        _fill_select(locator, page, spec.value, spec)
    elif spec.field_type in {FieldType.JS_VALUE, FieldType.AUTOCOMPLETE}:
        _fill_js(locator, page, spec.value, spec)
    else:
        _fill_text(locator, page, spec.value, spec)


def _is_valid(locator: LocatorLike, spec: FieldSpec, observed: str) -> bool:
    if spec.validator:
        return bool(spec.validator(locator, spec.value))
    return _default_validate(observed, spec.value, spec.field_type)


def fill_field(page: PageLike, spec: FieldSpec) -> FillResult:
    """Fill a field, verify it, and retry when the site clears/reformats it."""

    attempts: list[FillAttempt] = []
    final_value = ""
    try:
        locator = resolve_locator(page, spec)
    except Exception as exc:
        return FillResult(spec.name, False, message=str(exc))

    for attempt_no in range(1, max(1, spec.retries) + 1):
        try:
            _wait_interactive(locator, spec.timeout_ms)
            _apply_strategy(locator, page, spec)
            if spec.settle_ms > 0:
                page.wait_for_timeout(spec.settle_ms)
            final_value = spec.value_reader(locator) if spec.value_reader else _read_value(locator)
            ok = _is_valid(locator, spec, final_value)
            attempts.append(
                FillAttempt(
                    field_name=spec.name,
                    attempt=attempt_no,
                    expected=spec.value,
                    observed=final_value,
                    ok=ok,
                    message="" if ok else "value did not stick",
                )
            )
            if ok:
                return FillResult(spec.name, True, tuple(attempts), final_value)
        except Exception as exc:
            attempts.append(
                FillAttempt(
                    field_name=spec.name,
                    attempt=attempt_no,
                    expected=spec.value,
                    observed=final_value,
                    ok=False,
                    message=str(exc),
                )
            )

    return FillResult(
        spec.name,
        False,
        tuple(attempts),
        final_value,
        f"Could not stabilize field '{spec.name}' after {len(attempts)} attempt(s).",
    )
