#!/usr/bin/env python3
"""wizard_autoscaffold_probe.py - lazy, cached evidence probe for ult-cep-wizard's
W1 mode selector (Proposal Sec 9.4/10, "W1: probe cost", locked).

`wizard_stub_content.what_how_card()`/`upgrade_card()` take an `evidence` kwarg
(default `"unknown"`, never computed by that module itself - see its own docstring)
that this module supplies: `scaffold_state.probe_size(repo_root)`'s
`grounded_viable`/`greenfield` fields, dynamically imported cross-skill from
`ult-autoscaffold-content/scripts/`, same pattern `wizard_tripwire.py` established
for importing `decision_ledger.py` from `ult-institutional-memory-distill/scripts/`
(`_find_decision_ledger_scripts_dir`/`_import_decision_ledger_module` there -
`_find_scaffold_state_scripts_dir`/`_import_scaffold_state_module` here, same
shape). `ult-autoscaffold-content` is optional, exactly like
`ult-institutional-memory-distill` is for the Trip-wire box: a repo without it
installed still gets a working wizard, just with every mode's evidence
availability reported as `"unknown"` (the box isn't gated on this at all - the
mode selector just shows skeleton-only, which needs no evidence).

**Never imports `scaffold_state._git_head_commit` directly** - it's a private
(leading-underscore) helper, and this codebase's standing convention (stated in
`wizard_containment.py`/`wizard_tripwire.py`'s own docstrings, and in
`wizard_stub_content.py`'s reason for taking plain scalars instead of importing
`TripwireSummary`) is to duplicate small, genuinely-standalone helpers across
module boundaries rather than reach into another module's private internals.
`_git_head_commit` below is therefore a deliberate, verbatim-equivalent local copy
of `scaffold_state.py`'s own private helper of the same name - re-diff the two if
either ever changes.

**Cache.** Per the proposal's "W1: probe cost" bullets: the probe's result is
cached in `cache/autoscaffold-content/probe.json` (the same top-level `cache/`
tree `scaffold_state.py` itself already writes `proposed/` and `CEP-INDEX.md`
under - see its `_PROPOSED_CACHE_PREFIX`/`_CONTENT_INDEX_WORKSPACE_ROOT_LEAF`),
keyed by the HEAD commit and the mtimes of the "signal files". Written with
`wizard_atomic_write.write_text_atomic` (never a bare `Path.write_text` - this
module reuses the one write primitive the rest of `ult-cep-wizard` already
standardizes on), after first ensuring `cache/autoscaffold-content/` exists
(`write_text_atomic` itself refuses to create a missing parent directory, by
design - see its own docstring).

The "signal files" are deliberately an approximation, not a mirror, of
`probe_size()`'s own real signal walk: that walk is recursive across every
top-level candidate directory, and reproducing it exactly here just to decide
whether to re-run the very thing being cached would defeat caching's purpose.
Instead this module checks only `repo_root`'s own top level, for the exact
filenames in `scaffold_state`'s six public (no leading underscore, so read live
via `getattr` rather than duplicated) filename-constant sets
(`FORMATTER_CONFIG_FILENAMES`, `LINTER_CONFIG_FILENAMES`,
`WRAPPER_SCRIPT_FILENAMES`, `TEST_CONFIG_FILENAMES`, `CI_CONFIG_FILENAMES`,
`CONTRIBUTING_FILENAMES`). This is an honest, accepted gap: a nested-directory
config file change between commits with no top-level change and no HEAD change
won't invalidate the cache. In practice the HEAD-commit half of the key already
catches any *committed* change regardless of depth; the gap is only live between
commits, for an edit to a config file that isn't at repo-root, and self-heals
the moment that work is committed or the file list changes.

**Budget.** `scaffold_state.probe_size()` is a pure-Python, no-subprocess call,
so there is no subprocess timeout to lean on (unlike `_git_head_commit` above,
which already has its own `timeout=10`). `signal.alarm` is POSIX-only and this
must run on Windows too (the dev environment this skill ships from), so the 1.5s
budget is enforced with a daemon `threading.Thread` + `join(timeout)` instead:
best-effort, not a hard kill. If the probe is still running past budget,
`get_evidence()` gives up waiting and returns `"unknown"` immediately; the slow
thread is simply abandoned to finish (or not) on its own, same
no-reliable-kill-primitive posture `wizard_atomic_write.py`'s own retry-comment
already accepts for a different unmeasurable race. A probe that blows its
budget is never cached as a success - only a real result ever gets written to
probe.json.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import wizard_atomic_write as waw  # noqa: E402

OWNING_SKILL = "ult-autoscaffold-content"
_PROBE_MODULE_NAME = "scaffold_state"
_PROBE_BUDGET_SECONDS = 1.5
_CACHE_REL_PATH = Path("cache") / "autoscaffold-content" / "probe.json"

# Public (no leading underscore) filename-constant attribute names read live off
# the dynamically-imported scaffold_state module for the signal-file scan below -
# see module docstring for why these are read via getattr rather than duplicated
# (they're public, unlike _git_head_commit).
_SIGNAL_FILENAME_CONSTANTS = (
    "FORMATTER_CONFIG_FILENAMES",
    "LINTER_CONFIG_FILENAMES",
    "WRAPPER_SCRIPT_FILENAMES",
    "TEST_CONFIG_FILENAMES",
    "CI_CONFIG_FILENAMES",
    "CONTRIBUTING_FILENAMES",
)

UNKNOWN_EVIDENCE = "unknown"


def _find_scaffold_state_scripts_dir(repo_root: Path) -> Optional[Path]:
    skill_dir = repo_root / ".github" / "skills" / OWNING_SKILL
    scripts_dir = skill_dir / "scripts"
    if not (scripts_dir / f"{_PROBE_MODULE_NAME}.py").exists():
        return None
    return scripts_dir


def _import_scaffold_state_module(repo_root: Path):
    scripts_dir = _find_scaffold_state_scripts_dir(repo_root)
    if scripts_dir is None:
        return None
    scripts_dir_str = str(scripts_dir)
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    return importlib.import_module(_PROBE_MODULE_NAME)


def _git_head_commit(repo_root: Path) -> Optional[str]:
    """Deliberate local duplicate of scaffold_state.py's own private
    `_git_head_commit` - never imported directly, see module docstring."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    sha = result.stdout.strip()
    return sha or None


def _signal_fingerprint(repo_root: Path, scaffold_state_module) -> list:
    """Top-level-only (non-recursive) `[name, mtime_ns]` pairs for every signal
    filename that actually exists at `repo_root`'s own top level. Sorted so the
    result is stable across runs (dict/set iteration order is not relied on)."""
    names = set()
    for const_name in _SIGNAL_FILENAME_CONSTANTS:
        names.update(getattr(scaffold_state_module, const_name, ()))
    fingerprint = []
    for name in sorted(names):
        candidate = repo_root / name
        try:
            if candidate.is_file():
                fingerprint.append([name, candidate.stat().st_mtime_ns])
        except OSError:
            continue
    return fingerprint


def _cache_key(repo_root: Path, scaffold_state_module) -> dict:
    return {
        "head": _git_head_commit(repo_root),
        "signals": _signal_fingerprint(repo_root, scaffold_state_module),
    }


def _read_cache(repo_root: Path) -> Optional[dict]:
    cache_path = repo_root / _CACHE_REL_PATH
    try:
        raw = cache_path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def _write_cache(repo_root: Path, key: dict, evidence: dict) -> None:
    cache_path = repo_root / _CACHE_REL_PATH
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"key": key, "evidence": evidence}
    waw.write_text_atomic(cache_path, json.dumps(payload, indent=2, sort_keys=True))


def _run_probe_with_budget(
    scaffold_state_module, repo_root: Path
) -> Optional[dict]:
    """Runs `probe_size()` on a daemon thread and waits up to
    `_PROBE_BUDGET_SECONDS`. Returns its result dict, or `None` if the budget
    was exceeded (the thread is left to finish on its own - see module
    docstring's "Budget" section)."""
    result_box: dict = {}

    def _target():
        try:
            result_box["value"] = scaffold_state_module.probe_size(repo_root)
        except Exception as exc:  # pragma: no cover - defensive, never let a
            # misbehaving cross-skill probe take the whole wizard request down;
            # treat it the same as "no usable evidence" rather than propagating.
            result_box["error"] = exc

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join(_PROBE_BUDGET_SECONDS)
    if thread.is_alive():
        return None
    if "error" in result_box:
        return None
    return result_box.get("value")


def get_evidence(repo_root) -> object:
    """Returns what `wizard_stub_content.what_how_card()`/`upgrade_card()`
    expect for their `evidence` kwarg: either the literal string `"unknown"`
    (owning skill not installed, cache unreadable and a fresh probe is over
    budget or errors, or `repo_root` isn't a git repo at all and no cache
    exists) or a dict carrying at least `grounded_viable`/`greenfield`, exactly
    `scaffold_state.probe_size()`'s own return shape.

    Cache hit (same HEAD, same signal-file fingerprint) skips the probe
    entirely. Cache miss or absent runs `probe_size()` fresh under the 1.5s
    budget, writes a new cache entry on success, and returns `UNKNOWN_EVIDENCE`
    on timeout or error without caching that negative result (so the very next
    call tries again rather than being stuck on "unknown" until something else
    invalidates the cache)."""
    repo_root = Path(repo_root).resolve()
    module = _import_scaffold_state_module(repo_root)
    if module is None:
        return UNKNOWN_EVIDENCE

    key = _cache_key(repo_root, module)
    cached = _read_cache(repo_root)
    if isinstance(cached, dict) and cached.get("key") == key:
        evidence = cached.get("evidence")
        if isinstance(evidence, dict):
            return evidence

    evidence = _run_probe_with_budget(module, repo_root)
    if evidence is None:
        return UNKNOWN_EVIDENCE

    try:
        _write_cache(repo_root, key, evidence)
    except waw.AtomicWriteError:
        # Cache is a pure optimization - a write failure (e.g. a read-only
        # checkout) never blocks handing the just-computed evidence back.
        pass
    return evidence
