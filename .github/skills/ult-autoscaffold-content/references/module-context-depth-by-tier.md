# Module `CONTEXT.md` section depth by tier

Read by Step 5b before writing a module's `CONTEXT.md`. Tier comes from
`scaffold_state.py scan`'s own tiering (Step 4) — don't re-derive it.
`templates/context-md-template.md` carries the full Tier 1 section set with
its own per-section guidance; this table says which sections to keep.

Evidence gathering for whichever sections a tier keeps is governed by
`references/evidence-probes.md#context_md` — read it (and the packet's own
`must_cite`/`evidence_hints`, when this run has a packet) before writing
the section; it names what to look for per section and the exact
`[src: path#Lx-Ly]` / `Not evidenced. Searched: ... (absent).` reporting
format every kept section must use. This file only ever decides *which*
sections apply at a given tier, never *how* to evidence them.

| Tier | Sections to keep from the template |
|---|---|
| **Tier 1** (high-importance) | All of them — Purpose, Inputs, Outputs, Key abstractions, Dependencies, Design invariants, Gotchas (State machine only if the module actually has one). |
| **Tier 2** (ordinary) | Purpose, Key abstractions, Dependencies. Delete the rest; replace each deleted section with a single `TBD — not covered at this tier's depth` line instead of leaving it empty or half-filled. |
| **Tier 3** (leaf, only reached via manual selection — Step 4 auto-skips Tier 3 by default) | Purpose only. Delete everything else; same `TBD — not covered at this tier's depth` line for what's removed. |

Tier 0 (generated/vendor) is auto-skipped in Step 4 and never reaches this
step at all.

Same honesty standard as every other step: where a kept section's content
genuinely isn't observable, write `TBD — <what's missing and why>` instead
of a plausible-sounding guess.
