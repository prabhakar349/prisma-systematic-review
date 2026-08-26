#!/usr/bin/env python3
"""Validate prisma-state.json against references/state-schema.json.

Every script that mutates the state file should call `validate(state)`
before writing it back out — a malformed record (a typo'd decision like
"incldue", a missing required field) should fail loudly here rather than
silently corrupting counts or crashing deep inside the flow-diagram
renderer.

Uses the `jsonschema` package for full validation if it's installed.
Falls back to a smaller hand-rolled structural check (required keys,
enum values, decision-event shape) if it isn't — the fallback catches
the mistakes most likely to actually happen (typo'd enums, missing
reasons on a non-include decision) even without the dependency, since
this project otherwise has zero external dependencies by design.

A JSON Schema, however, can only check one field in isolation — it
can't express "this report's `stage` must match what its decision
history implies." So this script ALSO always runs a state-transition
check via `derive_stage()`, regardless of which schema backend ran:
a report whose stored `stage` disagrees with its decisions has drifted,
which is exactly the failure mode `stage` is prone to if anything ever
hand-sets or hand-advances it instead of leaving it to
generate_flow_diagram.py --update-state.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generate_flow_diagram import derive_stage  # noqa: E402

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "references", "state-schema.json")

DECISION_ENUM = {"include", "exclude", "maybe"}
STAGE_ENUM = {"identified", "screened", "excluded", "eligible_for_full_text",
              "full_text_not_retrieved", "full_text_excluded", "included"}


class ValidationError(Exception):
    pass


def validate_with_jsonschema(state, schema):
    import jsonschema  # type: ignore
    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(state), key=lambda e: list(e.path))
    if errors:
        messages = [f"{'/'.join(str(p) for p in e.path) or '(root)'}: {e.message}" for e in errors]
        raise ValidationError("\n".join(messages))


def validate_fallback(state):
    """Dependency-free structural check. Not a full JSON Schema implementation —
    covers the mistakes that actually corrupt downstream calculations."""
    errors = []

    for key in ("protocol", "search_runs", "reports", "studies"):
        if key not in state:
            errors.append(f"(root): missing required key '{key}'")

    protocol = state.get("protocol", {})
    if protocol:
        if protocol.get("status") not in ("draft", "confirmed"):
            errors.append(f"protocol.status: '{protocol.get('status')}' is not 'draft' or 'confirmed'")
        if not isinstance(protocol.get("version"), int):
            errors.append("protocol.version: must be an integer")
        crit = protocol.get("eligibility_criteria", {})
        if not crit.get("inclusion") or not crit.get("exclusion"):
            errors.append("protocol.eligibility_criteria: both 'inclusion' and 'exclusion' must be non-empty")

    for report_id, report in state.get("reports", {}).items():
        if not report.get("title"):
            errors.append(f"reports.{report_id}: missing 'title'")
        if report.get("stage") not in STAGE_ENUM:
            errors.append(f"reports.{report_id}.stage: '{report.get('stage')}' is not a valid stage")
        for field in ("screening_decisions", "eligibility_decisions"):
            for i, event in enumerate(report.get(field, [])):
                errors.extend(_check_decision_event(f"reports.{report_id}.{field}[{i}]", event))

    for study_id, study in state.get("studies", {}).items():
        if not study.get("reports"):
            errors.append(f"studies.{study_id}: 'reports' must be a non-empty list")

    if errors:
        raise ValidationError("\n".join(errors))


def _check_decision_event(path, event):
    errors = []
    decision = event.get("decision")
    if decision not in DECISION_ENUM:
        errors.append(f"{path}.decision: '{decision}' is not one of {sorted(DECISION_ENUM)}")
    reviewer = event.get("reviewer", "")
    if reviewer != "agent" and not str(reviewer).startswith("human:"):
        errors.append(f"{path}.reviewer: '{reviewer}' must be 'agent' or 'human:<name>'")
    if not event.get("timestamp"):
        errors.append(f"{path}.timestamp: missing")
    if not isinstance(event.get("protocol_version"), int):
        errors.append(f"{path}.protocol_version: missing or not an integer — which criteria version produced this decision?")
    if decision != "include" and not (event.get("reason_category") and event.get("reason")):
        errors.append(f"{path}: decision '{decision}' needs both 'reason_category' and 'reason'")
    return errors


def check_stage_consistency(state):
    """Cross-field check no JSON Schema can express: a report's stored
    `stage` must equal what its decision history implies. Skips reports
    that have no `stage` at all — that's a structural error the schema
    check already caught, not a drift error."""
    errors = []
    for report_id, report in state.get("reports", {}).items():
        stored = report.get("stage")
        if stored is None:
            continue
        expected = derive_stage(report)
        if stored != expected:
            errors.append(
                f"reports.{report_id}.stage: stored as '{stored}' but its decision history implies "
                f"'{expected}' — stage has drifted. Regenerate it with "
                f"generate_flow_diagram.py --update-state rather than hand-setting it."
            )
    if errors:
        raise ValidationError("\n".join(errors))


def validate(state):
    """Raises ValidationError on failure. Returns None on success."""
    try:
        with open(SCHEMA_PATH) as f:
            schema = json.load(f)
    except FileNotFoundError:
        schema = None

    ran_jsonschema = False
    if schema is not None:
        try:
            validate_with_jsonschema(state, schema)
            ran_jsonschema = True
        except ImportError:
            pass  # fall through to the dependency-free check

    if not ran_jsonschema:
        validate_fallback(state)

    check_stage_consistency(state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state_path", help="Path to prisma-state.json")
    args = parser.parse_args()

    with open(args.state_path) as f:
        state = json.load(f)

    try:
        validate(state)
    except ValidationError as e:
        print(f"INVALID: {args.state_path}\n{e}", file=sys.stderr)
        return 1

    print(f"Valid: {args.state_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
