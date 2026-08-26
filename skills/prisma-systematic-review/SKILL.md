---
name: prisma-systematic-review
description: Guides and runs a full PRISMA 2020 systematic literature review or meta-analysis — defining PICO/PECO eligibility criteria, executing multi-source literature search (PubMed, bioRxiv, Consensus, ClinicalTrials.gov, or any other connected source), deduplicating records, screening titles/abstracts and full texts against criteria with exclusion-reason tracking, extracting structured data, and generating the PRISMA 2020 flow diagram and 27-item checklist. Use this whenever the user is planning, running, or writing up a systematic review or meta-analysis; mentions PRISMA, PICO, or PECO; asks to screen or deduplicate a batch of papers/abstracts; wants a literature review flow diagram; needs a PRISMA checklist for a manuscript; or asks things like "how many papers did we exclude and why", "help me screen these 400 abstracts", or "track my review protocol" — even when they don't say "PRISMA" explicitly.
---

# PRISMA 2020 Systematic Review

PRISMA 2020 is the reporting standard for systematic reviews and meta-analyses: a 27-item checklist plus a flow diagram tracking records through four stages — **Identification → Screening → Eligibility → Included**. This skill runs that whole pipeline and keeps every decision in a single git-trackable state file, so the review's audit trail is as inspectable as code.

## Why a state file, and why git

Systematic reviews are judged on reproducibility: a reader (or a peer reviewer) needs to see *why* a given study was excluded, not just that it was. Keep the entire review — protocol, every record, every decision and its stated reason — in one JSON file, `prisma-state.json`, in the user's project directory. If that directory is a git repo, each meaningful update (criteria finalized, a screening batch completed, eligibility decisions made) deserves its own commit — the diff *is* the audit trail. Never silently overwrite a decision; if a reviewer changes their mind about a record, record the change, don't erase the prior state.

See `references/state-schema.md` for the exact shape of `prisma-state.json`. Read an existing one before writing to it — most steps below are incremental updates, not fresh writes.

## The workflow

Work through these phases in order, but treat this as resumable — a real review spans weeks. Always check whether `prisma-state.json` already exists and what phase it's at before assuming you're starting fresh.

### 1. Protocol: eligibility criteria and search strategy

Do not invent eligibility criteria — they encode a domain judgment call only the researcher can make. Elicit, in plain conversation:

- **Research question**, framed as PICO (Population, Intervention, Comparator, Outcome) for intervention questions, or PECO (Exposure instead of Intervention) for etiology/risk questions — ask which fits, don't assume.
- **Inclusion and exclusion criteria** — study designs, populations, date range, language, publication status (peer-reviewed only, or preprints too).
- **Sources to search** — check which literature MCP tools are actually connected (PubMed, bioRxiv, Consensus, ClinicalTrials.gov are common) and ask about any the user needs that aren't (hand searches, grey literature, citation chasing) — those get recorded as manual counts later, since no tool call can produce them.

Write this into `prisma-state.json` under `protocol`. Show the user the criteria back in plain language and get explicit confirmation before searching — criteria drive every downstream exclusion, so a mistake here invalidates everything after it.

### 2. Search execution (Identification)

Run the search strategy across each confirmed source using its MCP tool, using the same query logic per source (adapt syntax to each API, keep the underlying concept identical). For each source, record in `protocol.search_strategy` the exact query used — PRISMA item #7 requires this be reproducible by someone else. As results come back, append each record to `records` in the state file with `source`, `source_id`, `title`, `authors`, `year`, `doi`, `abstract`, and `stage: "identified"`.

Ask the user for counts from any non-tool-accessible sources (register searches, citation searching, hand-searching reference lists) and add them directly to `counts.identification.other_methods` — don't fabricate a search you didn't run.

### 3. Deduplication

Run `scripts/dedupe.py` against the state file. It matches on exact DOI first, then falls back to fuzzy title+year matching for records missing a DOI (common with preprints and older records). Read the reported near-miss pairs it's unsure about — flag anything below its confidence threshold for the user to confirm rather than silently merging. Update `counts.identification.duplicates_removed` from the script's output.

### 4. Title/abstract screening

This is the highest-volume step and the one worth delegating. For batches larger than ~20 records, dispatch the **`prisma-abstract-screener`** agent (see `agents/prisma-abstract-screener.md`) in parallel chunks of 20-40 records each, passing it the eligibility criteria and each record's title+abstract. It returns `include` / `exclude` / `maybe` with a one-sentence rationale citing which criterion drove the call — never a bare verdict. For small batches, or when the user wants to screen personally, do it inline instead.

Treat every agent decision as provisional, not final: this accelerates a human reviewer, it doesn't replace one. Surface `maybe` calls and a sample of `exclude` calls (PRISMA and Cochrane guidance both expect some human verification of automated/single-reviewer screening) back to the user before locking them in. Write each decision to the record's `screening_decision` with `reviewer` set to `"agent"` or `"human:<name>"` so the provenance stays visible. Give the screener agent a short, fixed list of `reason_category` labels drawn from the exclusion criteria (e.g. `"wrong population"`, `"wrong study design"`) — PRISMA item #16b wants exclusion reasons reported as grouped counts, not a per-record wall of text, and that only works if categories stay consistent across the whole batch.

### 5. Full-text eligibility assessment

For every record that survived screening, note whether the full text was retrievable (`counts.eligibility.not_retrieved` for the ones that weren't — this is its own PRISMA-tracked number, not silently dropped). For retrieved texts, assess against the same criteria at full-text depth and record `eligibility_decision` with a reason. Keep this stage's exclusion-reason taxonomy distinct from the screening stage's — PRISMA reports them separately because full-text exclusions are typically more specific (e.g., "wrong outcome measure" vs. a title/abstract-stage "wrong population").

### 6. Data extraction

For every included study, extract the structured fields the user's synthesis needs (this varies by review — ask, don't assume a fixed schema beyond the PRISMA-required basics of design, population, sample size, and outcome data). Store extracted fields under each record's `extraction` object. If the user wants risk-of-bias assessment (PRISMA item #18), record that per-study too — it's a per-tool judgment call (e.g., Cochrane RoB 2, ROBINS-I) that needs the user to pick the instrument.

### 7. Flow diagram and checklist

Once counts are stable, run:

```
python3 scripts/generate_flow_diagram.py prisma-state.json --out flow-diagram --update-state
```

This recomputes every count directly from `records` (never trust hand-edited numbers in `counts` — they're a cache) and produces `flow-diagram.mmd` (Mermaid, renders inline in most markdown viewers and Claude artifacts) and `flow-diagram.svg` (standalone, matches the standard PRISMA 2020 four-box layout: Identification → Screening → Eligibility → Included, with exclusion counts branching off at each stage).

Then run:

```
python3 scripts/generate_checklist.py prisma-state.json --out prisma-2020-checklist.md
```

This walks the 27-item checklist (`references/prisma-2020-checklist.md` has the item list) and marks each item as addressed (citing where in the state file / manuscript it's satisfied) or flags it as still open. Report the open items to the user plainly — a checklist with gaps silently marked "done" defeats its purpose.

## Updating an existing review, not just starting one

If `prisma-state.json` already has records, the user is far more likely to be resuming than restarting. Read `counts` and the per-record `stage` fields to figure out where they left off, summarize that back to them ("You've screened 340 of 512 records; 38 are in eligibility review"), and pick up there rather than re-running earlier phases.
