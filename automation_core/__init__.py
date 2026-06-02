"""Automation Core: primitives for resilient browser automation.

This package is intentionally parallel to the current Comprasnet/Solar code.
Nothing here is imported by the production flow until a caller opts in.
"""

from .diagnostics import FailureArtifact, capture_failure_context
from .models import (
    AutomationResult,
    FieldSpec,
    FieldType,
    FillAttempt,
    FillResult,
    StepResult,
    StepSpec,
)
from .runner import run_step
from .strategies import fill_field

__all__ = [
    "AutomationResult",
    "FailureArtifact",
    "FieldSpec",
    "FieldType",
    "FillAttempt",
    "FillResult",
    "StepResult",
    "StepSpec",
    "capture_failure_context",
    "fill_field",
    "run_step",
]
