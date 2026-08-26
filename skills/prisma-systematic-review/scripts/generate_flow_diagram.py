#!/usr/bin/env python3
"""Recompute PRISMA 2020 flow-diagram counts from prisma-state.json records
and render both a Mermaid flowchart (.mmd) and a standalone SVG.

Counts are ALWAYS derived from the `records` dict, never read from the
`counts` block in the state file — that block is a cache and gets
overwritten by this script. This is deliberate: a hand-edited count that
drifts from the actual record tally is a silent correctness bug in a
document meant to be an audit trail.

If some records haven't reached a stage yet (e.g. screened but not yet
assessed for eligibility), this script reports them as "pending" rather
than guessing a final number — the flow diagram is a snapshot, and PRISMA
review authors should regenerate it once the review is complete.
"""
import argparse
import json
import sys
from collections import Counter


def classify_source(source):
    if source == "clinicaltrials":
        return "registers"
    if source == "manual":
        return "other_methods"
    return "databases"


def compute_counts(records):
    counts = {
        "identification": {"databases": 0, "registers": 0, "other_methods": 0, "duplicates_removed": 0},
        "screening": {"screened": 0, "excluded": 0, "exclusion_reasons": Counter()},
        "eligibility": {"sought": 0, "not_retrieved": 0, "assessed": 0, "excluded": 0, "exclusion_reasons": Counter()},
        "included": {"studies": 0, "reports": 0},
        "pending": {"awaiting_screening": 0, "awaiting_eligibility": 0},
    }

    for rec in records.values():
        counts["identification"][classify_source(rec.get("source"))] += 1
        if str(rec.get("dedup_status", "")).startswith("duplicate_of:"):
            counts["identification"]["duplicates_removed"] += 1

    unique_records = [
        rec for rec in records.values()
        if not str(rec.get("dedup_status", "")).startswith("duplicate_of:")
    ]

    passed_screening = []
    for rec in unique_records:
        sd = rec.get("screening_decision")
        if not sd:
            counts["pending"]["awaiting_screening"] += 1
            continue
        counts["screening"]["screened"] += 1
        if sd["decision"] == "exclude":
            counts["screening"]["excluded"] += 1
            counts["screening"]["exclusion_reasons"][sd.get("reason_category", "unspecified")] += 1
        else:
            passed_screening.append(rec)

    counts["eligibility"]["sought"] = len(passed_screening)
    for rec in passed_screening:
        ed = rec.get("eligibility_decision")
        if not ed:
            counts["pending"]["awaiting_eligibility"] += 1
            continue
        if ed.get("full_text_retrieved") is False:
            counts["eligibility"]["not_retrieved"] += 1
            continue
        counts["eligibility"]["assessed"] += 1
        if ed["decision"] == "exclude":
            counts["eligibility"]["excluded"] += 1
            counts["eligibility"]["exclusion_reasons"][ed.get("reason_category", "unspecified")] += 1
        else:
            counts["included"]["studies"] += 1

    counts["included"]["reports"] = counts["included"]["studies"]  # v0.1: no multi-report consolidation

    counts["screening"]["exclusion_reasons"] = dict(counts["screening"]["exclusion_reasons"])
    counts["eligibility"]["exclusion_reasons"] = dict(counts["eligibility"]["exclusion_reasons"])
    return counts


def reason_lines(reasons):
    return [f"{label} (n={n})" for label, n in sorted(reasons.items(), key=lambda kv: -kv[1])]


def render_mermaid(counts):
    ident = counts["identification"]
    scr = counts["screening"]
    elig = counts["eligibility"]
    inc = counts["included"]

    lines = ["flowchart TD"]
    lines.append('    subgraph ID["Identification"]')
    ident_nodes = []
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


def render_svg(counts):
    ident = counts["identification"]
    scr = counts["screening"]
    elig = counts["eligibility"]
    inc = counts["included"]

    main_x, main_w = 40, 320
    side_x, side_w = 420, 340
    y = 20
    gap = 30
    boxes = []   # (x, y, w, h, lines)
    arrows = []  # (x1, y1, x2, y2)

    def add_box(x, w, title, extra_lines=None, y_override=None):
        nonlocal y
        lines_list = [title] + (extra_lines or [])
        h = 34 + 16 * (len(lines_list) - 1) + 16
        by = y_override if y_override is not None else y
        box = (x, by, w, h, lines_list)
        boxes.append(box)
        if y_override is None:
            y = by + h + gap
        return box

    ident_lines = []
    if ident["databases"]:
        ident_lines.append(f"Databases: n={ident['databases']}")
    if ident["registers"]:
        ident_lines.append(f"Registers: n={ident['registers']}")
    if ident["other_methods"]:
        ident_lines.append(f"Other methods: n={ident['other_methods']}")
    b_ident = add_box(main_x, main_w, "Records identified", ident_lines)

    b_dedup = add_box(main_x, main_w, "Duplicates removed", [f"n={ident['duplicates_removed']}"])
    arrows.append((b_ident, b_dedup))

    b_screened = add_box(main_x, main_w, "Records screened", [f"n={scr['screened']}"])
    arrows.append((b_dedup, b_screened))

    b_excl_scr = add_box(side_x, side_w, "Records excluded",
                          [f"n={scr['excluded']}"] + reason_lines(scr["exclusion_reasons"]),
                          y_override=b_screened[1])
    arrows.append((b_screened, b_excl_scr))

    b_sought = add_box(main_x, main_w, "Reports sought for retrieval", [f"n={elig['sought']}"])
    arrows.append((b_screened, b_sought))

    b_nr = add_box(side_x, side_w, "Reports not retrieved", [f"n={elig['not_retrieved']}"],
                    y_override=b_sought[1])
    arrows.append((b_sought, b_nr))

    b_assessed = add_box(main_x, main_w, "Reports assessed for eligibility", [f"n={elig['assessed']}"])
    arrows.append((b_sought, b_assessed))

    b_excl_elig = add_box(side_x, side_w, "Reports excluded",
                           [f"n={elig['excluded']}"] + reason_lines(elig["exclusion_reasons"]),
                           y_override=b_assessed[1])
    arrows.append((b_assessed, b_excl_elig))

    b_included = add_box(main_x, main_w, "Studies included in review",
                          [f"n={inc['studies']}", f"Reports of included studies: n={inc['reports']}"])
    arrows.append((b_assessed, b_included))

    total_h = y + 20
    total_w = side_x + side_w + 40

    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total_w} {total_h}" '
        f'font-family="Helvetica, Arial, sans-serif" font-size="13">',
        '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" '
        'orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#333"/></marker></defs>',
        f'<rect x="0" y="0" width="{total_w}" height="{total_h}" fill="white"/>',
    ]

    for (x, by, w, h, lines_list) in boxes:
        svg_parts.append(
            f'<rect x="{x}" y="{by}" width="{w}" height="{h}" rx="6" '
            f'fill="#f5f7fa" stroke="#333" stroke-width="1.5"/>'
        )
        for i, line in enumerate(lines_list):
            weight = "bold" if i == 0 else "normal"
            ty = by + 22 + i * 16
            svg_parts.append(
                f'<text x="{x + w / 2}" y="{ty}" text-anchor="middle" '
                f'font-weight="{weight}">{escape_xml(line)}</text>'
            )

    for (src, dst) in arrows:
        sx, sy, sw, sh, _ = src
        dx, dy, dw, dh, _ = dst
        if dx == sx:  # straight down
            x1, y1 = sx + sw / 2, sy + sh
            x2, y2 = dx + dw / 2, dy
        else:  # branch right
            x1, y1 = sx + sw, sy + sh / 2
            x2, y2 = dx, dy + dh / 2
        svg_parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                          f'stroke="#333" stroke-width="1.5" marker-end="url(#arrow)"/>')

    svg_parts.append("</svg>")
    return "\n".join(svg_parts)


def escape_xml(text):
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state_path", help="Path to prisma-state.json")
    parser.add_argument("--out", default="flow-diagram", help="Output basename (default: flow-diagram)")
    parser.add_argument("--update-state", action="store_true",
                         help="Also write the recomputed counts back into the state file")
    args = parser.parse_args()

    with open(args.state_path) as f:
        state = json.load(f)

    counts = compute_counts(state.get("records", {}))

    pending = counts.pop("pending")
    if pending["awaiting_screening"] or pending["awaiting_eligibility"]:
        print("NOTE: this is a snapshot of a review still in progress:")
        if pending["awaiting_screening"]:
            print(f"  {pending['awaiting_screening']} unique record(s) not yet screened")
        if pending["awaiting_eligibility"]:
            print(f"  {pending['awaiting_eligibility']} record(s) awaiting full-text eligibility assessment")
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
        state["counts"] = counts
        with open(args.state_path, "w") as f:
            json.dump(state, f, indent=2)
        print(f"\nUpdated counts written back to {args.state_path}")


if __name__ == "__main__":
    sys.exit(main())
