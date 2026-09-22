---
name: Bug report
about: Something produced a wrong or unexpected result
title: ''
labels: bug
assignees: ''

---

**What happened**
A clear description of the wrong or unexpected behavior (e.g. dedup merged two
studies that shouldn't have merged, the flow diagram counts don't add up, a
script raised an error).

**Which script/command**
e.g. `scripts/dedupe.py`, `scripts/generate_flow_diagram.py`, or "Claude ran
the screening step and..."

**Minimal reproduction**
If possible, a minimal `prisma-state.json` snippet (or attach the file) that
reproduces the issue. This is the fastest way to get a fix — the state file
never contains anything more sensitive than your review's own data, but feel
free to trim it to just the reports/studies involved.

**Expected behavior**
What you expected to happen instead.

**Environment**
- Plugin version (see `.claude-plugin/plugin.json` or your install date):
- Python version: (`python3 --version`)
- `jsonschema` installed? yes/no

**Additional context**
Anything else that might help — e.g. this only happens with registry entries,
or after linking studies, etc.
