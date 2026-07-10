# Setting up a project repo for context engineering

This guide walks through preparing a project repo so the skills in this repo get
good, source-attributed context — from "just the team's coding conventions" up to
"full code graph + requirements + constraints + blast radius, human-approved before
anything is generated."

It covers two paths:

- **Simple**: only compiled guidelines (`compiling-project-guidelines`'s output) feed
  downstream skills.
- **Complex**: the full context-engineering pipeline (`ult-codegraph` +
  `ult-context-generate`) — code graph, requirements, org conventions, and
  constraints, all assembled into a human-approved package that any consuming skill
  can build on (see `demo-consume-context` for a minimal worked example).

Both paths are valid end states — pick based on project size and how much any
downstream work needs to be grounded in real code/requirements structure. You can
start Simple and add the Complex pieces later; nothing in Simple needs to be undone.

---

## Path A — Simple: compiled guidelines only

**When this is enough:** small/medium codebases where you mainly want existing
conventions respected by any code-facing skill you run, but don't need a generated,
approved context package per feature.

### Setup steps

1. Run `/ult-compile-guidelines` (the `compiling-project-guidelines` skill). It
   auto-discovers conventional sources (`.github/instructions/*.instructions.md`,
   `.github/copilot-instructions.md`, `CONTRIBUTING.md`, `docs/guidelines/**`,
   `docs/architecture/**`), asks you to confirm/add/remove, and writes:
   ```
   starter_kit/project_guidelines/COMPILED-GUIDELINES.md
   ```
2. That's it. Any code-facing skill that follows `CONSUMING-COMPILED-GUIDELINES.md`
   will read this file first and apply the most-specific scoped guidance —
   automatically, non-blocking.
3. **Maintenance**: re-run `/ult-compile-guidelines` whenever a guideline source
   changes ("update my compiled guidelines — I added `docs/payments-conventions.md`").
   The compiled file's `## Noted Tensions` section is append-only and preserves prior
   conflict-resolution decisions across re-runs.

No other folders are required for this path.

---

## Path B — Complex: full context-engineering pipeline

**When you need this:** larger/multi-repo codebases, or any workflow where you want a
consuming skill to ground its work in real code structure, traced requirements, and an
explicit blast-radius/non-regression analysis — with a human approval gate before
anything downstream is generated.

### Setup steps

1. **Compile guidelines first** (Path A) — `ult-context-generate` Step 5.5 reads
   `starter_kit/project_guidelines/COMPILED-GUIDELINES.md` as the Constraints layer
   if it exists. Optional but recommended.

2. **Generate the code graph**: run `/ult-codegraph`. This produces, at the project
   root:
   ```
   graphify-out/graph.json
   graphify-out/GRAPH_REPORT.md
   graphify-out/graph.html
   ```
   This is What-L3. No normalization or copying — `graphify`'s own fixed output
   location is read directly by `ult-context-generate`.

3. **Add a `context-config.yaml`** at the project root. If you ran
   `./install.sh --init-project` / `install.ps1 -InitProject` (see the
   [Quickstart](../../README.md#quickstart)), this file already exists — skip the copy
   and go straight to filling it in. Otherwise, copy the template by hand:
   ```
   starter_kits/context_engineering/context-config.yaml.template → ./context-config.yaml
   ```
   Either way, fill in `project_name`, `description`, and the layer paths
   (`what_l3.path` = source root, `what_l2.path` = requirements docs root,
   `how_l2.path` = org conventions root). For `what_l1`, see step 4 below; for
   `how_l1`, see step 7 below — both are implemented but piloting, so the
   recommended default is to leave them disabled until you've run each once
   against your own corpus (see
   [What-L1 and How-L1 (both piloting)](#what-l1-and-how-l1-both-piloting)
   below).

4. **Populate What-L1 (external references) — optional, piloting**: if your
   feature touches an aspect with relevant external reference material (industry
   standards, competitor docs, architecture whitepapers), drop `.md` excerpts under a
   directory such as `specs/external/`, then in `context-config.yaml` set:
   ```yaml
   what_l1:
     enabled: true
     path: specs/external/
     md_index_profile: generic   # generic | 3gpp | rfc | ieee | <your-profile>.json
     index_path: specs-out/index.json
     graphify_budget: 20
   ```
   `ult-context-generate` Step 7.1 builds a deterministic structural index of these
   `.md` files (`scripts/md_index.py` — "the graphify for markdown", zero-LLM) and
   queries it only for aspects that are a "both-layers-gap candidate" (no What-L2 or
   What-L3 coverage for that aspect). Every match becomes a `context_items` entry
   with `what_l1_fallback: true`, presented in a dedicated
   `[L1 FALLBACK ITEMS — REVIEW]` block at Step 9 — the human reviewer must confirm
   (or reject) each item's product relevance before approval. See setup step 4 above
   to enable it.
   Skip this step if `what_l1.enabled: false` (the default) — every both-layers-gap
   aspect instead falls through to the disclosed training-knowledge offer (Step 7.1
   step 5a), then to the complete-gap prompt only if that's also declined or empty.

5. **Populate What-L2 (requirements)**: put requirements docs under the path you
   set for `what_l2` (default `docs/requirements/`). `ult-context-generate` Step 5
   reads these directly (not via the code graph) for small corpora — at or below
   `what_l2.large_corpus_threshold` (default 10) `.md` files. Larger corpora switch
   automatically to the same `scripts/md_index.py` indexed mechanism as What-L1
   (`what_l2.index_path`, default `specs-out/l2_index.json`, and
   `what_l2.md_index_profile`, default `generic`) — no extra setup beyond having the
   files in place.

6. **Populate How-L2 (org conventions/templates)**: under the path you set for
   `how_l2` (default `org/`):
   ```
   org/templates/     — document/artifact templates
   org/examples/      — worked examples of "good" output for this org
   org/guidelines/    — narrative guidance on house style
   ```
   `ult-context-generate` Step 2 reads these and caches the result to
   `org-conventions/<task_type>.yaml`, gated on `human_approved: true`.

7. **Populate How-L1 (org-wide process standards) — optional, piloting**: if your
   org has its own CMMI/ISO/IEEE-style process standards you want incorporated,
   drop `.md` excerpts under a directory such as `org/process-standards/`, then in
   `context-config.yaml` set:
   ```yaml
   how_dimension:
     how_l1:
       enabled: true
       path: org/process-standards/
       md_index_profile: generic   # generic | 3gpp | rfc | ieee | <your-profile>.json
       index_path: specs-out/how_l1_index.json
       graphify_budget: 20
   ```
   `ult-context-generate` Step 2.1 queries this the same way What-L1 is queried
   (`scripts/md_index.py`, zero-LLM), but **gap-triggered once per package**
   instead of per aspect — it only fires when Step 2's How-L2 check finds nothing
   for the task type at hand. Every match becomes a `context_items` entry with
   `how_l1_fallback: true`, presented in a dedicated
   `[HOW-L1 FALLBACK ITEMS — REVIEW]` block at Step 9 for human confirm/reject,
   same as What-L1. There's no web-search/training-knowledge fallback chain for
   How-L1 — Step 2's existing gap prompt substitutes for one if How-L1 is
   disabled or comes up empty. Skip this step if `how_l1.enabled: false` (the
   default).

8. **Run `/ult-context-generate`**. Walk through the 10-step flow; approve both the
   product context package and the org convention package when prompted. Output:
   ```
   contexts/<feature-slug>_<task-type>_<YYYYMMDD>.yaml
   org-conventions/<task-type>.yaml
   ```

9. **Try the worked-example consumer**: run `demo-consume-context` against the
   approved package (a bare feature name is enough as input). It follows
   `CONSUMING-CONTEXT-PACKAGE.md`'s discover/load/cite/tag/write-back loop end to end
   and writes:
   ```
   outputs/demo-notes/<feature-slug>.md
   ```
   Any other skill you build that needs to consume a context package can follow the
   same contract — see `ult-context-generate/CONSUMING-CONTEXT-PACKAGE.md` for the
   full protocol.

---

## Folder layout reference

| Path | Produced by | Consumed by |
|---|---|---|
| `starter_kit/project_guidelines/COMPILED-GUIDELINES.md` | `/ult-compile-guidelines` | any skill following `CONSUMING-COMPILED-GUIDELINES.md`; `ult-context-generate` Step 5.5 (Constraints layer) |
| `graphify-out/graph.json`, `GRAPH_REPORT.md`, `graph.html` | `/ult-codegraph` | any skill following `CONSUMING-CODE-GRAPH.md`; `ult-context-generate` Step 4/4.5 (What-L3, blast radius) |
| `context-config.yaml` (project root) | you, from `starter_kits/context_engineering/context-config.yaml.template` | `ult-context-generate` (layer paths, budgets) |
| `docs/requirements/**` (path configurable) | your team | `ult-context-generate` Step 5 (What-L2; direct-read, or `md_index.py`-indexed above `large_corpus_threshold`) |
| `org/templates/`, `org/examples/`, `org/guidelines/` (path configurable) | your team | `ult-context-generate` Step 2 (How-L2) |
| `org-conventions/<task_type>.yaml` | `ult-context-generate` Step 2, human-approved | `ult-context-generate` (cached How-L2) |
| `specs/<subfolder>/` (path configurable, e.g. `specs/external/`) | your team — curated `.md` excerpts of external references | `ult-context-generate` Step 7.1 (What-L1 fallback, per-aspect both-layers-gap-triggered, `md_index.py`-indexed) |
| `org/process-standards/` (path configurable) | your team — curated `.md` excerpts of org-wide process standards (CMMI/ISO/IEEE) | `ult-context-generate` Step 2.1 (How-L1 fallback, once-per-package gap-triggered off How-L2, `md_index.py`-indexed) |
| `contexts/<feature>_<task>_<date>.yaml` | `ult-context-generate`, human-approved | any skill following `CONSUMING-CONTEXT-PACKAGE.md` (see `demo-consume-context` for a worked example) — optional, non-blocking, "Status: piloting" |
| `outputs/demo-notes/<feature-slug>.md` | `demo-consume-context` | humans (worked-example output only — see that skill's description) |

Nothing here needs a separate install or scaffolding step — each skill creates its
own output paths the first time it runs, and you're free to create the input folders
(`docs/requirements/`, `org/`, `specs/external/`) yourself ahead of time.

---

## Keeping the code graph fresh

`/ult-codegraph` is **never auto-run**. After meaningful code changes:

- Any skill wired to `CONSUMING-CODE-GRAPH.md`, and `/ult-context-generate` Step 4,
  give a **non-blocking staleness nudge** — they compare `GRAPH_REPORT.md`'s recorded
  commit to `git rev-parse HEAD` and tell you if the graph predates `HEAD`.
- If you see that nudge (or just know you've made significant changes), re-run
  `/ult-codegraph` before the next `/ult-context-generate` run. There's no
  requirement to re-run on every commit — the nudge is advisory, and stale-but-close
  graphs are still useful.

---

## What-L1 and How-L1 (both piloting)

`context-config.yaml` has `what_l1` (external references — industry standards,
competitor docs, architecture whitepapers, 3GPP/ISO/IEEE/etc.) and `how_l1` (org-wide
process standards — CMMI/ISO/IEEE) sections, both `enabled: false` by default. Both
are implemented — indexed by the same `scripts/md_index.py` mechanism — but newly
added and not yet field-validated against a real, large corpus, so the recommended
default is to leave each disabled until you've run it once against your own project's
material and confirmed the results look right.

**Per-aspect gap detection**: `ult-context-generate` Step 1.5 breaks `FEATURE_TERM`
into a small set of **aspects** (e.g., for an enhancement, an existing baseline plus
the new extension/delta being added). What-L3/What-L2/What-L1 coverage is tracked
**per aspect**, not once for the whole feature — so an extension's gap is caught even
when the feature as a whole already has *some* code and/or requirements coverage from
its baseline.

**What-L1 (external references — piloting)**: implemented as an **indexed
fallback**, triggered only for aspects that are a "both-layers-gap candidate" (no
What-L2 or What-L3 coverage for that aspect). When `what_l1.enabled: true`, Step 7.1
builds (once per run, via `scripts/md_index.py index --stale-check`) a deterministic
structural index of `.md` files under `what_l1.path` (e.g. `specs/external/`) —
headings, clause ids, section bounds, resolved cross-references; "the graphify for
markdown", zero-LLM — then queries it per candidate aspect and reads only the matched
sections plus single-hop cross-referenced sections. Every match becomes a
`context_items` entry with `what_l1_fallback: true`, presented in a dedicated
`[L1 FALLBACK ITEMS — REVIEW]` block at Step 9 — the human reviewer must confirm (or
reject) each item's product relevance before approval. See setup step 4 above to
enable it.

**If What-L1 is disabled, or its index has nothing for a candidate aspect**: Step 7.1
offers a `knowledge_cutoff`-tagged item from the model's own training knowledge for
that aspect, one at a time, with the same confirm/reject/edit gating as the L1 items
— surfaced in an `[LLM TRAINING-KNOWLEDGE ITEMS — REVIEW]` block at Step 9. Only an
aspect where *both* What-L1 and this offer come up empty (or are declined) falls
through to the complete-gap prompt (Step 7.2).

**Large What-L2 corpora (reuses the What-L1 mechanism)**: if `what_l2.path` (default
`docs/requirements/`) has more than `what_l2.large_corpus_threshold` (default 10)
`.md` files, Step 5 automatically switches from direct-read to the same
`scripts/md_index.py` indexed mechanism described above, writing to
`what_l2.index_path` (default `specs-out/l2_index.json`) with `what_l2.md_index_profile`
(default `generic`). No extra setup beyond having the files in place — the `generic`
profile already indexes plain prose headings.

Cross-file citation-following (e.g. "see TS 38.214 clause 5.2.2" resolving into a
different indexed file, not just the referencing file) is **implemented** —
`md_index.py`'s `cross_refs` resolution spans the whole indexed corpus, matched on
exact string equality against each file's `doc_id` front-matter field (never fuzzy).
Same-file references are further distinguished as `resolved` /
`unresolved-not-found` / `unresolved-ambiguous` rather than silently guessed. See
[`scripts/README.md`](../../.github/skills/ult-context-generate/scripts/README.md)'s
"Cross-file citation resolution (R9)" section for the mechanism, and
[`examples/cross-file-resolution-demo/`](../../examples/cross-file-resolution-demo/)
for a runnable demo. Validated so far against a small synthetic 2-3 file corpus —
open an issue in this repo if your project's real multi-spec corpus surfaces a gap.

**How-L1 (org-wide process standards — CMMI/ISO/IEEE/etc. — piloting)**: implemented
as a **once-per-package gap-triggered fallback**, distinct from What-L1's per-aspect
trigger. Step 2 checks How-L2 (`org/`) for the task type at hand; if How-L2 has
nothing, Step 2.1 queries the `how_l1.path` index (e.g. `org/process-standards/`)
built the same way as What-L1's. There's no per-task-type aspect loop for How-L1 —
it fires at most once per package. Every match becomes a `context_items` entry with
`how_l1_fallback: true`, presented in a dedicated `[HOW-L1 FALLBACK ITEMS — REVIEW]`
block at Step 9 — the human reviewer must confirm (or reject) each item before
approval, same as What-L1. There is no web-search/training-knowledge fallback chain
for How-L1: if it's disabled, or its index has nothing, Step 2's existing
gap-handling prompt substitutes for one. See setup step 7 above to enable it.

**MCP-backed sources for What-L1 and How-L1**: instead of (or alongside) hand-dropped
`.md` files under `what_l1.path` / `how_l1.path`, both layers accept an optional
`mcp_source` list (e.g. pointing at a Confluence space or another MCP resource).
Before the index build, each entry is mirrored into a `.mcp-mirror/` subdirectory of
the layer's `path`, and the mirror file is only rewritten when the source's content
hash changes since the last run — so staleness detection works the same whether the
underlying `.md` file was hand-edited or fetched via MCP. See
`what_l1.mcp_source`/`what_l1.mcp_mirror_path`/`what_l1.mcp_manifest_path` and their
`how_l1` equivalents in `context-config.yaml.template` for the exact fields, and
[`examples/mcp-what-l1-demo/WALKTHROUGH.md`](../../examples/mcp-what-l1-demo/WALKTHROUGH.md)
for a runnable end-to-end demo (its closing section covers How-L1, since the
mechanism is identical).
