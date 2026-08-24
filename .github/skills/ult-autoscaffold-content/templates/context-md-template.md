---
generated_by: ult-autoscaffold-content
generated_at: <YYYY-MM-DD>
status: draft
---

<!-- Generated starting point — genuine draft for a human to extend, never
     a claim of completeness. Section depth for this module is governed by
     its tier — see references/module-context-depth-by-tier.md for which
     sections apply; delete every section that doesn't, replacing it with
     a single "TBD — not covered at this tier's depth" line. Where a kept
     section's content genuinely isn't observable, write
     "TBD — <what's missing and why>" instead of a plausible-sounding
     guess. -->

# <module-name> — Module Context

**Source path:** `<module-path>`
**Module owner:** TBD — fill in

## Purpose

<!-- Two to four sentences: what does this module do? What problem does it
     solve? What is its boundary — what does it own and what does it
     explicitly not own? Grounded in what the module's own files and entry
     points actually do. -->

TBD — fill in

## Inputs

<!-- What this module reads or receives — function/API arguments, config
     it reads, files it reads, messages it consumes. Only what's
     observable in the code. -->

| Source | Data / interface type | Trigger |
|---|---|---|
| TBD — fill in | TBD — fill in | TBD — fill in |

## Outputs

<!-- What this module produces, returns, or writes. -->

| Consumer | Data / interface type | Condition |
|---|---|---|
| TBD — fill in | TBD — fill in | TBD — fill in |

## Key abstractions

<!-- The two or three central types/classes/functions a new contributor
     would need to understand first. -->

| Name | Kind | Role |
|---|---|---|
| TBD — fill in | TBD — fill in | TBD — fill in |

## State machine (if applicable)

<!-- Delete this section entirely if this module has no state machine. -->

```
[STATE-A] ──→ [STATE-B] ──→ [STATE-C]
```

## Dependencies

<!-- What this module depends on and (when graph-mode is active) what
     depends on it, per scaffold_state.py's recorded in_degree/basis for
     this module. -->

| Depends on | What it provides |
|---|---|
| TBD — fill in | TBD — fill in |

## Design invariants

<!-- Any constraint the code visibly enforces (e.g. a guard clause, an
     assertion, a type constraint) — not a guessed-at best-practice the
     code doesn't actually enforce. -->

1. TBD — fill in

## Gotchas

<!-- Anything non-obvious you can point to concrete evidence for (a
     comment, a workaround, an unusual pattern) — never a generic warning
     that could apply to any module. -->

- TBD — fill in
