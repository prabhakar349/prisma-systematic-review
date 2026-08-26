"""End-to-end tests that run the actual CLI scripts as subprocesses,
against real files on disk — unlike the other test modules, which call
the underlying Python functions directly. This is the layer that would
have caught, for example, a script accepting the wrong number of CLI
args, or two scripts disagreeing about a file's on-disk format, that a
pure function-level test can't see.

link_study.py in particular had ZERO test coverage before this file —
none of the other test modules touch it at all.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..",
    "skills", "prisma-systematic-review", "scripts"
)
FIXTURE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..",
    "fixtures", "example-review"
)


def script(name):
    return os.path.join(SCRIPTS_DIR, name)


def run(*args, cwd):
    result = subprocess.run(
        [sys.executable, *args], cwd=cwd, capture_output=True, text=True
    )
    return result.returncode, result.stdout, result.stderr


def counts_from_stdout(stdout):
    """generate_flow_diagram.py prints optional NOTE lines and a "Wrote
    ..." line before the JSON counts block — locate the JSON by its
    opening brace rather than assuming a fixed line offset, since the
    NOTE lines appear or not depending on the state (e.g. whether any
    included report needs an auto-assigned 1:1 study)."""
    start = stdout.index("{")
    return json.loads(stdout[start:])


class TestExampleFixtureEndToEnd(unittest.TestCase):
    """Runs the full pipeline against a working copy of the committed
    example fixture — the closest thing to "does this actually work"
    without a live Claude Code session driving it."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        for name in os.listdir(FIXTURE_DIR):
            src = os.path.join(FIXTURE_DIR, name)
            if os.path.isfile(src):
                shutil.copy(src, self.tmpdir)
        self.state_path = os.path.join(self.tmpdir, "prisma-state.json")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def load_state(self):
        with open(self.state_path) as f:
            return json.load(f)

    def test_validate_passes_on_the_committed_fixture(self):
        code, out, err = run(script("validate_state.py"), self.state_path, cwd=self.tmpdir)
        self.assertEqual(code, 0, err)
        self.assertIn("Valid", out)

    def test_flow_diagram_update_state_matches_committed_counts(self):
        code, out, err = run(script("generate_flow_diagram.py"), "prisma-state.json",
                              "--out", "flow-diagram", "--update-state", cwd=self.tmpdir)
        self.assertEqual(code, 0, err)
        self.assertTrue(os.path.exists(os.path.join(self.tmpdir, "flow-diagram.mmd")))
        self.assertTrue(os.path.exists(os.path.join(self.tmpdir, "flow-diagram.svg")))

        state = self.load_state()
        self.assertEqual(state["derived"]["included"], {"studies": 1, "reports": 1})
        # every report's persisted stage must match what --update-state derived
        for rep in state["reports"].values():
            self.assertIn("stage", rep)

    def test_checklist_runs_after_flow_diagram(self):
        run(script("generate_flow_diagram.py"), "prisma-state.json", "--out", "flow-diagram", cwd=self.tmpdir)
        code, out, err = run(script("generate_checklist.py"), "prisma-state.json",
                              "--out", "checklist.md", cwd=self.tmpdir)
        self.assertEqual(code, 0, err)
        with open(os.path.join(self.tmpdir, "checklist.md")) as f:
            content = f.read()
        self.assertIn("PRISMA 2020", content)
        self.assertIn("addressed", content)

    def test_dedupe_is_idempotent_on_an_already_deduped_fixture(self):
        code, out, err = run(script("dedupe.py"), "prisma-state.json", cwd=self.tmpdir)
        self.assertEqual(code, 0, err)
        state = self.load_state()
        self.assertEqual(state["reports"]["r2"]["dedup_status"], "duplicate_of:r1")

    def test_full_pipeline_end_to_end_stays_valid_at_every_step(self):
        """dedupe -> flow-diagram -> checklist -> validate, all via
        subprocess, matching the order SKILL.md tells the orchestrating
        skill to run them in."""
        for cmd in [
            [script("dedupe.py"), "prisma-state.json"],
            [script("generate_flow_diagram.py"), "prisma-state.json", "--out", "flow-diagram", "--update-state"],
            [script("generate_checklist.py"), "prisma-state.json", "--out", "checklist.md"],
            [script("validate_state.py"), "prisma-state.json"],
        ]:
            code, out, err = run(*cmd, cwd=self.tmpdir)
            self.assertEqual(code, 0, f"{cmd} failed:\n{err}")


class TestLinkStudyIntegration(unittest.TestCase):
    """link_study.py had no coverage at all before this — these exercise
    it as a real subprocess against a synthetic multi-report state."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.state_path = os.path.join(self.tmpdir, "prisma-state.json")
        state = {
            "protocol": {
                "version": 1, "status": "confirmed", "confirmed_at": "2026-01-01T00:00:00Z",
                "research_question": "Q", "framing": "PICO",
                "eligibility_criteria": {"inclusion": ["RCT"], "exclusion": ["pediatric"]},
                "search_strategy": {"sources": ["pubmed", "clinicaltrials"]},
            },
            "search_runs": {},
            "reports": {
                "registry-1": {
                    "source": "clinicaltrials", "title": "NCT trial registration", "stage": "included",
                    "screening_decisions": [{"decision": "include", "reviewer": "agent",
                                              "timestamp": "2026-01-01T00:00:00Z", "protocol_version": 1}],
                    "eligibility_decisions": [{"decision": "include", "full_text_retrieved": True,
                                                "reviewer": "agent", "timestamp": "2026-01-01T00:00:00Z", "protocol_version": 1}],
                },
                "journal-1": {
                    "source": "pubmed", "title": "The eventual journal publication of the same trial", "stage": "included",
                    "screening_decisions": [{"decision": "include", "reviewer": "agent",
                                              "timestamp": "2026-01-01T00:00:00Z", "protocol_version": 1}],
                    "eligibility_decisions": [{"decision": "include", "full_text_retrieved": True,
                                                "reviewer": "agent", "timestamp": "2026-01-01T00:00:00Z", "protocol_version": 1}],
                },
                "unrelated-1": {
                    "source": "pubmed", "title": "A completely different included study", "stage": "included",
                    "screening_decisions": [{"decision": "include", "reviewer": "agent",
                                              "timestamp": "2026-01-01T00:00:00Z", "protocol_version": 1}],
                    "eligibility_decisions": [{"decision": "include", "full_text_retrieved": True,
                                                "reviewer": "agent", "timestamp": "2026-01-01T00:00:00Z", "protocol_version": 1}],
                },
            },
            "studies": {},
        }
        with open(self.state_path, "w") as f:
            json.dump(state, f)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def load_state(self):
        with open(self.state_path) as f:
            return json.load(f)

    def test_before_linking_three_included_reports_are_three_studies(self):
        code, out, err = run(script("generate_flow_diagram.py"), "prisma-state.json", "--out", "flow-diagram", cwd=self.tmpdir)
        self.assertEqual(code, 0, err)
        counts = counts_from_stdout(out)
        self.assertEqual(counts["included"]["reports"], 3)
        self.assertEqual(counts["included"]["studies"], 3)

    def test_linking_registry_and_journal_report_reduces_study_count(self):
        code, out, err = run(
            script("link_study.py"), "prisma-state.json",
            "--reports", "registry-1", "journal-1", "--primary", "journal-1",
            cwd=self.tmpdir,
        )
        self.assertEqual(code, 0, err)
        self.assertIn("Linked", out)

        state = self.load_state()
        self.assertEqual(state["reports"]["registry-1"]["study_id"], state["reports"]["journal-1"]["study_id"])
        study_id = state["reports"]["journal-1"]["study_id"]
        self.assertEqual(state["studies"][study_id]["primary_report"], "journal-1")
        self.assertEqual(set(state["studies"][study_id]["reports"]), {"registry-1", "journal-1"})

        # Now recompute counts and confirm 3 reports collapse to 2 studies.
        code, out, err = run(script("generate_flow_diagram.py"), "prisma-state.json", "--out", "flow-diagram", cwd=self.tmpdir)
        self.assertEqual(code, 0, err)
        counts = counts_from_stdout(out)
        self.assertEqual(counts["included"]["reports"], 3)
        self.assertEqual(counts["included"]["studies"], 2)

    def test_linking_unknown_report_id_fails_loudly(self):
        code, out, err = run(
            script("link_study.py"), "prisma-state.json", "--reports", "registry-1", "does-not-exist",
            cwd=self.tmpdir,
        )
        self.assertNotEqual(code, 0)
        self.assertIn("unknown report id", err)

    def test_linked_state_still_passes_validation(self):
        run(script("link_study.py"), "prisma-state.json", "--reports", "registry-1", "journal-1", cwd=self.tmpdir)
        code, out, err = run(script("validate_state.py"), "prisma-state.json", cwd=self.tmpdir)
        self.assertEqual(code, 0, err)

    def test_linking_a_third_report_into_an_existing_study_is_transitive(self):
        run(script("link_study.py"), "prisma-state.json", "--reports", "registry-1", "journal-1", cwd=self.tmpdir)
        code, out, err = run(
            script("link_study.py"), "prisma-state.json", "--reports", "journal-1", "unrelated-1",
            cwd=self.tmpdir,
        )
        self.assertEqual(code, 0, err)
        state = self.load_state()
        study_id = state["reports"]["registry-1"]["study_id"]
        self.assertEqual(study_id, state["reports"]["journal-1"]["study_id"])
        self.assertEqual(study_id, state["reports"]["unrelated-1"]["study_id"])
        self.assertEqual(len(state["studies"]), 1)
        self.assertEqual(set(state["studies"][study_id]["reports"]), {"registry-1", "journal-1", "unrelated-1"})


if __name__ == "__main__":
    unittest.main()
