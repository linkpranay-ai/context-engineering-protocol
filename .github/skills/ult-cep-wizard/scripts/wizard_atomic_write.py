#!/usr/bin/env python3
"""wizard_atomic_write.py - atomic same-directory temp-file-plus-rename write
utility for ult-cep-wizard (D24 §18.2b, locked).

**Live in production since Phase 1.** `wizard_server.py`'s `do_POST` handler wires
`POST /api/stage` to `wizard_decision_staging.stage_decision()`, which calls
`write_text_atomic()` directly (see `wizard_decision_staging.py`). Two further
production callers were added since: `wizard_retrofit_apply.py` (applying a
retrofit edit to a target file) and `wizard_retrofit_state.py` (writing
`.gitignore` and the retrofit state JSON). Grep the repo for `write_text_atomic`
before assuming any particular caller is the only one, or that this module is
still unused - it is not.

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
import time
from pathlib import Path


class AtomicWriteError(Exception):
    """Raised when the write cannot be completed - the target's parent directory
    doesn't exist, or the underlying filesystem operation fails. Never leaves a
    partially-written file at the target path in either case (see module
    docstring)."""


# Not empirically tuned against the real AV/indexer race -- there's no
# reliable way to reproduce that race on demand to measure how long it
# actually holds the handle. 5 attempts / 50ms apart is a cheap, generous
# default (4 sleeps, ~200ms worst case before giving up) chosen to be well
# above a plausible momentary-scan window while staying imperceptible in
# an interactive wizard flow; revisit if it's ever observed to still be
# too short in practice.
_REPLACE_RETRY_ATTEMPTS = 5
_REPLACE_RETRY_DELAY_SECONDS = 0.05


def _replace_with_retry(tmp_path: Path, target: Path) -> None:
    """`os.replace` with a few short retries on `PermissionError`.

    Windows-only race, harmless elsewhere: a just-written file can be held
    open momentarily by AV/indexer scanning, so the very next `os.replace`
    onto it (or onto the temp file about to replace it) raises
    `PermissionError` (WinError 5) even though nothing is actually wrong.
    This surfaced in practice as a flaky failure in a caller that replaces
    the same target file several times in quick succession
    (`wizard_decision_staging.stage_decision`, called repeatedly against
    `context-layout-discovery.md`). POSIX rename has no equivalent window,
    so this loop is a no-op there - the first attempt always succeeds. A
    *persistent* `PermissionError` (the lock never clears) still exhausts
    the retries and raises, same as before - this only smooths over a
    transient race, it does not mask a real failure."""
    last_exc: OSError | None = None
    for attempt in range(_REPLACE_RETRY_ATTEMPTS):
        try:
            os.replace(tmp_path, target)
            return
        except PermissionError as exc:
            last_exc = exc
            if attempt < _REPLACE_RETRY_ATTEMPTS - 1:
                time.sleep(_REPLACE_RETRY_DELAY_SECONDS)
    if last_exc is None:
        raise AssertionError("_REPLACE_RETRY_ATTEMPTS must be >= 1")
    raise last_exc


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
        _replace_with_retry(tmp_path, target)
    except OSError as exc:
        tmp_path.unlink(missing_ok=True)
        raise AtomicWriteError(f"could not atomically write '{target}': {exc}") from exc
