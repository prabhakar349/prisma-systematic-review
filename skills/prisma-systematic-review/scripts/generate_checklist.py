#!/usr/bin/env python3
"""Generate a PRISMA 2020 checklist status report from prisma-state.json.

Items that can be verified from the state file are checked automatically.
Items that genuinely require the researcher's own judgment or manuscript
prose (rationale, interpretation, competing interests, etc.) are always
flagged as open — silently marking a subjective item "done" would defeat
the point of a reporting checklist.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generate_flow_diagram import compute_counts  # noqa: E402

CHECKLIST = [
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


def nonempty(v):
    if v is None:
        return False
    if isinstance(v, (list, dict, str)):
        return len(v) > 0
    return bool(v)


def evaluate(auto_check, state, counts, records, flow_diagram_paths):
    protocol = state.get("protocol", {})

    if auto_check == "manual":
        return None, "Needs the author's own manuscript text / judgment call."

    if auto_check == "research_question":
        ok = nonempty(protocol.get("research_question"))
        return ok, f'protocol.research_question = "{protocol.get("research_question", "")}"'

    if auto_check == "eligibility_criteria":
        crit = protocol.get("eligibility_criteria", {})
        ok = nonempty(crit.get("inclusion")) or nonempty(crit.get("exclusion"))
        return ok, f"{len(crit.get('inclusion', []))} inclusion, {len(crit.get('exclusion', []))} exclusion criteria recorded"

    if auto_check == "sources":
        sources = protocol.get("search_strategy", {}).get("sources", [])
        return nonempty(sources), f"Sources: {', '.join(sources) if sources else 'none recorded'}"

    if auto_check == "queries":
        queries = protocol.get("search_strategy", {}).get("queries", {})
        return nonempty(queries), f"{len(queries)} source(s) with a recorded query string"

    if auto_check == "flow_diagram":
        found = [p for p in flow_diagram_paths if os.path.exists(p)]
        return nonempty(found), f"Found: {', '.join(found) if found else 'no flow-diagram file yet — run generate_flow_diagram.py'}"

    if auto_check == "eligibility_exclusion_reasons":
        reasons = counts["eligibility"]["exclusion_reasons"]
        return nonempty(reasons), f"{len(reasons)} exclusion-reason categor(y/ies) at full-text stage"

    if auto_check == "extraction":
        with_extraction = sum(1 for r in records.values() if nonempty(r.get("extraction")))
        included = counts["included"]["studies"]
        return with_extraction >= included and included > 0, f"{with_extraction} record(s) have extraction data ({included} included)"

    if auto_check == "risk_of_bias":
        with_rob = sum(1 for r in records.values() if nonempty(r.get("extraction", {}).get("risk_of_bias")))
        included = counts["included"]["studies"]
        return with_rob >= included and included > 0, f"{with_rob} record(s) have a risk_of_bias field ({included} included)"

    return None, "Unknown check type."


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state_path", help="Path to prisma-state.json")
    parser.add_argument("--out", default="prisma-2020-checklist.md", help="Output markdown path")
    parser.add_argument("--flow-diagram-base", default="flow-diagram",
                         help="Basename used when running generate_flow_diagram.py (default: flow-diagram)")
    args = parser.parse_args()

    with open(args.state_path) as f:
        state = json.load(f)

    records = state.get("records", {})
    counts = compute_counts(records)
    flow_diagram_paths = [f"{args.flow_diagram_base}.svg", f"{args.flow_diagram_base}.mmd"]

    rows = []
    satisfied = 0
    open_items = 0
    for num, section, item, auto_check in CHECKLIST:
        ok, note = evaluate(auto_check, state, counts, records, flow_diagram_paths)
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


if __name__ == "__main__":
    sys.exit(main())
