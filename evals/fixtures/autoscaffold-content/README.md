# AutoScaffold Content golden fixtures

Two small, fully synthetic repos used to pin down `ult-autoscaffold-content`'s
`scan` / `plan` / `probe-size` / `validate` behavior against real (not
hand-typed) tool output, plus a hand-authored good/bad `CODING-STANDARDS.md`
pair per repo that exercises the validator's floors, `must_cite`, and the
tool-version conflict check end to end.

**These fixtures are intentionally repo-agnostic.** Neither one models any
particular real-world project's file layout, module names, or tooling
choices — `cpp-repo` and `python-repo` are synthetic two-module repos
built only to exercise this skill's own tiering/probe/validator logic.
`ult-autoscaffold-content` works against any code repository; nothing here
should be read as assuming a specific one.

## Layout

Each `<lang>-repo/` fixture has the same shape:

```
<lang>-repo/
  repo/                    <- the actual --repo-root passed to every CLI call
  graph.json               <- graphify-shaped dependency graph, sibling of repo/
  expected/                <- captured output from real CLI runs (see below)
    TRIAGE-STATE.json         <- scan's output state file
    scan-output.json          <- scan's stdout summary (python-repo only)
    plan-output.json          <- plan's stdout summary ({"packets_written": N, ...})
    probe-size-output.json    <- probe-size's stdout
    packets/*.json            <- the actual work-packet files plan wrote
  good/CODING-STANDARDS.md <- hand-authored doc that passes ss.validate()
  bad/CODING-STANDARDS.md  <- hand-authored doc that fails ss.validate()
```

`repo/` is deliberately its own subdirectory, not the fixture root itself.
`scan()` treats every top-level directory under `--repo-root` as a
candidate module, so if `expected/`, `good/`, and `bad/` sat directly
inside `<lang>-repo/` alongside the real source, they'd be misdetected as
extra "modules" and trip `scan`'s `graph_module_overlap_warning`. Keeping
the scanned tree under its own `repo/` subdirectory (siblings: `graph.json`,
`expected/`, `good/`, `bad/`) avoids that entirely. Any new fixture added
here should follow the same shape.

`expected/*.json` is not hand-typed — every file in `expected/` was
produced by actually running the CLI below against this fixture and
capturing its real output. Re-running the same commands against an
unmodified fixture should reproduce byte-identical JSON, with one
deliberate exception: each packet's `head_commit` field records the
*live* git HEAD of whatever repo the fixture happens to be checked out
inside (`_git_head_commit()` walks up from `--repo-root` looking for a
`.git` directory) — it is expected to differ from the captured value as
soon as this repo gets new commits, and it is not part of the fixture's
own stability contract. Ignore that one field when diffing a fresh run
against `expected/`; every other field should match exactly.

## cpp-repo

Two modules: `alpha/` (tier 3 — a leaf, `Widget::compute` has no
dependents) and `beta/` (tier 2 — `Helper::run`, depended on by `alpha`).
`alpha` calls into `beta` across an `interface_boundary`.

Top-level tool config: `.clang-format` (formatter), `CPPLINT.cfg`
(linter), `format.sh` (wrapper script, cites `clang-format --version`),
`CMakeLists.txt` (contains `enable_testing()`), `.github/workflows/ci.yml`
(CI, also cites `clang-format --version` and `cpplint --version`).

`clang-format` is cited from two distinct sources (`format.sh` and
`.github/workflows/ci.yml`) — this is what forces `good/CODING-STANDARDS.md`
to include a literal `Conflicting evidence:` line to pass. `cpplint` has
only one citing source (`.github/workflows/ci.yml`) and must **not**
itself require a conflict line — this fixture is what
`test_coding_standards_single_source_tool_does_not_require_its_own_conflict_line`-style
precision tests are meant to catch a regression against.

## python-repo

Structurally identical to `cpp-repo`, renamed: `app/` (tier 3, leaf
`Runner.execute`) and `utils/` (tier 2, `Helper.run`, depended on by
`app`). Top-level tool config: `.style.yapf` (formatter), `ruff.toml`
(linter), `lint.sh` (wrapper script), `pytest.ini` (test_config, detected
by filename alone — no `tool_versions` entry), `.github/workflows/ci.yml`
(CI). Here the two-source conflict falls on `ruff` (cited from `lint.sh`
and `.github/workflows/ci.yml`); `yapf` has one source
(`.github/workflows/ci.yml` only) and, symmetrically with `cpp-repo`'s
`cpplint`, must not itself require a conflict line.

## Deterministic invocation

Run from `.github/skills/ult-autoscaffold-content/scripts/`, with
`<FIX>` = the absolute path to `evals/fixtures/autoscaffold-content/<lang>-repo`
(use absolute paths throughout — a long relative `../../../..` chain from
this directory has been observed to fail Windows/Git-Bash `mkdir` calls
inside `plan`):

```sh
python3 scaffold_state.py scan \
  "<FIX>/expected/TRIAGE-STATE.json" \
  --repo-root "<FIX>/repo" \
  --graph-mode graphify \
  --graph-path "<FIX>/graph.json"

python3 scaffold_state.py plan \
  "<FIX>/expected/TRIAGE-STATE.json" \
  --repo-root "<FIX>/repo" \
  --graph-path "<FIX>/graph.json" \
  --how-l2-path docs/how/repo \
  --out-dir "<FIX>/expected/packets"

python3 scaffold_state.py probe-size --repo-root "<FIX>/repo"
```

Expected results: `scan` reports `total_modules: 2` (one tier 3, one tier
2), `interfaces.total: 1`, no `graph_module_overlap_warning` and no
`graph_cep_contamination_warning`. `plan` reports `packets_written: 4`
(one `context_md` packet — the tier-2 module only, since
`PACKET_ELIGIBLE_MODULE_TIERS = (1, 2)` skips tier 3 — one
`interface_boundary`, `coding_standards`, and `testing_guidelines`).
`probe-size` reports `classification: "small"` and all three
`grounded_viable` kinds `true`.

To check the good/bad docs, copy one to `<FIX>/repo/docs/how/repo/CODING-STANDARDS.md`
and call `scaffold_state.validate(repo_root="<FIX>/repo", path="docs/how/repo/CODING-STANDARDS.md", packet=<the loaded coding-standards packet>)`
directly — see `tests/test_golden_fixtures.py` for the exact pattern, which
runs this automatically for both repos and both variants.
