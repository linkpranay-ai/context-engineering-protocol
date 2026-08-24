# Generating `TESTING-GUIDELINES.md`

Read by Step 5c when the user opts in and
`<how_l2_path>/TESTING-GUIDELINES.md` doesn't already exist.

## 1. Detect what's actually configured

Look for a test-framework or test-runner config already present — don't
ask the user to restate what a config file already states. Check for
(whichever apply):

| Signal file(s) | What it tells you |
|---|---|
| `pytest.ini`, `pyproject.toml` `[tool.pytest.ini_options]`, `tox.ini` `[pytest]` | Python via pytest |
| `jest.config.*`, `vitest.config.*` | JS/TS via Jest or Vitest |
| `*_test.go` convention + `go.mod` | Go's built-in `testing` package |
| `build.gradle`/`pom.xml` + a `junit`/`JUnit` dependency | JVM via JUnit |
| `Cargo.toml` `[dev-dependencies]` with a test crate, or bare `#[test]` usage | Rust's built-in test harness |
| `CTestConfig.cmake`, `CMakeLists.txt` `enable_testing()` | C/C++ via CTest |
| CI config (`.github/workflows/*.yml`, etc.) running a test command | The actual invoked command, even if no dedicated config file exists |

For each one found, name it and note where tests actually live in this
repo (the real directory/naming pattern you can observe — e.g. `tests/`,
`*_test.go` beside the source file, `__tests__/`) — don't guess a layout
the repo doesn't use.

## 2. Fill the template

Open `templates/testing-guidelines-template.md` and fill it in:

- **Detected tooling section**: the table from step 1, only the rows that
  actually matched something in this repo.
- **Everything else**: same "TBD when genuinely unknown" rule as Step 5 —
  a coverage threshold, naming convention, or mocking policy that isn't
  evidenced by a config file or a consistent pattern across the repo's
  actual test files gets `TBD — fill in`, not an invented number.

## 3. Write and record

Write the filled template to `<how_l2_path>/TESTING-GUIDELINES.md`. Then:

- **Wrote it:** `scaffold_state.py mark-repo-doc-generated <state.json>
  testing_guidelines --output <path>`.
- **User declined in Step 5c:** `scaffold_state.py mark-repo-doc-skipped
  <state.json> testing_guidelines --reason <text>`.
