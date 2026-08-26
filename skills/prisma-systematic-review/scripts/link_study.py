#!/usr/bin/env python3
"""Link two or more reports as the same underlying study.

Deduplication (dedupe.py) removes literal duplicate entries of the same
report — e.g. the same paper indexed twice. This script is different:
it's for genuinely distinct reports (a trial registry entry, a
conference abstract, the eventual journal publication) that describe
the same underlying piece of research. Neither report is a duplicate;
both stay in `reports` with their own data, but they share one entry in
`studies` so PRISMA's included-studies count doesn't over-count them as
separate studies.

If any of the given reports already belong to a study, that study's
other reports come along for the ride — linking is transitive, the same
way dedupe's union-find is.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validate_state import ValidationError, validate  # noqa: E402

State = dict[str, Any]


def link(
    state: State, report_ids: list[str], primary_report: str | None = None, study_id: str | None = None
) -> tuple[State, str]:
    reports: dict[str, Any] = state.setdefault("reports", {})
    studies: dict[str, Any] = state.setdefault("studies", {})

    missing = [rid for rid in report_ids if rid not in reports]
    if missing:
        raise SystemExit(f"error: unknown report id(s): {missing}")

    all_reports = set(report_ids)
    existing_study_ids = {reports[rid].get("study_id") for rid in report_ids if reports[rid].get("study_id")}
    for sid in existing_study_ids:
        all_reports.update(studies.get(sid, {}).get("reports", []))
        studies.pop(sid, None)

    new_study_id = study_id or f"study:{sorted(all_reports)[0]}"
    primary = primary_report or sorted(all_reports)[0]
    if primary not in all_reports:
        raise SystemExit(f"error: --primary {primary} must be one of the linked reports: {sorted(all_reports)}")

    studies[new_study_id] = {"reports": sorted(all_reports), "primary_report": primary}
    for rid in all_reports:
        reports[rid]["study_id"] = new_study_id

    return state, new_study_id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state_path", help="Path to prisma-state.json")
    parser.add_argument("--reports", nargs="+", required=True, help="Report IDs to link as one study (2 or more)")
    parser.add_argument("--primary", help="Which report is the primary reference for this study (default: first, sorted)")
    parser.add_argument("--study-id", help="Explicit study id to use (default: derived from a report id)")
    args = parser.parse_args()

    if len(args.reports) < 2:
        raise SystemExit("error: give at least two --reports to link")

    with open(args.state_path) as f:
        state = json.load(f)

    state, study_id = link(state, args.reports, args.primary, args.study_id)

    try:
        validate(state)
    except ValidationError as e:
        raise SystemExit(f"error: linking produced an invalid state, not writing:\n{e}")

    with open(args.state_path, "w") as f:
        json.dump(state, f, indent=2)

    print(f"Linked {args.reports} as study '{study_id}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
