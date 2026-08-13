#!/usr/bin/env python3
"""wizard_discover.py - UI-driven `discover` orchestration (D24 Phase 2, §18.14).

`run_discover()` is the only place in this skill that calls
`discover_layers.run_discovery()` - the real (re-)generation of
`context-layout-discovery.md`. Mirrors wizard_apply.py's shape (freshness check ->
guard -> the real in-process call -> result), but gets its own exception hierarchy
rather than sharing wizard_apply.py's `StaleArtifactError` - same
independent-hierarchy precedent as `DecisionStagingError`/`ApplyError` already being
separate from each other.

Two distinct refusals, both checked before the real call:

1. **Freshness check** (same pattern as wizard_apply.py's own, reusing
   `wizard_content_hash.hash_artifact`): the artifact's current content hash must
   match the hash the caller loaded it under. A mismatch means the artifact changed
   underneath this session since it was last read.
2. **Staged-decision guard (the real gap this module exists to close)**:
   `discover_layers.py`'s own drift tracking (`_load_prior_confirmed_state`) only
   preserves a section across a re-run when *every* field in it is already
   `# CONFIRMED`-stamped (confirmed via direct read of discover_layers.py:901-936).
   A section with a **staged-but-not-yet-Applied** decision does not satisfy that, so
   a bare re-run of `discover` would silently regenerate it as a fresh PENDING
   proposal, discarding the staged choice. `run_discover()` refuses (raising
   `AtRiskDecisionsError`, carrying the affected section titles) unless the caller
   passes `force=True` - the frontend turns that into an explicit
   confirm-to-discard step, not a generic error.
"""
from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import wizard_content_hash as wch  # noqa: E402


class DiscoverError(Exception):
    """Base class for any run_discover refusal - already-user-facing message."""


class StaleArtifactError(DiscoverError):
    """The artifact's content changed since it was loaded (same freshness contract
    as wizard_apply.StaleArtifactError, kept as an independent class per this
    module's own exception hierarchy)."""


class AtRiskDecisionsError(DiscoverError):
    """At least one section has a staged-but-not-yet-Applied decision that a bare
    re-run of `discover` would silently discard. Carries the affected section
    titles so the caller can render a specific confirm-to-discard step."""

    def __init__(self, at_risk_sections: List[str]):
        super().__init__(
            "re-running discover would discard staged (not yet Applied) decisions "
            "in: " + "; ".join(at_risk_sections)
        )
        self.at_risk_sections = list(at_risk_sections)


@dataclass
class DiscoverResult:
    artifact_path: Path
    artifact_hash_after: Optional[str]
    discarded_staged_sections: List[str] = dc_field(default_factory=list)


def _find_repo_layout_scripts_dir(repo_root) -> Path:
    """Same lookup wizard_apply.py's/wizard_layout_source.py's own (private)
    versions do - duplicated for the same reason those already duplicate it from
    each other: this module must be independently usable and independently
    unit-testable without either of them having already run in the same process."""
    scripts_dir = Path(repo_root) / ".github" / "skills" / "ult-repo-layout" / "scripts"
    if not (scripts_dir / "discover_layers.py").exists():
        raise DiscoverError(
            f"ult-repo-layout's discover_layers.py was not found under "
            f"{scripts_dir} - is ult-repo-layout installed in this repo?"
        )
    return scripts_dir


def _import_repo_layout_modules(repo_root):
    scripts_dir_str = str(_find_repo_layout_scripts_dir(repo_root))
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    discover_layers = importlib.import_module("discover_layers")
    confirm_layers = importlib.import_module("confirm_layers")
    return discover_layers, confirm_layers


def _at_risk_sections(cl, artifact_path: Path) -> List[str]:
    """Sections with at least one decision-bearing field that is neither still
    PENDING nor already `# CONFIRMED`-stamped - i.e. staged, in
    wizard_layout_source.DecisionField's own vocabulary. Same lightweight
    PENDING-vs-CONFIRMED-stamp check DecisionField.state and
    wizard_decision_staging.stage_decision already use, not a
    `.resolve()` call - a still-malformed field must not raise and take the whole
    guard down with it."""
    if not artifact_path.exists():
        return []
    _lines, fields = cl.parse_artifact(artifact_path.read_text(encoding="utf-8"))
    at_risk: List[str] = []
    for f in fields:
        if f.comment and cl.CONFIRMED_STAMP_RE.match(f.comment):
            continue
        if f.raw_value.strip() == "PENDING":
            continue
        if f.section_title not in at_risk:
            at_risk.append(f.section_title)
    return at_risk


def run_discover(repo_root, artifact_path, loaded_artifact_hash, force: bool = False) -> DiscoverResult:
    """(Re-)generate `context-layout-discovery.md` via
    `discover_layers.run_discovery()`, refusing if the artifact drifted since
    `loaded_artifact_hash` was captured, or if it would silently discard staged
    decisions unless `force=True`. Raises `StaleArtifactError` or
    `AtRiskDecisionsError` on refusal; returns a `DiscoverResult` on success."""
    repo_root = Path(repo_root).resolve()
    artifact_path = Path(artifact_path)

    current_artifact_hash = wch.hash_artifact(artifact_path)
    if current_artifact_hash != loaded_artifact_hash:
        raise StaleArtifactError(
            "the discovery artifact changed since it was loaded - reload it "
            "before running discover again"
        )

    dl, cl = _import_repo_layout_modules(repo_root)

    at_risk = _at_risk_sections(cl, artifact_path)
    if at_risk and not force:
        raise AtRiskDecisionsError(at_risk)

    out_path, _artifact_text = dl.run_discovery(repo_root)

    return DiscoverResult(
        artifact_path=out_path,
        artifact_hash_after=wch.hash_artifact(out_path),
        discarded_staged_sections=at_risk if force else [],
    )
