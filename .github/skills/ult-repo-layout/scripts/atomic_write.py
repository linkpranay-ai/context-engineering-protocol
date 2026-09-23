#!/usr/bin/env python3
"""atomic_write.py - atomic same-directory temp-file-plus-rename write utility
for ult-repo-layout (2026-09-23, torn-read fix).

ult-repo-layout's own copy of ult-cep-wizard's `wizard_atomic_write.py`,
duplicated rather than cross-imported so ult-repo-layout stays usable (and
its own `confirm-layers`/`discover` CLIs stay runnable) in any repo that
installs ult-repo-layout without ult-cep-wizard - the same
`_find_repo_layout_scripts_dir`-duplication precedent `wizard_decision_staging.py`,
`wizard_apply.py`, `wizard_discover.py`, and `wizard_layout_source.py` already
follow for the reverse direction. A cross-import here would make
ult-repo-layout depend on a skill that itself depends on ult-repo-layout.

The core guarantee: a reader of the target path never observes a
partially-written file. `os.replace` is atomic on both POSIX and Windows when
source and destination are on the same filesystem - the temp file is created
in the *same directory* as the target specifically so the final `os.replace`
never crosses a filesystem boundary.

Used by `confirm_layers.run_confirm()` (writes `context-config.yaml` and
stamps `context-layout-discovery.md`) and `discover_layers.run_discovery()`
(writes `context-layout-discovery.md`) so neither leaves a torn read visible
to a concurrent reader - notably `wizard_layout_source.py`'s
`discovery_artifact_path` property, which re-parses `context-config.yaml` on
every access to resolve `workspace_root`, and whose result other callers use
as a lock key (`wizard_decision_staging._lock_for_target`). A torn config
read there could previously resolve a different `workspace_root`, and
therefore a different lock key, than a concurrent writer - silently
defeating that lock. See wizard_decision_staging.py's Thread-safety
docstring.
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
