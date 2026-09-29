---
generated_by: ult-autoscaffold-content
generated_at: <YYYY-MM-DD>
status: draft
content_mode: <content-mode>
doc_kind: architecture_overview
skill_version: <skill-version>
---

<!-- Generated starting point — genuine draft for a human to extend, never
     a claim of completeness. Base every claim on what you can actually
     observe.

     Evidence: see references/evidence-probes.md#architecture_overview for
     what to look for per section below (prioritize the work packet's own
     must_cite/evidence_hints, when this run has any, first, then that
     checklist).

     Every claim needs one of exactly two things, never a plausible-sounding
     guess in between:
       - a citation, inline: [src: path#Lx-Ly]
       - or, if genuinely not observable after looking, the literal gap
         line: "Not evidenced. Searched: <signal 1>, <signal 2> (absent)."
     A wrong answer stated confidently is worse than an honest gap. -->

# <Project name> — Architecture & Conventions Overview

## Overview

<!-- One paragraph: what does this system do, and for whom? Include the
     primary purpose and deployment context if observable (library,
     service, CLI, embedded, etc.). -->

TBD — fill in

## Components

<!-- One row per top-level module/package actually present in the repo. -->

| Component | Source path | Role |
|---|---|---|
| TBD — fill in | TBD — fill in | TBD — fill in |

## Component interactions

<!-- ASCII or Mermaid, one level of nesting. Only draw an edge you can
     evidence from an import, a call, or a message — see the code graph if
     graph-mode is active for this run. -->

```
[Component A] ──→ [Component B]  : TBD — relationship / API / message type
```

## Primary data/control flows

<!-- Brief description of the primary flow(s) through the system, if
     observable — entry point to final consumer. -->

TBD — fill in

## External interfaces

<!-- Only if this project actually exposes or consumes an external
     interface (HTTP API, message queue, file format, CLI). Delete this
     section if none exist. -->

| Interface | Peer | Protocol / Format |
|---|---|---|
| TBD — fill in | TBD — fill in | TBD — fill in |

## Key design decisions

<!-- The 3-5 architectural decisions a new contributor most needs to
     understand. Only decisions you can evidence, not general best
     practice. -->

1. TBD — fill in

## Known constraints and invariants

<!-- Constraints the code visibly enforces — a guard clause, an assertion,
     a documented limit. Not a guessed-at best practice. -->

- TBD — fill in
