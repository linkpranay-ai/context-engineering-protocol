#!/usr/bin/env python3
"""autoscaffold_atomic_write.py - atomic same-directory temp-file-plus-rename
write utility for ult-autoscaffold-content (TASK-0109, D24 Phase B).

ult-autoscaffold-content's own copy of ult-cep-wizard's `wizard_atomic_write.py`
(also duplicated as ult-repo-layout's `atomic_write.py`), duplicated rather than
cross-imported so ult-autoscaffold-content stays usable, and `scaffold_state.py`
stays runnable as a single vendorable script, in any repo that installs
ult-autoscaffold-content without ult-cep-wizard or ult-repo-layout also
installed. A cross-import here would make ult-autoscaffold-content depend on a
sibling skill it has no other dependency on.

The core guarantee: a reader of `TRIAGE-STATE.json` never observes a
partially-written file. `os.replace` is atomic on both POSIX and Windows when
source and destination are on the same filesystem - the temp file is created
in the *same directory* as the target specifically so the final `os.replace`
never crosses a filesystem boundary.

Used by `scaffold_state.save_state()` so a concurrent reader (another
`scaffold_state.py` invocation, or the wizard's status endpoint) never sees a
torn write of the state file - paired with `scaffold_state.state_lock()`,
which serializes concurrent *writers* around the same load-mutate-save cycle
(Sec 9.3's file lock, defense in depth against the single-writer rule ever
being violated).
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


# Same rationale and values as wizard_atomic_write.py's - see that module for
# the full note on why these aren't empirically tuned against a reproducible
# race.
_REPLACE_RETRY_ATTEMPTS = 5
_REPLACE_RETRY_DELAY_SECONDS = 0.05


def _replace_with_retry(tmp_path: Path, target: Path) -> None:
    """`os.replace` with a few short retries on `PermissionError` - a
    Windows-only AV/indexer race, harmless elsewhere. See
    wizard_atomic_write.py's `_replace_with_retry` for the full explanation;
    duplicated here rather than imported for the same reason this whole
    module is duplicated (see module docstring)."""
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
