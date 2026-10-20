#!/usr/bin/env python3
"""Bulk-ingest PubMed records into prisma-state.json as `identified` reports —
WITHOUT loading abstracts into the model's context (that is the whole point:
hundreds of abstracts belong in the state file, not in the conversation).

It executes the query stored on one or more `search_runs` entries via NCBI
E-utilities, fetches structured metadata, and appends one report per unique
PMID. Idempotent: a PMID already present in `reports` is skipped, so re-running
after a crash is safe.

Usage:
    ingest_pubmed.py STATE [--run RUN_ID ...] [--email you@example.org]

With no --run, every search_run whose `source` is "pubmed" and that has a
`query` but no `retrieved_count` yet is executed. Record the run first (see
SKILL.md step 2) so the exact query string is captured for PRISMA item #7.

Why this is a script and not an MCP call: the MCP full-text/search tools return
their payload into the model context, which is both slow and expensive at scale.
E-utilities over plain HTTP keeps the abstracts out of context entirely.
"""
import argparse, json, os, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
# PublicationTypes that mark a report as a secondary/non-primary publication.
SECONDARY_PT = {"Review", "Systematic Review", "Meta-Analysis",
                "Comment", "Editorial", "Letter"}


def get(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read()


def esearch(term, tool):
    q = urllib.parse.urlencode({**tool, "db": "pubmed", "term": term, "retmax": 10000})
    data = json.loads(get(f"{EUTILS}/esearch.fcgi?retmode=json&{q}"))["esearchresult"]
    return data["idlist"], int(data["count"])


def efetch(pmids, tool):
    """Fetch metadata for a list of PMIDs. Every lookup is scoped to the
    article's OWN elements — a descendant match (.//) would wrongly pull in
    reference-list and comment PMIDs/DOIs (this was a real bug; see git log)."""
    out = {}
    for i in range(0, len(pmids), 100):
        chunk = pmids[i:i + 100]
        q = urllib.parse.urlencode({**tool, "db": "pubmed", "id": ",".join(chunk), "retmode": "xml"})
        root = ET.fromstring(get(f"{EUTILS}/efetch.fcgi?{q}"))
        for art in root.findall("./PubmedArticle"):
            cite = art.find("./MedlineCitation")
            article = cite.find("./Article")
            pmid = cite.findtext("./PMID")
            at = article.find("./ArticleTitle")
            title = "".join(at.itertext()) if at is not None else ""
            parts = []
            for ab in article.findall("./Abstract/AbstractText"):
                label = ab.get("Label")
                txt = "".join(ab.itertext())
                parts.append(f"{label}: {txt}" if label else txt)
            abstract = "\n".join(p for p in parts if p)
            pubdate = article.find("./Journal/JournalIssue/PubDate")
            year = ""
            if pubdate is not None:
                year = pubdate.findtext("./Year") or (pubdate.findtext("./MedlineDate") or "")[:4]
            authors = []
            for a in article.findall("./AuthorList/Author"):
                ln, init = a.findtext("LastName"), a.findtext("Initials")
                if ln:
                    authors.append(f"{ln} {init}" if init else ln)
            doi = None
            for aid in art.findall("./PubmedData/ArticleIdList/ArticleId"):
                if aid.get("IdType") == "doi":
                    doi = aid.text
                    break
            if doi is None:
                for el in article.findall("./ELocationID"):
                    if el.get("EIdType") == "doi":
                        doi = el.text
                        break
            ptypes = [p.text for p in article.findall("./PublicationTypeList/PublicationType")]
            out[pmid] = {"title": title, "abstract": abstract, "year": year,
                         "authors": authors, "doi": doi, "ptypes": ptypes}
        time.sleep(0.34)  # NCBI: <=3 req/s without an API key
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("state")
    ap.add_argument("--run", action="append", default=[], metavar="RUN_ID",
                    help="search_run id(s) to execute; default = all unexecuted pubmed runs")
    ap.add_argument("--email", default=os.environ.get("NCBI_EMAIL", "review@researcher.org"),
                    help="contact for NCBI's courtesy param (env NCBI_EMAIL)")
    ap.add_argument("--tool-name", default="prisma-systematic-review")
    args = ap.parse_args()
    tool = {"tool": args.tool_name, "email": args.email}

    state = json.load(open(args.state))
    runs = state.setdefault("search_runs", {})
    reports = state.setdefault("reports", {})

    if args.run:
        targets = args.run
    else:
        targets = [rid for rid, r in runs.items()
                   if r.get("source") == "pubmed" and r.get("query")
                   and r.get("retrieved_count") is None]
    if not targets:
        sys.exit("No pubmed search_runs to execute. Record a run with a `query` "
                 "first (SKILL.md step 2), or pass --run RUN_ID.")

    pmid_run, counts = {}, {}
    for run_id in targets:
        run = runs.get(run_id)
        if not run or not run.get("query"):
            sys.exit(f"search_run '{run_id}' missing or has no `query`.")
        ids, count = esearch(run["query"], tool)
        counts[run_id] = (count, len(ids))
        for p in ids:
            pmid_run.setdefault(p, run_id)  # first run that found it wins
        time.sleep(0.34)

    all_pmids = list(pmid_run)
    new = [p for p in all_pmids if f"pubmed-{p}" not in reports]
    meta = efetch(new, tool) if new else {}

    added = 0
    for pmid in new:
        m = meta.get(pmid)
        if not m:
            continue
        rtype = "secondary_analysis" if SECONDARY_PT & set(m["ptypes"]) else "primary_publication"
        reports[f"pubmed-{pmid}"] = {
            "search_run_id": pmid_run[pmid],
            "source": "pubmed",
            "source_id": pmid,
            "identifiers": {"doi": m["doi"], "pmid": pmid, "pmcid": None, "nct_id": None},
            "report_type": rtype,
            "title": m["title"],
            "authors": m["authors"],
            "year": int(m["year"]) if m["year"].isdigit() else None,
            "abstract": m["abstract"],
            "dedup_status": "unique",
            "stage": "identified",
            "screening_decisions": [],
            "eligibility_decisions": [],
        }
        added += 1

    for run_id, (count, nids) in counts.items():
        runs[run_id]["retrieved_count"] = nids
        runs[run_id].setdefault("result_count", count)

    json.dump(state, open(args.state, "w"), indent=2, ensure_ascii=False)
    print("esearch counts (reported_total, retrieved_ids):")
    for r, c in counts.items():
        print(f"  {r}: {c[0]}, {c[1]}")
    print(f"unique PMIDs across runs: {len(all_pmids)}")
    print(f"new reports added: {added} | total reports now: {len(reports)}")


if __name__ == "__main__":
    main()
