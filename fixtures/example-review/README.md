# Example review

A tiny (4-report) worked example of a complete review, used to sanity-check the scripts and to show what output to expect. `prisma-state.json` here has already been through every stage: two search runs, dedup (one exact-DOI duplicate), title/abstract screening (two exclusions with reasons, as decision events), full-text eligibility, and extraction + risk-of-bias for the one included study. This is also the fixture CI regenerates and diffs against on every push, so it stays in sync with the scripts.

Regenerate the outputs from the state file to see the scripts in action:

```bash
python3 ../../skills/prisma-systematic-review/scripts/validate_state.py prisma-state.json
python3 ../../skills/prisma-systematic-review/scripts/generate_flow_diagram.py prisma-state.json --out flow-diagram --update-state
python3 ../../skills/prisma-systematic-review/scripts/generate_checklist.py prisma-state.json --out prisma-2020-checklist.md
```
