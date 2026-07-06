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

> **Status: implemented (D20 Phases 0-2 + D21 Phases 3a-3e — all 8 phases
> complete).**
> This skill implements `context-engineering/CONTEXT-ENGINEERING-DESIGN.md`
> §15 (D20 v2, "Project Layout and Path-Dependency Configuration") and §16
> (D21 v3, "Workspace Root Consolidation" — `layout.workspace_root`, the
> Gap-B slots, scaffold-not-copy, and the `layout-slots-registry.yaml`
> superset registry), covering **eight** path-slots:
>
> - `context_packages` — read/written by `ult-context-generate` and every
>   `CONSUMING-CONTEXT-PACKAGE.md` consumer (D20 Phase 1).
> - `plans_output` — written by `writing-plans`, read by
>   `subagent-driven-development` and `requesting-code-review` (D21 Phase 3b,
>   §16.4 Gap-B).
> - `brainstorm_output` — written by `brainstorming`, read by its own
>   `spec-document-reviewer-prompt.md` (D21 Phase 3b, §16.4 Gap-B).
> - `compiled_guidelines` — written by `compiling-project-guidelines`, read by
>   its own `CONSUMING-COMPILED-GUIDELINES.md` consumers (D20 Phase 2). The
>   registry's only `kind: file` slot, and the only slot whose D21 default
>   re-roots to a different bucket (`inputs` → `cache`).
> - `user_stories_output` — written by `spw-write-user-story` (D20 Phase 2).
> - `security_docs` — written by `sec-threat-model` (D20 Phase 2).
> - `security_report` — written by `security-test-report` (D20 Phase 2).
> - `project_plan_docs` — written by `pm-project-plan` (D20 Phase 2).
>
> ...plus **5 starter-kit drop-zones** (`threat_modeling`,
> `secure_coding_guidelines`, `security_test_data`, `project_plan`,
> `project_guidelines` — D21 §16.6, Phase 3d). These are **not**
> `project_layout` path-slots (no marker, no resolution algorithm) — they're
> regenerated `.pointer.md` scaffold files; see "Starter-kit drop-zones and
> `.pointer.md`" below.
>
> Phase 1's exit criterion: `context_packages` can be renamed/relocated via
> `reconcile` with **zero** manual edits to those skills' `SKILL.md` files.
> Phase 3a's exit criterion: a project that sets `layout.workspace_root:
> docs/` and has no `context_packages` marker resolves to `docs/contexts/`
> instead of `contexts/`; a project that never sets `workspace_root` is
> unaffected. Phase 3b's exit criterion: a `plans_output`/`brainstorm_output`
> marker pointing somewhere other than `docs/superpowers/{plans,specs}/` makes
> all 5 retrofitted files (2 producers + 3 consumers, §16.4/H1) resolve to the
> marked location with zero further edits; a project with no marker resolves
> to the pre-D21 default, unchanged. Phase 3d's exit criterion: `init` on an
> empty repo produces a fully-wired `context-config.yaml` (no `<placeholder>`
> fields except `project_name`/`description`) plus the 5 starter-kit
> `.pointer.md` files, with no `starter_kits/` copy — the 4 directories
> `install.ps1`/`install.sh`'s now-retired `$BUNDLE_OUTPUT_DOCS` hashmap used
> to scaffold were explicitly out of scope for Phase 3d (Phase 3e, below,
> retired that hashmap).
> Phase 2's exit criterion: each of the five new slots
> (`compiled_guidelines`, `user_stories_output`, `security_docs`,
> `security_report`, `project_plan_docs`) is relocatable via `reconcile` with
> **zero** manual edits to its owning skill's `SKILL.md` — the same proof as
> Phase 1, repeated per slot. Phase 2 also registers each new slot's
> `workspace_root_leaf` (§16.4), so `init`/`reconcile` already resolve these
> five to their D21 defaults when `layout.workspace_root` is set, with **zero**
> resolution-algorithm changes (Phase 3b proved "no changes" going 1 → 3
> registered slots; Phase 2 repeats the proof going 3 → 8, additionally
> covering a `kind: file` slot and the S8 partial-install gate). Phase 3e's
> exit criterion: `init` on an empty repo with `layout.workspace_root` set
> creates `{workspace_root}/outputs/<family>/` for **every** registered
> `outputs`-bucket slot, not just Phase 3b's two — Phase 3d's
> `$BUNDLE_OUTPUT_DOCS` exclusion no longer applies, because
> `install.ps1`/`install.sh` no longer have a `$BUNDLE_OUTPUT_DOCS` hashmap at
> all: `init` step 2 (generic over all eight registered slots since Phase 2)
> is now the single place that scaffolds these directories,
> `workspace_root`-aware. Phase 3e also added the library-level
> `layout-slots-registry.yaml` superset registry (§16.8, see below), a
> registry-consistency check (#10) in `validate_layout.py`, and the
> non-blocking 7th `amb-review-contribution` dimension, "Path-dependency
> conformance", backed by `scripts/validate_path_conformance.py` (see below).
> All 8 phases (D20 0-2, D21 3a-3e) are now implemented.

## Dependencies

None — this skill is foundational. `ult-context-generate` (`utilities`
bundle, `context_packages`), `writing-plans` (`developer` bundle,
`plans_output`), `brainstorming` (`developer` bundle, `brainstorm_output`),
`compiling-project-guidelines` (`developer` bundle, `compiled_guidelines`),
`spw-write-user-story` (`developer` bundle, `user_stories_output`),
`sec-threat-model` (`security` bundle, `security_docs`),
`security-test-report` (`security` bundle, `security_report`), and
`pm-project-plan` (`manager` bundle, `project_plan_docs`) are **consumers** of
the markers/index this skill maintains (via the §15.5 resolution algorithm,
documented in each owning skill's own path-resolution note) — not dependencies
of this skill.

## Overview

Every project has a handful of **path-slots** — directories or files that one
skill owns and others read (e.g. "where do approved context packages live?").
Hardcoding those paths in every `SKILL.md` means relocating a folder requires
editing every skill that mentions it. D20 fixes this with two pieces:

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

## Slot registry (Phase 1 + Phase 3b + Phase 2)

`project_layout.slots` registers only slots whose path isn't already a key
under `layers.*` / `how_dimension.*` / `graphify.*` / `cache.*` in
`context-config.yaml` (§15.2) — relocating those is "edit the existing key,"
already supported. Phase 1 + Phase 3b + Phase 2 register eight slots:

| Slot key | Kind | Pre-D21 default | D21 default (`layout.workspace_root` set) | Falls back to (if unset) | Owning skill |
|---|---|---|---|---|---|
| `context_packages` | `directory` | `contexts/` | `{workspace_root}/contexts/` | `cache.product_context_path` | `ult-context-generate` |
| `plans_output` | `directory` | `docs/superpowers/plans/` | `{workspace_root}/outputs/plans/` | — | `writing-plans` |
| `brainstorm_output` | `directory` | `docs/superpowers/specs/` | `{workspace_root}/outputs/specs/` | — | `brainstorming` |
| `compiled_guidelines` | `file` | `starter_kit/project_guidelines/COMPILED-GUIDELINES.md` | `{workspace_root}/cache/project-guidelines/COMPILED-GUIDELINES.md` | — | `compiling-project-guidelines` |
| `user_stories_output` | `directory` | `output_docs/user-stories/` | `{workspace_root}/outputs/user-stories/` | — | `spw-write-user-story` |
| `security_docs` | `directory` | `output_docs/security_docs/` | `{workspace_root}/outputs/security_docs/` | — | `sec-threat-model` |
| `security_report` | `directory` | `output_docs/security_report/` | `{workspace_root}/outputs/security_report/` | — | `security-test-report` |
| `project_plan_docs` | `directory` | `output_docs/project_plan_docs/` | `{workspace_root}/outputs/project_plan_docs/` | — | `pm-project-plan` |

The "D21 default" column only applies to an **unmarked** slot when
`layout.workspace_root` is set (§16.2 step 3) — it never overrides a marker or
an explicit `project_layout.slots.<slot>.path` (§16.2 steps 1-2). A project
that never sets `layout.workspace_root` resolves via the "Pre-D21
default"/"Falls back to" columns exactly as before, forever (§16.10).

`plans_output` and `brainstorm_output` are the two **Gap-B** slots D21 §16.4
registers to close a gap Phase 1 left open: `docs/superpowers/{plans,specs}/`
were hardcoded output paths with no D20 slot at all. Like the five Phase 2
slots below, neither has a pre-existing config-key fallback — "Falls back to"
is "—", so an unmarked slot's step-1 fallback is simply its literal pre-D21
default.

Phase 2 (§15.11) registers the five remaining D20 slots:

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
  `output_docs/<family>/` subtree (§16.7's own example). All four belong to
  D21's `outputs` bucket, alongside `plans_output`/`brainstorm_output` — their
  D21 defaults sit under `{workspace_root}/outputs/`. None of the four nests
  inside another (they diverge at `output_docs/<family>/`'s second path
  segment), so `scripts/validate_layout.py`'s nesting check (§15.9 #3) needs no
  `nests_under:` whitelist entries for this set.

`context_addenda` (the `*.addenda.yaml` siblings D19 v2 writes) is **not** a
separate slot — its path is always
`{resolved context_packages path}/{package-id}_{date}.addenda.yaml` (§15.4).

`scripts/validate_layout.py`'s `SLOT_REGISTRY` is written generically over
"any number of registered slots." Phase 3b was the first slot-count increase
to exercise that claim (1 → 3, zero check-logic changes); Phase 2 is the
second (3 → 8) — it additionally exercises a `kind: file` slot and the S8
(§15.8) partial-install gate: a slot whose `owning_skill` directory isn't
present under this repo's `.github/skills/` is skipped entirely (no
INFO/WARN/FAIL, not part of bijectivity/nesting), so an adopter who installed
only the `developer` bundle never sees messages about
`security_docs`/`security_report`/`project_plan_docs`.

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
  (`resolved_path_for_marker` in `scripts/validate_layout.py` already handled
  this generically since Phase 1 — `compiled_guidelines` is simply the first
  slot to use it).
- `schema_version` — the `project_layout` schema version that introduced this
  slot (§15.8); `1` for the three Phase 1 + Phase 3b slots (`context_packages`,
  `plans_output`, `brainstorm_output`), `2` for the five Phase 2 slots
  (`compiled_guidelines`, `user_stories_output`, `security_docs`,
  `security_report`, `project_plan_docs`).
- If two slots happen to share a directory, list both entries under that one
  `slots:` array — one marker file can declare multiple slots.

## Starter-kit drop-zones and `.pointer.md` (D21 §16.6, Phase 3d)

Five `inputs/`-bucket drop-zones (§16.3/§16.4's starter-kit row) hold
project-owned, human-curated material that one or more skills read but never
regenerate:

| Leaf | Library source | Read by |
|---|---|---|
| `threat_modeling` | `starter_kits/security/threat_modeling/` | `sec-threat-model` |
| `secure_coding_guidelines` | `starter_kits/security/secure_coding_guidelines/` | *(none — reference material only)* |
| `security_test_data` | `starter_kits/security/security_test_data/` | `security-test-report` |
| `project_plan` | `starter_kits/manager/project_plan/` | `pm-project-plan` |
| `project_guidelines` | `starter_kits/project_guidelines/` | `compiling-project-guidelines` |

`context_engineering` (the 6th former `BUNDLE_STARTER_KIT['developer']`
entry) is **not** in this list — its only role was a manual
`context-config.yaml.template` copy-to-root, fully subsumed by "Generated
`context-config.yaml`" below. It is no longer scaffolded into projects at all.

Each drop-zone's directory contains a **regenerated** `.pointer.md` — never
copied, never hand-edited — alongside whatever files the project drops there:

```markdown
# <leaf> — starter-kit drop-zone

This directory holds project-owned, human-curated material for `<leaf>`.
Current template and README: `starter_kits/<library source path>/` in the
radisys-ai-power-lib library (gitlab.radisys.com/qe/quality_assets).

This file is regenerated by the installer's -InitProject/--init-project mode
and by `/ult-repo-layout init`/`reconcile` — do not edit it directly. Place
your own files alongside it; they are never touched.
```

**Location** (no marker, no `project_layout` entry — these are scaffold
files, not path-slots):

- **`layout.workspace_root` unset (pre-D21 default, today's behavior)** —
  `starter_kit/<leaf>/.pointer.md`, flat, matching the path every consuming
  skill already reads (e.g. `starter_kit/threat_modeling/`).
- **`layout.workspace_root` set** —
  `{workspace_root}/inputs/starter-kit/<leaf>/.pointer.md` (§16.3's `inputs/`
  bucket). Re-rooting a drop-zone this way is a human-actioned content move
  (§16.6) — `init`/`reconcile` only ever regenerate the pointer file at
  whichever location currently holds the drop-zone's content, they never move
  files themselves.

**Regeneration is idempotent and additive-only**: `install.ps1`/`install.sh
-InitProject` creates `starter_kit/<leaf>/` (if absent) and writes/overwrites
just `.pointer.md` inside it — any other files already there are left alone.
`/ult-repo-layout init`/`reconcile` do the same at the drop-zone's current
location. Consuming skills' content-discovery globs (`sec-threat-model`,
`pm-project-plan`, `compiling-project-guidelines`) skip `.pointer.md` — see
each skill's `SKILL.md` for the exact exclusion.

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

**Then run steps 1-5 below** (unchanged from Phase 1/3b, except that step 2's
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
         owning_skill: writing-plans
       brainstorm_output:
         path: docs/superpowers/specs/        # or wherever step 2 resolved it
         kind: directory
         owning_skill: brainstorming
       compiled_guidelines:
         path: starter_kit/project_guidelines/COMPILED-GUIDELINES.md  # or wherever step 2 resolved it
         kind: file
         owning_skill: compiling-project-guidelines
       user_stories_output:
         path: output_docs/user-stories/        # or wherever step 2 resolved it
         kind: directory
         owning_skill: spw-write-user-story
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
6. `reconcile --adopt-workspace-root <path>` (D21 §16.6) — **advisory/dry-run
   only: moves nothing, writes no marker.** For an **existing** project that
   just added `layout.workspace_root: <path>` to `context-config.yaml` and
   wants to know what changes, for every registered slot:
   - **Already has a marker (anywhere)** → report "`<slot>` — unaffected,
     already has a marker at `<marker path>`" (§16.11/S16) and move on. A
     marker always wins over `workspace_root`, so adopting it changes nothing
     for this slot.
   - **No marker, content exists at BOTH the pre-D21 default AND the
     `{workspace_root}/<leaf>` default** → flag as the S18 conflict (§16.11/M5)
     — "`<slot>` has content at both `<pre-D21 path>` and `<workspace_root
     path>` — resolve this duplication by hand before adopting
     `workspace_root` for this slot" — and offer **neither** option below for
     this slot.
   - **No marker, content exists only at the pre-D21 default** → report both
     human-actioned options, pick one:
     - (a) write a marker at the *current* (pre-D21) location, pinning this
       slot there indefinitely (same effect as `workspace_root` never having
       been set, for this slot only); or
     - (b) print the `mv`/`git mv` command to relocate the slot's content to
       `{workspace_root}/<leaf>` — after running it, the existing zero-marker
       `reconcile` flow (step 3 above, unchanged) writes the marker at the new
       location on the next run.
   - **No marker, nothing exists yet at either location** → report
     "`<slot>` — no content yet; future writes will use
     `{workspace_root}/<leaf>` (its new resolved default)." No action needed.

   The same report additionally lists each of the 5 starter-kit drop-zones
   (§16.6, "Starter-kit drop-zones and `.pointer.md`" above): current path
   (`starter_kit/<leaf>/`) vs. `{workspace_root}/inputs/starter-kit/<leaf>/`,
   with the same `mv`/`git mv` suggestion (option (b) shape) if the human
   wants to re-root a drop-zone's content. Drop-zones have no marker
   mechanism, so option (a) doesn't apply to them — after a human-run `mv`,
   the next `init`/`reconcile` simply regenerates `.pointer.md` at the new
   location (it already follows "current location," per that section).

   Whichever option the human picks, **`--adopt-workspace-root` itself takes
   no further action** — the marker write (option a) or the next `reconcile`
   pass (after option b's `mv`) is what actually changes state, using D20's
   already-shipped primitives. This is intentional: §15.7 never auto-moves
   content, and `workspace_root` changes *defaults only* (§16.2/S16).

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
   `output_docs/security_docs/`, or this repo's own
   `output_docs_structure/<family>/` convention), mention it as a likely
   answer rather than asking cold.
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
path: `ult-context-generate`/`CONSUMING-CONTEXT-PACKAGE.md`
(`context_packages`),
`writing-plans`/`subagent-driven-development`/`requesting-code-review`
(`plans_output`), `brainstorming`/`spec-document-reviewer-prompt.md`
(`brainstorm_output`),
`compiling-project-guidelines`/`CONSUMING-COMPILED-GUIDELINES.md`
(`compiled_guidelines`), `spw-write-user-story` (`user_stories_output`),
`sec-threat-model` (`security_docs`), `security-test-report`
(`security_report`), and `pm-project-plan` (`project_plan_docs`):

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
  (`cache.product_context_path`) — a project that set this key before Phase 1
  ever existed continues to work unchanged, even with `layout.workspace_root`
  unset.
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
did before Phase 3a/3b/Phase 2, forever (§16.10's zero-impact guarantee).
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
  works exactly as it did before Phase 1 — step 1 of the resolution algorithm
  above. `plans_output`/`brainstorm_output` have no equivalent config-key
  fallback (they're new slots, §16.4) — their step-1 fallback is always their
  literal pre-D21 default.
- **`layout.workspace_root`** (D21 §16.2, new in Phase 3a; Phase 3b extends its
  effect to 2 more slots) — optional, repo-relative directory path (e.g.
  `docs/`). When set, each **unmarked** registered slot's resolved default
  becomes `{workspace_root}/<leaf>` (§16.4) — `contexts/` for
  `context_packages`, `outputs/plans/` for `plans_output`, `outputs/specs/`
  for `brainstorm_output` — instead of its pre-D21 default; see "Resolved
  defaults per slot" above. Never overrides a marker or an explicit
  `project_layout.slots.<slot>.path`. `.` and `''` are rejected by
  `validate_layout.py --validate` (S22). Absent by default — a project that
  never sets it resolves exactly as before Phase 3a, forever.
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

Checks (§15.9; Phase 1 + Phase 3b + Phase 2 register all eight slots from the
slot registry table above, but every check is written generically over
`SLOT_REGISTRY` — Phase 3b proved "no logic changes" going from 1 to 3
registered slots, and Phase 2 repeats the proof going from 3 to 8, this time
including a `kind: file` slot and the S8 partial-install gate below):

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

Phase 3e adds a **`layout-slots-registry.yaml` consistency check** (D21
§16.8, check #10 in the script's own numbering) — if that file exists at the
repo root, its `slots:` entries with `project_layout_slot: true` must exactly
match `SLOT_REGISTRY`'s keys in this script; `FAIL` on drift in either
direction. A no-op (the file is library-level-only — see
"`layout-slots-registry.yaml`" below) for every consuming project and every
test fixture, including this repo's own test suite.

Phase 2 adds an S8 (§15.8) partial-install gate: if this repo has a
`.github/skills/` directory, a slot whose `owning_skill` isn't present under
it is skipped entirely for every check above (no INFO/WARN/FAIL, not part of
bijectivity/nesting) — an adopter who installed only the `developer` bundle
never sees messages about `security_docs`/`security_report`/
`project_plan_docs`. Repos with no `.github/skills/` directory at all
(including every test fixture in this suite that predates Phase 2) are
unaffected — the gate is a no-op there.

Exits 0 (`PASS`) or 1 (`FAIL`); prints `INFO`/`NOTE`/`WARN`/`FAIL` lines per
check. Unit tests in `scripts/tests/test_validate_layout.py`.

## `layout-slots-registry.yaml` — library-level superset registry (D21 §16.8)

A library-level file at `radisys-ai-power-lib`'s repo root — **not** generated
by `init`/`reconcile`, **not** copied into consuming projects, and not itself
a `project_layout` path-slot. A superset registry, one row per path any skill
reads or writes outside its own code tree, mirroring §16.4's table in
structured YAML. Three top-level sections under `schema_version: 1`:

- **`slots:`** — the eight `project_layout` slots from the "Slot registry"
  table above, each with `id`, `project_layout_slot: true`, `kind`,
  `default_bucket`, `pre_d21_default`, `workspace_root_leaf`, `config_key`
  (only `context_packages` has one — `cache.product_context_path`; `~` for
  the rest), `producer`, and `consumers`.
- **`config_keys:`** — the six existing `layers.*`/`how_dimension.*`/
  `graphify.*`/`cache.*` config keys (`what_l2_path`, `what_l1_path`,
  `how_dimension_path`, `how_l2_cache_path`, `graphify_graph_path`,
  `index_paths`), each `project_layout_slot: false`, with `config_key`,
  `kind`, `pre_d21_default`, and `workspace_root_leaf`/`workspace_root_default`.
- **`starter_kit_dropzones:`** — the five drop-zones from "Starter-kit
  drop-zones and `.pointer.md`" above (`threat_modeling`,
  `secure_coding_guidelines`, `security_test_data`, `project_plan`,
  `project_guidelines`), each `project_layout_slot: false`,
  `default_bucket: inputs`, with `consumers` where applicable.

Consumed by:

1. `validate_layout.py`'s registry-consistency check (#10, above) — keeps
   `SLOT_REGISTRY` (code) and `layout-slots-registry.yaml` (registry) in sync;
   `FAIL` on drift.
2. `validate_path_conformance.py` (below) — the 7th `amb-review-contribution`
   dimension's backend, which looks up a contributed skill's hardcoded path
   literals against this registry's `pre_d21_default`/`workspace_root_leaf`/
   `workspace_root_default` columns.

Since this file is library-level-only, both consumers treat its absence as a
no-op — every consuming project and every test fixture in this repo's own
suite simply skips the corresponding check/finding.

## `scripts/validate_path_conformance.py` (7th amb-review dimension, D21 §16.8)

Deterministic, stdlib-only, sibling to `validate_layout.py` (whose
`load_yaml_file()` it reuses to read `layout-slots-registry.yaml`). Backs
`meta-skills/amb-review-contribution`'s 7th review dimension, "Path-dependency
conformance" — **entirely non-blocking/informational** (resolves H3), never
exits non-zero on findings:

```
python .github/skills/ult-repo-layout/scripts/validate_path_conformance.py --validate <skill-md-or-dir> [<repo-root>]
```

Scans every `.md` file under `<skill-md-or-dir>` for lines matching a
write-verb-object pattern (`sav(e|es|ed|ing) ... to`, `writ(e|es|ten|ing) ...
to`, `creat(e|es|ed|ing) ... at`, `output(s|ted|ting)? ... to`, verb and
preposition within 40 characters of each other) with a backtick-quoted,
path-shaped literal (contains `/`, no whitespace, not a URL) on the same line.
For each match:

- **Not in `layout-slots-registry.yaml`** — `"possible new path convention
  ('<literal>') - consider registering it in layout-slots-registry.yaml
  (§16.4)."`
- **Matches a registered slot's default** — `"slot '<id>' is registered
  (§16.4) - resolve its path via §15.5 instead of hardcoding '<literal>', so
  projects that relocate '<id>' aren't broken by this skill."`
- **Matches a registered config-key/dropzone default** — `"'<literal>'
  matches the registered default for '<id>' (§16.4) - resolve it via
  context-config.yaml's resolution algorithm for that key instead of
  hardcoding, ..."`

`amb-review-contribution` runs this against the contributed file(s) and pastes
findings verbatim into its MR comment's "### 7. Path-dependency conformance"
section — `Clear` if the report is empty. Unit tests in
`scripts/tests/test_validate_path_conformance.py`.

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
