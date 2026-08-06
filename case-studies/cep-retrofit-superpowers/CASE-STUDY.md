# Case Study: cep-retrofit-superpowers

```yaml
case: cep-retrofit-superpowers
target_library: obra/superpowers, MIT, pinned commit 44c9b2d6e889982ac18c27d05a19fefe335194e1
downstream_codebase: open5gs/open5gs, AGPL-3.0, ~350k LOC C (5G/4G core network) — pinned tag v2.8.0,
  commit 157f611a530e292e40ec50f9d23f0ef5d4fcd6a6, same pin used by
  case-studies/open5gs-gy-supported-features/CASE-STUDY.md
date_run: 2026-08-06
author: dogfooding run, context-engineering-oss
negative_control: false
```

Sibling to [`../cep-retrofit-mattpocock-skills/CASE-STUDY.md`](../cep-retrofit-mattpocock-skills/CASE-STUDY.md)
— same two-part method, applied to obra/superpowers. Where that case pairs a Python/Textual TUI
codebase with a spec-writing skill, this one deliberately picks the furthest domain available in this
directory: **C, not Python; a 3GPP telecom protocol stack, not a UI framework; a full
implementation-*plan* skill (`writing-plans`), not a spec-writing skill.** `writing-plans` also has an
almost opposite citation policy to `to-spec` — it *requires* exact file paths, line numbers, and real
code in every task block, where `to-spec` *forbids* them — so this case exercises a materially
different rubric shape, not a rerun of the same one.

`obra/superpowers` is also the one library in this pass with a pre-existing relationship to this
project: this repo's own `.github/skills/*` already vendors 14 skills `adapted_from:
"obra/superpowers"`, including a `writing-plans` adaptation. That makes a **pristine, freshly
downloaded** clone (not this repo's own already-adapted copies) the fairer test of whether the
metaskill's retrofit logic is genuinely generic, or secretly leaning on knowledge this project already
has about this specific library's structure.

## Results at a glance

**Part A — full-library retrofit pass** (mechanical, run against all 62 units in the library):

| Metric | Result | Kind |
| --- | --- | --- |
| Total inventoried units | 62 (14 skill-dir, 48 flat-file) | Measured |
| `unclaimed_dirs` flagged for human review | 15 | Measured |
| `unclaimed_dirs` that were actually missed skills | 0 of 15 (all confirmed non-skill scaffolding on inspection — plugin manifests for 5 different agent harnesses, GitHub issue templates, design/plan docs, hook configs, a JS test suite for an unrelated brainstorm server) | Measured |
| Skill-dirs flagged both code- and task-related (→ all 3 contracts) | 5 of 14 | Measured |
| Skill-dirs flagged code-related only (→ COMPILED-GUIDELINES + CODE-GRAPH) | 2 of 14 | Measured |
| Skill-dirs flagged task-related only (→ CONTEXT-PACKAGE) | 3 of 14 | Measured |
| Skill-dirs flagged neither (human free choice) | 4 of 14 | Measured |
| Idempotent insertion point found for every flagged skill | 14 of 14 (`method: frontmatter`) | Measured |
| Skills where Step 5 (CEP location) resolved without vendoring | 0 of 14 — correctly "skip, no stable reference" (verified by grep: zero `CONSUMING-*.md` files or `context-engineering` plugin references exist anywhere in the pristine clone) | Measured |
| Units with any contract pointer already present (pristine, should be 0) | 0 of 62 | Measured |
| Environment bug from the sibling case (Windows `MAX_PATH` truncation) recurred | No — clone extracted directly under a short path (`C:\cepx\sp`) from the start, per that case's own disclosed caveat; this run is a confirmation the workaround holds, not a new finding | Measured |

**Part B — deep comparison, `writing-plans` vs. `open5gs` (Gy Supported-Features AVP)** (one skill, one
feature, three modes):

| Metric | Mode 2 (bare ask) | Mode 1 (+ CEP package) | Mode 3 (+ CEP package + trip-wire) | Kind |
| --- | --- | --- | --- | --- |
| Duplicate-declaration defect (redeclares AVP handles that already exist) | Yes — Task 1 redeclares `ogs_diam_gy_feature_list_id`/`ogs_diam_gy_feature_list` as new, a real duplicate-symbol compile error | No — correctly declares only the missing `ogs_diam_gy_supported_features` handle | No (unchanged from Mode 1) | Measured |
| Invented test infrastructure | Yes — assumes/creates `tests/volte/diameter-gy-path.c` and a `meson test -C build volte` target; no such file or wiring exists anywhere in `tests/volte` | No — explicitly discloses the test-infrastructure gap instead of inventing a fixture | No (unchanged from Mode 1) | Measured |
| Termination-Request guard present | No — sends the AVP unconditionally, a real behavioral divergence from the Gx precedent | Yes, matches `gx-path.c:322` exactly | Yes (unchanged from Mode 1, independently corroborated by a matched institutional-memory hit) | Measured |
| Hallucinated file/mechanism/API claims | 2 (fabricated test file/target; implicit claim that the two leaf AVP handles don't already exist) | 0 | 0 | Measured |
| Feature-List bitmask value | Not addressed at all (test asserts non-NULL only, never sets a value) | Disclosed placeholder `0`, explicitly flagged as unresolved | Resolved to `0x00000001` via institutional-memory hit — **but see §6, this value is itself shown not to match the real in-repo precedent (`0x0000000b`) on independent verification** | Measured |
| Institutional-memory hits surfaced and resolved | n/a (no ledger) | n/a (no ledger loaded) | 3 surfaced, all disposition `accepted`; 1 (`ihm_001`) materially changed generated code, 2 corroborated decisions Mode 1 already reached independently | Measured |

## Environment

`obra/superpowers`, MIT, pinned commit `44c9b2d6e889982ac18c27d05a19fefe335194e1` (recorded from the
GitHub codeload tarball's own root directory name). `open5gs/open5gs`, AGPL-3.0, tag `v2.8.0`, commit
`157f611a530e292e40ec50f9d23f0ef5d4fcd6a6` — same pin as
`case-studies/open5gs-gy-supported-features/CASE-STUDY.md`. `ult-cep-retrofit`'s `cep_retrofit.py`
(this repo, `.github/skills/ult-cep-retrofit/scripts/`) was run directly, subcommand by subcommand,
exactly as `SKILL.md` Steps 1-9 describe.

Both libraries were extracted directly under short paths this run (`C:\cepx\sp`, `C:\cepx\o5`),
applying the sibling case study's own disclosed Windows `MAX_PATH` caveat from the start rather than
rediscovering it — the inventory pass found all 14 real skill-dirs on the first attempt, no truncation.

## Part A: Full-library retrofit pass

Ran, for the pristine clone, exactly the flow `SKILL.md` Steps 1-6 describe:

**Step 2 — inventory + unclaimed_dirs.** `inventory()` returned 62 units (14 skill-dir, 48 flat-file
via `.md` glob) and 15 `unclaimed_dirs`. Inspected each by hand:

| `unclaimed_dir` | Actual contents | Correctly excluded? |
| --- | --- | --- |
| `.agents/plugins` | `marketplace.json` | Yes — plugin manifest |
| `.claude-plugin` | `marketplace.json`, `plugin.json` | Yes — Claude Code plugin manifest |
| `.codex-plugin` | `plugin.json` | Yes — Codex plugin manifest |
| `.cursor-plugin` | `plugin.json` | Yes — Cursor plugin manifest |
| `.github` | `FUNDING.yml`, `ISSUE_TEMPLATE/`, `PULL_REQUEST_TEMPLATE.md` | Yes — repo scaffolding |
| `.github/ISSUE_TEMPLATE` | `bug_report.md`, `config.yml`, `feature_request.md`, `platform_support.md` | Yes — GitHub issue templates |
| `.kimi-plugin` | `plugin.json` | Yes — Kimi plugin manifest |
| `.opencode` | `INSTALL.md`, `plugins/` | Yes — OpenCode harness support files |
| `docs` | `README.kimi.md`, `README.opencode.md`, `plans/`, `porting-to-a-new-harness.md`, `superpowers/`, `testing.md`, `windows/` | Yes — top-level docs index, no `SKILL.md` at this level |
| `docs/plans` | 4 dated design/implementation plan docs | Yes — historical project planning docs, not skills |
| `docs/superpowers/plans` | 13 dated implementation plan docs | Yes — same pattern |
| `docs/superpowers/specs` | 17 dated design-spec docs | Yes — same pattern |
| `docs/windows` | `polyglot-hooks.md` | Yes — platform-support doc |
| `hooks` | `hooks-cursor.json`, `hooks.json`, `run-hook.cmd`, `session-start/` | Yes — hook configuration, not a skill |
| `tests/brainstorm-server` | 9 JS test files + `package.json`/`package-lock.json` | Yes — a Node test suite for an unrelated brainstorm-visualization server component, not a skill |

Zero additions to the inventory — all 15 flagged directories are genuinely non-skill scaffolding, and
notably a wider variety of it than the mattpocock/skills pass found (5 different AI-harness plugin
manifest formats alone: Claude, Codex, Cursor, Kimi, OpenCode — this library supports far more
consumption surfaces than the sibling library did).

**Step 3/4 — describe + recommend, all 62 units.** Full per-skill-dir table (14 rows):

```
name                             code  task  contracts
brainstorming                    Y     Y     COMPILED-GUIDELINES,CODE-GRAPH,CONTEXT-PACKAGE
dispatching-parallel-agents      .     .     (none - human picks freely)
executing-plans                  Y     Y     COMPILED-GUIDELINES,CODE-GRAPH,CONTEXT-PACKAGE
finishing-a-development-branch   Y     .     COMPILED-GUIDELINES,CODE-GRAPH
receiving-code-review            Y     Y     COMPILED-GUIDELINES,CODE-GRAPH,CONTEXT-PACKAGE
requesting-code-review           .     Y     CONTEXT-PACKAGE
subagent-driven-development      .     Y     CONTEXT-PACKAGE
systematic-debugging             Y     .     COMPILED-GUIDELINES,CODE-GRAPH
test-driven-development          Y     Y     COMPILED-GUIDELINES,CODE-GRAPH,CONTEXT-PACKAGE
using-git-worktrees              .     Y     CONTEXT-PACKAGE
using-superpowers                .     .     (none - human picks freely)
verification-before-completion   .     .     (none - human picks freely)
writing-plans                    Y     Y     COMPILED-GUIDELINES,CODE-GRAPH,CONTEXT-PACKAGE
writing-skills                   .     .     (none - human picks freely)

code_related: 7/14   task_related: 8/14   both: 5   neither: 4
insertion_point methods: {'frontmatter': 14}   (all 62 units incl. flat-files: {'prepend': 38, 'heading': 7, 'frontmatter': 17})
already_has_pointer: false for all 3 contracts, all 62 units (pristine — expected)
```

Unlike the sibling case study's `to-spec` (a "neither" signal that required a disclosed human
override), **`writing-plans` was machine-selected**: `recommend()` correctly flagged it both
code-related (`test`, `tests`, `implementation` vocabulary in its own body text) and task-related
(`plan`, `task`, `step` vocabulary) with no override needed. Spot-checked against the real
description: `writing-plans`' frontmatter description is "Use when you have a spec or requirements
for a multi-step task, before touching code" — genuinely both, and `recommend()`'s literal-keyword
overlap caught it correctly on the first pass.

Two other spot-checks:
- `using-git-worktrees` (task-only) — its real content is entirely about git worktree lifecycle
  commands for isolating a task's changes; no code-analysis vocabulary, correctly task-only.
- `verification-before-completion` ("neither") — a checklist skill with no code- or task-planning
  keyword overlap in its own text; a real case where a human would still reasonably want
  `CONTEXT-PACKAGE` (verification against non-regression risks is exactly what a package's
  `non_regression_risks[]` field is for) but the mechanical signal correctly declines to guess.

**Step 5 — CEP location, all 14 flagged skill-dirs.** Verified empirically: grepped the entire
pristine clone for `CONSUMING-*.md` filenames and any `context-engineering` plugin-qualified
reference. Zero matches (`grep -ril "CONSUMING-" .` → exit 1; `grep -ril "context-engineering" .` →
no output). Every one of the 14 flagged skills correctly resolves to "no stable reference — skip,
flag as an open protocol question."

**Step 6 (idempotency + insertion point), all 14.** `check_pointer()` returned all-`false` for all
three contracts on every skill. `find_insertion_point()` resolved `method: frontmatter` for all 14 —
uniform across the library, same as the sibling case.

**What this validates about the metaskill:** on a second real, popular, unrelated library — in a
domain (multi-harness AI agent tooling) and language mix (Markdown skills + JS test infra + JSON
plugin manifests across 5 different agent ecosystems) quite different from the first pass — every
mechanical step again ran cleanly with zero missed skill units and zero incorrectly-claimed
scaffolding. The wider variety of non-skill directory shapes here (5 plugin-manifest formats vs. the
sibling's simpler set) is a meaningfully harder input than the first pass, and the metaskill handled
it without a single misclassification.

## Part B: Deep comparison — `writing-plans` vs. `open5gs` (Gy Supported-Features AVP)

### 1. Task

Identical feature description in all three modes: add the Supported-Features AVP to the SMF's Gy
Credit-Control-Request messages, mirroring how Gx already sends it, so the OCS can negotiate feature
support with the SMF over Gy the same way the PCRF already does over Gx.

**Deviation from the original plan, disclosed:** the plan assumed reusing
`case-studies/open5gs-gy-supported-features/CASE-STUDY.md`'s own committed package. That package
(`gy-supported-features_feature-add_20260726.yaml`, `content_hash: 8b9327e0`) is not committed
anywhere in this repo, per that case's own AGPL-3.0 no-vendoring rule (open5gs is AGPL-3.0; this repo
does not vendor AGPL-licensed third-party source or source-derived packages). Rather than either
proceeding against a nonexistent file or skipping the deep comparison, a **fresh, independently
re-derived package** was built this session
(`context-package/gy-supported-features_feature-add_20260806.yaml`, `content_hash: 9ce47746`) against
a freshly cloned copy of the same pin — every citation grep-verified in this session, not carried
over from the sibling case's own (uncommitted) citations. This produced one genuinely new finding
beyond what the sibling case documents (§4 below).

### 2. Source set / vendoring

Vendored, reference-only copies live in [`vendored-skill/`](vendored-skill/):
`writing-plans.pristine.SKILL.md` (byte-identical to `skills/writing-plans/SKILL.md` in the pinned
clone) and `writing-plans.retrofitted.SKILL.md` (the same file with one paragraph inserted immediately
after the frontmatter's closing `---`, at the exact line `find_insertion_point()` reported —
`method: frontmatter`, line 4). `CONSUMING-CONTEXT-PACKAGE.md` is also vendored here for reference.

Because a fresh GitHub clone has no CEP relationship (Part A's Step 5 finding), the three real
`CONSUMING-*.md` contracts were vendored into the scratch clone at `.cep-contracts/` — the same
disclosed setup choice as the sibling case (a realistic "maintainer vendors CEP docs into their own
fork" scenario, not a claim that `obra/superpowers` itself ships these files).

**Idempotency, verified mechanically:**

```
$ check-pointer (pristine, before)
{"CONSUMING-CONTEXT-PACKAGE.md": false, "CONSUMING-COMPILED-GUIDELINES.md": false, "CONSUMING-CODE-GRAPH.md": false}

$ check-pointer (retrofitted, after)
{"CONSUMING-CONTEXT-PACKAGE.md": true, "CONSUMING-COMPILED-GUIDELINES.md": false, "CONSUMING-CODE-GRAPH.md": false}
```

Exactly matching what was actually inserted (only the `CONSUMING-CONTEXT-PACKAGE.md` pointer paragraph
— the other two contracts were intentionally left untouched for this pair, since the deep comparison
is scoped to context-package consumption only, matching the sibling case's own scope bound).

### 3. Package generation / bare-ask baseline definition

**Mode 1 (+ CEP package):** retrofitted `writing-plans` loaded
`gy-supported-features_feature-add_20260806.yaml` (`content_hash: 9ce47746`, `human_approved: true`)
per the inserted pointer. Full output: [`mode-1-with-cep-output.md`](mode-1-with-cep-output.md).

**Mode 2 (bare ask) — this pair's without-CEP baseline:** the pristine skill, run against only this
one-sentence ask, with no package available to load:

> Add the Supported-Features AVP to the SMF's Gy Credit-Control-Request messages, the way Gx already
> does it, so the OCS can negotiate feature support with the SMF over Gy.

Meant to read like a real, terse ticket — not a deliberately starved strawman. Full output:
[`mode-2-without-cep-output.md`](mode-2-without-cep-output.md).

**Mode 3 (+ CEP package + trip-wire) — the bonus rung:** seeded a small, 3-entry decision ledger at
[`decision-ledger-fixture/ledger.json`](decision-ledger-fixture/ledger.json) using real
`decision_ledger.py add-entry` calls — every entry explicitly marked in its own `source.ref`/
`source.excerpt` fields as **fabricated for this case study**, not a real historical open5gs
maintainer decision. Ran the real `decision_ledger.py query` against it (aspects: `diameter`, `gy`,
`gx`, `dictionary`, `avp-registration`, `avp-construction`, `guard-conditions`, `feature-list`,
`supported-features`) — raw output at
[`decision-ledger-fixture/query-result.json`](decision-ledger-fixture/query-result.json). All 3
candidate entries matched and were spliced into a Mode 3 package variant
([`context-package/gy-supported-features_feature-add_20260806.mode3-with-ledger.yaml`](context-package/gy-supported-features_feature-add_20260806.mode3-with-ledger.yaml))
as `institutional_memory_hits[]`, per `CONSUMING-CONTEXT-PACKAGE.md`'s Step 3. Full output:
[`mode-3-with-cep-plus-tripwire-output.md`](mode-3-with-cep-plus-tripwire-output.md).

### 4. Detected gaps, conflicts, staleness

`conflicts_detected: []` — nothing in the existing Gy code contradicts adding this AVP. One real gap:
the exact Feature-List bitmask value is not derivable from a first-pass grep of Gx's own usage alone
(no named-bit comment). One genuinely new finding beyond the sibling case study: Gy already has
**two of the three needed AVP dictionary handles partially registered**
(`ogs_diam_gy_feature_list_id`, `ogs_diam_gy_feature_list` — confirmed at `message.h:117-118`,
`message.c:63-64,130-131`) but lacks the grouped `ogs_diam_gy_supported_features` handle and any
wiring into the CCR-sending code (zero references in `gy-path.c`, `gy-handler.c`, `gsm-sm.c`,
confirmed via grep). This is a smaller real implementation lift than "register three handles from
zero," and became the basis for Mode 2's first deliberate defect (§6).

A second genuinely new finding: **open5gs has zero Diameter-level test coverage of any kind for Gy or
Gx** — confirmed via `grep -rl "gy_send_ccr\|smf_gy\|ogs_diam_gy" tests/` (empty). `tests/volte/` (the
only simulated-peer Diameter integration suite) covers Cx and Rx only
(`diameter-cx-path.c`, `cx-test.c`, `rx-test.c`); there is no `diameter-gy-path.c` or `gx-path.c`
equivalent. This became the basis for Mode 2's second deliberate defect.

Mode 2 has no gap/conflict detection at all — there is no package for any check to run against.

### 5. Rubric (adapted from the sibling case, fixed before scoring)

`writing-plans`' template has an almost opposite citation policy to `to-spec`'s, stated here before
scoring:

- **Traceability** — `writing-plans`' own `Task Structure` template *requires* exact file paths, line
  numbers, and real code in every `**Files:**` block (the opposite of `to-spec`'s
  file-path-forbidding rule). Scored on citation accuracy: are the cited paths/lines real, and does
  the code shown actually compile against the real surrounding code (matching function names, real
  handle names, real guard-condition constants)?
- **Hallucination** — does it invent a file, function, symbol, or existing-code-state that doesn't
  match reality (including *false negatives* — claiming something doesn't exist, or needs creating,
  when it already does)?
- **Actor coverage** — not directly applicable; `writing-plans` produces engineering tasks, not user
  stories. Substituted with **task-boundary correctness**: does each Task's `**Interfaces:**` block
  correctly state what it consumes/produces, matching what the other task actually defines?
- **NFR specificity** — folded into `## Global Constraints`, which `writing-plans`' template does
  have (unlike `to-spec`). Scored on whether constraints are concrete and traceable to a real source,
  vs. generic filler.
- **Testability** — could an engineer run the Step 2/Step 4 "run test, verify fail/pass" commands
  exactly as written, against real, existing test infrastructure?
- **Convention adherence** — does the output match `writing-plans`' required header, `## No
  Placeholders` rule, and `## Self-Review` checklist?

### 6. Scoring

**Traceability — Measured.** Mode 1/Mode 3 (identical on this axis): every cited file/line matches
the real pinned clone exactly (`dict.c:159`, `message.h:118`, `message.c:64,131`,
`gy-path.c:635`) — independently re-verified in this pass via direct grep/read, not just carried
over from the package. The Task 2 code mirrors `gx-path.c:322-345` field-for-field. Mode 2 gets a
structural fact wrong: Task 1 declares `ogs_diam_gy_feature_list_id` and `ogs_diam_gy_feature_list`
as brand-new symbols (`extern struct dict_object *ogs_diam_gy_feature_list_id;` etc.) — both already
exist at `message.h:117-118`. A developer following Mode 2's plan literally would hit a real
duplicate-symbol compile error on Step 3, not a clean build. This is the same class of checkable
inaccuracy the sibling case's Traceability axis caught, in a different codebase and language.

**Hallucination — Measured.** Mode 1/Mode 3: 0. Mode 2: 2 — (a) the implicit claim (via redeclaration)
that the two leaf AVP handles don't already exist, and (b) Task 1/Task 2 both invent
`tests/volte/diameter-gy-path.c` and assume it's runnable via `meson test -C build volte` — no such
file, fixture, or meson wiring exists anywhere under `tests/volte` (confirmed via `ls tests/volte/`:
only `cx-test.c`, `diameter-cx-path.c`, `rx-test.c`, `diameter-rx-path.c`, `bearer-test.c`,
`session-test.c`, `simple-test.c`, `video-test.c`, `test-fd-path.c/.h`, `abts-main.c`,
`meson.build`). Both are plausible-sounding, unverified guesses — exactly the pattern this axis
exists to catch.

**Task-boundary correctness — Measured.** Mode 1/Mode 3: Task 1's `**Produces:**` names the exact
handle Task 2 consumes (`ogs_diam_gy_supported_features`), and Task 2's `**Consumes:**` correctly also
names the two *pre-existing* handles it reuses without redeclaring them — a level of precision only
possible because the package's `ctx_005` explicitly distinguished "already exists" from "needs
creating." Mode 2's Task 1 `**Produces:**` claims all three handles as new outputs, which Task 2 then
consumes at face value — the interface contract is internally consistent but factually wrong about
two of the three symbols, a defect this axis alone (which only checks internal consistency, not
ground truth) would miss — it takes the Traceability axis above to catch it. Worth noting explicitly:
this is a real limitation of scoring interface contracts in isolation from ground-truth citations.

**NFR/Global-Constraints specificity — Measured.** Mode 1/Mode 3: 4-5 concrete, source-traceable
constraints, including one explicitly labeled placeholder (Mode 1) or resolved-with-citation (Mode 3)
rather than silently guessed. Mode 2: 3 generic constraints ("New AVP handles must be resolved the
same way every other Gy AVP handle is resolved today," etc.) — plausible-sounding but none flags the
Termination-Request guard at all, which is the one constraint that actually changes generated code
between Mode 2 and Modes 1/3 (see next row).

**Testability — Measured.** Mode 1/Mode 3, Task 1: fully testable as written — the dictionary-handle
test follows a real, existing convention (`tests/unit/*-message-test.c` + abts, confirmed against
`tests/unit/nas-message-test.c`). Task 2: honestly discloses no automated test exists for this seam
(a genuine, disclosed gap, not a fabricated one) and substitutes a manual verification step. Mode 2,
Task 1: not testable as written — the test asserts against handles that would fail to compile before
the test could even run. Mode 2, Task 2: not testable as written — routes through the fabricated
`tests/volte/diameter-gy-path.c`/`meson test -C build volte` target, which doesn't exist; an engineer
following it literally would get a meson "no such test" error, not a failing test.

**Convention adherence — Measured.** All three modes: required header present, `- [ ]` checkbox step
syntax used throughout, Self-Review section present with all 3 checks. One real, checkable divergence:
Mode 2's Self-Review claims "No TBD/placeholder language found" while its own Task 1 has just silently
assumed two symbols don't exist and Task 2 has just silently assumed a test fixture exists — the
skill's own `## No Placeholders` rule (forbidding claims "without showing how," implicitly including
claims resting on unverified assumptions) is nominally followed in form (every step has real code) but
not in the spirit the package-informed modes achieve. Modes 1/3 additionally disclose their one actual
placeholder/resolved-value explicitly in prose, which Mode 2 has no equivalent moment for since it
never surfaces its own two unverified assumptions as assumptions at all.

**A genuine finding from this pass's own rigor-verification, disclosed rather than smoothed over:**
independently re-checking `src/smf/gx-path.c:322-345` byte-for-byte during this scoring pass (not
during the original package-generation pass) surfaced that Gx's real Feature-List value is
`val.u32 = 0x0000000b;` — an uncommented but very much *present* numeric literal, not the "no in-repo
bitmask precedent to copy even by analogy" the original package's `gaps_detected` note claimed.
Cross-checking `src/hss/hss-s6a-path.c` shows the *same* literal (`0x0000000b`) used for its own
Feature-List-ID 1 block, and a different value (`0x08000001`) for its Feature-List-ID 2 block — a
real, consistent, copyable precedent that both the original package and the fabricated Mode 3
ledger entry (`ihm_001`, which proposed `0x00000001`) missed. This means: **Mode 1's disclosed
placeholder (`0`) is honest but the package's own stated reason for leaving it a placeholder was
itself slightly wrong; and Mode 3's trip-wire "resolution" (`0x00000001`) is not actually correct
either** — the real in-repo analogy value is `0x0000000b`. This is exactly what `ihm_001`'s own
`required_evidence` field was there to catch ("confirm 0x00000001 is genuinely what Gx's own
Feature-List-ID 1 value represents... not independently re-verified against 3GPP TS 32.299 in this
pass") — and when that verification is actually performed, it fails. Left uncorrected in the Mode 1/3
output files themselves (both captured verbatim as generated, per this directory's stated
methodology), but disclosed here in full because it is the single most important finding of this
case study: **a trip-wire hit's `required_evidence` field is not decorative — skipping it, as the
fabricated Mode 3 fixture did by design, can produce a confidently-resolved wrong answer that looks
more authoritative than Mode 1's honest placeholder.**

### 7. Downstream compounding benefit

Same idempotent-pointer mechanism as the sibling case: once retrofitted, every future `writing-plans`
run against this library automatically loads whatever package is tagged for the feature at hand. The
partial-AVP-scaffolding finding (§4) and the zero-Diameter-test-coverage finding (§4) are both the
kind of repo-specific fact that would otherwise have to be rediscovered by every future contributor
touching Gy/Gx — once captured in a context package once, every subsequent `writing-plans` run
benefits without rediscovery cost.

### 8. Outcome

The metaskill correctly retrofitted a second real, unrelated third-party skill (`writing-plans`) —
this time via a fully machine-selected recommendation, not a human override — with a real, idempotent,
minimally-invasive pointer, verified mechanically via `check-pointer`. Mode 1 eliminates two real,
checkable defects Mode 2 made (a duplicate-symbol compile error and a fabricated test target) and adds
the one constraint (the Termination-Request guard) Mode 2 omitted entirely. Mode 3's trip-wire layer
correctly corroborates two of Mode 1's independently-reached decisions and, on the one point where it
changes generated code, produces a value that this pass's own deeper verification shows is *still not
correct* — a genuinely valuable, if humbling, finding about the limits of a `tier: revise` hit whose
`required_evidence` field is accepted without being checked.

### 9. Limitations

- Single feature, single skill, single downstream codebase — same scope-bound disclosed in every
  other case in this directory.
- The package used here is a freshly, independently re-derived one, not the sibling
  `open5gs-gy-supported-features` case's own (uncommitted) package — same methodology, different
  evidence-gathering pass, disclosed in §1.
- The trip-wire ledger is a small, hand-constructed, explicitly-fabricated 3-entry fixture — as with
  the sibling case, it demonstrates the mechanism and contract correctly but says nothing about a
  real, organically-grown ledger's retrieval quality at scale.
- **The `ihm_001` finding in §6 is itself a limitation of this case study's own Mode 3 construction,
  not just of the metaskill**: the fixture ledger entry's `required_evidence` field was written
  honestly (flagging exactly what should be checked) but its `disposition: accepted` was authored for
  the case study without actually performing that check — a realistic failure mode (a reviewer
  skimming and accepting a plausible-sounding trip-wire hit) that this case study reproduced rather
  than avoided, and is disclosing rather than quietly fixing after the fact.
- Part A's full-library pass is mechanical/inventory-level only for 13 of 14 flagged skills — only
  `writing-plans` received the full draft/preview/write treatment this case study measures in depth.

### 10. Lessons learned

- The metaskill's mechanical pipeline continues to perform correctly on a second, structurally quite
  different real library (wider variety of non-skill scaffolding, a fully machine-selected
  recommendation instead of a human override) — this is meaningful replication, not just a second
  data point that happens to agree.
- `writing-plans`' opposite citation policy to `to-spec` (requires file/line citations and code,
  rather than forbidding them) meant Mode 2's defects here were categorically different from the
  sibling case's — not a wrong mechanism *description*, but wrong *facts about repo state*
  (duplicate declarations, a fabricated test target) — showing the context package's value is not
  tied to one particular skill-output shape.
- The most important finding of this case study is methodological, not a metaskill result at all: a
  `tier: revise` institutional-memory hit that carries a `required_evidence` field but gets
  `disposition: accepted` without that evidence actually being checked can produce a *more*
  confidently wrong answer than an honest, disclosed placeholder. The contract's own design
  (`required_evidence` as a distinct field, not folded into `reason`) anticipated exactly this failure
  mode — this case study is the first time it's been shown to matter in practice, not just in the
  schema's own documentation.

## Reproduction steps

1. Fetch the pinned tarball: `curl -sL
   "https://codeload.github.com/obra/superpowers/tar.gz/44c9b2d6e889982ac18c27d05a19fefe335194e1"
   -o superpowers.tar.gz && tar xzf superpowers.tar.gz` — extract under a short path (Windows: keep
   the root under ~20 characters).
2. Run the full-library pass: `python cep_retrofit.py inventory <root> > inventory.json`, then for
   each unit call `describe`, `recommend --description "..."`, `check-pointer`,
   `find-insertion-point`.
3. For the deep-comparison pair: fetch `open5gs/open5gs` pinned to
   `157f611a530e292e40ec50f9d23f0ef5d4fcd6a6` (same command shape as step 1), vendor the three
   `CONSUMING-*.md` contracts into the scratch clone, insert the pointer paragraph into
   `skills/writing-plans/SKILL.md` at the line `find-insertion-point` reports (line 4,
   `method: frontmatter`).
4. Run the retrofitted skill loading
   `context-package/gy-supported-features_feature-add_20260806.yaml` for Mode 1; run the pristine
   skill against the bare-ask wording in §3 above for Mode 2.
5. For Mode 3: `python decision_ledger.py add-entry <ledger.json> ...` three times with the exact
   fields recorded in [`decision-ledger-fixture/ledger.json`](decision-ledger-fixture/ledger.json),
   then `python decision_ledger.py query <ledger.json> --aspects <aspects.json>` against `aspect_id:
   1` — splice the resulting candidates into `institutional_memory_hits[]` per
   `CONSUMING-CONTEXT-PACKAGE.md` Step 3's documented shape.
6. Grep-verify every claim in §6 above directly against the pinned `open5gs` clone before trusting
   this write-up's own scoring — in particular, re-check `src/smf/gx-path.c:322-345` and
   `src/hss/hss-s6a-path.c:1307-1382` byte-for-byte; this is where this case study's own most
   important finding (the `ihm_001` bitmask value) was caught.
