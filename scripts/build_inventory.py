#!/usr/bin/env python3
"""Build the published-works inventory from the STAPI pull.

STAPI is the spine here. Unlike the Star Wars side -- which has no structured
catalogue of its extended universe and has to parse a wiki dump -- Star Trek
has a complete, typed API, and this script is mostly a mapping exercise.

The schema is the one shared with the sister star-wars project, so the two
inventories can be concatenated and compared.

Two details worth knowing:

* **Search records are not full records.** /search gives titles and dates but
  no authors, publishers or series; those come from the per-uid hydration pass
  in fetch_sources.py, which writes <entity>_full.jsonl. A work missing from
  the hydration file still appears here, with empty authorship, rather than
  being dropped.
* **`kind` comes from the boolean type flags, not the endpoint.** STAPI's
  /book covers novels, reference books, biographies, RPG manuals, audiobooks
  and anthologies, distinguished only by flags like `novel: true`. Calling all
  1,494 of them "novel" would be wrong by a factor of three.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAPI = ROOT / "data" / "raw" / "stapi"
OUT = ROOT / "data" / "derived" / "inventory.jsonl"

SOURCE_URL = "https://stapi.co/api/v1/rest"
LICENCE = "STAPI (stapi.co), free API"

# Checked in order; the first true flag wins. Order matters: a novelization is
# a novel, but recording the more specific fact is the point of having flags.
BOOK_KINDS = [
    ("referenceBook", "reference"),
    ("biographyBook", "reference"),
    ("rolePlayingBook", "reference"),
    ("audiobook", "audio"),
    ("anthology", "collection"),
    ("novelization", "novel"),
    ("novel", "novel"),
]


def load(name: str) -> list[dict]:
    path = STAPI / f"{name}.json"
    if not path.exists():
        raise SystemExit(f"{path} is missing -- run `make fetch` first")
    return json.loads(path.read_text())


def load_full(entity: str) -> dict[str, dict]:
    """The hydrated records, keyed by uid. Empty if the pass has not run."""
    path = STAPI / f"{entity}_full.jsonl"
    if not path.exists():
        return {}
    out = {}
    with path.open() as fh:
        for line in fh:
            if line.strip():
                record = json.loads(line)
                out[record["uid"]] = record
    return out


def names(record: dict, *fields: str) -> list[str]:
    for field in fields:
        values = record.get(field) or []
        if values:
            return [v["name"] for v in values if v.get("name")]
    return []


def titles(record: dict, field: str) -> str | None:
    values = record.get(field) or []
    return values[0].get("title") if values else None


def date_of(record: dict) -> tuple[int | None, str | None]:
    """(year, raw) from whichever date fields this entity carries."""
    if record.get("releaseDate"):
        raw = record["releaseDate"]
        return int(raw[:4]), raw
    year = record.get("publishedYear")
    if year is None:
        return None, None
    parts = [str(year)]
    if record.get("publishedMonth"):
        parts.append(f"{record['publishedMonth']:02d}")
        if record.get("publishedDay"):
            parts.append(f"{record['publishedDay']:02d}")
    return year, "-".join(parts)


def setting(record: dict) -> str | None:
    """In-universe placement: stardate range, else year range."""
    for lo, hi, label in (
        ("stardateFrom", "stardateTo", "stardate"),
        ("yearFrom", "yearTo", "year"),
    ):
        a, b = record.get(lo), record.get(hi)
        if a is None and b is None:
            continue
        if a is not None and b is not None and a != b:
            return f"{label} {a}-{b}"
        return f"{label} {a if a is not None else b}"
    return None


def book_kind(record: dict) -> str:
    for flag, kind in BOOK_KINDS:
        if record.get(flag):
            return kind
    return "book"


def record_for(entity: str, summary: dict, full: dict) -> dict:
    merged = {**summary, **full}
    year, raw = date_of(merged)
    kind = {
        "book": book_kind(merged),
        "comics": "comic",
        "videoGame": "video_game",
        "magazine": "magazine",
        "episode": "episode",
        "movie": "film",
        "bookSeries": "series",
        "comicSeries": "comic_series",
        "magazineSeries": "magazine_series",
        "bookCollection": "collection",
        "comicCollection": "collection",
        "series": "tv_series",
    }[entity]
    return {
        "id": f"st:{merged['uid']}",
        "franchise": "star-trek",
        "title": merged.get("title", "").strip(),
        "uid": merged["uid"],
        "kind": kind,
        "entity": entity,
        "series": (
            titles(merged, "bookSeries")
            or titles(merged, "comicSeries")
            or titles(merged, "magazineSeries")
        ),
        # Order matters: the most specific credit wins. An episode carries
        # `writers` plus `teleplayAuthors` and `storyAuthors`; a film credits
        # `writers`; a game credits `developers`.
        "authors": names(
            merged,
            "authors",
            "writers",
            "teleplayAuthors",
            "storyAuthors",
            "developers",
            "staff",
        ),
        "directors": names(merged, "directors"),
        "artists": names(merged, "artists"),
        "publisher": next(iter(names(merged, "publishers")), None),
        "published": year,
        "published_raw": raw,
        "isbn": None,  # STAPI does not carry ISBNs on any entity
        "page_count": merged.get("numberOfPages"),
        # Everything STAPI catalogues outside the screen canon is the Beta
        # continuity -- licensed, published, and not canon. The films and
        # episodes are prime. Nothing here is a guess.
        "continuity": "prime" if entity in ("episode", "movie", "series") else "beta",
        "continuity_basis": "entity-type",
        "setting": setting(merged),
        "hydrated": bool(full),
        "source": "stapi",
        "source_url": f"{SOURCE_URL}/{entity}?uid={merged['uid']}",
        "source_licence": LICENCE,
    }


ENTITIES = [
    "book",
    "comics",
    "videoGame",
    "magazine",
    "episode",
    "movie",
    "bookSeries",
    "comicSeries",
    "magazineSeries",
    "bookCollection",
    "comicCollection",
    "series",
]


def main(argv: list[str]) -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    hydrated = total = 0
    # Load everything first. Discovering a missing source halfway through
    # leaves a truncated inventory on disk that looks like a complete one.
    loaded = [(e, load(e), load_full(e)) for e in ENTITIES]
    with OUT.open("w") as fh:
        for entity, summaries, full in loaded:
            for summary in summaries:
                record = record_for(entity, summary, full.get(summary["uid"], {}))
                fh.write(json.dumps(record, sort_keys=True) + "\n")
                counts[record["kind"]] = counts.get(record["kind"], 0) + 1
                hydrated += record["hydrated"]
                total += 1
    print(
        f"{OUT.relative_to(ROOT)}: {total} works " f"({hydrated} with full authorship)"
    )
    for kind, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {count:6d}  {kind}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
