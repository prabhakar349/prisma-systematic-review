#!/usr/bin/env python3
"""Find free, LEGAL open-access full text for the reports you still need to
retrieve, and record the result in the state file so full-text retrieval is
driven by data instead of guesswork.

For every report whose current screening decision is include/maybe and that has
no `retrieval` record yet, it queries Unpaywall (the standard legal OA index)
and writes:

    reports.<id>.retrieval = {
      "checked_at": "...", "is_oa": bool,
      "route": "oa" | "none",          # "none" => needs a non-OA route (see SKILL.md ladder)
      "url": "<best free full-text url or null>",
      "host": "publisher | repository | null"
    }

It never downloads anything and never touches a paywall — it only tells you
which reports have a free copy (fetch those) and which remain paywalled (those
go to the institutional-proxy / ILL / author-request / not-retrieved ladder in
SKILL.md). This is append-safe and idempotent: pass --recheck to refresh rows
that already have a retrieval record.

Usage:
    check_oa.py STATE [--email you@example.org] [--recheck]
"""
import argparse
import datetime
import json
import os
import time
import urllib.parse
import urllib.request


def get(url):
    for _ in range(3):
        try:
            with urllib.request.urlopen(url, timeout=45) as r:
                return r.read()
        except Exception:
            time.sleep(1.5)
    return None


def current(decisions):
    return decisions[-1]["decision"] if decisions else None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("state")
    ap.add_argument("--email", default=os.environ.get("UNPAYWALL_EMAIL", "review@researcher.org"),
                    help="contact for Unpaywall's courtesy param (env UNPAYWALL_EMAIL)")
    ap.add_argument("--recheck", action="store_true", help="re-query reports that already have a retrieval record")
    args = ap.parse_args()
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    state = json.load(open(args.state))
    todo = []
    for rid, rep in state.get("reports", {}).items():
        if rep.get("dedup_status", "unique") != "unique":
            continue
        if current(rep.get("screening_decisions", [])) not in ("include", "maybe"):
            continue
        if rep.get("retrieval") and not args.recheck:
            continue
        todo.append((rid, rep))

    oa = checked = 0
    for rid, rep in todo:
        doi = (rep.get("identifiers") or {}).get("doi")
        rec = {"checked_at": ts, "is_oa": False, "route": "none", "url": None, "host": None}
        if doi:
            data = get(f"https://api.unpaywall.org/v2/{urllib.parse.quote(doi)}?email={args.email}")
            checked += 1
            if data:
                try:
                    j = json.loads(data)
                    rec["is_oa"] = bool(j.get("is_oa"))
                    loc = j.get("best_oa_location") or {}
                    url = loc.get("url_for_pdf") or loc.get("url")
                    if rec["is_oa"] and url:
                        rec["url"] = url
                        rec["host"] = loc.get("host_type")
                        rec["route"] = "oa"
                        oa += 1
                except Exception:
                    pass
            time.sleep(0.15)
        rep["retrieval"] = rec

    json.dump(state, open(args.state, "w"), indent=2, ensure_ascii=False)
    print(f"reports needing retrieval: {len(todo)}")
    print(f"queried Unpaywall (have a DOI): {checked}")
    print(f"free legal OA copy found: {oa}")
    print(f"still need a non-OA route (proxy/ILL/author/not-retrieved): {len(todo) - oa}")


if __name__ == "__main__":
    main()
