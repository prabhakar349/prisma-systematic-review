# Contributing to prisma-systematic-review

Thanks for taking the time to contribute. This is a Claude Code plugin, and its
whole job is to keep a systematic review auditable — so precision in the
scripts, the state schema, and the docs matters more here than in most
projects. This guide covers how to propose changes and get them merged.

By participating, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).

## Ways to contribute

- **Bug reports** — something in `dedupe.py`, `link_study.py`,
  `generate_flow_diagram.py`, `generate_checklist.py`, or `validate_state.py`
  produces a wrong or inconsistent result. Open an issue with the input state
  (or a minimal reproduction) and the output you got vs. expected.
- **Feature requests** — use the "Feature request" issue template. For
  anything that changes the `prisma-state.json` schema or the screening/
  extraction workflow, please open an issue to discuss before writing code —
  see [Changing the state schema](#changing-the-state-schema-or-workflow)
  below.
- **Documentation** — fixes to `README.md`, `SKILL.md`, or the files under
  `skills/prisma-systematic-review/references/` are welcome as direct PRs.
- **Code** — bug fixes, new source integrations, performance improvements,
  test coverage.

## Development setup

The scripts themselves have zero runtime dependencies. Dev tooling (tests,
lint, type-checking) is separate:

```bash
git clone https://github.com/prabhakar349/prisma-systematic-review.git
cd prisma-systematic-review
pip install -r requirements-dev.txt
```

`jsonschema` is optional at runtime — `validate_state.py` falls back to a
dependency-free check without it — but it's in `requirements-dev.txt` so you
can exercise the full-schema path locally, the same as one leg of CI.

## Running the checks

Run all of these before opening a PR; CI runs the same steps on every push
and PR:

```bash
# Unit + integration tests (dedup, counts, checklist, state transitions,
# and real CLI subprocess runs including link_study.py)
cd tests && python3 -m unittest discover -v
cd ..

# Validate the example fixture against the schema
python3 skills/prisma-systematic-review/scripts/validate_state.py fixtures/example-review/prisma-state.json

# Lint
ruff check .

# Type check (run once with jsonschema installed, once without —
# validate_state.py's fallback path needs to type-check too)
mypy skills/prisma-systematic-review/scripts
pip uninstall -y jsonschema && mypy skills/prisma-systematic-review/scripts
pip install jsonschema
```

### If you change what the scripts generate

`fixtures/example-review/` holds committed, known-good output
(`flow-diagram.mmd`, `flow-diagram.svg`, `prisma-2020-checklist.md`) for the
example state file. CI regenerates these from `fixtures/example-review/prisma-state.json`
and diffs the result against the committed copies, so that fixture never
silently drifts from what the scripts actually produce. If your change
affects `generate_flow_diagram.py` or `generate_checklist.py`, regenerate and
commit the updated fixtures in the same PR:

```bash
rm -rf /tmp/example-review-check
cp -R fixtures/example-review /tmp/example-review-check
cd /tmp/example-review-check
python3 "$OLDPWD/skills/prisma-systematic-review/scripts/generate_flow_diagram.py" prisma-state.json --out flow-diagram
python3 "$OLDPWD/skills/prisma-systematic-review/scripts/generate_checklist.py" prisma-state.json --out prisma-2020-checklist.md
diff flow-diagram.mmd "$OLDPWD/fixtures/example-review/flow-diagram.mmd"
diff flow-diagram.svg "$OLDPWD/fixtures/example-review/flow-diagram.svg"
diff prisma-2020-checklist.md "$OLDPWD/fixtures/example-review/prisma-2020-checklist.md"
```

Then copy the regenerated files over the committed ones and include the diff
in your PR description so reviewers can see exactly what output changed and
why.

## Changing the state schema or workflow

`prisma-state.json` is the single source of truth a reviewer's whole audit
trail depends on, and decisions are recorded as append-only events on
purpose. Any change to its shape — new fields, changed semantics for an
existing field, a new decision/event type — needs:

1. An issue opened first, describing the change and why the current schema
   doesn't support it. This avoids wasted work if there's a simpler fix or a
   reason the schema is shaped the way it is.
2. Updates to **both** `skills/prisma-systematic-review/references/state-schema.md`
   (the rationale) and `state-schema.json` (the machine-checkable schema) —
   not just one.
3. A version bump per the versioning scheme already documented in
   `state-schema.md`, so a mid-review schema change doesn't silently
   reinterpret decisions made under an earlier version.
4. Test coverage in `tests/test_state_validation.py` and
   `tests/test_state_transitions.py` for the new shape.

## Style

- Lint/format: `ruff` (`pyproject.toml` — line length 130, `E`/`F`/`W`/`I`/`UP`
  rules; long generated-markdown/SVG lines are intentionally exempt from E501).
- Types: `mypy` in strict-ish mode (`warn_unused_ignores`,
  `warn_redundant_casts`, `check_untyped_defs`). `tests/` is excluded from
  type-checking but should still be reasonably typed.
- Target Python: 3.9+ (`target-version = "py39"`), since this runs inside
  whatever Python a user's Claude Code environment has.

## Submitting a pull request

1. Fork the repo and branch off `main`.
2. Keep the PR focused — one fix or feature per PR is much easier to review
   than a bundle of unrelated changes.
3. Add or update tests for any behavior change.
4. Make sure `ruff check .`, both `mypy` runs, and the full test suite pass
   locally.
5. Reference the related issue in the PR description if there is one, and
   describe *what changed in behavior*, not just what files changed —
   reviewers checking this against real review data care about the former.
6. One of the maintainers will review; expect follow-up questions on
   anything touching dedup logic, the state schema, or the checklist/flow
   diagram generation, since those are the parts other people's audit trails
   depend on.

## Questions and feedback

Not sure something is a bug, or want to float an idea before writing an
issue? See the "Questions & feedback" section in the README, or open a
[Discussion](../../discussions) if enabled on this repo — otherwise a regular
issue is fine, just say up front that it's a question rather than a bug
report.
