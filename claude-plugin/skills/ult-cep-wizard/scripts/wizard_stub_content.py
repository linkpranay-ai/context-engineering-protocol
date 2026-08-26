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
case only." "Empty" means a directory that doesn't exist, or exists but contains no
files (after the usual CEP-bucket/ignored-name exclusions) - genuinely different from
"has no resolved path" (What-L2/How-L2 always resolve to *some* path, per
wizard_layout_source.py's own docstring; a fresh repo still shows `docs/requirements/`
as What's path even though that directory has nothing in it yet). `_has_content()`
below delegates to `wizard_box_files.list_files()` for that check rather than keeping
its own walk - `wizard_boxes.py` needs the exact same "what real files are under this
path" answer to populate each `BoxPath`'s file listing, so this is one real signal
shared by two callers, not two small independent helpers that happen to look alike
(contrast wizard_containment.py/wizard_tripwire.py's own docstrings, which duplicate
genuinely standalone helpers on purpose).

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
same two-sources-of-truth reasoning that already governed Guidelines. Trip-wire's
card (added later than the other three - see `tripwire_card()` below) is
different in kind from all of them: `decision_ledger.py` populates the ledger as a
derived/regenerable log of real events, so this module has no business generating
ledger *content* the way it points What/How/Guidelines at generating file content.
What it can still do is point the user at *starting* that human-in-the-loop process
- `ult-institutional-memory-distill` needs a human to choose and confirm real
source streams before it writes anything, and per that skill's own contract no
entry may ever be synthesized without evidence. `tripwire_card()` takes plain
scalars rather than importing `wizard_tripwire.TripwireSummary`, keeping this
module decoupled from that one's read path (same reasoning wizard_containment.py/
wizard_tripwire.py's own docstrings give for duplicating standalone helpers rather
than sharing a type across module boundaries).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wizard_box_files as wbf  # noqa: E402


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
    """Delegates to `wizard_box_files.list_files()` - see module docstring on why
    this is no longer a locally-duplicated walk."""
    return wbf.list_files(repo_root, rel_path).total_count > 0


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
        f"the {content_kind} to `{expected_path}` itself - coding-standards, "
        f"testing-guidelines, interface-boundary docs, tiered module depth, "
        f"whatever the skill's own scan decides this repo needs - no separate "
        f"prompt to write."
    )


def what_how_card(
    box_title: str,
    repo_root,
    resolved_paths: List[str],
    *,
    layer_decisions_pending: bool = False,
) -> Optional[StubCard]:
    """Returns a card iff every one of the box's resolved paths is currently empty
    (per `_has_content`) - a box with *any* real content is not the empty case
    §18.10 scopes this to, even if other resolved paths under it are still bare.
    Returns None for a box with no resolved paths at all (shouldn't happen for
    What-L2/How-L2, which always resolve to something - see module docstring - but
    handled defensively rather than assumed).

    `layer_decisions_pending` (default False, so every pre-existing caller and
    test that never dealt with D23 decisions keeps working unchanged): the
    caller passes True whenever any of this box's own What/How decision
    fields (L2 and/or its opt-in L1) is not yet `confirmed` - still `pending`
    or `staged` - in context-layout-discovery.md. Suppress the card in that
    case rather than build one: the box's *resolved* path right now is
    whatever was last confirmed (or the pre-Discover baseline default), and a
    still-pending decision means Apply may be about to change that path out
    from under the very instruction this card just handed the user - sending
    them to scaffold content at a path Discover already proposed replacing."""
    if layer_decisions_pending:
        return None
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


def tripwire_card(
    repo_root,
    *,
    available: bool,
    initialized: bool,
    entries: int,
    ledger_path: Optional[str],
) -> Optional[StubCard]:
    """Trip-wire's card is different in kind from the other three (see module
    docstring): decision-ledger population isn't something a skill can safely
    finish unattended. Unlike What/How/Guidelines' "run it, no separate prompt to
    write" framing, `ult-institutional-memory-distill` needs a human to choose and
    confirm which project-specific source streams (PR history, design docs,
    postmortems, ...) are actually trustworthy for this repo before it writes
    anything, and must never synthesize an entry without real evidence behind it.
    The card below is procedural guidance for starting that human-in-the-loop
    process, not an "it writes the file itself, unattended" promise - still the
    same `mode="agent-writes-in-place"` as the other three (the coding agent runs
    the skill and relays the human's choices; nothing here needs a new mode value),
    deliberately different prompt content.

    `repo_root` is accepted but unused, matching `guidelines_card()`'s own
    signature (kept for a consistent call shape across all four card builders at
    the wizard_server.py call site) - see that function for the same choice.

    Returns None when Trip-wire is unavailable (its owning skill isn't installed -
    the frontend's own `describeTripwire`/"not available" messaging already covers
    that case; a stub card here would just repeat it, and naming a skill the user
    can't act on through this card anyway) or already has real entries. Fires for
    both the "never initialized" and the "initialized but still empty" ledger case:
    an initialized-but-0-entries ledger is exactly as much of an onboarding dead
    end as a missing one, so `entries == 0` gates this independently of
    `initialized`.
    """
    if not available:
        return None
    if initialized and entries > 0:
        return None
    if not ledger_path:
        # Shouldn't happen - wizard_tripwire.read_summary() always sets ledger_path
        # when available=True - but handled defensively rather than assumed, same
        # posture what_how_card takes for an empty resolved_paths list above.
        return None
    return StubCard(
        box_title="Trip-wire",
        expected_path=ledger_path,
        prompt_text=(
            "Run the `ult-institutional-memory-distill` skill against this repo. "
            "Unlike the other boxes, this is not a \"run it and it writes the "
            "file for you\" step: you must choose and confirm which "
            "project-specific source streams (PR history, design docs, "
            "postmortems, ...) the skill should read before it writes anything "
            f"to `{ledger_path}`. No decision-ledger entry should ever be "
            "synthesized without real evidence behind it."
        ),
        expect_description=(
            f"A decision ledger at `{ledger_path}` with real entries, populated "
            "only from source streams you reviewed and confirmed - not "
            "auto-generated."
        ),
    )
