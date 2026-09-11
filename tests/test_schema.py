"""Contract tests on the generated corpus.

These skip -- they do not fail -- when data/derived/ is absent, so the suite is
meaningful on a fresh clone and in CI, where the sources are deliberately not
present. When the data IS there, they are strict: a field that silently changed
type, or an upstream that quietly returned half the catalogue, should break the
build rather than ship.

The licence tests are the ones that matter most. Memory Alpha is CC BY-NC, and
a row that loses its licence tag is a row a downstream consumer cannot filter.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INVENTORY = ROOT / "data" / "derived" / "inventory.jsonl"
PLOTS = ROOT / "data" / "derived" / "plots.jsonl"

# Verified against STAPI on 2026-09-11. Floors, not equalities: the catalogue
# grows, but a sharp drop means the API changed shape or a pull was truncated.
MIN_WORKS = 4_200
MIN_BOOKS = 1_494
MIN_COMICS = 985
MIN_EPISODES = 860

KINDS = {
    "novel",
    "reference",
    "audio",
    "collection",
    "book",
    "comic",
    "comic_series",
    "video_game",
    "magazine",
    "magazine_series",
    "episode",
    "film",
    "series",
    "tv_series",
}
CONTINUITY = {"prime", "beta"}
LICENCES = {"CC-BY-SA-3.0", "CC-BY-NC-3.0", None}
REQUIRED = {
    "id": str,
    "franchise": str,
    "title": str,
    "kind": str,
    "uid": str,
    "entity": str,
    "continuity": str,
    "authors": list,
    "artists": list,
    "directors": list,
    "source": str,
    "source_url": str,
    "source_licence": str,
}


def load(path: Path) -> list[dict]:
    with path.open() as fh:
        return [json.loads(line) for line in fh if line.strip()]


class TestInventory(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not INVENTORY.exists():
            raise unittest.SkipTest(
                "data/derived/inventory.jsonl absent; run `make data`"
            )
        cls.rows = load(INVENTORY)

    def test_size(self) -> None:
        self.assertGreaterEqual(len(self.rows), MIN_WORKS)

    def test_required_fields_and_types(self) -> None:
        for row in self.rows[:2000]:
            for field, kind in REQUIRED.items():
                with self.subTest(id=row.get("id"), field=field):
                    self.assertIn(field, row)
                    self.assertIsInstance(row[field], kind)

    def test_ids_are_unique(self) -> None:
        ids = [r["id"] for r in self.rows]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_title_is_non_empty(self) -> None:
        blank = [r["id"] for r in self.rows if not r["title"].strip()]
        self.assertEqual(blank[:5], [], f"{len(blank)} works have no title")

    def test_kinds_are_from_the_shared_vocabulary(self) -> None:
        """The vocabulary is shared with the star-wars project on purpose, so
        the two inventories can be concatenated."""
        self.assertEqual({r["kind"] for r in self.rows} - KINDS, set())

    def test_continuity_vocabulary(self) -> None:
        self.assertEqual({r["continuity"] for r in self.rows} - CONTINUITY, set())

    def test_screen_canon_is_prime_and_everything_else_is_beta(self) -> None:
        for row in self.rows:
            with self.subTest(id=row["id"]):
                expected = (
                    "prime"
                    if row["entity"] in ("episode", "movie", "series")
                    else "beta"
                )
                self.assertEqual(row["continuity"], expected)

    def test_entity_counts_match_stapi(self) -> None:
        counts: dict[str, int] = {}
        for row in self.rows:
            counts[row["entity"]] = counts.get(row["entity"], 0) + 1
        self.assertGreaterEqual(counts.get("book", 0), MIN_BOOKS)
        self.assertGreaterEqual(counts.get("comics", 0), MIN_COMICS)
        self.assertGreaterEqual(counts.get("episode", 0), MIN_EPISODES)

    def test_episodes_credit_their_writers(self) -> None:
        """STAPI carries writers, teleplayAuthors, storyAuthors and directors
        on every episode; they only arrive via the hydration pass, and it is
        easy to leave an entity out of it by accident."""
        episodes = [r for r in self.rows if r["entity"] == "episode"]
        hydrated = [r for r in episodes if r["hydrated"]]
        if not hydrated:
            self.skipTest("episodes not hydrated yet")
        credited = [r for r in hydrated if r["authors"] or r["directors"]]
        self.assertGreater(
            len(credited),
            len(hydrated) * 0.9,
            "hydrated episodes should nearly all carry a writer or director",
        )

    def test_books_are_typed_by_flag_not_lumped_together(self) -> None:
        """STAPI's /book covers novels, reference, audio and anthologies. If
        every one came back "novel", the type flags were ignored."""
        kinds = {r["kind"] for r in self.rows if r["entity"] == "book"}
        self.assertGreater(len(kinds), 1, f"all 1,494 books got one kind: {kinds}")

    def test_known_works_are_present_and_correct(self) -> None:
        by_title = {r["title"]: r for r in self.rows}
        burning = by_title.get("A Burning House")
        self.assertIsNotNone(burning, "A Burning House is missing")
        self.assertEqual(burning["kind"], "novel")
        self.assertEqual(burning["published"], 2008)
        self.assertEqual(burning["continuity"], "beta")
        if burning["hydrated"]:
            self.assertIn("Keith R.A. DeCandido", burning["authors"])

    def test_publication_years_are_plausible(self) -> None:
        years = [r["published"] for r in self.rows if r["published"]]
        self.assertGreater(len(years), len(self.rows) * 0.6)
        # 1964, not 1966: "The Cage" -- the original TOS pilot -- was produced
        # two years before the series premiered, and STAPI dates it correctly.
        self.assertGreaterEqual(min(years), 1964)
        self.assertLessEqual(max(years), 2030)

    def test_source_urls_point_at_stapi(self) -> None:
        for row in self.rows[:500]:
            self.assertTrue(row["source_url"].startswith("https://stapi.co/"))


class TestPlots(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not PLOTS.exists():
            raise unittest.SkipTest("data/derived/plots.jsonl absent; run `make data`")
        cls.rows = load(PLOTS)

    def test_one_row_per_work(self) -> None:
        if not INVENTORY.exists():
            self.skipTest("inventory absent")
        self.assertEqual(
            len(self.rows),
            len(load(INVENTORY)),
            "plots and inventory must stay the same length",
        )

    def test_every_summary_records_which_licence_it_inherited(self) -> None:
        """The whole point. A summary whose licence is unknown cannot be used,
        because Memory Alpha's is NonCommercial and Memory Beta's is not."""
        for row in self.rows:
            with self.subTest(id=row["id"]):
                self.assertIn(row["summary_licence"], LICENCES)
                if row["summary"]:
                    self.assertIsNotNone(
                        row["summary_licence"],
                        "a summary with no licence tag is unusable",
                    )
                else:
                    self.assertIsNone(row["summary_licence"])

    def test_noncommercial_rows_are_a_minority(self) -> None:
        """Memory Beta is scanned first precisely so the share-alike text wins.
        If the NC half dominates, that ordering broke."""
        with_summary = [r for r in self.rows if r["summary"]]
        if not with_summary:
            self.skipTest("no summaries matched")
        nc = [r for r in with_summary if r["summary_licence"] == "CC-BY-NC-3.0"]
        self.assertLess(
            len(nc),
            len(with_summary) * 0.75,
            "NonCommercial text dominates; the wiki order is wrong",
        )

    def test_word_count_matches_the_summary(self) -> None:
        for row in self.rows[:500]:
            expected = len(row["summary"].split()) if row["summary"] else 0
            self.assertEqual(row["words"], expected)

    def test_summaries_carry_no_residual_markup(self) -> None:
        for row in self.rows[:1000]:
            if not row["summary"]:
                continue
            with self.subTest(id=row["id"]):
                for marker in ("[[", "]]", "{{", "}}", "<ref", "&ndash;"):
                    self.assertNotIn(marker, row["summary"])


if __name__ == "__main__":
    unittest.main()
