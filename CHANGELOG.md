# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project uses simple `MAJOR.MINOR.PATCH`
versioning without a formal SemVer API-compatibility guarantee yet (see [`ROADMAP.md`](ROADMAP.md)).

## [0.1.0]

Initial public release.

### Added

- **`ult-context-generate`**: the protocol's centerpiece skill — assembles a human-approved,
  source-attributed context package (code graph + requirements + org conventions + constraints)
  before a downstream generation task runs, gated on an explicit gap → conflict → staleness
  state machine per feature aspect.
- **`ult-codegraph`**: generates a codebase knowledge graph (`graphify`) so other skills can
  query cross-file relationships before touching code — the What-L3 layer.
- **`compiling-project-guidelines`**: compiles scattered guideline sources into one scope-aware
  `COMPILED-GUIDELINES.md`, feeding the How-L2 layer and any code-facing skill directly.
- **`ult-repo-layout`**: registers, resolves, and validates path-slots via `.layout-slots.yaml`
  markers, so relocating a project's conventional folders needs zero `SKILL.md` edits.
- **`demo-consume-context`**: a from-scratch worked example proving the produce/consume/tag loop
  end to end — discovers, loads, spot-checks, cites, and tags an approved context package per
  `CONSUMING-CONTEXT-PACKAGE.md`.
- **What-L1 (piloting)**: deterministic, zero-LLM structural indexing of external `.md`
  references (`md_index.py` — "the graphify for markdown") with bundled `generic`/`3gpp` pattern
  profiles, triggered as a gated fallback only for aspects with no What-L2/What-L3 coverage.
- **Cross-runtime adapters**, generated (never hand-duplicated) from each skill's `SKILL.md` by
  `catalog/export_adapters.py`: `.prompt.md` wrappers for GitHub Copilot, `.mdc` rules for
  Cursor, and an `AGENTS.md` table for OpenAI Codex.
- **Quality gates as OSS infra**: CI workflow, pytest coverage across skill scripts and the
  adapter generator, `--check` drift detection for generated adapter files.
- **Dogfood validation (Phase 9)**: all four real skills run end-to-end, by hand, against a
  freshly cloned, unrelated real-world repo (`Textualize/textual`) — not just read for
  correctness. Claude Code and GitHub Copilot are field-validated with real transcripts; Codex is
  field-validated via Codex Desktop (with one disclosed, unrelated VS Code extension caveat). See
  [`README.md` "Runtime support"](README.md#runtime-support) for details.
- **`PROTOCOL.md`**: the full layer model, gap/conflict/staleness state machine (with diagrams),
  human-approval gate, and How-L1's specified-but-not-yet-built design.
- **`user_guides/topics/consuming-a-context-package.md`**: a plain-language, 10-minute on-ramp
  for building a skill that consumes an approved context package.
- **`examples/telecom-what-l1-demo/`**: a worked, hand-run example of the What-L1 mechanism
  against a synthetic (clearly labeled, non-copyrighted) 3GPP-style spec fixture.
- **`ROADMAP.md`**: prioritized list of what's next — installer, How-L1 implementation,
  cross-file citation resolution, and more.

### Known limitations (disclosed, not regressions)

- How-L1 (org-wide process-standard ingestion) is specified but not implemented.
- Cross-file citation resolution is single-hop/same-file only.
- `graphify merge-graphs` is broken for multi-root repos (documented workaround: one root at a
  time).
- No installer script exists yet — setup today is manual file copying.
- Cursor's adapter is generated and doc-verified but not field-tested against a live install.

See [`README.md` "What's not yet done"](README.md#whats-not-yet-done) and
[`ROADMAP.md`](ROADMAP.md) for the full, current disclosure.
