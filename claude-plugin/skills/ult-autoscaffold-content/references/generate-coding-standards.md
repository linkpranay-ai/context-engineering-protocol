# Generating `CODING-STANDARDS.md`

Read by Step 5c when the user opts in and
`<how_l2_path>/CODING-STANDARDS.md` doesn't already exist.

## 1. Detect what's actually configured

Evidence gathering for this kind is governed by
`references/evidence-probes.md#coding_standards` — that file holds the
full signal table (formatter/linter/wrapper-script/CI/contribution-doc
classes, with representative file names across languages), the
tool-version cross-check step, and the exact `[src: path#Lx-Ly]` /
`Not evidenced. Searched: ... (absent).` reporting format every section
must use. Read it before probing; this step doesn't repeat that table.

If the packet driving this generation carries `must_cite` and
`evidence_hints`, read those first — the orchestrator already probed the
repo once; don't re-derive the same signals independently.

## 2. Fill the template

Open `templates/coding-standards-template.md` and fill it in, following
that template's own per-section evidence comments (each one points back
at the matching `evidence-probes.md#coding_standards` row):

- **Detected tooling section**: one row per signal actually found, using
  `evidence-probes.md`'s signal-class table — never list a tool this repo
  doesn't use.
- **Formatting**: if this run found more than one source pinning a tool's
  version and they disagree, the section needs a `Conflicting evidence:`
  line (`mark-*` checks for one whenever the probe finds a tool discussed
  from more than one distinct source file) — see the template's own
  comment for the exact wording.
- **Everything else**: same "TBD when genuinely unknown" rule the rest of
  this skill follows (see `SKILL.md` Step 5) — a project convention that
  isn't evidenced by a config file or by consistent patterns you can point
  to in the actual codebase gets the honest gap line, not a
  plausible-sounding invented rule. Do not invent naming conventions,
  review-gate policy, or security-review triggers that no file in the
  repo states.

## 3. Write and record

Write the filled template to `<how_l2_path>/CODING-STANDARDS.md`. Then:

- **Wrote it:** `scaffold_state.py mark-repo-doc-generated <state.json>
  coding_standards --output <path>`.
- **User declined in Step 5c:** `scaffold_state.py mark-repo-doc-skipped
  <state.json> coding_standards --reason <text>`.
