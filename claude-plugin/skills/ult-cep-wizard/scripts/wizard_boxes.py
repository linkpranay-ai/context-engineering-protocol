#!/usr/bin/env python3
"""wizard_boxes.py - assembles the four-box read-only view model for
ult-cep-wizard's Phase 0 frontend (D24 §18.1/§18.7, locked).

§18.1: "All three [journeys] converge on the same visual surface (§18.7): labeled
boxes for What, How, Guidelines, and Trip-wire, each listing the files currently
resolved into it." This module is the one place that assembles those four boxes -
`wizard_server.py`'s status route calls `build_boxes` and serializes the result;
nothing else in this module talks to the network or the filesystem directly (it reads
through `wizard_layout_source.LayoutSource` and `wizard_tripwire.read_summary`, both
of which own their own fresh-every-call guarantees).

What/How are each a *union* of their L2 (always-on) and L1 (opt-in) layer, not two
separate boxes - four boxes total, matching §18.1's count, and consistent with
§18.2b/H2's "a box may represent more than one resolved path" note (a box already
handles a layer's own multi-root include_roots; unioning L1 in is the same idea one
level up). Guidelines is the `compiled_guidelines` SLOT_REGISTRY slot - a
marker-derived slot like the other eight, not a layer key at all, so it's read via
`read_slots()` rather than `read_layers()`. Trip-wire is `wizard_tripwire`'s own
summary, passed through unchanged.

Guidelines and Trip-wire share an `available`/`unavailable_reason` shape (mirroring
`wizard_tripwire.TripwireSummary`) so the frontend can render "this box's owning skill
isn't installed" uniformly for either, rather than two different not-available
conventions. What/How have no such state - `layers.what_l2`/`how_dimension.how_l2`
have no owning-skill gate in `discover_layers.py` (they're always-on, per §18.2b), so
unlike the marker-derived slots there is no "skill not installed" case for them to
represent.
"""

from __future__ import annotations

import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wizard_layout_source as wls  # noqa: E402
import wizard_tripwire as wt  # noqa: E402


@dataclass
class BoxPath:
    path: str
    source: str  # "L2" | "L1" - which underlying layer contributed this path, so the
    # frontend can distinguish a What box's always-on L2 paths from its opt-in L1 ones.


@dataclass
class WhatHowBox:
    title: str  # "What" | "How"
    l2_enabled: bool
    l1_enabled: bool
    paths: List[BoxPath] = field(default_factory=list)


@dataclass
class GuidelinesBox:
    title: str = "Guidelines"
    available: bool = True
    unavailable_reason: Optional[str] = None
    initialized: bool = False
    resolved_paths: List[str] = field(default_factory=list)
    default_path: str = ""


@dataclass
class BoxesView:
    what: WhatHowBox
    how: WhatHowBox
    guidelines: GuidelinesBox
    tripwire: wt.TripwireSummary


def _what_how_box(title: str, l2: wls.LayerState, l1: wls.LayerState) -> WhatHowBox:
    paths = [BoxPath(path=p, source="L2") for p in l2.resolved_paths]
    paths += [BoxPath(path=p, source="L1") for p in l1.resolved_paths]
    return WhatHowBox(
        title=title, l2_enabled=l2.enabled, l1_enabled=l1.enabled, paths=paths
    )


def build_boxes(source: wls.LayoutSource) -> BoxesView:
    """Fresh every call - delegates entirely to `LayoutSource.read_slots()`/
    `read_layers()` and `wizard_tripwire.read_summary()`, none of which cache (see
    their own module docstrings), so this inherits the same never-stale guarantee
    rather than adding a second one."""
    layers = source.read_layers()
    slots = source.read_slots()

    what = _what_how_box("What", layers["layers.what_l2"], layers["layers.what_l1"])
    how = _what_how_box(
        "How", layers["how_dimension.how_l2"], layers["how_dimension.how_l1"]
    )

    guidelines_slot = slots.get("compiled_guidelines")
    if guidelines_slot is None:
        guidelines = GuidelinesBox(
            available=False,
            unavailable_reason=(
                "compiling-project-guidelines is not installed in this repo - the "
                "Guidelines box needs it to resolve compiled_guidelines."
            ),
        )
    else:
        guidelines = GuidelinesBox(
            initialized=guidelines_slot.initialized,
            resolved_paths=guidelines_slot.resolved_paths,
            default_path=guidelines_slot.default_path,
        )

    tripwire = wt.read_summary(source.repo_root, slots.get("decision_ledger"))

    return BoxesView(what=what, how=how, guidelines=guidelines, tripwire=tripwire)


def to_json_dict(view: BoxesView) -> dict:
    """Plain-dict form for `json.dumps` - dataclasses (including the nested
    `TripwireSummary`) aren't JSON-serializable directly."""
    return asdict(view)
