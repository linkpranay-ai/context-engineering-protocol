#!/usr/bin/env python3
"""wizard_stub_content.py - "Run this yourself" preview cards for the empty case
only (D24 §18.6/§18.10, locked).

**Pure preview, zero filesystem writes.** This module contains no `write_text`,
`os.replace`, or any other mutating call anywhere - it only ever builds and returns
`StubCard` values describing what a user *could* paste into their coding agent.
Phase 0 registers zero mutating routes anywhere in wizard_server.py (§18.7, §18.10);
if this module ever grows a write call, that is a Phase-1-or-later change, not a
Phase 0 one, and should not land here without the accompanying §18.2b write-path
security spec (see wizard_atomic_write.py's own docstring).

§18.10 scopes this precisely: "`ult-scaffold-content` generates for the **empty**
case only." §18.3/discover_layers.py's own `_has_content()` is the signal for
"empty" - a directory that doesn't exist, or exists but contains no files (after the
usual CEP-bucket/ignored-name exclusions) - genuinely different from "has no
resolved path" (What-L2/How-L2 always resolve to *some* path, per
wizard_layout_source.py's own docstring; a fresh repo still shows `docs/requirements/`
as What's path even though that directory has nothing in it yet). This module
duplicates a minimal version of that content-check locally rather than reaching into
`discover_layers.py`'s underscore-prefixed internals through wizard_layout_source's
already-imported module handle - same "each module owns its own copy, usable
standalone" reasoning wizard_containment.py/wizard_tripwire.py's own docstrings give
for their independent duplicated helpers.

§18.6 designs two handoff modes for generative steps, but only one is meaningfully
previewable in Phase 0: **agent-writes-in-place** (the coding agent, which already
has ordinary filesystem access to the repo, writes the file directly; the wizard
later re-reads the expected path on an explicit "Check now" click). The other mode,
**paste-back**, ends with "the wizard writes the content to the resolved target path
itself, through the same write endpoint" - that endpoint does not exist until Phase
1, so a Phase-0 paste-back card would end in a dead affordance. This module therefore
only builds agent-writes-in-place cards. All three boxes now converge on the same
card shape (D24 Phase D): each card's `prompt_text` points at running a real skill
rather than authoring a freeform generation prompt this module would have to keep
in sync with that skill's own `SKILL.md` by hand. Guidelines points at
`compiling-project-guidelines` (its content is a compiled artifact, not prose a
user asks an agent to freehand). What/How point at `ult-autoscaffold-content`, once
it existed to point at - `_what_how_prompt()` used to author the What/How prompt
text inline; that's superseded outright as of Phase D, no fallback kept, per the
same two-sources-of-truth reasoning that already governed Guidelines. Trip-wire has
no card at all - it's a derived/regenerable log populated by `decision_ledger.py` as
things happen, not authored content (same reasoning `wizard_tripwire.py`'s own
docstring gives for treating it as read-only-derived).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

# Mirrors discover_layers.py's own SCAN_IGNORED_DIR_NAMES-class pruning closely enough
# for a "does this look empty" preview signal - not required to be bit-for-bit
# identical, since a false "not empty" here only means the wizard skips offering a
# card that would have been slightly premature, never a correctness/safety issue
# (contrast wizard_containment.py, where an under-inclusive check would be a real
# security gap).
_IGNORED_NAMES = frozenset(
    {".git", "__pycache__", ".DS_Store", "Thumbs.db", ".gitkeep"}
)


@dataclass
class StubCard:
    box_title: str  # "What" | "How" | "Guidelines"
    expected_path: str  # repo-relative, POSIX-style - where the generated content
    # should land, dictated to the agent explicitly (§18.6 round-3 M5 fix: never left
    # to the agent's discretion, so a later "Check now" click has a real path to test).
    prompt_text: str  # copy-button block - plain text, agent-agnostic (§18.6).
    expect_description: str  # plain-language statement of what should come back.
    mode: str = "agent-writes-in-place"  # the only mode Phase 0 previews (see module
    # docstring) - carried on the card so the frontend never has to hardcode it and
    # a future Phase-1 paste-back card is a value this field can simply also take.


def _has_content(repo_root: Path, rel_path: str) -> bool:
    """Local, minimal existence+non-empty check - see module docstring on why this
    is duplicated rather than imported."""
    target = repo_root / rel_path.rstrip("/")
    if not target.is_dir():
        return False
    for entry in target.rglob("*"):
        if entry.is_file() and entry.name not in _IGNORED_NAMES:
            return True
    return False


def _what_how_prompt(box_title: str, expected_path: str) -> str:
    """Points at running `ult-autoscaffold-content` rather than authoring a freeform
    generation prompt inline (D24 Phase D, mirrors `guidelines_card()`'s shape below).
    Unconditional - this module never checks whether the skill is actually installed
    before naming it, same as `guidelines_card()` doesn't for
    `compiling-project-guidelines`; a missing skill is a fail-fast case for whatever
    the user pastes this into, not a reason to keep the old freeform prompt alive as
    a silent fallback."""
    content_kind = (
        "requirements/specs documentation"
        if box_title == "What"
        else "architecture/conventions documentation"
    )
    return (
        f"Run the `ult-autoscaffold-content` skill against this repo. It writes "
        f"the {content_kind} to `{expected_path}` itself - no separate prompt to "
        f"write."
    )


def what_how_card(box_title: str, repo_root, resolved_paths: List[str]) -> Optional[StubCard]:
    """Returns a card iff every one of the box's resolved paths is currently empty
    (per `_has_content`) - a box with *any* real content is not the empty case
    §18.10 scopes this to, even if other resolved paths under it are still bare.
    Returns None for a box with no resolved paths at all (shouldn't happen for
    What-L2/How-L2, which always resolve to something - see module docstring - but
    handled defensively rather than assumed)."""
    if not resolved_paths:
        return None
    repo_root = Path(repo_root).resolve()
    if any(_has_content(repo_root, p) for p in resolved_paths):
        return None

    expected_path = resolved_paths[0]
    return StubCard(
        box_title=box_title,
        expected_path=expected_path,
        prompt_text=_what_how_prompt(box_title, expected_path),
        expect_description=(
            f"A new file (or a small set of files) under `{expected_path}`, "
            f"non-empty, in your coding agent's usual writing style."
        ),
    )


def guidelines_card(repo_root, initialized: bool, default_path: str) -> Optional[StubCard]:
    """Guidelines' card is different in kind from What/How's (see module docstring):
    it points at running the `compiling-project-guidelines` skill, not a freeform
    prompt this module authors itself - that skill owns its own generation logic,
    this module has no business paraphrasing it into a prompt block."""
    if initialized:
        return None
    return StubCard(
        box_title="Guidelines",
        expected_path=default_path,
        prompt_text=(
            "Run the `compiling-project-guidelines` skill against this repo. It "
            f"compiles the project's guidelines to `{default_path}` itself - no "
            f"separate prompt to write."
        ),
        expect_description=f"A new, non-empty file at `{default_path}`.",
    )
