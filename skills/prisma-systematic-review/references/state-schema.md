# `prisma-state.json` schema

The single source of truth for a review. Every script and every workflow step in `SKILL.md` reads and writes this file — never maintain review state anywhere else, or the flow diagram and checklist generators will silently work from stale data. The authoritative, machine-checkable version of this schema is `state-schema.json`; run `scripts/validate_state.py prisma-state.json` after any manual edit or before trusting a batch of agent output.

## Why decisions are event logs, not fields

A record like `"screening_decision": {"decision": "exclude", ...}` looks fine until a reviewer changes their mind. Overwrite that field with `include` and the fact that someone excluded it first — and why — is gone from the JSON, recoverable only by digging through git history if you happen to have committed at the right moment. For a document whose entire purpose is auditability, that's backwards.

So `screening_decisions` and `eligibility_decisions` are **append-only lists of decision events**, never single fields. The *current* decision is simply the last entry — nothing is ever removed or edited in place, a reversal is a new event appended after the old one. `scripts/generate_flow_diagram.py`'s `current_decision()` helper is the one place that resolves "last entry wins"; every script should call it rather than re-implementing the logic.

## Why protocol has a version number

Eligibility criteria drive every downstream exclusion (see `SKILL.md`), so a mid-review criteria change is not cosmetic — it can invalidate exclusions made under the old wording. Every decision event carries the `protocol_version` that was active when it was made. If you tighten a criterion from "adults with condition Y" to "adults ≥65 with condition Y" partway through, the 400 records already screened keep the version stamp that produced their decision, and you can answer "which criteria produced this exclusion?" instead of guessing. Bump `protocol.version` and re-confirm (`protocol.status: "confirmed"`, new `confirmed_at`) whenever criteria change; don't edit criteria in place without bumping it.

## Why reports and studies are separate

PRISMA distinguishes a **report** (one publication — a journal article, a conference abstract, a trial registry entry) from a **study** (the underlying research, which may have several reports). Treating every record as a study conflates "3 studies, 5 reports" into "5 studies" the moment one trial has a registry entry, a conference abstract, and a journal article. `reports` holds everything identified by search, one entry per distinct publication; `studies` groups reports that describe the same underlying research. `scripts/link_study.py` merges reports into a study explicitly (use it when you can tell two reports are the same trial); an included report with no `study_id` is treated as its own single-report study by default — the common case, since most included reports really are the only report of their study.

Do not confuse this with deduplication: `dedupe.py` removes literal duplicate *entries* of the same report (e.g. a paper indexed twice); `link_study.py` connects genuinely distinct reports that happen to describe one study. Neither report is a duplicate in the second case — both keep their own data.

## Schema

```jsonc
{
  "protocol": {
    "version": 1,
    "status": "draft | confirmed",
    "confirmed_at": "ISO 8601 timestamp or null",
    "research_question": "string",
    "framing": "PICO | PECO",
    "picos": {
      "population": "string", "intervention": "string", "exposure": "string",  // intervention XOR exposure by framing
      "comparator": "string", "outcome": "string", "study_design": "string"
    },
    "eligibility_criteria": {
      "inclusion": ["string", "..."],   // both inclusion and exclusion required non-empty
      "exclusion": ["string", "..."]
    },
    "search_strategy": {
      "sources": ["pubmed", "biorxiv", "consensus", "clinicaltrials", "..."],
      "manual_sources": ["hand-search of X reference lists", "..."]
    }
  },
  "search_runs": {
    "<search_run_id>": {
      "source": "pubmed | biorxiv | consensus | clinicaltrials | manual | other",
      "query": "exact query string used (omit for a manual/hand-search run)",
      "method": "e.g. 'citation chasing', 'reference list hand-search' — for manual runs",
      "searched_at": "ISO 8601 timestamp",
      "result_count": 1245,
      "retrieved_count": 1000,
      "notes": "string"
    }
  },
  "reports": {
    "<report_id>": {
      "search_run_id": "<search_run_id that identified this report>",
      "source": "pubmed | biorxiv | consensus | clinicaltrials | manual | other",
      "source_id": "whatever ID that source uses (PMID, DOI, NCT number, ...)",
      "identifiers": { "doi": "string|null", "pmid": "string|null", "pmcid": "string|null", "nct_id": "string|null" },
      "report_type": "primary_publication | follow_up | secondary_analysis | conference_abstract | registry_record | preprint | other",
      "title": "string",
      "authors": ["string", "..."],
      "year": 2024,
      "abstract": "string",
      "dedup_status": "unique | duplicate_of:<report_id>",
      "stage": "identified | screened | excluded | eligible_for_full_text | full_text_not_retrieved | full_text_excluded | included",
      "study_id": "set once this report is linked to a study (explicitly or by default at inclusion)",
      "screening_decisions": [
        {
          "decision": "include | exclude | maybe",
          "reason_category": "short controlled label — required unless decision is 'include'",
          "reason": "one sentence citing the specific criterion — required unless decision is 'include'",
          "reviewer": "agent | human:<name>",
          "timestamp": "ISO 8601 timestamp",
          "protocol_version": 1
        }
      ],
      "eligibility_decisions": [
        {
          "decision": "include | exclude | maybe",
          "full_text_retrieved": true,
          "reason_category": "...", "reason": "...",
          "reviewer": "agent | human:<name>",
          "timestamp": "ISO 8601 timestamp",
          "protocol_version": 1
        }
      ]
    }
  },
  "studies": {
    "<study_id>": {
      "reports": ["<report_id>", "..."],
      "primary_report": "<report_id>",
      "extraction": { "// review-specific fields, e.g.": "sample_size, outcome_result, ..." },
      "risk_of_bias": { "// per the instrument chosen (Cochrane RoB 2, ROBINS-I, ...)": "..." }
    }
  },
  "derived": {
    "// written by generate_flow_diagram.py — a cache, never hand-edit, never trust without regenerating": "..."
  }
}
```

## The stage state machine

`reports[].stage` should always be reachable by this path — there is no state that skips a stage or goes backward except by a new decision event superseding an old one:

```
identified
  -> screened
      -> excluded                       (screening_decisions current = exclude)
      -> eligible_for_full_text         (screening_decisions current = include or maybe)
          -> full_text_not_retrieved    (eligibility_decisions current.full_text_retrieved = false)
          -> full_text_excluded         (eligibility_decisions current = exclude)
          -> included                   (eligibility_decisions current = include or maybe)
```

`stage` is a derived convenience field, not a second source of truth — if it ever disagrees with what the decision events imply, trust the events and treat `stage` as stale (regenerate it, don't hand-edit it into agreement).

## Notes

- `record_id` / `report_id` keys should be stable and short — e.g. `<source>-<source_id>`. Every script and the screener agent reference reports by this key.
- `exclusion_reasons` tallies use `reason_category` verbatim as the grouping key — keep it a short, consistent controlled vocabulary within one review (always `"wrong population"`, never a mix of `"wrong population"` and `"population mismatch"`).
- `derived` is a cache — `scripts/generate_flow_diagram.py` recomputes it from `reports`/`studies` every run and overwrites this block. Don't hand-edit it expecting it to stick.
- Run `scripts/validate_state.py` before trusting any batch of writes, especially after merging agent-produced screening decisions — a typo'd `"decision": "incldue"` should fail loudly here, not silently corrupt a count three scripts later.
