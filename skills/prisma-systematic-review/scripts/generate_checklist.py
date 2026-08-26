#!/usr/bin/env python3
"""Generate a PRISMA 2020 checklist status report from prisma-state.json.

Items that can be verified from the state file are checked automatically.
Items that genuinely require the researcher's own judgment or manuscript
prose (rationale, interpretation, competing interests, etc.) are always
flagged as open — silently marking a subjective item "done" would defeat
the point of a reporting checklist.

Two things this deliberately checks strictly, because a looser check
would rubber-stamp incomplete work: eligibility criteria needs BOTH
inclusion AND exclusion criteria present (one alone isn't a usable
criterion set), and extraction/risk-of-bias coverage is checked against
the actual set of *included* studies, not just a total count that a
study excluded earlier could accidentally satisfy.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generate_flow_diagram import Counts, Report, Study, compute_counts, current_decision  # noqa: E402

State = dict[str, Any]

# The PRISMA statement is periodically revised (PRISMA 2009 -> PRISMA
# 2020 was the last major one). CHECKLIST below encodes the 2020 item
# list specifically — if a future revision changes the numbering or
# item set, that's a new CHECKLIST_VERSION and a new CHECKLIST, not an
# in-place edit that leaves old output ambiguous about which version it
# was checked against.
CHECKLIST_VERSION = "PRISMA 2020"
CHECKLIST_SOURCE = "Page MJ, et al. The PRISMA 2020 statement. BMJ 2021;372:n71."

CHECKLIST: list[tuple[int | str, str, str, str]] = [
    (1, "Title", "Identify the report as a systematic review", "manual"),
    (2, "Abstract", "Structured summary: objectives, methods, results, funding", "manual"),
    (3, "Introduction", "Rationale for the review", "manual"),
    (4, "Introduction", "Explicit objectives / research question", "research_question"),
    (5, "Methods", "Eligibility criteria", "eligibility_criteria"),
    (6, "Methods", "Information sources searched", "sources"),
    (7, "Methods", "Full, reproducible search strategy", "queries"),
    (8, "Methods", "Study selection process", "manual"),
    (9, "Methods", "Data collection process", "manual"),
    ("10a", "Methods", "Outcomes / data items sought", "manual"),
    ("10b", "Methods", "Other variables collected", "manual"),
    (11, "Methods", "Risk-of-bias assessment method", "manual"),
    (12, "Methods", "Effect measures used", "manual"),
    ("13a-f", "Methods", "Synthesis methods", "manual"),
    (14, "Methods", "Reporting bias assessment method", "manual"),
    (15, "Methods", "Certainty-of-evidence assessment method", "manual"),
    ("16a", "Results", "Study selection flow diagram", "flow_diagram"),
    ("16b", "Results", "Studies excluded with reasons", "eligibility_exclusion_reasons"),
    (17, "Results", "Characteristics of included studies", "extraction"),
    (18, "Results", "Risk-of-bias results per included study", "risk_of_bias"),
    (19, "Results", "Results for all outcomes, per study", "extraction"),
    ("20a-d", "Results", "Synthesis results", "manual"),
    (21, "Results", "Assessment of reporting bias", "manual"),
    (22, "Results", "Certainty of evidence per outcome", "manual"),
    ("23a-d", "Discussion", "Interpretation, limitations, implications", "manual"),
    ("24a", "Other info", "Registration name and number", "manual"),
    ("24b", "Other info", "Where the protocol can be accessed", "manual"),
    ("24c", "Other info", "Protocol amendments", "manual"),
    (25, "Other info", "Funding sources for the review", "manual"),
    (26, "Other info", "Competing interests of review authors", "manual"),
    (27, "Other info", "Availability of data, code, and materials", "manual"),
]


def nonempty(v: object) -> bool:
    if v is None:
        return False
    if isinstance(v, (list, dict, str)):
        return len(v) > 0
    return bool(v)


def included_study_ids(reports: dict[str, Report], studies: dict[str, Study], counts: Counts) -> set[str]:
    """The actual set of included study ids — including the auto 1:1
    assignment generate_flow_diagram.py would make for an included
    report that has no explicit study_id yet."""
    ids: set[str] = set()
    for rid, rep in reports.items():
        if str(rep.get("dedup_status", "")).startswith("duplicate_of:"):
            continue
        sd = current_decision(rep.get("screening_decisions", []))
        if not sd or sd["decision"] == "exclude":
            continue
        ed = current_decision(rep.get("eligibility_decisions", []))
        if not ed or ed.get("full_text_retrieved") is False or ed["decision"] == "exclude":
            continue
        ids.add(rep.get("study_id") or f"study:{rid}")
    return ids


def evaluate(
    auto_check: str, state: State, counts: Counts, reports: dict[str, Report],
    studies: dict[str, Study], flow_diagram_paths: list[str],
) -> tuple[bool | None, str]:
    protocol = state.get("protocol", {})

    if auto_check == "manual":
        return None, "Needs the author's own manuscript text / judgment call."

    if auto_check == "research_question":
        ok = nonempty(protocol.get("research_question"))
        return ok, f'protocol.research_question = "{protocol.get("research_question", "")}"'

    if auto_check == "eligibility_criteria":
        crit = protocol.get("eligibility_criteria", {})
        n_inc, n_exc = len(crit.get("inclusion", [])), len(crit.get("exclusion", []))
        ok = n_inc > 0 and n_exc > 0
        return ok, f"{n_inc} inclusion, {n_exc} exclusion criteria recorded (both required)"

    if auto_check == "sources":
        sources = protocol.get("search_strategy", {}).get("sources", [])
        return nonempty(sources), f"Sources: {', '.join(sources) if sources else 'none recorded'}"

    if auto_check == "queries":
        queries = {sr.get("source"): sr.get("query") for sr in state.get("search_runs", {}).values() if sr.get("query")}
        return nonempty(queries), f"{len(queries)} source(s) with a recorded query string"

    if auto_check == "flow_diagram":
        found = [p for p in flow_diagram_paths if os.path.exists(p)]
        return nonempty(found), f"Found: {', '.join(found) if found else 'no flow-diagram file yet — run generate_flow_diagram.py'}"

    if auto_check == "eligibility_exclusion_reasons":
        reasons = counts["eligibility"]["exclusion_reasons"]
        return nonempty(reasons), f"{len(reasons)} exclusion-reason categor(y/ies) at full-text stage"

    if auto_check == "extraction":
        included = included_study_ids(reports, studies, counts)
        missing = [sid for sid in included if not nonempty(studies.get(sid, {}).get("extraction"))]
        ok = len(included) > 0 and not missing
        return ok, (f"{len(included) - len(missing)}/{len(included)} included stud(y/ies) have extraction data"
                    + (f" — missing: {missing}" if missing else ""))

    if auto_check == "risk_of_bias":
        included = included_study_ids(reports, studies, counts)
        missing = [sid for sid in included if not nonempty(studies.get(sid, {}).get("risk_of_bias"))]
        ok = len(included) > 0 and not missing
        return ok, (f"{len(included) - len(missing)}/{len(included)} included stud(y/ies) have a risk_of_bias field"
                    + (f" — missing: {missing}" if missing else ""))

    return None, "Unknown check type."


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state_path", help="Path to prisma-state.json")
    parser.add_argument("--out", default="prisma-2020-checklist.md", help="Output markdown path")
    parser.add_argument("--flow-diagram-base", default="flow-diagram",
                         help="Basename used when running generate_flow_diagram.py (default: flow-diagram)")
    args = parser.parse_args()

    with open(args.state_path) as f:
        state = json.load(f)

    reports = state.get("reports", {})
    studies = state.get("studies", {})
    counts, _ = compute_counts(reports, studies)
    flow_diagram_paths = [f"{args.flow_diagram_base}.svg", f"{args.flow_diagram_base}.mmd"]

    rows: list[tuple[int | str, str, str, str, str]] = []
    satisfied = 0
    open_items = 0
    for num, section, item, auto_check in CHECKLIST:
        ok, note = evaluate(auto_check, state, counts, reports, studies, flow_diagram_paths)
        if ok is True:
            status = "✅ addressed"
            satisfied += 1
        elif ok is False:
            status = "⬜ open"
            open_items += 1
        else:
            status = "⬜ needs manual confirmation"
            open_items += 1
        rows.append((num, section, item, status, note))

    lines = [
        "# PRISMA 2020 checklist status",
        "",
        f"Checked against: **{CHECKLIST_VERSION}** ({CHECKLIST_SOURCE}). If a later PRISMA revision changes "
        "item numbering, results generated under a different version aren't comparable to this report.",
        "",
        f"Auto-checked from `{args.state_path}`. {satisfied} item(s) verifiable from recorded data; "
        f"{open_items} item(s) still need the author's manuscript text or a judgment call — "
        "review those before submission.",
        "",
        "| # | Section | Item | Status | Note |",
        "|---|---------|------|--------|------|",
    ]
    for num, section, item, status, note in rows:
        note_escaped = note.replace("|", "\\|")
        lines.append(f"| {num} | {section} | {item} | {status} | {note_escaped} |")

    with open(args.out, "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Wrote {args.out}  ({satisfied} addressed, {open_items} open)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
