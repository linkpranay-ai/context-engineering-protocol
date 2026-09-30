# Evidence probes

One checklist per document kind, keyed by the packet's `kind` field. A
worker filling a `grounded` (or `augmented`) document reads this file for
its packet's kind before writing anything, and uses it in this order:

1. **`must_cite` first.** Every path in the packet's `must_cite` list is
   evidence the orchestrator's probe already found and pinned to this
   packet; read those files before anything below and cite every one of
   them somewhere in the document (`mark-*` rejects a doc that doesn't).
2. **`evidence_hints` next**, when populated — `top_symbols_by_in_degree`,
   `depends_on`, `depended_on_by`, and `call_sites` are graph facts the
   orchestrator already computed once; use them instead of re-deriving
   the same graph traversal per worker. `call_sites` is populated by
   `list-interfaces --with-sites` where that's been run; when it's empty,
   fall back to inspecting the module's own imports/call expressions
   directly.
3. **This file's per-kind checklist last**, in the order listed, until
   the packet's soft `read_budget` is spent. The checklist tells you
   *what kind of signal to look for*, never a fixed file name — every
   probe below is a pattern to search a repo for, not an assumption
   about which language, framework, or project this run's repo is.

This file is generic on purpose: it must work unmodified against any
codebase CEP is pointed at — a C++ project, a Python service, a
JavaScript monorepo, or a project mixing several languages — never a
single worked example baked into the skill. Every table row below names
a *class* of file (a build manifest, a lint config, a CI workflow) with
representative examples across languages, not a specific project's
layout.

## Reporting rules (apply to every kind and every section)

- **Cite what you use.** `[src: path#Lx-Ly]` for every claim that came
  from a specific file and line range. A claim with no citation is
  indistinguishable from a guess and `mark-*` treats prose without one as
  ungrounded.
- **Report absence honestly**, in the section itself, not by leaving the
  section empty: `Not evidenced. Searched: <signal 1>, <signal 2> ...
  (absent).` List the actual signals you looked for. `mark-*` re-checks
  that every path named in a `Searched:` line really is absent from the
  repo, so naming a signal you didn't actually check is worse than
  naming fewer.
- **Report conflicts explicitly.** When two pieces of evidence disagree
  (two config files pin different tool versions, a CI workflow runs a
  different command than the one documented in a contributing guide),
  write a dedicated line: `Conflicting evidence: <claim A> [src: ...] vs.
  <claim B> [src: ...].` Don't silently pick one side — the validator's
  conflict check exists precisely to catch a doc that cites evidence but
  states something that evidence doesn't actually agree on (Sec 6,
  "Conflicts").
- **Never infer from convention alone.** A module's name or a language's
  usual idiom is not evidence. If the only thing pointing at a claim is
  "projects like this usually do X," that's a gap, not a fact — write
  the honest `TBD` / `Not evidenced` line instead.
- **A `grounded` section still needs every heading present.** Skipping a
  required section entirely is a hard validator failure; an honest gap
  line under a present heading is not.

---

## `context_md`

Required sections: Purpose, Inputs, Outputs, Key abstractions,
Dependencies, Design invariants, Gotchas (State machine only if this
module actually has one). Tier governs which of these stay — see
`module-context-depth-by-tier.md` — but the probes below apply to
whichever sections a given tier keeps.

| Section | Look for | Evidence hint field |
|---|---|---|
| Purpose | The module's entry point(s): a `main`/`__main__`, an exported top-level class or function with a docstring/doc comment, a README or module-level comment inside the module's own directory. | `must_cite` (the module's own highest-in-degree files) |
| Inputs | Function/method parameters on the module's public surface, config keys it reads (env vars, a config-file section scoped to this module), messages/events it subscribes to or consumes. | `top_symbols_by_in_degree` |
| Outputs | Return types/values of the module's public functions, files or side channels it writes to, events/messages it publishes. | `top_symbols_by_in_degree` |
| Key abstractions | The types/classes/functions with the most incoming references *within this module* — not just the most lines of code. | `top_symbols_by_in_degree` |
| Dependencies | Import/include statements naming another module in this repo; the graph's own `depends_on`/`depended_on_by` edges for this module. | `depends_on`, `depended_on_by` |
| Design invariants | A guard clause, an assertion, a type constraint, a comment stating a precondition the code enforces — not a general best practice the code doesn't visibly enforce. | (direct source read) |
| Gotchas | A code comment flagging a workaround, an unusual pattern, a known limitation — something concrete, never a generic warning that could apply to any module. | (direct source read) |
| State machine (if applicable) | An explicit enum/state field plus the transitions the code actually implements between its values. Delete the section if the module has none. | (direct source read) |

## `coding_standards`

Required sections: Detected tooling, Formatting, Naming conventions,
Error handling, Logging, Review expectations.

| Signal class | Representative files (any language) | What it evidences |
|---|---|---|
| Formatter config | `.clang-format`, `pyproject.toml` `[tool.black]`/`[tool.ruff.format]`, `.prettierrc*`, `rustfmt.toml`, `.editorconfig` | Formatting section |
| Linter config | `CPPLINT.cfg`, `.clang-tidy`, `.eslintrc*`, `.flake8`, `pyproject.toml` `[tool.ruff]`/`[tool.mypy]`, `.golangci.yml`, `checkstyle.xml` | Formatting / Naming conventions section |
| Wrapper/tooling scripts | A repo-root script that invokes the formatter/linter (e.g. `format.sh`, `lint.sh`, a `Makefile` target, an `npm`/`package.json` script) | Formatting section — confirms the config is actually run, not just present |
| Test/build config that also gates style | `CMakeLists.txt` (a lint/format custom target), `tox.ini`, `noxfile.py`, `package.json` `scripts` | Formatting / Review expectations |
| CI workflow | `.github/workflows/*.yml`, `.gitlab-ci.yml`, `Jenkinsfile`, `azure-pipelines.yml` | Confirms formatting/linting/review checks are enforced, not just documented |
| Contribution docs | `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, a docs-site style guide | Naming conventions, Review expectations — and a common source of the version-pin conflicts below |

- **Detected tooling**: one row per signal actually found; never list a
  tool this repo doesn't use.
- **Formatting — tool-version cross-check.** Where a tool's version is
  pinned in more than one place (a wrapper script's shebang/version
  check, a CI workflow's install step, a version constraint stated in
  `CONTRIBUTING.md` or a lockfile), compare them. If they agree, cite
  all of them. If they disagree, this is exactly the conflict this
  checklist's reporting rules require a `Conflicting evidence:` line
  for — never silently prefer one source.
- **Error handling / Logging**: look for a project-wide exception
  hierarchy, a designated logging library/wrapper, or a documented
  convention (a section in `CONTRIBUTING.md`, a linter rule that
  forbids bare `except`/silent failure). Absent either, use the honest
  gap line — do not state a language's generic idiom as this project's
  convention.
- **Review expectations**: a CODEOWNERS file, a PR template
  (`.github/PULL_REQUEST_TEMPLATE.md`), or a stated review-count/approval
  rule in `CONTRIBUTING.md`.

## `testing_guidelines`

Required sections: Detected tooling, Test layout, Structure, Coverage
expectations, Naming convention.

| Signal class | Representative files (any language) | What it evidences |
|---|---|---|
| Test runner config | `pytest.ini`, `pyproject.toml` `[tool.pytest.ini_options]`, `tox.ini` `[pytest]`, `jest.config.*`, `vitest.config.*`, `CTestConfig.cmake`, `CMakeLists.txt` `enable_testing()`, `Cargo.toml` `[dev-dependencies]`, `build.gradle`/`pom.xml` + a JUnit dependency | Detected tooling |
| Test file convention | Files matching `*_test.*`, `test_*.*`, `*.spec.*`, or a dedicated `tests/`/`__tests__/`/`test/` directory actually present in this repo | Test layout |
| Coverage config | `.coveragerc`, `pyproject.toml` `[tool.coverage.*]`, a CI step invoking a coverage tool, a stated coverage threshold | Coverage expectations |
| CI invocation | The actual test command a CI workflow runs — this is authoritative even when no dedicated config file exists (e.g. a bare `pytest` or `ctest` invocation in a workflow step) | Detected tooling, Test layout |

- **Test layout**: report the real directory/naming pattern this repo
  uses, never a generic default a given language's ecosystem usually
  prefers.
- **Structure**: only claim a setup/exercise/assert (or equivalent)
  convention if you can point at more than one actual test file
  following it — one example is an anecdote, not a convention.
- **Coverage expectations / Naming convention**: honest gap line if no
  config or consistent pattern evidences an answer.

## `interface_boundary`

Required sections: Relations observed, Contract, Versioning /
deprecation policy, Owners.

| Section | Look for | Evidence hint field |
|---|---|---|
| Relations observed | The interface entry's own `relations` (dependency-edge kinds: imports, imports_from, calls) and `weight` (qualifying-edge count), taken verbatim — never re-derived by hand. | (interface entry, from `list-interfaces`) |
| Contract | The actual import/include statement or call expression connecting the two modules — a header inclusion, a function call, a message schema shared between them. Prefer `evidence_hints.call_sites` when `list-interfaces --with-sites` has populated it; otherwise inspect each module's own source for the concrete call/import site. | `call_sites` |
| Versioning / deprecation policy | A CODEOWNERS/MAINTAINERS file, an explicit deprecation marker or version-compat comment near the interface's definition. | (direct source read) |
| Owners | A CODEOWNERS/MAINTAINERS file naming either module's path. | (direct source read) |

A dependency-graph edge proves the two modules are *coupled*; it never
proves *how*. Do not infer a contract's shape from either module's name
or from a language/framework's usual convention — every field this
checklist can't evidence from an actual import, call site, or ownership
file stays `TBD — fill in`, exactly as `generate-interface-docs.md`
already instructs.

## `architecture_overview`

Required sections: Overview, Components, Component interactions,
Primary data/control flows, External interfaces (delete if the project
exposes none), Key design decisions, Known constraints and invariants.

| Section | Look for |
|---|---|
| Overview | A repo-root README's own description, a package manifest's `description` field, or the entry point's own top-level doc comment. |
| Components | The repo's actual top-level module/package directories, each with the role you can state from its own `CONTEXT.md` (if generated) or its own entry-point file — one row per component genuinely present, never a boilerplate list of common component types. |
| Component interactions | Only an edge you can evidence from an import, a call, or a message — the code graph's `depends_on`/`depended_on_by` edges, when graph-mode is active for this run, are the authoritative source. |
| Primary data/control flows | The path from an actual entry point (a `main`, an HTTP route table, a CLI command dispatcher) to where it ultimately hands off, traced through real calls. |
| External interfaces | An actual exposed/consumed HTTP route table, message-queue topic, RPC service definition, or documented file format — delete the section if none is evidenced. |
| Key design decisions | Only a decision the code or its comments actually evidence (a chosen concurrency model, a chosen storage engine, a documented tradeoff) — never a generic "best practice" claim. |
| Known constraints and invariants | A guard clause, an assertion, or a documented limit the code visibly enforces. |

## `requirements_overview`

Required sections: Overview, Functional requirements observed,
Constraints observed, Open questions.

| Section | Look for |
|---|---|
| Overview | Same sources as `architecture_overview`'s Overview probe. |
| Functional requirements observed | An actual entry point, API route, CLI command, or a documented feature you can point at directly — never a requirement the codebase doesn't actually implement. |
| Constraints observed | A performance budget or resource limit in a config file, a supported-platform/version list, a compatibility requirement stated in existing docs. |
| Open questions | A genuine gap a human needs to resolve — reserved for places the available evidence is actually unclear, not a hedge repeated on every line. |

This kind defaults to `skeleton` mode (Sec 4.2) precisely because a
"grounded" requirements doc, written from the same code a What-L3 graph
already describes, tends to just restate that graph back at itself
rather than add anything (the proposal's own case-study finding, Sec
4.2). When `grounded` mode is explicitly requested for this kind
anyway, the same reporting rules above still apply in full.
