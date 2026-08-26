---
name: prisma-systematic-review
description: Guides and runs a full PRISMA 2020 systematic literature review or meta-analysis — defining PICO/PECO eligibility criteria, executing multi-source literature search (PubMed, bioRxiv, Consensus, ClinicalTrials.gov, or any other connected source), deduplicating records, screening titles/abstracts and full texts against criteria with exclusion-reason tracking, extracting structured data, and generating the PRISMA 2020 flow diagram and 27-item checklist. Use this whenever the user is planning, running, or writing up a systematic review or meta-analysis; mentions PRISMA, PICO, or PECO; asks to screen or deduplicate a batch of papers/abstracts; wants a literature review flow diagram; needs a PRISMA checklist for a manuscript; or asks things like "how many papers did we exclude and why", "help me screen these 400 abstracts", or "track my review protocol" — even when they don't say "PRISMA" explicitly.
---

# PRISMA 2020 Systematic Review

PRISMA 2020 is the reporting standard for systematic reviews and meta-analyses: a 27-item checklist plus a flow diagram tracking records through four stages — **Identification → Screening → Eligibility → Included**. This skill runs that whole pipeline and keeps every decision in a single git-trackable state file, so the review's audit trail is as inspectable as code.

## Why a state file, and why git

Systematic reviews are judged on reproducibility: a reader (or a peer reviewer) needs to see *why* a given study was excluded, not just that it was. Keep the entire review — protocol, every report, every decision and its stated reason — in one JSON file, `prisma-state.json`, in the user's project directory. If that directory is a git repo, each meaningful update (criteria finalized, a screening batch completed, eligibility decisions made) deserves its own commit — the diff *is* the audit trail.

Two things are non-negotiable about how this file gets mutated, because they're what make the audit trail actually trustworthy rather than just plausible-looking:

- **Decisions are events, never overwritten fields.** `screening_decisions` and `eligibility_decisions` are append-only lists. If a reviewer changes their mind, append a new decision — don't edit the old one. The current decision is always the *last* entry (see `references/state-schema.md`).
- **Validate before you write.** Run `scripts/validate_state.py prisma-state.json` after merging any batch of changes — especially agent-produced screening output — before treating the file as good. A typo'd decision value should fail loudly here, not silently corrupt a count three steps later.

See `references/state-schema.md` for the full schema, including why `reports` and `studies` are separate concepts (short version: one study can have several reports — a registry entry, a conference abstract, a journal article — and conflating them overcounts "studies included"). Read the existing state file before writing to it — most steps below are incremental updates, not fresh writes.

## The workflow

Work through these phases in order, but treat this as resumable — a real review spans weeks. Always check whether `prisma-state.json` already exists and what phase it's at before assuming you're starting fresh.

### 1. Protocol: eligibility criteria and search strategy

Do not invent eligibility criteria — they encode a domain judgment call only the researcher can make. Elicit, in plain conversation:

- **Research question**, framed as PICO (Population, Intervention, Comparator, Outcome) for intervention questions, or PECO (Exposure instead of Intervention) for etiology/risk questions — ask which fits, don't assume.
- **Inclusion and exclusion criteria** — study designs, populations, date range, language, publication status (peer-reviewed only, or preprints too). Both lists need at least one entry each; a criteria set with only inclusions (or only exclusions) isn't usable and `generate_checklist.py` will flag it as incomplete.
- **Sources to search** — check which literature MCP tools are actually connected (PubMed, bioRxiv, Consensus, ClinicalTrials.gov are common) and ask about any the user needs that aren't (hand searches, grey literature, citation chasing) — those become manual `search_runs` entries later, since no tool call can produce them.

Write this into `prisma-state.json` under `protocol` with `version: 1` and `status: "draft"`. Show the user the criteria back in plain language and get explicit confirmation — only then set `status: "confirmed"` and stamp `confirmed_at`. Criteria drive every downstream exclusion, so a mistake here invalidates everything after it.

**If criteria change mid-review** (the user tightens a population definition, adds an exclusion, etc.), don't edit `protocol` in place — increment `version`, re-confirm, and keep going. Every decision event already carries the `protocol_version` active when it was made, so later you can tell which exclusions happened under which criteria. Flag to the user that records screened under the old version may be worth revisiting, but don't auto-revisit them without asking — that could be a lot of re-work they may not want.

### 2. Search execution (Identification)

For each confirmed source, run the search and record a `search_runs` entry first — `source`, `query` (the exact string used; PRISMA item #7 requires this be reproducible by someone else), `searched_at`, and `result_count`. As results come back, append each one to `reports` with `source`, `source_id`, `identifiers` (DOI/PMID/PMCID/NCT as available), `title`, `authors`, `year`, `abstract`, `search_run_id` pointing back at the run, and `stage: "identified"` (this is the one and only place you set `stage` by hand — from here on it's derived automatically, see the note at the end of step 7).

For non-tool-accessible sources (register browsing, citation searching, hand-searching reference lists), still create a `search_runs` entry (`source: "manual"`, a `method` string, and the count the user gives you) rather than a tool-driven one — don't fabricate a search you didn't run, but do record that it happened.

### 3. Deduplication

Run `scripts/dedupe.py` against the state file. It auto-merges only on exact-identifier agreement (DOI, PMID, PMCID, registry ID, or an exact title+first-author+year match) — same title and year alone is *not* enough evidence two reports are the same (a follow-up publication or subgroup analysis can share both). Fuzzy title similarity below that bar is reported as a candidate pair, never auto-merged; if the user confirms a pair is really the same report, write it to a small JSON file of `[id_a, id_b]` pairs and re-run with `--confirm-pairs`.

Don't confuse this with study-linking (step 6a) — dedupe removes literal duplicate *entries* of one report; it doesn't decide whether two distinct reports describe the same study.

### 4. Title/abstract screening

This is the highest-volume step and the one worth delegating. For batches larger than ~20 reports, dispatch the **`prisma-abstract-screener`** agent (see `agents/prisma-abstract-screener.md`) in parallel chunks of 20-40, passing it the eligibility criteria, a fixed list of `reason_category` labels to choose from, and each report's title+abstract. It writes its decisions to its own output file — **never to `prisma-state.json` directly** — and you (the orchestrator) are the only one who applies them. Treat the agent purely as an advisory computation: read its output, validate it looks sane, then append each decision as a new event to the corresponding report's `screening_decisions`, with `reviewer: "agent"`, a `timestamp`, and the current `protocol_version`. For small batches, or when the user wants to screen personally, do it inline instead, with `reviewer: "human:<name>"`.

Treat every agent decision as provisional, not final: this accelerates a human reviewer, it doesn't replace one. Surface `maybe` calls and a sample of `exclude` calls (PRISMA and Cochrane guidance both expect some human verification of automated/single-reviewer screening) back to the user before treating them as settled — if the user overrides one, append a *new* decision event on top rather than editing the agent's, so both are visible in the log.

### 5. Full-text eligibility assessment

For every report that survived screening (current screening decision is `include` or `maybe`), note whether the full text was retrievable — append an eligibility decision event with `full_text_retrieved: false` for the ones that weren't (this is its own PRISMA-tracked number, not silently dropped). For retrieved texts, assess against the same criteria at full-text depth and append an eligibility decision with a reason. Keep this stage's `reason_category` vocabulary distinct from the screening stage's — PRISMA reports them separately because full-text exclusions are typically more specific (e.g., "wrong outcome measure" vs. a title/abstract-stage "wrong population").

### 6. Data extraction

**6a. Link reports into studies first.** If any included reports are different publications of the same underlying trial (a registry entry plus its eventual journal article, a conference abstract plus the full publication), run `scripts/link_study.py prisma-state.json --reports <id1> <id2> ...` to group them — ask the user if you're not sure two reports are the same study, don't guess. An included report with no explicit link is treated as its own single-report study by default, which is correct for the common case.

**6b. Extract.** For every included study (not report — extract once per study, on its primary report unless the user needs per-report detail), capture the structured fields the synthesis needs — ask, don't assume a fixed schema beyond the PRISMA-required basics of design, population, sample size, and outcome data. Store it under `studies.<study_id>.extraction`. If the user wants risk-of-bias assessment (PRISMA item #18), record that under `studies.<study_id>.risk_of_bias` — the instrument (Cochrane RoB 2, ROBINS-I, etc.) is the user's judgment call, not yours.

### 7. Flow diagram and checklist

Once decisions are stable, run:

```
python3 scripts/generate_flow_diagram.py prisma-state.json --out flow-diagram --update-state
```

This recomputes every count directly from `reports`/`studies` (never trust the cached `derived` block) and produces `flow-diagram.mmd` (Mermaid) and `flow-diagram.svg`, matching the standard PRISMA 2020 four-box layout. `--update-state` also persists any 1:1 study auto-assignments for included reports that were never explicitly linked.

Then run:

```
python3 scripts/generate_checklist.py prisma-state.json --out prisma-2020-checklist.md
```

This walks the 27-item checklist (`references/prisma-2020-checklist.md` has the item list) and marks each item addressed — citing what in the state file satisfies it — or flags it open. Extraction and risk-of-bias items are checked against the actual set of included *studies*, not a raw count, so a study that's missing extraction data shows up by name. Report the open items to the user plainly — a checklist with gaps silently marked "done" defeats its purpose.

**Never hand-set or hand-advance `stage` on a report beyond its initial `"identified"` value.** `--update-state` recomputes it for every report from its decision history (`generate_flow_diagram.derive_stage`) and writes the result back — that's the only path `stage` should ever change through. `validate_state.py` checks stored `stage` against what the decisions imply and fails loudly on drift, precisely because a hand-maintained `stage` field is guaranteed to go stale the moment someone forgets to update it after a decision.

## Updating an existing review, not just starting one

If `prisma-state.json` already has reports, the user is far more likely to be resuming than restarting. Run the flow-diagram script (it's read-only without `--update-state`) to see current counts and pending totals, summarize that back to them ("You've screened 340 of 512 reports; 38 are in eligibility review"), and pick up there rather than re-running earlier phases.
