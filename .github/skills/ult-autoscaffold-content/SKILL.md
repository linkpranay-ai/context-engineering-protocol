---
name: autoscaffold-content
description: Generate real starter content for a project's What-L2 (requirements) and How-L2 (architecture/conventions) CEP layers once ult-repo-layout has resolved their paths but found them empty — an honest, minimal, YAML-frontmatter-first overview document per layer for small/single targets, or graphify-informed per-module tiering with resumable per-module CONTEXT.md generation, existence-gated CODING-STANDARDS.md/TESTING-GUIDELINES.md, interface-boundary docs for graph-crossing module pairs, and a rendered CEP-INDEX.md router for large repos, optionally informed by a user-supplied domain-pack of terminology/references if one is configured. This skill generates a NEW starter doc only when none exists — it never compiles or reconciles EXISTING scattered guideline sources (that's compiling-project-guidelines' job). Do NOT use to enforce layout paths or run layer discovery — that's ult-repo-layout. Do NOT use to author or generate a domain pack — this skill only ever consumes one you already wrote.
namespace: ult
version: 0.5.0
origin: ground-up
author: Pranay Mishra
maintainer: Pranay Mishra
adapted_from: ~
upstream_version: ~
released: 2026-08-13
tags: [developer, onboarding, documentation, scaffolding, content-generation]
bundle: utilities
tier: draft
---

# ult-autoscaffold-content

## Overview

`ult-repo-layout` can resolve *where* a project's What-L2 (requirements) and
How-L2 (architecture/conventions) content should live without that content
actually existing yet — a freshly-discovered repo, or a greenfield one, often
has a real, confirmed path and nothing written there. This skill fills that
gap: it writes real, honest, minimal starting content at the exact path
`ult-repo-layout` already resolved, so the layer stops being an empty promise
and starts being something a human can extend.

For a small repo (or a genuinely small layer target), that's one overview
file, same as Phase A — Step 4 has the exact small/large criteria. For a
large repo — many independent, non-trivial subsystems under one target
directory — one overview file undersells it, so
Phase B adds a second path: enumerate modules, rank them by real
dependency importance (not directory size) using `ult-codegraph`'s output
when available, generate a per-module `CONTEXT.md` for the modules that
matter, and persist progress in a state file so a second run resumes
instead of restarting. Both paths write real, human-extensible content —
Phase B doesn't replace Phase A's honesty standard, it scales it.

This is **not** a subprocess the onboarding wizard (`ult-cep-wizard`)
shells out to. Like `compiling-project-guidelines`, it's invoked directly by
a human inside whichever coding agent they already have open — Claude Code,
Copilot Chat, or otherwise. When the wizard's What/How boxes are empty, its
preview card tells the user to run this skill and states the exact path the
result must land at; this skill honors that path rather than picking its
own — the output path is never left to agent discretion, so the wizard's
"Check now" button has a real path to test.

**Run this:**
- When `ult-cep-wizard`'s What or How box is empty and its card told you to
  run this skill
- Standalone, conversationally, any time you want a starting requirements or
  architecture overview for a repo that already has `ult-repo-layout` layer
  paths resolved
- For a large repo, any time you want per-module coverage rather than one
  overview file — or to continue a Phase B run that was interrupted partway
  through
- Standalone, any time you want a repo-wide `CODING-STANDARDS.md`/
  `TESTING-GUIDELINES.md`, or an interface-boundary doc for an
  already-triaged module pair

**Output:** for a small target, one Markdown overview file under the
resolved What-L2 path, one under the resolved How-L2 path, or both —
whichever box(es) prompted the run. For a large target, one `CONTEXT.md`
per covered module under the resolved path, plus a `TRIAGE-STATE.json`
checkpoint and a rendered `CEP-INDEX.md` router file (see
`layout-slots-registry.yaml`'s `autoscaffold_content_state`/
`autoscaffold_content_index` slots for where these live). Independent of
target size, it also writes existence-gated `CODING-STANDARDS.md`/
`TESTING-GUIDELINES.md` and, for graph-mode large-repo runs, per-pair
`interfaces/<module-a>-to-<module-b>.md` docs under the resolved How-L2
path (Step 5c/5d). Every generated file has a YAML frontmatter block
declaring itself a generated draft, and body prose written for a human to
extend, never to treat as finished.

## Hard dependency: `ult-repo-layout` resolves first, always

This skill never invents a path, never scans the filesystem to guess where
requirements or architecture docs "should" go, and never runs before
`ult-repo-layout discover` / `confirm-layers` has produced a real answer. If
neither `layers.what_l2.path` nor `how_dimension.how_l2.path` is resolved in
`context-config.yaml` yet, say so plainly and stop — tell the user to run
`ult-repo-layout` first. This is a one-way dependency: content scaffolding
depends on layout, never the reverse.

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

## Step 2.5 — Resume check (Phase B)

Before deciding anything else, check whether a `TRIAGE-STATE.json` already
exists for this repo (the `autoscaffold_content_state` slot —
`cache/autoscaffold-content/TRIAGE-STATE.json` under the resolved workspace
root; run `scaffold_state.py show <state.json>` if it exists).

- **State file exists:** this repo already has a Phase B run in progress or
  finished. Report current progress plainly (N generated / M pending / K
  skipped, per tier, and which graph mode was used) and ask the user
  whether to **continue** (skip straight to Step 5b for the still-pending
  modules) or **start over** (re-run `scan --rescan` and re-offer the tier
  table). Never silently restart — a silent restart would look like
  progress was lost — and never silently continue either, since the user
  may have meant to target a different, smaller subset this time.
- **No state file:** this is either a first Phase B run or a Phase A
  single-overview run. Continue to Step 3.

## Step 3 — Router/index file

For a **small/single-overview target** (Phase A shape), check whether the
repo already has a small top-level index describing what lives where
(candidate location: `CEP-INDEX.md` at the repo root). If one exists, add
or update the entry for the layer you're about to write into. If none
exists yet and this run stays in the single-overview case, don't invent the
full router-file mechanism here — that's Step 5b/7's job for large repos,
which actually need it. Skip rather than half-build it here — for a
root-level onboarding index across CEP artifacts (not just this layer), run
`ult-onboarding-index` separately/later instead; say so in your final
report.

For a **large target** (Phase B shape, determined at Step 4), the router
file *is* built — it's `scaffold_state.py render-index`'s output, covered
in Step 5b and Step 7, not this step.

## Step 3.5 — Code graph bootstrap (large repos only)

If Step 4's `probe-size` classification (or an explicit user override) is
about to make this a large-repo run, first check whether `ult-codegraph`'s
output is available — follow
`ult-codegraph/CONSUMING-CODE-GRAPH.md` steps 1 and 4 (presence check,
staleness nudge against `graphify-out/GRAPH_REPORT.md`'s "Graph Freshness"
section — not produced under `--no-cluster`, so its absence there is
expected, not an error) rather than duplicating that procedure here. Then
offer a three-state choice, never silently defaulted:

1. **Use the existing graph** (present and not obviously stale).
2. **Regenerate it** — point the user at `/ult-codegraph` (or run
   `graphify update .` yourself if that's the established workflow in this
   project), then use the fresh output.
3. **Proceed with heuristic mode** — file-count-based tiering instead of
   dependency-rank tiering. Explicitly lower confidence; every downstream
   report says so.

Whichever mode is used, state it plainly — same "state which mode you
used" one-liner `CONSUMING-CODE-GRAPH.md` step 3 requires of every graph
consumer: *"Code graph consulted: `graphify-out/graph.json` loaded once for
module-level tiering"* or *"No code graph found — tiering by file count
(heuristic mode)."*

This step's one-time full-graph load (via `scaffold_state.py scan
--graph-mode graphify`) is a **different access pattern** from
`CONSUMING-CODE-GRAPH.md` step 2's "prefer scoped queries" guidance — that
guidance targets repeated per-question consumption during normal work; a
one-time aggregation pass to compute per-module in-degree is a structural
analysis this skill's own script performs directly on `graph.json`, not a
`graphify query` call, and isn't what step 2 is arguing against.

This skill never runs `graphify extract --mode deep` itself — that's a
gated, LLM-backed enrichment `CONSUMING-CODE-GRAPH.md` step 5 owns, with
its own check-then-confirm sequence. If the existing graph seems too sparse
to tier well, mention that deeper extraction exists as an option (per that
doc's own gating), but don't run it inline as part of this skill.

Graph mode also gates Step 5d's interface-boundary docs: they're only ever
offered when this step lands on graphify mode, since a crossing-module
dependency pair is exactly what `graph:in-degree` tiering computes from the
same one-time graph load — heuristic mode has no equivalent signal to
generate them from.

## Step 4 — Repo-size gate: the fork point

Check whether the resolved target path is empty: the directory doesn't
exist, or exists but contains no files after the usual ignored-name
exclusions (`.git`, `__pycache__`, `.DS_Store`, `Thumbs.db`, `.gitkeep` —
same exclusion set `wizard_stub_content.py`'s `_has_content()` already
uses).

- **Not empty** → stop. Tell the user real content already exists at this
  path and that this skill doesn't do partial-fill or reconciliation
  against existing docs — re-running against a non-empty target isn't
  supported.
- **Empty** → classify small vs. large before doing anything else. Run
  `scaffold_state.py probe-size --repo-root <root>` (the same `<root>` the
  Phase B `scan` below uses) — a cheap, read-only count of top-level
  directories that clear `MIN_FILES_FOR_SIZE_GATE` files each, same pruning
  `scan`'s own module enumeration already applies (`.git`, `node_modules`,
  `vendor`, `dist`, `build`, `target`, `.venv`, `__pycache__`,
  `graphify-out`, dot-directories, and the `contexts`/`inputs`/`cache` CEP
  buckets never count). State the count either way — never classify
  silently:
  - **≤ `SMALL_REPO_MAX_MODULES` substantive directories** → small by
    default. Proceed to Step 5 (unchanged Phase A behavior — one overview
    file).
  - **≥ `LARGE_REPO_MIN_MODULES` substantive directories** → large by
    default — this is the Phase B fork:
    1. Run `scaffold_state.py scan <state.json> --repo-root <root>
       --graph-mode <graphify|heuristic> [--graph-path <path>]` (mode
       decided in Step 3.5).
    2. Present the resulting tier table to the user (Tier 1
       high-importance, Tier 2 ordinary, Tier 3 leaf, Tier 0
       generated/vendor — auto-skipped, shown for transparency).
    3. Ask **how much to generate now**: all pending modules, Tier 1 only,
       or a hand-picked subset. This is a "how much work right now" call,
       not a layout-config decision — one question, answered once per run,
       not a PENDING-field-editing artifact.
    4. Proceed to Step 5b for the chosen modules.
  - **Between the two thresholds (the ambiguous band)** → the one case
    with no safe default. State the count and ask the user directly which
    path to take — a wrong guess in either direction either undersells a
    big repo with one thin file or overwhelms a small one with unnecessary
    tiering ceremony.

  These thresholds (`scaffold_state.py`'s `MIN_FILES_FOR_SIZE_GATE`/
  `SMALL_REPO_MAX_MODULES`/`LARGE_REPO_MIN_MODULES`) are flagged
  implementation defaults, not a design-doc-cited number — same posture as
  the Tier 1 thresholds used in Step 3.5/5b. The user can always override
  the probe's classification with an explicit instruction ("treat this as
  a large repo" / "treat this as small"); state which one actually
  governed the run — the probe's default, an ambiguous-band answer, or an
  explicit override.

## Step 4.5 — Domain pack (optional)

Check `context-config.yaml` for `autoscaffold_content.domain_pack_path`.
This key is absent by default — most runs have no domain pack, and that's
the normal case, not a degraded one.

- **Key absent or unset:** state so, one line ("No domain pack configured —
  proceeding on observed evidence only"), and continue unchanged.
- **Key set, but the path doesn't exist:** tell the user plainly the
  configured pack is missing, and continue without it — never invent pack
  content, never block the run over a missing optional file.
- **Key set, and the file exists:** Read it directly. No script parses or
  schema-validates a domain pack — same consumption model this skill
  already uses for `context-config.yaml` itself, and the same "no PyYAML
  dependency, no YAML-parsing script anywhere in this repo" convention
  every other config file in this project follows. See
  `starter_kits/context_engineering/domain-pack.yaml.template` for the
  schema and field-by-field docs. Use its `terminology`/
  `standard_references`/`module_patterns` sections only as vocabulary and
  citation aids for Step 5/5b's prose — **never** as license to assert
  something the codebase doesn't evidence (the "TBD when genuinely
  unknown" rule from Step 5 still governs), **never** written into
  generated frontmatter (frontmatter schema is unchanged by this step),
  and **never** consulted for Step 4's tiering (already decided by the
  time this step runs — tiering stays purely structural, on purpose).

OSS ships **zero built-in domain packs** — this step only ever consumes a
pack the user already wrote themselves; it never authors, suggests, or
scaffolds one.

## Step 5 — Generate (small/single-overview case)

Write one document per requested box. Template-plus-human-extension: this is
a genuine starting point the human is expected to edit, never a claim of
completeness.

- **What box** → open `templates/requirements-overview-template.md` and
  fill it in.
- **How box** → open `templates/architecture-overview-template.md` and fill
  it in.

Base every claim on what you can actually observe — package manifests,
entry points, directory names, existing (even if sparse) docs, commit
history if useful. Never invent requirements or conventions the codebase
doesn't evidence. Where you genuinely don't know, write a plain
"TBD — <what's missing and why>" line instead of guessing plausibly. A wrong
answer stated confidently is worse than an honest gap, for exactly the
reason `compiling-project-guidelines` gives for its own scope-awareness
principle.

## Step 5b — Per-module generation (large repos only)

For each module the user chose to cover in Step 4, one at a time:

1. Open `templates/context-md-template.md` and fill it in, scoped to what's
   observable about *this module specifically* — its own files, its own
   entry points, and (when graph-mode is active) what it depends on and
   what depends on it, per `scaffold_state.py`'s recorded `in_degree` and
   `basis`. Same honesty standard as Step 5: a "TBD" line beats a
   confident guess. Section depth varies by tier — read
   `references/module-context-depth-by-tier.md` for which sections to
   keep before writing; delete the rest from the template rather than
   leaving them half-filled.
2. Immediately call `scaffold_state.py mark-generated <state.json>
   <module-id> --output <path>`, then `scaffold_state.py render-index
   <state.json> --repo-name <name> --out <CEP-INDEX.md path>` so the
   checkpoint and router file both stay current mid-run — if the run is
   interrupted after this point, nothing generated so far is lost or
   miscounted.
3. Continue to the next chosen module. If the user asked for "Tier 1 only"
   or a hand-picked subset, stop after the last one in that set rather than
   continuing into modules they didn't ask for this run.

A module the user explicitly declines (not chosen this run, or actively
deprioritized) gets `scaffold_state.py mark-skipped <state.json>
<module-id> --reason <text>` instead of silently staying `pending` forever
with no record of why it was passed over.

## Step 5c — Repo-wide convention docs (existence-gated)

Runs once per repo, independent of Phase A/B and independent of tiering —
offer it any time How-L2 is in scope and hasn't already been covered.

For each of `CODING-STANDARDS.md` and `TESTING-GUIDELINES.md`, check
whether it already exists at `<how_l2_path>/<filename>`:

- **Already exists:** skip it silently — this step never partially fills or
  reconciles against an existing doc, same non-destructive rule Step 4
  applies to the overview case.
- **Doesn't exist:** ask the user once whether to generate it. If yes, read
  `references/generate-coding-standards.md` or
  `references/generate-testing-guidelines.md` (matching the kind) and
  follow it — each reads real project config to ground the doc in what's
  actually present, then fills `templates/coding-standards-template.md` or
  `templates/testing-guidelines-template.md`. Call
  `scaffold_state.py mark-repo-doc-generated <state.json> <kind> --output
  <path>` immediately after writing. If the user declines, call
  `scaffold_state.py mark-repo-doc-skipped <state.json> <kind> --reason
  <text>` instead of leaving it silently unrecorded.

## Step 5d — Interface-boundary docs (graph-mode, large repos only)

Only reachable when Step 3.5 landed on graphify mode and this is a Phase B
(large-repo) run — see Step 3.5's gating note. Skip this step entirely
otherwise; there's no crossing-edge data to generate from in heuristic mode
or in the small/single-overview case.

1. Run `scaffold_state.py list-interfaces <state.json> --eligible-only` —
   pairs whose both endpoint modules are already `generated` this run
   (Step 5b must reach both endpoints before their interface doc is
   eligible; that's what `--eligible-only` filters for).
2. For each eligible pair the user chooses to cover, read
   `references/generate-interface-docs.md` and follow it — it fills
   `templates/interface-boundary-template.md`, grounded only in the
   graph-observed `relations`/`weight` for that pair (see that reference
   file for exactly what stays `TBD` and why). Call
   `scaffold_state.py mark-interface-generated <state.json> <interface-id>
   --output <path>` immediately after writing.
3. For a pending pair not yet eligible (an endpoint not generated this
   run) or one the user declines, call `scaffold_state.py
   mark-interface-deferred <state.json> <interface-id> --reason <text>`
   (e.g. "endpoint utils/ not generated this run") instead of leaving it
   silently `pending` with no record of why.

## Step 6 — Write exactly where dictated

Write to the path Step 1/2 established for the small/single-overview case,
the resolved target directory (one `CONTEXT.md` per module, under a
module-named subpath) for the large-repo case, or one of these fixed
How-L2 subpaths for Step 5c/5d's repo-wide content:
`<how_l2_path>/CODING-STANDARDS.md`, `<how_l2_path>/TESTING-GUIDELINES.md`,
`<how_l2_path>/interfaces/<module-a>-to-<module-b>.md`. Create parent
directories as needed. Never write anywhere else, and never silently pick a
different filename than what the wizard's card (or this step) specified.

## Step 7 — Report back

**Small/single-overview case:** state plainly which file(s) you wrote, at
which path(s), whether a domain pack was used (per Step 4.5) and, if
this run was triggered by a wizard card — remind the user to go back to
the wizard tab and click "Check now" to confirm the box picked it up.

**Large-repo case:** report:
- The graph mode used (graphify or heuristic, per Step 3.5's
  one-liner requirement) and, if heuristic, the lower-confidence caveat
  again here so it isn't lost between steps.
- Domain pack status, per Step 4.5: used `<path>`, not configured, or
  configured but missing — same "state which mode you used" convention as
  the graph-mode line above.
- The tier summary (module counts per tier) and how many were generated
  this run vs. skipped vs. still pending.
- Repo-wide docs status (Step 5c): which of `CODING-STANDARDS.md`/
  `TESTING-GUIDELINES.md` were generated this run, already existed and were
  left alone, or were skipped by the user.
- Interface-boundary doc status (Step 5d, graph-mode runs only): how many
  pairs were generated this run vs. deferred, per
  `scaffold_state.py list-interfaces`.
- The path to `CEP-INDEX.md` (the router file) and to `TRIAGE-STATE.json`
  (the checkpoint) — `layout-slots-registry.yaml`'s
  `autoscaffold_content_index`/`autoscaffold_content_state` slots.
- How to resume later: re-run this skill against the same target: Step 2.5
  finds the existing state file and picks up where this run left off.

## What this skill deliberately does not do

- **Does not author or generate domain packs.** Only ever consumes a
  user-supplied one if `autoscaffold_content.domain_pack_path` is
  configured (Step 4.5) — OSS ships zero built-in packs, and this skill has
  no mechanism to create one for you. See
  `starter_kits/context_engineering/domain-pack.yaml.template` for the
  shape to copy and fill in yourself.
- **Never mechanically parses or schema-validates a domain pack.** It's
  read directly by the agent as advisory context, the same way
  `context-config.yaml` itself is — no Python script touches it, no PyYAML
  dependency, no structured validation. A malformed pack degrades to "the
  agent does its best reading it," not a crash.
- **Never lets a domain pack influence tiering.** Module importance
  (Step 4) stays purely dependency-rank/file-count based, regardless of
  what a pack's `module_patterns` section claims — Step 4.5 (domain-pack
  consumption) runs after Step 4 (tiering) is already decided, so pack
  content is structurally incapable of reaching the tiering logic.
- **No GLOSSARY.md, no ARCHITECTURE.md-specifically-named file.** Small
  targets get one honestly-titled overview file per box; large targets get
  per-module `CONTEXT.md` files plus `CEP-INDEX.md`; repo-wide and
  interface-boundary content (Step 5c/5d) uses exactly the fixed names
  `CODING-STANDARDS.md`, `TESTING-GUIDELINES.md`, and
  `interfaces/<module-a>-to-<module-b>.md` — no other fixed filenames are
  invented.
- **Does not author Copilot/Claude/Cursor/Codex-specific instruction files
  or a root multi-tool onboarding index.** That's a distinct, deferred
  concern — this skill's own output is tool-agnostic CEP content, consumed
  the same way regardless of which agent reads it.
- **Does not compile or reconcile existing guideline documents** — that's
  `compiling-project-guidelines`'s job, entirely separate from this skill.
- **Does not run layer discovery or touch `context-config.yaml`'s layer
  resolution** — that's `ult-repo-layout`'s job; this skill only reads what
  it already resolved.
- **Does not overwrite or partially fill a non-empty target.** Step 4 stops
  rather than guessing how to merge with what's already there.
- **Never runs `graphify extract --mode deep` itself.** It only ever
  consults whatever graph already exists, inheriting
  `CONSUMING-CODE-GRAPH.md`'s own gated escalation rather than
  reimplementing it — see Step 3.5.
- **Never picks the repo-size classification, tiering thresholds, graph
  mode, or domain-pack status silently.** All four are always stated to
  the user (Step 4's `probe-size` count and classification, Step 3.5's
  mode one-liner, Step 4's tier table, Step 4.5/Step 7's pack-status
  line) — never a quiet default buried in a report nobody reads.
