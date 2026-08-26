#!/usr/bin/env python3
"""Deduplicate reports in a prisma-state.json file.

Same title + same year is NOT sufficient evidence two records are the
same report — "Effect of Drug X in Condition Y" and "...: a 5-year
follow-up" are legitimately different reports. So this script only
AUTO-MERGES on exact-identifier agreement (DOI, PMID, PMCID, a registry
ID, a source-specific ID, or an exact normalized title+first-author+year
match) and uses a union-find structure across all of those passes so
transitive relationships resolve consistently — if A and B share a DOI,
and B and C share a PMID, all three land in one cluster regardless of
which pass ran first, instead of a pairwise bug where A~B and B~C
doesn't imply A~C.

Fuzzy title similarity is NEVER auto-merged. It only produces candidate
pairs for a human to confirm (--confirm-pairs) or reject. This is
deliberately conservative: a wrongly-merged report silently drops a real
study from the review, which is a worse failure than one extra row a
human has to glance at.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from difflib import SequenceMatcher
from itertools import combinations
from typing import Any, Callable

Report = dict[str, Any]
State = dict[str, Any]
MergeLogEntry = dict[str, Any]
NearMiss = dict[str, Any]


def normalize_title(title: str | None) -> str:
    title = (title or "").lower()
    title = re.sub(r"[^a-z0-9\s]", "", title)
    return re.sub(r"\s+", " ", title).strip()


def normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    doi = doi.strip().lower()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    return doi or None


def normalize_id(value: object) -> str | None:
    if not value:
        return None
    return str(value).strip().lower() or None


def first_author(authors: list[str] | None) -> str | None:
    if not authors:
        return None
    return re.sub(r"[^a-z]", "", authors[0].lower())


class UnionFind:
    def __init__(self, ids: list[str]) -> None:
        self.parent: dict[str, str] = {i: i for i in ids}

    def find(self, x: str) -> str:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        # Deterministic: lexicographically smaller id becomes root.
        if ra < rb:
            self.parent[rb] = ra
        else:
            self.parent[ra] = rb


def group_and_union(uf: UnionFind, keyed_ids: dict[str, list[str]]) -> list[tuple[str, list[str]]]:
    """keyed_ids: dict of normalized-key -> [report_ids]. Unions every
    id sharing a key. Returns the list of keys that had >1 id, for
    reporting which identifier drove each merge."""
    merged_via: list[tuple[str, list[str]]] = []
    for key, ids in keyed_ids.items():
        if key and len(ids) > 1:
            for other in ids[1:]:
                uf.union(ids[0], other)
            merged_via.append((key, ids))
    return merged_via


def dedupe(
    state: State, near_miss_threshold: float, confirmed_pairs: list[tuple[str, str]]
) -> tuple[State, int, list[MergeLogEntry], list[NearMiss]]:
    reports: dict[str, Report] = state.get("reports", {})
    ids = list(reports.keys())
    uf = UnionFind(ids)
    merge_log: list[MergeLogEntry] = []

    def index_by(fn: Callable[[Report], str | None]) -> dict[str, list[str]]:
        buckets: dict[str, list[str]] = {}
        for rid in ids:
            key = fn(reports[rid])
            if key:
                buckets.setdefault(key, []).append(rid)
        return buckets

    # Priority order: strongest identifiers first. Each pass unions
    # within itself; order doesn't affect the final clustering because
    # union-find merges are commutative and transitive by construction.
    passes = [
        ("doi", lambda r: normalize_doi(r.get("identifiers", {}).get("doi") or r.get("doi"))),
        ("pmid", lambda r: normalize_id(r.get("identifiers", {}).get("pmid"))),
        ("pmcid", lambda r: normalize_id(r.get("identifiers", {}).get("pmcid"))),
        ("nct_id", lambda r: normalize_id(r.get("identifiers", {}).get("nct_id"))),
        ("source_id", lambda r: f"{r.get('source')}:{normalize_id(r.get('source_id'))}" if r.get("source_id") else None),
        ("title+author+year", lambda r: (
            f"{normalize_title(r.get('title'))}|{first_author(r.get('authors'))}|{r.get('year')}"
            if r.get("title") and r.get("authors") and r.get("year") else None
        )),
    ]

    for label, fn in passes:
        merged = group_and_union(uf, index_by(fn))
        for key, group in merged:
            merge_log.append({"matched_on": label, "key": key, "report_ids": group})

    # Human-confirmed pairs from a prior --confirm-pairs review.
    for a, b in confirmed_pairs:
        if a in uf.parent and b in uf.parent:
            uf.union(a, b)
            merge_log.append({"matched_on": "human_confirmed", "key": None, "report_ids": [a, b]})

    # Fuzzy title+year candidates — reporting only, never auto-merged.
    # Restricted to reports not already clustered together, so a
    # confirmed DOI match doesn't also show up as a "near miss".
    near_misses: list[NearMiss] = []
    titles = {rid: normalize_title(reports[rid].get("title")) for rid in ids}
    years = {rid: reports[rid].get("year") for rid in ids}
    for a, b in combinations(ids, 2):
        if uf.find(a) == uf.find(b):
            continue
        if not titles[a] or not titles[b] or years[a] != years[b]:
            continue
        sim = SequenceMatcher(None, titles[a], titles[b]).ratio()
        if sim >= near_miss_threshold:
            near_misses.append({"a": a, "b": b, "similarity": round(sim, 3)})

    duplicates_removed = 0
    for rid in ids:
        canonical = uf.find(rid)
        if canonical != rid:
            reports[rid]["dedup_status"] = f"duplicate_of:{canonical}"
            duplicates_removed += 1
        else:
            reports[rid]["dedup_status"] = "unique"

    return state, duplicates_removed, merge_log, near_misses


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state_path", help="Path to prisma-state.json")
    parser.add_argument("--out", help="Output path (default: overwrite state_path)")
    parser.add_argument("--near-miss-threshold", type=float, default=0.80,
                         help="Title similarity (0-1) above which a same-year pair is reported as a candidate (default 0.80)")
    parser.add_argument("--confirm-pairs", help="Path to a JSON file: a list of [report_id_a, report_id_b] pairs "
                                                  "a human has confirmed are the same report (e.g. from a prior "
                                                  "near-miss review). These get merged even though fuzzy matching alone never does.")
    parser.add_argument("--dry-run", action="store_true", help="Report only, don't write output")
    args = parser.parse_args()

    with open(args.state_path) as f:
        state = json.load(f)

    confirmed_pairs = []
    if args.confirm_pairs:
        with open(args.confirm_pairs) as f:
            confirmed_pairs = [tuple(pair) for pair in json.load(f)]

    state, duplicates_removed, merge_log, near_misses = dedupe(
        state, args.near_miss_threshold, confirmed_pairs
    )

    print(f"Duplicates found: {duplicates_removed}")
    if merge_log:
        print("\nMerges (auto, exact-identifier or confirmed):")
        for entry in merge_log:
            print(f"  [{entry['matched_on']}] {entry['report_ids']}")
    if near_misses:
        print(f"\nFuzzy near-miss pairs needing human review ({len(near_misses)}) — NOT merged:")
        for nm in near_misses:
            print(f"  {nm['a']}  <->  {nm['b']}   similarity={nm['similarity']}")
        print("\nTo merge any of these, write them to a JSON file as a list of [id_a, id_b] pairs "
              "and re-run with --confirm-pairs <file>.")
    else:
        print("\nNo fuzzy near-miss pairs in the review band.")

    if not args.dry_run:
        out_path = args.out or args.state_path
        with open(out_path, "w") as f:
            json.dump(state, f, indent=2)
        print(f"\nWrote updated state to {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
