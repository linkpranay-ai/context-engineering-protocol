#!/usr/bin/env python3
"""wizard_box_files.py - read-only file enumeration for a resolved What/How
box path.

§18.1's own spec for the four-box surface says each box lists "the files
currently resolved into it" - until now `wizard_boxes.py` only ever carried
the *directory path(s)* a layer resolves to (`BoxPath{path, source}`), never
what's actually inside them. This module is the missing piece: given a
resolved directory, walk it and report what's there.

Same "read-only discovery" shape `wizard_docs.py` already uses for the
wizard's own project docs, but generic rather than a fixed doc set - any
resolved What/How path, not a closed list of known files. Missing/
non-directory input is an empty result, not an error, matching
`wizard_docs.py`'s "missing docs are not an error" stance and the fail-closed-
but-not-fatal posture used elsewhere in this skill (a broken layout doesn't
crash the server; a missing/empty box path shouldn't either).

This is now also the single owner of the "does this path have real content"
signal. `wizard_stub_content.py` used to keep its own separate copy of the
same ignored-name pruning and rglob walk for its `_has_content()` check -
duplication that made sense when it was a small standalone helper (the
"each module owns its own copy" reasoning `wizard_containment.py`/
`wizard_tripwire.py` give for *their* independent helpers), but stops making
sense once a second module (`wizard_boxes.py`, here) needs to do the exact
same walk for the exact same reason: both are answering "what real files
exist under this resolved path," not two conceptually different checks that
happen to look similar. `wizard_stub_content._has_content` now delegates to
`list_files()` below instead of keeping its own copy.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

# How many files a single box path will list before truncating. Arbitrary but
# named, so it's a one-line change if a real repo turns out to need more/fewer
# - not a magic number buried in the walk below.
MAX_FILES_PER_PATH = 40

# Same pruning `wizard_stub_content.py` used to keep its own copy of - not a
# security boundary (contrast `wizard_containment.py`), just noise this box
# listing shouldn't bother a first-time user with.
IGNORED_NAMES = frozenset(
    {".git", "__pycache__", ".DS_Store", "Thumbs.db", ".gitkeep"}
)


@dataclass
class FileListing:
    files: List[str] = field(default_factory=list)  # POSIX paths, relative to
    # the queried directory itself (not repo-root-relative) - the box header
    # already shows the directory, so an entry reads "interfaces/foo.md", not
    # the redundant full "docs/how/interfaces/foo.md".
    total_count: int = 0  # real count, even when `files` was truncated.
    truncated: bool = False


def list_files(
    repo_root: Path, rel_dir: str, limit: int = MAX_FILES_PER_PATH
) -> FileListing:
    """Recursively lists the files under `repo_root / rel_dir`, sorted
    case-fold, first `limit` returned with `truncated=True` if there were
    more. A missing path, or one that isn't a directory, returns an empty
    listing rather than raising - callers never need to check existence
    first.

    Uses `os.walk` with in-place `dirnames` pruning (not `Path.rglob`) so an
    ignored directory - `.git` above all - is never descended into at all,
    rather than walked and then filtered entry-by-entry; for a real repo
    that's the difference between a fast, small listing and silently
    surfacing thousands of `.git` internals to a first-time user."""
    target = Path(repo_root) / rel_dir.rstrip("/")
    if not target.is_dir():
        return FileListing()

    found: List[str] = []
    for dirpath, dirnames, filenames in os.walk(target):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_NAMES]
        rel_here = Path(dirpath).relative_to(target)
        for name in filenames:
            if name in IGNORED_NAMES:
                continue
            found.append(name if rel_here == Path(".") else (rel_here / name).as_posix())
    found.sort(key=str.casefold)

    total = len(found)
    return FileListing(
        files=found[:limit], total_count=total, truncated=total > limit
    )
