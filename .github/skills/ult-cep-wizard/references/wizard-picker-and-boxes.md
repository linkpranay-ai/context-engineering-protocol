# Picker and the four boxes

Self-contained restatement of the two-source read model, the directory picker, and the
four labeled boxes the wizard renders (D24 §18.3 / §18.7). Read alongside
`wizard_layout_source.py`, `wizard_picker.py`, `wizard_tripwire.py`, and
`wizard_boxes.py` — each carries the same reasoning in its own docstring; this file
gives a reviewer one place to read the whole read-side model without opening four
files. See `wizard-security-model.md` for the write-side/auth/containment model this
one builds on.

## 1. Two sources of truth, read fresh on every request

`ult-repo-layout` records project layout in two independent places, and the wizard
reads both — neither is authoritative over the other, they answer different
questions:

- **9 `SLOT_REGISTRY` entries** (marker-derived) — resolved from `.layout-slots.yaml`
  marker files actually present on disk. This is "where did a slot actually end up,"
  ground truth from the filesystem itself.
- **4 CEP layer keys** (`layers.what_l2`, `layers.what_l1`, `how_dimension.how_l2`,
  `how_dimension.how_l1`) — read directly from `context-config.yaml`, via
  `discover_layers.py`'s `TITLE_TO_BASE_KEY` mapping. This is "what did the user
  configure," which can exist before any marker does.

Both are re-resolved **on every request**, never cached across requests — a change to
`context-config.yaml` or a newly-written marker file is visible on the very next
`/api/status` call, with no server restart and no explicit refresh action. This is
deliberate: Phase 0 is a passive viewer over state something else (`ult-repo-layout`,
or a human editing the config by hand) is changing, and a stale cache would silently
lie about that state.

**Changed in Phase 2 (D24 §18.14):** validation against `validate_layout.py
--validate` is no longer a one-time startup gate — `wizard_server.build_server()` no
longer eagerly constructs a `LayoutSource` at all, precisely so a repo with a currently
*broken* layout still binds and serves the `layout_broken` state screen instead of
`SystemExit`ing before opening a socket. Each handler that needs a `LayoutSource` now
builds one fresh **per request** via `_try_layout_source()`, which re-runs validation
every time and returns a 503 (not a startup crash) if it currently fails — consistent
with this section's own "read fresh on every request, never cached" principle, just
extended to cover the validate-gate itself, not only the box/picker data behind it. See
`wizard-onboarding-state-machine.md` for how `GET /api/state` uses the same
`validate()` call to decide whether to route to `layout_broken` in the first place.

## 2. The four boxes (`wizard_boxes.py`)

`BoxesView` is the exact shape returned by `/api/status`: `{what, how, guidelines,
tripwire}`, plus a Phase-2-added `stub_cards` key (`wizard_stub_content.py`, wired into
this same response rather than a new route) sourced from the same `what`/`how`/
`guidelines` data below, not a fifth independent box.

- **What / How** (`WhatHowBox`: `title`, `l2_enabled`, `l1_enabled`, `paths: List[BoxPath]`) —
  the union of the always-on L2 layer and the opt-in L1 layer for that dimension. Each
  `BoxPath` is `{path, source, files, total_file_count, truncated}` — `source` says
  whether that path came from the L2 (always-on) or L1 (opt-in) layer, since a box can
  show entries from both at once and a reader benefits from knowing which. `files`
  (`wizard_box_files.list_files`, capped at `MAX_FILES_PER_PATH`) is the actual file
  listing under that path, relative to the path itself; `total_file_count`/`truncated`
  carry the real count when the listing was capped. A box with an empty `paths` list is
  the real, correctly-rendered empty case — not an error state — and is what triggers
  the empty-case content-scaffolding card (`wizard_stub_content.py`); a `BoxPath` whose
  `files` list is empty (but which is itself present in `paths`) is a different,
  narrower case — the path resolved but has nothing in it yet.
- **Guidelines** (`GuidelinesBox`: `title="Guidelines"`, `available`, `unavailable_reason`,
  `initialized`, `resolved_paths`, `default_path`) — sourced from the
  `compiled_guidelines` slot. `available` is false whenever
  `compiling-project-guidelines` isn't installed in the target repo, with
  `unavailable_reason` carrying the specific reason string rather than a generic
  "not available."
- **Trip-wire** (`GuidelinesBox`-shaped: `available` plus the same supporting fields) —
  a read-only summary sourced from `decision_ledger.py`'s `show` subcommand only,
  called in-process (a direct import, not a second subprocess) since Phase 0 needs
  nothing `show` doesn't already return. No `query`, `add-entry`, or `disposition` call
  exists anywhere in `wizard_tripwire.py` — this box can only ever display, never
  mutate, the ledger.

`/api/status`'s top-level JSON keys are exactly `{"what", "how", "guidelines",
"tripwire"}` — `what`/`how` carry `title`, `l2_enabled`, `l1_enabled`, `paths` (a list
of `{"path": ...}` objects); `guidelines`/`tripwire` carry `available` plus the
supporting fields above.

## 3. The picker (`wizard_picker.py`)

- **GET-only, still.** `wizard_picker.py` itself registers no mutating route and never
  will — Phase 1's write path (`POST /api/stage`, `POST /api/apply`) lives entirely in
  `wizard_server.py`/`wizard_decision_staging.py`/`wizard_apply.py` instead. That said,
  the server *as a whole* is no longer GET-only now that those two routes exist, so
  don't take "the picker is GET-only" as "the server has no mutating routes" — see
  `wizard-write-path.md` for what those routes do and how they're gated.
- **Containment-scoped to the affirmed repo root** on every single call — the picker
  is the primary reason `wizard_containment.py` exists at all; every candidate
  directory returned is checked, not just the one the client asked to descend into.
- **Filtered.** Hidden entries (dotfile/dot-directory), `node_modules`, `.git`, and
  build-output-shaped directories are excluded from listings — the picker exists to
  help a user point at a real content directory, not to be a general-purpose file
  browser over noise that was never a candidate.
- `/api/picker` response shape: `{rel_path, parent_rel_path, entries, target_root}` —
  `parent_rel_path` is `null` at the affirmed root (nothing to go up to), and each entry in
  `entries` is `{"name": ..., "rel_path": ...}`. `rel_path` (both the top-level one and
  each entry's) is always relative to the affirmed root, never an absolute filesystem
  path — the client never needs to know (or send back) the real absolute path on disk,
  which also means a crafted absolute path from the client can't be used to request
  something outside the root in the first place. `target_root` (ISSUES.md Round 2 finding
  7, 2026-08-31) is `null` when the affirmed root is `ctx.repo_root` (the default,
  unchanged from before this finding); it's the resolved, canonicalized absolute path
  when the caller opted into an external root via the optional `external_root` query
  param, re-validated on every request via `wizard_containment.resolve_external_target()`
  — see `wizard-retrofit-flow.md` §1.2, the one current consumer of that param. Phase 1's
  frontend passes an entry's
  `rel_path` straight through to `POST /api/stage`'s `arg` when a user picks a directory
  for a `CUSTOM` decision (see `wizard-write-path.md` §2) — it is the same
  containment-checked value the picker itself already validated, not a second path the
  client is trusted to construct.
- No drag-and-drop (S1, a project-owner decision predating this build): every picker
  interaction is a server-rendered link the browser navigates, matching the
  server-rendered-picker choice made for the rest of the UI and avoiding a whole class
  of client-side path-handling bugs a drag target would introduce for no Phase-0
  benefit.

## 4. What this read path still deliberately leaves out

- No write endpoint anywhere in the picker or box views themselves — `GET /api/status`
  and `GET /api/picker` stay exactly as GET-only as they were in Phase 0.
  `wizard_atomic_write.py` is used by the write path now (`wizard_decision_staging.py`),
  just not by anything documented in this file.
- No caching layer over either source of truth — see §1 above; this is a considered
  choice, not an oversight to "optimize later."
- No pagination on picker listings — real project directory trees at the depth this
  picker operates at (pointing at a content root, not walking an entire monorepo) don't
  need it yet; revisit only if a real large-repo case demonstrates otherwise.
