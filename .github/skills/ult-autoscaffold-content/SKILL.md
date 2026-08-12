---
name: autoscaffold-content
description: Generate real starter content for a project's What-L2 (requirements) and How-L2 (architecture/conventions) CEP layers once ult-repo-layout has resolved their paths but found them empty — an honest, minimal, YAML-frontmatter-first overview document per layer, written to the exact path ult-repo-layout resolved. Do NOT use to enforce layout paths or run layer discovery — that's ult-repo-layout. Do NOT use to compile or reconcile existing guideline documents — that's compiling-project-guidelines. Do NOT use on a large repo expecting per-module triage or tiered coverage — that mechanism doesn't exist yet (Phase B, unbuilt); this phase only handles the single-overview-file, empty-target case.
namespace: ult
version: 0.1.0
origin: ground-up
author: Pranay Mishra
maintainer: Pranay Mishra
adapted_from: ~
upstream_version: ~
released: 2026-08-12
tags: [developer, onboarding, documentation, scaffolding, content-generation]
bundle: utilities
tier: draft
---

# ult-autoscaffold-content

**Status: Phase A only (empty-case, single-overview-file generation).** Phase B
(large-repo triage/tiering, resume/checkpoint across runs), Phase C (domain
packs), and Phase D (wizard integration, CI wiring) are designed but not yet
built — see `D24-WIZARD-REMAINING-WORK.md` in the design repo for the full
phase sequence. Nothing in this file should be read as covering those phases.

## Overview

`ult-repo-layout` can resolve *where* a project's What-L2 (requirements) and
How-L2 (architecture/conventions) content should live without that content
actually existing yet — a freshly-discovered repo, or a greenfield one, often
has a real, confirmed path and nothing written there. This skill fills that
gap: it writes a real, honest, minimal starting document at the exact path
`ult-repo-layout` already resolved, so the layer stops being an empty promise
and starts being something a human can extend.

This is **not** a subprocess the onboarding wizard (`ult-layout-wizard`)
shells out to. Like `compiling-project-guidelines`, it's invoked directly by
a human inside whichever coding agent they already have open — Claude Code,
Copilot Chat, or otherwise. When the wizard's What/How boxes are empty, its
preview card tells the user to run this skill and states the exact path the
result must land at; this skill honors that path rather than picking its own
(§18.6 round-3 M5 of the design doc: never leave the output path to agent
discretion, so the wizard's "Check now" button has a real path to test).

**Run this:**
- When `ult-layout-wizard`'s What or How box is empty and its card told you to
  run this skill
- Standalone, conversationally, any time you want a starting requirements or
  architecture overview for a repo that already has `ult-repo-layout` layer
  paths resolved

**Output:** one Markdown file under the resolved What-L2 path, one under the
resolved How-L2 path, or both — whichever box(es) prompted the run. Each file
has a YAML frontmatter block declaring itself a generated draft, and body
prose written for a human to extend, never to treat as finished.

## Hard dependency: `ult-repo-layout` resolves first, always

This skill never invents a path, never scans the filesystem to guess where
requirements or architecture docs "should" go, and never runs before
`ult-repo-layout discover` / `confirm-layers` has produced a real answer. If
neither `layers.what_l2.path` nor `how_dimension.how_l2.path` is resolved in
`context-config.yaml` yet, say so plainly and stop — tell the user to run
`ult-repo-layout` first. This is the same one-way dependency direction
§18.3 of the design doc establishes for the whole D24 surface: content
scaffolding depends on layout, never the reverse.

## Step 1 — Determine invocation mode

Two ways this skill gets run:

1. **From a wizard card.** The user pasted a prompt block the wizard
   generated. That prompt names the exact expected output path — use it
   verbatim, don't re-resolve it yourself.
2. **Standalone.** The user asked you directly ("generate a starter
   architecture doc for this repo"). Proceed to Step 2 to resolve the path
   yourself.

## Step 2 — Resolve target

Read the project's `context-config.yaml`:

- **What box** → `layers.what_l2.path`
- **How box** → `how_dimension.how_l2.path`

If the config file is absent, or the relevant key is unset/`enabled: false`,
that layer hasn't been resolved — stop for that box specifically (the other
box may still be resolvable) and tell the user to run `ult-repo-layout
discover` then `confirm-layers` first. Do not fall back to a guessed
directory like `docs/` — an unresolved layer is a stop condition, not a
default.

## Step 3 — Router/index file

Check whether the repo already has a small top-level index describing what
lives where (candidate location: `CEP-INDEX.md` at the repo root, or a
`project_layout` note inside `context-config.yaml` — the concrete shape is
still open and may vary run to run until Phase B settles it structurally).
If one exists, add or update the entry for the layer you're about to write
into. If none exists yet, this phase does not invent the full router-file
mechanism (that's real design work reserved for Phase B, where it has to
handle many modules, not one overview file) — skip this step rather than
half-building a mechanism this phase can't finish, and say so in your final
report to the user.

## Step 4 — Repo-size gate (Phase A: empty case only)

Check whether the resolved target path is empty: the directory doesn't exist,
or exists but contains no files after the usual ignored-name exclusions
(`.git`, `__pycache__`, `.DS_Store`, `Thumbs.db`, `.gitkeep` — same exclusion
set `wizard_stub_content.py`'s `_has_content()` already uses; keep your own
check consistent with it rather than diverging).

- **Empty** → proceed to Step 5.
- **Not empty** → stop. Tell the user real content already exists at this
  path and that this phase doesn't do partial-fill or reconciliation against
  existing docs — re-running against a non-empty target isn't yet supported.
- **Repo is large** (roughly: the target layer would need per-module
  coverage, not one overview file, to be useful — e.g. a monorepo with many
  independent subsystems) → say so plainly: "This repo looks large enough
  that a single overview file undersells it — per-module triage and tiered
  coverage is designed but not built yet (Phase B). Generating one overview
  file for now; treat it as a starting point, not full coverage." Then
  proceed to Step 5 anyway — a partial, honest starting point is still better
  than nothing, as long as it's labeled as partial.

## Step 5 — Generate

Write one document per requested box. Template-plus-human-extension: this is
a genuine starting point the human is expected to edit, never a claim of
completeness.

YAML frontmatter first, then body prose:

```markdown
---
generated_by: ult-autoscaffold-content
generated_at: <YYYY-MM-DD>
status: draft
---

# <Project name> — <Requirements Overview | Architecture & Conventions Overview>

<Honest, minimal prose. Base every claim on what you can actually observe —
package manifests, entry points, directory names, existing (even if sparse)
docs, commit history if useful. Never invent requirements or conventions the
codebase doesn't evidence. Where you genuinely don't know, write a plain
"TBD — <what's missing and why>" line instead of guessing plausibly. A wrong
answer stated confidently is worse than an honest gap, for exactly the reason
`compiling-project-guidelines` gives for its own scope-awareness principle.>
```

What box → cover: what the project is, who/what it's for, the functional
requirements you can actually observe or infer from the codebase.

How box → cover: the project's structure, key design decisions you can
observe, and any conventions a new contributor should follow.

## Step 6 — Write exactly where dictated

Write to the path Step 1/2 established — the wizard card's exact path if
invoked that way, the resolved `context-config.yaml` path if standalone.
Create parent directories as needed. Never write anywhere else, and never
silently pick a different filename than what the wizard's card specified.

## Step 7 — Report back

State plainly: which file(s) you wrote, at which path(s), and — if this run
was triggered by a wizard card — remind the user to go back to the wizard tab
and click "Check now" to confirm the box picked it up. If Step 4 hit the
large-repo case, repeat that caveat here so it isn't lost between steps.

## What this skill deliberately does not do (Phase A)

- **No large-repo triage or tiering.** No module enumeration, no
  dependency-rank-based importance scoring, no per-module `CONTEXT.md`
  files. One overview file per requested box, full stop, this phase.
- **No resume/checkpoint across runs.** Each run is a single pass against an
  empty target; there's no persisted state tracking partial progress yet.
- **No domain packs.** No pluggable domain-specific content (telecom,
  fintech, etc.) — §18.8's mechanism is still undesigned.
- **No GLOSSARY.md, no ARCHITECTURE.md-specifically-named file, no fixed
  router-file mechanism.** These are named in the design doc's fuller vision
  but are Phase B/C scope — Phase A writes one honestly-titled overview file
  per box and says so.
- **Does not compile or reconcile existing guideline documents** — that's
  `compiling-project-guidelines`'s job, entirely separate from this skill.
- **Does not run layer discovery or touch `context-config.yaml`'s layer
  resolution** — that's `ult-repo-layout`'s job; this skill only reads what
  it already resolved.
- **Does not overwrite or partially fill a non-empty target.** Step 4 stops
  rather than guessing how to merge with what's already there.
