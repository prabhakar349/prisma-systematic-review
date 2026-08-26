import unittest

import _paths  # noqa: F401
from validate_state import ValidationError, validate, validate_fallback


def valid_state():
    return {
        "protocol": {
            "version": 1, "status": "confirmed", "confirmed_at": "2026-01-01T00:00:00Z",
            "research_question": "Does X reduce Y?", "framing": "PICO",
            "eligibility_criteria": {"inclusion": ["RCT"], "exclusion": ["pediatric"]},
            "search_strategy": {"sources": ["pubmed"]},
        },
        "search_runs": {},
        "reports": {
            "a": {
                "source": "pubmed", "title": "T", "stage": "identified",
                "screening_decisions": [], "eligibility_decisions": [],
            }
        },
        "studies": {},
    }


class TestValidateFallback(unittest.TestCase):
    """Exercises the dependency-free fallback path directly, so the suite
    passes the same whether or not the `jsonschema` package is installed."""

    def test_valid_state_passes(self):
        validate_fallback(valid_state())  # should not raise

    def test_missing_top_level_key_fails(self):
        state = valid_state()
        del state["studies"]
        with self.assertRaises(ValidationError):
            validate_fallback(state)

    def test_unknown_decision_value_fails(self):
        state = valid_state()
        state["reports"]["a"]["screening_decisions"] = [{
            "decision": "incldue",  # typo, the exact bug this guards against
            "reviewer": "agent", "timestamp": "2026-01-01T00:00:00Z", "protocol_version": 1,
        }]
        with self.assertRaises(ValidationError) as ctx:
            validate_fallback(state)
        self.assertIn("decision", str(ctx.exception))

    def test_exclude_without_reason_fails(self):
        state = valid_state()
        state["reports"]["a"]["screening_decisions"] = [{
            "decision": "exclude",
            "reviewer": "agent", "timestamp": "2026-01-01T00:00:00Z", "protocol_version": 1,
            # reason_category/reason omitted
        }]
        with self.assertRaises(ValidationError) as ctx:
            validate_fallback(state)
        self.assertIn("reason", str(ctx.exception))

    def test_clean_include_without_reason_is_fine(self):
        state = valid_state()
        state["reports"]["a"]["screening_decisions"] = [{
            "decision": "include",
            "reviewer": "agent", "timestamp": "2026-01-01T00:00:00Z", "protocol_version": 1,
        }]
        validate_fallback(state)  # should not raise

    def test_bad_reviewer_format_fails(self):
        state = valid_state()
        state["reports"]["a"]["screening_decisions"] = [{
            "decision": "include",
            "reviewer": "pdigumarthi",  # missing the "human:" prefix
            "timestamp": "2026-01-01T00:00:00Z", "protocol_version": 1,
        }]
        with self.assertRaises(ValidationError):
            validate_fallback(state)

    def test_missing_protocol_version_fails(self):
        state = valid_state()
        state["protocol"]["version"] = "one"  # not an int
        with self.assertRaises(ValidationError):
            validate_fallback(state)

    def test_only_inclusion_criteria_fails(self):
        state = valid_state()
        state["protocol"]["eligibility_criteria"]["exclusion"] = []
        with self.assertRaises(ValidationError):
            validate_fallback(state)

    def test_invalid_stage_fails(self):
        state = valid_state()
        state["reports"]["a"]["stage"] = "screening"  # not a valid enum value (should be "screened")
        with self.assertRaises(ValidationError):
            validate_fallback(state)

    def test_study_with_no_reports_fails(self):
        state = valid_state()
        state["studies"]["study:empty"] = {"reports": []}
        with self.assertRaises(ValidationError):
            validate_fallback(state)


class TestValidateDispatch(unittest.TestCase):
    def test_validate_uses_real_schema_or_falls_back_without_crashing(self):
        # Whether or not the `jsonschema` package and the schema file are
        # available, validate() must not raise on a genuinely valid state.
        validate(valid_state())


if __name__ == "__main__":
    unittest.main()
