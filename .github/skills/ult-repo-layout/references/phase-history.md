# ult-repo-layout — phase history

Full D20/D21 phase-by-phase build history and exit criteria. Not needed to
operate this skill day to day — see `SKILL.md` for the current operating
manual. Kept here for provenance and for anyone extending the slot registry
further.

This skill implements `context-engineering/CONTEXT-ENGINEERING-DESIGN.md` §15
("Project Layout and Path-Dependency Configuration", D20 v2) and §16
("Workspace Root Consolidation", D21 v3 — `layout.workspace_root`, the Gap-B
slots, scaffold-not-copy, and the `layout-slots-registry.yaml` superset
registry).

## Slots covered

- `context_packages` — read/written by `ult-context-generate` and every
  `CONSUMING-CONTEXT-PACKAGE.md` consumer (D20 Phase 1).
- `plans_output` — illustrative; would be written by a plan-writing skill,
  read by a plan-executing and review-requesting skill (D21 Phase 3b, §16.4
  Gap-B). Not a skill shipped in this repo.
- `brainstorm_output` — illustrative; would be written by a brainstorming
  skill, read by its own spec-reviewer prompt (D21 Phase 3b, §16.4 Gap-B). Not
  a skill shipped in this repo.
- `compiled_guidelines` — written by `compiling-project-guidelines`, read by
  its own `CONSUMING-COMPILED-GUIDELINES.md` consumers (D20 Phase 2). The
  registry's only `kind: file` slot, and the only slot whose D21 default
  re-roots to a different bucket (`inputs` → `cache`).
- `user_stories_output`, `security_docs`, `security_report`,
  `project_plan_docs` — illustrative (D20 Phase 2) — not skills shipped in
  this repo.

...plus **5 starter-kit drop-zones** (`threat_modeling`,
`secure_coding_guidelines`, `security_test_data`, `project_plan`,
`project_guidelines` — D21 §16.6, Phase 3d). These are **not** `project_layout`
path-slots (no marker, no resolution algorithm) — they're regenerated
`.pointer.md` scaffold files; see `references/starter-kit-dropzones.md`.

## Exit criteria, phase by phase

- **Phase 1** — `context_packages` can be renamed/relocated via `reconcile`
  with **zero** manual edits to consuming skills' `SKILL.md` files.
- **Phase 3a** — a project that sets `layout.workspace_root: docs/` and has no
  `context_packages` marker resolves to `docs/contexts/` instead of
  `contexts/`; a project that never sets `workspace_root` is unaffected.
- **Phase 3b** — a `plans_output`/`brainstorm_output` marker pointing
  somewhere other than `docs/superpowers/{plans,specs}/` makes all 5
  retrofitted files (2 producers + 3 consumers, §16.4/H1) resolve to the
  marked location with zero further edits; a project with no marker resolves
  to the pre-D21 default, unchanged.
- **Phase 3d** — `init` on an empty repo produces a fully-wired
  `context-config.yaml` (no `<placeholder>` fields except
  `project_name`/`description`) plus the 5 starter-kit `.pointer.md` files,
  with no `starter_kits/` copy — the directories `install.ps1`/`install.sh`'s
  now-retired `$BUNDLE_OUTPUT_DOCS` hashmap used to scaffold were explicitly
  out of scope for Phase 3d (Phase 3e, below, retired that hashmap).
- **Phase 2** — each of the five new slots (`compiled_guidelines`,
  `user_stories_output`, `security_docs`, `security_report`,
  `project_plan_docs`) is relocatable via `reconcile` with **zero** manual
  edits to its owning skill's `SKILL.md` — the same proof as Phase 1, repeated
  per slot. Phase 2 also registers each new slot's `workspace_root_leaf`
  (§16.4), so `init`/`reconcile` already resolve these five to their D21
  defaults when `layout.workspace_root` is set, with **zero**
  resolution-algorithm changes (Phase 3b proved "no changes" going 1 → 3
  registered slots; Phase 2 repeats the proof going 3 → 8, additionally
  covering a `kind: file` slot and the S8 partial-install gate).
- **Phase 3e** — `init` on an empty repo with `layout.workspace_root` set
  creates `{workspace_root}/outputs/<family>/` for **every** registered
  `outputs`-bucket slot, not just Phase 3b's two — Phase 3d's
  `$BUNDLE_OUTPUT_DOCS` exclusion no longer applies, because
  `install.ps1`/`install.sh` no longer have a `$BUNDLE_OUTPUT_DOCS` hashmap at
  all: `init` step 2 (generic over all eight registered slots since Phase 2)
  is now the single place that scaffolds these directories,
  `workspace_root`-aware. Phase 3e also added the library-level
  `layout-slots-registry.yaml` superset registry (§16.8, see
  `references/library-level-registry.md`), a registry-consistency check (#10)
  in `validate_layout.py`, and the non-blocking 7th path-dependency-review
  dimension backed by `scripts/validate_path_conformance.py`.

All 8 phases (D20 0-2, D21 3a-3e) are now implemented.
