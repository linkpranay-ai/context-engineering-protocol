# Case Study: BurntSushi/ripgrep

> **⚠️ Tooling side-quest, not a CEP protocol case study.** This evaluates `graphify`
> (the `ult-codegraph` skill's underlying tool) against naive search on a real Rust
> codebase — nothing here exercises CEP's actual protocol machinery: no context package
> was generated, no approval gate was exercised, no provenance/staleness/composition
> mechanics ran. It shows graphify is a useful component; it is **not** evidence for
> CEP's core thesis (grounding reduces hallucination, packages are provenance-tracked
> and reusable). Read it as a tool evaluation that happens to live in this directory
> for reproducibility, not as one of the protocol-level cases below it. A real
> CEP-protocol case study in a new ecosystem — context package generation + a
> downstream consuming skill, the same pattern as
> [`consumer-benefit-user-stories`](../consumer-benefit-user-stories/CASE-STUDY.md) —
> is still owed and tracked separately.

```yaml
case: ripgrep-crlf-replace-terminator
codebase: BurntSushi/ripgrep, dual-licensed Unlicense OR MIT, ~50 KSLOC Rust across 10 crates (CLI search tool)
date_run: 2026-08-01
author: dogfooding run, context-engineering-oss
negative_control: false
```

This is CEP's first case study in a non-Python, non-JS/TS ecosystem: a real Rust CLI tool built as a
Cargo workspace of 10 crates (`crates/core`, `cli`, `printer`, `searcher`, `regex`, `matcher`,
`grep`, `globset`, `ignore`, `pcre2`). It exercises `ult-codegraph` (`graphify`) alone — no
`ult-context-generate` package-generation run was performed, so this case is scoped to the
token-efficiency/fallback-relevance surfaces of `EVIDENCE-METHODOLOGY.md` §1 (surfaces 1-2), not the
context-package or consumer-output-quality surfaces (3-4). §3, §6, and §7 below say so explicitly
rather than being silently skipped.

## Results at a glance

| Metric | Without CEP (naive keyword search) | With CEP | Kind |
| --- | --- | --- | --- |
| Did the naive baseline find the real integration point? | Partial — a global `grep -rli "crlf"` matches 14 files across 6 crates with no disambiguation; narrowing to `crates/printer/` (guessing `--replace` is a printer/output concern) narrows to 3 files, all of which had to be read in full to locate the actual fix | Found — `graphify explain "Replacer"` resolves directly and unambiguously to `crates/printer/src/util.rs:14`, the exact struct PR [#3100](https://github.com/BurntSushi/ripgrep/pull/3100) modified | Measured |
| Naive read cost to confirm the fix (`crates/printer/{json,standard,util}.rs` in full) | 20,115 words (~26,820 tokens) | 239 words (~319 tokens) — combined output of `explain "Crlf"` + `explain "Replacer"` + `explain "HiArgs"` + `explain ".printer_standard()"` + `path "HiArgs" "Standard"`, ~84x fewer tokens | Measured |
| `graphify explain`/`path`/`affected` starting from the CLI **flag-definition symbol** (`Crlf`, the struct in `crates/core/flags/defs.rs`) | naive equivalent: reading `defs.rs`'s `Crlf` impl block, cheap either way | `explain "Crlf"` resolves correctly (degree 9) but every attempt to trace *from* it to the actual fix failed: `affected "Crlf"` → "No affected nodes found"; `path "Crlf" "Replacer"` and `path "Crlf" "StandardSink"` both degrade to a shallow, uninformative 4-hop path through the generic `super`/`std` import edge, with an "ambiguous source match" warning on both | Measured |
| `graphify explain` on an **ambiguous** symbol name (`trim_line_terminator`, which exists as both a free function in `util.rs` and an unrelated same-named method on `StandardImpl` in `standard.rs`) | naive equivalent: `grep -n "fn trim_line_terminator"` returns both definitions directly, no ambiguity | `explain "trim_line_terminator"` silently resolves to the *wrong* one (the `StandardImpl` method, not the `util.rs` free function PR #3100 actually rewrote) | Measured |
| `graphify path` starting from the **right abstraction level** (`HiArgs`, the runtime args struct, rather than the flag-definition struct) | naive equivalent: `grep -n "fn printer_standard" crates/core/flags/hiargs.rs`, one hit | `path "HiArgs" "Standard"` → correct, real 2-hop static edge: `HiArgs --method--> .printer_standard() --references--> Standard` | Measured |
| `graphify benchmark` reduction (whole-repo corpus, graphify's built-in generic questions) | naive-full-corpus-read baseline | 14.9x fewer tokens per query (206,750 words → ~275,666 naive tokens; 4,135 nodes / 10,263 edges; avg ~18,489 tokens/query) | Measured |

**Retrospective, not blind** (`EVIDENCE-METHODOLOGY.md` §7): the task was chosen from a real, closed,
already-merged PR, so the "right" answer was known before any query was run — the naive-search and
graphify queries below are the natural first attempts a developer would try, run after the fact, not
a blind trial.

## 1. Environment

Target codebase: a local clone of `BurntSushi/ripgrep`, tag `15.2.0`, commit
`e89fff89ac9af12e8d4ce9d5fd07beb408ca730f`. CEP commit: `ult-codegraph` skill as it stands in this
repo today; `graphify` CLI version `0.9.11` (PyPI package `graphifyy`, installed via `uv tool
install`), which satisfies the skill's `>= 0.9.11` floor. Runtime: no live interactive coding-agent
session — every `graphify` command below was run directly from a shell, and the naive-baseline
`grep`/`wc` commands were run the same way, for a fair side-by-side comparison.

**A real environment wrinkle, disclosed rather than worked around silently:** the first
`graphify update . --no-cluster` run, executed from the originally-provided clone path (a deeply
nested Windows path under `AppData\Local\Temp\claude\...\scratchpad\ripgrep`), failed silently in a
way that matters: every one of the 130 source files logged
`warning: worker failed for <file>: [Errno 2] No such file or directory: '<...>.tmp'` during AST
extraction, and the run completed with **0 nodes, 0 edges** — no hard error, just an empty graph.
The root cause: `graphify`'s AST-extraction workers write per-file temp cache files under
`graphify-out/cache/ast/v0.9.11/<hash>.<rand>.tmp`, and the full path length for that original clone
location was 299 characters — over Windows' legacy 260-character `MAX_PATH` limit — so every single
temp-file write failed. The fix was to make a **local-only** `git clone --local` (no network fetch,
pure filesystem copy) of the exact same clone into a short path (`C:\Users\pmishra\rgcep`), verified
identical (`git log -1` → same commit `e89fff89ac9af12e8d4ce9d5fd07beb408ca730f`, same tag `15.2.0`,
clean working tree) before re-running `graphify update . --no-cluster` there, which succeeded in
7.9s: `4,070 nodes, 10,263 edges`. This is a real, reproducible Windows-specific operational finding
for anyone running `graphify` from a deeply nested working directory (common under CI temp dirs, IDE
sandboxes, or `AppData`-rooted scratch paths) — logged here rather than in the governance defect log
since it is an environment/OS interaction, not a defect in CEP's own logic or in `graphify`'s
cross-platform code path in the abstract.

No `context-config.yaml` was populated and no `discover`/`confirm-layers` workflow was run — this
case does not use `ult-context-generate`. Setup was limited to `graphify update . --no-cluster` at
the (short-path) clone root, per this repo's own `.github/skills/ult-codegraph/SKILL.md` default
invocation.

## 2. Task

A real, closed, already-merged bug fix: **PR
[#3100](https://github.com/BurntSushi/ripgrep/pull/3100)**, "printer: preserve line terminator when
using `--crlf` and `--replace`" (merge commit `64174b8e68b59e560ad459f3c11cc9c4f00964bd`, referencing
issue #3097, shipped in ripgrep `15.0.0` per `CHANGELOG.md` line 108-109: `[BUG #3100]: Preserve line
terminators when using -r/--replace flag.`). The bug: combining `--crlf` (treat `\r\n` as the line
terminator) with `-r`/`--replace` (rewrite matched text) silently forced every output line to end in
`\r\n`, even for lines whose original terminator was a bare `\n` — a real correctness bug a developer
would phrase as: *"why does `rg --crlf -r '$0' PATTERN file` add a spurious `\r` to lines that didn't
have one, and where in the codebase is that behavior actually decided?"* Verified as an ancestor of
the pinned `15.2.0` commit (`git merge-base --is-ancestor 64174b8e... HEAD` → true), so the fix is
present in the exact codebase graphed for this case — the task is "trace how it works," not
"reproduce a live bug."

This is exactly the kind of cross-crate flag-flow question the assignment named as a template: the
flag is declared in `crates/core/flags/defs.rs` (a `Crlf` struct implementing the `Flag` trait), its
boolean value is threaded through `crates/core/flags/hiargs.rs` (`HiArgs`, the parsed/validated
runtime args struct), and the actual behavior it controls lives three crates away, in
`crates/printer/src/util.rs`'s `Replacer`/`trim_line_terminator` — the exact code PR #3100 rewrote.

## 3. Source set

Not applicable in the `ult-context-generate` sense (What-L1/L2/L3, How-L1/L2 layers) — this case
does not run that skill. The only "source" populated is `graphify`'s own code graph: `graphify update
. --no-cluster` at the repo root, covering the whole workspace (all 10 crates, 130 source files after
excluding non-Rust/generated content graphify itself filters). No manual scoping to a subdirectory
was used, matching this repo's own `SKILL.md` default invocation (`graphify update . --no-cluster`
from the repo root) rather than the crate-subdirectory scoping the skill's "Step 0" section describes
as an option for codebases with one dominant source directory.

## 4. Package generation

No context package was generated (`ult-context-generate` not run — see header). What was actually
run and its real output:

- `graphify update . --no-cluster` → `graphify-out/{graph.json, manifest.json, cache/}` (no
  `GRAPH_REPORT.md`/`graph.html`, since `--no-cluster` skips the clustering step that produces them).
  **4,070 nodes, 10,263 edges** in 7.9s (real time, short-path clone).
- `graphify explain "Crlf"` → resolves `crates_core_flags_defs_crlf`
  (`crates/core/flags/defs.rs:1382`), degree 9, connections to `.update()`, `.name_long()`,
  `.doc_short()`, etc. — the `Flag`-trait boilerplate every flag struct implements. Correct
  resolution, but a structural dead end (see §8).
- `graphify explain "Replacer"` → resolves `crates_printer_src_util_replacer`
  (`crates/printer/src/util.rs:14`), degree 7, connections including `<-- StandardSink [references]`
  and `<-- JSONSink [references]`. This is exactly the struct PR #3100 modified.
- `graphify explain "HiArgs"` → resolves `crates_core_flags_hiargs_hiargs`
  (`crates/core/flags/hiargs.rs:36`), degree 58, including `--> .printer() [method]` and
  `--> .search_worker() [method]`.
- `graphify explain ".printer_standard()"` → resolves `crates_core_flags_hiargs_hiargs_printer_standard`
  (`crates/core/flags/hiargs.rs:608`), degree 6, `--> Standard [references]`.
- `graphify path "HiArgs" "Standard"` → **correct, real 2-hop path**:
  `HiArgs --method--> .printer_standard() --references--> Standard`.
- `graphify explain "trim_line_terminator"` → resolves `crates_printer_src_standard_standardimpl_a_m_w_trim_line_terminator`
  (`crates/printer/src/standard.rs:1523`) — **the wrong symbol**: a same-named but unrelated method on
  `StandardImpl`, not the `util.rs:535` free function PR #3100 actually rewrote.
- `graphify path "Crlf" "Replacer"` and `graphify path "Crlf" "StandardSink"` → both return a shallow
  4-hop path through a generic same-file import (`Crlf <--contains-- defs.rs --imports_from--> super
  <--imports_from-- util.rs --contains--> Replacer`), each with a `warning: source match was
  ambiguous` note, and neither traces anything resembling the real dependency.
- `graphify affected "Crlf"` → `No affected nodes found` (BFS depth 2, all relation types).
- `graphify query "how does the --crlf flag affect line terminator handling in the printer
  replacement logic" --budget 1500` → 1,026 nodes matched, truncated to budget; real relevant nodes
  (`HiArgs`, `Standard`, `StandardImpl`, `.replacement()`) are present in the output but buried among
  ~20 shown nodes dominated by unrelated flags (`MaxCount`, `Multiline`, `TypeNot`) — noisy, not a
  precise answer.
- `graphify benchmark graphify-out/graph.json` → `206,750 words → ~275,666 tokens (naive); 4,135
  nodes, 10,263 edges; avg query cost ~18,489 tokens; 14.9x reduction` (3 generic built-in questions,
  not task-specific — see §9). Node count here (4,135) differs slightly from the `update` run's
  report (4,070); both are the tool's own real output, reported as observed rather than reconciled.

## 5. Detected gaps, conflicts, staleness

Not applicable — no `context-config.yaml`-driven gap/conflict/staleness checks exist for a
`graphify`-only run (those checks live in `ult-context-generate`, not run here). The closest
equivalent finding is tooling behavior, not a content gap: `graphify affected "Crlf"` returning "No
affected nodes found" is itself informative (§8), but it is a query-result characteristic, not a
gap/conflict/staleness detection in the template's sense.

## 6. Approval decision

Not applicable — no human-reviewed context package exists for this run to approve (see header).

## 7. Downstream use

Not applicable in the "handed to a coding agent" sense — no context package was generated to hand
off. The closest analog: the `graphify explain`/`path` outputs quoted in §4 are exactly what a
developer investigating this bug (or verifying its fix) would use directly, in place of reading
`crates/printer/src/util.rs` and `standard.rs` in full.

## 8. Outcome

**Measured, mixed.** `graphify explain` correctly and cheaply resolved the two load-bearing symbols
(`Crlf` the flag, `Replacer` the struct the fix touched) and a real, correct 2-hop static path
(`HiArgs --method--> .printer_standard() --references--> Standard`) — genuinely useful, and at a
small fraction of the token cost of reading the naive-grep-narrowed file set (239 words / ~319 tokens
vs. 20,115 words / ~26,820 tokens, ~84x fewer).

But the specific query pattern the task actually invites — "start from the CLI flag, trace to its
behavioral effect" — **failed** for every tool invocation that tried it starting from `Crlf` itself:
`affected "Crlf"` returned nothing; `path "Crlf" "Replacer"` and `path "Crlf" "StandardSink"` both
degraded into a generic, uninformative same-file-import hop. The reason is structural, not a bug to
file: ripgrep's CLI-parsing pattern gives every flag its own struct implementing a shared `Flag`
trait (`crates/core/flags/defs.rs`), used only during argument parsing to populate a plain `bool`
field on `HiArgs` (`crlf: low.crlf`, `hiargs.rs:265`). From that point on, the *value* (not the
`Crlf` struct) is threaded through unrelated builder-method calls
(`RegexMatcherBuilder::crlf(true)`, `Searcher::line_terminator(...)`) on types that never reference
`Crlf` by name. `graphify`'s AST-only static graph has no data-flow analysis to follow a `bool` value
across independent function calls, so it correctly has no edge to offer — the tool is not wrong here,
it is reporting the true absence of a *static* connection, even though a real *runtime* connection
exists. Querying at the right abstraction level instead (`HiArgs`, the struct that actually carries
the parsed value, or `LineTerminator`, the shared config type both `hiargs.rs` and `util.rs`
reference) works; querying the flag-definition struct itself does not. This distinction is not
obvious to someone who hasn't already read the code — which is exactly the case this finding is
worth recording for.

One additional real defect-adjacent finding: `explain "trim_line_terminator"` silently resolved to
the wrong same-named symbol (§4) with no warning that a second, unrelated definition exists elsewhere
in the same crate — a same-name collision in the same family as `DEF-001` from the `textual` case
study (`graphify query`'s bare-term BFS colliding two same-named classes), but here affecting
`explain`'s single-node resolution instead of `query`'s broad search.

## 9. Limitations

Single task, single codebase, no live human reviewer, no `ult-context-generate` package-generation
run — this case is scoped narrowly to `ult-codegraph`'s `explain`/`path`/`affected`/`benchmark`
commands (`EVIDENCE-METHODOLOGY.md` §1 surfaces 1-2 only), not the full protocol. The
`graphify benchmark` reduction figure (14.9x) uses graphify's own built-in generic questions ("what
is the main entry point", "what connects the data layer to the api", "what are the core
abstractions"), not questions about the `--crlf`/`--replace` task specifically — it measures
whole-corpus query economics, not this task's precision. The naive-keyword-search baseline is real
but retrospective (§ "Results at a glance"), reusing the same terms a developer chasing this task
would plausibly try, chosen after the real answer (PR #3100) was already known. The
flag-struct-vs-runtime-value finding in §8 is specific to ripgrep's one-struct-per-flag CLI pattern
(shared by several Rust CLI tools using a similar declarative-flag-trait approach) — it should not be
read as "graphify cannot trace CLI flags in general" without testing against a codebase using a
different flag-parsing pattern (e.g. `clap`'s derive macros, which some other Rust CLIs use instead
of ripgrep's hand-rolled `Flag` trait).

## 10. Lessons learned

Two real, actionable findings for future runs, not just this one:

1. **Windows deep-path environments break `graphify update` silently.** A `graphify-out/cache/`
   temp-file path exceeding 260 characters causes every AST-extraction worker to fail with a generic
   `[Errno 2]` warning per file, and the run still exits "successfully" with an empty (0-node) graph
   rather than a hard error — easy to miss if the per-file warnings scroll past unread. Anyone running
   `graphify` from a deeply nested working directory on Windows (common under CI/agent scratch
   directories) should check the reported node/edge count after `update`, not just its exit code, and
   should be ready to re-run from a shorter path if the count is zero or implausibly low.
2. **Query at the abstraction level that actually carries runtime behavior, not the declaration
   site.** For CLI-flag-flow questions specifically, querying the flag's own definition symbol
   (`Crlf`) is close to useless with `graphify path`/`affected` in a codebase using ripgrep's
   one-struct-per-flag pattern; querying the parsed-args struct that holds the resulting value
   (`HiArgs`) or the shared runtime config type the value ultimately configures (`LineTerminator`)
   works well. This is a specific, disclosed instance of a more general caveat worth carrying into
   other statically-typed, builder-heavy codebases (Rust and otherwise): a CLI flag's *declaration*
   and its *behavioral effect* are frequently different nodes with no static edge between them, once
   a plain scalar value is the only thing that crosses the gap.

## Reproduction steps

1. Obtain the pinned corpus: a clone of `BurntSushi/ripgrep` at tag `15.2.0`, commit
   `e89fff89ac9af12e8d4ce9d5fd07beb408ca730f`. **Use a short filesystem path on Windows** (see §1) —
   e.g. `git clone https://github.com/BurntSushi/ripgrep.git C:\rgcep && cd C:\rgcep && git checkout
   15.2.0` — to avoid the `MAX_PATH` cache-write failure documented in §1.
2. Confirm PR #3100's fix is present: `git merge-base --is-ancestor
   64174b8e68b59e560ad459f3c11cc9c4f00964bd HEAD` should exit 0.
3. Install `graphify` (`uv tool install graphifyy` or `pipx install graphifyy`); verify `graphify
   --version` reports `>= 0.9.11`.
4. From the clone root: `graphify update . --no-cluster`. Expect roughly 4,070 nodes / 10,263 edges
   (real counts may drift slightly as `graphify` itself is updated).
5. Run the specific queries from §4 in order: `graphify explain "Crlf"`, `graphify explain
   "Replacer"`, `graphify explain "HiArgs"`, `graphify explain ".printer_standard()"`, `graphify path
   "HiArgs" "Standard"`, `graphify explain "trim_line_terminator"`, `graphify path "Crlf" "Replacer"`,
   `graphify affected "Crlf"`. Compare resolved node IDs/source locations against §4's recorded
   values.
6. Run `graphify benchmark graphify-out/graph.json` (note: `benchmark [graph.json]` takes the graph
   file path as an optional positional argument, defaulting to `graphify-out/graph.json` — passing a
   directory instead of the `graph.json` file path is a usage error). Compare the reported
   corpus/graph size and reduction multiple against §4's recorded values.
7. For the naive baseline: `grep -rli "crlf" --include="*.rs" crates/` (expect 14 files), then `wc -w
   crates/printer/src/json.rs crates/printer/src/standard.rs crates/printer/src/util.rs` (expect
   ~20,115 words total) to reproduce the naive-read-cost figures in "Results at a glance".
