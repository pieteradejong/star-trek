"""Unit tests for the wikitext parser.

The fixture is real wikitext from Memory Beta's "A Burning House", fetched via
its api.php and trimmed. Synthetic markup would not exercise what actually
breaks a parser -- a template nested inside an infobox value, a wrapped
`{{ISBN|...}}`, a caption with its own link. These run offline and need no dump.

Memory Beta's conventions differ from Wookieepedia's in ways that matter here:
the infobox is `{{Novel|`, dates are wrapped in `{{srcdate|...}}`, the series
is `{{ST|...}}`, and the blurb sits under `==Introduction==` rather than
`==Publisher's summary==`.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import wikitext as wt

BURNING_HOUSE = """{{DEFAULTSORT:Burning House}}{{otheruses|House}}
{{Novel|
|type = novel
|title = A Burning House
|cover image = [[File:ABurningHouse.jpg|220px]]
|artist = [[Stephan Martiniere]]
|series = {{ST|Klingon Empire}}
|author = [[Keith R.A. DeCandido]]
|publisher =
|format = [[Paperback]]
|published = {{srcdate|2008|February}}
|pages = 368
|ISBN = {{ISBN|1-4165-5647-8}}
|date = [[2376]]
|}}
'''''A Burning House''''' is a ''[[Star Trek]]'' [[novel]] by [[Keith R.A. DeCandido]].

==Introduction==
They have been the [[Federation]]'s staunchest allies, and its fiercest
adversaries. They are the [[Klingon]]s &ndash; and if you think you already
know all there is to learn about them... think again.

==References==
*[[Worf]]

[[Category:Novels]]
"""


class TestInfobox(unittest.TestCase):
    def setUp(self) -> None:
        found = wt.find_infobox(BURNING_HOUSE, {"novel", "comic"})
        assert found is not None
        self.name, self.params = found

    def test_finds_the_infobox_not_the_preceding_templates(self) -> None:
        """{{DEFAULTSORT}} and {{otheruses}} come first and are not infoboxes."""
        self.assertEqual(self.name, "novel")

    def test_simple_fields(self) -> None:
        self.assertEqual(wt.flatten(self.params["title"]), "A Burning House")
        self.assertEqual(self.params["pages"], "368")

    def test_empty_fields_are_kept_as_empty_not_dropped(self) -> None:
        """Memory Beta leaves unused parameters present and blank."""
        self.assertEqual(self.params.get("publisher"), "")

    def test_author_is_a_link(self) -> None:
        self.assertEqual(wt.links(self.params["author"]), ["Keith R.A. DeCandido"])

    def test_templates_inside_values_do_not_split_the_field(self) -> None:
        """`{{srcdate|2008|February}}` and `{{ISBN|1-4165-5647-8}}` carry pipes."""
        self.assertIn("published", self.params)
        self.assertIn("isbn", self.params)
        self.assertIn("date", self.params)
        self.assertEqual(wt.year_of(self.params["published"]), 2008)

    def test_cover_image_yields_no_person(self) -> None:
        self.assertEqual(wt.links(self.params["cover image"]), [])

    def test_year_survives_a_template_wrapped_date(self) -> None:
        """Memory Beta writes {{srcdate|2008|February}}; flattening first
        strips the template and loses the year entirely."""
        self.assertEqual(wt.year_of("{{srcdate|2008|February}}"), 2008)

    def test_year_ignores_a_citation_year(self) -> None:
        """A <ref> naming a differently-dated source sits in the same field."""
        self.assertEqual(
            wt.year_of("<ref name='YBY'>Year By Year, 2012</ref>[[May 1]], [[1991]]"),
            1991,
        )


class TestFlatten(unittest.TestCase):
    def test_strips_markup(self) -> None:
        self.assertEqual(wt.flatten("'''''Bold italic'''''"), "Bold italic")
        self.assertEqual(wt.flatten("[[Worf]]"), "Worf")
        self.assertEqual(wt.flatten("[[Worf, son of Mogh|Worf]]"), "Worf")
        self.assertEqual(wt.flatten("text<!-- hidden -->more"), "textmore")

    def test_br_becomes_a_space(self) -> None:
        """Dropping <br/> outright welds words together."""
        self.assertEqual(
            wt.flatten("A Burning:<br />House"),
            "A Burning: House",
        )

    def test_html_entities_are_decoded(self) -> None:
        # The EN DASH here is deliberate: it is what &ndash; must decode to.
        self.assertEqual(wt.flatten("2376&ndash;2377"), "2376\u20132377")
        self.assertEqual(wt.flatten("Kirk &amp; Spock"), "Kirk & Spock")

    def test_image_embeds_are_dropped_caption_and_all(self) -> None:
        """A picture is not prose, and its caption carries layout junk."""
        self.assertEqual(
            wt.flatten("[[File:X.jpg|thumb|left|180px|A caption]]Real prose."),
            "Real prose.",
        )
        self.assertEqual(wt.flatten("[[Image:a.png|thumb|c]]Text."), "Text.")

    def test_links_nested_inside_an_image_caption_leave_no_markup(self) -> None:
        """The regression: a non-greedy match stops at the INNER ']]' and
        strands the outer one in the output as literal markup."""
        out = wt.flatten("[[File:X.jpg|thumb|[[Worf, son of Mogh|Worf.]]]]Prose.")
        self.assertEqual(out, "Prose.")
        for marker in ("[[", "]]", "thumb"):
            self.assertNotIn(marker, out)

    def test_malformed_source_markup_leaves_nothing_behind(self) -> None:
        """The wikis contain genuinely broken links -- a doubled "]]", an
        unclosed "[[". No correct parse resolves those, because the source is
        wrong; once the well-formed links are gone, the remains are swept."""
        for broken in (
            "the [[Klingon Empire|empire]]]] at war",
            "an [[unclosed link that never closes",
            "a stray ]] bracket",
        ):
            with self.subTest(broken=broken):
                out = wt.flatten(broken)
                self.assertNotIn("[[", out)
                self.assertNotIn("]]", out)

    def test_refs_are_removed_including_self_closing(self) -> None:
        self.assertEqual(wt.flatten("Text<ref name='a'>Note</ref> more"), "Text more")
        self.assertEqual(wt.flatten("Text<ref name='a' /> more"), "Text more")


class TestSections(unittest.TestCase):
    def test_finds_the_introduction(self) -> None:
        """Memory Beta's blurb heading; Wookieepedia calls it something else."""
        body = wt.section(BURNING_HOUSE, {"introduction"})
        assert body is not None
        self.assertTrue(body.startswith("They have been the Federation's"))
        # Must stop at the next heading, not run to the end of the article.
        self.assertNotIn("Worf", body)

    def test_missing_section_is_none(self) -> None:
        self.assertIsNone(wt.section(BURNING_HOUSE, {"gameplay"}))

    def test_lead_excludes_infobox_and_banners(self) -> None:
        lead = wt.lead(BURNING_HOUSE)
        self.assertIn("is a Star Trek novel by Keith R.A. DeCandido", lead)
        self.assertNotIn("368", lead)  # infobox content
        self.assertNotIn("Paperback", lead)


class TestBalance(unittest.TestCase):
    def test_nested_templates_are_balanced(self) -> None:
        found = wt.find_infobox("{{Novel|a={{X|{{Y|z}}}}|b=2}}", {"novel"})
        assert found is not None
        self.assertEqual(found[1]["b"], "2")

    def test_unclosed_template_is_not_a_crash(self) -> None:
        self.assertIsNone(wt.find_infobox("{{Novel|a=1", {"novel"}))

    def test_absent_infobox_returns_none(self) -> None:
        self.assertIsNone(wt.find_infobox("plain text", {"novel"}))


if __name__ == "__main__":
    unittest.main()
