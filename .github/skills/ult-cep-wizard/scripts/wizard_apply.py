#!/usr/bin/env python3
"""wizard_apply.py - Apply orchestration for the write path (D24 §18.3/§18.9,
locked).

`apply_confirmed()` is the only place in this skill that calls
`confirm_layers.run_confirm()` - the real commit. Everything before that call
is refusal logic; everything after it is result classification, never a
second write.

1. **Freshness check (round-3 H6)**: the artifact's current content hash must
   match the hash the caller loaded it under (`loaded_artifact_hash`,
   normally the value a prior `/api/decisions` read handed back). A mismatch
   means the artifact changed underneath this session - e.g. a concurrent
   `discover` re-run's drift tracking rewrote it, or another browser tab
   staged something - and Apply refuses rather than commit against a session
   that no longer reflects what's on disk.
2. **All-resolved pre-check**: every `Field` in the artifact is resolved and
   `_check_single_primary_choice` is run, exactly mirroring what
   `run_confirm` enforces internally - done here first so a still-PENDING
   field (or a still-unresolved H-2 double-primary-choice) produces a
   structured `ValidationError` with every offending message, not a bare
   `(1, [...])` tuple the caller has to interpret.
3. **The real call**: `context-config.yaml` is hashed before, then
   `confirm_layers.run_confirm(repo_root)` is called in-process (no
   subprocess - there is nothing interactive in it and a subprocess would
   only add exit-code/stdout-parsing failure modes on top of the tuple
   return `run_confirm` already gives directly), then hashed again after.
4. **Result classification (round-3 C2)**: `run_confirm` returning
   `(0, [...])` is not by itself proof anything was committed - three
   distinct outcomes share that same exit code:
   - the config hash changed: a real commit happened (`config_changed=True`);
   - the config hash is unchanged **and** a message starts with "Nothing to
     confirm": every field was already confirmed - a legitimate idempotent
     no-op (`idempotent=True`), not a failure;
   - the config hash is unchanged **and** no such message appears: this is
     the round-3 C2 silent-no-op failure mode - `run_confirm` claimed
     success but nothing happened and gave no explanation. Raised as
     `UnexpectedNoOpError`, never reported to a caller as success.
"""
from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import wizard_content_hash as wch  # noqa: E402


class ApplyError(Exception):
    """Base class for any apply_confirmed refusal - already-user-facing
    message."""


class StaleArtifactError(ApplyError):
    """The artifact's content changed since it was loaded (round-3 H6)."""


class ValidationError(ApplyError):
    """One or more fields are not yet resolvable (still PENDING, an offered
    verb doesn't parse, a section still has more than one primary choice,
    ...). Carries every per-field message, not just the first one."""

    def __init__(self, messages: List[str]):
        super().__init__("; ".join(messages) if messages else "validation failed")
        self.messages = list(messages)


class UnexpectedNoOpError(ApplyError):
    """run_confirm() returned success (exit code 0) but context-config.yaml's
    content did not change and it did not say "Nothing to confirm" either -
    round-3 C2's silent-no-op failure mode. Never present this to a caller
    as success."""


@dataclass
class ApplyResult:
    config_changed: bool
    idempotent: bool
    messages: List[str] = dc_field(default_factory=list)
    config_hash_after: Optional[str] = None
    artifact_hash_after: Optional[str] = None


def _find_repo_layout_scripts_dir(repo_root) -> Path:
    """Same lookup wizard_layout_source.py's and wizard_decision_staging.py's
    own (private) versions do - duplicated a third time for the same reason
    those two duplicate it from each other (see wizard_decision_staging.py's
    docstring): this module must be independently usable - and
    independently unit-testable, see test_wizard_apply.py - without either
    of them having already run in the same process."""
    scripts_dir = Path(repo_root) / ".github" / "skills" / "ult-repo-layout" / "scripts"
    if not (scripts_dir / "confirm_layers.py").exists():
        raise ApplyError(
            f"ult-repo-layout's confirm_layers.py was not found under "
            f"{scripts_dir} - is ult-repo-layout installed in this repo?"
        )
    return scripts_dir


def _import_confirm_layers(repo_root):
    scripts_dir_str = str(_find_repo_layout_scripts_dir(repo_root))
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    return importlib.import_module("confirm_layers")


def _resolve_all_fields_or_raise(cl, fields):
    errors: List[str] = []
    for field in fields:
        try:
            field.resolve()
        except cl.FieldError as exc:
            errors.append(str(exc))
    if not errors:
        cl._check_single_primary_choice(fields, errors)
    if errors:
        raise ValidationError(errors)


def apply_confirmed(repo_root, artifact_path, loaded_artifact_hash) -> ApplyResult:
    """Commit every currently-resolved decision line in `artifact_path` into
    `context-config.yaml`, refusing if the artifact drifted since
    `loaded_artifact_hash` was captured or if anything is still unresolved.
    Raises `StaleArtifactError`, `ValidationError`, or `UnexpectedNoOpError`
    on refusal; returns an `ApplyResult` on success (real commit or a
    legitimate already-all-confirmed idempotent no-op - both are success)."""
    repo_root = Path(repo_root).resolve()
    artifact_path = Path(artifact_path)

    current_artifact_hash = wch.hash_artifact(artifact_path)
    if current_artifact_hash != loaded_artifact_hash:
        raise StaleArtifactError(
            "the discovery artifact changed since it was loaded - reload it "
            "and re-stage before applying again"
        )

    cl = _import_confirm_layers(repo_root)
    if not artifact_path.exists():
        raise ValidationError([f"{artifact_path} not found - run `discover` first."])

    _lines, fields = cl.parse_artifact(artifact_path.read_text(encoding="utf-8"))
    _resolve_all_fields_or_raise(cl, fields)

    config_hash_before = wch.hash_config(repo_root)
    exit_code, messages = cl.run_confirm(repo_root)

    if exit_code != 0:
        raise ValidationError(messages)

    config_hash_after = wch.hash_config(repo_root)
    artifact_hash_after = wch.hash_artifact(artifact_path)
    config_changed = config_hash_before != config_hash_after
    said_nothing_to_confirm = any(m.startswith("Nothing to confirm") for m in messages)

    if not config_changed and not said_nothing_to_confirm:
        raise UnexpectedNoOpError(
            "apply reported success but context-config.yaml did not change and no "
            "explanation was given - refusing to report this as success "
            "(messages: " + "; ".join(messages) + ")"
        )

    return ApplyResult(
        config_changed=config_changed,
        idempotent=(not config_changed) and said_nothing_to_confirm,
        messages=list(messages),
        config_hash_after=config_hash_after,
        artifact_hash_after=artifact_hash_after,
    )
