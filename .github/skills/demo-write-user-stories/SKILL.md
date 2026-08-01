---
name: demo-write-user-stories
description: Reference implementation that writes functional user stories from a feature description, optionally grounded in an approved CEP context package per CONSUMING-CONTEXT-PACKAGE.md, with per-story citations and the standard tag/reverse-index loop. A worked example for downstream teams building their own context-consuming skills.
namespace: demo
version: 0.1.0
origin: ground-up
author: Pranay Mishra
maintainer: Pranay Mishra
adapted_from: ~
upstream_version: ~
released: 2026-08-01
tags: [demo, user-stories, consumer-reference, context-engineering, worked-example]
bundle: utilities
tier: draft
---

# Demo: Writing User Stories (worked example)

## Overview

This is a lean, from-scratch reference implementation of a real downstream
consumer of CEP context packages — not a toy, and not part of core CEP.
Given a feature description, it writes standard-form user stories, grounded
in an approved context package's `context_items` when one is available, and
follows the same discover/load/tag/reverse-index loop every consuming skill
in this repo follows via `CONSUMING-CONTEXT-PACKAGE.md`.

It is deliberately minimal: no actor taxonomy, no Enabler/NFR/
Requirement-Note story types, no org-convention lookup, no scoring rubric.
Any team that wants a production backlog tool should build one of those on
top of this pattern — this skill exists to show the pattern itself, cleanly,
end to end, and to be genuinely usable as-is for a quick, honestly-grounded
first pass at a feature's user stories.

**Scope note:** this skill writes **functional user stories only** — plain
"As a / I want / so that" statements. It does not distinguish Enabler
stories, non-functional requirements, or requirement notes from functional
stories; a production backlog tool should make that distinction, a lean
reference example does not need to.

## Inputs

1. **Feature description** (required) — one or two sentences describing the
   feature or behavior to write stories for, the way a developer would
   actually phrase a ticket.
2. **Context package path** (optional) — an explicit path to an approved
   `contexts/<id>.yaml` file to use instead of discovering one. If given,
   skip step 1's glob check below and treat that file as the "Found"
   package for step 2 onward, subject to the same existence/approval check
   (non-empty `approved_by`).

## Steps

1. **Discover or load a context package** — follow
   `.github/skills/ult-context-generate/CONSUMING-CONTEXT-PACKAGE.md` steps
   0–3, using the feature description as the input artifact for step 0's tag
   scan (it will usually carry no `[Context: ...]` tag for a bare ask —
   that's expected, fall through to step 1's glob check) and an explicit
   package path (if given) per "Inputs" above. Load `context_items`,
   `decisions_log`/`decisions`, `aspects`, and `summary` per step 3 if a
   package is found and approved.

   **If no package is found:** write, as the first line of the output file:
   `No context package found — proceeding without it.` (same wording
   convention as `demo-consume-context`). Every story written this run is
   necessarily ungrounded — say so once here rather than per story.

2. **Identify actors** — keep this a plain list, not a taxonomy:
   - First, pull any actor/persona explicitly named in the feature
     description itself (e.g. "a keyboard-only user", "an admin", "the CLI
     caller").
   - If a package was loaded, also scan `context_items[].summary` (and
     `decisions_log`/`decisions` entries) for roles implied by who
     exercises the described behavior (e.g. a summary describing a flag's
     CLI-facing behavior implies "the CLI user"; a summary describing an
     internal API contract implies "a downstream caller/integrator").
   - If neither source yields anything specific, fall back to the two
     generic actors "User" and "Developer" — and say so explicitly in the
     output ("no specific actor named or implied — using generic actors").
   - Do not invent a bucketed taxonomy (end-user / system / stakeholder,
     etc.) — a flat list is the whole mechanism here.

3. **Write user stories**, one per distinct capability identified from the
   feature description (and, if loaded, the package's `context_items` /
   `decisions_log`), in standard form:

   > As a `<actor>`, I want `<capability>`, so that `<benefit>`.

   Functional stories only, per the Scope note above. Aim for one story per
   actor/capability pair that's actually distinct — don't pad with
   near-duplicate stories to hit a target count.

4. **Cite grounding per story.** If a package was loaded, every story ends
   with one line naming the `context_items` `id`(s) it actually drew from:

   > Grounded in: `ctx_003`, `ctx_005`

   A story that draws on no specific item (e.g. it follows directly from
   the feature description's own wording, not from anything the package
   added) is written as:

   > Grounded in: feature description only (no package item cited)

   If no package was loaded, every story instead carries:

   > Grounded in: bare feature description (no context package available)

   This is a plain citation line, not the contract's formal `[Context:
   <package-id>@<hash8> · ctx_NNN · aspect <id>]` item-level tag —
   `CONSUMING-CONTEXT-PACKAGE.md` step 9 marks item-level tags N/A for a
   document-level consuming skill like this one (they apply to a producer
   that pushes individually-addressable sub-units to an external tracker,
   which this skill does not do). The document-level tag in step 5 below is
   this skill's actual step-9 tag.

5. **Tag the output and write the reverse-index addendum** — reuse the
   exact mechanism `demo-consume-context` already uses, unchanged:
   - Per step 9, add a `**Context package(s):** <id>@<hash8>` line at the
     top of the output file for every package consulted (omit entirely if
     none was).
   - Per step 9's "Reverse-index addendum" subsection, append a `kind:
     reference` entry to each consulted package's sibling
     `contexts/<package-id>_<date>.addenda.yaml` (`added_by:
     demo-write-user-stories`, `artifact:` the output file's path, `cites:
     {ctx_ids: [...]}` listing every `context_items` id actually cited
     across all stories in step 4).
   - State which mode was used, per step 8: `"Context package consulted:
     <id>@<hash8> (...)"`, or `"No context package found — proceeding
     without it."`

6. **Save the output** to `outputs/user-stories/<feature-slug>.md`, where
   `<feature-slug>` is a kebab-case slug derived from the feature
   description (same slugging convention `ult-context-generate` uses for
   `FEATURE_SLUG`).

## Output shape

```markdown
**Context package(s):** <id>@<hash8>       <!-- omitted if none consulted -->

# User Stories: <feature name>

<one line: package consulted / not found, per step 5>

## Actors

- <actor 1>
- <actor 2>
...

## Stories

### US-001

As a <actor>, I want <capability>, so that <benefit>.

Grounded in: `ctx_00N`[, `ctx_00M`]

### US-002
...
```

## Do NOT use for

Anything requiring Enabler stories, NFR acceptance criteria, org-convention
enforcement, or multi-actor-bucket taxonomies — those are production
backlog-tool concerns, deliberately left out of this lean reference. This
skill also does not generate or modify a context package itself — for that,
use `ult-context-generate`.
