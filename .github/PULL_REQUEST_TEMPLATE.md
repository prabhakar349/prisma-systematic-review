## What does this change?

<!-- One or two sentences: what behavior changes, and why. -->

## Related issue

<!-- Fixes #___ / Relates to #___ (open one first for schema or workflow changes — see CONTRIBUTING.md) -->

## Checklist

- [ ] `cd tests && python3 -m unittest discover -v` passes
- [ ] `ruff check .` passes
- [ ] `mypy skills/prisma-systematic-review/scripts` passes (with and without `jsonschema` installed, if you touched `validate_state.py`)
- [ ] If this changes `generate_flow_diagram.py` or `generate_checklist.py` output, `fixtures/example-review/` was regenerated and the diff is included below
- [ ] If this changes the shape of `prisma-state.json`, both `state-schema.md` and `state-schema.json` were updated and the schema version was bumped

## Fixture diff (if applicable)

<!-- Paste the diff from regenerating fixtures/example-review/, or delete this section if not applicable. -->
