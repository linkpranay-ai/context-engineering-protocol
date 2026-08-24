---
name: cep-retrofit
description: Point at an existing skill library, inventory it format-agnostically, and (with human confirmation at every step) insert pointers to CEP's existing CONSUMING-*.md contracts into the skills that should consume them. Do NOT use to write new CONSUMING-*.md contracts, validate that a retrofit works at runtime, or edit a library's own logic beyond the inserted pointer.
namespace: ult
version: 0.1.0
origin: ground-up
author: Pranay Mishra
maintainer: Pranay Mishra
adapted_from: ~
upstream_version: ~
released: 2026-08-05
tags: [developer, workflow, adoption, retrofit, consuming-contracts, cep]
bundle: utilities
tier: draft
---

# CEP Retrofit

## Overview

Every CEP consumption contract (`CONSUMING-CONTEXT-PACKAGE.md`, `CONSUMING-COMPILED-GUIDELINES.md`,
`CONSUMING-CODE-GRAPH.md`) already says it's meant to be "referenced by a one-line pointer from
each consuming skill's `SKILL.md`/`.prompt.md` rather than copied into each one." That's cheap in
principle. In practice, adding that pointer to an *existing* skill library — correctly, one skill
at a time, in a format that matches the library's own conventions — takes someone who has read
`PROTOCOL.md` and the relevant contract(s) end to end. For a library with a dozen or more skills,
that friction is real, and it sits squarely between CEP and "every retrofitted library becomes a
live adoption story for free."

This skill inventories an existing skill library — any shape, seen or unseen — asks a human which
skills should consume which contract(s), then drafts the minimal pointer insertion, previews every
change, and writes only what's confirmed. **It invents no new consumption mechanism.** It reuses
the three `CONSUMING-*.md` contracts verbatim; if a real retrofit need doesn't map to any of them,
that's a gap in CEP itself to raise separately (see "What this skill deliberately does not do").

## The one hard rule: zero hardcoded knowledge of any specific library

This skill must run identically against a library it has never seen, in a format nobody has
described to it yet, and against the author's own private skill collections. Concretely:

- No real library's name, skill name, or path fragment ever appears in this skill's own
  instructions, its helper script, or its tests — not even as "for example, in a library like...".
  Every example anywhere in this skill is a fabricated placeholder (`example-skill/`,
  `widget-reviewer/`).
- Detection heuristics are **shape-based**, never **name-based**. "Does this directory contain a
  file matching `SKILL.md`/`skill.md`" is fine; "if the file is literally named `X`" for any real
  `X` is not.
- `scripts/cep_retrofit.py` owns every heuristic that can be made deterministic (inventory,
  description extraction, recommendation *signals*, idempotency checking, insertion-point
  detection) so those rules live in one tested place, not re-derived ad hoc per run. **All ledger-
  style mechanical work goes through the script — never hand-roll a directory walk or a frontmatter
  regex inline.** See the script's own module docstring for the exact subcommand surface.

## Flow

### Step 1 — Locate the target library

Ask for a path. Run `cep_retrofit.py inventory <path>` — if it errors because the path isn't a
readable directory, say so concretely and re-ask. No default guessed silently: an unconfirmed
guess about where someone's skill library lives is worse than just asking.

### Step 2 — Inventory candidate skill units

`cep_retrofit.py inventory <path>` returns `{"units": [...], "unclaimed_dirs": [...]}` — the union
of three shape-based heuristics (skill-directory, manifest-directory, flat-file), never a single
winner, so a library mixing conventions (skill directories and flat prompt files coexisting as
real siblings — this repo's own shape) doesn't silently lose one convention's files. Conventional
generated/dependency/VCS directories are excluded by default; symlinked directories are inventoried
one level deep with their real path recorded, never followed further.

If `unclaimed_dirs` is non-empty, **show it to the human and ask** how a "skill" is delimited for
those directories — don't guess a fourth heuristic. Always show the full resulting inventory
(`units` plus any human-clarified additions) and get explicit confirmation/correction before
continuing. Never silently commit to a possibly-wrong or incomplete parse of an unfamiliar library.

### Step 3 — Summarize each candidate

For each confirmed unit, run `cep_retrofit.py describe <primary_file>` to get `{"name",
"description"}` (frontmatter field → first heading + paragraph → first non-blank line, in that
order). Present the confirmed inventory as a numbered list of name + one-line description.

### Step 4 — Ask which skills to retrofit, and with which contract(s)

Per confirmed skill, run `cep_retrofit.py recommend --description "<extracted description>"` to get
`{"code_related": bool, "task_related": bool, "matched_code_terms": [...], "matched_task_terms":
[...]}`. This is a **signal, not a decision**.

On Windows/PowerShell (or any shell, if the description hasn't been visually confirmed quote-free),
prefer `cep_retrofit.py recommend --description-file <path>` instead: write the extracted
description to a temp file and pass its path. A description containing embedded double quotes
(e.g. `asks to "review since X"`) can be silently mangled or truncated by PowerShell's argument
quoting before the script ever sees it, producing a false "neither" classification with no error —
confirmed for real against a third-party library, where two real skills' descriptions both
contained embedded quotes. `--description` and `--description-file` are mutually exclusive. Turn it into a recommendation grounded directly in
each contract's own stated trigger, since `CONSUMING-COMPILED-GUIDELINES.md` and
`CONSUMING-CODE-GRAPH.md` open with the identical literal sentence about their own scope (they are
not mutually exclusive with each other):

- `code_related: true` → recommend **both** `CONSUMING-COMPILED-GUIDELINES.md` and
  `CONSUMING-CODE-GRAPH.md`.
- `task_related: true` → recommend `CONSUMING-CONTEXT-PACKAGE.md`.
- Neither true → present all three with no default recommendation; let the human choose freely,
  including "none."

Either way it's **recommendation only** — the human picks the final answer per skill: accept,
override, add/drop contracts, or none. Most substantive dev-facing skills will end up with two or
three recommended contracts at once; that's expected, not a bug in the heuristic. This mirrors
trip-wire's own tier-is-a-recommendation-never-an-autoapply pattern (`PROTOCOL.md` §7): the
matching step is deterministic and mechanical, the judgment call stays human.

### Step 5 — Resolve where CEP itself lives relative to the target library

The pointer written into each retrofitted file needs a real, resolvable reference, and its shape
depends on the answer — ask, don't assume. **v1 scope is deliberately narrow**, to the two cases
with real precedent elsewhere in this repo's own conventions:

- **Same repo** as the target library → a relative path.
- **Installed as a plugin** (mirrors the `claude-plugin/` manifest convention already shipped here)
  → the plugin-qualified reference (`/context-engineering-protocol:ult-context-generate` style).

For a target library that vendors CEP at a subpath, or references it from an entirely separate
location with no vendoring — ask for a stable reference the human is confident will keep resolving;
if none exists yet, say so and **skip that skill** rather than write a pointer already known to be
dead on arrival. Cross-repo referencing into a `CONSUMING-*.md` contract isn't something
`PROTOCOL.md` itself defines today for that harder case — treat it as a real open protocol question
worth raising on its own, not something to quietly settle here.

### Step 6 — Draft the insertion, per confirmed skill

Combine every contract confirmed for a given skill in Step 4 into one pass, not one pass per
contract:

1. **Idempotency check first, by contract identity**: run `cep_retrofit.py check-pointer <file>
   --contracts <comma-separated contract filenames>`. It matches on the bare contract filename
   appearing anywhere in the text — a same-repo relative path today and a plugin-qualified
   reference tomorrow both count as "already has this pointer," so a later re-run under a
   different reference shape doesn't duplicate it. Already present for a given contract → report
   "already retrofitted for `<contract>`," drop just that contract from this file's draft; any
   other newly-confirmed contract not yet present still proceeds.
2. **Find the insertion point**: run `cep_retrofit.py find-insertion-point <file>`. It checks, in
   order, an existing See Also/References/Related section, the end of YAML frontmatter, a heading
   that reads as overview/process content, then a "prepend near the top" fallback — always
   returning a method (`find-insertion-point` never declines outright), but the calling skill is
   still free to skip a file entirely if, for example, every confirmed contract for it is already
   idempotency-satisfied and nothing remains to insert.
3. **Draft the text**: a sentence or two per remaining contract plus the resolved path from Step 5
   — not a copy of the contract's own content, matching the "referenced by pointer, not copied"
   principle the contracts already state about themselves. Write it to blend with the target
   file's own existing voice and structure, not CEP's — this skill is a guest in someone else's
   library.
4. If a given skill has multiple remaining contracts, insert them together as **one combined
   block at one insertion point**, in a fixed stable order (`CONSUMING-CONTEXT-PACKAGE.md`, then
   `CONSUMING-COMPILED-GUIDELINES.md`, then `CONSUMING-CODE-GRAPH.md`) — never as separate passes
   that could each compute a different insertion point and scatter pointers through the file.

### Step 7 — Preview before writing

Show every drafted change as a diff, batched, before anything touches disk. Nothing is written
until explicit confirmation. Human confirms per-file or in one batch, their choice.

### Step 8 — Write confirmed changes, report a summary

Write only what was confirmed. Report: N retrofitted, M skipped (no confident insertion point /
already retrofitted / declined by the human), and per-file which contract(s) each got. A write
failure on one file is reported for that file and does not abort the rest of the batch.

### Step 9 — Explicit non-actions

Doesn't commit, doesn't open a PR, doesn't validate that a retrofitted skill actually behaves
correctly with CEP at runtime (that's the target skill's own subsequent real usage). If the target
library is one the human doesn't own or maintain — a third-party collection without write access —
that's a real possible misuse: flag it once, before Step 7's write, as a caution rather than a
block.

## What this skill deliberately does not do

- **It never invents a new consumption mechanism.** It reuses `CONSUMING-CONTEXT-PACKAGE.md`,
  `CONSUMING-COMPILED-GUIDELINES.md`, and `CONSUMING-CODE-GRAPH.md` verbatim. If a retrofit need
  genuinely doesn't map to any of the three — trip-wire's own `institutional_memory_hits[]` field
  is a known live example: `CONSUMING-CONTEXT-PACKAGE.md`'s current field list doesn't instruct a
  consuming skill to read it yet, even though it rides inside the same package — that's a real gap
  in CEP itself, worth a separate explicit pass to close (either by extending
  `CONSUMING-CONTEXT-PACKAGE.md`'s own field list, or by writing a dedicated
  `CONSUMING-DECISION-LEDGER.md`), not something this skill should paper over with bespoke logic.
- **It never auto-applies a recommendation.** Every inventory item, every contract match, every
  insertion point, and every write is human-confirmed. `recommend`'s output is a signal, never a
  selection.
- **It is not a validator.** It doesn't check that a retrofit "worked" — that's the retrofitted
  skill's own subsequent real usage and test suite.
- **It is not a general-purpose file-refactoring or codemod tool**, and it doesn't lint or judge
  the target library's own conventions or quality beyond what's needed to place a pointer.
- **It doesn't touch the target library's version control.** Reads and writes plain files only —
  the human's own VCS workflow handles commits, same as every other skill in this repo.

## When something doesn't fit the flow

If `unclaimed_dirs` from Step 2 turns out to be most of the library — a format this skill's three
heuristics genuinely don't fit — say so plainly rather than forcing a match. Ask the human to
describe their own convention once, apply it consistently for the rest of that run, and note in
the Step 8 summary that this run used a human-supplied convention rather than the built-in
heuristics, so a future re-run (which won't remember that conversation) is warned to ask again
rather than silently guess.

If Step 5's reference resolution turns up a case this skill's v1 scope doesn't cover (CEP vendored
at a subpath, or living in an entirely separate, unvendored location), don't invent a resolution —
skip the affected skill(s), report why, and treat it as a real open protocol question rather than
something this skill quietly settles on its own.
