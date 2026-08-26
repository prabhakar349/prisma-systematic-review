# Example review

A tiny (4-record) worked example of a complete review, used to sanity-check the scripts and to show what output to expect. `prisma-state.json` here has already been through every stage: search, dedup (one exact-DOI duplicate), title/abstract screening (two exclusions with reasons), full-text eligibility, and extraction for the one included study.

Regenerate the outputs from the state file to see the scripts in action:

```bash
python3 ../../skills/prisma-systematic-review/scripts/generate_flow_diagram.py prisma-state.json --out flow-diagram --update-state
python3 ../../skills/prisma-systematic-review/scripts/generate_checklist.py prisma-state.json --out prisma-2020-checklist.md
```
