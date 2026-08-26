import unittest

import _paths  # noqa: F401
from generate_flow_diagram import derive_stage
from validate_state import check_stage_consistency, ValidationError


def event(decision, full_text_retrieved=None, reason_category=None, reason=None):
    e = {"decision": decision, "reviewer": "agent", "timestamp": "2026-01-01T00:00:00Z", "protocol_version": 1}
    if full_text_retrieved is not None:
        e["full_text_retrieved"] = full_text_retrieved
    if reason_category:
        e["reason_category"] = reason_category
        e["reason"] = reason
    return e


class TestDeriveStage(unittest.TestCase):
    """The full state-transition graph from references/state-schema.md,
    exercised branch by branch — this is the P1 'explicit state-transition
    validation' item."""

    def test_no_decisions_is_identified(self):
        self.assertEqual(derive_stage({"screening_decisions": [], "eligibility_decisions": []}), "identified")

    def test_screening_exclude_is_excluded(self):
        rep = {"screening_decisions": [event("exclude", reason_category="wrong population", reason="pediatric")]}
        self.assertEqual(derive_stage(rep), "excluded")

    def test_screening_include_with_no_eligibility_decision_is_eligible_for_full_text(self):
        rep = {"screening_decisions": [event("include")], "eligibility_decisions": []}
        self.assertEqual(derive_stage(rep), "eligible_for_full_text")

    def test_screening_maybe_with_no_eligibility_decision_is_eligible_for_full_text(self):
        rep = {"screening_decisions": [event("maybe", reason_category="unclear design", reason="abstract vague")],
               "eligibility_decisions": []}
        self.assertEqual(derive_stage(rep), "eligible_for_full_text")

    def test_full_text_not_retrieved(self):
        rep = {"screening_decisions": [event("include")],
               "eligibility_decisions": [event("exclude", full_text_retrieved=False)]}
        self.assertEqual(derive_stage(rep), "full_text_not_retrieved")

    def test_full_text_excluded(self):
        rep = {"screening_decisions": [event("include")],
               "eligibility_decisions": [event("exclude", full_text_retrieved=True, reason_category="wrong outcome", reason="no hospitalization data")]}
        self.assertEqual(derive_stage(rep), "full_text_excluded")

    def test_included_via_clean_include(self):
        rep = {"screening_decisions": [event("include")],
               "eligibility_decisions": [event("include", full_text_retrieved=True)]}
        self.assertEqual(derive_stage(rep), "included")

    def test_included_via_maybe_at_eligibility(self):
        rep = {"screening_decisions": [event("include")],
               "eligibility_decisions": [event("maybe", full_text_retrieved=True)]}
        self.assertEqual(derive_stage(rep), "included")

    def test_reversal_moves_stage_forward(self):
        """exclude -> include (a human overriding the agent) must move the
        derived stage forward, not stay stuck at 'excluded' — this is the
        whole point of decisions being an append-only log."""
        rep = {"screening_decisions": [
            event("exclude", reason_category="wrong population", reason="looked pediatric"),
            event("include"),
        ]}
        self.assertEqual(derive_stage(rep), "eligible_for_full_text")

    def test_duplicate_is_always_identified_regardless_of_decisions(self):
        """A report marked as a duplicate never progresses through the
        pipeline itself, even if it somehow accumulated decision events
        before being caught by dedupe."""
        rep = {
            "dedup_status": "duplicate_of:other",
            "screening_decisions": [event("include")],
            "eligibility_decisions": [event("include", full_text_retrieved=True)],
        }
        self.assertEqual(derive_stage(rep), "identified")


class TestStageConsistencyCheck(unittest.TestCase):
    def test_matching_stage_passes(self):
        state = {"reports": {"a": {"stage": "excluded",
                                    "screening_decisions": [event("exclude", reason_category="x", reason="y")],
                                    "eligibility_decisions": []}}}
        check_stage_consistency(state)  # should not raise

    def test_drifted_stage_fails_with_actionable_message(self):
        """The exact v0.1 bug: stage was written once as 'identified' and
        never advanced after a decision was appended."""
        state = {"reports": {"a": {"stage": "identified",
                                    "screening_decisions": [event("exclude", reason_category="x", reason="y")],
                                    "eligibility_decisions": []}}}
        with self.assertRaises(ValidationError) as ctx:
            check_stage_consistency(state)
        self.assertIn("drifted", str(ctx.exception))
        self.assertIn("--update-state", str(ctx.exception))

    def test_missing_stage_is_not_a_consistency_error(self):
        """A missing stage is a structural error the schema/fallback check
        already owns — check_stage_consistency shouldn't also complain
        about it, to keep error messages from one problem in one place."""
        state = {"reports": {"a": {"screening_decisions": [], "eligibility_decisions": []}}}
        check_stage_consistency(state)  # should not raise


if __name__ == "__main__":
    unittest.main()
