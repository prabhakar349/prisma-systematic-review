import unittest

import _paths  # noqa: F401
from generate_flow_diagram import compute_counts, current_decision


def event(decision, reason_category=None, reason=None, reviewer="agent",
          timestamp="2026-01-01T00:00:00Z", protocol_version=1, full_text_retrieved=None):
    e = {"decision": decision, "reviewer": reviewer, "timestamp": timestamp, "protocol_version": protocol_version}
    if reason_category:
        e["reason_category"] = reason_category
    if reason:
        e["reason"] = reason
    if full_text_retrieved is not None:
        e["full_text_retrieved"] = full_text_retrieved
    return e


def report(source="pubmed", title="T", year=2020, screening=None, eligibility=None,
           dedup_status="unique", study_id=None):
    r = {"source": source, "title": title, "year": year, "dedup_status": dedup_status,
         "screening_decisions": screening or [], "eligibility_decisions": eligibility or []}
    if study_id:
        r["study_id"] = study_id
    return r


class TestCurrentDecision(unittest.TestCase):
    def test_no_events_is_none(self):
        self.assertIsNone(current_decision([]))

    def test_last_event_wins_after_reversal(self):
        events = [event("exclude", "wrong population", "adults only"), event("include")]
        self.assertEqual(current_decision(events)["decision"], "include")


class TestComputeCounts(unittest.TestCase):
    def test_zero_reports(self):
        counts, auto_studies = compute_counts({}, {})
        self.assertEqual(counts["screening"]["screened"], 0)
        self.assertEqual(counts["included"]["studies"], 0)
        self.assertEqual(auto_studies, {})

    def test_duplicate_reports_excluded_from_identification_pipeline_but_counted_in_identification(self):
        reports = {
            "a": report(dedup_status="unique"),
            "b": report(dedup_status="duplicate_of:a"),
        }
        counts, _ = compute_counts(reports, {})
        self.assertEqual(counts["identification"]["databases"], 2)  # both counted at identification
        self.assertEqual(counts["identification"]["duplicates_removed"], 1)
        self.assertEqual(counts["pending"]["awaiting_screening"], 1)  # only "a" is unique and unscreened

    def test_maybe_passes_forward_to_eligibility(self):
        reports = {"a": report(screening=[event("maybe", "unclear design", "abstract silent on RCT vs. cohort")])}
        counts, _ = compute_counts(reports, {})
        self.assertEqual(counts["screening"]["excluded"], 0)
        self.assertEqual(counts["eligibility"]["sought"], 1)

    def test_exclude_does_not_pass_forward(self):
        reports = {"a": report(screening=[event("exclude", "wrong population", "pediatric cohort")])}
        counts, _ = compute_counts(reports, {})
        self.assertEqual(counts["screening"]["excluded"], 1)
        self.assertEqual(counts["eligibility"]["sought"], 0)
        self.assertEqual(counts["screening"]["exclusion_reasons"], {"wrong population": 1})

    def test_full_text_not_retrieved_is_a_distinct_bucket(self):
        reports = {
            "a": report(
                screening=[event("include")],
                eligibility=[event("exclude", full_text_retrieved=False)],  # decision field ignored when not retrieved
            )
        }
        counts, _ = compute_counts(reports, {})
        self.assertEqual(counts["eligibility"]["not_retrieved"], 1)
        self.assertEqual(counts["eligibility"]["assessed"], 0)
        self.assertEqual(counts["included"]["reports"], 0)

    def test_reversal_via_new_event_changes_current_outcome(self):
        reports = {
            "a": report(screening=[
                event("exclude", "wrong population", "looked pediatric at first glance"),
                event("include", reviewer="human:reviewer1"),  # reviewer overrides the agent
            ])
        }
        counts, _ = compute_counts(reports, {})
        self.assertEqual(counts["screening"]["excluded"], 0)
        self.assertEqual(counts["eligibility"]["sought"], 1)

    def test_included_study_with_multiple_reports_counts_as_one_study_many_reports(self):
        reports = {
            "a": report(screening=[event("include")], eligibility=[event("include", full_text_retrieved=True)], study_id="study-42"),
            "b": report(screening=[event("include")], eligibility=[event("include", full_text_retrieved=True)], study_id="study-42"),
            "c": report(screening=[event("include")], eligibility=[event("include", full_text_retrieved=True)]),  # separate, unlinked study
        }
        counts, auto_studies = compute_counts(reports, {})
        self.assertEqual(counts["included"]["reports"], 3)
        self.assertEqual(counts["included"]["studies"], 2)  # study-42 (2 reports) + c's own 1:1 study
        self.assertIn("study:c", auto_studies)
        self.assertNotIn("study:a", auto_studies)  # already explicitly linked, no auto-assignment needed


if __name__ == "__main__":
    unittest.main()
