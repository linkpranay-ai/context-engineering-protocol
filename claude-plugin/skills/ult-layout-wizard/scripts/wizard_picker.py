#!/usr/bin/env python3
"""wizard_picker.py - server-rendered directory picker for ult-layout-wizard (D24
§18.7 / S1, locked).

S1 locked a server-rendered picker over drag-and-drop: the browser never receives a
raw filesystem listing to render client-side JS against - every directory this module
returns has already passed `wizard_containment.check_containment`, so there is no path
the frontend can construct that escapes the affirmed root; the server is the only
thing that ever walks the filesystem.

GET-only, deliberately: this module has exactly one public entry point
(`list_directory`) and defines no write/delete/create function anywhere - Phase 0 is
read-only-by-design (§18.10), and `wizard_server.py` must never be able to wire a
mutating route to anything in this file because nothing mutating exists here to wire.

Filtering (hidden dirs, `node_modules`/`.git`/build-output-shaped names) is a display
convenience only, not a security boundary - it reduces picker noise so a user isn't
scrolling past `.git` and `node_modules` on every repo. The actual security boundary
is `check_containment` plus the symlinked-child skip below (both fail-closed);
narrowing what's *listed* never widens what's reachable.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wizard_containment  # noqa: E402

# Display-filter only (see module docstring) - not exhaustive, not a security list.
EXCLUDED_DIR_NAMES = frozenset(
    {
        "node_modules",
        ".git",
        "dist",
        "build",
        "out",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".venv",
        "venv",
        "env",
    }
)


class PickerError(Exception):
    """Raised for any request the picker won't serve - containment failure, a
    non-directory target, or an unreadable directory. Always a user-facing message,
    never a raw traceback."""


@dataclass
class PickerEntry:
    name: str
    rel_path: str  # POSIX-style, relative to the affirmed root


@dataclass
class PickerResult:
    rel_path: str  # the listed directory itself, POSIX-style, "." at the root
    parent_rel_path: Optional[str]  # None only when rel_path is the root itself
    entries: List[PickerEntry] = field(default_factory=list)


def _is_hidden_or_excluded(name: str) -> bool:
    return name.startswith(".") or name in EXCLUDED_DIR_NAMES


def list_directory(affirmed_root, rel_path: str = ".") -> PickerResult:
    """The only public function in this module (see module docstring). Lists the
    immediate subdirectories of `rel_path` (relative to `affirmed_root`) - files are
    never returned, since this picker exists to let a user point at a directory, not
    browse file contents."""
    root = Path(affirmed_root).resolve()
    try:
        target = wizard_containment.check_containment(root, rel_path)
    except wizard_containment.ContainmentError as exc:
        raise PickerError(str(exc)) from exc

    if not target.is_dir():
        raise PickerError(f"'{rel_path}' is not a directory.")

    try:
        children = sorted(target.iterdir(), key=lambda p: p.name.casefold())
    except OSError as exc:
        raise PickerError(f"could not list '{rel_path}': {exc}") from exc

    entries: List[PickerEntry] = []
    for child in children:
        if not child.is_dir():
            continue
        if wizard_containment.component_is_containment_violation(child):
            # A symlinked/junctioned subdirectory is invisible to the picker, not
            # just unselectable - same fail-closed posture as check_containment
            # itself, applied one level early so the UI never even offers it.
            continue
        if _is_hidden_or_excluded(child.name):
            continue
        entries.append(
            PickerEntry(name=child.name, rel_path=child.relative_to(root).as_posix())
        )

    norm_rel = target.relative_to(root).as_posix()
    parent_rel = None
    if target != root:
        parent_rel = target.parent.relative_to(root).as_posix()

    return PickerResult(rel_path=norm_rel, parent_rel_path=parent_rel, entries=entries)
