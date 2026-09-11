# CLAUDE.md

Guidance for AI coding assistants working in this repository. Symlinked as `AGENTS.md`.

## Overview

A provenance-tracked inventory of the Star Trek extended universe: 4,497
published works from STAPI, with 864,000 words of plot summary joined by title
from the Memory Beta and Memory Alpha dumps. The repository holds the code that
builds the corpus, never the corpus itself. Its sister project is `../star-wars`,
which emits the same schema — but has no API and must parse a wiki dump for its
catalogue, where this one does not.

## Commands

```sh
make data        # fetch then build inventory + plots + invariants (~1 hour)
make fetch       # download only: STAPI + both dumps, into gitignored data/raw/
make inventory   # STAPI -> data/derived/inventory.jsonl
make plots       # both dumps -> data/derived/plots.jsonl
make invariants  # assert the figures the README quotes
make dialogue    # COPYRIGHTED transcripts, local-only -- not part of `make data`
make clean       # remove data/derived/. KEEPS data/raw/, so no re-download.

./test.sh              # the full gate: lint, unit, boundary, data, manifest, docs
./test.sh --fast       # skip the sections that read the dumps
./test.sh boundary     # one section by name
make lint / make format
```

Requires `7z` (`brew install p7zip`). No runtime Python dependencies by design.

## Architecture

```
scripts/fetch.py            shared fetch layer: robots, throttle, manifest
scripts/fetch_sources.py    STAPI search + hydration, and the two dumps
scripts/fetch_dialogue.py   separate on purpose; copyrighted, local-only
scripts/dump.py             streams pages out of a .7z, never extracts it
scripts/wikitext.py         infobox parsing, markup flattening, section finding
scripts/build_inventory.py  STAPI -> inventory.jsonl
scripts/build_plots.py      both dumps -> plots.jsonl, joined by normalised title
data/curated/sources.yaml   hand-authored source register (committed, CC BY 4.0)
data/MANIFEST.csv           tracked record of every fetch: sha256, licence, date
```

## Gotchas

- **Memory Alpha is CC BY-NC.** This is the one licensing trap in the project.
  Memory Beta and Wookieepedia are CC BY-SA; Memory Alpha is NonCommercial and
  must never be redistributed from a public repo. Every summary row carries
  `summary_licence` so a consumer can filter, Memory Beta is scanned **first**
  so the share-alike text wins wherever both cover a work, and
  `tests/test_manifest.py` asserts the NC label is present. Do not reorder
  `WIKIS` in `build_plots.py` without understanding this.
- **Memory Beta's database is named `startrek`**, not `memorybeta`. Both db
  names and both licences came from each wiki's
  `api.php?action=query&meta=siteinfo`. Do not construct them.
- **STAPI's `/search` returns summaries, not full records** — no authors,
  publishers or series. Those need one request per uid, which is what
  `hydrate_stapi` does for the six entities in `STAPI_HYDRATE`. It appends and
  skips what it has, so it is resumable; keep it that way, a full pass is ~4,000
  serial requests. Adding an entity to the inventory without adding it to
  hydration silently yields works with no authorship.
- **`staff` is not a list of authors.** It once sat in the author field list and
  swept whole production crews in, inflating distinct authors to ~1,000 where
  the true figure is 697. `teleplayAuthors` and `storyAuthors` come first.
- **`kind` comes from STAPI's boolean type flags, not the endpoint.** `/book`
  covers novels, reference, biography, RPG, audio and anthologies.
- **Plot matching must stay deterministic.** The match keys are an ordered list,
  not a set: set iteration order made the summary count drift between identical
  builds.
- **mypy cannot run on this machine** — its shebang points at a removed Python
  3.11. `test.sh` reports it as a skip naming the cause; CI is the only thing
  that actually type-checks.
- **The CI workflow's shell is `bash -e`.** A trailing `&&` chain inside a
  command substitution ends false and fails the step with no message. Use `if`.
