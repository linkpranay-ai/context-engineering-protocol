#!/usr/bin/env python3
"""wizard_stub_content.py - "Run this yourself" preview cards for the empty case
only (D24 §18.6/§18.10, locked).

**Pure preview, zero filesystem writes.** This module contains no `write_text`,
`os.replace`, or any other mutating call anywhere - it only ever builds and returns
`StubCard` values describing what a user *could* paste into their coding agent. That
stays true even though `wizard_server.py` itself has, since Phase 1, grown real
mutating routes (`/api/stage`, `/api/apply`, `/api/discover`, and others) backed by
`wizard_atomic_write.write_text_atomic()` elsewhere in the skill - this module in
particular was never one of their callers and was never meant to be. If this module
ever grows a write call, it should use that same already-landed §18.2b write-path
primitive (see wizard_atomic_write.py) rather than inventing a new one.

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
supported here: **agent-writes-in-place** (the coding agent, which already has
ordinary filesystem access to the repo, writes the file directly; the wizard later
re-reads the expected path on an explicit "Check now" click). The other mode,
**paste-back**, ends with "the wizard writes the content to the resolved target path
itself, through the same write endpoint" - no route does that for box content today
(the live mutating routes commit staged decisions, apply a specific retrofit edit, or
run discovery; none of them accepts pasted-back generated content and writes it to a
box's resolved target path), so a paste-back card here would end in a dead
affordance. This module therefore only builds agent-writes-in-place cards.
All three boxes now converge on the same
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

P1 adds a second, narrower generative affordance (Proposal Sec 9.4/10/12): a W1
mode selector on every What/How card (`content_modes`/`default_mode` - which of
`ult-autoscaffold-content`'s skeleton/grounded/augmented content modes are
currently viable, per that skill's own `scaffold_state.MODE_CAP_BY_LAYER_KIND`
ceiling), and a distinct "Upgrade drafts" card (`upgrade_card()`) for the
opposite case `what_how_card()` doesn't cover at all: a path that already has
content, every byte of which is still an untouched autoscaffold-content draft.
Both stay inside this module's pure-preview/zero-write contract - `evidence` is
a plain, caller-supplied dict (or the string `"unknown"`), never computed here;
wizard_server.py's own lazy, cached probe (TASK-0403) is the only thing that
ever calls into `ult-autoscaffold-content`'s `scaffold_state.probe_size()`.
Likewise, draft detection reads each candidate file's YAML frontmatter with a
small local parser (`_frontmatter_fields()`) deliberately duplicated from
`scaffold_state._parse_frontmatter()` rather than imported - same "two
genuinely standalone readers of the same shape, not one shared dependency"
reasoning this module already gives above for `tripwire_card()`'s scalars.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wizard_box_files as wbf  # noqa: E402

# How many files upgrade_card() will enumerate under a resolved path before
# giving up and suppressing the card (see upgrade_card's own docstring on why
# truncation means "can't prove every file is a draft" rather than "assume
# the rest are"). Higher than wizard_box_files.MAX_FILES_PER_PATH's UI-display
# default of 40 - this isn't rendering a list to a human, it's deciding
# whether an unconditional claim ("every file here is a draft") is provable,
# so it should tolerate a real small-to-medium repo's module count before
# conservatively bailing.
_UPGRADE_SCAN_LIMIT = 500

# The content modes `ult-autoscaffold-content` can resolve a layer to
# (scaffold_state.CONTENT_MODES), duplicated here as display labels rather
# than imported - this module never imports that skill's code (see module
# docstring), only ever receives its evidence as a plain dict from a caller.
_MODE_LABELS = {
    "skeleton": "Skeleton (fast, no LLM)",
    "grounded": "Grounded",
    "augmented": "Augmented",
}

# Per scaffold_state.MODE_CAP_BY_LAYER_KIND, every What-L2 (layer, kind) pair
# caps at "grounded" - "augmented" is never offered for What, not just marked
# unavailable (Proposal Sec 10: "For What-L2 ... augmented isn't shown").
# How-L2 can reach "augmented" for coding_standards/testing_guidelines, so its
# selector always offers all three; evidence-availability (below) decides
# which of grounded/augmented are actually selectable for a given repo.
_MODE_IDS_BY_BOX = {
    "What": ("skeleton", "grounded"),
    "How": ("skeleton", "grounded", "augmented"),
}


def _grounded_evidence_availability(box_title: str, evidence) -> Tuple[bool, Optional[str]]:
    """Whether `grounded`/`augmented` content modes are usable for this box,
    per the `evidence` a caller optionally passes (wizard_server.py's lazy,
    cached `scaffold_state.probe_size()` result - TASK-0403; this module
    never computes it itself). `evidence` is one of:

    - `"unknown"` (the default - no caller, or the probe hasn't completed /
      timed out): unavailable, reason says so plainly.
    - a dict shaped like `probe_size()`'s return value (`greenfield: bool`,
      `grounded_viable: {kind: bool}`): unavailable with a specific reason
      for a greenfield repo or one with no viable grounded-mode evidence yet
      for this box's relevant kind(s); available otherwise.

    Both `grounded` and `augmented` share this same signal for a given box -
    reaching `augmented` already presupposes a usable grounded base, so a
    second, separate availability check for `augmented` would just repeat
    this one. Documented simplification, not an oversight."""
    if evidence == "unknown" or not isinstance(evidence, dict):
        return False, "unknown: evidence probe unavailable or timed out"
    if evidence.get("greenfield"):
        return False, "repo is greenfield - not enough commit history/signals yet"
    grounded_viable = evidence.get("grounded_viable") or {}
    if box_title == "What":
        viable = bool(grounded_viable.get("requirements_overview"))
    else:
        viable = bool(
            grounded_viable.get("coding_standards")
            or grounded_viable.get("testing_guidelines")
        )
    if not viable:
        return False, "no grounded-mode evidence found for this layer yet"
    return True, None


def _mode_options(box_title: str, evidence) -> List[dict]:
    """Builds the `content_modes` list for a What/How card. `box_title` must
    be "What" or "How" - Guidelines/Trip-wire never call this, they have no
    content-mode concept (their cards keep `content_modes=[]`)."""
    options: List[dict] = []
    for mode_id in _MODE_IDS_BY_BOX[box_title]:
        if mode_id == "skeleton":
            options.append(
                {"id": mode_id, "label": _MODE_LABELS[mode_id], "available": True, "reason": None}
            )
            continue
        available, reason = _grounded_evidence_availability(box_title, evidence)
        options.append(
            {"id": mode_id, "label": _MODE_LABELS[mode_id], "available": available, "reason": reason}
        )
    return options


def _default_mode(box_title: str, content_modes: List[dict]) -> str:
    """"grounded" if available for How (What never defaults past "skeleton" -
    Proposal Sec 10), else "skeleton" - which is always available (it needs
    no evidence), so this never falls through to no default at all."""
    preferred = "grounded" if box_title == "How" else "skeleton"
    by_id = {opt["id"]: opt for opt in content_modes}
    if by_id.get(preferred, {}).get("available"):
        return preferred
    return "skeleton"


def _frontmatter_fields(path: Path) -> dict:
    """Minimal `key: value` frontmatter reader, deliberately duplicated from
    `scaffold_state._parse_frontmatter()` rather than imported (see module
    docstring) - same algorithm, including its most load-bearing edge case:
    a missing closing `---` returns `{}` (no partial dict), so a file that
    merely starts with a stray `---` line is never misread as having real
    frontmatter. Returns `{}` for anything unreadable (missing file, not
    UTF-8, no frontmatter at all) - callers treat that the same as "not a
    draft," never as an error."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}
    frontmatter: dict = {}
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
        if ":" in lines[i]:
            key, _, value = lines[i].partition(":")
            frontmatter[key.strip()] = value.strip()
    if end is None:
        return {}
    return frontmatter


@dataclass
class StubCard:
    box_title: str  # "What" | "How" | "Guidelines"
    expected_path: str  # repo-relative, POSIX-style - where the generated content
    # should land, dictated to the agent explicitly (§18.6 round-3 M5 fix: never left
    # to the agent's discretion, so a later "Check now" click has a real path to test).
    prompt_text: str  # copy-button block - plain text, agent-agnostic (§18.6).
    expect_description: str  # plain-language statement of what should come back.
    mode: str = "agent-writes-in-place"  # the only mode this module builds cards for
    # (see module docstring: no live route writes pasted-back content to a box's
    # target path) - carried on the card so the frontend never has to hardcode it,
    # and a future paste-back card is a value this field can simply also take if a
    # route for it is ever added.
    card_kind: str = "scaffold"  # "scaffold" (what_how_card/guidelines_card/
    # tripwire_card) | "upgrade" (upgrade_card). The frontend needs this to pick
    # the right affordance for a box's single stub-card slot (D24's `renderStubCards`
    # keys on `box_title` alone, one card per box - see wizard.js) without having to
    # infer which builder produced it from field presence.
    content_modes: List[dict] = field(default_factory=list)  # [{id, label,
    # available, reason}, ...] - empty for Guidelines/Trip-wire (they have no
    # content-mode concept); populated for every What/How scaffold-or-upgrade
    # card by `_mode_options()` below, from the optional `evidence` a caller
    # passes into `what_how_card`/`upgrade_card`.
    default_mode: Optional[str] = None  # one of content_modes' ids, or None
    # when content_modes is empty (Guidelines/Trip-wire).
    draft_files: List[str] = field(default_factory=list)  # upgrade_card only -
    # the repo-relative draft files it found under the resolved path(s); always
    # empty for a scaffold-kind card.


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
    evidence="unknown",
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
    them to scaffold content at a path Discover already proposed replacing.

    `evidence` (default `"unknown"`, so every pre-existing caller/test keeps
    working unchanged): optionally the caller's `scaffold_state.probe_size()`
    result (a plain dict - this module never imports that function itself,
    see module docstring), used only to populate the card's
    `content_modes`/`default_mode` (P1 W1 mode selector, Proposal Sec 10)."""
    if layer_decisions_pending:
        return None
    if not resolved_paths:
        return None
    repo_root = Path(repo_root).resolve()
    if any(_has_content(repo_root, p) for p in resolved_paths):
        return None

    expected_path = resolved_paths[0]
    content_modes = _mode_options(box_title, evidence)
    return StubCard(
        box_title=box_title,
        expected_path=expected_path,
        prompt_text=_what_how_prompt(box_title, expected_path),
        expect_description=(
            f"A new file (or a small set of files) under `{expected_path}`, "
            f"non-empty, in your coding agent's usual writing style."
        ),
        content_modes=content_modes,
        default_mode=_default_mode(box_title, content_modes),
    )


def guidelines_card(
    repo_root,
    initialized: bool,
    default_path: str,
    *,
    layer_decisions_pending: bool = False,
) -> Optional[StubCard]:
    """Guidelines' card is different in kind from What/How's (see module docstring):
    it points at running the `compiling-project-guidelines` skill, not a freeform
    prompt this module authors itself - that skill owns its own generation logic,
    this module has no business paraphrasing it into a prompt block.

    `layer_decisions_pending` (default False, same "every pre-existing caller
    keeps working unchanged" posture what_how_card's own parameter has):
    the caller passes True whenever either the What or How layer's own
    decision fields are not yet confirmed. Guidelines compilation reads
    from whatever What/How currently resolve to, so pointing a user at it
    while either is still mid-decision risks the same
    prompt-content-becomes-stale-the-moment-Apply-runs problem
    what_how_card's own docstring describes - suppress the card here for
    the same reason, not a different one."""
    if layer_decisions_pending:
        return None
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
    layer_decisions_pending: bool = False,
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

    `layer_decisions_pending` (default False, same posture as
    `guidelines_card`'s own parameter): decision-ledger entries are meant to
    capture real institutional-memory context about this repo's actual
    layout, and a still-pending What/How decision means that layout is
    itself about to change - suppress the card until it settles, same
    reasoning as `guidelines_card` and `what_how_card`.
    """
    if layer_decisions_pending:
        return None
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


def upgrade_card(
    box_title: str,
    repo_root,
    resolved_paths: List[str],
    *,
    layer_decisions_pending: bool = False,
    evidence="unknown",
) -> Optional[StubCard]:
    """The opposite case from `what_how_card()`: a resolved What/How path that
    already has content, every byte of which is still an untouched
    `ult-autoscaffold-content` draft (Proposal Sec 9.4/10 - eval case 13).
    Returns a card only when *every* file found under every resolved path
    carries `generated_by: ult-autoscaffold-content` and `status: draft` in
    its frontmatter; any finalized file, any file with no frontmatter at all
    (a human wrote it, or edited a draft enough to strip the markers), or an
    empty directory suppresses the card entirely - same all-or-nothing
    posture `what_how_card()` takes for "any resolved path has content"
    above, just inverted.

    A truncated file listing (more files than `_UPGRADE_SCAN_LIMIT`)
    suppresses the card too: this function can only ever claim "every file
    here is a draft," and a truncated listing means it never actually looked
    at all of them - conservative by construction, matching this module's
    posture elsewhere (`what_how_card`'s own defensive `not resolved_paths`
    branch).

    `layer_decisions_pending`/`evidence` mean exactly what they mean on
    `what_how_card()` - a still-pending What/How decision suppresses this
    card for the same "the resolved path might be about to change out from
    under this instruction" reason, and `evidence` only ever feeds
    `content_modes`/`default_mode`, never the draft-detection logic above."""
    if layer_decisions_pending:
        return None
    if not resolved_paths:
        return None
    repo_root = Path(repo_root).resolve()

    found_files: List[str] = []
    for rel_path in resolved_paths:
        listing = wbf.list_files(repo_root, rel_path, limit=_UPGRADE_SCAN_LIMIT)
        if listing.truncated:
            return None
        for name in listing.files:
            found_files.append((Path(rel_path.rstrip("/")) / name).as_posix())
    if not found_files:
        return None

    for rel in found_files:
        fields = _frontmatter_fields(repo_root / rel)
        if fields.get("generated_by") != "ult-autoscaffold-content":
            return None
        if fields.get("status") != "draft":
            return None

    expected_path = resolved_paths[0]
    content_modes = _mode_options(box_title, evidence)
    return StubCard(
        box_title=box_title,
        expected_path=expected_path,
        prompt_text=(
            "Run the `ult-autoscaffold-content` skill against this repo in "
            "upgrade mode: regenerate every untouched draft under "
            f"`{expected_path}` at the chosen content mode, and write a "
            "proposal under `cache/autoscaffold-content/proposed/` for any "
            "draft a human has since edited, rather than overwriting it."
        ),
        expect_description=(
            f"Every untouched draft under `{expected_path}` regenerated in "
            "place at the chosen content mode; any draft you've since "
            "edited left alone, with a separate proposal for it instead."
        ),
        content_modes=content_modes,
        default_mode=_default_mode(box_title, content_modes),
        card_kind="upgrade",
        draft_files=sorted(found_files),
    )
