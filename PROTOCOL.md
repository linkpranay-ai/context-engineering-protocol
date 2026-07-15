# The Context Engineering Protocol

> A written spec for how a coding agent should assemble, validate, and get approval for the
> context it works from — not just another retrieval trick.

This document explains the protocol in depth: the layer model, the cross-cutting Constraints
dimension, the gap → conflict → staleness state machine, the human-approval gate, and the newly
piloted How-L1 layer, not yet field-validated against a real corpus. For a shorter overview and a
skill-by-skill index, see [`README.md`](README.md). For term definitions, see
[`GLOSSARY.md`](GLOSSARY.md). For what's planned next, see [`ROADMAP.md`](ROADMAP.md).

## Interpretation of MUST/SHOULD/MAY

The keywords **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY**, when they appear in
capitals in this document, are to be interpreted as described in
[RFC 2119](https://www.ietf.org/rfc/rfc2119.txt): **MUST**/**MUST NOT** denote an absolute
requirement or prohibition; **SHOULD**/**SHOULD NOT** denote a strong recommendation that may be
deviated from only with a documented reason; **MAY** denotes something genuinely optional. Every
keyword introduced in this document describes behavior this protocol already implements — none
introduces a new requirement.

## 1. The problem this protocol addresses

Ask a coding agent to implement a feature and it will read *something* before writing code —
usually whatever files are nearest to the prompt, chosen by the agent's own judgment in the
moment. Three things go wrong with that by default:

1. **Nobody checks whether the sources agree.** A requirements doc can say one thing while the
   code already does another, or two "org conventions" documents can quietly contradict each
   other, and the agent has no reason to notice either.
2. **Nobody checks whether the sources are current.** A code graph built last week, or a compiled
   guidelines cache built before yesterday's refactor, looks exactly as authoritative as a fresh
   one — there's no signal that it might be stale.
3. **Nobody has to approve what the agent is about to treat as ground truth.** The agent decides
   what's relevant and proceeds, with no human checkpoint between "gathered context" and
   "generated code."

This protocol's centerpiece skill, `ult-context-generate`, exists to close all three gaps before
generation starts, not to make retrieval faster.

## 2. The layer model

Every claim in a context package traces back to one of five layers, plus one cross-cutting
dimension (**Constraints**, §2.1) that isn't tied to a specific aspect. Layer names follow a
`<What|How>-L<1|2|3>` convention: **What** layers describe product requirements/specs; **How**
layers describe process/convention. The number is a maturity/scope tier, not a ranking of
importance.

| Layer | What it is | Status | Where it lives |
|---|---|---|---|
| **What-L3** | The code itself — a generated knowledge graph of cross-file relationships | Implemented | `ult-codegraph` (`graphify`) |
| **What-L2** | This product's own requirements/spec documents | Implemented | `docs/requirements/` (path configurable) |
| **What-L1** | External references — industry standards, competitor docs, architecture whitepapers (e.g. 3GPP, ISO, IEEE) | **Piloting** | `specs/external/` (path configurable), indexed by `md_index.py` — hand-dropped `.md` files, or MCP-mirrored (optional, opt-in — ROADMAP item 9) |
| **How-L2** | Your org's compiled, scope-aware conventions (style guides, templates, examples) | Implemented | `compiling-project-guidelines`, cached as `COMPILED-GUIDELINES.md` |
| **How-L1** | Org-wide **process** standards (CMMI, ISO 9001, IEEE process standards, etc.) | **Piloting** — see §5 | `org/process-standards/` (path configurable), indexed by `md_index.py` — hand-dropped `.md` files, or MCP-mirrored (optional, opt-in — ROADMAP item 11) |

**Why external specs (What-L1) rank below your own docs (What-L2/L3):** an external standard
describes what the *industry* does, not what *this product* does or requires. When a What-L1
item gets pulled into a context package, it's tagged `what_l1_fallback: true` and shown to the
human reviewer in a dedicated block — informative, never treated as authoritative for this
product without a human saying so.

### 2.1 The third dimension: Constraints (D11)

What and How layers both describe *content* — what the product should do, or how this
org/team works — and both fall through a defined gap sequence when coverage is missing (§3.2).
**Constraints** are orthogonal to that: coding/design conventions, compliance/regulatory
requirements, and scheduling/dependency constraints that bound the solution space regardless of
which feature is being built. They don't get a `<What|How>-L<N>` number because they aren't
tiered by scope/maturity — they're always-apply guardrails, compiled once and checked once per
context package, not per aspect.

| Dimension | What it is | Status | Where it lives |
|---|---|---|---|
| **Constraints** | Coding/design conventions, compliance/regulatory requirements, and scheduling/dependency constraints, each tagged `constraint_class: compliance \| convention \| scheduling` | **Optional infrastructure** | `compiling-project-guidelines`, cached as `COMPILED-GUIDELINES.md` — the same skill and cache file How-L2 above draws on, but read for a different purpose (see below) |

**Optional, not a gap.** Unlike a What-L1/How-L1 gap (§3.2), a project that has never run
`compiling-project-guidelines` simply proceeds without a Constraints layer —
`ult-context-generate/SKILL.md` Step 5.5 checks whether `COMPILED-GUIDELINES.md` exists and, if
not, skips past it. Absence here says nothing about coverage the way a What/How gap does; it just
means this optional infrastructure hasn't been set up yet.

**A distinct conflict-detection shape**, alongside §3.1's `l2-l3-contradiction`:
- **`constraint-lateral`** — two scope-glob sections of `COMPILED-GUIDELINES.md` disagree at a
  shared interaction point (e.g. one path-glob's convention contradicts another's exactly where
  the two scopes touch).
- **`constraint-vertical`** — a constraint contradicts a requirement or code-graph finding pulled
  from the What dimension.

Both block the same way any other conflict does (§3.1) — surfaced to a human, never silently
resolved. See `ult-context-generate/SKILL.md` Step 5.5 and
[`references/context-package-schema.md`](.github/skills/ult-context-generate/references/context-package-schema.md)
for the exact schema.

## 3. How a context package gets built

A context package isn't retrieved once and cached forever — it's assembled fresh for a specific
feature/task, per **aspect** (a feature is broken into a small set of aspects — e.g. an existing
baseline plus the new delta being added — so a gap in the new part isn't hidden by coverage that
only applies to the old part).

```mermaid
flowchart LR
    subgraph Sources["Sources (source-attributed)"]
        L3["What-L3<br/>code graph"]
        L2W["What-L2<br/>requirements docs"]
        L1W["What-L1 (piloting)<br/>external specs"]
        L2H["How-L2<br/>compiled guidelines"]
        L1H["How-L1 (piloting)<br/>org process standards"]
        Con["Constraints (§2.1, optional)<br/>compiled guidelines, read as guardrails"]
    end

    Sources --> Engine["ult-context-generate<br/>gap · conflict · staleness checks"]
    Engine --> Package["Context package<br/>(YAML, source-attributed,<br/>content-hashed)"]
    Package --> Gate{"Human<br/>approval gate"}
    Gate -- approved --> Consumer["Downstream skill<br/>(design / plan / tests / review / ...)"]
    Gate -- rejected / edited --> Engine

    style L1H stroke-dasharray: 5 5
    style Con stroke-dasharray: 5 5
```

### 3.1 Conflict detection — blocks

Before anything is assembled, sources are checked against each other: does a requirement
contradict what the code graph shows (`l2-l3-contradiction`)? Do two Constraints scope-glob
sections disagree at a shared interaction point, or does a constraint contradict a What-dimension
requirement (`constraint-lateral`/`constraint-vertical`, §2.1)? On a genuine contradiction, the
agent **MUST NOT** resolve it on its own — it **MUST** stop and ask a human, concretely:
"`<decision topic>` was decided as `<X>` here but `<Y>` there — which is right?"
The contested point **MUST NOT** proceed until that's answered.

### 3.2 Gap detection — falls through layers, never guesses

For each aspect, coverage is checked top-down: does the code (What-L3) cover it? Do the
requirements (What-L2) cover it? If **both** come up empty, the agent **MUST NOT** silently fill
the hole from its own judgment — the protocol **MUST** fall through a defined sequence:

```mermaid
flowchart TD
    A["Aspect has no What-L3<br/>or What-L2 coverage"] --> B{"What-L1 enabled<br/>and has a match?"}
    B -- yes --> C["Surface as What-L1 fallback item<br/>[L1 FALLBACK ITEMS — REVIEW]"]
    B -- no / no match --> D{"Offer model's own<br/>training knowledge?"}
    D -- accepted --> E["Surface as training-knowledge item<br/>[LLM TRAINING-KNOWLEDGE ITEMS — REVIEW]<br/>tagged with knowledge_cutoff"]
    D -- declined / empty --> F["Complete gap — ask the human directly,<br/>don't guess"]
    C --> G["Human reviews & confirms/rejects<br/>each item before approval"]
    E --> G
    F --> G
```

Every fallback item — whether sourced from an external spec or the model's own training data —
**MUST** carry an explicit provenance tag and sit in its own reviewer block. An item **MUST NOT**
enter an approved package without a human confirming it belongs there.

### 3.3 Staleness detection — non-blocking, but never silent

Two things can go stale between when a source was built and when it's used: the code graph (was
it built from the current commit?) and the compiled-guidelines cache (has anything it was built
from changed since?). Staleness **MUST** be checked, but a stale source **MUST NOT** block
assembly — the protocol surfaces a one-line nudge ("graph built from `<old-commit>`, current is
`<head>` — consider re-running `ult-codegraph`") and proceeds with what's available. The judgment
call — is a slightly stale graph good enough right now, or does this feature need a fresh one —
stays with the human; the agent **MUST NOT** decide it unilaterally.

### 3.4 The human-approval gate

Once gaps and conflicts are resolved (or explicitly deferred with the human's sign-off), the
package **MUST** be assembled with every item source-attributed to a `file:line-range` or an
external reference, and every decision logged. It is presented for review — a package **MUST NOT**
be treated as final until a human explicitly approves it. This is the one property that separates
this protocol from "the agent read some files and proceeded": a downstream consumer **MUST NOT**
trust a package that hasn't been looked at.

Approved packages are content-hashed and tagged (`<package-id>@<hash8>`), so any consumer can
tell later whether the package it's citing has drifted since approval — see
[`CONSUMING-CONTEXT-PACKAGE.md`](.github/skills/ult-context-generate/CONSUMING-CONTEXT-PACKAGE.md)
for the full consumption contract, or
[`user_guides/topics/consuming-a-context-package.md`](user_guides/topics/consuming-a-context-package.md)
for a shorter, friendlier on-ramp.

A human's correction at this gate can optionally be persisted forward, opt-in and one question
at a time, into compiled project guidelines so future packages start from it too — see
`ult-context-generate/SKILL.md` Step 9.5.

## 4. What makes this a protocol, not a tool

A few properties are deliberately non-negotiable across every skill in this repo, because
they're what "protocol" means here rather than "product":

- **Every claim is source-attributed.** A `context_items` entry always names where it came from
  — a file:line-range, an external doc, or (explicitly labeled) the model's own training
  knowledge. Nothing is asserted without a citation.
- **Conflicts block; gaps fall through a defined sequence; staleness nudges.** These are three
  distinct failure modes with three distinct handling rules — never collapsed into one generic
  "warning."
- **The human-approval gate is mandatory, not configurable away.** A context package that hasn't
  been approved is not a context package a downstream skill should trust.
- **Consumption is a documented contract, not folklore.** Any skill that wants to use an approved
  package follows the same numbered steps (discover → confirm → load → spot-check → cite →
  tag) — see §3.4's links.

## 5. How-L1 — gap-triggered, task-type-scoped (piloting)

**How-L1 is implemented, but newly added and not yet field-validated against a real corpus.**
`context-config.yaml`'s `how_l1` section defaults to `enabled: false`; leave it that way until
you've run it once against your own org's process-standard `.md` files and confirmed the results
look right. Once enabled, it reuses the same deterministic `md_index.py` mechanism as What-L1
(§2 above), but is wired into the flow differently, described below.

**What it ingests:** org-wide *process* standards — the kind of thing a CMMI appraisal, an
ISO 9001 quality manual, or an IEEE process standard describes — as distinct from How-L2's
project-specific compiled conventions (style guides, templates, examples). Where How-L2 answers
"how does *this team* format a design doc," How-L1 answers "what does *this organization's*
quality process require of any design doc, regardless of team."

**Where it slots in:** inside Step 2's existing D8 branch ("How dimension complete gap" — How-L2
has no relevant content for this task type), not between Step 2 and Step 3, and not per aspect.
Step 2 has no aspect loop, so How-L1 fires **once per package**, gap-triggered off How-L2 coming
up empty for the task type — structurally parallel to What-L1's Step 7.1, but task-type-scoped
rather than aspect-scoped. See `ult-context-generate/references/how-l1-fallback-query.md` for the
exact procedure. Unlike What-L1, there is no web-search/training-knowledge fallback chain of its
own: Step 2's existing D8 prompt ("(a) use my best-practice suggestion / (b) I'll provide the
template myself") already gives the human an equivalent decision point when How-L1 finds nothing.

**How it's gated:** the same way What-L1 fallback items are gated — a dedicated
`[HOW-L1 FALLBACK ITEMS — REVIEW]` block at Step 9's human-review step, tagged with provenance,
never auto-approved. A How-L1 item describes what the *organization's process* requires, not what
*this product* does — the same "informative, not automatically authoritative" caveat that
applies to What-L1 items applies here too. Rejecting an item decrements
`how_l1_fallback_count`, removes it from `context_items`, and (if it was the only How-L1 evidence
for the package) resets `how_l1_covered` to `false` and re-surfaces Step 2's D8 prompt.

**What's still manual:** curating the process-standard corpus itself (dropping the relevant
CMMI/ISO/IEEE `.md` files under `how_l1.path` and building the index) is on the org, same as
How-L2's `org/guidelines/` corpus. How-L2 remains the supported path for project-specific
narrative process guidance; How-L1 only fires when How-L2 has nothing for the task type at hand.

## 6. Runtime adapters are generated, the protocol isn't

One more property worth naming explicitly: the protocol content (each `SKILL.md`, its
consumption contract, its config schema) is written once, in Claude Code's native format, and
every other runtime's adapter (`.prompt.md` for Copilot, `.mdc` for Cursor, `AGENTS.md` rows for
Codex) is **generated from it** by `catalog/export_adapters.py` — never hand-duplicated. See
[`README.md`](README.md#runtime-support) for current per-runtime validation status.
