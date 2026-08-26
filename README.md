# PRISMA Systematic Review

A Claude Code plugin that runs a full PRISMA 2020 systematic literature review: eligibility criteria, multi-source search, deduplication, screening, data extraction, and the final flow diagram + checklist. Every decision is kept in one JSON file in your own repo, so the review is diffable and auditable instead of locked in a SaaS tool.

## What it does

- **Protocol** — elicits PICO/PECO framing, eligibility criteria, and search strategy; confirms with you before anything gets excluded on the strength of it. Criteria are versioned, so a mid-review change doesn't erase which version produced an earlier decision
- **Search** — runs your strategy across connected literature sources (PubMed, bioRxiv, Consensus, ClinicalTrials.gov, etc.) and logs each search as its own run: exact query, timestamp, result count
- **Deduplication** — auto-merges only on exact-identifier agreement (DOI, PMID, PMCID, registry ID, or exact title+first-author+year), using a proper union-find so transitive matches resolve consistently. Fuzzy title similarity is never auto-merged — it's surfaced as a candidate for you to confirm
- **Screening** — title/abstract and full-text screening against your criteria, with exclusion reasons tracked by category; large batches are delegated to a bundled subagent that only ever proposes decisions — it never writes to the review state directly, and every decision is an append-only event, so a later override doesn't erase the original call
- **Study linking** — distinguishes a *report* (one publication) from a *study* (the underlying research, which may have several reports); `link_study.py` groups multiple reports as one study so the included-studies count isn't inflated by counting a registry entry and its journal article as two studies
- **Extraction** — structured data capture per included study, including risk-of-bias fields
- **Reporting** — generates the PRISMA 2020 flow diagram (Mermaid + SVG) and a 27-item checklist status report, both computed directly from your recorded data, with extraction/risk-of-bias checks scoped to the studies actually included
- **Validation** — `validate_state.py` checks the state file against a real JSON Schema (or a dependency-free fallback) before you trust a batch of changes

## Install

```bash
git clone https://github.com/prabhakar349/prisma-systematic-review.git
cd prisma-systematic-review
./install.sh                                # personal install, available in every project
./install.sh --project /path/to/your/repo   # project install, shared with your team via that repo
```

Restart Claude Code afterward. To remove it: `./install.sh --uninstall` (add `--project <path>` to match how you installed it). Pass `--copy` to vendor a real copy instead of a symlink.

Alternative, via Claude Code's plugin manager:

```
/plugin marketplace add https://github.com/prabhakar349/prisma-systematic-review
/plugin install prisma-systematic-review
```

## Use

Once installed, just talk to Claude about your review in a normal Claude Code session — no slash command or special syntax needed. The skill triggers automatically whenever the conversation is clearly about running or writing up a systematic review, and Claude drives the workflow described in `SKILL.md` from there: asking you for eligibility criteria, running searches, dispatching screening, and so on.

**Starting a new review**, in the project directory where you want `prisma-state.json` to live:

> "I'm starting a systematic review on whether SGLT2 inhibitors reduce hospitalization in adults with heart failure, compared to standard care. Help me set up the PRISMA protocol and search PubMed and ClinicalTrials.gov."

Claude will walk you through PICO framing and eligibility criteria, confirm them with you, run the searches, and write everything to `prisma-state.json`.

**Mid-review, resuming later:**

> "Where did I leave off on the SGLT2 review?"

> "Screen the new batch of abstracts we just pulled from PubMed against the review criteria."

> "Dedupe the search results — I think there are some duplicates between the PubMed and registry pulls."

**Wrapping up:**

> "Generate the PRISMA flow diagram and checklist for this review."

You can also just ask directly for any single piece — "how many papers did we exclude and why", "link these two reports as the same trial", "add risk-of-bias data for the Smith 2022 study" — and Claude will use the relevant script or state-file update rather than running the whole pipeline. See `fixtures/example-review/` for a complete worked example of the state file and generated outputs.

## Limits

Built for a single reviewer or small team. It does not replace dual independent human screening where that's methodologically required (e.g. Cochrane reviews) — treat every automated decision as something to check, not trust blind. Search-run history covers tool-driven and manually-logged searches, but doesn't yet model incremental re-runs of the same search (e.g. a monthly alert re-query) as anything other than a fresh run.

## Structure

```
install.sh
skills/prisma-systematic-review/
  SKILL.md
  references/state-schema.md          — schema docs and design rationale
  references/state-schema.json        — machine-checkable JSON Schema
  references/prisma-2020-checklist.md
  scripts/dedupe.py
  scripts/link_study.py
  scripts/generate_flow_diagram.py
  scripts/generate_checklist.py
  scripts/validate_state.py
agents/prisma-abstract-screener.md
fixtures/example-review/
tests/                                — run with: cd tests && python3 -m unittest discover
```
