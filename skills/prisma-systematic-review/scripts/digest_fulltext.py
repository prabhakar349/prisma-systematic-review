#!/usr/bin/env python3
"""Compress a full-text payload into a few review-relevant sentences per article,
so the model never has to read whole papers into context.

Input is a JSON file holding articles — either an MCP `get_full_text_article`
result ({"articles": [{doi, title, abstract, full_text}, ...]}) or a plain list
of such objects. For each article it prints: the identifiers, any matched
domain *entities*, the first few cohort/methods sentences, and the outcome
sentences that carry numbers. That digest is what you paste into an extraction
batch (or hand to the prisma-data-extractor agent) — not the full text.

The domain vocabulary is per-review, so pass a lexicon:

    digest_fulltext.py FULLTEXT.json [--lexicon lexicon.json]

lexicon.json (all keys optional; these override the generic defaults):
    {
      "entities": ["DNAH\\d+", "CFAP\\d+", "FSIP2"],   # regexes for what you tally
      "outcome":  ["live birth", "ICSI", "pregnan"],   # outcome-signal regexes
      "cohort":   ["cohort of", "we enrolled"]          # design/sample regexes
    }

With no lexicon it falls back to generic systematic-review cues (sample size,
enrollment, p-values, effect sizes) and reports no entities — fine for a quick
look, but a real review should supply its own `entities`/`outcome` terms.
"""
import argparse, json, re, sys

# Generic fallbacks — intentionally domain-neutral.
DEFAULT_OUTCOME = [r"\boutcome", r"\bprimary endpoint", r"\bsecondary endpoint",
                   r"\bmortalit", r"\bsurviv", r"\bresponse rate", r"\bremission",
                   r"\bodds ratio", r"\bhazard ratio", r"\bconfidence interval", r"\bp\s*[<=]"]
DEFAULT_COHORT = [r"cohort of", r"a total of", r"we recruited", r"we enrolled",
                  r"enrolled", r"patients? with", r"participants", r"sample size",
                  r"retrospective", r"prospective", r"randomi[sz]ed"]


def build(patterns):
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.I) if patterns else None


def sents(t):
    return re.split(r"(?<=[.!?])\s+", t)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("fulltext")
    ap.add_argument("--lexicon", help="JSON with entities/outcome/cohort regex lists")
    ap.add_argument("--max-outcome", type=int, default=8)
    ap.add_argument("--max-cohort", type=int, default=3)
    args = ap.parse_args()

    lex = json.load(open(args.lexicon)) if args.lexicon else {}
    ent_re = build(lex.get("entities"))
    out_re = build(lex.get("outcome") or DEFAULT_OUTCOME)
    coh_re = build(lex.get("cohort") or DEFAULT_COHORT)

    data = json.load(open(args.fulltext))
    articles = data.get("articles", data) if isinstance(data, dict) else data
    if not isinstance(articles, list):
        sys.exit("Expected an 'articles' list or a top-level list of article objects.")

    for a in articles:
        ft = a.get("full_text") or ""
        ab = a.get("abstract") or ""
        body = ft or ab
        print("==== DOI", a.get("doi"), "| PMID", a.get("pmid"), "| ft_len", len(ft))
        print("TITLE:", (a.get("title") or "")[:120])
        if ent_re:
            ents = sorted({m.group(0) for m in ent_re.finditer(ft + " " + ab)})
            print("ENTITIES:", ", ".join(ents) or "(none matched)")
        cohort = [s.strip() for s in sents(body) if coh_re and coh_re.search(s)][:args.max_cohort]
        outc = [s.strip() for s in sents(body) if out_re and out_re.search(s)]
        outc_num = [s for s in outc if re.search(r"\d", s)][:args.max_outcome]
        print("COHORT:", " || ".join(c[:220] for c in cohort)[:700])
        print("OUTCOME:", " || ".join(o[:240] for o in outc_num)[:1600])
        if not ft:
            print("  (NOTE: no full text returned; digest is from abstract only)")
        print()


if __name__ == "__main__":
    main()
