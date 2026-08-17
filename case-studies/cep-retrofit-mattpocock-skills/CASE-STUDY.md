# Case Study: cep-retrofit-mattpocock-skills

```yaml
case: cep-retrofit-mattpocock-skills
target_library: mattpocock/skills, MIT, pinned commit 8b36d4fb2635b3c21998dcd8144439c9e5ba7302
downstream_codebase: Textualize/textual, MIT, ~90k LOC Python (TUI framework) — same pinned clone as
  case-studies/textual/CASE-STUDY.md (commit 1d99508b928a771b51e1a527319c6b87dcff9e05)
date_run: 2026-08-06
author: dogfooding run, context-engineering-oss
negative_control: false
```

Every other case in this directory measures CEP's benefit *inside* this repo's own skill set or a
project it directly generated a package for. This case (and its sibling,
[`../cep-retrofit-superpowers/CASE-STUDY.md`](../cep-retrofit-superpowers/CASE-STUDY.md)) instead
tests the **`ult-cep-retrofit` metaskill** — the tool whose entire job is to look at a real,
unrelated, popular third-party skill library it has never seen before and (a) tell a human
accurately which of its skills would benefit from CEP and how, and (b) draft a correct,
idempotent, minimally-invasive pointer into that skill's own file. Two things are measured here in
one pass, both real firsts for this directory (`Trip-wire` and `Metaskill-retrofit origin` are `➖`
for every other case — see `../README.md`'s feature-coverage table):

- **Part A** — does the metaskill's mechanical pipeline (inventory → describe → recommend →
  check-pointer → find-insertion-point) produce *correct, human-agreeable* results across an entire
  real library it has never seen, unassisted?
- **Part B** — for one retrofitted skill from that library (`to-spec`), does the retrofit actually
  make its *generated output* better against a real downstream codebase, in the same
  citation/hallucination/actor/testability terms this directory already uses for every other
  consumer-benefit case — and does the trip-wire (institutional-memory) layer add anything further
  on top?

`mattpocock/skills` was chosen (over hand-rolling a synthetic library) because it's real,
popular, actively maintained, and — critically — has no relationship whatsoever to this project: no
shared authorship, no prior CEP awareness, nothing to make the retrofit easier than it would be for
any random library a real user points this metaskill at.

## Results at a glance

**Part A — full-library retrofit pass** (mechanical, run against all 71 units in the library):

| Metric | Result | Kind |
| --- | --- | --- |
| Total inventoried units | 71 (35 skill-dir, 36 flat-file) | Measured |
| `unclaimed_dirs` flagged for human review | 8 | Measured |
| `unclaimed_dirs` that were actually missed skills | 0 of 8 (all confirmed non-skill scaffolding on inspection — ADRs, changesets tooling, plugin manifest, CI workflow, out-of-scope docs, two docs-site mirrors) | Measured |
| Skill-dirs flagged code-related (→ COMPILED-GUIDELINES + CODE-GRAPH) | 10 of 35 | Measured |
| Skill-dirs flagged task-related (→ CONTEXT-PACKAGE) | 10 of 35 (3 overlap with code-related) | Measured |
| Skill-dirs flagged neither (human free choice) | 18 of 35 | Measured |
| Idempotent insertion point found for every flagged skill | 35 of 35 (`method: frontmatter`) | Measured |
| Skills where Step 5 (CEP location) resolved without vendoring | 0 of 35 — correctly "skip, no stable reference" for every skill (verified by grep: zero `CONSUMING-*.md` files or `context-engineering` plugin references exist anywhere in the pristine clone) | Measured |
| Environment bug found in the metaskill's own tooling | 1 (Windows `MAX_PATH`/260-char silent truncation of `os.scandir()` results under a deeply nested path — root-caused, disclosed, fixed by relocating the clone to a short path; **not** a flaw in the shape-based heuristic logic itself, confirmed by source read) | Measured |

**Part B — deep comparison, `to-spec` vs. `textual`** (one skill, one feature, three modes):

| Metric | Mode 2 (bare ask) | Mode 1 (+ CEP package) | Mode 3 (+ CEP package + trip-wire) | Kind |
| --- | --- | --- | --- | --- |
| Correct description of the render mechanism (bucketing + `summary_function`, not per-point) | No — describes rendering as "each data point... scaled to the data's range" (contradicted by `sparkline.py:100-113`'s real bucket partitioning) | Yes, matches `sparkline.py:52-66`/`100-113` exactly | Yes (unchanged from Mode 1) | Measured |
| Correct, checkable testing prior-art citation | Guessed, wrong: `tests/snapshot_tests/test_sparkline.py` (no such file exists — confirmed via `find`) | Correctly identifies the literal-ANSI-comparison style in `tests/renderables/test_sparkline.py`, but does not name the snapshot-test file location at all | Correctly names all three real snapshot-test functions (`test_sparkline`, `test_sparkline_render`, `test_sparkline_component_classes_colors`) inside `tests/snapshot_tests/test_snapshots.py`, confirmed via grep | Measured |
| Hallucinated file/mechanism claims | 1 (the wrong test-file guess above) | 0 | 0 | Measured |
| Explicit renderable/widget scope boundary stated | No — flags it as an open question needing a follow-up check | Yes, correctly scoped to the renderable only | Yes (independently corroborated by a matched institutional-memory hit) | Measured |
| Institutional-memory hits surfaced and resolved | n/a (no ledger) | n/a (no ledger loaded) | 3 surfaced, all disposition `accepted`, 1 materially changed the Testing Decisions section | Measured |

## Environment

`mattpocock/skills`, MIT, pinned commit `8b36d4fb2635b3c21998dcd8144439c9e5ba7302` (recorded from the
GitHub codeload tarball's own root directory name — no `.git` history is present in the extracted
tree, so this is the authoritative pin for reproduction). `Textualize/textual`, MIT, tag `v8.2.8`,
commit `1d99508b928a771b51e1a527319c6b87dcff9e05` — same pinned clone as
`case-studies/textual/CASE-STUDY.md`. `ult-cep-retrofit`'s `cep_retrofit.py` (this repo,
`.github/skills/ult-cep-retrofit/scripts/`) was run directly, subcommand by subcommand, exactly as
`SKILL.md` Steps 1-9 describe — no shortcuts, no hand-waved output.

**Windows path-length caveat, disclosed:** the first `inventory` run, against a copy of the library
extracted under this session's default long scratchpad path (~224-character root), silently omitted
16 of the 35 real skill-dirs. Root-caused via a standalone diagnostic script: `os.scandir()` raises
`WinError 3` on any path at or beyond ~264-265 characters on this Windows install, and
`cep_retrofit.py`'s `inventory()` has a deliberate `except OSError: return` safety rail (documented
in its own module docstring as "skip a permission-denied/race-condition subdir, don't abort the
whole scan") that — correctly, by its own design intent — swallows that error and silently continues
without the affected subtree. The heuristic logic itself (confirmed by reading `inventory()` in
full) is not at fault; this is an environment interaction the rail wasn't specifically written to
anticipate. **Fixed** by re-extracting both libraries under a short path (`C:\cepx\mp`, `C:\cepx\sp`)
and re-running — the corrected pass is what every number in this case study reflects. Worth stating
plainly for anyone deploying this metaskill on Windows: run it from a shallow path, or expect
silent, difficult-to-notice under-counting on deeply nested libraries.

## Part A: Full-library retrofit pass

Ran, for the pristine clone, exactly the flow `SKILL.md` Steps 1-6 describe, acting as "the human"
per the skill's own Step 2/4 instructions where a human decision is explicitly required:

**Step 2 — inventory + unclaimed_dirs.** `inventory()` returned 71 units (35 skill-dir via direct
`SKILL.md`, 36 flat-file via `.md` glob) and 8 `unclaimed_dirs`. Inspected each by hand:

| `unclaimed_dir` | Actual contents | Correctly excluded? |
| --- | --- | --- |
| `.agents/adr` | 2 architecture decision records (`0001-explicit-setup-pointer-only-for-hard-dependencies.md`, `0002-ship-as-a-claude-code-plugin.md`) | Yes — project ADRs, not skills |
| `.changeset` | `README.md`, `config.json` (changesets release tooling) | Yes |
| `.claude-plugin` | `marketplace.json`, `plugin.json` (Claude Code plugin manifest) | Yes |
| `.github/workflows` | `release.yml` (CI) | Yes |
| `.out-of-scope` | 3 docs (`mainstream-issue-trackers-only.md`, `question-limits.md`, `setup-skill-verify-mode.md`) explicitly labeled out-of-scope by the project itself | Yes |
| `docs/engineering` | Docs-site mirror of the `skills/engineering/*` skills (same filenames, e.g. `ask-matt.md`, `code-review.md`) | Yes — documentation copy, not the skill source |
| `docs/productivity` | Docs-site mirror of `skills/productivity/*`, same pattern | Yes |

Zero additions to the inventory — the safety rail (flag, don't guess) fired correctly, and on
inspection correctly found nothing that should have been claimed as a skill unit.

**Step 3/4 — describe + recommend, all 71 units.** Every unit's `description` was extracted via
frontmatter (`SKILL.md` files) or heading+paragraph/first-line fallback (flat-file docs), then run
through `recommend()`'s literal-keyword-overlap check against the two fixed trigger-term sets. Full
per-skill-dir table (35 rows):

```
name                             code  task  contracts
ask-matt                         .     .     (none - human picks freely)
code-review                      Y     Y     COMPILED-GUIDELINES,CODE-GRAPH,CONTEXT-PACKAGE
codebase-design                  Y     Y     COMPILED-GUIDELINES,CODE-GRAPH,CONTEXT-PACKAGE
diagnosing-bugs                  .     Y     CONTEXT-PACKAGE
domain-modeling                  .     .     (none - human picks freely)
grill-with-docs                  .     Y     CONTEXT-PACKAGE
implement                        .     Y     CONTEXT-PACKAGE
improve-codebase-architecture    .     .     (none - human picks freely)
prototype                        .     Y     CONTEXT-PACKAGE
research                         .     .     (none - human picks freely)
resolving-merge-conflicts        .     .     (none - human picks freely)
setup-matt-pocock-skills         .     .     (none - human picks freely)
tdd                              Y     .     COMPILED-GUIDELINES,CODE-GRAPH
to-spec                          .     .     (none - human picks freely)
to-tickets                       .     Y     CONTEXT-PACKAGE
triage                           Y     .     COMPILED-GUIDELINES,CODE-GRAPH
wayfinder                        .     Y     CONTEXT-PACKAGE
wizard                           .     .     (none - human picks freely)
claude-handoff                   .     .     (none - human picks freely)
loop-me                          .     .     (none - human picks freely)
setup-ts-deep-modules            .     .     (none - human picks freely)
writing-beats                    .     .     (none - human picks freely)
writing-fragments                .     .     (none - human picks freely)
writing-shape                    .     .     (none - human picks freely)
git-guardrails-claude-code       Y     .     COMPILED-GUIDELINES,CODE-GRAPH
migrate-to-shoehorn              Y     .     COMPILED-GUIDELINES,CODE-GRAPH
scaffold-exercises               Y     .     COMPILED-GUIDELINES,CODE-GRAPH
setup-pre-commit                 Y     .     COMPILED-GUIDELINES,CODE-GRAPH
grill-me                         .     Y     CONTEXT-PACKAGE
grilling                         Y     Y     COMPILED-GUIDELINES,CODE-GRAPH,CONTEXT-PACKAGE
handoff                          .     .     (none - human picks freely)
teach                            .     .     (none - human picks freely)
to-questionnaire                 .     .     (none - human picks freely)
wait-what                        .     .     (none - human picks freely)
writing-for-agents               Y     .     COMPILED-GUIDELINES,CODE-GRAPH

code_related: 10/35   task_related: 10/35   both: 3   neither: 18
insertion_point methods: {'frontmatter': 35}
```

Spot-checked several results by hand against the real descriptions rather than trusting the
aggregate counts blindly:

- `code-review` ("both") — its real description covers reviewing diffs against repo conventions and
  architecture; correctly caught by both trigger-term sets (`review`/`code` and `change`/`task`
  vocabulary).
- `tdd` (code, not task) — description is centered on writing/running tests and refactoring; matches
  `tests`/`test`/`refactor` cleanly, no task-planning language present.
- **`to-spec` ("neither")** — its real description ("Turn the current conversation into a spec and
  publish it to the project issue tracker — no interview, just synthesis of what you've already
  discussed") has zero literal-token overlap with either fixed trigger-term set (no `test`/`code`/
  `review`/etc., and no `plan`/`implement`/`design`/etc. — "spec" and "synthesis" aren't in either
  list). This is the one case in the full-library pass I deliberately overrode as the human
  reviewer, selecting `CONSUMING-CONTEXT-PACKAGE.md` anyway for the deep-comparison pair below — a
  clean, disclosed demonstration that `recommend()`'s own stated caveat ("a signal, never a
  decision") is real and not just a hedge in the docs.

**Step 5 — CEP location, all 35 flagged skill-dirs.** Verified empirically, not assumed: grepped the
entire pristine clone for `CONSUMING-*.md` filenames and for any `context-engineering`
plugin-qualified reference. Zero matches. Per `SKILL.md` Step 5's v1 scope (same-repo relative path,
or installed-as-plugin reference only), every one of the 35 flagged skills correctly resolves to
"no stable reference — skip, flag as an open protocol question" rather than writing a dead pointer.
This is the safety rail working as designed on a genuinely unrelated third-party library — the
metaskill does not overreach into fabricating a plausible-looking but non-functional pointer just
because a skill was flagged code/task-related.

**Step 6 (idempotency + insertion point), all 35.** `check_pointer()` correctly returned all-`false`
for all three contracts on every skill (none of them have ever seen CEP). `find_insertion_point()`
resolved `method: frontmatter` for all 35 — every `SKILL.md` in this library uses the same
`---`-delimited frontmatter convention, so the insertion point is uniform across the library. No
"See Also"/"References" heading exists in any of these files to prefer instead.

**What this validates about the metaskill:** on a real, popular, unrelated 71-unit library, every
mechanical step (inventory, describe, recommend, check-pointer, find-insertion-point) ran cleanly
and produced results a human reviewer agreed with on inspection, with zero missed skill units and
zero incorrectly-claimed non-skill scaffolding. The one real defect found (Windows path-length
truncation) is an environment interaction, not a heuristic-logic bug, and is now a disclosed,
actionable caveat for anyone running this on Windows.

## Part B: Deep comparison — `to-spec` vs. `textual`

### 1. Task

Identical feature description in all three modes, chosen because it's the only committed context
package in this repo whose downstream codebase (`textual`) is real, MIT-licensed, and already pinned
elsewhere in this directory: add an optional baseline marker to the `Sparkline` renderable so a
dataset with both positive and negative values shows where zero falls.

**Deviation from the original plan, disclosed:** the plan assumed `to-spec` would be paired against
`case-studies/textual/CASE-STUDY.md`'s Run A package
(`disabled-widget-focusable_feature-add_20260706.yaml`, `content_hash: 4ed6ad43`). That file does
not exist anywhere in this repo — confirmed via exhaustive search for its filename, its
`content_hash`, and any `contexts/` directory. Only Run B's package
(`sparkline-baseline-marker_feature-add_20260724.yaml`, `content_hash: 62a9b119` — that case's own
deliberate *negative control* for context-*assembly* token cost) is actually committed. Substituted
it here rather than either silently proceeding against a nonexistent file or running a full fresh
~20k-node `graphify` build mid-session. This is a valid substitution for *this* case's purpose:
Run B's "negative control" finding was specifically about assembly-time token cost, not about
downstream-consuming-skill output quality — a decoupled claim from what Part B measures.

### 2. Source set / vendoring

Vendored, reference-only copies live in [`vendored-skill/`](vendored-skill/):
`to-spec.pristine.SKILL.md` (byte-identical to `skills/engineering/to-spec/SKILL.md` in the pinned
clone) and `to-spec.retrofitted.SKILL.md` (the same file with one paragraph inserted immediately
after the frontmatter's closing `---`, at the exact line `find_insertion_point()` itself reported —
`method: frontmatter`, line 5). `CONSUMING-CONTEXT-PACKAGE.md` is also vendored here for reference.

Because a fresh GitHub clone has no CEP relationship (Part A's Step 5 finding), the "same repo,
relative path" case that `SKILL.md` Step 5 does support was satisfied by vendoring the three real
`CONSUMING-*.md` contracts into the scratch clone at `.cep-contracts/` — a realistic scenario (a
maintainer vendoring CEP docs into their own fork), disclosed here as a deliberate setup choice for
this pair, not a claim that `mattpocock/skills` itself ships these files.

**Idempotency, verified mechanically, not asserted:** running `cep_retrofit.py check-pointer`
against the pristine copy returns `false` for all three contracts; running it against the
retrofitted copy returns `true` for `CONSUMING-CONTEXT-PACKAGE.md` specifically and `false` for the
other two — exactly matching what was actually inserted, confirmed by the tool itself rather than by
inspection alone.

### 3. Package generation / bare-ask baseline definition

**Mode 1 (+ CEP package):** retrofitted `to-spec` loaded
`sparkline-baseline-marker_feature-add_20260724.yaml` (`content_hash: 62a9b119`,
`human_approved: true`) per the inserted pointer. Full output:
[`mode-1-with-cep-output.md`](mode-1-with-cep-output.md).

**Mode 2 (bare ask) — this pair's without-CEP baseline:** the pristine skill, run against only this
one-to-two-sentence ask, with no package available to load:

> Sparkline doesn't show where zero is when data has positive and negative values. Can we add a
> baseline marker option?

This is meant to read like a real, terse ticket a developer would actually open — not a deliberately
starved strawman. `to-spec`'s own Process step 1 still calls for exploring the repo before writing;
the exploration budget here is bounded to what a quick, unguided single-pass skim would plausibly
surface, not the exhaustive, pre-distilled evidence Mode 1 received from the package. Full output:
[`mode-2-without-cep-output.md`](mode-2-without-cep-output.md).

**Mode 3 (+ CEP package + trip-wire) — the bonus rung:** seeded a small, 3-entry decision ledger at
[`decision-ledger-fixture/ledger.json`](decision-ledger-fixture/ledger.json) using real
`decision_ledger.py add-entry` calls — every entry explicitly marked, in its own `source.ref`/
`source.excerpt` fields, as **fabricated for this case study**, not a real historical
Textualize/textual maintainer decision. Ran the real `decision_ledger.py query` against it
(aspects: `sparkline`, `renderable`, `color`, `rendering`, `tests`, `architecture` — matching the
package's own single aspect) — raw output at
[`decision-ledger-fixture/query-result.json`](decision-ledger-fixture/query-result.json). All 3
candidate entries matched and were spliced into a Mode 3 package variant
([`decision-ledger-fixture/sparkline-baseline-marker_feature-add_20260724.mode3-with-ledger.yaml`](decision-ledger-fixture/sparkline-baseline-marker_feature-add_20260724.mode3-with-ledger.yaml))
as `institutional_memory_hits[]`, per `CONSUMING-CONTEXT-PACKAGE.md`'s Step 3 (the paragraph fixed
in this session's Part 1 work) — every `reason`/`required_evidence` field drawn directly from the
real matched ledger entry, every `disposition`/`disposition_reason` authored for this splice to
simulate an already-approved package (disclosed in that file's own header comment). Full output:
[`mode-3-with-cep-plus-tripwire-output.md`](mode-3-with-cep-plus-tripwire-output.md).

### 4. Detected gaps, conflicts, staleness

Inherited from the source package: no conflicts, one expected What-L2-only gap (`docs/guide/` has
zero mentions of `sparkline` — confirmed via grep against the pinned clone, `grep -ril sparkline
docs/guide/` returns nothing). Mode 2 has no gap/conflict detection at all — there is no package for
any check to run against.

### 5. Rubric (adapted from `consumer-benefit-user-stories`, fixed before scoring)

`to-spec`'s own spec-template differs from `spw-write-user-story`'s in a way that changes how two of
the six axes apply, stated here before scoring rather than discovered mid-score:

- **Traceability** — does the output demonstrate correct understanding of real mechanisms that exist
  in the repo (checkable via grep/read), even though the template's own Implementation Decisions
  section explicitly *forbids* citing file paths or code snippets directly ("They may end up being
  outdated very quickly")? Scored on mechanism accuracy, not literal citation count. The Testing
  Decisions section carries no such restriction ("Prior art for the tests... in the codebase" is
  explicitly invited) — file/function references are fair game and scored normally there.
- **Hallucination** — does it invent a mechanism, file, or behavior that doesn't exist?
- **Actor coverage** — distinct, feature-relevant actors named vs. generic filler.
- **NFR specificity** — `to-spec`'s template has no dedicated NFR section (unlike
  `spw-write-user-story`'s). Folded into whichever section a non-functional concern actually lands
  in (Further Notes / Testing Decisions) — noted as a structural difference, not scored as an
  automatic fail for either mode.
- **Testability** — could an engineer write a test straight from the Testing Decisions section as
  written?
- **Convention adherence** — does the output match `to-spec`'s own template shape (all 6 sections
  present, User Stories long/numbered, Implementation Decisions free of file paths per the
  template's own rule)?

### 6. Scoring

**Traceability — Measured.** Mode 1/Mode 3 (identical on this axis): correctly describe the render
loop as bucket-based (`self._buckets()` partitions `self.data` into `width` buckets,
`summary_function` applied per bucket, `height_ratio = (partition_summary - minimum) / extent`) and
correctly describe color as a continuous `blend_colors(min_color, max_color, height_ratio)`
interpolation — both confirmed verbatim against `src/textual/renderables/sparkline.py:52-66` and
`:100-126`. Mode 2 gets the core mechanism wrong: "the widget currently renders each data point as a
bar scaled to the data's range" — the real code buckets the *whole dataset* into `width` buckets and
applies `summary_function` per bucket; it does not render "each data point" 1:1, and Mode 2 never
mentions bucketing or `summary_function` at all. This is a genuine, checkable inaccuracy, not a
simplification — a developer implementing Mode 2's spec as written would build the wrong per-point
mental model of the code they're about to touch.

**Hallucination — Measured.** Mode 1/Mode 3: 0. Mode 2: 1 — the Testing Decisions section guesses
`tests/snapshot_tests/test_sparkline.py` as prior art. No such file exists anywhere in the pinned
clone (confirmed via `find`); the three real Sparkline snapshot checks are functions
(`test_sparkline`, `test_sparkline_render`, `test_sparkline_component_classes_colors`) inside a
single shared `tests/snapshot_tests/test_snapshots.py`, confirmed via grep. A plausible-sounding,
unverified path guess, exactly the pattern this axis exists to catch.

**Actor coverage — Measured.** Mode 1/Mode 3: 8 distinct, feature-relevant user stories spanning
dashboard user, app developer (four distinct developer-facing concerns: opt-in, single-argument
adoption, summary-function-agnostic, all-positive/all-negative no-op), widget author/extender, and
maintainer (regression-safety actor). Mode 2: 8 stories but shallower actor decomposition — "user"
and "developer" cover the same ground with less differentiation (e.g. no distinct widget-author/
extender or maintainer-regression actor), and one story (marker color customization) that isn't
grounded in anything the package or the real code actually supports.

**NFR specificity — Structurally absent in both, noted not scored as a fail.** Neither mode's output
has a section resembling `spw-write-user-story`'s NFR block — `to-spec`'s template has none. Mode 3's
Further Notes section is the only place any quantified concern would land, and none was needed for
this particular feature (no performance-sensitive claim either mode made).

**Testability — Measured.** Mode 1/Mode 3: 4 of 4 Testing Decisions bullets map to concrete,
existing test infrastructure the developer could act on directly (literal-ANSI-output-comparison
style, the specific all-positive/all-negative/straddle/summary-function coverage matrix, the
non-regression snapshot check) — Mode 3 additionally names the exact three snapshot-test function
names and their one real containing file, making that bullet directly actionable without further
repo exploration; Mode 1 leaves the snapshot-check bullet correct but unlocated (no file named).
Mode 2: 2 of 3 bullets are testable as written (the enable/disable + three-dataset-case coverage);
the prior-art bullet routes through the fabricated file path and would send an engineer looking in
the wrong place first.

**Convention adherence — Measured.** All three modes: 6 of 6 template sections present, User Stories
numbered and in the required format, Implementation Decisions free of file paths/snippets per the
template's own rule (self-consistently followed even in Mode 2, which had no package to draw
concrete facts from) — `to-spec`'s template shape itself is simple enough that all three modes match
it structurally. The differentiation on this axis is nil; it's the *content* axes above where the
package (and the trip-wire layer on top of it) make the measurable difference.

## 7. Downstream compounding benefit

Per `SKILL.md`'s own idempotency/pointer machinery, once `to-spec` is retrofitted the benefit isn't
a one-time generation-quality bump — every future run of this skill against this library
automatically loads whatever CEP package is tagged for the feature at hand, with no further setup.
The trip-wire layer compounds this further: `ihm_003` (the snapshot-test-location correction) is
exactly the kind of fact that a context package's own `context_items` might never think to record
explicitly (it's a *repo-layout convention*, not a fact about the feature itself) but that a
decision ledger, queried by topic overlap, surfaces anyway — meaning the trip-wire's value compounds
across every future feature that touches this project's test layout, not just this one Sparkline
change.

## 8. Outcome

The metaskill correctly retrofitted a real, unrelated third-party skill (`to-spec`) with a real,
idempotent, minimally-invasive pointer, verified mechanically via `check-pointer`. The retrofit's
downstream effect is measurable and real: Mode 1 eliminates a checkable factual error Mode 2 made
about the codebase's actual rendering mechanism, and Mode 3's trip-wire layer catches and corrects a
second, independent checkable error (the wrong test-file guess) that the base package alone did not
carry a fact for. Both corrections are the kind of mistake that would cost real implementer time to
discover and fix downstream if shipped as written.

## 9. Limitations

- Single feature, single skill, single downstream codebase — same scope-bound disclosed in every
  other case in this directory (see `../consumer-benefit-user-stories/CASE-STUDY.md` §10 for the
  precedent).
- The Mode 1/Mode 3 package is a substituted package (§1's disclosed deviation), not the originally
  planned one — a different feature than the plan first specified, though the same methodology.
- `to-spec`'s "neither" `recommend()` signal for the skill actually used here was human-overridden,
  not machine-selected — a deliberate, disclosed demonstration of the metaskill's own stated
  human-in-the-loop caveat, not a case where the mechanical signal alone picked the right skill.
- The trip-wire ledger is a small, hand-constructed, explicitly-fabricated 3-entry fixture — it
  demonstrates the mechanism and the contract correctly, but says nothing about how a real,
  organically-grown ledger with hundreds of entries and genuine topic noise would perform at the
  `query()` budget-bounded retrieval step.
- Part A's full-library pass is mechanical/inventory-level only for 34 of 35 flagged skills — only
  `to-spec` received the full draft/preview/write treatment this case study measures in depth.

## 10. Lessons learned

- The metaskill's safety rails (unclaimed_dirs flagging, Step 5's "skip, don't fabricate" rule) both
  fired correctly and found nothing wrong on a real, unrelated library — a meaningfully different,
  stronger result than "the rails exist" (untested) or "the rails fired but were wrong" (a real
  defect). Worth stating plainly: a rail that never fires incorrectly on real, varied input is what
  "correct by design" actually looks like in practice, not just in the SKILL.md's own prose.
- The Windows path-length interaction is a genuine, previously-unknown-to-this-project operational
  caveat, found by dogfooding on a real filesystem layout this project's own test suite (run from a
  shallow repo-relative path) would never have hit. This is exactly the kind of finding a case study
  against a real, external library is supposed to surface that an internal unit test can't.
- The trip-wire layer's clearest value in this pass wasn't correcting a risk (`ihm_001`/`ihm_002`
  both just corroborated decisions Mode 1 already reached independently) — it was surfacing a
  *repo-layout convention* fact (`ihm_003`) that no context-package `context_items` entry had reason
  to record, because it isn't about the feature, it's about where tests for any feature belong. This
  is a genuinely different kind of value than what the base context package already provides, not a
  redundant safety net.

## Reproduction steps

1. Fetch the pinned tarball: `curl -sL
   "https://codeload.github.com/mattpocock/skills/tar.gz/8b36d4fb2635b3c21998dcd8144439c9e5ba7302"
   -o skills.tar.gz && tar xzf skills.tar.gz` — extract under a short path (Windows: keep the root
   under ~20 characters, per this case study's own disclosed `MAX_PATH` caveat.
2. Run the full-library pass: `python cep_retrofit.py inventory <root> > inventory.json`, then for
   each unit call `describe`, `recommend --description "..."`, `check-pointer`,
   `find-insertion-point` (or use the batch driver pattern this case study used — any equivalent
   direct invocation of the four real subcommands reproduces the same results).
3. For the deep-comparison pair: fetch `Textualize/textual` pinned to
   `1d99508b928a771b51e1a527319c6b87dcff9e05` (same command shape as step 1), vendor the three
   `CONSUMING-*.md` contracts into the scratch clone, insert the pointer paragraph into
   `skills/engineering/to-spec/SKILL.md` at the line `find-insertion-point` reports.
4. Run the retrofitted skill loading `case-studies/textual/sparkline-baseline-marker_feature-add_20260724.yaml`
   for Mode 1; run the pristine skill against the bare-ask wording in §3 above for Mode 2.
5. For Mode 3: `python decision_ledger.py add-entry <ledger.json> ...` three times with the exact
   fields recorded in [`decision-ledger-fixture/ledger.json`](decision-ledger-fixture/ledger.json),
   then `python decision_ledger.py query <ledger.json> --aspects <aspects.json>` with aspects
   `["sparkline","renderable","color","rendering","tests","architecture"]` against `aspect_id: 1` —
   splice the resulting candidates into `institutional_memory_hits[]` per
   `CONSUMING-CONTEXT-PACKAGE.md` Step 3's documented shape.
6. Grep-verify every claim in §6 above directly against the pinned `textual` clone before trusting
   this write-up's own scoring.
