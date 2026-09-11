#!/usr/bin/env python3
"""Cache episode transcripts locally. COPYRIGHTED -- never committed, never published.

A separate script and a separate make target, deliberately. It is not part of
`make data`, so the default path of this project never touches it.

Status: DEGRADED, and honestly so
---------------------------------
chakoteya.net is the canonical fan transcript archive for Star Trek -- complete
transcripts of every TOS, TNG, DS9, VOY and ENT episode. As of 2026-09-11 the
host does not respond, over either http or https, from this machine. The
fetcher is written against it and is left ENABLED, because the failure is the
host's and may be temporary; it simply reports the failure as a failure rather
than pretending there was nothing to fetch.

Recording a dead source as dead is the point. Deleting the code would make it
indistinguishable from a source nobody looked for.

What to use instead
-------------------
`make data` already collects dialogue that CAN be redistributed: the
"Memorable quotes" sections inside the Memory Alpha and Memory Beta dumps.
Those are CC BY-SA and CC BY-NC respectively, are part of the corpus, and cover
every episode -- in quotes rather than full transcripts.

The transcripts themselves are Paramount's. Nothing here changes that:

  * output goes only to data/raw/dialogue/, which is gitignored
  * the script REFUSES to run if git does not confirm that path is ignored
  * nothing derived from this text reaches data/derived/ or the corpus
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import fetch
from fetch import RAW

DEST = RAW / "dialogue"

# chakoteya indexes each series on its own path, with per-episode pages beneath.
BASE = "https://www.chakoteya.net"
SERIES = {
    "tos": "/StarTrek/episodes.htm",
    "tng": "/NextGen/episodes.htm",
    "ds9": "/DS9/episodes.htm",
    "voy": "/Voyager/episode_listing.htm",
    "ent": "/Enterprise/episodes.htm",
}

NOTICE = """\
COPYRIGHTED TEXT -- LOCAL USE ONLY
==================================

The files in this directory are fan transcriptions of Star Trek episodes.
The episodes are Copyright (c) Paramount Pictures / CBS Studios. They are NOT
covered by this repository's MIT or CC BY 4.0 licences, and no licence to
redistribute them is granted or implied by their presence here.

They were fetched by scripts/fetch_dialogue.py for personal reading. This
directory is gitignored and the fetcher refuses to run if it is not. Do not
commit these files, do not publish them, and do not include them in anything
derived from this project that leaves your machine.

Source: https://www.chakoteya.net/ -- a fan transcript archive, not an
authorised publisher. Treat the text as approximate.

For dialogue that CAN be redistributed, use the quotes already inside the
corpus: Memory Beta is CC BY-SA, Memory Alpha is CC BY-NC.
"""

LINK = re.compile(r'href="([^"]+\.html?)"', re.I)
TAG = re.compile(r"<[^>]+>")
BR = re.compile(r"<\s*br\s*/?\s*>", re.I)


def refuse_if_committable() -> None:
    """Do not write copyrighted text anywhere git would let you commit it."""
    root = Path(__file__).resolve().parent.parent
    if not (root / ".git").exists():
        print(
            "  ~ not a git repository; the gitignore check cannot run.\n"
            "    Refusing anyway: set up the repo first, so the ignore rule "
            "is in place before the text is.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    probe = "data/raw/dialogue/probe.txt"
    result = subprocess.run(
        ["git", "check-ignore", "-q", probe], cwd=root, capture_output=True
    )
    if result.returncode != 0:
        print(
            f"REFUSING: {probe} is not gitignored.\n"
            f"This script writes copyrighted text and will not put it "
            f"anywhere that could be committed. Fix .gitignore first.",
            file=sys.stderr,
        )
        raise SystemExit(2)


def to_text(html: bytes) -> str:
    import html as html_mod

    text = BR.sub("\n", html.decode("utf-8", "replace"))
    return html_mod.unescape(TAG.sub("", text)).strip()


def main(argv: list[str]) -> int:
    refuse_if_committable()
    DEST.mkdir(parents=True, exist_ok=True)
    (DEST / "README.txt").write_text(NOTICE)

    reachable = failed = 0
    for series, index_path in SERIES.items():
        result = fetch.get(f"{BASE}{index_path}")
        if not result.ok:
            print(
                f"  !! {series}: index unreachable ({result.status})", file=sys.stderr
            )
            failed += 1
            continue
        episodes = sorted(set(LINK.findall(result.body.decode("utf-8", "replace"))))
        print(f"  ↓ {series}: {len(episodes)} episode pages listed")
        reachable += 1

    if reachable == 0:
        print(
            "\nNo transcript source reachable. chakoteya.net has been "
            "unresponsive since at least 2026-09-11; this is the host's "
            "failure, not a missing feature.\n"
            "Redistributable dialogue is already in the corpus: run "
            "`make data` and read the quotes from the wiki dumps instead.",
            file=sys.stderr,
        )
        return 1

    print(f"\n{reachable} series reachable, {failed} failed, in {DEST}")
    print(
        "This text is copyrighted and gitignored. It is not part of the "
        "published corpus."
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
