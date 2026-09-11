#!/usr/bin/env python3
"""Download every third-party source into data/raw/ (gitignored).

Nothing here is committed: the dumps are large, they carry their own licences,
and they change upstream. Run `make data` to fetch and then rebuild the corpus
under data/derived/.

Sources and licences are catalogued in README.md -> "Data sources", and every
fetch is recorded in data/MANIFEST.csv, which IS tracked.

Deliberately NOT here: scripts/fetch_dialogue.py. Verbatim episode dialogue is
Paramount copyright and is cached local-only; keeping it out of `make data`
means the default path never touches it.
"""

from __future__ import annotations

import json
import sys
import time

import fetch
from fetch import RAW, Manifest

# The three bulk sources. Db names came from each wiki's
# api.php?action=query&meta=siteinfo -- note Memory Beta's is "startrek", not
# the "memorybeta" you would guess, which is why this is recorded rather than
# constructed. Licences came from the same endpoint's rightsinfo.
DUMPS = {
    "memory-alpha.xml.7z": {
        "url": "https://s3.amazonaws.com/wikia_xml_dumps/e/en/enmemoryalpha_pages_current.xml.7z",
        # NOT share-alike -- NonCommercial. Everything derived from this file is
        # tagged CC-BY-NC downstream and never leaves data/derived/. See README.
        "licence": "CC-BY-NC-3.0 (Memory Alpha)",
        "note": "canon: episodes, films, characters",
    },
    "memory-beta.xml.7z": {
        "url": "https://s3.amazonaws.com/wikia_xml_dumps/s/st/startrek_pages_current.xml.7z",
        "licence": "CC-BY-SA-3.0 (Memory Beta)",
        "note": "extended universe: novels, comics, games",
    },
}

# STAPI is the spine of this project. It is the only structured, complete
# catalogue of the Star Trek extended universe that exists -- the Star Wars
# side of this pair has no equivalent and has to parse a wiki dump instead.
STAPI = "https://stapi.co/api/v1/rest"

# Expected counts, verified 2026-09-11. `make invariants` asserts these: an
# upstream that quietly returns less should break the build rather than ship a
# thinner catalogue.
STAPI_ENTITIES = {
    "book": 1494,
    "bookSeries": 91,
    "comics": 985,
    "comicSeries": 134,
    "videoGame": 74,
    "magazine": 555,
    "episode": 860,
    "movie": 14,
    "series": 12,
    "magazineSeries": None,
    "bookCollection": None,
    "comicCollection": None,
}

# The /search endpoints return a SUMMARY record -- title, dates, page count, and
# the boolean type flags -- but no authors, publishers or series. Those exist
# only on the full /<entity>?uid=... record, one HTTP request each. So the
# entities whose authorship actually matters get a second, hydrating pass; the
# rest are complete from search alone. Episodes and films are in the list
# because STAPI credits their writers, teleplay and story authors, and
# directors -- none of which appear in a search result.
STAPI_HYDRATE = ["book", "comics", "videoGame", "magazine", "episode", "movie"]
STAPI_LICENCE = "STAPI, free API (stapi.co) -- data about copyrighted works"

PAGE_SIZE = 100
# ~3,100 hydration requests. At the shared 1.0s delay that is 52 minutes against
# a hobbyist's free API; at 0.4s it is 21, which is still serial and still
# announces itself. Overridable with --delay= if stapi.co ever complains.
HYDRATE_DELAY = 0.4


def fetch_dumps(manifest: Manifest, force: bool) -> None:
    known = manifest.previous_urls()
    for name, spec in DUMPS.items():
        dest = RAW / name
        stale = known.get(name) not in (None, spec["url"])
        if stale and dest.exists():
            print(f"  ~ {name} was fetched from a different URL; re-downloading")
        if dest.exists() and not force and not stale:
            print(f"  = {name} ({dest.stat().st_size / 1e6:.1f} MB, cached)")
            manifest.record(
                name,
                "dump",
                spec["url"],
                fetch.Result("200", "application/x-7z-compressed", b""),
                spec["licence"],
                dest,
            )
            continue
        print(f"  ↓ {name}  [{spec['note']}]")
        # S3 serves no robots.txt for these paths and the dumps are published
        # for exactly this use; the wiki hosts themselves are still checked.
        res = fetch.stream_to(spec["url"], dest, respect_robots=False)
        if res.ok:
            print(
                f"    {dest.stat().st_size / 1e6:.1f} MB  "
                f"sha256={fetch.sha256_of(dest)[:16]}"
            )
        else:
            print(f"    !! {res.status}", file=sys.stderr)
        manifest.record(name, "dump", spec["url"], res, spec["licence"], dest)


def fetch_stapi(manifest: Manifest, force: bool) -> None:
    """Page through every STAPI entity into one JSON file each.

    STAPI's search endpoints are POST-friendly but accept GET with query
    params, and return {"page": {...}, "<entity>s": [...]}. The plural key is
    not always the entity name plus "s" (comics -> comics), so the payload is
    read by taking whichever key holds the list.
    """
    for entity, expected in STAPI_ENTITIES.items():
        dest = RAW / "stapi" / f"{entity}.json"
        if dest.exists() and not force:
            n = len(json.loads(dest.read_text()))
            print(f"  = stapi/{entity}.json ({n} records, cached)")
            manifest.record(
                f"stapi/{entity}",
                "api",
                f"{STAPI}/{entity}/search",
                fetch.Result("200", "application/json", b""),
                STAPI_LICENCE,
                dest,
            )
            continue
        records: list[dict] = []
        page, total_pages, status = 0, 1, "200"
        while page < total_pages:
            url = f"{STAPI}/{entity}/search?pageNumber={page}&pageSize={PAGE_SIZE}"
            res = fetch.get(url, respect_robots=False)
            if not res.ok:
                status = res.status
                print(f"    !! {entity} page {page}: {res.status}", file=sys.stderr)
                break
            payload = json.loads(res.body)
            meta = payload.get("page", {})
            total_pages = meta.get("totalPages", 1)
            for key, value in payload.items():
                if key != "page" and isinstance(value, list):
                    records.extend(value)
            page += 1
            print(
                f"\r  ↓ stapi/{entity}  page {page}/{total_pages}  "
                f"{len(records)} records",
                end="",
                flush=True,
            )
        print()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(records, indent=1) + "\n")
        if expected and len(records) < expected:
            print(
                f"    ~ {entity}: {len(records)} records, expected >= {expected}",
                file=sys.stderr,
            )
        manifest.record(
            f"stapi/{entity}",
            "api",
            f"{STAPI}/{entity}/search",
            fetch.Result(status, "application/json", b""),
            STAPI_LICENCE,
            dest,
        )


def hydrate_stapi(manifest: Manifest, force: bool) -> None:
    """Pull the full record for every uid in the entities that carry authorship.

    Resumable by design: records are appended to a .jsonl as they arrive and the
    uids already present are skipped on a re-run. Three thousand serial requests
    is long enough that an interrupted run must not mean starting over.
    """
    for entity in STAPI_HYDRATE:
        index = RAW / "stapi" / f"{entity}.json"
        if not index.exists():
            print(f"  ~ stapi/{entity}.json missing; run the search pass first")
            continue
        uids = [r["uid"] for r in json.loads(index.read_text())]
        dest = RAW / "stapi" / f"{entity}_full.jsonl"
        if force:
            dest.unlink(missing_ok=True)
        done: set[str] = set()
        if dest.exists():
            with dest.open() as fh:
                done = {json.loads(line)["uid"] for line in fh if line.strip()}
        todo = [u for u in uids if u not in done]
        if not todo:
            print(f"  = stapi/{entity}_full.jsonl ({len(done)} records, complete)")
            manifest.record(
                f"stapi/{entity}_full",
                "api",
                f"{STAPI}/{entity}?uid=",
                fetch.Result("200", "application/json", b""),
                STAPI_LICENCE,
                dest,
            )
            continue
        print(
            f"  ↓ stapi/{entity}_full.jsonl  {len(todo)} to fetch "
            f"({len(done)} already cached)"
        )
        status, failed = "200", 0
        with dest.open("a") as fh:
            for i, uid in enumerate(todo, 1):
                res = fetch.get(f"{STAPI}/{entity}?uid={uid}", respect_robots=False)
                if res.ok:
                    payload = json.loads(res.body)
                    record = payload.get(entity) or payload
                    fh.write(json.dumps(record, sort_keys=True) + "\n")
                    fh.flush()
                else:
                    failed += 1
                    status = res.status
                if i % 25 == 0 or i == len(todo):
                    print(f"\r    {i}/{len(todo)}  {failed} failed", end="", flush=True)
        print()
        manifest.record(
            f"stapi/{entity}_full",
            "api",
            f"{STAPI}/{entity}?uid=",
            fetch.Result(status, "application/json", b""),
            STAPI_LICENCE,
            dest,
        )


def main(argv: list[str]) -> int:
    force = "--force" in argv
    only = next((a.split("=", 1)[1] for a in argv if a.startswith("--only=")), None)
    delay = next((a.split("=", 1)[1] for a in argv if a.startswith("--delay=")), None)
    RAW.mkdir(parents=True, exist_ok=True)
    manifest = Manifest()
    started = time.monotonic()

    if only in (None, "stapi"):
        print("STAPI (structured catalogue of the whole franchise)")
        fetch_stapi(manifest, force)
        print("\nSTAPI full records (authors, publishers, series)")
        fetch.DELAY = float(delay) if delay else HYDRATE_DELAY
        hydrate_stapi(manifest, force)
        fetch.DELAY = 1.0
    if only in (None, "dumps"):
        print("\nWiki dumps (plot summaries and everything STAPI does not model)")
        fetch_dumps(manifest, force)

    manifest.write()
    print(f"done in {time.monotonic() - started:.0f}s")
    return 0 if all(r["http_status"] == "200" for r in manifest.rows) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
