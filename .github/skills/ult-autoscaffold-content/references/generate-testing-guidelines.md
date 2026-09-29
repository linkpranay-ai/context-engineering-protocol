# Generating `TESTING-GUIDELINES.md`

Read by Step 5c when the user opts in and
`<how_l2_path>/TESTING-GUIDELINES.md` doesn't already exist.

## 1. Detect what's actually configured

Evidence gathering for this kind is governed by
`references/evidence-probes.md#testing_guidelines` — that file holds the
full signal table (test-runner config, test-file convention, coverage
config, and CI-invocation classes across languages) and the exact
`[src: path#Lx-Ly]` / `Not evidenced. Searched: ... (absent).` reporting
format every section must use. Read it before probing; this step doesn't
repeat that table.

If the packet driving this generation carries `must_cite` and
`evidence_hints`, read those first — the orchestrator already probed the
repo once; don't re-derive the same signals independently.

Report the real directory/naming pattern this repo actually uses for its
tests — never a generic default a given language's ecosystem usually
prefers.

## 2. Fill the template

Open `templates/testing-guidelines-template.md` and fill it in, following
that template's own per-section evidence comments (each one points back
at the matching `evidence-probes.md#testing_guidelines` row):

- **Detected tooling section**: one row per signal actually found, using
  `evidence-probes.md`'s signal-class table — never list a framework this
  repo doesn't use.
- **Everything else**: same "TBD when genuinely unknown" rule as Step 5 —
  a coverage threshold, naming convention, or mocking policy that isn't
  evidenced by a config file or a consistent pattern across the repo's
  actual test files gets the honest gap line, not an invented number.

## 3. Write and record

Write the filled template to `<how_l2_path>/TESTING-GUIDELINES.md`. Then:

- **Wrote it:** `scaffold_state.py mark-repo-doc-generated <state.json>
  testing_guidelines --output <path>`.
- **User declined in Step 5c:** `scaffold_state.py mark-repo-doc-skipped
  <state.json> testing_guidelines --reason <text>`.
