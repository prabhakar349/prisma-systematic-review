# Security Policy

## Scope

This is a Claude Code plugin: everything under `skills/prisma-systematic-review/scripts/`
runs locally, on your machine, reading and writing a JSON state file and
generating Markdown/SVG output. There is no server, no hosted service, and
no telemetry — the scripts themselves make no network calls (searches
against PubMed, bioRxiv, ClinicalTrials.gov, etc. happen through Claude
Code's own connected tools, not this repo's code).

Given that, the realistic attack surface is things like:

- A crafted `prisma-state.json` (or a value pulled from a search result —
  titles, abstracts, author names) causing unsafe behavior when a script
  processes it — path handling around `--out` arguments, unescaped content
  ending up in generated SVG/Markdown, or resource exhaustion on adversarial
  input.
- Vulnerabilities in the one optional dependency (`jsonschema`) or in dev
  tooling (`ruff`, `mypy`).
- `install.sh` doing something unsafe when installing or uninstalling the
  plugin.

**Out of scope:** vulnerabilities in the literature-source APIs themselves,
or in Claude Code / the Claude Agent SDK — please report those upstream, to
the API provider or to Anthropic respectively.

## Supported Versions

This project is pre-1.0 (currently v0.4.0 — see `.claude-plugin/plugin.json`)
with a single maintainer. There's no backport policy: security fixes land on
`main` and ship in the next release. Please make sure you're on the latest
version before reporting.

## Reporting a Vulnerability

Please **don't** open a public GitHub issue for a suspected vulnerability.

Use GitHub's private vulnerability reporting instead: go to the
[Security tab](../../security) of this repo and click **"Report a
vulnerability"**. That opens a private advisory only the maintainer (and
anyone you add) can see, with room to attach a proof-of-concept `prisma-state.json`
or reproduction script.

(If that option isn't visible, private vulnerability reporting hasn't been
turned on for this repo yet — open a minimal, non-sensitive issue asking for
it to be enabled, and full details can follow privately.)

What to expect:

- Acknowledgement within about 5 business days. This is a side project
  maintained by one person, so treat that as best-effort rather than an SLA.
- If confirmed, a fix and a new release, with credit to the reporter unless
  you'd rather stay anonymous.
- If declined (not a vulnerability, out of scope, or a duplicate), an
  explanation of why.
- Coordinated disclosure — please hold off on public disclosure until a fix
  has shipped, or by mutual agreement if a fix is taking longer than
  expected.
