#!/usr/bin/env python3
"""Extract plot summaries from the two wiki dumps, matched to the STAPI inventory.

STAPI catalogues the works but carries no prose, so the summaries come from the
wikis and are joined to the inventory by title.

Two sources, two very different licences, and the difference is load-bearing:

  Memory Beta  CC BY-SA 3.0   the extended universe: novels, comics, games
  Memory Alpha CC BY-NC 3.0   the screen canon: episodes and films

Memory Alpha is **NonCommercial**. Every row derived from it is tagged
`summary_licence: CC-BY-NC-3.0` so that a downstream consumer can filter it
out, and nothing from either wiki is ever committed -- data/derived/ is
gitignored for exactly this reason.

Matching is by normalised title, and deliberately conservative: a work that
does not match is recorded with `summary: null` rather than guessed at. The
match rate is reported so a drop in it is visible.

Output is data/derived/plots.jsonl.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

import dump
import wikitext as wt

ROOT = Path(__file__).resolve().parent.parent
INVENTORY = ROOT / "data" / "derived" / "inventory.jsonl"
OUT = ROOT / "data" / "derived" / "plots.jsonl"

WIKIS = [
    (
        "memory-beta",
        ROOT / "data" / "raw" / "memory-beta.xml.7z",
        "CC-BY-SA-3.0",
        "https://memory-beta.fandom.com/wiki/",
    ),
    (
        "memory-alpha",
        ROOT / "data" / "raw" / "memory-alpha.xml.7z",
        "CC-BY-NC-3.0",
        "https://memory-alpha.fandom.com/wiki/",
    ),
]

PLOT_HEADINGS = [
    {"summary", "plot", "plot summary", "synopsis", "story", "contents"},
    # "Introduction" is Memory Beta's own heading for the jacket blurb, and is
    # by far the most common prose section on a novel article there.
    {
        "introduction",
        "publisher's summary",
        "publishers summary",
        "back cover",
        "from the publisher",
        "description",
        "official description",
        "blurb",
    },
    {"gameplay", "premise", "overview", "background information"},
]

MIN_CHARS = 40
# Memory Beta disambiguates with a parenthetical: "Vendetta (novel)". The STAPI
# title is the bare one, so both forms are indexed.
PAREN = re.compile(r"\s*\([^)]*\)\s*$")


def normalise(title: str) -> str:
    """Case-folded, punctuation-light key for joining a STAPI title to a wiki page."""
    text = unicodedata.normalize("NFKD", title)
    # Escapes, not literals: a right single quote and an en dash are visually
    # indistinguishable from ' and - in most fonts, which is exactly the sort of
    # thing that makes a title-matching bug impossible to see.
    text = text.replace("\u2019", "'").replace("\u2013", "-").replace("\u2014", "-")
    text = re.sub(r"^(star trek:?\s*)", "", text.strip(), flags=re.I)
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return text.strip()


def summarise(text: str) -> tuple[str | None, str | None]:
    for i, headings in enumerate(PLOT_HEADINGS):
        body = wt.section(text, headings)
        if body and len(body) >= MIN_CHARS:
            return body, ("plot", "publisher", "overview")[i]
    body = wt.lead(text)
    if body and len(body) >= MIN_CHARS:
        return body, "lead"
    return None, None


def main(argv: list[str]) -> int:
    if not INVENTORY.exists():
        raise SystemExit(
            "data/derived/inventory.jsonl is missing -- "
            "run scripts/build_inventory.py first"
        )
    with INVENTORY.open() as fh:
        works = [json.loads(line) for line in fh if line.strip()]

    # Many works share a normalised title (a novel and its audiobook, say), so
    # the index maps a key to every work that claims it.
    index: dict[str, list[dict]] = {}
    for work in works:
        key = normalise(work["title"])
        if key:
            index.setdefault(key, []).append(work)
    print(f"{len(works)} works, {len(index)} distinct titles to match")

    # (summary, heading it came from, licence, wiki url). The heading is
    # Optional because summarise() falls back to the lead paragraph, which has
    # no heading of its own.
    found: dict[str, tuple[str, str | None, str, str]] = {}
    for name, archive, licence, base_url in WIKIS:
        if not archive.exists():
            print(f"  ~ {archive.name} absent; skipping {name}", file=sys.stderr)
            continue
        dump.check_7z()
        matched = scanned = 0
        for page in dump.stream(archive, namespaces={0}, skip_redirects=True):
            scanned += 1
            if scanned % 5000 == 0:
                print(
                    f"\r  {name}: {scanned:,} pages, {matched} matched",
                    end="",
                    flush=True,
                )
            for key in {normalise(page.title), normalise(PAREN.sub("", page.title))}:
                if not key or key not in index:
                    continue
                # First wiki to supply a summary wins. Memory Beta is scanned
                # first on purpose: its share-alike licence is the less
                # restrictive of the two, so prefer it wherever both have the
                # work and only fall back to the NonCommercial text.
                for work in index[key]:
                    if work["id"] in found:
                        continue
                    summary, source = summarise(page.text)
                    if summary:
                        found[work["id"]] = (
                            summary,
                            source,
                            licence,
                            base_url + page.title.replace(" ", "_"),
                        )
                        matched += 1
                break
        print(f"\r  {name}: {scanned:,} pages, {matched} matched" + " " * 12)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    licences: dict[str, int] = {}
    with OUT.open("w") as out:
        for work in works:
            summary: str | None = None
            source: str | None = None
            licence: str | None = None
            url: str | None = None
            entry = found.get(work["id"])
            if entry is not None:
                summary, source, licence, url = entry
            if licence:
                licences[licence] = licences.get(licence, 0) + 1
            out.write(
                json.dumps(
                    {
                        "id": work["id"],
                        "title": work["title"],
                        "kind": work["kind"],
                        "summary": summary,
                        "summary_source": source,
                        "words": len(summary.split()) if summary else 0,
                        "source_url": url or work["source_url"],
                        "summary_licence": licence,
                    },
                    sort_keys=True,
                )
                + "\n"
            )

    total = len(found)
    print(
        f"\n{OUT.relative_to(ROOT)}: {len(works)} works, {total} with a summary "
        f"({100 * total / len(works):.0f}%)"
    )
    for licence, count in sorted(licences.items()):
        flag = "  <- NonCommercial, never redistribute" if "NC" in licence else ""
        print(f"  {count:6d}  {licence}{flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
