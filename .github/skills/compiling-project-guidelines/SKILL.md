---
name: compiling-project-guidelines
description: Compile scattered guideline sources into one scope-aware COMPILED-GUIDELINES.md for other skills and ult-context-generate's Constraints layer. Do NOT use to enforce rules at runtime.
namespace: ult
version: 0.2.0
origin: ground-up
author: Pranay Mishra
maintainer: Pranay Mishra
adapted_from: ~
upstream_version: ~
released: 2026-06-08
tags: [developer, workflow, guidelines, conventions, scope-aware, conflict-resolution]
bundle: utilities
tier: draft
---

# Compiling Project Guidelines

## Overview

Large C/C++/Go/Java codebases (often ~500 KSLOC, sometimes multi-repo) almost always carry their
own design and coding conventions — scattered across `CONTRIBUTING.md`, `.github/instructions/`,
architecture docs, PDFs, wiki exports, and tribal knowledge. Project teams will not adopt any
workflow skill that quietly violates those conventions.

This skill is the **one-time (and on-demand) compiler**: it reads whatever guideline sources a
team already has — without asking them to migrate to a new schema or folder convention — and
produces a single, predictable, human-readable file that every other skill can cite before
it reads, writes, modifies, reviews, or judges project code.

**Run this:**
- Once, during project setup (`/ult-compile-guidelines`)
- Again on demand whenever guideline sources change ("update my compiled guidelines — I added
  `docs/payments-conventions.md`")

For multi-repo projects, run it once per repo — scopes are path globs relative to that repo, so
no cross-repo machinery is needed.

**Output:** `starter_kit/project_guidelines/COMPILED-GUIDELINES.md` — see
[the format spec](#step-6--write-the-compiled-file) below. This is the *only* artifact this
skill produces. There is no registry, no schema, no state machine, no decision log file — the
compiled file carries its own provenance and its own conflict-resolution history.

**`compiled_guidelines` (D20 Phase 2, D21 §16.4):** the output path above is
the `compiled_guidelines` path-slot — the registry's only `kind: file` slot,
resolved via `ult-repo-layout/SKILL.md`'s "Path resolution algorithm (§15.5 +
§16.2)," not a hardcoded path. If `/ult-repo-layout init|reconcile` has run
for this project, read `project_layout.slots.compiled_guidelines.path`
(confirmed by its `.layout-slots.yaml` marker — `kind: file, file:
COMPILED-GUIDELINES.md`); otherwise fall back to the slot's **resolved
default** — `{workspace_root}/cache/project-guidelines/COMPILED-GUIDELINES.md`
if `layout.workspace_root` is set, else
`starter_kit/project_guidelines/COMPILED-GUIDELINES.md` (unchanged from before
Phase 2). Note the bucket reassignment under `workspace_root`: this file
re-roots to `cache/`, **not** `inputs/` — it is a derived artifact, no longer
colocated with the raw `starter_kit/project_guidelines/` drop-zone sources
once `workspace_root` is set. Resolve it once per run and substitute it for
`starter_kit/project_guidelines/COMPILED-GUIDELINES.md` everywhere it appears
below.

## The load-bearing principle: scope-awareness, applied while reading — not while resolving

Read this before doing anything else. Everything below depends on it.

> Large and multi-repo codebases routinely contain *legitimate*, non-conflicting,
> module/component-specific conventions — legacy vs. new code, differing build systems per
> service, language-specific idioms within a polyglot monorepo. "Legacy drivers use K&R brace
> style" and "new modules use Allman style" are **two correct entries**, not a conflict.
> Flattening that layered reality into one global answer — or defaulting to a global pattern
> when a more specific one actually governs — produces guidance that *looks* authoritative while
> being *wrong for the area it's applied to*. That's worse than no compiled guidance at all,
> because wrong-with-confidence is harder to catch in review than no-guidance-given.

The fix is procedural: **tag scope as you read each source, before you ever compare sources to
each other.** Untagged guidance defaults to scope = `Global`. If you do this consistently, the
later "find conflicts" step becomes trivial and almost always comes up empty — because most
apparent disagreements between docs written years apart turn out to be correctly-scoped
differences, not contradictions. Skipping or shortcutting this step is the single most likely way
this skill produces a bad compiled file, so do not let yourself rush past it.

## The flow

Run these steps in order. Don't skip step 2's scope-tagging to "save time" — that's where the
quality of everything downstream is decided.

### Step 1 — Gather sources

Auto-suggest candidates from conventional locations:
- `.github/instructions/*.instructions.md`
- `.github/copilot-instructions.md`
- `CONTRIBUTING.md`
- `docs/guidelines/**`, `docs/architecture/**`
- anything already sitting in `starter_kit/project_guidelines/` (except
  `.pointer.md`)

Then **show the user what you found and ask them to confirm, add, or remove paths** —
including pointing you at PDFs, DOCX, wiki exports, or style-guide documents that auto-discovery
can't see. For binary formats, use the existing `ult-read-pdf` / `ult-read-docx` skills to read
them (install their script dependencies first, the same way `pm-project-plan` does — see that
skill's "Install dependencies" step for the exact idempotent npm-install commands if you need
them).

Do not silently skip a source the user points you at because it's an unfamiliar format — ask for
help reading it before giving up on it.

### Step 2 — Extract WITH scope tags (the step that must not be shortcut)

While reading each source, record not just *what* the guidance says but *where it claims to
apply*: a directory/module/component name, a path glob, a language/build-target boundary, an
explicit "legacy vs. new" distinction, a service name, etc.

For every rule you extract, you should be able to answer: "if an engineer were touching path `X`,
would this rule apply?" If the source doesn't say, the scope is `Global` — don't guess a
narrower scope into existence, and don't widen a narrow one to Global either.

**Real sources very often state scope by *named functional area* rather than by path** — a
`learnings.md` tagging entries `[Auth]`, `[DB]`, `[UI]`, `[Ops]`; a design doc that says "this
file is scoped to visual language only, it must not change CRUD semantics or backend behavior."
That's a legitimate scope statement, not a vague one — but consumers of the compiled file match
against the *paths their task touches* (see `CONSUMING-COMPILED-GUIDELINES.md` step 2), not
against topic tags. So when you encounter a named-area scope, **resolve it to the path footprint
that area actually occupies in this codebase** (a quick `grep`/`glob` for the area's
characteristic names is usually enough — e.g., `[Auth]` → wherever `auth`/`login`/`session`
logic lives) and write the `### Scope:` heading with those real globs, keeping the area name as
the human label so the *why* stays traceable. If a clean path mapping genuinely doesn't exist
for a named area (it's cross-cutting, or the codebase doesn't group by it), say so in the entry
rather than forcing a glob that would never match anything — and note in "Noted Tensions" that
this guidance is topic-scoped, not path-scoped, so a human applying it has to recognize the
*topic* of their change, not just its location.

**Also tag each rule's `constraint_class`** (D11) — this drives the conflict check in
step 4 and lets `ult-context-generate` load this file as the project's Constraints
layer:

- `compliance` — a regulatory, legal, security, or audit requirement. Narrower scopes
  may **tighten** a `compliance` rule but never **loosen** it (step 4 checks this). Look
  for cited standards (GDPR, SOC2, MISRA, DO-178C, internal security policy) or language
  like "must", "required by", "audit", "retention".
- `scheduling` — a sequencing, phasing, or dependency constraint ("migrate consumers
  before removing the old endpoint", "feature flag rolls out region-by-region").
- `convention` — everything else: coding style, architecture choices, naming, tooling.
  **This is the default** — if a rule doesn't clearly read as `compliance` or
  `scheduling`, tag it `convention`. Most guideline docs are conventions.

Keep a running scratch list shaped like:
```
RULE: <the guidance, paraphrased faithfully — don't editorialize>
SCOPE: <Global | path-glob + short label>
CONSTRAINT_CLASS: compliance | convention | scheduling
SOURCE: <file path + the line/section that said so>
```

### Step 3 — Group by scope, not by source document

Guidance that shares a scope *and* topic gets merged into one entry. Guidance with different
scopes is kept as **separate entries** even when it looks superficially similar or contradictory.

This is where the scope-tagging from step 2 pays off: "legacy drivers use K&R" and "new modules
use Allman" are not weighed against each other here — they're filed as two entries under two
different `### Scope:` headings, full stop.

### Step 4 — Escalate only genuine conflicts

Two kinds of genuine conflict get escalated here. Both are narrow by design — the
point is to keep the human Q&A focused on things that genuinely need a judgment call.

**1. Same-scope conflict** (original trigger): **the same rule, claimed for the same
scope, stated two incompatible ways** — e.g., two documents both describe
`services/payments/**` and disagree on which test framework is canonical for it.

**2. Vertical compliance conflict** (D11 Type 1): a narrower-scope `compliance` entry
that would **loosen** a broader-scope `compliance` entry on the same topic, where the
narrower scope's path glob sits inside the broader scope's (every scope sits inside
`Global`). Example: `Global` says "[compliance] all PII deleted within 2 years"; a
`services/guest-accounts/**` entry says "[compliance] guest account activity logs
retained indefinitely for fraud analysis." Same topic (data retention), narrower
scope, and the narrower entry loosens the broader requirement — escalate it.

A narrower entry that **tightens** a broader compliance entry (e.g., "Global: 2 years"
→ "payments/**: 90 days") is **not** a conflict — narrower-tightens-broader is the
expected, healthy case. Only loosening escalates.

Anything that resolves by scoping is **not** a conflict — it was already filed as two entries in
step 3. Do not escalate:
- Differences that turn out to be about different scopes (that's step 3's job, already done)
- Stylistic rewording of the same rule for the same scope (that's the same rule — merge it, cite
  both sources)
- A newer doc superseding an older one on the *same point for the same scope* where the newer
  doc says so explicitly (note the supersession in the entry, don't escalate it)
- A narrower `compliance` entry that **tightens** (rather than loosens) a broader one on the
  same topic

Keeping this list short is the point: it keeps the human Q&A focused on things that genuinely
need a judgment call, instead of forcing the engineer to adjudicate every textual difference
between documents written years apart by different authors.

### Step 5 — Resolve flagged conflicts interactively, one at a time

For each **same-scope conflict** from step 4, ask the user directly and concretely:

> "Source A (`<file>`) says `<X>` for `<scope>`. Source B (`<file>`) says `<Y>` for the same
> scope. Which is current — or does each actually apply to a different sub-scope I should split
> out?"

For each **vertical compliance conflict** from step 4, frame it differently — the
question is whether the narrower scope's exemption is legitimate, not which source is
"more current":

> "`<broader scope>` requires `<X>` (compliance, from `<source>`). `<narrower scope>`
> appears to loosen this to `<Y>` (from `<source>`). Is `<narrower scope>` genuinely
> exempt for a documented reason — or should it be tightened to comply with `<X>`?"

Three possible outcomes for a vertical conflict:
- **Exempted** — the user confirms a documented reason for the exemption. Record as
  resolved with that reason.
- **Corrected** — the user says the narrower scope should comply. Update that entry's
  text (step 3's grouping) to the tightened value and record as resolved.
- **Unresolved** — the user can't decide on the spot (needs sign-off from
  compliance/legal/another team). Record as unresolved, naming who it's escalated to.
  `ult-context-generate` (D11 Step 5.5) carries unresolved vertical conflicts forward
  into any feature whose scope they touch.

One question at a time. Record the resolution **and the user's stated reason** verbatim (or
close to it) directly into the compiled file's `## Noted Tensions` section — that log is the
only "decision persistence" this design needs. It lives in the one artifact everyone already
reads, so it can't drift out of sync with a separate state store (because there isn't one).

### Step 6 — Write the compiled file

Write to the resolved `compiled_guidelines` path (see the path-resolution note
above). Its pre-D21 default — the standard, predictable path when
`layout.workspace_root` is unset:

```
starter_kit/project_guidelines/COMPILED-GUIDELINES.md
```

Colocated with whatever raw sources the team already drops in
`starter_kit/project_guidelines/` — the same starter-folder convention as
`starter_kit/threat_modeling/` — so provenance sits one folder away from the
artifact it produced, **when `layout.workspace_root` is unset**. Once set,
`compiled_guidelines` re-roots to `{workspace_root}/cache/project-guidelines/`
while the raw sources stay under
`{workspace_root}/inputs/starter-kit/project_guidelines/` — colocation is a
property of the pre-D21 default, not a guarantee.

Use exactly this shape (organized prose with scope as a first-class structural element — not a
database, not YAML, a Markdown file a human can open and skim):

```markdown
# Project Guidelines (Compiled)

> Generated by /ult-compile-guidelines on <YYYY-MM-DD>
> Sources:
>   - <source file> (modified <date>)
>   - <source file> (modified <date>)
> Re-run /ult-compile-guidelines after changing any source above — this file does not auto-update.

## How consuming skills should use this file
1. Identify the file paths / components your current task touches.
2. Find every section under "Scoped Guidance" whose path pattern matches those paths.
   The MOST SPECIFIC matching scope governs that area — it overrides "Global" for anything
   inside it. Do not apply Global guidance where a more specific scope exists and conflicts with it.
3. Where no scoped section matches, "Global" applies.
4. State which scope(s) you used in your output.

## Global
- [convention|compliance|scheduling] <guidance that genuinely applies everywhere, one bullet per rule>

## Scoped Guidance

### Scope: `<path-glob>` — "<short human label>"
- [convention|compliance|scheduling] <guidance that applies only within this scope>

## Noted Tensions (resolved during compilation — preserved across re-runs)
- <date>: <Source A> (<its scope>) says <X>; <Source B> (<its scope>) says <Y>.
  Resolved as <scope split | supersession | other> — see entries above.
  Confirmed by <who> as <their stated reason>.
- <date>: [VERTICAL/COMPLIANCE] `<broader scope>` requires <X>; `<narrower scope>`
  would loosen this to <Y>.
  Status: Exempted — <reason> | Corrected — narrower entry now reads <Z> | Unresolved — escalated to <who> on <date>

## Recent Observations (pending compile)
- <date> [<skill-name>]: <observation — a new lint rule, a convention that appears
  to have drifted from what's documented, anything guideline-relevant noticed
  while doing unrelated work>
```

Notes on filling this in:
- The header's source list is load-bearing — it's what makes the staleness nudge in
  `CONSUMING-COMPILED-GUIDELINES.md` possible. Record the real modification date of each source
  at compile time.
- `## Global` holds only guidance that is genuinely scope-free. If you're unsure whether
  something is Global or just under-specified in its source, prefer filing it as Global and note
  the ambiguity rather than inventing a scope the source never stated.
- Every `### Scope:` heading carries both a path glob (so consumers can match against it
  mechanically) and a short human label (so a reviewer immediately understands *why* that
  boundary exists — "legacy", "new service", "vendor-supplied", etc.).
- Every bullet under `## Global` and `## Scoped Guidance` carries a `[constraint_class]`
  prefix (D11) — `compliance`, `convention`, or `scheduling`, as tagged in step 2.
  `ult-context-generate` reads this tag when loading this file as the project's
  Constraints layer.
- `## Noted Tensions` is append-only across re-runs (see below) — it is the project's compiled
  history of "we looked at this, and here's what we decided and why." `[VERTICAL/COMPLIANCE]`
  entries with `Status: Unresolved` are how `ult-context-generate` (D11 Step 5.5) finds
  open compliance questions that touch a feature's scope.
- `## Recent Observations (pending compile)` is also append-only between re-runs, but for a
  different reason: it's an *inbox*, not a log. Entries are written by consuming skills via
  `CONSUMING-COMPILED-GUIDELINES.md` step 5 — a lightweight, unreviewed note left between
  compile runs. Triage it on the next `/ult-compile-guidelines` run (see "On re-run" below);
  the section should be empty immediately after a compile. Omit the section entirely if it
  would be empty.

## On re-run (updating an existing compiled file)

When `/ult-compile-guidelines` is invoked and the resolved `compiled_guidelines`
path (`starter_kit/project_guidelines/COMPILED-GUIDELINES.md` by default — see
the path-resolution note above) already exists:

1. **Triage `## Recent Observations (pending compile)` first**, before anything else. For each
   entry: if it's straightforward new guidance, fold it into `## Global` or `## Scoped Guidance`
   as a new rule (tagging it with a `[constraint_class]` per step 2, same as any other source
   material). If it conflicts with existing compiled guidance, run it through the step 4/5
   conflict flow below and let the outcome land in `## Noted Tensions`. Either way, remove the
   entry from `## Recent Observations` once triaged — the section should be empty (or omitted
   entirely) by the time this compile finishes.
2. **Read it first.** Its `## Noted Tensions` log tells you which conflicts were already raised,
   how they were resolved, and why.
3. **Carry forward resolved tensions** whose underlying sources haven't changed since — don't
   re-litigate them. If a source involved in a previously-resolved tension *has* changed, surface
   it to the user as "this was previously resolved as `<X>` — still applies, or has something
   changed?" rather than re-running the full Q&A from scratch.
3a. **Re-check `Status: Unresolved` vertical conflicts** — ask the user once per re-run
   whether there's now an answer ("`<broader scope>` vs `<narrower scope>` on `<topic>`
   was escalated to `<who>` — has that come back?"). If yes, update the entry to
   Exempted/Corrected. If still pending, carry it forward unchanged.
4. **Only run the full step 4/5 conflict flow on genuinely new material** — new sources,
   changed sections of existing sources, or `## Recent Observations` entries flagged in step 1
   as conflicting.
5. Rewrite the file in place, preserving prior `## Noted Tensions` entries and appending new
   ones. The compiled file is its own state — there is no separate
   `conflicts.resolved.json` or decision log to keep in sync.

## What this skill deliberately does not do

- It does not execute, lint, or validate anything described in the guidance — it only reads and
  organizes prose. There is nothing here that runs commands sourced from guideline text.
- It does not gate, block, or enforce. A scope mismatch downstream is a one-line note for human
  review, not a stop-the-line condition — there is no waiver workflow because there is no gate to
  waive.
- It does not require teams to restructure their existing docs, adopt a new schema, or move
  anything out of where it already lives — `starter_kit/project_guidelines/` is a place to drop
  *additional* sources if a team wants to, not a mandatory relocation target.
- It does not change how any other skill executes its own work. It only gives them one more file
  to read first, when one exists. See `CONSUMING-COMPILED-GUIDELINES.md` (colocated in this
  skill's directory) for the exact protocol every code-facing skill follows to consume the file
  this skill produces.

## When something doesn't fit this flow

If a source is genuinely unreadable (corrupted file, format none of the `ult-read-*` skills
handle), say so plainly, list it as "not compiled — could not read `<file>`" in the output file's
header, and continue with the rest. Don't block the whole compile on one bad source.

If the user has no guideline sources at all, say so and stop — don't fabricate a compiled file
from generic best practices. A compiled file that doesn't reflect this project's actual
conventions is worse than no compiled file, for the same reason stated in the scope-awareness
principle above: it looks authoritative while being wrong.
