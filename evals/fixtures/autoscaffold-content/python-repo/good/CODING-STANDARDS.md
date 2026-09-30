---
generated_by: ult-autoscaffold-content
generated_at: 2026-09-29T00:00:00Z
status: draft
content_mode: grounded
doc_kind: coding_standards
skill_version: fixture-v1
---

## Detected tooling

This repo pins a formatter and a linter and checks both in CI.

- Formatter config: `.style.yapf`, PEP8-based with a widened line length
  [src: .style.yapf#L1-L3]
- Linter config: `ruff.toml` [src: ruff.toml#L1-L4]
- Local wrapper script: `lint.sh`, which prints the resolved `ruff`
  version before running the lint check [src: lint.sh#L4-L5]
- CI re-verifies both tools on every push
  [src: .github/workflows/ci.yml#L7-L8]

Conflicting evidence: `ruff` is invoked from two distinct locations in
this repo -- the local `lint.sh` wrapper [src: lint.sh#L4] and the
`lint-check` CI job [src: .github/workflows/ci.yml#L8] -- with no single
pinned version recorded in either place, so a contributor's local lint
run is not guaranteed to match what CI checks. Until one location is
made the single source of truth, treat the CI job as authoritative.

## Formatting

The formatter is PEP8-based with the line length widened to 100 columns
[src: .style.yapf#L1-L3]. `ruff.toml` independently caps line length at
100 columns as well [src: ruff.toml#L1-L1], so the formatter and linter
agree on the 100-column limit.

## Naming conventions

Not evidenced. Searched: a style guide document, naming convention
comments in the tool configs (absent).

## Error handling

Not evidenced. Searched: an error-handling policy document, exception
usage conventions in the tool configs (absent).

## Logging

Not evidenced. Searched: a logging policy document, logging library
pin in the tool configs (absent).

## Review expectations

The `lint-check` CI job runs `yapf --version` and `ruff --version` as
its own steps ahead of the `test` job
[src: .github/workflows/ci.yml#L4-L9], so formatting and lint conformance
are enforced automatically on every push rather than left to reviewer
discretion.
