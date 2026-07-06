# Setting up a project repo for context engineering

This guide walks through preparing a project repo so `spw-*` skills (and especially
`/spw-write-user-story`) get good, source-attributed context — from "just the
team's coding conventions" up to "full code graph + requirements + constraints +
blast radius, human-approved before anything is generated."

It covers two paths:

- **Simple**: only compiled guidelines (D11 constraints) feed `spw-*` skills.
- **Complex**: the full context-engineering pipeline (`ult-codegraph` +
  `ult-context-generate` + `spw-write-user-story`) — code graph, requirements, org
  conventions, and constraints, all assembled into a human-approved package.

Both paths are valid end states — pick based on project size and how much you'll
lean on `/spw-write-user-story`. You can start Simple and add the Complex pieces
later; nothing in Simple needs to be undone.

---

## Path A — Simple: compiled guidelines only

**When this is enough:** small/medium codebases, teams that mainly use the core
`/spw-*` loop (`brainstorm` → `write-plan` → `execute-plan`/`tdd` → `request-review`
→ `finish-branch`, see [spw.md](../spw.md)) and want their existing conventions
respected, but don't need a generated, approved context package per feature.

### Setup steps

1. Install the `developer` bundle (includes `compiling-project-guidelines` /
   `/spw-compile-guidelines`).
2. Run `/spw-compile-guidelines`. It auto-discovers conventional sources
   (`.github/instructions/*.instructions.md`, `.github/copilot-instructions.md`,
   `CONTRIBUTING.md`, `docs/guidelines/**`, `docs/architecture/**`), asks you to
   confirm/add/remove, and writes:
   ```
   starter_kit/project_guidelines/COMPILED-GUIDELINES.md
   ```
3. That's it. Any code-facing `/spw-*` skill that follows
   `CONSUMING-COMPILED-GUIDELINES.md` will read this file first and apply the
   most-specific scoped guidance — automatically, non-blocking.
4. **Maintenance**: re-run `/spw-compile-guidelines` whenever a guideline source
   changes ("update my compiled guidelines — I added `docs/payments-conventions.md`").
   The compiled file's `## Noted Tensions` section is append-only and preserves prior
   conflict-resolution decisions across re-runs.

No other folders are required for this path.

---

## Path B — Complex: full context-engineering pipeline

**When you need this:** larger/multi-repo codebases, teams that want
`/spw-write-user-story` to ground stories in real code structure, traced
requirements, and an explicit blast-radius/non-regression analysis — with a human
approval gate before any story is written.

### Setup steps

1. **Compile guidelines first** (Path A, steps 1–2) — `ult-context-generate` Step
   5.5 reads `starter_kit/project_guidelines/COMPILED-GUIDELINES.md` as the
   Constraints layer (D11) if it exists. Optional but recommended.

2. **Install the `utilities` bundle too** (for `ult-codegraph` and
   `ult-context-generate`). `roles/developer.json` already includes both
   `developer` and `utilities`, so most developers get this automatically.

3. **Generate the code graph**: run `/ult-codegraph`. This produces, at the
   project root:
   ```
   graphify-out/graph.json
   graphify-out/GRAPH_REPORT.md
   graphify-out/graph.html
   ```
   This is What-L3. No normalization or copying — `graphify`'s own fixed output
   location is read directly by `ult-context-generate`.

4. **Add a `context-config.yaml`** at the project root. Copy the template:
   ```
   starter_kits/context_engineering/context-config.yaml.template → ./context-config.yaml
   ```
   (If you used `--init-project` with the `developer` bundle, this template is
   already scaffolded to `starter_kit/context_engineering/` — copy it from there.)
   Fill in `project_name`, `description`, and the layer paths
   (`what_l3.path` = source root, `what_l2.path` = requirements docs root,
   `how_l2.path` = org conventions root). For `what_l1`, see step 5 below — leave
   `how_l1` disabled (see
   [What-L1 (piloting) and How-L1 (not yet implemented)](#what-l1-piloting-and-how-l1-not-yet-implemented)
   below).

5. **Populate What-L1 (external references) — optional, piloting (D13)**: if your
   feature touches an aspect with relevant external reference material (industry
   standards, competitor docs, architecture whitepapers — see D2's source-diversity
   clause), drop `.md` excerpts under a directory such as `specs/external/`, then in
   `context-config.yaml` set:
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
   What-L3 coverage for that aspect — see Step 1.5's per-aspect model). Every match
   becomes a `context_items` entry with `what_l1_fallback: true`, presented in a
   dedicated `[L1 FALLBACK ITEMS — REVIEW]` block at Step 9 — the human reviewer must
   confirm (or reject) each item's product relevance before approval. See setup step
   5 above to enable it.
   Skip this step if `what_l1.enabled: false` (the default) — every both-layers-gap
   aspect instead falls through to the disclosed training-knowledge offer (Step 7.1
   step 5a), then to D8's complete-gap prompt only if that's also declined or empty.

6. **Populate What-L2 (requirements)**: put requirements docs under the path you
   set for `what_l2` (default `docs/requirements/`). `ult-context-generate` Step 5
   reads these directly (not via the code graph) for small corpora — at or below
   `what_l2.large_corpus_threshold` (default 10) `.md` files. Larger corpora switch
   automatically to the same `scripts/md_index.py` indexed mechanism as What-L1
   (`what_l2.index_path`, default `specs-out/l2_index.json`, and
   `what_l2.md_index_profile`, default `generic`) — no extra setup beyond having the
   files in place.

7. **Populate How-L2 (org conventions/templates)**: under the path you set for
   `how_l2` (default `org/`):
   ```
   org/templates/    — document/artifact templates
   org/examples/      — worked examples of "good" output for this org
   org/guidelines/    — narrative guidance on house style
   ```
   `ult-context-generate` Step 2 reads these and caches the result to
   `org-conventions/<task_type>.yaml`, gated on `human_approved: true`.

8. **Add the user-story convention** (only needed for `/spw-write-user-story`):
   copy `starter_kits/context_engineering/user-story.yaml.template` →
   `org-conventions/user-story.yaml`, fill in `<role>` placeholders, review, and set
   `human_approved: true`.

9. **Run `/ult-context-generate`** (or just run `/spw-write-user-story` — it
   auto-invokes context generation if no approved package exists for the feature).
   Walk through the 10-step flow; approve both the product context package and the
   org convention package when prompted. Output:
   ```
   contexts/<feature-slug>_<task-type>_<YYYYMMDD>.yaml
   org-conventions/<task-type>.yaml
   ```

10. **Run `/spw-write-user-story`** against the approved package. Output (if you
    choose to save):
    ```
    output_docs/user-stories/<feature-slug>_user-stories_<date>.md
    ```

---

## Folder layout reference

| Path | Produced by | Consumed by |
|---|---|---|
| `starter_kit/project_guidelines/COMPILED-GUIDELINES.md` | `/spw-compile-guidelines` | `CONSUMING-COMPILED-GUIDELINES.md` (most code-facing `spw-*`); `ult-context-generate` Step 5.5 (D11) |
| `graphify-out/graph.json`, `GRAPH_REPORT.md`, `graph.html` | `/ult-codegraph` | `CONSUMING-CODE-GRAPH.md` (5 wired `spw-*` skills); `ult-context-generate` Step 4/4.5 (What-L3, D10 blast radius) |
| `context-config.yaml` (project root) | you, from `starter_kits/context_engineering/context-config.yaml.template` | `ult-context-generate` (layer paths, budgets) |
| `docs/requirements/**` (path configurable) | your team | `ult-context-generate` Step 5 (What-L2; direct-read, or `md_index.py`-indexed above `large_corpus_threshold`, D15) |
| `org/templates/`, `org/examples/`, `org/guidelines/` (path configurable) | your team | `ult-context-generate` Step 2 (How-L2) |
| `org-conventions/<task_type>.yaml` | `ult-context-generate` Step 2, human-approved | `ult-context-generate` (cached How-L2) |
| `org-conventions/user-story.yaml` | you, from `user-story.yaml.template`, human-approved | `spw-write-user-story` |
| `specs/<subfolder>/` (path configurable, e.g. `specs/external/`) | your team — curated `.md` excerpts of external references | `ult-context-generate` Step 7.1 (What-L1 fallback, per-aspect both-layers-gap-triggered, `md_index.py`-indexed, D2/D13/D14/D15) |
| `contexts/<feature>_<task>_<date>.yaml` | `ult-context-generate`, human-approved | `spw-write-user-story` (direct); plus `spw-brainstorm`, `spw-write-plan`, `spw-execute-plan`, `spw-tdd`, `spw-debug`, `spw-receive-review`, `spw-request-review`, `spw-verify` via `CONSUMING-CONTEXT-PACKAGE.md` (optional, non-blocking — "Status: piloting") |
| `output_docs/user-stories/<feature>_user-stories_<date>.md` | `spw-write-user-story` | humans / backlog tooling |

`--init-project` (see `SKILL-BUNDLES-GUIDE.md`) scaffolds
`starter_kit/project_guidelines/`, `starter_kit/context_engineering/`, and
`output_docs/user-stories/` automatically for the `developer` bundle.

---

## Keeping the code graph fresh

`/ult-codegraph` is **never auto-run**. After meaningful code changes:

- The 5 `spw-*` skills wired to `CONSUMING-CODE-GRAPH.md` and
  `/ult-context-generate` Step 4 both give a **non-blocking staleness nudge** — they
  compare `GRAPH_REPORT.md`'s recorded commit to `git rev-parse HEAD` and tell you if
  the graph predates `HEAD`.
- If you see that nudge (or just know you've made significant changes), re-run
  `/ult-codegraph` before the next `/ult-context-generate` run. There's no
  requirement to re-run on every commit — the nudge is advisory, and stale-but-close
  graphs are still useful.

---

## What-L1 (piloting) and How-L1 (not yet implemented)

`context-config.yaml` has `what_l1` (external references — industry standards,
competitor docs, architecture whitepapers, 3GPP/ISO/IEEE/etc.) and `how_l1` (org-wide
process standards — CMMI/ISO/IEEE) sections, both `enabled: false` by default.

**Per-aspect gap detection (D15)**: `ult-context-generate` Step 1.5 breaks
`FEATURE_TERM` into a small set of **aspects** (e.g., for an enhancement, an existing
baseline plus the new extension/delta being added). What-L3/What-L2/What-L1 coverage
is tracked **per aspect**, not once for the whole feature — so an extension's gap is
caught even when the feature as a whole already has *some* code and/or requirements
coverage from its baseline.

**What-L1 (external references — D13/D14 pilot)**: implemented as an **indexed
fallback**, triggered only for aspects that are a "both-layers-gap candidate" (no
What-L2 or What-L3 coverage for that aspect). When `what_l1.enabled: true`, Step 7.1
builds (once per run, via `scripts/md_index.py index --stale-check`) a deterministic
structural index of `.md` files under `what_l1.path` (e.g. `specs/external/`) —
headings, clause ids, section bounds, resolved cross-references; "the graphify for
markdown", zero-LLM — then queries it per candidate aspect and reads only the matched
sections plus single-hop cross-referenced sections (D14). Every match becomes a
`context_items` entry with `what_l1_fallback: true`, presented in a dedicated
`[L1 FALLBACK ITEMS — REVIEW]` block at Step 9 — the human reviewer must confirm (or
reject) each item's product relevance before approval. See setup step 5 above to
enable it.

**If What-L1 is disabled, or its index has nothing for a candidate aspect (D15, Q3)**:
Step 7.1 offers a `knowledge_cutoff`-tagged item from the model's own training
knowledge for that aspect, one at a time, with the same confirm/reject/edit gating as
the L1 items — surfaced in an `[LLM TRAINING-KNOWLEDGE ITEMS — REVIEW]` block at Step
9. Only an aspect where *both* What-L1 and this offer come up empty (or are declined)
falls through to D8's complete-gap prompt (Step 7.2).

**Large What-L2 corpora (D15 — reuses the What-L1 mechanism)**: if `what_l2.path`
(default `docs/requirements/`) has more than `what_l2.large_corpus_threshold` (default
10) `.md` files, Step 5 automatically switches from direct-read to the same
`scripts/md_index.py` indexed mechanism described above, writing to
`what_l2.index_path` (default `specs-out/l2_index.json`) with `what_l2.md_index_profile`
(default `generic`). No extra setup beyond having the files in place — the `generic`
profile already indexes plain prose headings.

Cross-file citation-following (e.g. "see TS 38.214 clause 5.2.2" resolving into a
different indexed file) remains **future work** — today's `cross_refs` resolution is
single-hop and same-file (R9 in `ADVERSARIAL-REVIEW-OSS-AND-MD-MINING.md`). Raise it
with the RadiSys Skills Guild if your project's corpus needs it.

**How-L1 (org-wide process standards — CMMI/ISO/IEEE/etc.)**: still **not yet
implemented** — `how_l1` in `context-config.yaml` remains `enabled: false`. There is
currently no query step in `ult-context-generate`'s flow that reads this layer. If
your project has org-wide process standards you want incorporated today, the
supported path is the **How-L2 org-conventions layer** (`org/guidelines/`) — drop
relevant excerpts or summaries there as narrative guidance. Full How-L1 support is a
larger follow-up — raise it with the RadiSys Skills Guild if it would unblock your
project, since it affects `ult-context-generate`'s config schema and Step 2 flow
design.
