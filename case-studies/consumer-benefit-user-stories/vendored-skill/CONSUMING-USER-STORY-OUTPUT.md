<!--
Vendored reference copy, for reproducibility of the consumer-benefit-user-stories
case study. NOT part of this repo's installable skill set — see SKILL.md in this
same directory for the full note.
-->

# How a downstream stage of work consumes a generated user-story file

> **Status: production.** Complements `CONSUMING-CONTEXT-PACKAGE.md` (which
> covers the underlying YAML context package, `contexts/<id>.yaml`) — this
> contract covers the separate, human-readable user-story markdown file that
> `spw-write-user-story` produces at the `user_stories_output` path-slot
> (default `output_docs/user-stories/<feature-slug>_user-stories_<date>.md`).
> These are two distinct artifacts; a skill that wires in only one of the two
> contracts gets only half the available context.

Any skill asked to work on a feature that already has user stories — brainstorming
a design, writing a plan, writing tests, implementing a task — should check for
this artifact before doing that work.

## 1 — Detect

If your input (the user's request, a pasted reference, or an explicit file path)
references a file matching the `user_stories_output` path-slot (resolve the slot
via `ult-repo-layout`'s path resolution algorithm if the literal default
`output_docs/user-stories/*.md` doesn't match this project's configuration):
read it in full.

If no such file is referenced: proceed normally. This is purely additive, not
a requirement — most tasks have no associated user-story file.

## 2 — Extract

From the file:
- Feature title and scope (from the document header — `3a — Document header`
  in `spw-write-user-story/SKILL.md`)
- Story IDs (`US-NNN`) and each story's Acceptance Criteria (Gherkin scenarios
  or measurable bullet criteria, per the story's template)
- The Actor list (`[Actor: <name>]` tags)
- Out-of-scope items (used to prevent over-implementation)
- Each story's `[Context: <package-id>@<hash8> · ctx_NNN[, ...] · aspect
  <id>[, ...]]` tag — these cite the same context package(s) the user stories
  were generated from. Feed every distinct `<package-id>@<hash8>` found into
  `CONSUMING-CONTEXT-PACKAGE.md`'s step 0 (tag discovery) — the package itself
  (decisions, evidence, gaps) is additional context beyond what's in the
  user-story file alone.

## 3 — Apply (per consuming skill)

- **Design/review stage**: design sections must not contradict any Acceptance
  Criterion. Cross-check the design's scope and actors against the story
  file's scope/actor list before presenting the design — flag any mismatch
  to the user rather than silently resolving it.
- **Planning stage**: every Acceptance Criterion should trace to at least
  one task. Before finalizing the plan, check each story (and each
  Requirement Note's `→ Covered by:` target) against the task list — flag
  any story with no corresponding task as a gap, not a silent omission.
- **Test-writing stage**: write tests directly from each story's Gherkin
  scenarios — they're already in Given/When/Then form, not a paraphrase
  target. NFR stories' measurable criteria (the threshold + unit) become the
  test's assertion values directly.
- **Implementation stage**: when implementing a task, check whether it
  traces to a story (per the plan's own tracing from the planning stage
  above). If so, treat that story's Acceptance Criteria as the task's
  Definition of Done — implementation isn't complete until every criterion
  the task claims to cover is demonstrably true.

## 4 — Announce

State, in one line, whether this contract found anything:
- `"User story file consulted: <path> (<N> stories, <M> Acceptance Criteria traced)"`
- or `"No user-story file referenced — proceeding without it."`

---

This file is colocated with `spw-write-user-story/SKILL.md` — the skill that
produces the artifact this file describes how to consume — so anyone changing
one sees the other and keeps them in sync. It is referenced by a one-line
pointer from each consuming skill's `.prompt.md` shim, the same pattern
`CONSUMING-CODE-GRAPH.md`, `CONSUMING-COMPILED-GUIDELINES.md`, and
`CONSUMING-CONTEXT-PACKAGE.md` already use — the protocol is written,
reviewed, and updated in exactly one place, not duplicated into every
consuming skill's own `SKILL.md`.

This is additive alongside `CONSUMING-CONTEXT-PACKAGE.md`, `CONSUMING-CODE-GRAPH.md`,
and `CONSUMING-COMPILED-GUIDELINES.md` — when no user-story file exists for the
current feature, this contract is a no-op and the other three behave exactly
as they do today.
