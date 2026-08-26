# `prisma-state.json` schema

The single source of truth for a review. Every script and every workflow step in `SKILL.md` reads and writes this file — never maintain review state anywhere else (a separate spreadsheet, a second JSON file) or the flow diagram and checklist generators will silently work from stale data.

```jsonc
{
  "protocol": {
    "research_question": "string",
    "framing": "PICO | PECO",
    "picos": {
      "population": "string",
      "intervention": "string",       // omit if framing is PECO
      "exposure": "string",           // omit if framing is PICO
      "comparator": "string",
      "outcome": "string",
      "study_design": "string"
    },
    "eligibility_criteria": {
      "inclusion": ["string", "..."],
      "exclusion": ["string", "..."]
    },
    "search_strategy": {
      "sources": ["pubmed", "biorxiv", "consensus", "clinicaltrials", "..."],
      "date_range": "string, e.g. 2015-01-01 to 2026-08-25",
      "queries": { "pubmed": "exact query string used", "...": "..." },
      "manual_sources": ["hand-search of X reference lists", "..."]
    }
  },
  "records": {
    "<record_id>": {
      "source": "pubmed | biorxiv | consensus | clinicaltrials | manual | other",
      "source_id": "PMID / DOI / NCT number / etc — whatever that source uses as its identifier",
      "title": "string",
      "authors": ["string", "..."],
      "year": 2024,
      "doi": "string or null",
      "abstract": "string",
      "dedup_status": "unique | duplicate_of:<record_id>",
      "stage": "identified | screening | eligibility | included | excluded",
      "screening_decision": {
        "decision": "include | exclude | maybe",
        "reason_category": "short controlled label, e.g. 'wrong population' — omit for a clean include",
        "reason": "string citing the specific criterion — omit for a clean include",
        "reviewer": "agent | human:<name>"
      },
      "eligibility_decision": {
        "full_text_retrieved": true,
        "decision": "include | exclude",
        "reason_category": "short controlled label — omit for a clean include",
        "reason": "string citing the specific criterion — omit for a clean include",
        "reviewer": "agent | human:<name>"
      },
      "extraction": {
        "// arbitrary, review-specific fields decided in step 6 of SKILL.md": "..."
      }
    }
  },
  "counts": {
    "identification": {
      "databases": 0,
      "registers": 0,
      "other_methods": 0,
      "duplicates_removed": 0
    },
    "screening": {
      "screened": 0,
      "excluded": 0,
      "exclusion_reasons": { "<reason category>": 0 }
    },
    "eligibility": {
      "sought": 0,
      "not_retrieved": 0,
      "assessed": 0,
      "excluded": 0,
      "exclusion_reasons": { "<reason category>": 0 }
    },
    "included": {
      "studies": 0,
      "reports": 0
    }
  }
}
```

## Notes

- `record_id` (the key under `records`) should be stable and short — e.g. a running integer or `<source>-<source_id>`. Every script and the screener agent reference records by this key.
- `counts` is derived data — it should always be recomputable from `records` by counting stages/decisions. Treat mismatches between `counts` and the actual record tally as a bug to fix, not something to paper over by editing `counts` directly.
- `exclusion_reasons` keys are free text but should stay consistent within one review (e.g. always `"wrong population"`, never a mix of `"wrong population"` and `"population mismatch"`) — the checklist and flow diagram generators group by these strings verbatim.
- `counts` in this file is a cache, not authoritative — `scripts/generate_flow_diagram.py` recomputes it from `records` every run (tallying `dedup_status`, `screening_decision`, and `eligibility_decision`) and overwrites this block. Don't hand-edit `counts` expecting it to stick.
