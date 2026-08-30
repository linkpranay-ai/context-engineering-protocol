#!/usr/bin/env python3
"""wizard_layout_source.py - the two-source read model for ult-cep-wizard (D24
§18.2b/§18.3, locked).

ult-repo-layout's resolved state lives in two genuinely different places, not one:

  1. Nine marker-derived path-slots (`SLOT_REGISTRY` in validate_layout.py), resolved
     from `.layout-slots.yaml` marker files scattered through the repo.
  2. Four CEP layer keys (`layers.what_l2`, `layers.what_l1`, `how_dimension.how_l2`,
     `how_dimension.how_l1`), resolved straight from `context-config.yaml` - these
     have no marker file of their own; `discover_layers.py`'s `TITLE_TO_BASE_KEY`
     is what maps each layer's human title to its dotted config key.

Both are re-derived fresh on every `read_slots()`/`read_layers()` call, never cached:
a user can edit `context-config.yaml` or add/move a marker file in another
terminal/editor while the wizard tab stays open, and the visual boxes (a later build
step) must reflect that on the very next read, not a stale snapshot from when the
server started. This is the opposite of most local dev-server patterns (which
typically cache config at startup for performance) - deliberate here, since
staleness in a tool whose whole job is showing "what does ult-repo-layout currently
think" would be actively misleading.

Every actual resolution rule below is reused directly from validate_layout.py's own
resolver functions (`resolve_default`, `resolved_path_for_marker`,
`resolve_what_l2_path`, `resolve_what_l2_include_roots`, `resolve_how_l2_path`,
`resolve_what_l1_path`/`resolve_what_l1_enabled`, `resolve_how_l1_path`/
`resolve_how_l1_enabled`) rather than reimplemented here - staying bit-for-bit in
sync with the real resolution logic (workspace_root-relative defaults, pre-D21
fallback defaults, opt-in-layer-with-no-path-has-nothing-to-resolve) beats risking
drift from a hand-copied paraphrase, same reasoning wizard_preflight.py documents for
reusing `_owning_skill_installed` directly.

`validate_layout.py --validate` is checked once, at construction time
(`LayoutSource.__init__`), not per-request - if the repo's layout is broken, that's a
one-time refusal-to-serve-at-all decision. This module re-checks it independently of
wizard_preflight.py's own check 3 (not because Phase 0's server skips preflight - it
doesn't - but so `LayoutSource` is safe to use standalone by anything that constructs
it directly without going through wizard_server.py's startup path, e.g. the
`wizard-e2e` CI job in a later build step).
"""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


class LayoutSourceError(Exception):
    """Raised at construction time if the target repo's layout doesn't validate
    clean - an already-user-facing message."""


@dataclass
class SlotState:
    slot: str
    owning_skill: str
    initialized: bool  # True if at least one `.layout-slots.yaml` marker registers
    # this slot - False means resolved_paths is empty and default_path is a
    # not-yet-registered fallback, not a real resolved location.
    resolved_paths: List[str]  # relative, POSIX-style; may contain more than one
    # entry (a slot can have more than one marker - multi-root, same as the layer
    # keys below).
    default_path: str  # always computed (resolve_default never returns None), even
    # when initialized is True - shown alongside resolved_paths so a stale/removed
    # marker's fallback is visible too, not just its absence.


@dataclass
class DecisionField:
    """One decision-bearing line's current display state, for /api/decisions
    (D24 Phase 1). Deliberately a display-state summary, not a resolved
    `confirm_layers.Field` - `state` is derived the same lightweight way
    `wizard_decision_staging.stage_decision`'s own PENDING/CONFIRMED-stamp
    checks are (CONFIRMED_STAMP_RE on the comment vs. raw_value == "PENDING"),
    not by calling `.resolve()` - a still-malformed field must still be
    listed here, not raise and take the whole read route down with it.
    `apply_confirmed` (wizard_apply.py) is where resolution and its errors
    actually gate anything."""

    section_title: str
    field_key: str  # confirm_layers.Field.key - "decision",
    # "include_roots_decision", "exclude_decision", "collision_decision", or
    # "enable"
    line_no: int  # 0-based, matches confirm_layers.Field.line_no exactly -
    # callers pass this straight back to stage_decision's own line_no
    # disambiguation parameter when more than one candidate shares
    # (section_title, field_key).
    raw_value: str
    comment: Optional[str]
    state: str  # "pending" | "staged" | "confirmed"
    allowed_verbs: List[str]  # [] once state == "confirmed" (nothing left to
    # offer); the verbs parse_comment_clauses finds in `comment` otherwise.
    layer: frozenset = field(default_factory=frozenset)  # {"what"}, {"how"},
    # {"what", "how"} (COLLISION_TITLE and any re-discovery of it), or an
    # empty frozenset for a section_title layout_decision_grammar.
    # resolve_section_layer() doesn't recognize - from
    # layout_decision_grammar.resolve_section_layer(section_title), not a
    # `section_title.startswith(...)` guess (see that function's docstring
    # for exactly which false negatives that guess had).


@dataclass
class LayerState:
    key: str  # dotted context-config.yaml key, e.g. "layers.what_l2"
    title: str  # human title, from discover_layers.py's TITLE_TO_BASE_KEY
    enabled: bool  # always True for the two always-on layers (What-L2/How-L2);
    # reflects the real opt-in flag for What-L1/How-L1.
    path: Optional[str]  # None only for an opt-in layer with nothing configured yet
    include_roots: List[str] = field(default_factory=list)  # only ever non-empty for
    # What-L2 - the other three layer keys have no include_roots concept.

    @property
    def resolved_paths(self) -> List[str]:
        """The paths this layer box should actually display: nothing at all if the
        layer is disabled or has no path resolved yet, else the primary path plus any
        include_roots (multi-root, same shape as SlotState.resolved_paths)."""
        if not self.enabled or self.path is None:
            return []
        return [self.path, *self.include_roots]


def _find_repo_layout_scripts_dir(repo_root: Path) -> Path:
    """Same lookup wizard_preflight.py's own (private) version does. Duplicated
    rather than imported from it: that function is name-prefixed as module-internal
    to wizard_preflight.py, and this module has an independent reason to need its own
    copy - it must be usable standalone, without wizard_preflight having already run
    in the same process (see module docstring)."""
    scripts_dir = repo_root / ".github" / "skills" / "ult-repo-layout" / "scripts"
    if not (scripts_dir / "validate_layout.py").exists():
        raise LayoutSourceError(
            f"ult-repo-layout's validate_layout.py was not found under "
            f"{scripts_dir} - is ult-repo-layout installed in this repo?"
        )
    return scripts_dir


def _import_repo_layout_modules(repo_root: Path):
    """Returns (validate_layout, discover_layers, layout_decision_grammar,
    confirm_layers). The latter two were added in D24 Phase 1: the write path
    (wizard_decision_staging.py, wizard_apply.py) needs layout_decision_grammar's
    line grammar directly (not indirected through discover_layers's re-export)
    and confirm_layers's parse_artifact/run_confirm to stage and commit
    decisions - the same reuse-not-reimplement posture read_slots()/
    read_layers() already follow for validate_layout.py's resolvers."""
    scripts_dir_str = str(_find_repo_layout_scripts_dir(repo_root))
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    validate_layout = importlib.import_module("validate_layout")
    discover_layers = importlib.import_module("discover_layers")
    layout_decision_grammar = importlib.import_module("layout_decision_grammar")
    confirm_layers = importlib.import_module("confirm_layers")
    return validate_layout, discover_layers, layout_decision_grammar, confirm_layers


# Per-layer-key resolver dispatch, built from validate_layout.py's own per-key
# resolver functions. Keyed by the same dotted strings discover_layers.py's
# TITLE_TO_BASE_KEY maps titles to - (path_resolver, enabled_resolver_or_None,
# include_roots_resolver_or_None). enabled_resolver is None for the two always-on
# layers (What-L2/How-L2); include_roots_resolver is None for the three layer keys
# that don't have an include_roots concept (only What-L2 does, per §16.7).
def _layer_resolvers(vl):
    return {
        "layers.what_l2": (
            vl.resolve_what_l2_path,
            None,
            vl.resolve_what_l2_include_roots,
        ),
        "how_dimension.how_l2": (vl.resolve_how_l2_path, None, None),
        "layers.what_l1": (vl.resolve_what_l1_path, vl.resolve_what_l1_enabled, None),
        "how_dimension.how_l1": (vl.resolve_how_l1_path, vl.resolve_how_l1_enabled, None),
    }


class LayoutSource:
    def __init__(self, repo_root) -> None:
        self.repo_root = Path(repo_root).resolve()
        (
            self._validate_layout,
            self._discover_layers,
            self._layout_decision_grammar,
            self._confirm_layers,
        ) = _import_repo_layout_modules(self.repo_root)
        ok, report = self._validate_layout.validate(self.repo_root)
        if not ok:
            failures = "\n".join(line for line in report if line.startswith("FAIL"))
            raise LayoutSourceError(
                "ult-repo-layout's own validation is failing for this repo - "
                "refusing to read layout state from it. Failures:\n" + failures
            )

    def _load_config(self) -> dict:
        return (
            self._validate_layout.load_yaml_file(self.repo_root / "context-config.yaml")
            or {}
        )

    @property
    def discovery_artifact_path(self) -> Path:
        """Where `context-layout-discovery.md` lives for this repo - the exact
        same `{workspace_root}/` (if set) vs. repo-root placement logic
        confirm_layers.run_confirm() computes internally (confirm_layers.py's
        run_confirm, `wr = vl._normalize_workspace_root(config); artifact_dir =
        (repo_root / wr) if wr and wr != "." else repo_root`), factored out
        here as a single shared helper (D24 Phase 1) so wizard_server.py's
        /api/stage, /api/apply, /api/decisions handlers don't each hand-roll a
        third copy of this placement dance and risk drifting from where
        run_confirm itself actually looks."""
        vl = self._validate_layout
        config = self._load_config()
        wr = vl._normalize_workspace_root(config)
        artifact_dir = (self.repo_root / wr) if wr and wr != "." else self.repo_root
        return artifact_dir / "context-layout-discovery.md"

    def read_slots(self) -> Dict[str, SlotState]:
        """Fresh every call: re-reads context-config.yaml and re-scans for markers
        every time, never cached (see module docstring)."""
        vl = self._validate_layout
        config = self._load_config()
        markers = vl.find_markers(self.repo_root)

        result: Dict[str, SlotState] = {}
        for slot, spec in vl.SLOT_REGISTRY.items():
            if not vl._owning_skill_installed(self.repo_root, spec["owning_skill"]):
                continue
            matches = vl.find_slot_markers(markers, slot)
            resolved_paths = []
            for marker_path, entry in matches:
                rel_path, _kind = vl.resolved_path_for_marker(
                    marker_path, entry, spec, self.repo_root
                )
                resolved_paths.append(rel_path.as_posix())
            result[slot] = SlotState(
                slot=slot,
                owning_skill=spec["owning_skill"],
                initialized=bool(matches),
                resolved_paths=sorted(set(resolved_paths)),
                default_path=vl.resolve_default(slot, config),
            )
        return result

    def read_layers(self) -> Dict[str, LayerState]:
        """Fresh every call, same staleness guarantee as read_slots(). Reads
        context-config.yaml directly through validate_layout.py's own per-key
        resolvers - a genuinely different mechanism from the marker-based slots
        above (see module docstring)."""
        vl = self._validate_layout
        gr = self._layout_decision_grammar
        config = self._load_config()
        title_by_base_key = {v: k for k, v in gr.TITLE_TO_BASE_KEY.items()}

        result: Dict[str, LayerState] = {}
        for base_key, (path_fn, enabled_fn, include_roots_fn) in _layer_resolvers(vl).items():
            enabled = bool(enabled_fn(config)) if enabled_fn else True
            path = path_fn(config)
            include_roots = include_roots_fn(config) if include_roots_fn else []
            result[base_key] = LayerState(
                key=base_key,
                title=title_by_base_key[base_key],
                enabled=enabled,
                path=path,
                include_roots=list(include_roots),
            )
        return result

    def read_decisions(self) -> List[DecisionField]:
        """Parses `context-layout-discovery.md` (if it exists yet - a repo
        that hasn't run `discover` at all has none) into a flat list of every
        decision-bearing line's current state, in file order, for
        `/api/decisions`. Fresh every call, same staleness guarantee as
        `read_slots()`/`read_layers()` - a `discover` re-run or a hand edit in
        another tab must be visible on the very next read."""
        artifact_path = self.discovery_artifact_path
        if not artifact_path.exists():
            return []
        cl = self._confirm_layers
        gr = self._layout_decision_grammar
        _lines, fields = cl.parse_artifact(artifact_path.read_text(encoding="utf-8"))

        result: List[DecisionField] = []
        for f in fields:
            if f.comment and cl.CONFIRMED_STAMP_RE.match(f.comment):
                state = "confirmed"
                allowed: List[str] = []
            else:
                allowed = sorted(cl.parse_comment_clauses(f.comment)) if f.comment else []
                state = "pending" if f.raw_value.strip() == "PENDING" else "staged"
            result.append(
                DecisionField(
                    section_title=f.section_title,
                    field_key=f.key,
                    line_no=f.line_no,
                    raw_value=f.raw_value,
                    comment=f.comment,
                    state=state,
                    allowed_verbs=allowed,
                    layer=gr.resolve_section_layer(f.section_title),
                )
            )
        return result
