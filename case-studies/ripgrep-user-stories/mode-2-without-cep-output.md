# User Stories: ripgrep `--trim`/`--no-trim` flag

No context package found — proceeding without it.

**Feature description given:** "Add a `--trim`/`--no-trim` flag to ripgrep
that strips leading ASCII whitespace from each printed matching line, and
make sure trimming happens before `-M`/`--max-columns` truncation is
applied."

## Actors

No specific actor named or implied in the bare feature description — using
generic actors:

- User
- Developer

## Stories

### US-001

As a User, I want to strip leading whitespace from each printed matching
line using a `--trim` flag, so that my search output looks cleaner.

Grounded in: bare feature description (no context package available)

### US-002

As a User, I want to disable trimming with `--no-trim`, so that I can see
the original whitespace when I need it.

Grounded in: bare feature description (no context package available)

### US-003

As a Developer, I want `--trim` to always run before `-M`/`--max-columns`
truncates the line, so that the max-columns limit isn't spent displaying
whitespace that was supposed to be removed already.

Grounded in: bare feature description (no context package available)

---

*Mode-2 run (bare ask, no context package) for the
`ripgrep-user-stories` case study — see
[`CASE-STUDY.md`](CASE-STUDY.md) for the full comparison against Mode 1.*
