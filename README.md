# Context Engineering Protocol

A set of AI-coding-agent skills that assemble a **human-approved, source-attributed context
package** — code graph + requirements + org conventions + constraints — before a generation task
runs, instead of letting the agent free-read the repo and guess.

Built for Claude Code / GitHub Copilot; adaptable to Cursor and OpenAI Codex (see
[Runtime support](#runtime-support) below).

## Why this exists

Most "give the agent context" tools stop at retrieval: chunk the repo, embed it, hand back
whatever's nearest to the prompt. That's fine for lookups. It's not enough for a change that
touches requirements, org conventions, and code at once — because nothing checks whether those
three sources actually agree, or whether the code graph they're reasoning from is still current.

This protocol's centerpiece, [`ult-context-generate`](.github/skills/ult-context-generate/SKILL.md),
runs an explicit **gap → conflict → staleness** state machine before anything gets generated:

- **Gap detection** — per requirement aspect, is it covered by code, by docs, by neither?
- **Conflict detection** — does a requirement doc contradict what the code graph shows, or do two
  org-convention sources disagree with each other?
- **Staleness detection** — was the code graph or the compiled-guidelines cache built from a commit
  that's no longer HEAD?

Unresolved conflicts block approval. The package that comes out the other side is source-attributed
(every claim traces to a file/section) and requires a human approval step before a downstream skill
consumes it — this is deliberately not a fully autonomous pipeline.

That's the difference from Cline's Memory Bank (persistent notes, no conflict/staleness checking),
Cursor's `.cursorrules` (static convention injection, no code-graph grounding), and generic
RAG-over-docs frameworks (retrieval without a gate): this protocol treats "is the context still
true" as a first-class question, not an assumption.

## Quickstart

See [`user_guides/topics/project-setup-context-engineering.md`](user_guides/topics/project-setup-context-engineering.md)
for the two paths:

- **Path A** (simple) — just compile scattered guideline sources into one conflict-checked
  `COMPILED-GUIDELINES.md` for any AI agent to read. 3 steps.
- **Path B** (full pipeline) — code graph + requirements + constraints assembled into a full
  context package, then handed to a downstream generation skill. 8 steps, using
  [`demo-consume-context`](.github/skills/demo-consume-context/SKILL.md) as a worked example of
  what "consuming" a context package looks like.

## Skills in this repo

| Skill | What it does |
|---|---|
| [`compiling-project-guidelines`](.github/skills/compiling-project-guidelines/SKILL.md) | Compile scattered guideline sources into one scope-aware `COMPILED-GUIDELINES.md` for other skills and `ult-context-generate`'s Constraints layer. |
| [`ult-codegraph`](.github/skills/ult-codegraph/SKILL.md) | Generate a codebase knowledge graph with `graphify` so other skills can query cross-file relationships before touching code. |
| [`ult-context-generate`](.github/skills/ult-context-generate/SKILL.md) | Assemble a context package (code graph, requirements, constraints, blast radius) before a downstream generation task runs — human-approved, source-attributed. |
| [`ult-repo-layout`](.github/skills/ult-repo-layout/SKILL.md) | Register, resolve, and validate where a project's path-slots actually live via `.layout-slots.yaml` markers, so relocating a slot needs zero `SKILL.md` edits. |
| [`demo-consume-context`](.github/skills/demo-consume-context/SKILL.md) | Worked example that discovers, loads, and tags a context package per `CONSUMING-CONTEXT-PACKAGE.md` — proves the produce/consume/tag loop end-to-end. |

Each skill's `SKILL.md` frontmatter carries `tier`/`origin`/`tags`/`bundle` per the Agent Skills
convention, with an explicit "Do NOT use for..." clause to keep triggering unambiguous.

## Runtime support

| Runtime | Support |
|---|---|
| Claude Code | Native — `SKILL.md` files under `.github/skills/` |
| GitHub Copilot | Thin `.prompt.md` wrappers under `.github/prompts/` (currently for `ult-context-generate`, `ult-codegraph`, `demo-consume-context`; `ult-repo-layout` and `compiling-project-guidelines` don't have wrappers yet) |
| Cursor / OpenAI Codex | Not yet adapted — planned as a generator from each `SKILL.md`'s frontmatter, not hand-authored per runtime |

## What's not yet done

Disclosed plainly rather than glossed over:

- **How-L1** (deep org-convention ingestion beyond the compiled-guidelines cache) is not
  implemented — only How-L2 (compiled guidelines) exists today.
- **Cross-file citation resolution is deferred.** The corroboration/citation-following mechanism
  only resolves single-hop, same-file references; multi-hop or cross-file citation chains aren't
  followed.
- **`graphify merge-graphs` is broken for multi-root repos.** Documented workaround: point
  `ult-codegraph` at one root at a time.
- **Codegraph validation is general-purpose, not domain-specific.** The C/C++ validation examples
  cover general constructs (e.g. `re2`, `protobuf`), not any particular embedded or telecom domain.
- **Token-cost claims for `ult-context-generate` are partly self-reported** and have not yet been
  independently measured against a real, large repo.
- **Only `ult-context-generate` has an eval file** under `evals/` with full trigger-check coverage;
  `ult-repo-layout` and `compiling-project-guidelines` don't have one yet.
- **No capability-profile / tool-restriction field** (e.g. an `allowed-tools`-style frontmatter key)
  exists yet on any skill.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

Apache License 2.0 — see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).
