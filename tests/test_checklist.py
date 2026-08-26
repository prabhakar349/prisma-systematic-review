import unittest

import _paths  # noqa: F401
from generate_checklist import evaluate, included_study_ids
from generate_flow_diagram import compute_counts


def event(decision, reason_category=None, reason=None, full_text_retrieved=None):
    e = {"decision": decision, "reviewer": "agent", "timestamp": "2026-01-01T00:00:00Z", "protocol_version": 1}
    if reason_category:
        e["reason_category"] = reason_category
    if reason:
        e["reason"] = reason
    if full_text_retrieved is not None:
        e["full_text_retrieved"] = full_text_retrieved
    return e


class TestEligibilityCriteriaCheck(unittest.TestCase):
    """Regression test: v0.1 used `inclusion OR exclusion`, so a criteria
    set with only ONE list populated was wrongly marked addressed."""

    def test_only_inclusion_present_is_not_addressed(self):
        state = {"protocol": {"eligibility_criteria": {"inclusion": ["RCT only"], "exclusion": []}}}
        ok, _ = evaluate("eligibility_criteria", state, {}, {}, {}, [])
        self.assertFalse(ok)

    def test_only_exclusion_present_is_not_addressed(self):
        state = {"protocol": {"eligibility_criteria": {"inclusion": [], "exclusion": ["pediatric"]}}}
        ok, _ = evaluate("eligibility_criteria", state, {}, {}, {}, [])
        self.assertFalse(ok)

    def test_both_present_is_addressed(self):
        state = {"protocol": {"eligibility_criteria": {"inclusion": ["RCT only"], "exclusion": ["pediatric"]}}}
        ok, _ = evaluate("eligibility_criteria", state, {}, {}, {}, [])
        self.assertTrue(ok)


class TestExtractionScopedToIncludedStudies(unittest.TestCase):
    """Regression test: v0.1 compared `with_extraction >= included` as raw
    counts, so an EXCLUDED report with extraction data could satisfy the
    check for an unrelated included study that had none."""

    def setUp(self):
        self.reports = {
            "included_no_extraction": {
                "source": "pubmed", "title": "T", "year": 2020, "dedup_status": "unique",
                "screening_decisions": [event("include")],
                "eligibility_decisions": [event("include", full_text_retrieved=True)],
            },
            "excluded_but_has_extraction_elsewhere": {
                "source": "pubmed", "title": "T2", "year": 2020, "dedup_status": "unique",
                "screening_decisions": [event("exclude", "wrong population", "pediatric")],
                "eligibility_decisions": [],
            },
        }
        self.studies = {
            # belongs to the excluded report's study id by coincidence of numbering — must not count
            "study:excluded_but_has_extraction_elsewhere": {
                "reports": ["excluded_but_has_extraction_elsewhere"], "extraction": {"sample_size": 100}
            },
        }

    def test_excluded_studys_extraction_does_not_satisfy_included_studys_requirement(self):
        counts, _ = compute_counts(self.reports, self.studies)
        ok, note = evaluate("extraction", {}, counts, self.reports, self.studies, [])
        self.assertFalse(ok)
        self.assertIn("study:included_no_extraction", note)

    def test_adding_extraction_to_the_actually_included_study_fixes_it(self):
        self.studies["study:included_no_extraction"] = {
            "reports": ["included_no_extraction"], "extraction": {"sample_size": 50}
        }
        counts, _ = compute_counts(self.reports, self.studies)
        ok, _ = evaluate("extraction", {}, counts, self.reports, self.studies, [])
        self.assertTrue(ok)

    def test_no_included_studies_is_not_addressed(self):
        counts, _ = compute_counts({}, {})
        ok, note = evaluate("extraction", {}, counts, {}, {}, [])
        self.assertFalse(ok)


class TestIncludedStudyIds(unittest.TestCase):
    def test_maybe_at_both_stages_counts_as_included(self):
        reports = {
            "a": {
                "source": "pubmed", "title": "T", "year": 2020, "dedup_status": "unique",
                "screening_decisions": [event("maybe", "unclear", "abstract vague on design")],
                "eligibility_decisions": [event("maybe", full_text_retrieved=True)],
            }
        }
        counts, _ = compute_counts(reports, {})
        ids = included_study_ids(reports, {}, counts)
        self.assertEqual(ids, {"study:a"})


if __name__ == "__main__":
    unittest.main()
