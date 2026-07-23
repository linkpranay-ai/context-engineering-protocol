---
name: repo-layout
description: Register, resolve, and validate where a project's path-slots actually live via .layout-slots.yaml markers, so relocating a slot needs zero SKILL.md edits. Do NOT use for single-file lookups.
namespace: ult
version: 0.1.0
origin: ground-up
author: Pranay Mishra
maintainer: Pranay Mishra
adapted_from: ~
upstream_version: ~
released: 2026-06-14
tags: [utility, project-layout, configuration, markers, pilot]
bundle: utilities
tier: draft
---

# ult-repo-layout

**Status: implemented — all 8 phases complete.** This skill implements
`context-engineering/CONTEXT-ENGINEERING-DESIGN.md` §15 ("Project Layout and
Path-Dependency Configuration") and §16 ("Workspace Root Consolidation" —
`layout.workspace_root`, scaffold-not-copy, and the
`layout-slots-registry.yaml` superset registry), covering **eight**
path-slots:

- `context_packages` — read/written by `ult-context-generate` and every
  `CONSUMING-CONTEXT-PACKAGE.md` consumer. The only slot a real, shipped skill
  in this repo both produces and consumes.
- `compiled_guidelines` — written by `compiling-project-guidelines`, read by
  its own `CONSUMING-COMPILED-GUIDELINES.md` consumers. The registry's only
  `kind: file` slot, and the only slot whose D21 default re-roots to a
  different bucket (`inputs` → `cache`).
- `plans_output`, `brainstorm_output`, `user_stories_output`, `security_docs`,
  `security_report`, `project_plan_docs` — six further slots that prove the
  same registry/marker mechanism scales past one owner. Their producer/
  consumer skills (`example-plan-writer`, `example-brainstorm-writer`,
  `example-consumer`, `example-threat-modeler`, `example-report-writer`,
  `example-project-planner`, etc.) are **illustrative — not shipped in this
  repo**; see the slot registry table below.

...plus **5 starter-kit drop-zones** — not `project_layout` path-slots (no
marker, no resolution algorithm), just regenerated `.pointer.md` scaffold
files. Read `references/starter-kit-dropzones.md` now and follow it if you're
touching that mechanism.

Read `references/phase-history.md` for the full D20/D21 phase-by-phase build
history and exit criteria — not needed to operate this skill day to day.

## Dependencies

None — this skill is foundational. `ult-context-generate` (`utilities`
bundle, `context_packages`) and `compiling-project-guidelines` (`utilities`
bundle, `compiled_guidelines`) are real, shipped-in-this-repo **consumers** of
the markers/index this skill maintains (via the §15.5 resolution algorithm,
documented in each owning skill's own path-resolution note) — not
dependencies of this skill. Six further illustrative slots (`plans_output`,
`brainstorm_output`, `user_stories_output`, `security_docs`,
`security_report`, `project_plan_docs`, owned by hypothetical skills like
`example-plan-writer`/`example-brainstorm-writer`/`example-consumer`/
`example-threat-modeler`/`example-report-writer`/`example-project-planner`)
demonstrate that the same registry mechanism scales to any number of owners —
not dependencies of this skill either way.

## Overview

Every project has a handful of **path-slots** — directories or files that one
skill owns and others read (e.g. "where do approved context packages live?").
Hardcoding those paths in every `SKILL.md` means relocating a folder requires
editing every skill that mentions it. This skill fixes that with two pieces:

1. **Markers** (`.layout-slots.yaml`, §15.3) — a small YAML file dropped in
   the directory that *is* (or *contains*) a slot, declaring `slot: <key>`.
   The marker travels with the folder if it's renamed or moved — identity
   lives with the folder, not in a separate table.
2. **`project_layout`** in `context-config.yaml` — a **generated index**
   (`reconcile` rebuilds it from markers), cached for fast lookups. It is
   never hand-authored and never the source of truth — markers are.

This skill is the only thing that writes markers and rebuilds the index.
Other skills only *read* `project_layout` (fast path) and fall back to a
repo-wide marker search (§15.5) if the index is stale or absent — they never
hardcode a slot's path.

## Slot registry

`project_layout.slots` registers only slots whose path isn't already a key
under `layers.*` / `how_dimension.*` / `graphify.*` / `cache.*` in
`context-config.yaml` (§15.2) — relocating those is "edit the existing key,"
already supported. Eight slots are registered:

| Slot key | Kind | Pre-D21 default | D21 default (`layout.workspace_root` set) | Falls back to (if unset) | Owning skill |
|---|---|---|---|---|---|
| `context_packages` | `directory` | `contexts/` | `{workspace_root}/contexts/` | `cache.product_context_path` | `ult-context-generate` |
| `plans_output` | `directory` | `docs/superpowers/plans/` | `{workspace_root}/outputs/plans/` | — | `example-plan-writer` *(illustrative)* |
| `brainstorm_output` | `directory` | `docs/superpowers/specs/` | `{workspace_root}/outputs/specs/` | — | `example-brainstorm-writer` *(illustrative)* |
| `compiled_guidelines` | `file` | `starter_kit/project_guidelines/COMPILED-GUIDELINES.md` | `{workspace_root}/cache/project-guidelines/COMPILED-GUIDELINES.md` | — | `compiling-project-guidelines` |
| `user_stories_output` | `directory` | `output_docs/user-stories/` | `{workspace_root}/outputs/user-stories/` | — | `example-consumer` *(illustrative)* |
| `security_docs` | `directory` | `output_docs/security_docs/` | `{workspace_root}/outputs/security_docs/` | — | `example-threat-modeler` *(illustrative)* |
| `security_report` | `directory` | `output_docs/security_report/` | `{workspace_root}/outputs/security_report/` | — | `example-report-writer` *(illustrative)* |
| `project_plan_docs` | `directory` | `output_docs/project_plan_docs/` | `{workspace_root}/outputs/project_plan_docs/` | — | `example-project-planner` *(illustrative)* |

The "D21 default" column only applies to an **unmarked** slot when
`layout.workspace_root` is set (§16.2 step 3) — it never overrides a marker or
an explicit `project_layout.slots.<slot>.path` (§16.2 steps 1-2). A project
that never sets `layout.workspace_root` resolves via the "Pre-D21
default"/"Falls back to" columns exactly as before, forever (§16.10).

`plans_output` and `brainstorm_output` are the two **Gap-B** slots that close
a gap left open by the first registered slot: `docs/superpowers/{plans,specs}/`
were hardcoded output paths with no slot at all. Like the five slots below,
neither has a pre-existing config-key fallback — "Falls back to" is "—", so an
unmarked slot's step-1 fallback is simply its literal pre-D21 default.

The five remaining slots:

- `compiled_guidelines` is the only `kind: file` slot in the registry — its
  resolved path is a single file, not a directory (see "Marker file format"
  below for the `file:` marker field this requires). It's also the only slot
  whose D21 default **changes bucket** (§16.3/§16.4): the pre-D21 default
  `starter_kit/project_guidelines/COMPILED-GUIDELINES.md` sits in the
  `inputs`-bucket starter-kit drop-zone (alongside the raw sources
  `compiling-project-guidelines` reads), but `COMPILED-GUIDELINES.md` itself
  is a *derived, regenerable* artifact — so its D21 default re-roots to the
  `cache` bucket, `{workspace_root}/cache/project-guidelines/COMPILED-GUIDELINES.md`,
  not `{workspace_root}/inputs/...`.
- `user_stories_output`, `security_docs`, `security_report`, and
  `project_plan_docs` are four sibling `directory` slots, each one project's
  `output_docs/<family>/` subtree. All four belong to the `outputs` bucket,
  alongside `plans_output`/`brainstorm_output` — their D21 defaults sit under
  `{workspace_root}/outputs/`. None of the four nests inside another (they
  diverge at `output_docs/<family>/`'s second path segment), so
  `scripts/validate_layout.py`'s nesting check (§15.9 #3) needs no
  `nests_under:` whitelist entries for this set.

`context_addenda` (the `*.addenda.yaml` siblings D19 v2 writes) is **not** a
separate slot — its path is always
`{resolved context_packages path}/{package-id}_{date}.addenda.yaml` (§15.4).

`scripts/validate_layout.py`'s `SLOT_REGISTRY` is written generically over
"any number of registered slots" and additionally exercises a `kind: file`
slot and the S8 (§15.8) partial-install gate: a slot whose `owning_skill`
directory isn't present under this repo's `.github/skills/` is skipped
entirely (no INFO/WARN/FAIL, not part of bijectivity/nesting), so an adopter
who installed only a subset of skills never sees messages about slots whose
owning skill they didn't install.

## Marker file format — `.layout-slots.yaml`

One file per directory that hosts one or more slots:

```yaml
# contexts/.layout-slots.yaml -- this directory IS the context_packages slot
slots:
  - slot: context_packages
    kind: directory
    schema_version: 1
```

`plans_output`/`brainstorm_output`/`user_stories_output`/`security_docs`/
`security_report`/`project_plan_docs` markers have the same shape, just a
different `slot:` key:

```yaml
# my-plans/.layout-slots.yaml -- this directory IS the plans_output slot
slots:
  - slot: plans_output
    kind: directory
    schema_version: 1
```

`compiled_guidelines` is the registry's only `kind: file` slot — its marker
adds a `file:` field naming the file *within* the marker's directory:

```yaml
# starter_kit/project_guidelines/.layout-slots.yaml -- this directory CONTAINS
# the compiled_guidelines slot (the file COMPILED-GUIDELINES.md within it)
slots:
  - slot: compiled_guidelines
    kind: file
    file: COMPILED-GUIDELINES.md
    schema_version: 2
```

- `kind: directory` → the slot's resolved path is the marker's own directory.
- `kind: file` → the slot's resolved path is `<marker's directory>/<file>`
  (`resolved_path_for_marker` in `scripts/validate_layout.py` handles this
  generically — `compiled_guidelines` is simply the first slot to use it).
- `schema_version` — the `project_layout` schema version that introduced this
  slot (§15.8); `1` for `context_packages`/`plans_output`/`brainstorm_output`,
  `2` for `compiled_guidelines`/`user_stories_output`/`security_docs`/
  `security_report`/`project_plan_docs`.
- If two slots happen to share a directory, list both entries under that one
  `slots:` array — one marker file can declare multiple slots.

## Starter-kit drop-zones and `.pointer.md` (D21 §16.6, Phase 3d)

Five `inputs/`-bucket drop-zones hold project-owned, human-curated material
that consuming skills read but never regenerate (e.g. `project_guidelines` →
`compiling-project-guidelines`). Read `references/starter-kit-dropzones.md`
now and follow it — it has the full per-leaf table, the regenerated
`.pointer.md` template, and the workspace-root-aware location rules.

## Generated `context-config.yaml` (D21 §16.6, Phase 3d)

`install.ps1`/`install.sh -InitProject` generates a baseline
`context-config.yaml` at the project root (only if one doesn't already exist)
by copying `starter_kits/context_engineering/context-config.yaml.template` and
applying this **mechanical substitution table** — the same defaults a human
would get by hand-copying `.template` and accepting every `e.g.` value,
byte for byte (§16.2's non-impact guarantee extends to this generated file):

| Template placeholder (`<...>` token) | Generated value | Field |
|---|---|---|
| `<your-project-name>` | *(left as-is — human input)* | `project_name` |
| `<one-line description of what this product/service does>` | *(left as-is — human input)* | `description` |
| `<source code root, e.g. app/ or src/>` | `.` | `what_l3.path` |
| `<requirements docs root, e.g. docs/requirements/>` | `docs/requirements/` | `what_l2.path` |
| `<external reference root, e.g. specs/external/>` | `specs/external/` | `what_l1.path` |
| `<org conventions/templates root, e.g. org/>` | `org/` | `how_l2.path` |
| `<process standards root, e.g. org/process-standards/>` | `org/process-standards/` | `how_l1.path` |

`project_name`/`description` are the only two fields left as literal
`<placeholder>` — exactly §16.6 item 2's "the only fields requiring human
input." `what_l3.path` resolves to `.` (repo root) rather than the
`app/`-or-`src/` example: neither candidate is guaranteed to exist, and `.`
is the universally-safe "index the whole repo" default for a brand-new
project (a deliberate deviation from the literal `e.g.` value for this one
field — every other row uses its `e.g.` value as-is). The generated file has
**no `project_layout` section** — `init` step 1's "refuse if already
initialized" guard only fires on `project_layout.initialized: true`, so this
generated baseline composes cleanly with `init` below.

`init` (this skill) then **completes** this file: it asks the human for
`project_name`/`description`, optionally offers the `layout.workspace_root`
opt-in (re-rooting the 5 drop-zones' `.pointer.md` locations and pre-populating
`layers.what_l2.exclude`/`include_roots` per §16.5/§16.7), and performs its
existing slot-marker/`project_layout` work (below). If `context-config.yaml`
doesn't exist yet when `init` runs (the human skipped `-InitProject`), `init`
generates it inline using the table above before continuing.

## Modes

### `init` — greenfield projects

**Before step 1 (D21 §16.6, Phase 3d) — config completion and pointer
regeneration:**

- If `context-config.yaml` doesn't exist at the project root, generate it
  using the substitution table in "Generated `context-config.yaml`" above
  (same output `install.ps1`/`install.sh -InitProject` would have produced).
- Ask the human for `project_name` and `description` and fill those two
  placeholders — the only ones the table leaves unset.
- Ask whether to opt into `layout.workspace_root` (brief explanation: re-roots
  this project's slots and starter-kit drop-zones under one directory, e.g.
  `docs/`). This question is **skipped entirely** if `layout.workspace_root`
  is already set (re-running `init` must never re-prompt or change an
  existing value — S7's "never silently reset" applies here too). If the
  human opts in:
  - Set `layout.workspace_root: <value>` (validate per S22 — reject `.`/`''`).
  - Pre-populate `layers.what_l2.exclude: [contexts/, inputs/, cache/]` (the
    §16.5 recommended triad — only add entries for subtrees that don't already
    appear in `what_l2.exclude`).
  - If `output_docs_structure/` (or another existing SDLC-output tree) is
    present, suggest — don't silently add — `what_l2.include_roots` entries
    per §16.7; otherwise leave `include_roots: []`.
- For each of the 5 starter-kit drop-zones (`threat_modeling`,
  `secure_coding_guidelines`, `security_test_data`, `project_plan`,
  `project_guidelines`), regenerate `.pointer.md` at its current location:
  `starter_kit/<leaf>/.pointer.md` if `layout.workspace_root` is unset (the
  common case — this is where `-InitProject` already created it), or
  `{workspace_root}/inputs/starter-kit/<leaf>/.pointer.md` if the human just
  opted into `workspace_root` for a **brand-new** project with no existing
  drop-zone content (re-rooting an **existing** project's drop-zones is
  `reconcile --adopt-workspace-root`'s job, below — `init` never moves files).
  Create the directory first if it doesn't exist; never touch any other file
  already in that directory.

**Then run steps 1-5 below** (except that step 2's
`{workspace_root}/<leaf>` resolution now has a real `workspace_root` value to
use if the human opted in above):

1. **Refuse if already initialized** — if `context-config.yaml` has
   `project_layout.initialized: true`, stop and say so; point at `reconcile`
   or offer a diff view instead (S7). Re-running `init` must never silently
   reset a customized layout back to defaults.
2. Otherwise, for each registered slot (see the slot registry table above —
   all eight) whose owning skill is installed (S8):
   - Resolve its **resolved default** (§16.2, M4): `{workspace_root}/<leaf>`
     if `layout.workspace_root` is set in `context-config.yaml` (and
     well-formed — S22), else the slot's "Falls back to" config key if set
     (only `context_packages` has one — `cache.product_context_path`), else
     its pre-D21 default (§15.2/§16.4 — see the slot registry table above).
   - Scaffold that directory if it doesn't exist yet — for the one `kind:
     file` slot (`compiled_guidelines`), scaffold the *containing* directory
     (`starter_kit/project_guidelines/` or
     `{workspace_root}/cache/project-guidelines/`); the file itself is
     `compiling-project-guidelines`'s output, not created by `init`.
   - Write `<path>/.layout-slots.yaml` with the marker shown above (one
     `slot:` entry per slot; slots that resolve to the same directory share
     one marker file's `slots:` list). For `compiled_guidelines`, the marker
     is written in the containing directory with `kind: file, file:
     COMPILED-GUIDELINES.md` (see "Marker file format" above).
3. Write/update `context-config.yaml`'s `project_layout`:
   ```yaml
   project_layout:
     version: 1
     initialized: true
     slots:
       context_packages:
         path: contexts/        # or wherever step 2 resolved it
         kind: directory
         owning_skill: ult-context-generate
       plans_output:
         path: docs/superpowers/plans/        # or wherever step 2 resolved it
         kind: directory
         owning_skill: example-plan-writer    # illustrative
       brainstorm_output:
         path: docs/superpowers/specs/        # or wherever step 2 resolved it
         kind: directory
         owning_skill: example-brainstorm-writer   # illustrative
       compiled_guidelines:
         path: starter_kit/project_guidelines/COMPILED-GUIDELINES.md  # or wherever step 2 resolved it
         kind: file
         owning_skill: compiling-project-guidelines
       user_stories_output:
         path: output_docs/user-stories/        # or wherever step 2 resolved it
         kind: directory
         owning_skill: example-consumer         # illustrative
       # ...and so on for security_docs, security_report, project_plan_docs --
       # same shape, one entry per remaining row of the slot registry table
       # above.
   ```
4. **Optionally interactive up front** — before scaffolding, ask: "Here's the
   default layout for all eight registered slots — `<slot>` → `<resolved
   default>` for each row of the slot registry table above (or its
   `{workspace_root}/...` equivalent if `layout.workspace_root` is set) —
   rename or relocate any of these before we start?" A team that wants a
   custom layout from day one does it in one pass; each marker is written at
   its chosen location either way.
5. **Scaffold a CI/pre-commit hook by default** (resolves H2) — see "CI /
   pre-commit hook" below. Opt out with `init --no-ci-hook`.

### `reconcile` — rebuild the index from markers; the repair tool for drift

Runs the steps below **independently for each registered slot** — a marker
for one slot doesn't affect another's resolution, even if two slots' markers
happen to live in the same `.layout-slots.yaml` file's `slots:` list.

1. Repo-wide search for `slot: <key>` across every `.layout-slots.yaml` (the
   same deterministic scan `validate_layout.py` performs — path depth
   ascending, then lexical ascending).
2. **Exactly one marker found** → write/update
   `project_layout.slots.<key>.path` to match it. This is what fixes a stale
   index automatically (S5) — no prompt needed.
3. **Zero markers found** → ask the human where `<key>` lives now, or whether
   it was intentionally removed — mention the **resolved default** (§16.2, M4)
   as the likely candidate, e.g. "...its resolved default would be `<path>` —
   is that where it lives?". **Never guess by name similarity.** On
   confirmation, write a new marker there.
4. **More than one marker found (for one slot)** → bijectivity violation (S15,
   §15.9) — surface it as a conflict for the human to resolve (pick one
   location, or merge the two folders' contents). Do not auto-resolve.
5. `reconcile --validate` — no prompts, just runs
   `scripts/validate_layout.py --validate` and reports pass/fail with a
   non-zero exit code on failure, for CI / pre-commit (§15.9).
6. `reconcile --adopt-workspace-root <path>` (D21 §16.6) — advisory/dry-run
   helper for migrating an existing project onto `layout.workspace_root`: for
   every registered slot and starter-kit drop-zone, reports whether it's
   already marker-pinned (unaffected), has a duplication conflict that needs
   resolving by hand, or offers a pin-here-vs-relocate choice. Read
   `references/workspace-root-adoption.md` now and follow it — it has the
   full per-slot decision tree.

### `discover` — brownfield adoption (no prior markers or `project_layout`)

Each registered slot has its own content-based signature for guessing a
candidate location — except the five Phase 2 slots, which have none and skip
straight to asking (§15.7):

1. **`context_packages`** — scan for `*.yaml` files containing a top-level
   `context_package:` key with a `human_approved` field, **sorted
   deterministically** (path depth ascending, then lexical ascending — the
   same order `reconcile`'s tie-breaks use).
2. **`plans_output`/`brainstorm_output`** — simpler signature: does the slot's
   pre-D21 default path (`docs/superpowers/plans/` / `docs/superpowers/specs/`)
   exist and contain `.md` files? If so, that's the candidate.
3. **`compiled_guidelines`/`user_stories_output`/`security_docs`/
   `security_report`/`project_plan_docs`** — no content-based signature
   (§15.7): go straight to step 5 below for each of these five, every time.
   If the slot's pre-D21 default path already exists (e.g.
   `output_docs/security_docs/`, or another existing `output_docs_structure/
   <family>/` convention), mention it as a likely answer rather than asking
   cold.
4. For slots with a candidate (items 1-2), present it to the human for
   confirmation: "Found `<path>` — is this where `<slot>` lives?"
5. If nothing is found for a slot (items 1-2), the human says no, or the slot
   has no signature at all (item 3), ask directly: "Where does this project
   keep `<slot description>`? (path, or 'not in use')"
6. On confirmation, write a marker at that location (creating the directory
   first if it doesn't exist) — per slot. For the `kind: file` slot
   (`compiled_guidelines`), write the marker in the *containing* directory
   with `kind: file, file: COMPILED-GUIDELINES.md` (see "Marker file format"
   above).
7. Write `project_layout` with `initialized: true`, `version: 1`, same shape
   as `init` step 3, covering every slot that was confirmed.

## Path resolution algorithm (§15.5 + §16.2) — for consuming skills

Each owning/consuming skill resolves its slot this way instead of a hardcoded
path. `ult-context-generate`/`CONSUMING-CONTEXT-PACKAGE.md` (`context_packages`)
and `compiling-project-guidelines`/`CONSUMING-COMPILED-GUIDELINES.md`
(`compiled_guidelines`) are the two real, shipped-in-this-repo consumers. The
same algorithm applies identically to the six illustrative slots
(`example-plan-writer` for `plans_output`, `example-brainstorm-writer` for
`brainstorm_output`, `example-consumer` for `user_stories_output`,
`example-threat-modeler` for `security_docs`, `example-report-writer` for
`security_report`, `example-project-planner` for `project_plan_docs`):

1. No `context-config.yaml`, or no `project_layout` section → use the slot's
   **resolved default** (defined below) — unconfigured project, today's
   behavior, unchanged unless `layout.workspace_root` is set.
2. `project_layout.slots.<slot>` present (cache hit) → read `.path`, then
   check whether that location's `.layout-slots.yaml` still lists
   `slot: <slot>`:
   - Confirms → resolved (fast path, one YAML read).
   - Missing/stale → cache miss, fall through to step 3.
3. Cache miss, or `slots.<slot>` absent → repo-wide marker search (the same
   scan `reconcile` performs):
   - Zero matches → the slot's **resolved default** (defined below), plus
     non-blocking note: `"Note: slot '<slot>' has no marker in this repo —
     using default '<path>'. Run /ult-repo-layout reconcile to register it if
     this isn't where you keep it."` (`<path>` is the resolved default).
   - Exactly one match → resolved to that path; if the index pointed
     elsewhere, this run also flags it as stale (next `reconcile` refreshes
     it, S5).
   - Multiple matches → bijectivity violation (S15): read context uses the
     first by stable sort order with a warning; write context **hard-stops**
     — `/ult-repo-layout reconcile` must resolve it first.
4. Once resolved: existence check (`directory` → can be listed), type check
   (is it actually a directory?). Not found in read context →
   warn-and-continue (S3). Not found in write context → governed by
   `layout.on_missing_write_path` below.

### Resolved defaults per slot (D21 §16.2/§16.4, resolves M4)

A **marker** (steps 2-3 above) always wins regardless of this section — it
only governs steps 1 and 3's "zero matches" case, i.e. an **unmarked** slot.
For an unmarked slot, see the slot registry table above for every slot's
"Pre-D21 default" and "D21 default" columns:

- **`layout.workspace_root` set** (and well-formed — not `.`/`''`, S22) → the
  slot's "D21 default" column, `{workspace_root}/<leaf>` (§16.4).
- **`layout.workspace_root` absent (or malformed)** → the slot's "Falls back
  to" config key if set (only `context_packages` has one —
  `cache.product_context_path`, §15.2/Phase 0), else its "Pre-D21 default"
  column, literally.

Two slots have a wrinkle worth calling out by name:

- **`context_packages`** is the only slot with a config-key fallback
  (`cache.product_context_path`) — a project that set this key before this
  skill ever existed continues to work unchanged, even with
  `layout.workspace_root` unset.
- **`compiled_guidelines`** is the only slot whose D21 default changes
  *bucket*, not just root: its pre-D21 default
  (`starter_kit/project_guidelines/COMPILED-GUIDELINES.md`) sits in the
  `inputs` bucket, but its D21 default
  (`{workspace_root}/cache/project-guidelines/COMPILED-GUIDELINES.md`) sits in
  the `cache` bucket — `{workspace_root}/inputs/...` is never a candidate for
  this slot (see "Slot registry" above for why).

`workspace_root` therefore changes **defaults only** — it can never override a
marker (steps 2-3) or an explicit `project_layout.slots.<slot>.path` (step 2,
S16). A project that never sets `layout.workspace_root` resolves exactly as it
did before this mechanism existed, forever (§16.10's zero-impact guarantee).
`validate_layout.py --validate` rejects `layout.workspace_root: .` and
`layout.workspace_root: ''` (S22, see below) — a single config-level check
that applies to every registered slot at once, not a per-slot check.

## Config reference — `context-config.yaml`

This skill reads and writes:

- **`project_layout`** — the generated index (see `init`/`reconcile` above).
  Never hand-author this section; running `init` (new project) or `discover`
  (existing project) writes it for you. Hand-editing
  `project_layout.slots.<slot>.path` without also moving the marker produces
  the stale-index case `reconcile` exists to fix (S5) — move the folder (and
  its marker), or run `reconcile`, don't edit this path directly.
- **`cache.product_context_path`** — read-only for this skill, as
  `context_packages`'s pre-D21 documented default/fallback (§15.2, Phase 0).
  Setting this alone (no `project_layout`, no `layout.workspace_root`) still
  works exactly as it did originally — step 1 of the resolution algorithm
  above. `plans_output`/`brainstorm_output` have no equivalent config-key
  fallback (they're newer slots, §16.4) — their step-1 fallback is always
  their literal pre-D21 default.
- **`layout.workspace_root`** (D21 §16.2) — optional, repo-relative directory
  path (e.g. `docs/`). When set, each **unmarked** registered slot's resolved
  default becomes `{workspace_root}/<leaf>` (§16.4) — `contexts/` for
  `context_packages`, `outputs/plans/` for `plans_output`, `outputs/specs/`
  for `brainstorm_output` — instead of its pre-D21 default; see "Resolved
  defaults per slot" above. Never overrides a marker or an explicit
  `project_layout.slots.<slot>.path`. `.` and `''` are rejected by
  `validate_layout.py --validate` (S22). Absent by default — a project that
  never sets it resolves exactly as before.
- **`layout.on_missing_write_path`** (resolves H1) — governs what happens when
  a skill tries to *write* to a registered slot but its resolved path doesn't
  exist:
  - `prompt` (default in interactive sessions) — "Configured output path for
    slot '<slot>' ('<path>') doesn't exist — create it now, or has it moved?
    (create / tell me the new path / skip this write)"
  - `skip` (default in non-interactive sessions) — warn, don't write, report
    the write as skipped. Whether that's an error is the calling skill's call.
  - `create` — silently create the directory. Opt-in only — declares "the
    configured path is always correct, create it if absent."

  If unset: `prompt` interactively, `skip` otherwise — never `create` by
  default ("ask the human" degrades to "do nothing and say so," never to
  "guess"). Applies the same way to every registered slot (see the slot
  registry table above — all eight). For the one `kind: file` slot
  (`compiled_guidelines`), "doesn't exist" means the file itself; `create`
  creates its containing directory only — the file is
  `compiling-project-guidelines`'s own output, never fabricated empty by this
  mechanism.

A ready-to-copy template with these keys (annotated) is at
`starter_kits/context_engineering/context-config.yaml.template`.

## CI / pre-commit hook

`init` (unless run with `--no-ci-hook`) scaffolds a hook that runs, from the
repo root:

```
python .github/skills/ult-repo-layout/scripts/validate_layout.py --validate
```

failing the build/commit on a non-zero exit code. This is the only thing the
hook does — no LLM involved (§15.9), same precedent as
`content_hash.py`/`md_index.py`. Wire it into whatever this repo already uses
(`.github/workflows/`, `.pre-commit-config.yaml`, etc.) —
`validate_layout.py` itself has no opinion on the wrapper.

## `scripts/validate_layout.py`

Deterministic, stdlib-only (no pip install), vendorable alongside
`md_index.py`/`content_hash.py`. Run from the repo root:

```
python .github/skills/ult-repo-layout/scripts/validate_layout.py --validate [<repo-root>]
```

Checks (§15.9; all eight slots from the slot registry table above are
registered, but every check is written generically over `SLOT_REGISTRY` — the
mechanism was proven going from 1 to 3 to 8 registered slots with zero
logic changes, including a `kind: file` slot and the S8 partial-install gate
below):

1. **Bijectivity (S15)** — no slot has more than one marker; no two slots
   resolve to the same path.
2. **Type consistency** — a slot's resolved path, if it exists, matches its
   declared `kind`.
3. **Nesting** — same-kind slots sharing a path prefix (excluding `.`).
4. **Path well-formedness (S14)** — repo-relative only (no `..`), no
   Windows-reserved device names (`CON`, `COM1`-`COM9`, etc., exact match
   only — `COM1-migration` is fine), no trailing space/dot segments.
5. **Cross-platform normalization (S12)** — `project_layout.slots.*.path`
   values must use forward slashes.
6. **Config-vanished check (S4)** — `context-config.yaml`'s git history once
   had `initialized: true` but the current file has no `project_layout`
   section (likely accidental deletion) → run `reconcile`.
7. **`workspace_root` well-formedness (D21 §16.2, S22)** — `layout.workspace_root`,
   if set, must be a non-empty repo-relative path other than `.`/`''` (reuses
   check 4's path-wellformedness rules). `.`/`''` → `FAIL` (hard-stop, not a
   silent fallback to either default).

Also reports a non-blocking `WARN` (D21 S18) when an **unmarked** slot has
content at both its pre-D21 default and its `workspace_root`-relative default
— a likely partial migration; `reconcile` lets the human pick one location.

A **`layout-slots-registry.yaml` consistency check** (D21 §16.8, check #10 in
the script's own numbering) — if that file exists at the repo root, its
`slots:` entries with `project_layout_slot: true` must exactly match
`SLOT_REGISTRY`'s keys in this script; `FAIL` on drift in either direction. A
no-op (the file is library-level-only) for every consuming project and every
test fixture, including this repo's own test suite. Read
`references/library-level-registry.md` now and follow it — it has the full
registry schema and the companion `validate_path_conformance.py` check.

An S8 (§15.8) partial-install gate: if this repo has a `.github/skills/`
directory, a slot whose `owning_skill` isn't present under it is skipped
entirely for every check above (no INFO/WARN/FAIL, not part of
bijectivity/nesting) — an adopter who installed only a subset of skills never
sees messages about slots owned by skills they didn't install. Repos with no
`.github/skills/` directory at all (including every test fixture in this
suite) are unaffected — the gate is a no-op there.

11. **Layer path population (D23 §17.8, CEP-DP-001G Stage 2, S28)** — a
    non-blocking `WARN` if an *enabled* layer's resolved path
    (`layers.what_l2.path`, `layers.what_l1.path`, `how_dimension.how_l2.path`,
    `how_dimension.how_l1.path`) doesn't exist or contains no files.
    What-L2/How-L2 are always checked (no opt-out in the shipped config
    surface); What-L1/How-L1 are checked only when their own `enabled: true`
    is set — a disabled opt-in layer left at its placeholder/absent `path`
    never warns. Closes the silent-fallback risk documented in
    `ult-context-generate/SKILL.md`'s D8 table (a misconfigured path and a
    genuinely empty layer previously produced identical, silent behavior).
    Discovery/auto-proposal of these four paths (D23 §17.2–§17.7) is a
    separate, deferred mechanism — this check only validates a path that's
    already configured (or defaulted), it never suggests one.

Exits 0 (`PASS`) or 1 (`FAIL`); prints `INFO`/`NOTE`/`WARN`/`FAIL` lines per
check. Unit tests in `scripts/tests/test_validate_layout.py`.

## Error conditions

| Condition | Action |
|---|---|
| `init` run when `project_layout.initialized: true` | Refuse — "Already initialized. Run `/ult-repo-layout reconcile` to update the index, or `discover` to re-confirm slot locations." (S7) |
| A registered slot has zero markers (`reconcile`) | Ask the human where it moved or whether it was removed — never guess by name similarity |
| A registered slot has multiple markers (any mode) | Bijectivity violation (S15) — surface as a conflict; do not auto-resolve |
| Resolved slot path doesn't exist, read context | Warn-and-continue: "proceeding as if `<slot>` has no content for this run" (S3) |
| Resolved slot path doesn't exist, write context | Apply `layout.on_missing_write_path` (prompt / skip / create) |
| Resolved path exists but wrong `kind` (file vs. directory) | Report as type-consistency violation — distinct from "not found" |
| Resolved path exists but not writable (write context) | Distinct error — "permission denied, not a `project_layout` configuration issue" (S13) |
| `validate_layout.py --validate` on a repo with zero markers and no `project_layout` | `PASS` with one `INFO: project_layout is not initialized...` line per registered slot — not an error |
| `layout.workspace_root` is `.` or `''` | `FAIL` — hard-stop (S22); treated as present-but-invalid, not as absent; applies to every registered slot at once |
| Content at both a slot's pre-D21 default and its `workspace_root`-relative default, no marker | Non-blocking `WARN` — partial migration (S18); `reconcile` lets the human choose one |
| `reconcile --adopt-workspace-root`, slot content at both pre-D21 and `workspace_root`-relative defaults, no marker | Flag as the S18 conflict (§16.11/M5) — offer **neither** pin-marker nor `mv` option; human must resolve the duplication first |
| `reconcile --adopt-workspace-root`, slot already has a marker (anywhere) | Report "unaffected — already has a marker" (§16.11/S16); no options offered, nothing changes |
| `layout-slots-registry.yaml`'s `slots:` (where `project_layout_slot: true`) doesn't exactly match `SLOT_REGISTRY` | `FAIL` (D21 §16.8, check #10) — registry/code drift; a no-op if the file is absent (every consuming project) |

---

This skill is colocated with its own `scripts/` (per the
`ult-context-generate/scripts/md_index.py` precedent — scripts live under the
owning skill, not a shared top-level `scripts/`). It does not read or write
`roles/` — "slot" (path-slot, §15.2) and the `roles/*.json` agent personas are
unrelated concepts that happen to sound similar; see §15.2's terminology note.
