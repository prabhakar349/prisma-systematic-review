# PRISMA Systematic Review

A Claude Code plugin that runs a full PRISMA 2020 systematic literature review: eligibility criteria, multi-source search, deduplication, screening, data extraction, and the final flow diagram + checklist. Every decision is kept in one JSON file in your own repo, so the review is diffable and auditable instead of locked in a SaaS tool.

## What it does

- **Protocol** — elicits PICO/PECO framing, eligibility criteria, and search strategy; confirms with you before anything gets excluded on the strength of it
- **Search** — runs your strategy across connected literature sources (PubMed, bioRxiv, Consensus, ClinicalTrials.gov, etc.) and logs the exact query used per source
- **Deduplication** — exact-DOI match plus fuzzy title+year matching; near-miss pairs are surfaced for you to confirm, not silently auto-merged
- **Screening** — title/abstract and full-text screening against your criteria, with exclusion reasons tracked by category; large batches are delegated to a bundled subagent, but every decision is provisional until you confirm it
- **Extraction** — structured data capture per included study, including risk-of-bias fields
- **Reporting** — generates the PRISMA 2020 flow diagram (Mermaid + SVG) and a 27-item checklist status report, both computed directly from your recorded data

## Install

```bash
git clone https://github.com/prabhakar349/prisma-systematic-review.git
cd prisma-systematic-review
./install.sh                                # personal install, available in every project
./install.sh --project /path/to/your/repo   # project install, shared with your team via that repo
```

Restart Claude Code afterward. To remove it: `./install.sh --uninstall` (add `--project <path>` to match how you installed it). Pass `--copy` to vendor a real copy instead of a symlink.

Alternative, via Claude Code's plugin manager:

```
/plugin marketplace add https://github.com/prabhakar349/prisma-systematic-review
/plugin install prisma-systematic-review
```

## Use

Once installed, just talk to Claude about your review — mention PRISMA, PICO/PECO, ask it to screen a batch of abstracts, deduplicate your search results, or generate a flow diagram, and the skill picks it up automatically. See `fixtures/example-review/` for a complete worked example.

## Limits

Built for a single reviewer or small team. It does not replace dual independent human screening where that's methodologically required (e.g. Cochrane reviews) — treat every automated decision as something to check, not trust blind. Multi-report-per-study consolidation isn't handled yet.

## Structure

```
install.sh
skills/prisma-systematic-review/
  SKILL.md
  references/state-schema.md
  references/prisma-2020-checklist.md
  scripts/dedupe.py
  scripts/generate_flow_diagram.py
  scripts/generate_checklist.py
agents/prisma-abstract-screener.md
fixtures/example-review/
```
