#!/usr/bin/env python3
"""Recompute PRISMA 2020 flow-diagram counts from prisma-state.json and
render both a Mermaid flowchart (.mmd) and a standalone SVG.

Counts are ALWAYS derived from `reports` and `studies`, never read from
a cached `derived` block — that block is a cache and gets overwritten by
this script. A hand-edited count that drifts from the actual record
tally is a silent correctness bug in a document meant to be an audit
trail.

Each report's *current* screening/eligibility decision is the last
entry in its decision-event list, not a single overwritable field — see
references/state-schema.md for why. A record whose decision history is
exclude -> include reports as currently included; the exclude is still
in the log for anyone who wants to see it changed.

Reports vs. studies: PRISMA distinguishes a *report* (one publication —
a journal article, a conference abstract, a trial registry entry) from
a *study* (the underlying piece of research, which may have several
reports). An included report with no `study_id` yet is assumed to be
its own single-report study — pass --update-state to persist that
1:1 assignment into `studies`, or link multiple reports to one study
first with link_study.py if you know they're the same underlying trial.
"""
from __future__ import annotations

import argparse
import json
import sys
import textwrap
from collections import Counter
from typing import Any

Report = dict[str, Any]
Study = dict[str, Any]
DecisionEvent = dict[str, Any]
Counts = dict[str, Any]


def classify_source(source: str | None) -> str:
    if source in ("clinicaltrials", "registry", "who-ictrp"):
        return "registers"
    if source == "manual":
        return "other_methods"
    return "databases"


def current_decision(events: list[DecisionEvent]) -> DecisionEvent | None:
    """The log is append-only and chronological; the current decision is
    simply the last entry. `supersedes` is audit metadata, not a pointer
    the reader needs to follow — last-wins is unambiguous by construction."""
    return events[-1] if events else None


def is_duplicate(report: Report) -> bool:
    return str(report.get("dedup_status", "")).startswith("duplicate_of:")


def derive_stage(report: Report) -> str:
    """The ONE place that maps a report's decision history to a stage.
    `report["stage"]` in the state file is a cache of this function's
    output — it is never hand-set or hand-advanced, specifically because
    a field nothing recomputes drifts the moment a decision is appended
    (v0.1's bug: `stage` was written once as "identified" and nothing
    ever moved it forward). compute_counts() below calls this rather
    than re-deriving the same branching logic, so the two can't diverge."""
    if is_duplicate(report):
        return "identified"  # duplicates never enter the pipeline themselves

    sd = current_decision(report.get("screening_decisions", []))
    if sd is None:
        return "identified"
    if sd["decision"] == "exclude":
        return "excluded"

    ed = current_decision(report.get("eligibility_decisions", []))
    if ed is None:
        return "eligible_for_full_text"
    if ed.get("full_text_retrieved") is False:
        return "full_text_not_retrieved"
    if ed["decision"] == "exclude":
        return "full_text_excluded"
    return "included"


def compute_counts(reports: dict[str, Report], studies: dict[str, Study]) -> tuple[Counts, dict[str, Study]]:
    counts: Counts = {
        "identification": {"databases": 0, "registers": 0, "other_methods": 0, "duplicates_removed": 0},
        "screening": {"screened": 0, "excluded": 0, "exclusion_reasons": Counter()},
        "eligibility": {"sought": 0, "not_retrieved": 0, "assessed": 0, "excluded": 0, "exclusion_reasons": Counter()},
        "included": {"studies": 0, "reports": 0},
        "pending": {"awaiting_screening": 0, "awaiting_eligibility": 0},
    }

    for rep in reports.values():
        counts["identification"][classify_source(rep.get("source"))] += 1
        if is_duplicate(rep):
            counts["identification"]["duplicates_removed"] += 1

    included_report_ids: list[str] = []
    for rid, rep in reports.items():
        if is_duplicate(rep):
            continue
        stage = derive_stage(rep)

        if stage == "identified":
            counts["pending"]["awaiting_screening"] += 1
            continue

        counts["screening"]["screened"] += 1
        if stage == "excluded":
            sd = current_decision(rep["screening_decisions"])
            assert sd is not None, "derive_stage returned 'excluded' without a screening decision"
            counts["screening"]["excluded"] += 1
            counts["screening"]["exclusion_reasons"][sd.get("reason_category", "unspecified")] += 1
            continue

        counts["eligibility"]["sought"] += 1
        if stage == "eligible_for_full_text":
            counts["pending"]["awaiting_eligibility"] += 1
        elif stage == "full_text_not_retrieved":
            counts["eligibility"]["not_retrieved"] += 1
        elif stage == "full_text_excluded":
            ed = current_decision(rep["eligibility_decisions"])
            assert ed is not None, "derive_stage returned 'full_text_excluded' without an eligibility decision"
            counts["eligibility"]["assessed"] += 1
            counts["eligibility"]["excluded"] += 1
            counts["eligibility"]["exclusion_reasons"][ed.get("reason_category", "unspecified")] += 1
        elif stage == "included":
            counts["eligibility"]["assessed"] += 1
            included_report_ids.append(rid)

    counts["included"]["reports"] = len(included_report_ids)

    # Study linking: an included report keeps its existing study_id if
    # one was assigned (e.g. via link_study.py); otherwise it's treated
    # as its own single-report study. auto_studies records the 1:1
    # assignments the caller may want to persist with --update-state.
    study_ids: set[str] = set()
    auto_studies: dict[str, Study] = {}
    for rid in included_report_ids:
        rep = reports[rid]
        sid = rep.get("study_id")
        if not sid:
            sid = f"study:{rid}"
            auto_studies[sid] = {"reports": [rid], "primary_report": rid}
        study_ids.add(sid)
    counts["included"]["studies"] = len(study_ids)

    counts["screening"]["exclusion_reasons"] = dict(counts["screening"]["exclusion_reasons"])
    counts["eligibility"]["exclusion_reasons"] = dict(counts["eligibility"]["exclusion_reasons"])
    return counts, auto_studies


MAX_REASON_CATEGORIES_SHOWN = 6


def reason_lines(reasons: dict[str, int]) -> list[str]:
    """A review can accumulate many distinct exclusion-reason categories
    (a large multi-topic review easily has 15-30). Listing every one of
    them as a separate line makes a box grow without bound and the
    diagram illegible, so this shows the top categories by count and
    rolls the rest into a single summary line — full detail is always
    in the state file itself, the diagram is a visual summary of it."""
    items = sorted(reasons.items(), key=lambda kv: -kv[1])
    lines = [f"{label} (n={n})" for label, n in items[:MAX_REASON_CATEGORIES_SHOWN]]
    rest = items[MAX_REASON_CATEGORIES_SHOWN:]
    if rest:
        rest_n = sum(n for _, n in rest)
        lines.append(f"+{len(rest)} more categor{'y' if len(rest) == 1 else 'ies'} (n={rest_n}) — see prisma-state.json")
    return lines


def render_mermaid(counts: Counts) -> str:
    ident = counts["identification"]
    scr = counts["screening"]
    elig = counts["eligibility"]
    inc = counts["included"]

    lines = ["flowchart TD"]
    lines.append('    subgraph ID["Identification"]')
    ident_nodes: list[str] = []
    if ident["databases"]:
        lines.append(f'        A1["Records identified from databases<br/>n={ident["databases"]}"]')
        ident_nodes.append("A1")
    if ident["registers"]:
        lines.append(f'        A2["Records identified from registers<br/>n={ident["registers"]}"]')
        ident_nodes.append("A2")
    if ident["other_methods"]:
        lines.append(f'        A3["Records identified from other methods<br/>n={ident["other_methods"]}"]')
        ident_nodes.append("A3")
    lines.append("    end")

    lines.append(f'    DEDUP["Duplicates removed<br/>n={ident["duplicates_removed"]}"]')
    for src in ident_nodes:
        lines.append(f"    {src} --> DEDUP")
    lines.append(f'    DEDUP --> SCR["Records screened<br/>n={scr["screened"]}"]')

    excl_scr_parts = [f'Records excluded<br/>n={scr["excluded"]}'] + reason_lines(scr["exclusion_reasons"])
    lines.append(f'    SCR --> EXCL_SCR["{"<br/>".join(excl_scr_parts)}"]')
    lines.append(f'    SCR --> SOUGHT["Reports sought for retrieval<br/>n={elig["sought"]}"]')
    lines.append(f'    SOUGHT --> NR["Reports not retrieved<br/>n={elig["not_retrieved"]}"]')
    lines.append(f'    SOUGHT --> ASSESSED["Reports assessed for eligibility<br/>n={elig["assessed"]}"]')

    excl_elig_parts = [f'Reports excluded<br/>n={elig["excluded"]}'] + reason_lines(elig["exclusion_reasons"])
    lines.append(f'    ASSESSED --> EXCL_ELIG["{"<br/>".join(excl_elig_parts)}"]')
    lines.append(f'    ASSESSED --> INCLUDED["Studies included in review<br/>n={inc["studies"]}<br/>Reports of included studies: n={inc["reports"]}"]')

    return "\n".join(lines)


AVG_CHAR_WIDTH_PX = 6.5  # rough width of one character at font-size 13, Helvetica/Arial
LINE_HEIGHT_PX = 16
BOX_PADDING_PX = 16


Box = tuple[float, float, float, float, list[tuple[str, bool]], list[str]]


def wrap_to_width(text: str, box_width: float) -> list[str]:
    """Word-wrap one label to fit inside a box of the given pixel width.
    A box sized only for the raw string count (v0.1's approach) lets a
    single long exclusion-reason sentence run outside its box — this
    makes the box grow to actually fit its own text instead."""
    max_chars = max(10, int((box_width - BOX_PADDING_PX) / AVG_CHAR_WIDTH_PX))
    return textwrap.wrap(text, width=max_chars) or [""]


def render_svg(counts: Counts) -> str:
    ident = counts["identification"]
    scr = counts["screening"]
    elig = counts["eligibility"]
    inc = counts["included"]

    main_x, main_w = 40, 320
    side_x, side_w = 420, 340
    gap = 30
    # Two independent vertical frontiers: boxes in the same column must
    # never overlap each other, but the two columns advance at different
    # rates (a tall "excluded" box in the side column shouldn't push the
    # next MAIN-column box down — only the next SIDE-column box).
    frontier = {"main": 20.0, "side": 20.0}
    boxes: list[Box] = []
    arrows: list[tuple[Box, Box]] = []

    def add_box(
        column: str, x: float, w: float, title: str,
        extra_lines: list[str] | None = None, align_with: Box | None = None,
    ) -> Box:
        """align_with: the main-column box this side box should start
        level with, IF the side column's own frontier allows it — a side
        box never starts above the row it logically belongs to, but if
        an earlier, taller side box is still extending downward, this
        one starts after it instead of overlapping it."""
        raw_lines = [title] + (extra_lines or [])
        wrapped: list[tuple[str, bool]] = []
        for i, line in enumerate(raw_lines):
            for wrapped_line in wrap_to_width(line, w):
                wrapped.append((wrapped_line, i == 0))  # (text, is_title)
        h = BOX_PADDING_PX + LINE_HEIGHT_PX + LINE_HEIGHT_PX * (len(wrapped) - 1) + BOX_PADDING_PX / 2

        desired_y = frontier[column] if align_with is None else max(align_with[1], frontier["side"])
        by = desired_y
        box: Box = (x, by, w, h, wrapped, raw_lines)
        boxes.append(box)
        frontier[column] = by + h + gap
        return box

    ident_lines: list[str] = []
    if ident["databases"]:
        ident_lines.append(f"Databases: n={ident['databases']}")
    if ident["registers"]:
        ident_lines.append(f"Registers: n={ident['registers']}")
    if ident["other_methods"]:
        ident_lines.append(f"Other methods: n={ident['other_methods']}")
    b_ident = add_box("main", main_x, main_w, "Records identified", ident_lines)

    b_dedup = add_box("main", main_x, main_w, "Duplicates removed", [f"n={ident['duplicates_removed']}"])
    arrows.append((b_ident, b_dedup))

    b_screened = add_box("main", main_x, main_w, "Records screened", [f"n={scr['screened']}"])
    arrows.append((b_dedup, b_screened))

    b_excl_scr = add_box("side", side_x, side_w, "Records excluded",
                          [f"n={scr['excluded']}"] + reason_lines(scr["exclusion_reasons"]),
                          align_with=b_screened)
    arrows.append((b_screened, b_excl_scr))

    b_sought = add_box("main", main_x, main_w, "Reports sought for retrieval", [f"n={elig['sought']}"])
    arrows.append((b_screened, b_sought))

    b_nr = add_box("side", side_x, side_w, "Reports not retrieved", [f"n={elig['not_retrieved']}"],
                    align_with=b_sought)
    arrows.append((b_sought, b_nr))

    b_assessed = add_box("main", main_x, main_w, "Reports assessed for eligibility", [f"n={elig['assessed']}"])
    arrows.append((b_sought, b_assessed))

    b_excl_elig = add_box("side", side_x, side_w, "Reports excluded",
                           [f"n={elig['excluded']}"] + reason_lines(elig["exclusion_reasons"]),
                           align_with=b_assessed)
    arrows.append((b_assessed, b_excl_elig))

    b_included = add_box("main", main_x, main_w, "Studies included in review",
                          [f"n={inc['studies']}", f"Reports of included studies: n={inc['reports']}"])
    arrows.append((b_assessed, b_included))

    total_h = max(frontier["main"], frontier["side"]) + 20
    total_w = side_x + side_w + 40
    summary = (f"PRISMA 2020 flow diagram: {ident['databases'] + ident['registers'] + ident['other_methods']} "
               f"records identified, {scr['excluded']} excluded at screening, {elig['excluded']} excluded at "
               f"eligibility, {inc['studies']} studies included from {inc['reports']} reports.")

    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total_w} {total_h}" '
        f'font-family="Helvetica, Arial, sans-serif" font-size="13" role="img" '
        f'aria-label="{escape_xml(summary)}">',
        f"<title>{escape_xml(summary)}</title>",
        '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" '
        'orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#333"/></marker></defs>',
        f'<rect x="0" y="0" width="{total_w}" height="{total_h}" fill="white"/>',
    ]

    for (x, by, w, h, wrapped, raw_lines) in boxes:
        box_label = " — ".join(raw_lines)
        svg_parts.append(
            f'<g><title>{escape_xml(box_label)}</title>'
            f'<rect x="{x}" y="{by}" width="{w}" height="{h}" rx="6" '
            f'fill="#f5f7fa" stroke="#333" stroke-width="1.5"/></g>'
        )
        for i, (text, is_title) in enumerate(wrapped):
            weight = "bold" if is_title else "normal"
            ty = by + 22 + i * LINE_HEIGHT_PX
            svg_parts.append(
                f'<text x="{x + w / 2}" y="{ty}" text-anchor="middle" '
                f'font-weight="{weight}">{escape_xml(text)}</text>'
            )

    for (src, dst) in arrows:
        sx, sy, sw, sh = src[:4]
        dx, dy, dw, dh = dst[:4]
        if dx == sx:
            x1, y1 = sx + sw / 2, sy + sh
            x2, y2 = dx + dw / 2, dy
        else:
            x1, y1 = sx + sw, sy + sh / 2
            x2, y2 = dx, dy + dh / 2
        svg_parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                          f'stroke="#333" stroke-width="1.5" marker-end="url(#arrow)"/>')

    svg_parts.append("</svg>")
    return "\n".join(svg_parts)


def escape_xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state_path", help="Path to prisma-state.json")
    parser.add_argument("--out", default="flow-diagram", help="Output basename (default: flow-diagram)")
    parser.add_argument("--update-state", action="store_true",
                         help="Also write recomputed counts, and any auto-created 1:1 studies, back into the state file")
    args = parser.parse_args()

    with open(args.state_path) as f:
        state = json.load(f)

    counts, auto_studies = compute_counts(state.get("reports", {}), state.get("studies", {}))

    pending = counts.pop("pending")
    if pending["awaiting_screening"] or pending["awaiting_eligibility"]:
        print("NOTE: this is a snapshot of a review still in progress:")
        if pending["awaiting_screening"]:
            print(f"  {pending['awaiting_screening']} unique report(s) not yet screened")
        if pending["awaiting_eligibility"]:
            print(f"  {pending['awaiting_eligibility']} report(s) awaiting full-text eligibility assessment")
        print()

    if auto_studies:
        print(f"NOTE: {len(auto_studies)} included report(s) have no study_id yet — "
              f"counted as their own single-report study for this snapshot.")
        if args.update_state:
            print("      Persisting these as 1:1 studies (pass link_study.py first if any of these "
                  "are actually multiple reports of the same trial).")
        print()

    mmd_path = f"{args.out}.mmd"
    svg_path = f"{args.out}.svg"
    with open(mmd_path, "w") as f:
        f.write(render_mermaid(counts) + "\n")
    with open(svg_path, "w") as f:
        f.write(render_svg(counts) + "\n")

    print(f"Wrote {mmd_path} and {svg_path}")
    print(json.dumps(counts, indent=2))

    if args.update_state:
        for sid, study in auto_studies.items():
            state.setdefault("studies", {})[sid] = study
            state["reports"][study["primary_report"]]["study_id"] = sid
        for rep in state["reports"].values():
            rep["stage"] = derive_stage(rep)
        state["derived"] = counts
        with open(args.state_path, "w") as f:
            json.dump(state, f, indent=2)
        print(f"\nUpdated state written back to {args.state_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
