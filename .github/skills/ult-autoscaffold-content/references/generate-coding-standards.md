# Generating `CODING-STANDARDS.md`

Read by Step 5c when the user opts in and
`<how_l2_path>/CODING-STANDARDS.md` doesn't already exist.

## 1. Detect what's actually configured

Look for language/lint/format config already present in the repo — don't
ask the user to restate what a config file already states. Check for
(whichever apply; most repos have zero or one per language):

| Signal file(s) | What it tells you |
|---|---|
| `.eslintrc*`, `.prettierrc*` | JS/TS lint + format rules |
| `pyproject.toml` `[tool.ruff]` / `[tool.black]` / `[tool.mypy]`, `.flake8`, `setup.cfg` `[flake8]` | Python lint/format/type-check rules |
| `.clang-format`, `.clang-tidy` | C/C++ format + lint rules |
| `.editorconfig` | Cross-language whitespace/charset baseline |
| `rustfmt.toml`, `.rustfmt.toml` | Rust format rules |
| `.golangci.yml`, `gofmt` (implicit — Go always has one) | Go lint/format |
| `checkstyle.xml`, `.editorconfig` under a Java/Kotlin root | JVM style rules |

For each one found, name it and summarize its enforced rules in one line —
don't paste the whole config, and don't restate a rule the file doesn't
actually set.

## 2. Fill the template

Open `templates/coding-standards-template.md` and fill it in:

- **Detected tooling section**: the table from step 1, only the rows that
  actually matched something in this repo.
- **Everything else**: same "TBD when genuinely unknown" rule the rest of
  this skill follows (see `SKILL.md` Step 5) — a project convention that
  isn't evidenced by a config file or by consistent patterns you can point
  to in the actual codebase gets `TBD — fill in`, not a plausible-sounding
  invented rule. Do not invent naming conventions, review-gate policy, or
  security-review triggers that no file in the repo states.

## 3. Write and record

Write the filled template to `<how_l2_path>/CODING-STANDARDS.md`. Then:

- **Wrote it:** `scaffold_state.py mark-repo-doc-generated <state.json>
  coding_standards --output <path>`.
- **User declined in Step 5c:** `scaffold_state.py mark-repo-doc-skipped
  <state.json> coding_standards --reason <text>`.
