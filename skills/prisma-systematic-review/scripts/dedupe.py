#!/usr/bin/env python3
"""Deduplicate records in a prisma-state.json file.

Matches on exact DOI first (normalized), then falls back to fuzzy
title+year matching for records missing a DOI. Marks duplicates with
dedup_status = "duplicate_of:<canonical_id>" rather than deleting them,
so the original record and the reasoning stay auditable.

Near-miss title pairs that fall between --near-miss-threshold and
--fuzzy-threshold are reported but NOT auto-merged, since a wrong merge
silently drops a real study — those need a human's eyes.
"""
import argparse
import json
import re
import sys
from difflib import SequenceMatcher
from itertools import combinations


def normalize_title(title):
    title = (title or "").lower()
    title = re.sub(r"[^a-z0-9\s]", "", title)
    return re.sub(r"\s+", " ", title).strip()


def normalize_doi(doi):
    if not doi:
        return None
    doi = doi.strip().lower()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    return doi or None


def title_similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()


def dedupe(state, fuzzy_threshold, near_miss_threshold):
    records = state.get("records", {})
    ids = list(records.keys())

    canonical_of = {rid: rid for rid in ids}
    near_misses = []

    # Pass 1: exact DOI match
    by_doi = {}
    for rid in ids:
        doi = normalize_doi(records[rid].get("doi"))
        if doi:
            by_doi.setdefault(doi, []).append(rid)
    for doi, group in by_doi.items():
        if len(group) > 1:
            canonical = sorted(group)[0]
            for rid in group:
                canonical_of[rid] = canonical

    # Pass 2: fuzzy title+year match, restricted to records still unmatched
    # by DOI (or without a DOI at all) — avoids re-flagging DOI-confirmed
    # duplicates as separate near-misses.
    unmatched = [rid for rid in ids if canonical_of[rid] == rid]
    titles = {rid: normalize_title(records[rid].get("title")) for rid in unmatched}
    years = {rid: records[rid].get("year") for rid in unmatched}

    for a, b in combinations(unmatched, 2):
        if not titles[a] or not titles[b]:
            continue
        if years[a] != years[b]:
            continue
        sim = title_similarity(titles[a], titles[b])
        if sim >= fuzzy_threshold:
            canonical = sorted([a, b])[0]
            other = b if canonical == a else a
            canonical_of[other] = canonical
        elif sim >= near_miss_threshold:
            near_misses.append({"a": a, "b": b, "similarity": round(sim, 3)})

    duplicates_removed = 0
    for rid in ids:
        canonical = canonical_of[rid]
        if canonical != rid:
            records[rid]["dedup_status"] = f"duplicate_of:{canonical}"
            duplicates_removed += 1
        else:
            records[rid].setdefault("dedup_status", "unique")

    state.setdefault("counts", {}).setdefault("identification", {})
    state["counts"]["identification"]["duplicates_removed"] = duplicates_removed

    return state, duplicates_removed, near_misses


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state_path", help="Path to prisma-state.json")
    parser.add_argument("--out", help="Output path (default: overwrite state_path)")
    parser.add_argument("--fuzzy-threshold", type=float, default=0.92,
                         help="Title similarity (0-1) above which same-year records auto-merge (default 0.92)")
    parser.add_argument("--near-miss-threshold", type=float, default=0.80,
                         help="Title similarity (0-1) above which a pair is reported for human review (default 0.80)")
    parser.add_argument("--dry-run", action="store_true", help="Report only, don't write output")
    args = parser.parse_args()

    with open(args.state_path) as f:
        state = json.load(f)

    state, duplicates_removed, near_misses = dedupe(
        state, args.fuzzy_threshold, args.near_miss_threshold
    )

    print(f"Duplicates found: {duplicates_removed}")
    if near_misses:
        print(f"\nNear-miss pairs needing human review ({len(near_misses)}):")
        for nm in near_misses:
            print(f"  {nm['a']}  <->  {nm['b']}   similarity={nm['similarity']}")
    else:
        print("No near-miss pairs in the review band.")

    if not args.dry_run:
        out_path = args.out or args.state_path
        with open(out_path, "w") as f:
            json.dump(state, f, indent=2)
        print(f"\nWrote updated state to {out_path}")


if __name__ == "__main__":
    sys.exit(main())
