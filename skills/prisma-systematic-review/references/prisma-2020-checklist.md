# PRISMA 2020 checklist — item map

The 27-item PRISMA 2020 checklist, organized by manuscript section. `scripts/generate_checklist.py` uses the `auto_check` field to decide what it can verify directly from `prisma-state.json`; everything else it flags as needing the author's own manuscript text, since a checklist item being "satisfied" often means a sentence exists in the paper, not a field in a JSON file.

| # | Section | Item | auto_check |
|---|---------|------|------------|
| 1 | Title | Identify the report as a systematic review | manual |
| 2 | Abstract | Structured summary covering objectives, methods, results, and funding | manual |
| 3 | Introduction | Rationale for the review in the context of existing knowledge | manual |
| 4 | Introduction | Explicit objectives / research question | protocol.research_question |
| 5 | Methods | Eligibility criteria used to decide inclusion | protocol.eligibility_criteria |
| 6 | Methods | Information sources searched, and last-searched date | protocol.search_strategy.sources |
| 7 | Methods | Full search strategy for at least one database, reproducible | protocol.search_strategy.queries |
| 8 | Methods | Study selection process (how many reviewers, independently or not) | manual |
| 9 | Methods | Data collection process from each included study | manual |
| 10a | Methods | List of outcomes/data items sought | manual |
| 10b | Methods | Other variables collected (funding sources, study characteristics) | manual |
| 11 | Methods | Risk-of-bias assessment method, at what level | manual |
| 12 | Methods | Effect measures used for each outcome | manual |
| 13a-f | Methods | Synthesis methods (grouping, tabulation, statistical synthesis, heterogeneity, sensitivity analyses) | manual |
| 14 | Methods | Reporting bias assessment methods (e.g. publication bias) | manual |
| 15 | Methods | Certainty/quality-of-evidence assessment method | manual |
| 16a | Results | Study selection flow diagram with counts at each stage | flow_diagram |
| 16b | Results | Studies excluded with reasons, at least at full-text stage | eligibility.exclusion_reasons |
| 17 | Results | Characteristics of each included study | records[].extraction |
| 18 | Results | Risk-of-bias results for each included study | records[].extraction (risk_of_bias) |
| 19 | Results | Results for all outcomes, for each study | records[].extraction |
| 20a-d | Results | Synthesis results (study/effect count, heterogeneity, sensitivity) | manual |
| 21 | Results | Assessment of reporting bias | manual |
| 22 | Results | Certainty of evidence for each outcome | manual |
| 23a-d | Discussion | Interpretation, limitations of the evidence and of the review process, implications | manual |
| 24a | Other info | Registration (name and registration number) | manual |
| 24b | Other info | Where the protocol can be accessed | manual |
| 24c | Other info | Amendments to registered/published protocol | manual |
| 25 | Other info | Funding sources for the review itself | manual |
| 26 | Other info | Competing interests of review authors | manual |
| 27 | Other info | Availability of data, code, and materials from the review | manual |

Items marked `manual` genuinely need the researcher's own judgment or manuscript prose — the generator flags them as open rather than guessing, since a checklist that silently marks subjective items "done" defeats the point of the checklist.
