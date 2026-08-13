#!/usr/bin/env python3
"""wizard_preflight.py - fail-fast dependency gate for ult-cep-wizard (D24 §18.10
exit criterion 6; narrowed in Phase 2, §18.14).

Refuses to start the wizard server unless `ult-repo-layout` is genuinely installed in
the target repo. No socket is opened and no bootstrap token is generated until this
check passes - `wizard_server.py`'s `build_server()` calls `run_preflight()` before
doing anything else network-facing.

1. `ult-repo-layout` is present at all (`.github/skills/ult-repo-layout/SKILL.md`
   exists, plus `validate_layout.py` alongside it). Catches
   `install.ps1 -Only "ult-cep-wizard"` - a fully valid, unblocked install today,
   since neither install script enforces a cross-skill dependency graph.

Phase 2 (D24 §18.14) retired this module's old checks 2 and 3 - not softened, retired,
because check 2 (`_check_initialized`) tested the wrong axis entirely. It looked for
D20 slot-registry state (`project_layout` key / `.layout-slots.yaml` markers -
written by `ult-repo-layout`'s interactive `init`/`reconcile` flow), but this wizard's
own Decisions UI operates on the D23 discover/confirm-layers system
(`context-layout-discovery.md`) - confirmed by direct read that `confirm_layers.py`
never touches `project_layout` or any marker file. A repo that only ever ran
`discover`+`confirm-layers` (the real brownfield path) could never pass the old check
2, no matter how complete its setup was. Both retired checks' logic moved to
`wizard_onboarding_state.py`, which computes real per-request state
(`layout_broken`/`needs_discover`/`decisions_pending`/`steady_state`) instead of a
single startup-fatal gate - see
`references/wizard-onboarding-state-machine.md`. D20 initialization status is still
computed (relocated to `wizard_onboarding_state._is_d20_initialized`), but only as a
non-gating informational flag, never as a reason to refuse to start.

This module intentionally does not import `validate_layout.py` at all any more - check
1 is a pure filesystem-presence check, nothing about the target repo's *content*.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


class PreflightError(Exception):
    """Raised with an already-user-facing message. Callers print str(e) to
    stderr and exit nonzero - the exception's message *is* the UX, not a code."""


def _check_present(repo_root: Path) -> None:
    """Check 1: is `ult-repo-layout` installed at all in this repo?"""
    skill_dir = repo_root / ".github" / "skills" / "ult-repo-layout"
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        raise PreflightError(
            "ult-cep-wizard requires ult-repo-layout, but "
            f"{skill_md} was not found.\n"
            "If this was installed with `install.ps1 -Only \"ult-cep-wizard\"` "
            "(or the equivalent -Only flag on install.sh), ult-repo-layout was excluded "
            "from the install - re-run install with both skills included, e.g.:\n"
            '  install.ps1 -Only "ult-repo-layout,ult-cep-wizard"'
        )

    scripts_dir = skill_dir / "scripts"
    if not (scripts_dir / "validate_layout.py").exists():
        raise PreflightError(
            f"ult-repo-layout's SKILL.md exists ({skill_md}) but "
            f"{scripts_dir / 'validate_layout.py'} does not - the install looks "
            "partial or corrupted. Re-run install.ps1/install.sh for ult-repo-layout."
        )


def run_preflight(repo_root) -> None:
    """Runs the one remaining check. Raises PreflightError on failure with an
    already-user-facing message. Returns None (silently) on success - deliberately:
    no socket opens and no bootstrap token is printed by this module. Success is just
    "did not raise"."""
    repo_root = Path(repo_root).resolve()
    _check_present(repo_root)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_root", help="Target repo root to check.")
    args = parser.parse_args(argv)

    try:
        run_preflight(args.repo_root)
    except PreflightError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
