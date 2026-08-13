```yaml
case: robotframework-wizard-ui
codebase: robotframework/robotframework (Apache-2.0, ~55K lines Python across src/robot/, excluding tests)
date_run: 2026-08-13
author: Pranay Mishra
negative_control: false
```

## Results at a glance

| Metric | Without CEP (bare ask) | With CEP (approved package) | Kind |
| --- | --- | --- | --- |
| Real, `context_items`-verifiable citations | 0 (every story cites "bare feature description" only) | 9 of 9 package `context_items` cited across 5 stories | Measured |
| Distinct, feature-relevant actors named | 2 (generic fallback: "User", "Developer") | 2 (specific: core maintainer/contributor, Libdoc user with a large library — both drawn from `context_items`, not invented) | Measured |
| Distinct capabilities turned into stories | 3 | 5 (2 extra stories — real blast-radius coverage of both Libdoc call sites, and the fact the real fix already exists upstream) | Measured |
| Unknowable-without-grounding fact surfaced | None | US-005 states the exact real fix commit (`6d0c6a463`) already exists upstream, postdating this pinned clone | Measured |
| `graphify affected ".converter_for()" --depth 2` blast radius | not consulted | 11 real affected nodes (both Libdoc call sites + 6 subclass `__init__`s + runtime caller) | Measured |
| `graphify explain "TypeConverter"` degree | not consulted | 44 (25 converter subclasses inherit from it) | Measured |
| Autoscaffolded What-L2/How-L2 coverage (Phase B) | n/a | 13/13 modules generated for both boxes, 0 skipped | Measured |
| Stretch: code-change proposal validated against real unit tests | n/a | `libdoc` 47/47 pass, `running` 362/362 pass, identically before and after the fix | Measured |
| Wizard UI Playwright walkthrough | n/a | 6 real screens exercised before and after autoscaffold, 0 page errors, 2 harness-timing bugs found (both in the test script, not the wizard) | Measured |

## 1. Environment

- Codebase: `robotframework/robotframework`, shallow-cloned at tag `v7.1.1` (commit
  `10f24c2896dcd15bce591d76fd278aff64da418d`, 2024-10-19) to the short sibling path
  `C:\Users\pmishra\cep-dogfood-rf` (Windows `MAX_PATH` avoidance — a nested scratchpad path had
  already been hit and worked around once this session).
- Size verified before proceeding, per the plan's Step 1 gate: `find src/robot -name '*.py' |
  xargs wc -l` → **54,912 lines** across `src/robot/` (tests excluded) — squarely inside the
  50-100 KSLOC target, no fallback to `aiohttp`/`poetry` needed.
- CEP installed via `./install.sh --target C:\Users\pmishra\cep-dogfood-rf --init-project`.
- New branch `case-study/robotframework-wizard-ui` in `context-engineering-oss`, off the
  `ult-cep-wizard` rename tip — local only, not pushed.
- `graphify` 0.9.11 (same version validated in the ripgrep case studies).
- Playwright 1.62.0 was already installed in the Python env; `playwright install chromium` was run
  first (~150MB download, confirmed live) since the Chromium binary itself was missing.
- `context-config.yaml` scaffolded by `--init-project`, then confirmed through the wizard UI itself
  (§2 below) rather than hand-edited: What-L2 → `docs/requirements`, How-L2 → `org`, both staged as
  `CUSTOM` decisions and genuinely empty on disk at the point they were confirmed — the exact
  precondition `ult-autoscaffold-content`'s Phase D wiring is meant to detect.

## 2. Wizard UI walkthrough (Playwright)

This is the first case study in this directory to drive the wizard's browser UI at all — every
prior case exercised `ult-context-generate`/`graphify`/consuming skills directly, never the
`ult-cep-wizard` HTTP server through a real browser.

Script: [`wizard_playwright_walkthrough.py`](wizard_playwright_walkthrough.py) (kept as real,
runnable evidence, not a description). Launched `python -u
.github/skills/ult-cep-wizard/scripts/wizard_server.py C:\Users\pmishra\cep-dogfood-rf` in the
background, then drove Chromium headless through:

1. Open the printed `/exchange?token=...` URL.
2. Detect initial state (`needs_discover` vs `decisions_pending` vs `steady_state`) and click
   **Run Discover** if needed.
3. Screenshot `decisions_pending`, resolve each real `PENDING` field to `CUSTOM` targeting genuinely
   empty `docs/requirements`/`org` directories (the wizard's own discovered candidates pointed at
   real, non-empty `doc/`/`.github/` directories with 151 pre-existing files — confirming those
   would have skipped the empty-case stub cards entirely and defeated the point of the walkthrough,
   so this run deliberately retargeted to empty paths instead).
4. Click **Apply**, screenshot `steady_state` — the four boxes and their stub cards.
5. Exercise the docs-viewer nav (Protocol / README / Case Studies).
6. Save screenshots to [`wizard-screenshots/`](wizard-screenshots/) with a `before-*`/`after-*`
   prefix, plus a machine-readable `*-report.json` per run.

Run twice: **before** `ult-autoscaffold-content` (Section 3) had written anything, and **after** —
the same server/session, so the two screenshot sets are a genuine before/after pair, not staged
separately.

**Before** (`before-report.json`, `before-01..06-*.png`): initial state was `decisions_pending`
(not `needs_discover` — discover had already run once this session), 2 fields staged as `CUSTOM`,
Apply confirmed "2 field(s), wrote 2 config key(s)," landing in `steady_state` with **3 populated
stub cards** — What, How, and the untouched Guidelines box — each quoting
`ult-autoscaffold-content`'s real prompt text and expected path. 0 page errors; 3 console 404/400s
(benign, see bugs below).

**After** (`after-report.json`, `after-01..06-*.png`): initial state was already `steady_state`
(the What/How boxes now have real content from Section 3). Apply reported "Nothing to confirm —
every field was already confirmed." The stub-card check found only **1 populated stub card**
(Guidelines, deliberately left untouched) and 2 empty slots where What/How's stub cards used to be.
Confirmed via `wizard.js:229` that this is intentional, not a defect: the stub-card DOM slot stays
present but renders empty once real content exists for that box. This is genuine positive
before/after evidence that Phase D's wiring works end-to-end through the real browser UI, not just
that the scaffolder ran: 3 stub cards before, 1 (correctly, the untouched one) after.

Docs-viewer nav opened all three documents successfully in both runs (Protocol: 28,316 chars,
README: 20,606 chars, Case Studies: 8,251 chars) with 0 page errors.

### Bugs and friction found (test harness, not the wizard)

Two real timing issues surfaced during scripting, both in the Playwright harness itself, not in
shipped wizard code:

1. **Apply-button race.** The script's first attempt to stage both `CUSTOM` fields and immediately
   check the Apply button hit a `400: "line 13 is already staged as 'CUSTOM: docs/requirements' -
   re-stage explicitly if you want to change it"` — both fields were genuinely staged correctly on
   disk, but the script checked before the async `loadDecisions()` re-render caught up, so a
   screenshot taken at that moment showed stale `PENDING` badges despite a successful stage. Fixed
   by polling for the re-render before proceeding, not a wizard defect.
2. **`wizard_server.py` stdout buffering.** Its stdout is buffered when piped to a file (not a
   TTY), so the printed `/exchange?token=...` URL wasn't visible until the process was restarted
   with `python -u`. A real, minor operability gap worth a one-line README note (skip a live
   background-process read cycle), not a functional defect.

Console also logged 2 benign 400s (the redundant-CONFIRM refusal above, working as designed) and 1
404 (unrelated static asset, present in both runs) — none affected functional correctness.

## 3. Task

Write functional user stories for a real, closed GitHub issue:
**[#5254](https://github.com/robotframework/robotframework/issues/5254), "Libdoc performance
degradation starting RF 6.0"** (opened 2024-11-04, closed 2024-11-05, milestone v7.2). Root cause:
`TypeConverter.__init__` (`src/robot/running/arguments/typeconverters.py:54`) unconditionally does
`self.languages = languages or Languages()`; Libdoc's doc-generation path (`TypeDoc.for_type()` in
`libdocpkg/datatypes.py:50`, `_get_type_docs()` in `libdocpkg/robotbuilder.py:45,68`) never passes
`languages`, so every documented argument type constructs a fresh `Languages()` instance purely for
documentation, roughly doubling Libdoc's run time on large libraries. Phrased the way a developer
would actually hand this to a user-story-writing tool:

> "Write user stories for fixing Libdoc's performance regression on large keyword libraries —
> `TypeConverter` is constructing a new `Languages()` instance for every documented argument type
> even though Libdoc never needs it."

The real upstream fix, commit `6d0c6a4630bf6b906253c802e2bf5b266a1a8893` ("Initiallize
`TypeConverter.languages` only when needed," 2024-11-05, "Fixes #5254"), postdates this pinned
`v7.1.1` clone (2024-10-19) — the bug is still live, reproducible source here, satisfying the same
evidentiary bar as FastAPI's `links=` gap and ripgrep's PR #3100 in prior case studies.

## 4. Source set

- **What-L3** (code): `src/robot/` — `running/arguments/typeconverters.py`,
  `libdocpkg/datatypes.py`, `libdocpkg/robotbuilder.py`, `conf/languages.py`.
- **What-L2** (`docs/requirements/`) and **How-L2** (`org/`): both were genuinely empty at the
  start of this run — confirmed live through the wizard UI (§2) — then populated by
  `ult-autoscaffold-content`'s Phase B (large-repo triage/tiering), run directly and
  conversationally as the agent, per its own `SKILL.md` (it is never invoked as a wizard
  subprocess by design).
  - Real path-relativity bug found and fixed in this run's own first `graphify` invocation: `graphify
    update src/ --no-cluster` was run from the repo root, so `graph.json`'s `source_file` values
    came out repo-root-relative (`src/robot/api/deco.py`, ...). `scaffold_state.py`'s
    `_module_of()` does a naive split on the first `/`, expecting module names like `api`,
    `running`, `conf` directly under `src/robot` — with the graph's top-level segment always
    `src`, every module falsely landed in Tier 3 with `in_degree: 0`. This is not a skill bug — the
    graph invocation's cwd simply didn't match the scan's expected repo-root — but it is a real,
    silent-failure-shaped footgun: nothing validates or warns about the mismatch, it just produces
    a plausible-looking (wrong) tiering. Fixed by re-running `graphify update` with cwd set to
    `src/robot`; re-scanning then correctly aligned per-package module names.
  - With the graph corrected (6,932 nodes / 18,909 links, scoped to `src/robot`), Phase B tiered
    all 13 top-level modules identically for both boxes: Tier 1 — `utils/` (in-degree 11); Tier 2 —
    `api`, `conf`, `htmldata`, `libraries`, `model`, `output`, `parsing`, `reporting`, `result`,
    `running`, `variables` (11 modules); Tier 3 — `libdocpkg/` (in-degree 0, the only leaf); Tier 0
    — none. **13/13 generated for both What-L2 and How-L2, 0 skipped, 0 pending.** No domain pack
    was configured (`autoscaffold_content.domain_pack_path` absent) — proceeded on observed
    dependency-graph evidence only.
- **What-L1**: not enabled (no external spec source configured for this project).
- Code graph: `graphify update`, scoped correctly to `src/robot` — 6,932 nodes, 18,909 links.

## 5. Package generation

Ran `ult-context-generate`'s real workflow (`graphify query`/`explain`/`affected`,
`content_hash.py`), self-answered dogfooding (no live human reviewer in the loop — disclosed per
this repo's standing convention), producing
[`libdoc-lazy-languages_user-story_20260813.yaml`](libdoc-lazy-languages_user-story_20260813.yaml):

- `context_package.id`: `libdoc-lazy-languages_user-story_20260813`, `content_hash: b0489975`
- 2 `aspects`: (a1) root cause — eager-vs-lazy `TypeConverter.languages` construction; (a2) Libdoc's
  call path into `converter_for()` (blast radius)
- 9 `context_items` (`ctx_001`-`ctx_009`): 5 What-L3 (the `__init__` line, both real Libdoc call
  sites, a `graphify explain`/`affected` blast-radius pair, and the direct-source confirmation the
  bug is still live at this pinned commit), 2 What-L2 (the real GitHub issue + its real fix commit,
  treated as an external What-L2-equivalent artifact — same precedent the ripgrep case studies set
  for `CHANGELOG.md`), 2 What-L2 from this run's own freshly-autoscaffolded content
  (`docs/requirements/libdocpkg/CONTEXT.md`, `docs/requirements/running/CONTEXT.md`, corroborating
  real dependency edges but not mentioning the bug itself — module-granularity, disclosed below), 1
  domain-knowledge item (`confidence: SUGGESTED`, corroborated directly against
  `conf/settings.py:531`'s real execution-path usage)
- `conflicts_detected: []`, `gaps_detected: []`, 1 disclosed `open_questions` entry (whether the
  companion commit optimizing `Languages.__init__` itself makes the lazy-vs-eager question moot for
  smaller libraries — out of scope for this task's source set)
- 3 `decisions_log` entries and 3 `non_regression_risks` entries — see §6 and the package file for
  full text.

## 6. Detected gaps, conflicts, staleness — and a genuine autoscaffold-quality finding

`conflicts_detected` and `gaps_detected` both came back empty — the real GitHub issue, the real
source, and this run's own autoscaffolded content all describe the same mechanism without
contradiction.

One real, disclosed finding worth surfacing on its own: this run's freshly-autoscaffolded
What-L2/How-L2 content (`docs/requirements/libdocpkg/CONTEXT.md`,
`docs/requirements/running/CONTEXT.md`) was genuinely useful for corroborating dependency edges
(`libdocpkg` → `running` → `conf`, matching the real call chain found in What-L3) but **does not
mention performance or this specific bug at all** — because `ult-autoscaffold-content`'s Phase B
content is generated at module granularity (docstring + tier + dependency edges), not at line- or
issue-level detail. This task's real primary grounding came from What-L3 (source) + the code graph
+ the real GitHub issue/commit, with the autoscaffolded What-L2/How-L2 serving a corroborating, not
primary, role. This is disclosed explicitly here rather than silently counting autoscaffolded
What-L2 as "covered" in a way that overstates what it actually contributed to this specific,
narrow task — a genuine, first-of-its-kind finding about Phase B's real usefulness ceiling that no
prior case study (none of which exercised the large-repo autoscaffold path) could have surfaced.

Separately, unlike both ripgrep case studies in this repo, `graphify affected` never returned a "no
affected nodes found" low-degree-leaf result anywhere in this run — `TypeConverter` (degree 44) and
`Languages` (degree 25 via `affected --depth 1`, 11 real dependent nodes) are both high-degree,
central utility classes, far above that failure mode. A genuine contrasting data point on when the
previously-disclosed limitation does and doesn't bite, not a new defect.

## 7. Approval decision

Self-approved dogfooding run — no live human reviewer available this session, same disclosed
convention as every other case study in this repo. Approved as-is; no addenda needed at approval
time (the one addendum produced in §8 is a downstream reverse-index reference written after
approval, not a pre-approval correction).

## 8. Downstream use

Ran `.github/skills/demo-write-user-stories/SKILL.md` twice against the identical task description
from §3:

- **Mode 1 (with CEP)** — the approved package loaded per `CONSUMING-CONTEXT-PACKAGE.md`. 2
  specific actors (core maintainer/contributor; Libdoc user with a large library — both drawn from
  `context_items`, not invented). 5 stories (US-001–US-005), collectively citing all 9 `ctx_ids`.
  US-005 specifically states that the real fix already exists upstream (commit `6d0c6a463...`,
  "roughly 50% performance enhancement") and postdates this pinned clone — a fact only the package
  makes available; nothing in the bare task description states it.
  See [`mode-1-with-cep-output.md`](mode-1-with-cep-output.md).
- **Mode 2 (without CEP)** — the same task description, no package loaded. Fell back to the skill's
  generic actors ("User", "Developer") exactly as its own Step 2 specifies when no actor is named
  and no package is loaded. 3 stories, each grounded only in "bare feature description (no context
  package available)" — no real call-site line numbers, no fix-commit citation, no execution-path
  corroboration.
  See [`mode-2-without-cep-output.md`](mode-2-without-cep-output.md).

A `kind: reference` addendum was written,
[`libdoc-lazy-languages_user-story_20260813.addenda.yaml`](libdoc-lazy-languages_user-story_20260813.addenda.yaml),
citing `mode-1-with-cep-output.md` and all 9 `ctx_ids`, per `CONSUMING-CONTEXT-PACKAGE.md` step 9 —
so a future reader of the package can discover the downstream artifact that consulted it.

**Stretch goal — code-change proposal.** Beyond user stories, this run also produced and validated
a concrete fix for the same task: converted `TypeConverter.__init__`'s eager
`self.languages = languages or Languages()` into a lazy `@property`, matching the real upstream
commit's described mechanism exactly. See
[`code-change-proposal.diff`](code-change-proposal.diff). Validated against the target repo's own
real unit tests, run twice (before and after the change) via `python utest/run.py -q <dir>`:

| Suite | Before | After |
| --- | --- | --- |
| `libdoc` | 47/47 pass, 1.824s | 47/47 pass, 0.495s |
| `running` | 362/362 pass, 14.714s | 362/362 pass, 9.400s |

Both suites pass identically before and after — real, measured non-regression evidence. The
wall-clock drop is directionally consistent with the real issue's reported "~50%" improvement but
is **not** a rigorous reproduction of it: that figure came from profiling a 10,000+-keyword library
with `pyinstrument`; this is a small unit-test suite's wall-clock time, a much noisier signal not
controlled for machine load, warm caches, or test ordering. Reported as a weak, directionally
consistent corroboration only — not claimed as a measured performance benchmark. The dogfood
clone's `typeconverters.py` was reverted to its pinned `v7.1.1` original after capturing the diff,
so the clone still represents the pinned upstream baseline for anyone reproducing this case.

## 9. Outcome

Real, committed artifacts on real, pinned source: two markdown user-story outputs (Mode 1, Mode 2),
one approved context package, one reverse-index addendum, one validated code-change diff, 13×2 real
autoscaffolded `CONTEXT.md` files plus 2 `CEP-INDEX.md` routers, 16 real Playwright screenshots plus
2 machine-readable reports, and this case study — all produced on the real, pinned
`robotframework/robotframework` v7.1.1 clone. Committed to branch
`case-study/robotframework-wizard-ui` for human review — **not merged, no PR opened**, matching
every prior case study in this repo.

## 10. Limitations

- **Single feature, single run.** One issue, one case. Do not extrapolate "CEP always finds N extra
  stories" or "Phase B always tiers cleanly" from this alone.
- **Same agent authored both wizard runs and both consumption modes.** Not a blind A/B test — the
  agent that ran Phase B, built the package, and wrote Mode 1 also authored Mode 2's "bare ask,"
  constrained to only the literal task description by authoring discipline, not a structural
  guarantee the way two independently-blinded runs would be.
- **Autoscaffolded What-L2/How-L2's real contribution to this task was corroborating, not
  primary** — see §6. This case does not show Phase B content being sufficient on its own for
  issue-specific grounding; it shows what module-granularity content is and isn't good for.
- **The two harness-timing bugs were caught and fixed within this same session** — they are
  reported as real friction found during a from-scratch Playwright walkthrough, not as
  outstanding defects still present in `wizard_playwright_walkthrough.py` as committed.
- **The performance corroboration is weak and disclosed as such** (§8) — a unit-test wall-clock
  delta is not a rigorous reproduction of the real issue's large-library profiling result.
- **Dogfooding self-approval, no live human reviewer** — disclosed per standing convention, same as
  every other case in this repo.
- **New domain for this repo's case studies** (test-automation tooling), but still one ecosystem,
  one language (Python), one repo size band. Do not extrapolate to enterprise-scale monorepos or
  substantially different languages/architectures.

## 11. Lessons learned

- This is the first case study in this directory to drive `ult-cep-wizard`'s browser UI through
  Playwright rather than curl/HTTP, and the first to exercise `ult-autoscaffold-content`'s Phase B
  large-repo path directly. The Phase D wiring (empty box → autoscaffold prompt → real content, all
  reflected correctly in the UI before and after) held up under real browser automation with 0 page
  errors across both runs.
- Both timing bugs found were in the test harness, not the wizard — but both are worth folding into
  future Playwright-driven case studies as known patterns to guard against: poll for the async
  re-render before checking button/badge state, and launch `wizard_server.py` with `python -u` when
  piping stdout.
- The `graphify update` cwd/path-relativity footgun (§4) is a real, silent-failure-shaped usability
  gap — it produces a plausible-looking wrong tiering (all modules at Tier 3, in-degree 0) rather
  than an error. Worth a defensive check in `ult-codegraph`/`ult-autoscaffold-content` (e.g.
  validating that at least one graph `source_file` resolves under the expected repo-root before
  tiering) rather than relying on operators to notice a suspicious all-zero result — logged as a
  candidate governance-side improvement rather than fixed in this session (out of scope per the
  plan: no skill source-code changes here).
- The generative-benefit pattern from the two prior `demo-write-user-stories` case studies
  (ripgrep) reproduces a third time here, on a third independent ecosystem (Python test-automation
  tooling, vs. Rust CLI and the earlier UI-framework cases) — more specific actors, more grounded
  claims, and at least one fact (the real fix already existing upstream) that is genuinely
  unknowable from the bare task description alone.
- Autoscaffolded What-L2/How-L2 content's module-level granularity is a real, disclosed ceiling on
  its usefulness for narrow, issue-specific tasks — worth treating as an expected property of Phase
  B's design (docstring + tier + dependency edges is what it promises), not a defect, but worth
  making explicit in `ult-autoscaffold-content`'s own documentation so downstream consumers don't
  assume module-level content substitutes for issue-level detail.

## Reproduction steps

1. Clone `robotframework/robotframework` at tag `v7.1.1`
   (`10f24c2896dcd15bce591d76fd278aff64da418d`) to a short path (Windows: avoid nesting near/over
   260 chars), e.g. `C:\Users\pmishra\cep-dogfood-rf`.
2. Install CEP: `./install.sh --target <clone> --init-project` (or `install.ps1` on Windows).
3. `playwright install chromium` if not already present.
4. Launch the wizard: `python -u .github/skills/ult-cep-wizard/scripts/wizard_server.py <clone>`
   (note the printed `/exchange?token=...` URL).
5. Run [`wizard_playwright_walkthrough.py`](wizard_playwright_walkthrough.py) against that URL
   twice — once before running `ult-autoscaffold-content`, once after — to reproduce the
   before/after screenshot pair in [`wizard-screenshots/`](wizard-screenshots/).
6. Run `ult-autoscaffold-content` (conversationally, as the agent) against the empty
   `docs/requirements`/`org` targets. **Critical:** run `graphify update` with cwd set to the
   clone's `src/robot` directory (not the clone root), or module tiering will silently land
   everything in Tier 3 with `in_degree: 0` (§4).
7. In the clone: confirm the code graph — `graphify explain "TypeConverter"` → degree 44;
   `graphify affected ".converter_for()" --depth 2` → 11 real affected nodes.
8. In `context-engineering-oss`, on branch `case-study/robotframework-wizard-ui`: read
   [`libdoc-lazy-languages_user-story_20260813.yaml`](libdoc-lazy-languages_user-story_20260813.yaml)
   (the approved package) and verify `content_hash: b0489975` by re-running
   `.github/skills/ult-context-generate/scripts/content_hash.py` against it.
9. Run `.github/skills/demo-write-user-stories/SKILL.md` twice against the task description in §3
   — once with the package from step 8 loaded (Mode 1), once without (Mode 2) — and diff the result
   against [`mode-1-with-cep-output.md`](mode-1-with-cep-output.md) and
   [`mode-2-without-cep-output.md`](mode-2-without-cep-output.md).
10. Optional (stretch): apply [`code-change-proposal.diff`](code-change-proposal.diff) to the
    clone's `src/robot/running/arguments/typeconverters.py` and re-run
    `python utest/run.py -q libdoc` / `python utest/run.py -q running` to reproduce the 47/47 and
    362/362 pass counts from §8.
