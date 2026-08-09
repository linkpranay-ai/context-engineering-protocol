#!/usr/bin/env python3
"""wizard_atomic_write.py - atomic same-directory temp-file-plus-rename write
utility for ult-layout-wizard (D24 §18.2b, locked).

**Not called by anything yet.** Phase 0 (this build order step) registers zero
mutating routes anywhere in wizard_server.py - the picker is browse-only (§18.7,
§18.10), and wizard_stub_content.py only ever *previews* text, it never writes any
of it to disk. This module exists now, ahead of its first caller, because §18.2b's
write-path security spec is a single deliverable landing together with Phase 1's
write endpoint (§18.10: "Gated on §18.2b's full write-path security spec ... landing
as one deliverable together with the containment/auth test suite, not written ahead
of or separately from it") - building the primitive now and exercising it with its
own direct unit tests lets that later landing be "wire this in" rather than "design
and build this from scratch under Phase-1 time pressure." **Phase 1 will be the
first caller** - do not remove this module for looking unused; grep the repo for
`wizard_atomic_write` before assuming it's dead code.

The core guarantee: a reader of the target path never observes a partially-written
file. `os.replace` is atomic on both POSIX and Windows when source and destination
are on the same filesystem - the temp file is created in the *same directory* as the
target specifically so the final `os.replace` never crosses a filesystem boundary
(a temp dir elsewhere, e.g. `tempfile.gettempdir()`, could easily be a different
volume, silently downgrading the rename to a non-atomic copy+delete on some
platforms).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


class AtomicWriteError(Exception):
    """Raised when the write cannot be completed - the target's parent directory
    doesn't exist, or the underlying filesystem operation fails. Never leaves a
    partially-written file at the target path in either case (see module
    docstring)."""


def write_text_atomic(target_path, content: str, encoding: str = "utf-8") -> None:
    """Writes `content` to `target_path` atomically: a temp file in the same
    directory is written and flushed first, then `os.replace`d onto the target in
    one step. If anything fails before the replace, the temp file is cleaned up and
    `target_path` is left untouched (either absent, if it didn't exist before, or
    holding its previous content, if it did) - never a half-written file."""
    target = Path(target_path)
    parent = target.parent
    if not parent.is_dir():
        raise AtomicWriteError(
            f"cannot write '{target}': parent directory '{parent}' does not exist."
        )

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(parent)
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, target)
    except OSError as exc:
        tmp_path.unlink(missing_ok=True)
        raise AtomicWriteError(f"could not atomically write '{target}': {exc}") from exc
