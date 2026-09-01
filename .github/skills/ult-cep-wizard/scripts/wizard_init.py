#!/usr/bin/env python3
"""wizard_init.py - UI-driven `init` orchestration, including the first-run
`workspace_root` namespacing offer (ISSUES.md Round 2 finding 9, 2026-08-31; see
references/wizard-onboarding-state-machine.md for how this fits the four-state
router).

Root-cause finding this module fixes: `layout.workspace_root` (D21 §16.x) - the
existing, already-mature config key that re-roots every registered slot's *default*
path under one namespace directory (e.g. `.cep/`), so CEP-generated/cache/state
artifacts stop sitting at generic repo-root names (`org/`, `contexts/`,
`starter_kit/`) that are indistinguishable from a project's own structure - has
always had a real backing mechanism (`validate_layout.run_init`) and a documented
conversational path through the CLI/agent-driven `init` skill, but no wizard-UI
equivalent. A human working entirely through the wizard never saw the option, never
saw a preview of the resulting tree, and had no way to accept or decline it before
the first `discover` ran. This module is the wizard-facing wrapper around
`validate_layout.run_init` that closes that gap: preview first (dry_run=True, zero
disk writes), then commit only on explicit confirmation (dry_run=False) - matching
`wizard_discover.py`'s own preview-then-real-call shape and this skill's standing
wizard-proposes/CLI-commits invariant (the deterministic script is the only thing
that ever writes; the wizard only calls it).

Two distinct refusals, both surfaced as `InitError` (own exception class per this
skill's standing independent-hierarchy precedent - see wizard_discover.py's
docstring for why `DiscoverError`/`ApplyError`/`InitError` are kept separate rather
than sharing a base):

1. **Invalid or already-set workspace_root** - `validate_layout.run_init` itself
   refuses (`--workspace-root` well-formedness, S22 repo-root check, the
   never-silently-reset rule when `layout.workspace_root` is already set). Its exit
   code and messages are the single source of truth for what "invalid" means here -
   this module does not re-implement any of those checks.
2. **Already D20-initialized** - `run_init` refuses unconditionally (except a repeat
   `ci_hook=True`-only call, not exposed through this module at all). The wizard's
   own `wizard_onboarding_state.compute_state()` is expected to have already gated
   this via `workspace_root_offer_eligible` before ever presenting the offer; this
   module's refusal is the defensive backstop, not the primary router.
"""
from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


class InitError(Exception):
    """Base class for any preview_init/run_init refusal - already-user-facing
    message (verbatim from validate_layout.run_init's own messages list)."""


@dataclass
class InitResult:
    messages: List[str] = field(default_factory=list)


def _find_repo_layout_scripts_dir(repo_root) -> Path:
    """Same lookup wizard_discover.py's/wizard_apply.py's/wizard_layout_source.py's
    own (private) versions do - duplicated for the same independent-usability reason
    those already duplicate it from each other."""
    scripts_dir = Path(repo_root) / ".github" / "skills" / "ult-repo-layout" / "scripts"
    if not (scripts_dir / "validate_layout.py").exists():
        raise InitError(
            f"ult-repo-layout's validate_layout.py was not found under "
            f"{scripts_dir} - is ult-repo-layout installed in this repo?"
        )
    return scripts_dir


def _import_validate_layout(repo_root):
    scripts_dir_str = str(_find_repo_layout_scripts_dir(repo_root))
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    return importlib.import_module("validate_layout")


def _clean_workspace_root(workspace_root: Optional[str]) -> Optional[str]:
    """A blank/whitespace-only value from the frontend's text input means "no
    namespacing, use pre-D21 defaults" - the same as never passing
    --workspace-root on the CLI. Only a non-empty string is forwarded to
    `run_init`, which owns all real well-formedness validation."""
    if workspace_root is None:
        return None
    cleaned = workspace_root.strip()
    return cleaned or None


def preview_init(repo_root, workspace_root: Optional[str] = None) -> InitResult:
    """Dry-run preview (zero disk writes) of what `run_init` would do with this
    `workspace_root` - the tree/messages the wizard shows before the human commits.
    Raises `InitError` on any refusal (invalid workspace_root, already
    initialized, no installed slot's owning skill present)."""
    repo_root = Path(repo_root).resolve()
    vl = _import_validate_layout(repo_root)
    code, messages = vl.run_init(
        repo_root, workspace_root=_clean_workspace_root(workspace_root), dry_run=True
    )
    if code != 0:
        raise InitError("; ".join(messages))
    return InitResult(messages=messages)


def run_init(repo_root, workspace_root: Optional[str] = None) -> InitResult:
    """The real, committing call - identical inputs/shape to `preview_init`, but
    `dry_run=False`. The frontend is expected to have already shown the human the
    matching `preview_init` output for the same `workspace_root` value before
    calling this (mirrors wizard_apply.py's stage-then-apply two-step, adapted to
    init's own preview-then-commit shape rather than a freshness-hash check, since
    there is no prior artifact here to drift)."""
    repo_root = Path(repo_root).resolve()
    vl = _import_validate_layout(repo_root)
    code, messages = vl.run_init(
        repo_root, workspace_root=_clean_workspace_root(workspace_root), dry_run=False
    )
    if code != 0:
        raise InitError("; ".join(messages))
    return InitResult(messages=messages)
