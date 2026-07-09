---
name: context-generate
description: Assemble a context package (code graph, requirements, constraints, blast radius) before a downstream generation task runs - human-approved, source-attributed. Do NOT use for simple lookups.
namespace: ult
version: 0.1.0
origin: ground-up
author: Pranay Mishra
maintainer: Pranay Mishra
adapted_from: ~
upstream_version: ~
released: 2026-06-10
tags: [utility, context-engineering, code-graph, requirements, constraints, blast-radius, pilot]
bundle: utilities
tier: draft
---

# ult-context-generate

> **Status: piloting.** The What-L3/What-L2 dual-layer model, D10 blast-radius
> analysis, D11 constraints layer, and the D12 handoff to a downstream generation
> skill were validated end-to-end on a real ~40 KSLOC FastAPI codebase (an RBAC
> guest-role feature, run through a full context-package generation and approval
> cycle) before this migration. Now rolling out to a small set of pilot users on
> substantially larger codebases (500 KSLOC+, often multi-repo), where the What-L1
> (external-spec) layer remains disabled and token-cost behavior at this scale is
> still an open question. Report findings (works well / doesn't / surprises —
> especially around graphify query budgets and token costs at scale) as an issue
> in this repo so this can graduate out of pilot status or be reworked.
>
> **What-L1 fallback (Step 7.1, D13/D14) is also now piloting** — a small
> `specs/external/` corpus is indexed by `scripts/md_index.py`, a
> Python-stdlib-only CLI that builds a deterministic structural index
> (headings, clause ids, section bounds, resolved cross-references — "the
> graphify for markdown"; see `scripts/README.md`). Step 7.1 builds this index
> once per run (`--stale-check`, the same build-once contract `graphify update`
> uses), then queries it per both-layers-gap aspect with synonym-expanded keyword
> matching to bridge terminology gaps between an aspect's wording and the external
> spec's own terms. Validated end-to-end against a real downloaded 3GPP TS
> 33.401 spec plus a NIST SP 800-63B excerpt — see
> `WHAT-L1-AND-CONTEXT-REUSE-ASSESSMENT.md` and
> `scripts/IMPLEMENTATION-NOTES.md`. The 500 KSLOC+ volunteer pilots above
> should still leave `what_l1.enabled: false` until indexing strategy for large
> multi-file external-spec corpora (Open Question 1) is resolved — this pilot
> covers only the small-corpus case.
>
> **The index also carries heading-tree bounds and resolved single-hop
> cross-references (D14)** — its markdown-AST (ATX + Setext headings) gives
> deterministic section boundaries, and a per-profile cross-reference pass
> (`clause X`, `Annex Y`, `(see Z)`, etc.) resolves in-document references at
> index-build time, so Step 7.1 can follow a matched section's citations to
> directly-cited sections as additional candidates with no further parsing.
> Validated against the same two files: recovered a genuinely relevant section
> (NIST §7.2 "Session Termination", cross-referenced from both
> originally-matched sections) that the keyword/synonym pass alone had missed,
> and confirmed Setext-only Annex headings (TS 33.401's Annexes A-K) are
> correctly bounded. **Zero-LLM extraction** — a stdlib subprocess builds the
> index; the agent only reads the matched `section_bounds` line-ranges. See
> D13/D14.
>
> **How-L1 fallback (Step 2.1, D13/D14) is newly added, not yet field-validated
> against a real corpus.** It reuses the same `scripts/md_index.py` mechanism as
> What-L1's Step 7.1, gap-triggered off the existing How-L2 org-convention check
> (Step 2) instead of per-aspect, and with no web-search/training-knowledge
> fallback chain of its own — see `references/how-l1-fallback-query.md`. Leave
> `how_l1.enabled: false` until you've run it once against your own org's
> process-standard `.md` files and confirmed the results look right.

## Dependencies

- **`ult-codegraph`** (`utilities` bundle) — Steps 4 and 4.5 query
  `graphify-out/graph.json` via `graphify query` / `graphify affected`. If that file
  doesn't exist yet, run `/ult-codegraph` first (see the error conditions table at the
  bottom of this file). Step 4 also runs the non-blocking staleness nudge from
  `ult-codegraph/CONSUMING-CODE-GRAPH.md` step 4 before querying.
- **`compiling-project-guidelines`** (`developer` bundle) — Step 5.5 reads
  `starter_kit/project_guidelines/COMPILED-GUIDELINES.md` as the project's Constraints
  layer (D11), if it exists. Optional — this skill proceeds without it if the file is
  absent.

Assembles a structured, source-attributed, human-approved context package before any
artifact is generated. Produces two outputs: a **product context package** (what the
product does — from code, requirements, and external reference) and an **org convention
package** (how the artifact should be structured — from org templates and examples).

Both packages require explicit human approval before any downstream artifact generator
may use them.

---

## Config reference

Read `context-config.yaml` at the project root before starting. It specifies:
- Layer paths (`what_l3.path`, `what_l2.path`, `what_l1.path`, `how_l2.path`,
  `how_l1.path`)
- Budget limits per layer
- `org_conventions.commit_to_repo` flag
- Product context packages location — the `context_packages` path-slot (D20
  §15.5)

If the file does not exist, use these defaults:
- What-L3 path (`what_l3.path`): `app/`, budget 40
- What-L2 path (`what_l2.path`): `docs/requirements/`, budget 20 — direct read if
  at or below `large_corpus_threshold` (default 10) `.md` files, else indexed
  mode via `md_index.py` (same mechanism as What-L1; see below)
- What-L1: disabled
- How-L2 path (`how_l2.path`): `org/`, cache: `org-conventions/`
- How-L1: disabled
- Product context packages path (`context_packages` path-slot): `contexts/`

**Throughout this skill**, `what_l3.path`, `what_l2.path`, `what_l1.path`,
`how_l2.path`, and `how_l1.path` mean "the value configured for this key in
`context-config.yaml`, or the default above if the file or key is absent."
Where the Flow below shows a literal example path like `app/` or
`docs/requirements/`, substitute this project's configured value.

**`context_packages` (D20 §15.5, D21 §16.2):** every literal `contexts/` in
the Flow below is the `context_packages` path-slot, resolved via
`ult-repo-layout/SKILL.md`'s "Path resolution algorithm (§15.5 + §16.2)" — not
a hardcoded path. In short: if `/ult-repo-layout init|reconcile` has run for
this project, read `project_layout.slots.context_packages.path` (confirmed by
its `.layout-slots.yaml` marker); otherwise fall back to the slot's
**resolved default** — `{workspace_root}/contexts/` if `layout.workspace_root`
is set (D21 Phase 3a), else `cache.product_context_path` (default `contexts/`,
unchanged from Phase 0). Resolve it once per run and substitute it for every
`contexts/` literal below.

**What-L1 (`what_l1`):** when `enabled: true`, `path` points at a directory of
`.md` files (default `specs/external/`) that Step 7.1 indexes with
`scripts/md_index.py` — a Python-stdlib-only CLI that builds a deterministic
structural index (headings, clause ids, section bounds, resolved
cross-references — "the graphify for markdown"; see `scripts/README.md`) at
`index_path` (default `specs-out/index.json`), once per run via
`--stale-check`. `md_index_profile` (default `generic`; also `3gpp`, `rfc`,
`ieee`, or a custom `profiles/<name>.json`) selects the clause-numbering and
cross-reference conventions for this corpus's house style — see
`scripts/README.md` "Profiles". `graphify_budget` is a soft cap on how many
section line-ranges Step 7.1 reads per both-layers-gap aspect. The index also carries each
section's single-hop, same-file cross-references (`clause X`, `Annex Y`, `(see
Z)`, profile-dependent), already resolved (D14) — Step 7.1 follows these with no
further parsing. This is **zero-LLM extraction**: a stdlib subprocess builds the
index; the agent only reads matched line-ranges (D13/D14). Larger per-spec-family
corpora (e.g. a full 3GPP series) and cross-FILE citation-following are future
work (Open Question 1 in `CONTEXT-ENGINEERING-DESIGN.md`; R9), not part of this
pilot.

`allow_web_fallback` (default `false`) is a separate opt-in, independent of
`enabled`/indexing: when `true`, Step 7.1 step 5a may attempt one scoped
`WebSearch`/`WebFetch` for a both-layers-gap aspect *before* falling back to
the Q3 training-knowledge offer — trading the "free and instant, training-data
only" default for "one web lookup, possibly more current." See Step 7.1 step
5a and D18 (`CONTEXT-ENGINEERING-DESIGN.md`).

**What-L2 (`what_l2`):** `path` points at the project's own requirements docs
(default `docs/requirements/`; D21 §16.5 — if `layout.workspace_root` is set
and `path` is left unset, the default widens to `{workspace_root}/`, the whole
workspace subtree). Step 5's corpus-size check (substep 0) counts the `.md`
files in **the What-L2 corpus** — `path`, minus any subtree matching an entry
in `exclude` (default `[]`), plus every `.md` file under each entry in
`include_roots` (default `[]`) — and compares against
`large_corpus_threshold` (default 10):
- **At or below the threshold:** direct-read mode (the original behavior) —
  read every file in the What-L2 corpus, per aspect.
- **Above the threshold:** indexed mode — the same `scripts/md_index.py`
  `index`/`query`/`section_bounds` mechanism Step 7.1 uses for What-L1, against
  `index_path` (default `specs-out/l2_index.json`) and `md_index_profile`
  (default `generic`; also `3gpp`, `rfc`, `ieee`, or a custom
  `profiles/<name>.json` — see `scripts/README.md` "Profiles"). `graphify_budget`
  is reused as the per-aspect cap on `section_bounds` line-ranges read in indexed
  mode (in direct-read mode it instead caps the number of requirement sections
  extracted, as before).

`exclude` (D21 §16.5) and `include_roots` (D21 §16.7) both default to `[]`
(no-op) — a project that doesn't set either key collects exactly the files it
did before these keys existed. When `workspace_root` is set, `exclude` is
typically `[contexts/, inputs/, cache/]` (each indexed separately through its
own pathway, not "dead" — see the template's per-entry comments) so widening
`path` to `{workspace_root}/` doesn't double-index them; `include_roots` lets
an `outputs/`-bucket slot remapped *outside* `{workspace_root}` (e.g. to this
repo's own `output_docs_structure/Requirements/`, `output_docs_structure/Designs/`
via D20's per-slot override) rejoin the What-L2 corpus without adopting
`workspace_root`'s single-root shape.

**How-L1 (`how_l1`):** when `enabled: true`, `path` points at a directory of
`.md` files (default `org/process-standards/`) that Step 2.1 indexes with the
same `scripts/md_index.py` mechanism as What-L1, at `index_path` (default
`specs-out/how_l1_index.json` — distinct from What-L1's and What-L2's index
paths so all three can coexist), once per run via `--stale-check`.
`md_index_profile` (default `generic`) selects the clause-numbering and
cross-reference conventions for this corpus's house style, same as What-L1.
`graphify_budget` (default `20`) is a soft cap on how many section
line-ranges Step 2.1 reads. Unlike What-L1, Step 2.1 runs **once per
package** (gap-triggered off Step 2's How-L2 check, not per aspect) and has
**no `allow_web_fallback` option** — Step 2's existing D8 prompt already
gives the human an equivalent decision point when nothing is found. See
`references/how-l1-fallback-query.md`.

A ready-to-copy template (with these same defaults, annotated) is available at
`starter_kits/context_engineering/context-config.yaml.template` in this library —
copy it to the project root as `context-config.yaml` and adjust the layer paths to
match the project's actual directory layout.

---

## Flow

> Paths below (`app/`, `docs/requirements/`, `specs/external/`, `org/`, etc.)
> are the **defaults** — read them as `what_l3.path`, `what_l2.path`,
> `what_l1.path`, `how_l2.path` per the Config reference above. If
> `context-config.yaml` configures a different path for this project, use
> that instead everywhere the default is shown.
>
> `contexts/` below is the `context_packages` path-slot — resolve it via the
> Config reference's "`context_packages` (D20 §15.5, D21 §16.2)" note above,
> and substitute that resolved path everywhere `contexts/` appears.

### Step 1 — Scope clarification

Ask the user these questions before doing anything else. All are required:

1. **Feature / subsystem**: What is the feature or component this task is about?
2. **Task type**: What artifact are you generating? (user-story / test-case / impact-analysis / threat-model / design-doc / other)
3. **New or existing**: Is this a new feature or an enhancement to something already in the codebase?
4. **Scope boundary**: Is there anything explicitly out of scope for this task?
5. **Known gaps**: Are there any areas where you already know internal documentation is missing?

Collect all answers before proceeding. Store:
- `FEATURE_TERM` — the key search term(s) for querying (e.g. "release event metric value")
- `TASK_TYPE` — normalized slug (e.g. "user-story")
- `FEATURE_SLUG` — kebab-case slug for filenames (e.g. "release-event-metric-link")

---

### Step 1.5 — Aspect decomposition

Break `FEATURE_TERM` into a small set of **aspects** — sub-topics whose
What-L3/What-L2/What-L1 coverage may genuinely differ. This list is the
iteration unit for Steps 4, 5, 7, and 7.1: gap detection runs **per aspect**,
not once for the whole feature (see CONTEXT-ENGINEERING-DESIGN.md D15).

Propose aspects from `FEATURE_TERM` plus the Step 1 answers:

- **Atomic/narrow feature:** one aspect — `{name: FEATURE_TERM, search_terms:
  [FEATURE_TERM]}`. This is the common case and reduces to today's
  single-pass behavior with no added friction.
- **Enhancement/extension** (Step 1 answer 3 = "existing"): separate the
  **existing baseline** from **the new extension/delta being added**. These
  are exactly the aspects most likely to have divergent coverage — the
  baseline is in code and old docs; the extension may only be in an updated
  external spec, or nowhere yet. Example: extending an existing password-reset
  flow to support passkeys → aspects `"Password reset (baseline)"` and
  `"Password reset — passkey extension"`.
- Add a distinct aspect for anything called out in Step 1's "known gaps"
  answer.

Cap at 5 aspects. Present:

> "I'll gather context per aspect:
> 1. `<name>` — `<one-line: what this covers>`
> 2. `<name>` — `<one-line>`
> ...
> Edit, add, remove, or confirm?"

One confirm/edit exchange — not iterative per-aspect Q&A. Assign each aspect a
stable `aspect_id` (1, 2, 3, ... in the order presented above) — this is the
join key every later step uses for per-aspect coverage/records, and it does
not change even if the user edits `name` during this exchange (D17). Store
`ASPECTS: [{aspect_id, name, search_terms: [...]}]`.

---

### Step 2 — How-L2 org convention check

Check whether `org-conventions/<TASK_TYPE>.yaml` exists.

**If it exists:** Load it. Report "Org convention loaded from cache for [task type]." Go to Step 3.

**If it does not exist:** Check whether the `org/` folder has any relevant content for
this task type:
- Look for files in `org/templates/`, `org/examples/`, `org/guidelines/` that match
  the task type name.

**If org/ has relevant content:** Read those files. Assemble a How-L2 org convention
package from them. Save to `org-conventions/<TASK_TYPE>.yaml`. Go to Step 3.

**If org/ has no relevant content (D8 — How dimension complete gap):**

#### Step 2.1 — How-L1 fallback query (gap-triggered, task-type-scoped, D13/D14)

Before surfacing the D8 prompt below, read
`references/how-l1-fallback-query.md` in full and follow it. In short: if
`how_l1.enabled: true`, it queries an indexed org-wide process-standards
corpus (CMMI/ISO/IEEE, etc. — same `md_index.py` mechanism as What-L1) once
for this task type and, if it finds anything, records `how-l1` context items
(`how_l1_fallback: true`, gated for review at Step 9's
`[HOW-L1 FALLBACK ITEMS — REVIEW]` block) and sets `how_l1_covered: true`. If
disabled, or nothing is found, it sets `how_l1_covered: false` and returns
here with no other side effect — proceed to the D8 prompt below unchanged.
There is no separate web-search/training-knowledge fallback for How-L1: the
D8 prompt below already gives the human an equivalent decision point.

Surface to the user:

> "No org conventions found for [TASK_TYPE]. I can suggest a standard format based on
> best practice for [artifact type], or you can provide your own templates/examples.
> (a) Use my suggestion — I'll generate a starting template now
> (b) I'll provide the template or examples myself"

If user chooses (a): Generate a best-practice template/format for the task type.
Include: output structure, key fields, quality criteria, 1-2 example entries.
Label it clearly as LLM-suggested. Present it to the user for review/editing, then
save to `org-conventions/<TASK_TYPE>.yaml` with `source: llm_suggested`.

If user chooses (b): Ask them to paste or describe their template/examples. Incorporate
and save to `org-conventions/<TASK_TYPE>.yaml` with `source: user_provided`.

In both cases, after saving, note whether to commit this file to the repo based on
`context-config.yaml` `org_conventions.commit_to_repo` (default: true — recommend
the user `git add org-conventions/` after this session).

For `user-story`, a ready-to-copy starting template is available at
`starter_kits/context_engineering/user-story.yaml.template` in this library —
offer it as option (a)'s starting point rather than generating one from scratch.

---

### Step 3 — Product context cache check

Check whether `contexts/` contains a file matching `<FEATURE_SLUG>_<TASK_TYPE>_*.yaml`.

**If found:** Read it and show the user a summary. Also check for a sibling
`<FEATURE_SLUG>_<TASK_TYPE>_*.addenda.yaml` (written by consuming skills via
`CONSUMING-CONTEXT-PACKAGE.md`) — if present, summarize its entries (count,
dates, and how many are facts vs. decisions).

Ask:
> "Found a cached context package for this feature ([date])[, plus N addenda
> from later work]. What would you like to do?
> (r) Reuse — I'll approve it for this task as-is
> (f) Fold addenda — merge the addenda into the package, re-check for
>     gaps/conflicts, and re-approve   [only offered if an addenda file exists]
> (g) Regenerate — rebuild from current code and docs"

If user chooses **reuse**: skip to Step 9 (human review gate) using the
cached package.

If user chooses **fold addenda**:
- Merge each addendum's entries into the main package:
  - **Facts** (`context_items`) — for a given `source`/topic, the entry with
    the latest `added_at` wins; it replaces the superseded `context_items`
    entry (or is appended if no matching entry exists).
  - **Decisions** (`decisions_log` / `decisions`) — never auto-merged. Each
    addendum decision becomes a new `conflicts_detected` entry (so Step 6 and
    the Step 9 review gate surface it for human resolution), per D7.
- Re-run **Step 6** (contradiction detection) and **Step 7** (gap detection)
  on the merged result — addenda may close a previously-detected gap or
  introduce a new contradiction.
- Set `human_approved: false` again (the merged content hasn't been reviewed)
  and proceed to **Step 9** for re-approval.
- On approval, remove the `.addenda.yaml` file — its contents are now part of
  the approved package.

If user chooses **regenerate** (D19 v2 C2 — never overwrite an existing
package in place):
1. Continue to Step 4 as normal (rebuild from current code and docs), but
   mint a **new** `<package-id>`: same `<feature-slug>_<task-type>` prefix,
   new `<YYYYMMDD>` (or a `_v2`/`_v3` suffix if regenerating same-day). Set
   `context_package.supersedes: <old-package-id>` on the new package (Step 8
   schema).
2. Leave `contexts/<old-package-id>.yaml` (and its `.md` summary) untouched —
   do not delete or rewrite it.
3. After the new package is saved and approved (Step 9/10), write a
   `kind: supersession` addendum to the **old** package's sibling
   `contexts/<old-package-id>_<date>.addenda.yaml` (create the file if it
   doesn't exist yet):
   ```yaml
   addenda:
     - id: add_<NNN>
       kind: supersession
       added_by: ult-context-generate
       added_at: <ISO timestamp>
       superseded_by: <new-package-id>
       note: >
         Regenerated at user request; <new-package-id> created instead of
         overwriting this package's content.
   ```
   This addendum file is plain markdown-free YAML, not a `contexts/<id>.yaml`
   package — it has no `content_hash` field and the two-pass save does not
   apply to it.

---

### Step 4 — What-L3 query (code graph)

**Staleness nudge (cheap, non-blocking):** check `graphify-out/GRAPH_REPORT.md`'s
"Graph Freshness" section for the commit the graph was built from, and compare it to
`git rev-parse HEAD`. If they differ, report it in one line — "the code graph looks
stale — built from `<old-commit>`, current is `<head>`; consider re-running
`/ult-codegraph` for an up-to-date What-L3 layer" — and continue with the existing
graph anyway; don't block context generation on it. This mirrors
`ult-codegraph/CONSUMING-CODE-GRAPH.md` step 4, applied here so a stale graph doesn't
silently feed a context package without the user knowing.

The code graph is already indexed in `graphify-out/`. Run targeted queries to surface
the implementation reality of the feature, **once per aspect in `ASPECTS`**:

```
graphify query "<aspect.search_terms joined>" --budget 200
```

`--budget 200` is a floor, not a target. If the result's truncation note (e.g.
"... N more nodes cut") covers any of the aspect's core search terms, re-run
with a higher budget (e.g. 500) before drawing conclusions — a truncated
result can hide the very evidence needed for an accurate `l3_coverage` call
(D16).

For each NODE returned with `src=` under `what_l3.path` (What-L3 nodes):
- Note the label, source file, and source location, and which aspect's query
  returned it
- For the 3–5 most directly relevant nodes across all aspects: run `graphify explain
  "<node-label>"` to get full connection details

Focus on: the primary service/model handling this feature, its key functions, any
test coverage, and relationships to adjacent components.

**Layer assignment:** Any node where `src=` starts with `what_l3.path` (default
`app/`) or `tests/` is What-L3. Nodes from other paths are not What-L3 — skip
them for this step.

**Corroboration before crediting coverage (D16 — required before recording
`l3_coverage[aspect.aspect_id] = true`):** read `references/corroboration-gate.md`
now and apply it to every returned What-L3 node before crediting any aspect's
coverage — a `graphify query` hit means the query's BFS *reached* a node, not that
the node's functionality matches the aspect, and generic search terms routinely
collide with unrelated symbols.

**Record coverage:** for each aspect, set `l3_coverage[aspect.aspect_id] = true`
only if the corroboration check above passes for at least one returned
What-L3 node, else `false`. Step 7 uses this per-aspect map for gap
detection — do not collapse results into a single feature-wide yes/no.

**If an aspect's query returns nothing meaningful, or nothing survives
corroboration:** `l3_coverage[aspect.aspect_id] = false`. For a net-new feature this
is expected for most or all aspects — continue.

---

### Step 4.5 — Blast radius analysis (all features)

**Run this step for ALL features — new and existing alike.**

Even a net-new feature reaches into the existing system: it calls shared infrastructure
(`get_db`, `require_capability`, `get_authenticated_user`), registers with the existing
router, instantiates existing models, and plugs into existing auth/audit pipelines. The
blast radius of those shared symbols is equally relevant whether the feature is new or
an enhancement — because any drift in their contract affects everything that already
depends on them.

From the What-L3 findings, identify the existing symbols this feature will **interact
with** — that is, symbols it will call, modify, extend, register with, or plug into.

For each identified interaction point, first resolve its exact node label with
`graphify explain "<symbol>"` (an unresolved or `()`-less label can make
`affected` silently return "No unique node match" or "No affected nodes
found"), then run:
```
graphify affected "<resolved-label>" --depth 2
```

This performs reverse traversal — it answers "what existing code depends on this symbol?"
This tells you the blast radius: everything that must not regress when this feature
touches that shared symbol.

Record each result as a context item:
```yaml
- id: ctx_<NNN>
  layer: what-l3
  source: "<symbol> (blast radius)"
  type: blast-radius
  confidence: EXTRACTED
  summary: >
    This feature interacts with <symbol> (calls / modifies / extends / registers with it).
    Dependents: <list of dependent symbols and their relationship — calls, imports, uses>.
    Non-regression risk: <what existing behaviour must not change for dependents to keep working>.
  what_l1_fallback: false
```

Also populate a top-level `non_regression_risks` list in the context package (Step 8
schema) — one bullet per interaction point, stating what must remain stable for existing
features not to regress.

**If `graphify affected` returns nothing for a resolved symbol (D16):** first
check whether that node itself is low-degree (`graphify explain` shows degree
roughly ≤ 5 — typical of a thin public-API wrapper or a header-declaration-only
function). If so, **this is the expected normal flow, not an error or a dead
end** — pivot to a higher-degree, structurally-related node in the same
file/area (e.g. the class or module the function belongs to, or the core type
it operates on) and re-run `graphify affected` on that node; that's usually
where the real blast radius shows up. Only record "self-contained, no
dependents" as a genuine isolation signal once a higher-degree related node
*also* returns nothing — don't take an empty result from a leaf node at face
value.

**Before moving to Step 5, sanity-check that this step actually ran.** Every
feature interacts with *something* — at minimum shared infrastructure like
auth/session handling, the database layer, or router registration. If
`non_regression_risks` would come out empty, treat that as a signal this step
was skipped or under-scoped, not as evidence the feature has no blast radius —
go back and identify at least the shared-infrastructure touch points before
continuing.

---

### Step 5 — What-L2 query (requirements docs)

**Substep 0 — corpus-size check (once per run):** count the `.md` files under
`what_l2.path` (default `docs/requirements/`). Compare against
`what_l2.large_corpus_threshold` (default 10).

- **At or below the threshold — direct-read mode** (typical for a project's
  own requirements folder):
  1. List all `.md` files in `what_l2.path`.
  2. Read each file.
  3. For each aspect in `ASPECTS`, identify sections relevant to that
     aspect's `search_terms` (by keyword match on headings and content)
     across all files read.
  4. Extract the relevant functional requirements, non-requirements, and
     status for each matched section.

- **Above the threshold — indexed mode** (same mechanism Step 7.1 uses for
  What-L1; requirement docs are graph-isolated and don't surface through
  code-graph BFS either way, but a large corpus shouldn't be fully read every
  run):
  1. Build/refresh the index once:
     ```
     python scripts/md_index.py index <what_l2.path> -o <what_l2.index_path> --profile <what_l2.md_index_profile> --stale-check
     ```
     using `what_l2.index_path` (default `specs-out/l2_index.json`) and
     `what_l2.md_index_profile` (default `generic`). If `what_l2.exclude` is
     non-empty, append `--exclude <entry>` once per entry; if
     `what_l2.include_roots` is non-empty, append `--include-root <entry>` once
     per entry (D21 §16.5/§16.7). Both default to `[]` — when both are empty,
     neither flag is appended and the invocation is unchanged from before these
     keys existed.
  2. For each aspect in `ASPECTS`, query once:
     ```
     python scripts/md_index.py query <what_l2.index_path> "<aspect.search_terms + 2-4 curated synonyms>" --top <what_l2.graphify_budget>
     ```
  3. Read only the matched `section_bounds` (up to `what_l2.graphify_budget`
     line-ranges per aspect), and follow single-hop `cross_refs` exactly as
     in Step 7.1 steps 3–4.
  4. Extract requirements/status from the sections read, same as direct-read
     mode.

For each relevant requirement found, record:
- File name and section heading (becomes the `source` field)
- Requirement text (becomes the `summary` field)
- Status (Implemented / Partial / Not implemented — if stated)
- Which aspect it addresses

**Record coverage:** for each aspect, set `l2_coverage[aspect.aspect_id] = true` if
at least one relevant section was found (either mode), else `false`. Step 7
uses this per-aspect map for gap detection — do not collapse it into a single
feature-wide yes/no.

**If `what_l2.path` does not exist or contains no `.md` files:**
`l2_coverage[aspect.aspect_id] = false` for every aspect. Proceed to Step 5.5.

---

### Step 5.5 — Constraints compilation (third dimension — see D11)

Constraints are coding/design conventions, compliance/regulatory requirements, and
scheduling/dependency constraints that bound the solution space regardless of feature.
Full model: CONTEXT-ENGINEERING-DESIGN.md D11.

1. Check for `starter_kit/project_guidelines/COMPILED-GUIDELINES.md` (produced by
   `compiling-project-guidelines`).

   **If absent:** proceed without a constraints layer. This is **not** a D8 gap —
   constraints infrastructure is optional; not every project has run
   `compiling-project-guidelines`.

   **If present:** read it fully.

2. Load the `## Global` section **wholesale** — these apply regardless of feature
   scope. Do not relevance-filter them the way What-L2/L3 items are filtered.

3. From the touched modules/components identified in Step 4.5 (interaction points),
   match against `### Scope:` path-glob headings. Load every matching scoped section
   **wholesale** — these are constraints, not optional context, so completeness
   matters more than brevity here.

4. Record each loaded entry as a context item:
   ```yaml
   - id: ctx_<NNN>
     layer: constraints
     source: "starter_kit/project_guidelines/COMPILED-GUIDELINES.md (<Global|scope label>)"
     type: constraint
     constraint_class: compliance | convention | scheduling  # as tagged in the source;
                                                               # default convention if untagged
     scope: <Global | path-glob>
     confidence: EXTRACTED
     summary: >
       <the guidance, faithfully paraphrased>
   ```

5. **Type 2 (lateral) conflict detection** — only across the SCOPED sections matched
   in step 3 (not Global, which by definition applies consistently everywhere). If
   this feature touches 2+ scopes, and two scoped sections address the same topic with
   incompatible values — particularly at an interaction point Step 4.5 identified
   between those scopes — record:
   ```yaml
   - id: conflict_<NNN>
     conflict_type: constraint-lateral
     topic: <topic>
     scope_a: <path-glob A>
     claim_a: "<guidance from scope A>"
     scope_b: <path-glob B>
     claim_b: "<guidance from scope B>"
     interaction_point: "<symbol/integration point from Step 4.5 where this collides>"
     resolution_required: true
     note: "<why this matters for the artifact>"
   ```
   This feeds Step 6 (D7) — lateral conflicts block approval the same as L2-vs-L3
   contradictions.

6. **Vertical (Type 1) conflicts are not detected here.** A narrower-scope `compliance`
   entry that would loosen a broader-scope `compliance` entry is
   `compiling-project-guidelines`'s responsibility (its own Step 4/5, recorded in its
   `## Noted Tensions`). If COMPILED-GUIDELINES.md's `## Noted Tensions` contains an
   *unresolved* vertical conflict touching one of this feature's scopes, carry it
   forward as `conflict_type: constraint-vertical` into Step 6.

7. **Staleness nudge:** if any source listed in COMPILED-GUIDELINES.md's header has a
   newer modification time than the compiled file itself, note it in one line per
   `CONSUMING-COMPILED-GUIDELINES.md` step 4 — non-blocking.

---

### Step 6 — Contradiction detection (D7)

Two conflict types feed this step. All conflicts — regardless of type — are recorded
in `conflicts_detected` and block approval at Step 9 until acknowledged.

**1. L2-vs-L3 contradiction** (`conflict_type: l2-l3-contradiction`)

Compare What-L2 (requirements) and What-L3 (code) results on the same feature entity.

For each requirement that also has a corresponding code implementation:
- Does the requirement describe behavior X, but the code does something mutually
  exclusive (not just different terminology, but a genuinely different behavior)?
- If yes: record as a conflict with the L2 claim, L3 finding, and two interpretation
  options ("code is behind requirement" vs "requirement was not updated after change")

**Do not flag terminology differences.** Only flag genuine contradictions where both
cannot simultaneously be true.

**2. Constraint conflicts** (`conflict_type: constraint-lateral` or
`constraint-vertical`)

Carried forward from Step 5.5 — lateral conflicts across scopes this feature touches,
and any unresolved vertical conflicts from COMPILED-GUIDELINES.md's `## Noted Tensions`
that touch this feature's scopes.

---

### Step 7 — Gap detection

For each aspect in `ASPECTS`, classify using `l2_coverage[aspect.aspect_id]` and
`l3_coverage[aspect.aspect_id]` from Steps 4 and 5:

| L2 | L3 | Classification |
|----|----|----------------|
| ✓  | ✓  | Covered — no gap |
| ✓  | ✗  | What-L3 gap for this aspect (likely net-new code for this aspect specifically) |
| ✗  | ✓  | What-L2 gap for this aspect (undocumented existing behavior) |
| ✗  | ✗  | **Both-layers-gap candidate** — record as `(aspect)` (candidate for D8 — complete What dimension gap) and continue to Step 7.1. What-L1 (external reference) may still close the gap before falling back to D8 (Step 7.2). |

**Do not roll this up to a single feature-wide yes/no.** An aspect can be a
both-layers-gap candidate even when other aspects of the same feature — or the
feature term as a whole — return results from L2 and/or L3. This is the
common case for an enhancement: the existing-baseline aspect is covered, the
new-extension aspect is the gap, and only the extension aspect should reach
Step 7.1.

**What-L2 low-confidence warning (feature-wide, run once after the per-aspect
table above):** If What-L2 returned fewer than 3 relevant requirement
sections across all aspects and all docs files:
> "What-L2 has minimal documentation for this feature (found [N] relevant sections).
> The context package will rely mainly on code analysis. Key product decisions and
> intent may be missing. Proceed, or would you like to add requirements context now?"
> Wait for confirmation.

---

### Step 7.1 — What-L1 fallback query (gap-triggered, D2/D13/D14)

Read `references/what-l1-fallback-query.md` now and follow it for every
both-layers-gap candidate aspect Step 7 hands you — it covers the index
build/refresh, the per-aspect query, reading matched sections, single-hop
citation-following (D14), the disclosed web-fallback (D18) and training-knowledge
(Q3) offers, and recording the resulting context items. Return here (Step 7.2) once
every candidate aspect has been processed.

---

### Step 7.2 — Complete gap handling (D8)

For each aspect that reaches this step — i.e. it was a both-layers-gap
candidate in Step 7, **and** Step 7.1's What-L1 query (if enabled) returned
nothing, **and** the Q3 training-knowledge offer (step 5a) was declined or
also had nothing to offer — surface to the user:

> "I found no implementation, requirements documentation, or external reference
> for [FEATURE_TERM][ (aspect: <aspect.name>), if `len(ASPECTS) > 1`]. This may
> be a net-new feature[/aspect], or the scope query may be too narrow.
> Options:
> (a) Use my best-judgment context scaffold (I'll infer from domain knowledge)
> (b) I'll describe the feature context myself
> (c) Let me re-scope — the feature term might be wrong"

If user chooses (a): Generate a context scaffold labeled `source: llm_generated`,
`confidence: SUGGESTED`, tagged with this aspect's `aspect_id` and `name`.
Continue to Step 8.

---

### Step 7.5 — Open question resolution (one at a time, mandatory)

Before assembling the package, resolve every open question identified during Steps 4–7.

**Do NOT list all questions at once.** Ask them one at a time:

1. State the question with a one-line explanation of why it matters for the package.
2. If you have a default, show it explicitly: "My default: X — confirm or override."
3. Wait for the user's answer before moving to the next question.
4. Record the resolved value as a **decided** field in the package (not as an assumption).

Repeat until every open question is answered. Only then proceed to Step 8.

**If the user says "use your assumptions" or equivalent shorthand for all remaining
questions:** treat each pending default as decided, record them explicitly as
`decided: <value> (user accepted default)` in the package, and proceed to Step 8.
Do NOT silently absorb this — echo back each decision you are locking in so the user
can see exactly what was accepted, before you move on.

---

### Step 7.6 — Feature-level domain enrichment (one at a time)

After all open questions are resolved, perform a domain knowledge pass at the **feature
level** — before assembly, while all the gathered evidence is in working memory.

Ask yourself as a domain expert:
> "Given what was found in What-L3, What-L2, the blast radius, and the resolved
> decisions — what context items are typically expected for a feature of this type
> (e.g. RBAC role addition, time-limited access, authentication change) that are NOT
> yet represented in the gathered context?"

Consider: UX patterns typical for this feature type, security invariants, operational
concerns (monitoring, logging), compliance implications, inter-feature interaction risks
not surfaced by blast radius.

List each candidate as:
```
[domain-N] <short title>
Rationale: <one line — why typically needed, what gap it fills>
```

**Present to the user one at a time.** For each:
> "Domain suggestion [domain-N]: <title>
> Rationale: <one line>
> Add to context? (y) Yes / (n) No / (e) Edit first"

Do NOT add any suggestion without explicit user approval.
Do NOT ask for all approvals at once — one at a time.

For each approved suggestion, add a context item:
```yaml
- id: ctx_<NNN>
  layer: domain-knowledge
  source: llm_domain_knowledge
  type: domain-best-practice
  confidence: SUGGESTED
  human_approved: true
  summary: >
    <the approved suggestion expressed as a factual context item>
```

These items enter the package before assembly — all downstream consumer skills
(user story writer, test case writer, design doc writer) inherit them automatically
with no feedback loop or write-back needed.

If zero suggestions are approved: proceed to Step 8 without adding items.

---

### Step 8 — Assemble product context package

Read `references/context-package-schema.md` now and follow it — it has the full
YAML schema for `contexts/<FEATURE_SLUG>_<TASK_TYPE>_<YYYYMMDD>.yaml`, the
companion-markdown-summary instruction, and the two-pass `content_hash` save
procedure (D19 v2 C1/C2) that applies any time this file is written or rewritten.
Aim for 5-12 `context_items` — more than 15 makes the package unwieldy to review.

---

### Step 9 — Human review gate (mandatory)

**STOP. Do not proceed until the user explicitly approves both packages.**

Present to the user:

```
CONTEXT PACKAGE READY FOR REVIEW
=================================

PRODUCT CONTEXT  (contexts/<filename>.yaml)
  Feature:        <feature>
  Task type:      <task_type>
  Items:          <N> context items
  Sources:        <N> What-L3 (code), <N> What-L2 (requirements), <N> What-L1 (external reference)
  Conflicts:      <N>  [MUST RESOLVE BEFORE APPROVAL if > 0]
  L1 fallbacks:   <N>  [CONFIRM RELEVANCE BEFORE APPROVAL if > 0 — see below]
  LLM knowledge:  <N>  [CONFIRM RELEVANCE BEFORE APPROVAL if > 0 — see below]
  Web fallbacks:  <N>  [CONFIRM RELEVANCE BEFORE APPROVAL if > 0 — see below]
  LLM scaffolds:  <N>
  How-L1 fallback: <N>  [CONFIRM RELEVANCE BEFORE APPROVAL if > 0 — see below]

ASPECT COVERAGE
  #  | Aspect                        | L3  | L2  | L1  | Notes
  ---|-------------------------------|-----|-----|-----|---------------------------------
  <aspect_id> | <aspect.name>        | ✓/✗ | ✓/✗ | ✓/✗ | <e.g. "LLM knowledge used (ctx_004)",
              |                       |     |     |     |  "web fallback used (ctx_005)",
              |                       |     |     |     |  "gap — LLM scaffold (ctx_007)", or
              |                       |     |     |     |  blank if fully covered>

<summary bullets>

ORG CONVENTION  (org-conventions/<task_type>.yaml)
  Task type:  <task_type>
  Source:     <org-provided | llm_suggested | user_provided>
  Items:      <N> conventions

<org convention summary>

[CONFLICTS TO RESOLVE — if any]
<for each conflict: what L2 says, what L3 shows, options>

[L1 FALLBACK ITEMS — REVIEW — if any]
<for each what-l1 context item with confidence: EXTRACTED: its source citation and summary>

[LLM TRAINING-KNOWLEDGE ITEMS — REVIEW — if any]
<for each what-l1 context item with confidence: SUGGESTED and a knowledge_cutoff
 field (Step 7.1 step 5a / Q3 items): its aspect_id/aspect, knowledge_cutoff, and summary>

[WEB FALLBACK ITEMS — REVIEW — if any]
<for each what-l1 context item with confidence: SUGGESTED and a source starting
 with "web_search(" (Step 7.1 step 5a / D18 items): its aspect_id/aspect,
 retrieved_at timestamp, source, and summary>

[HOW-L1 FALLBACK ITEMS — REVIEW — if any]
<for each how-l1 context item (how_l1_fallback: true, Step 2.1): its source
 citation and summary — these have no aspect_id/aspect, they are task-type-scoped>
```

**`L1 fallbacks` line wording:**
- `what_l1.enabled: false` (or absent): `0  (What-L1 layer disabled)`
- `what_l1.enabled: true` but Step 7.1 found nothing: `0  (no L1 fallbacks)`
- `what_l1.enabled: true` and Step 7.1 found items: `<N>  [CONFIRM RELEVANCE BEFORE
  APPROVAL — see below]`, with the `[L1 FALLBACK ITEMS — REVIEW]` block listing
  each item's `source` and `summary`. Items found via citation-following (D14)
  carry that provenance in their `summary` ("Found via citation-following from
  ...") — call it out so the reviewer can judge relevance independently of the
  section that led to it.

**`LLM knowledge` line wording:**
- `llm_knowledge_count == 0`: `0  (no training-knowledge items)`
- `llm_knowledge_count > 0`: `<N>  [CONFIRM RELEVANCE BEFORE APPROVAL — see below]`,
  with the `[LLM TRAINING-KNOWLEDGE ITEMS — REVIEW]` block listing each item's
  `aspect_id`/`aspect`, `knowledge_cutoff`, and `summary` (the summary already
  carries the unverified-against-current-spec caveat from Step 7.1 step 5a —
  surface it as-is, don't soften or drop it).

**`Web fallbacks` line wording (D18):**
- `what_l1.allow_web_fallback: false` (or absent, the default):
  `0  (web fallback disabled)`
- `allow_web_fallback: true` but `web_fallback_count == 0`:
  `0  (no web fallback items)`
- `web_fallback_count > 0`: `<N>  [CONFIRM RELEVANCE BEFORE APPROVAL — see below]`,
  with the `[WEB FALLBACK ITEMS — REVIEW]` block listing each item's
  `aspect_id`/`aspect`, `retrieved_at` timestamp, `source`, and `summary` (the
  summary already carries the unverified-against-project caveat from Step 7.1
  step 5a — surface it as-is, don't soften or drop it).

**`How-L1 fallback` line wording:**
- `how_l1.enabled: false` (or absent): `0  (How-L1 layer disabled)`
- `how_l1.enabled: true` but Step 2.1 found nothing: `0  (no How-L1 fallbacks)`
- `how_l1.enabled: true` and Step 2.1 found items: `<N>  [CONFIRM RELEVANCE
  BEFORE APPROVAL — see below]`, with the `[HOW-L1 FALLBACK ITEMS — REVIEW]`
  block listing each item's `source` and `summary`. Items found via
  citation-following (D14) carry that provenance in their `summary`, same as
  What-L1's.

Then ask:
> "Please review the context package above.
> — If there are conflicts: tell me which interpretation is correct for each.
> — If there are L1 fallback items: confirm each is actually relevant to this
>   product before I rely on it (these come from external specs, not this
>   codebase or its requirements docs).
> — If there are LLM training-knowledge items: confirm each is still accurate and
>   relevant — these come from my training data (cutoff noted per item), not a
>   verified source, and may be outdated.
> — If there are web fallback items: confirm each is still accurate and
>   relevant — these come from a live web search (retrieval timestamp noted
>   per item), not this project's own sources, and may not apply to this
>   product.
> — If there are How-L1 fallback items: confirm each still applies to this
>   organization's actual process before I rely on it (these come from an
>   external process-standard corpus, not this project's own How-L2
>   conventions).
> — If anything is missing or wrong: tell me what to fix.
> — When you are satisfied: say APPROVE to proceed."

**If there are conflicts:** Do NOT accept approval until the user has addressed each
conflict (even if just acknowledging "this is known, proceed with option X").

**If there are L1 fallback items:** Do NOT accept approval until the user has
confirmed (or rejected) each item's product-relevance. A rejected item must be
removed from `context_items` and `what_l1_fallback_count` decremented before saving.
If that was the aspect's only What-L1 evidence, also reset — for the `aspects[]` and
`gaps_detected[]` entries with the **same `aspect_id`** as the rejected item —
`aspects[].what_l1_covered` and `gaps_detected[].what_l1_fallback_used` to `false`
— the aspect reverts to a gap. If `what_l1.enabled: true` and step 5a (Q3) has not
yet run for this aspect, offer it now; otherwise apply Step 7.2.

**If there are LLM training-knowledge items:** Do NOT accept approval until the user
has confirmed (or rejected) each item. A rejected item must be removed from
`context_items`, `llm_knowledge_count` decremented, and — for the `aspects[]` and
`gaps_detected[]` entries with the **same `aspect_id`** as the rejected item —
`aspects[].llm_knowledge_used` and `gaps_detected[].llm_knowledge_used` reset to
`false` (the aspect reverts to a gap — apply Step 7.2 for it) before saving.

**If there are web fallback items (D18):** Do NOT accept approval until the user
has confirmed (or rejected) each item. A rejected item must be removed from
`context_items`, `web_fallback_count` decremented, and — for the `aspects[]` and
`gaps_detected[]` entries with the **same `aspect_id`** as the rejected item —
`aspects[].web_fallback_used` and `gaps_detected[].web_fallback_used` reset to
`false` (the aspect reverts to a gap). Because the web fallback offer (if
accepted) skipped the Q3 training-knowledge offer for this aspect, offer Q3
now per step 5a; if Q3 is also declined or empty, apply Step 7.2.

**If there are How-L1 fallback items:** Do NOT accept approval until the user
has confirmed (or rejected) each item's applicability. A rejected item must
be removed from `context_items` and `how_l1_fallback_count` decremented
before saving. If that was the only How-L1 evidence for this package, also
reset `how_l1_covered` to `false` and re-surface Step 2's D8 prompt — "(a)
use my best-practice suggestion / (b) I'll provide the template myself" —
since it has not yet been offered for this task type.

**Do not treat any shorthand ("go ahead", "looks good", "use assumptions") as APPROVE.**
The user must say the word APPROVE (or a clear explicit equivalent like "approved" or
"I approve"). If they say anything ambiguous, ask: "Do you approve both packages?"

Once user says APPROVE (and all conflicts addressed):
1. Set `human_approved: true` in the YAML, then apply the **two-pass
   `content_hash` save** (Step 8) before writing `contexts/<id>.yaml` to disk.
2. Set `human_approved: true` in the org convention YAML (if it was newly generated)
3. Report: "Both packages approved. Ready for artifact generation."

---

### Step 9.5 — Optional: persist corrections to project guidelines

Everything the human decided at Step 9 is saved into this one feature's
`contexts/<id>.yaml` and stops there by default — the next `ult-context-generate`
run for a different feature won't see it. This step closes that loop for the
narrow subset of Step 9 decisions that are actually general, reusable project
guidance rather than judgments specific to this feature.

**Only run this step if this approved package had at least one of:**

1. A resolved `constraint-lateral` conflict (Step 5.5/Step 6, D7) — two
   `COMPILED-GUIDELINES.md` scoped sections disagreeing at an interaction point
   this feature touches, now resolved by the human's answer at Step 9.
2. A rejected fallback item (What-L1 / LLM-knowledge / web / How-L1) whose
   stated rejection reason reads as **general, reusable project guidance**
   rather than "not relevant to this feature."

If neither applies, skip this step silently — most runs end at Step 9.

**Judging whether a fallback-item rejection is general guidance:** ask whether
the human's reason would still hold for a *different* feature touching the same
area, or whether it's specific to this one. For example:
- *"We don't do gRPC health checks that way here — we use the shared
  `/healthz` middleware in `pkg/health`"* → general: reword as guidance and
  offer to persist it.
- *"This particular endpoint doesn't need rate limiting because it's
  admin-only and already behind VPN"* → feature-specific: do not offer to
  persist it.

**For each qualifying item, ask one explicit question (never write silently):**
> "This run resolved `<topic>` — you said `<resolution and reason>`. Should I
> note this in `COMPILED-GUIDELINES.md` for future runs and
> `/ult-compile-guidelines` to pick up? (y/n)"

- **On yes:** append one line to the `## Recent Observations (pending compile)`
  section of `COMPILED-GUIDELINES.md` (creating the section if it's absent),
  following the write-back contract in
  `compiling-project-guidelines/CONSUMING-COMPILED-GUIDELINES.md` step 5
  exactly — same file, same section, same dated/attributed line shape, just
  attributed `[ult-context-generate]` and citing this package's `id` (from
  Step 8's `contexts/<id>.yaml`) for traceability back to the full resolution.
  Resolve `COMPILED-GUIDELINES.md`'s location the same way that write-back
  contract does — do not re-derive the `compiled_guidelines` path-slot logic
  here.
- **On no:** do nothing and move on. No retry, no nagging.

This is purely persisting a decision the human already made at Step 9 — it
never infers a guideline from agent behavior on its own.

---

### Step 10 — Save, signal, and STOP

Both files are now saved and approved. Report the file paths:
- `contexts/<FEATURE_SLUG>_<TASK_TYPE>_<YYYYMMDD>.yaml`
- `org-conventions/<TASK_TYPE>.yaml`

If `org_conventions.commit_to_repo: true` (default): remind the user to
`git add org-conventions/<TASK_TYPE>.yaml` if this was newly created.

**STOP HERE. This skill's job is context assembly only — it does not generate
any artifact (user story, test case, design doc, etc.).**

- If this skill was invoked by a chaining skill (e.g. a user-story or test-case
  generation skill called `ult-context-generate` as a prerequisite): return control
  to the calling skill now. The calling skill will proceed with artifact generation
  using the approved packages.
- If this skill was invoked directly (naked, no chaining skill): halt and tell the user
  which skill to invoke next to generate the artifact, e.g.:
  > "Context package is ready and approved. To generate [TASK_TYPE], invoke
  > the appropriate generation skill for your task type."

Do not generate any artifact content. Do not write any user stories, test cases,
design documents, or other output beyond the two YAML/markdown context files.

---

## Token cost tracking

A model narrating its own per-step token estimates is not telemetry — do not
report invented "~N–MK tokens" breakdowns. Instead:

- **Capture real usage from the harness.** Most agent harnesses (Claude Code,
  Copilot, etc.) surface actual token usage for the session/run. At the end of
  each run, record that real number in this project's `learnings.md` (or
  equivalent running-notes file), dated, alongside: the feature scope, the
  number of aspects (Step 1.5) and how many were both-layers-gap candidates,
  whether `what_l1.enabled` and `how_l1.enabled` were true, and roughly how
  many `graphify query`/`explain` calls Step 4 made. This is the data the
  pilot needs — an LLM's self-estimate is not.
- **What-L3 (Step 4) cost** is dominated by `graphify query`/`graphify explain`
  call volume. `ult-codegraph` provides `graphify benchmark` (run once per
  pilot codebase — see its SKILL.md "Measuring impact") to measure token
  reduction vs. a naive full-corpus-read baseline. Cite that measured number,
  not a per-query guess, when reporting What-L3 cost.
- **Step 7.1 (What-L1) cost** is the one-time index build (amortized via
  `--stale-check`) plus exactly the `section_bounds` line-ranges `Read` per
  both-layers-gap aspect — see "Zero-LLM extraction" in Step 7.1. If you want a
  concrete number, record the total line-ranges read per aspect in `learnings.md`; do not
  estimate it in tokens.
- **Step 2.1 (How-L1) cost** is the same shape as Step 7.1's — a one-time
  index build (amortized via `--stale-check`) plus exactly the
  `section_bounds` line-ranges `Read`, but once per package rather than per
  aspect.

**Open Question 4** (`CONTEXT-ENGINEERING-DESIGN.md` §10 — token cost as the
primary Phase 1 measurement gate) **is not yet measurable** from this skill's
own output. It requires real harness-level usage data collected across pilot
runs (the `learnings.md` entries above), not self-reported estimates. Treat
Open Question 4 as open until that data exists — when reporting findings back
as an issue in this repo, include `learnings.md` excerpts (real numbers),
especially from 500 KSLOC+ codebases where What-L3 query volume is the main
cost driver.

---

## Error conditions

| Condition | Action |
|-----------|--------|
| `graphify-out/graph.json` not found | "Code graph not found. Run `/ult-codegraph` (or `graphify update .`) first, then retry." |
| `graphify-out/graph.json` exists but stale (Step 4 staleness nudge) | Non-blocking: report the one-line staleness nudge and continue using the existing graph |
| `what_l2.path` (default `docs/requirements/`) does not exist | Treat What-L2 as empty (D8 path) |
| `how_l2.path` (default `org/`) does not exist | Treat How-L2 as empty — Step 2.1 runs (How-L1 query, if enabled), then Step 2's D8 prompt |
| Both What-L2 and What-L3 empty for an aspect | Both-layers-gap candidate for that aspect (Step 7) — Step 7.1 runs first: What-L1 query (if enabled), then the optional web fallback (step 5a, D18, if `allow_web_fallback: true`), then the Q3 training-knowledge offer (step 5a) if the above are disabled or return nothing. D8 complete gap (Step 7.2) only if all of these also fail to close it for that aspect |
| `what_l1.enabled: true` but `path` missing/empty, or `md_index.py index` fails (step 1) | Treat as "What-L1 returns nothing" for every candidate aspect — go to step 5a (web fallback if enabled, then Q3 training-knowledge offer) for each; fall through to Step 7.2 (D8) only if that is also declined/empty — not a hard error |
| `what_l1.allow_web_fallback: true` but `WebSearch`/`WebFetch` is unavailable, errors, or returns nothing usable (step 5a, D18) | Treat as "web fallback returns nothing" — fall through to the Q3 training-knowledge offer unchanged, not a hard error |
| `how_l1.enabled: true` but `path` missing/empty, or `md_index.py index` fails, or the query returns nothing (Step 2.1) | Treat as "How-L1 returns nothing" — set `how_l1_covered: false` and go directly to Step 2's existing D8 prompt — not a hard error |
| A query result's `cross_refs` entry has `resolved: false` (D14) | Drop that reference — do not guess or read an unrelated section |
| User does not approve after 3 rounds | "Pausing context generation. Resume by running ult-context-generate again — the partial draft is NOT saved." |
