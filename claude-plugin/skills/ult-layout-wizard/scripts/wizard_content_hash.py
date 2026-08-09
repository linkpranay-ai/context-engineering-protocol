#!/usr/bin/env python3
"""wizard_content_hash.py - content-hash helpers for the write path (D24
§18.3/§18.9, locked).

Two distinct re-entrancy checks in the write path need a plain content hash,
not a mtime or a size check (mtime granularity and clock skew make it an
unreliable freshness signal; a same-size-different-content edit would slip
past a size check entirely):

1. `wizard_apply.py` hashes `context-config.yaml` before and after calling
   `confirm_layers.run_confirm()`, to distinguish a real write from both a
   legitimate idempotent no-op (`run_confirm` returns `(0, ["Nothing to
   confirm ..."])` when every field is already confirmed) and the round-3 C2
   silent-no-op failure mode (`run_confirm` returns `(0, [...])` but neither
   wrote anything nor said "Nothing to confirm").
2. `wizard_apply.py` also hashes `context-layout-discovery.md` at load time
   and re-hashes it immediately before calling `run_confirm`, refusing to
   apply if the artifact changed underneath the staged session (round-3 H6) -
   e.g. a concurrent `discover` re-run's drift tracking rewrote it.

No existing hash utility in this repo applies here: `validate_layout.py` has
none, and `ult-context-generate`'s `content_hash8()` is a different file
format with its own field-stripping logic (it hashes semantic content after
stripping volatile front-matter fields) that doesn't transfer to a plain
"did these exact bytes change" check.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_file(path) -> Optional[str]:
    """SHA-256 hex digest of `path`'s current bytes, or None if the file
    doesn't exist. "Absent" is a distinct, meaningful state from "hashes to
    some value" here - `context-config.yaml` may genuinely not exist yet on
    a brand-new repo (confirm_layers.py itself treats a missing config file
    as an empty one, not an error), so callers compare this return value
    directly rather than needing a try/except around a missing-file
    exception."""
    p = Path(path)
    if not p.exists():
        return None
    return _hash_bytes(p.read_bytes())


def hash_config(repo_root) -> Optional[str]:
    """Hashes `{repo_root}/context-config.yaml` - always at the repo root,
    never workspace_root-relative (matches confirm_layers.run_confirm's own
    `config_path = repo_root / "context-config.yaml"`, which is not subject
    to the artifact's workspace_root placement dance)."""
    return hash_file(Path(repo_root) / "context-config.yaml")


def hash_artifact(artifact_path) -> Optional[str]:
    """Hashes the discovery artifact at `artifact_path` - callers pass
    `LayoutSource.discovery_artifact_path` (or the same path
    `confirm_layers.run_confirm` computes internally) rather than this
    module guessing its placement a third time."""
    return hash_file(artifact_path)
