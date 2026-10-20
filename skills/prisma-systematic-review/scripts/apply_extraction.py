#!/usr/bin/env python3
"""Apply a full-text eligibility + extraction batch to the state file.

This is the one place extraction output (from the prisma-data-extractor agent,
or hand-written) gets merged in — so the orchestrator stays the only writer of
`prisma-state.json`, exactly as with screening. For each batch item it appends
an eligibility decision event, then (after study_id assignment) attaches the
extraction to the STUDY, not the report.

Each batch item:
    {
      "report_id": "pubmed-12345",        # or "pmid": "12345"
      "decision": "include",               # default "include"
      "retrieved": true,                   # default true; false => full_text_not_retrieved
      "reason_category": "...",             # required unless decision == include
      "reason": "...",                      # required unless decision == include
      "reviewer": "agent",                  # default "agent"; use "human:<name>" for your own
      "extraction": { ... }                 # optional structured fields -> studies.<id>.extraction
    }

Usage:
    apply_extraction.py STATE BATCH.json [--protocol-version N]

It runs generate_flow_diagram.py --update-state itself to recompute stages and
assign single-report study_ids, then attaches extractions. Always run
validate_state.py afterward.
"""
import argparse, datetime, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("state")
    ap.add_argument("batch")
    ap.add_argument("--protocol-version", type=int, default=None,
                    help="default: the current protocol.version in the state file")
    args = ap.parse_args()
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    state = json.load(open(args.state))
    reports = state["reports"]
    pv = args.protocol_version if args.protocol_version is not None \
        else state.get("protocol", {}).get("version", 1)
    by_pmid = {(r.get("identifiers") or {}).get("pmid"): rid for rid, r in reports.items()}

    batch = json.load(open(args.batch))
    applied = {}
    for item in batch:
        rid = item.get("report_id") or by_pmid.get(item.get("pmid"))
        if not rid or rid not in reports:
            sys.exit(f"batch item does not match any report: {item.get('report_id') or item.get('pmid')}")
        rep = reports[rid]
        dec = item.get("decision", "include")
        ev = {"decision": dec,
              "full_text_retrieved": item.get("retrieved", True),
              "reviewer": item.get("reviewer", "agent"),
              "timestamp": ts, "protocol_version": pv}
        if dec != "include":
            if not item.get("reason_category") or not item.get("reason"):
                sys.exit(f"{rid}: decision '{dec}' requires reason_category and reason")
            ev["reason_category"] = item["reason_category"]
            ev["reason"] = item["reason"]
        rep.setdefault("eligibility_decisions", []).append(ev)
        if item.get("extraction"):
            applied[rid] = item["extraction"]

    json.dump(state, open(args.state, "w"), indent=2, ensure_ascii=False)

    # Recompute stages and assign 1:1 study_ids for the newly included reports.
    subprocess.run([sys.executable, os.path.join(HERE, "generate_flow_diagram.py"),
                    args.state, "--out", "flow-diagram", "--update-state"],
                   check=True, stdout=subprocess.DEVNULL)

    state = json.load(open(args.state))
    rep2study = {}
    for sid, st in state.get("studies", {}).items():
        for r in st.get("reports", []):
            rep2study[r] = sid
    n = 0
    for rid, ex in applied.items():
        sid = rep2study.get(rid) or state["reports"][rid].get("study_id")
        if sid:
            state["studies"][sid]["extraction"] = ex
            n += 1
    json.dump(state, open(args.state, "w"), indent=2, ensure_ascii=False)
    print(f"applied {len(batch)} eligibility decisions; attached {n} extractions")
    print("now run: validate_state.py", args.state)


if __name__ == "__main__":
    main()
