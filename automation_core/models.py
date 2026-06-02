from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable, Sequence


class FieldType(StrEnum):
    TEXT = "text"
    TEXTAREA = "textarea"
    MASKED = "masked"
    SELECT = "select"
    PRIMEFACES_SELECT = "primefaces_select"
    AUTOCOMPLETE = "autocomplete"
    DATE = "date"
    JS_VALUE = "js_value"


Validator = Callable[[Any, str], bool]
ValueReader = Callable[[Any], str]
LocatorResolver = Callable[[Any, "FieldSpec"], Any]


@dataclass(frozen=True)
class FieldSpec:
    """Declarative description of a single field in a browser page."""

    name: str
    value: str
    selectors: Sequence[str] = field(default_factory=tuple)
    label: str = ""
    field_type: FieldType = FieldType.TEXT
    required: bool = True
    retries: int = 3
    settle_ms: int = 350
    timeout_ms: int = 8000
    trigger_blur: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
    validator: Validator | None = None
    value_reader: ValueReader | None = None
    resolver: LocatorResolver | None = None


@dataclass(frozen=True)
class StepSpec:
    name: str
    fields: Sequence[FieldSpec] = field(default_factory=tuple)
    preconditions: Sequence[Callable[[Any], None]] = field(default_factory=tuple)
    postconditions: Sequence[Callable[[Any], None]] = field(default_factory=tuple)
    timeout_ms: int = 30000


@dataclass(frozen=True)
class FillAttempt:
    field_name: str
    attempt: int
    expected: str
    observed: str
    ok: bool
    message: str = ""


@dataclass(frozen=True)
class FillResult:
    field_name: str
    ok: bool
    attempts: tuple[FillAttempt, ...] = ()
    final_value: str = ""
    message: str = ""


@dataclass(frozen=True)
class StepResult:
    step_name: str
    ok: bool
    fields: tuple[FillResult, ...] = ()
    message: str = ""


@dataclass(frozen=True)
class AutomationResult:
    ok: bool
    steps: tuple[StepResult, ...] = ()
    message: str = ""
