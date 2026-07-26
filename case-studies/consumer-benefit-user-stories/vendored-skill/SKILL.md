<!--
Vendored reference copy, for reproducibility of the consumer-benefit-user-stories
case study. NOT part of this repo's installable skill set — origin: ground-up,
maintained by RadiSys Skills Guild in the sibling Experiment_Threat_Modeling repo,
not context-engineering-oss. See ROADMAP.md "Not on this roadmap" and
case-studies/consumer-benefit-user-stories/CASE-STUDY.md.
-->

---
name: spw-write-user-story
description: Write user stories (functional, NFR, Enabler) for a feature from an approved ult-context-generate context package — actor-driven coverage, constraint routing, Enabler/Requirement-Note shaping.
namespace: spw
version: 0.1.0
origin: ground-up
author: Pranay Mishra
maintainer: RadiSys Skills Guild
adapted_from: ~
upstream_version: ~
released: 2026-06-30
tags: [developer, workflow, user-stories, requirements, actors, backlog, pilot]
bundle: developer
tier: act
---

# spw-write-user-story

> **Status: piloting.** The actor-identification pass (Step 2.5), the constraint
> routing table (Step 3b — Enabler stories vs. Requirement Notes vs. Sequencing
> Notes), and the D12 coverage gates (Step 4 — actor coverage, NFR threshold,
> Requirement Note coverage, Enabler cross-reference) were validated end-to-end on a
> real RBAC guest-role feature, including the full Enabler/Requirement-Note backlog
> shaping for Jira-ready output, before this migration — see
> `CONTEXT-ENGINEERING-DESIGN.md` D12 for the full design rationale. This skill always
> runs against an approved `ult-context-generate` context package (also piloting,
> `utilities` bundle) — install both bundles together. Report findings (works well /
> doesn't / surprises) back to the RadiSys Skills Guild so this can graduate out of
> pilot status or be reworked.

Writes user stories for a given feature. Checks for an approved context package first;
if not found, invokes `ult-context-generate` before generating stories.

---

## Step 1 — Context package check

**Tagged-input check (D19 v2):** if the user's request included an existing
artifact — e.g. "add more stories related to this Jira item: <pasted text>",
or a file path to an already-generated story — run
`CONSUMING-CONTEXT-PACKAGE.md` item 0 against it first. Any `contexts/<id>.yaml`
package(s) it resolves are merged (deduped by `<package-id>`) with the
glob-found product context package below, regardless of the resolved
package's own `task_type`.

Look for these two files:

1. **Product context**: `contexts/<feature-slug>_user-story_*.yaml` where `human_approved: true`
2. **Org convention**: `org-conventions/user-story.yaml` where `human_approved: true`

**If both found and approved:** Load them. Report which files are being used. Go to Step 2.5.

Note each loaded `contexts/<id>.yaml` product context package's
`context_package.content_hash` field (a plain field read — `content_hash` is
already computed and maintained by `ult-context-generate`'s two-pass save).
This is the `<hash8>` used in Step 3a/3c/3d's `[Context: <package-id>@<hash8>
· ...]` tags.

**If either missing or not approved:**
> "No approved context package found for user stories. Running ult-context-generate
> first to assemble product context and org conventions."
>
> Follow the skill at `.github/skills/ult-context-generate/SKILL.md`.
> Return here after both packages are approved.

---

## Step 2 — (After context generation) Confirm scope

Confirm with the user: "Context packages are ready. Shall I write user stories now?"
Wait for confirmation. Go to Step 2.5.

---

## Step 2.5 — Identify actors

Before generating stories, establish **who** this feature serves — human and system
actors. This grounds story coverage in actor needs (Step 3), not just traced
`context_items`, and surfaces personas (testers, support, compliance) that don't
correspond to an RBAC role but still have a stake in the feature.

**Check for existing actors first:** if the product context package already contains
`context_items` with `layer: actors`, present them: "Actors identified previously:
[list]. Still accurate, or has anything changed?" If confirmed unchanged, go to Step 3.

**Otherwise, propose a 3-bucket actor list:**

1. **System roles** — from the product context package's existing role/capability
   `context_items` (e.g. `guest`, `superadmin`, `viewer`), plus any role newly
   introduced by this feature.
2. **Stakeholder personas** — human actors who don't necessarily hold a system role
   but consume its outputs or are affected by it. Suggest from domain knowledge given
   the feature's scope (e.g. compliance/audit reviewer, support/help-desk, QA/tester,
   ops/SRE). For other domains, adapt accordingly (e.g. for telecom/5G NR: field
   engineer, network manager, UE owner).
3. **System actors** — other systems, automated components, or interfaces this
   feature interacts with (enforcement middleware, scheduled jobs, external APIs,
   peer network elements).

**Present the proposed list to the user**, grouped by bucket:
> "Here are the actors I think this feature involves: [list]. Did I cover everyone, or
> are there roles, personas, or system actors I missed or should drop?"

Wait for confirmation/edits.

**Write back the confirmed list** as new `context_items` in the product context
package:
```yaml
- id: ctx_<next-available-NNN>
  layer: actors
  source: llm_domain_knowledge
  type: actor-definition
  actor_category: human-system-role | human-stakeholder | system
  confidence: SUGGESTED
  human_approved: true
  summary: >
    <actor name + one-line description of their stake in this feature>
```

Update `context_package.last_enriched_at` and `domain_additions_count` (same
write-back pattern as Step 4.5). Go to Step 3.

---

## Step 3 — Generate user stories, enablers, and requirement notes

Using **both** context packages as your primary inputs:

**What to say** (from product context package):
- Use `context_items` to ground each story in real implementation state and requirements
- Reference actual code entities (function names, models, endpoints) where relevant
- If a `conflicts_detected` entry exists: the conflict has been acknowledged by the human
  (required before approval) — write stories that reflect the resolved interpretation
- If any `llm_scaffold_count > 0`: those items are LLM-inferred — write stories
  more conservatively, flag them for stakeholder validation

**How to say it** (from org convention package):
- Follow the templates (`functional_story`, `nfr_story`, `enabler_story`,
  `requirement_note`), examples, and quality criteria exactly
- Use the terminology and detail level shown in the examples
- Apply the quality guidelines as acceptance criteria for your own output
- Follow `ordering` for presentation (Step 5) — Enablers first (tier 0), then the
  actor-driven stories generated below

### 3a — Document header

Build the output document's header block:
- **Context package(s)** (D19 v2) — first line of the header:
  `**Context package(s):** <package-id>@<hash8> (human_approved[, N addenda])`
  for each `contexts/<id>.yaml` product context package loaded in Step 1
  (`;`-separated if more than one). This is the document-level tag
  `CONSUMING-CONTEXT-PACKAGE.md` item 0 looks for in downstream artifacts. The
  org convention package (`org-conventions/user-story.yaml`) has no
  `content_hash` and is not part of this tag — note it separately if useful
  (e.g. "Org convention: org-conventions/user-story.yaml (human_approved)").
- **Scope** — as today: capabilities in/out, key behavioral decisions from
  `decisions_log`
- **Affected Areas** — one line summarizing Step 4.5's blast-radius/interaction-points
  `context_items` (`type: blast-radius`, D10): the modules/files this feature touches
  or whose behavior it depends on. If Step 4.5 found "no dependents," say so — that's
  a useful isolation signal for reviewers too.

### 3b — Route constraints and system-level requirements

Before the actor brainstorm, sort `layer: constraints` `context_items` (D11, if
present) and any other context_items describing system-level/cross-cutting
requirements with no natural actor (schema/migration impact, backward-compatibility,
determinism, audit/observability invariants):

| `constraint_class` | scope | → |
|---|---|---|
| `compliance` | broad / multi-story | **Enabler story** (3d) |
| `compliance` | single-story | **Requirement Note** (3e) on that story |
| `convention` | any | not surfaced in the backlog — implementer guidance via `CONSUMING-COMPILED-GUIDELINES.md` |
| `scheduling` | any | **Sequencing Note** — affects Step 5 ordering only |

Items without a `constraint_class` (e.g. plain constitution-style MUST requirements)
follow the `compliance` row: broad → Enabler, single-story → Requirement Note.

### 3c — Actor-driven story brainstorm

For each actor confirmed in Step 2.5, ask: *"what does this actor need, expect, or
value from this feature?"* Cross-reference candidates against `context_items` to
ground each story. This actor-by-actor pass is the primary lens for coverage — do
**not** rely solely on tracing `context_items` or a generic happy-path/edge-case
ordering, both of which can miss actor-specific perspectives (e.g. testability,
auditability) that don't map to an existing context item.

**Each story's body begins with a `[Context: ...]` tag as its first line**
(D19 v2 C6/C8 — this is what survives a Jira push, letting a later reader of
the pushed ticket discover the source context package without access to this
repo):

```
[Context: <package-id>@<hash8> · ctx_NNN[, ctx_MMM...] · aspect <aspect_id>[, <aspect_id>...]]

As a ...
I want ...
So that ...
```

If the story draws on `context_items` from more than one package (multiple
packages loaded in Step 1), `;`-separate each package's group:
`[Context: <pkg-1>@<hash8-1> · ctx_001, ctx_003 · aspect 2; <pkg-2>@<hash8-2> · ctx_010 · aspect 5]`.

For each story include:
- The `[Context: ...]` tag (above) as the first line of the story body
- As a / I want / So that
- Acceptance criteria (follow org convention — typically Gherkin or bullet format)
- `[Actor: <name>]` — the actor this story primarily serves, at the end of the
  story block (unchanged position)

**Story count**: Aim for 3–8 functional/NFR stories (Enablers don't count toward this).
More than 8 suggests the scope should be split.

### 3d — Write Enabler stories

For each Enabler candidate from 3b, follow the `enabler_story` template:
`ENB-NNN`, `**Type:** Enabler`. The body begins with the same `[Context:
<package-id>@<hash8> · ctx_NNN[, ctx_MMM...] · aspect <aspect_id>[, ...]]` tag
as 3c, as its first line, followed by the free-form description + acceptance
criteria. `Referenced by: <story IDs>` — listing every functional story that
depends on it — stays at the end of the block, unchanged position. Tag each
of those stories `[Enabler: ENB-NNN]`.

### 3e — Attach Requirement Notes

For each single-story candidate from 3b, attach a `requirement_note` block under the
relevant story's acceptance criteria. If no existing scenario/criterion verifies the
requirement, add one — don't just record the requirement with nothing backing it.

---

## Step 4 — Self-review before presenting

Before presenting the stories, ask yourself:
- Does each story reference something that actually exists or is required (traceable to
  a context item)?
- Would an engineer who didn't write the context package understand what "done" means?
- Are the acceptance criteria testable?
- Did I follow the org convention template?

**D12 gates — check each explicitly:**
- **Actor coverage**: does every actor confirmed in Step 2.5 have `[Actor: <name>]` on
  at least one story? If not, either add a story for that actor or note "no story for
  <actor> — because <reason>."
- **NFR threshold gate**: does every NFR acceptance criterion include a number + unit?
  Vague terms ("negligible", "minimal", "fast", "reasonable") without a paired
  threshold fail — add a number or move the item to Open Questions.
- **Requirement Note coverage**: does each Requirement Note's `→ Covered by:` point to
  a scenario/criterion that actually verifies it (added if it didn't already exist)?
- **Enabler cross-reference**: does each Enabler story list `Referenced by: <story
  IDs>`, and does each referenced story carry the matching `[Enabler: ENB-NNN]` tag?
- **Context tag gate (D19 v2)**: does every functional/NFR/Enabler story's
  body begin with a `[Context: <package-id>@<hash8> · ...]` line, and does
  every `<package-id>@<hash8>` it uses match a package actually loaded in
  Step 1?

Fix anything that fails these checks, then present the stories.

---

## Step 4.5 — Artifact-level domain enrichment (safety net)

**Note:** Feature-level domain enrichment (UX patterns, security invariants, operational
concerns for this feature type) is handled in `ult-context-generate` Step 7.6 — before
context assembly — and is already present in the context package you loaded.

This step handles only **user-story-craft-specific** gaps: patterns in how user stories
for this type of feature are typically structured that the org convention template does
not already prescribe. Note: "system as actor" and "admin vs. end-user perspective"
patterns are now largely covered by Step 2.5 (actor identification) and Step 3c
(actor-driven brainstorm) — only raise them here if the actor-driven pass genuinely
missed one.

Ask yourself:
> "Looking at the stories generated and the org convention applied, are there any
> *story structural patterns* specific to [feature type] that are missing? Examples:
> explicit 'system as actor' stories for automated enforcement, stories that distinguish
> admin vs. end-user perspectives on the same capability, stories for error recovery flows
> that are distinct from the error itself."

**This should produce 0–2 suggestions at most.** If you find yourself suggesting
feature-scope additions (new capabilities, new behaviors not in the context), stop —
those belong in `ult-context-generate` Step 7.6, not here.

List each candidate as:
```
[craft-N] <story title>
Rationale: <one line — why this story structure is typically needed>
```

**Present to the user one at a time.** For each:
> "Story-craft suggestion [craft-N]: <title>
> Rationale: <one line>
> Include? (y) Yes / (n) No / (e) Edit first"

**For each approved suggestion:**

1. Write the full story following the org convention template,
   tagged `[Source: story-craft]`.

2. Write it back into the context package YAML as a new `context_item`:
   ```yaml
   - id: ctx_<next-available-NNN>
     layer: domain-knowledge
     source: llm_domain_knowledge
     type: domain-best-practice
     confidence: SUGGESTED
     human_approved: true
     summary: >
       <the approved story expressed as a factual context item>
   ```

3. Update `context_package.last_enriched_at` and `domain_additions_count`.

4. Apply the **two-pass `content_hash` save** (`ult-context-generate/SKILL.md`'s
   "content_hash maintenance" subsection, Step 8) — the package content just
   changed, so `content_hash` must be recomputed and patched in before the
   final save. Any `[Context: <package-id>@<hash8> · ...]` tags already
   written in Step 3 for this package now reference a stale `<hash8>` — this
   is expected and non-blocking (`CONSUMING-CONTEXT-PACKAGE.md` item 0's hash
   check handles it as a drift note, not an error).

If zero suggestions are approved: skip the context update. Report:
"No story-craft additions — context package unchanged."

---

## Step 5 — Present and offer refinement

Present the document header (3a: Scope + Affected Areas), then all stories in
`ordering` order — Enablers (tier 0) first, then the actor-driven stories +
approved domain additions grouped into the remaining tiers. Apply any Sequencing
Notes from 3b to adjust relative placement within that order.
Then ask:
> "Would you like to: (a) refine any story, (b) add scope, (c) these look good?"

If (a) or (b): make changes. If (c): done. Offer to write the stories to a file
at `output_docs/user-stories/<feature-slug>_user-stories_<date>.md` if the user wants
to persist them.

**`user_stories_output` (D20 Phase 2, D21 §16.4):** `output_docs/user-stories/`
above is the `user_stories_output` path-slot, resolved via
`ult-repo-layout/SKILL.md`'s "Path resolution algorithm (§15.5 + §16.2)" — not
a hardcoded path. If `/ult-repo-layout init|reconcile` has run for this
project, read `project_layout.slots.user_stories_output.path` (confirmed by
its `.layout-slots.yaml` marker); otherwise fall back to the slot's **resolved
default** — `{workspace_root}/outputs/user-stories/` if
`layout.workspace_root` is set, else `output_docs/user-stories/` (unchanged
from before Phase 2). Resolve it once per run and substitute it for
`output_docs/user-stories/` everywhere it appears below.

**Don't confuse this with the context package summary.** If this skill ran
`ult-context-generate` as a prerequisite, that step already wrote
`contexts/<feature-slug>_user-story_<date>.md` (singular "user-story") — a
*Context Package Summary*, not the user stories themselves. This step's output
is `output_docs/user-stories/<feature-slug>_user-stories_<date>.md` (plural
"user-stories") — a distinct artifact with a near-identical name.

---

## Downstream Usage — Traceability Handoff

When handing the user story file to any downstream skill (`/spw-brainstorm`,
`/spw-write-plan`, `/spw-tdd`, etc.), mention its path explicitly so the
downstream skill can activate **User Story Mode**:

> "User stories saved to `output_docs/user-stories/<feature-slug>_user-stories_<date>.md`.
> Pass this file to `/spw-brainstorm` (or `/spw-write-plan` directly) so that
> brainstorming, planning, and test writing all trace back to the acceptance criteria
> defined here. Example: `/spw-brainstorm output_docs/user-stories/<filename>.md`"

**Why this matters:** mentioning the explicit path lets the downstream skill find
and read this file as part of its own first steps. Without it, the skill has no
reason to go looking for a user-story file and acceptance criteria are not
propagated into the design doc, plan tasks, or test cases.

**What downstream skills do with this file:** see
`.github/skills/spw-write-user-story/CONSUMING-USER-STORY-OUTPUT.md` — the
canonical contract for what gets extracted (Story IDs, Acceptance Criteria,
Actor list, out-of-scope items, `[Context: ...]` tags) and how each consuming
skill (`spw-brainstorm`, `spw-write-plan`, `spw-tdd`, `spw-execute-plan`,
`spw-subagent-dev`) applies it. Defined once there, not restated here, so the
two stay in sync.
