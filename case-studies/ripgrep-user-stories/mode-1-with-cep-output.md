**Context package(s):** trim-prefix-whitespace_user-story_20260801@ee9c7b70

# User Stories: ripgrep `--trim`/`--no-trim` flag

Context package consulted: trim-prefix-whitespace_user-story_20260801@ee9c7b70
(approved, generated 2026-08-01; 0 addenda read, 1 addendum written)

**Feature description given:** "Add a `--trim`/`--no-trim` flag to ripgrep
that strips leading ASCII whitespace from each printed matching line, and
make sure trimming happens before `-M`/`--max-columns` truncation is
applied."

## Actors

- CLI user — invokes `rg` interactively or in a script and reads the
  printed, possibly colorized/truncated, output.
- ripgrep maintainer/contributor — owns the `trim_ascii`/`max_columns`
  interaction and its existing test coverage.

(Both roles are drawn from `context_items` summaries — `ctx_001`-`ctx_004`,
`ctx_009` imply the CLI user reading terminal output; `ctx_006` implies the
maintainer role via existing test names. Neither is a generic fallback.)

## Stories

### US-001

As a CLI user, I want ripgrep to strip leading whitespace from each printed
matching line when I pass `--trim`, so that indentation carried over from
the source file doesn't clutter my terminal output.

Grounded in: `ctx_001`, `ctx_002`, `ctx_003`, `ctx_007`

### US-002

As a CLI user, I want `--trim` to run before `-M`/`--max-columns` truncates
a line, so that my max-columns budget isn't spent displaying whitespace I
already asked to have removed.

Grounded in: `ctx_004`, `ctx_008`

### US-003

As a CLI user, I want trimmed lines to still be correctly color-highlighted
and correctly measured against `--max-columns`, so that the colorized match
span and the truncation point agree about where the line actually starts.

Grounded in: `ctx_009`

### US-004

As a ripgrep maintainer, I want the existing `trim_ascii()` /
`trim_ascii_multi_line()` / `trim_ascii_with_line_term()` and
`max_columns*()` test families to keep passing whenever either feature
changes, so regressions in the trim/max-columns interaction are caught
automatically rather than by a user report.

Grounded in: `ctx_006`

### US-005

As a CLI user, I want `--trim` to never strip the line terminator itself
(e.g. the `\r` in a CRLF-terminated line), so that line boundaries stay
intact even when I ask for prefix whitespace to be removed.

Grounded in: `ctx_005`

---

*Mode-1 run (with approved context package) for the
`ripgrep-user-stories` case study — see
[`CASE-STUDY.md`](CASE-STUDY.md) for the full comparison against Mode 2.*
