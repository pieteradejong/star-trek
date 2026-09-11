# star-trek

A complete, provenance-tracked inventory of the Star Trek extended universe —
every novel, comic, video game, magazine, episode and film — with plot summaries
drawn from Memory Beta and Memory Alpha. **4,497 works and 863,000 words of
summary**, covering 98% of the catalogue, built from source in about an hour.

The code is here. The corpus is not: it is rebuilt locally by `make data` and
never committed, because the upstream text is CC BY-SA and, for Memory Alpha,
**CC BY-NC**. See [Licensing](#licensing).

Its sister project, [star-wars](https://github.com/pieteradejong/star-wars),
does the same for the other franchise, into the same schema.

## Quick start

```sh
make data     # fetch and build everything -- about an hour, mostly polite waiting
make test     # the full gate; also runs as ./test.sh
```

`make help` lists every target. `7z` is required for the dumps
(`brew install p7zip`); everything else is the Python standard library.

## What you get

`data/derived/inventory.jsonl` — one JSON object per work, the same schema the
star-wars project emits, so the two can be concatenated:

```json
{
  "id": "st:BOMA0000154026",
  "title": "A Burning House",
  "kind": "novel",
  "series": "Star Trek: Klingon Empire",
  "authors": ["Keith R.A. DeCandido"],
  "publisher": "Pocket Books",
  "published": 2008,
  "page_count": 464,
  "continuity": "beta",
  "continuity_basis": "entity-type",
  "setting": "stardate 57000-57100",
  "source_url": "https://stapi.co/api/v1/rest/book?uid=BOMA0000154026"
}
```

`data/derived/plots.jsonl` — one summary per work, same `id`, same length, each
carrying the licence of the wiki it came from.

| kind | works |
|---|---:|
| comic (issues and series) | 1,119 |
| episode | 860 |
| novel | 587 |
| magazine (issues and series) | 599 |
| reference | 398 |
| book (untyped) | 332 |
| collection | 269 |
| audio | 142 |
| series | 91 |
| video_game | 74 |
| film | 14 |
| tv_series | 12 |
| **total** | **4,497** |

Field coverage: 67% have a publication year, 65% an author, 65% a page count,
63% a publisher, 47% a series. 697 distinct authors and 149 directors.
Plot summaries cover 4,420 of 4,497 works — **2,706 under CC BY-SA** from Memory
Beta and 1,714 under **CC BY-NC** from Memory Alpha.

## Data sources

| Source | What it gives | Licence | Scale |
|---|---|---|---|
| [STAPI](https://stapi.co) | **the spine**: the complete typed catalogue | free API | 4,497 works; 1,494 books, 985 comics, 860 episodes |
| [Memory Beta dump](https://s3.amazonaws.com/wikia_xml_dumps/s/st/startrek_pages_current.xml.7z) | EU plot summaries | **CC BY-SA 3.0** | 40 MB `.7z`, 76,856 articles, dumped 2026-01-13 |
| [Memory Alpha dump](https://s3.amazonaws.com/wikia_xml_dumps/e/en/enmemoryalpha_pages_current.xml.7z) | canon episode and film plots | **CC BY-NC 3.0** ⚠ | 78 MB `.7z`, 66,468 articles, dumped 2026-09-07 |

Every fetch is recorded in `data/MANIFEST.csv` — url, http status, bytes,
sha256, licence, date — which **is** tracked, so the cache can be verified
without the repository carrying it. A failed fetch is a row, not a gap.

Memory Beta's database is named `startrek`, not the `memorybeta` you would
guess. Both db names and both licences were read from each wiki's
`api.php?action=query&meta=siteinfo` rather than assumed.

### Sources evaluated and not used

- **chakoteya.net**, the canonical fan transcript archive — complete
  transcripts of every TOS, TNG, DS9, VOY and ENT episode. The host has not
  responded over either http or https since at least 2026-09-11.
  `scripts/fetch_dialogue.py` is written against it and left enabled, so the
  failure is reported as a failure rather than vanishing.
- **Full text of the novels.** 1,494 in-copyright books with no legitimate bulk
  source. This project catalogues and summarises the EU; it does not reproduce
  it.

## How it works

```
scripts/fetch_sources.py    STAPI + the dumps -> data/raw/, write data/MANIFEST.csv
scripts/dump.py             stream pages out of a .7z without unpacking it
scripts/wikitext.py         infobox, plot section and markup handling
scripts/build_inventory.py  STAPI -> inventory.jsonl
scripts/build_plots.py      the two dumps -> plots.jsonl, joined by title
scripts/check_invariants.py assert the figures this README quotes
```

### Four things worth knowing

- **STAPI's search records are not its full records.** `/search` gives titles
  and dates but no authors, publishers or series; those need one request per
  work. So `make fetch` runs a second, hydrating pass over 3,982 uids — serial,
  spaced, and **resumable**, appending as it goes and skipping what it already
  has, because a run that long must not start over when interrupted. Episodes
  and films are in that pass too: it is where their writers, teleplay and story
  authors, and directors come from.
- **`kind` comes from the type flags, not the endpoint.** `/book` covers novels,
  reference books, biographies, RPG manuals, audiobooks and anthologies, told
  apart only by booleans like `novel: true`. Calling all 1,494 "novel" would be
  wrong by a factor of three.
- **Memory Beta is scanned before Memory Alpha, on purpose.** Where both
  describe a work, the CC BY-SA text is preferred and the NonCommercial text is
  only a fallback — which is why 2,706 summaries are share-alike and only 1,714
  are NonCommercial, rather than the other way round.
- **`staff` is not a list of authors.** It was in the author field list at
  first, and swept entire production crews in: the corpus claimed ~1,000
  distinct authors where it really has 697. Putting `teleplayAuthors` and
  `storyAuthors` ahead of it fixed the count downwards, which was the correct
  direction.

The dumps are never extracted: `7z x -so` writes to stdout and
`ElementTree.iterparse` consumes the stream, clearing each element and
detaching it from the root. `tests/check_dump.py` fails the build if peak
memory ever stops being flat.

## Dialogue

`make dialogue` would cache episode transcripts into `data/raw/dialogue/`. That
text is Paramount copyright, is not covered by this repository's licences, and
is not part of the corpus. The fetcher refuses to run unless git confirms the
target directory is ignored. Its only source is currently unreachable — see
above.

Dialogue that *can* be redistributed — the "Memorable quotes" sections inside
both dumps — comes with `make data` like any other source.

## Tests

`./test.sh` runs six sections and reports all failures, not just the first:

| section | what it checks |
|---|---|
| `lint` | ruff, black, mypy, every script compiles, shellcheck |
| `unit` | the wikitext parser and the fetch layer, offline, no data needed |
| `boundary` | nothing fetched or generated is tracked; the baseline files exist |
| `data` | corpus contracts, the dumps still stream in bounded memory, invariants |
| `manifest` | every row has a licence, Memory Alpha is labelled NC, hashes match |
| `docs` | every path and `make` target this README names actually exists |

`./test.sh --fast` skips the sections that read the dumps; `./test.sh lint` runs
one section. Checks that need data **skip** rather than fail when `data/raw/` is
absent, so the suite is meaningful on a fresh clone and in CI. A tool that is
installed but broken is reported as a skip naming the cause, not as a failure.

## Licensing

Three-way split, and one part of it is unusually strict:

- **Code** — `scripts/`, `tests/`, the build — is MIT. See `LICENSE`.
- **`data/curated/`** — the hand-authored source register — is CC BY 4.0. See
  `LICENSE-DATA`.
- **Everything fetched or derived from the wikis** stays under their terms.
  Memory Beta is CC BY-SA 3.0. **Memory Alpha is CC BY-NC 3.0** — NonCommercial,
  which is incompatible with redistribution from a permissively licensed repo.
  None of it is here: `data/raw/` and `data/derived/` are gitignored, CI fails
  the build if anything under them is committed, and every summary row records
  which licence it inherited so a downstream consumer can filter. Rebuild it
  yourself with `make data`.

Star Trek, its titles, characters and settings are trademarks and copyrights of
Paramount Pictures / CBS Studios. This is an unofficial catalogue, not endorsed
by or affiliated with them.
