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

- Formatter config: `.clang-format` [src: .clang-format#L1-L3]
- Linter config: `CPPLINT.cfg` [src: CPPLINT.cfg#L1-L2]
- Local wrapper script: `format.sh`, which prints the resolved
  `clang-format` version before rewriting files in place
  [src: format.sh#L4-L5]
- CI re-verifies both tools on every push
  [src: .github/workflows/ci.yml#L7-L8]

Conflicting evidence: `clang-format` is invoked from two distinct
locations in this repo -- the local `format.sh` wrapper
[src: format.sh#L4] and the `fmt-check` CI job
[src: .github/workflows/ci.yml#L7] -- with no single pinned version
recorded in either place, so a contributor's local formatter run is not
guaranteed to match what CI checks. Until one location is made the single
source of truth, treat the CI job as authoritative.

## Formatting

The formatter is Google-style with a widened line length and 4-space
indent [src: .clang-format#L1-L3]. `CPPLINT.cfg` additionally caps line
length at 100 columns and disables the whitespace and include-order
categories [src: CPPLINT.cfg#L1-L2], so `clang-format` and `cpplint` agree
on the 100-column limit.

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

The `fmt-check` CI job runs `clang-format --version` and
`cpplint --version` as its own steps ahead of the `test` job
[src: .github/workflows/ci.yml#L4-L8], so formatting and lint conformance
are enforced automatically on every push rather than left to reviewer
discretion.
