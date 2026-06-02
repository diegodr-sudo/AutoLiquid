from __future__ import annotations

from .diagnostics import capture_failure_context
from .models import FieldSpec, StepResult, StepSpec
from .playwright_protocols import PageLike
from .strategies import fill_field


def run_fields(page: PageLike, fields: list[FieldSpec] | tuple[FieldSpec, ...]):
    results = []
    for field in fields:
        result = fill_field(page, field)
        results.append(result)
        if field.required and not result.ok:
            break
    return tuple(results)


def run_step(page: PageLike, step: StepSpec, *, artifact_dir: str | None = None) -> StepResult:
    try:
        for precondition in step.preconditions:
            precondition(page)

        field_results = run_fields(page, tuple(step.fields))
        fields_ok = all((not spec.required) or result.ok for spec, result in zip(step.fields, field_results))
        if not fields_ok:
            if artifact_dir:
                capture_failure_context(page, artifact_dir, step.name)
            return StepResult(step.name, False, field_results, "One or more required fields failed.")

        for postcondition in step.postconditions:
            postcondition(page)

        return StepResult(step.name, True, field_results)
    except Exception as exc:
        if artifact_dir:
            capture_failure_context(page, artifact_dir, step.name)
        return StepResult(step.name, False, message=str(exc))
