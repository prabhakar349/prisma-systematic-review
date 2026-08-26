import unittest

import _paths  # noqa: F401
from dedupe import dedupe


def report(title, year, doi=None, authors=None, source="pubmed", **identifiers):
    r = {"title": title, "year": year, "authors": authors or ["Smith J"], "source": source}
    if doi is not None:
        r["identifiers"] = {"doi": doi, **identifiers}
    elif identifiers:
        r["identifiers"] = identifiers
    return r


class TestDedupe(unittest.TestCase):
    def run_dedupe(self, reports, near_miss_threshold=0.80, confirmed_pairs=None):
        state = {"reports": reports}
        state, removed, merge_log, near_misses = dedupe(state, near_miss_threshold, confirmed_pairs or [])
        return state["reports"], removed, merge_log, near_misses

    def test_zero_records(self):
        reports, removed, merge_log, near_misses = self.run_dedupe({})
        self.assertEqual(reports, {})
        self.assertEqual(removed, 0)

    def test_one_record(self):
        reports, removed, _, _ = self.run_dedupe({"a": report("Study A", 2020, doi="10.1/a")})
        self.assertEqual(removed, 0)
        self.assertEqual(reports["a"]["dedup_status"], "unique")

    def test_exact_doi_duplicate(self):
        reports, removed, merge_log, _ = self.run_dedupe({
            "a": report("Study A", 2020, doi="10.1/x"),
            "b": report("Study A (mirror)", 2020, doi="10.1/X"),  # case-insensitive match
        })
        self.assertEqual(removed, 1)
        self.assertEqual(reports["b"]["dedup_status"], "duplicate_of:a")
        self.assertEqual(reports["a"]["dedup_status"], "unique")
        self.assertTrue(any(m["matched_on"] == "doi" for m in merge_log))

    def test_doi_missing_falls_back_to_title_author_year(self):
        reports, removed, merge_log, _ = self.run_dedupe({
            "a": report("Effect of Drug X on Condition Y", 2021, authors=["Lee K"]),
            "b": report("Effect of Drug X on Condition Y", 2021, authors=["Lee K"]),
        })
        self.assertEqual(removed, 1)
        self.assertTrue(any(m["matched_on"] == "title+author+year" for m in merge_log))

    def test_same_title_different_year_is_not_a_duplicate(self):
        reports, removed, _, near_misses = self.run_dedupe({
            "a": report("Effect of Drug X on Condition Y", 2020),
            "b": report("Effect of Drug X on Condition Y", 2023),
        })
        self.assertEqual(removed, 0)
        # different year should also not show up as a fuzzy near-miss
        self.assertEqual(near_misses, [])

    def test_same_title_same_year_different_authors_is_not_auto_merged(self):
        """A shared title+year with DIFFERENT authors must not exact-match on
        title+author+year, and must not be silently auto-merged via fuzzy
        matching either — it should show up as a near-miss for a human,
        at most."""
        reports, removed, merge_log, near_misses = self.run_dedupe({
            "a": report("Long-term Outcomes in Condition Y", 2022, authors=["Kim A"]),
            "b": report("Long-term Outcomes in Condition Y", 2022, authors=["Patel R"]),
        })
        self.assertEqual(removed, 0)
        self.assertFalse(any(m["matched_on"] == "title+author+year" for m in merge_log))

    def test_similar_but_distinct_titles_are_not_merged(self):
        """A follow-up or subgroup analysis sharing most of a title is a
        DIFFERENT report, not a duplicate — must never auto-merge on fuzzy
        title similarity alone."""
        reports, removed, merge_log, near_misses = self.run_dedupe({
            "a": report("Effect of Drug X in Condition Y", 2022, authors=["Chen L"]),
            "b": report("Effect of Drug X in Condition Y: a 5-year follow-up", 2022, authors=["Chen L"]),
        })
        self.assertEqual(removed, 0, "fuzzy title similarity must never auto-merge")
        self.assertFalse(any(m["matched_on"] not in ("human_confirmed",) and "a" in m["report_ids"] and "b" in m["report_ids"] for m in merge_log))

    def test_transitive_merge_across_different_identifier_types(self):
        """A shares a DOI with B; B shares a PMID with C. All three must
        end up in ONE cluster even though no single identifier links A
        and C directly — this is the union-find transitivity guarantee."""
        reports, removed, merge_log, _ = self.run_dedupe({
            "a": report("Study", 2020, doi="10.1/shared"),
            "b": {**report("Study (conf. abstract)", 2020, doi="10.1/shared"), "identifiers": {"doi": "10.1/shared", "pmid": "PM123"}},
            "c": report("Study (registry mirror)", 2020, doi=None, pmid="PM123"),
        })
        # exactly one of them is "unique" (the canonical root); the other two point at it
        uniques = [rid for rid in ("a", "b", "c") if reports[rid]["dedup_status"] == "unique"]
        self.assertEqual(len(uniques), 1)
        root = uniques[0]
        for rid in ("a", "b", "c"):
            if rid != root:
                self.assertEqual(reports[rid]["dedup_status"], f"duplicate_of:{root}")

    def test_confirmed_pairs_merge_even_without_shared_identifiers(self):
        reports, removed, merge_log, _ = self.run_dedupe(
            {
                "a": report("Study Alpha", 2019),
                "b": report("Totally Different Wording", 2019),
            },
            confirmed_pairs=[("a", "b")],
        )
        self.assertEqual(removed, 1)
        self.assertTrue(any(m["matched_on"] == "human_confirmed" for m in merge_log))


if __name__ == "__main__":
    unittest.main()
