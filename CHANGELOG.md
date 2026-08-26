# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project uses simple `MAJOR.MINOR.PATCH`
versioning without a formal SemVer API-compatibility guarantee yet (see [`ROADMAP.md`](ROADMAP.md)).

## [Unreleased]

### Added

- **`CONCEPT.md`**: a new conceptual/mental-model document, meant to be read before
  `PROTOCOL.md` — placed first in `README.md`'s nav line and pointed to from `PROTOCOL.md`'s
  intro. Includes a "Contents" table linking to all 22 sections, and short "How CEP does this"
  cross-reference pointers on the sections backed by a shipped mechanism (layers, How-L1/L2,
  Constraints, Trip-Wires, Gap/Conflict/Staleness, Human Approval, the Context Package, context
  reuse, and the addendum mechanism for context lifecycle).
- **`ult-cep-wizard`**: `CONCEPT.md` is now the first entry in the in-app docs viewer's nav,
  ahead of Protocol — same read-before-Protocol ordering as the README and PROTOCOL.md pointer.
- **`PROTOCOL.md` §2**: a new "Why there's no How-L3" note explaining, as normative text, that
  the structural/pattern-level part of "how similar work has been done" is already surfaced by
  What-L3's codegraph, so a separate How-L3 tier would duplicate it; workflow/process content
  belongs under How-L2 instead. Layer count and boundaries remain an implementation choice, not
  a protocol requirement.
- **`FAQ.md`**: a new 24-question FAQ covering getting started, core concepts, day-to-day usage,
  maturity/piloting status, extending CEP, and evidence/limitations — cross-linked to
  `CONCEPT.md`, `PROTOCOL.md`, `GLOSSARY.md`, and the case studies. Available in `ult-cep-wizard`'s
  in-app docs viewer as a new "FAQ" nav entry (last in the nav order), filling a placeholder that
  was already reserved for it in the UI.
- **`ult-onboarding-index`** (new skill). Discovers which CEP-managed content already exists in a
  target repo (compiled guidelines, context packages, decision ledger, What/How layer docs) via
  existence checks against `layout-slots-registry.yaml`-resolved paths, then writes one canonical
  root `AGENTS.md` onboarding index plus thin per-tool pointer stubs
  (`.github/copilot-instructions.md`, `CLAUDE.md`, `.cursor/rules/onboarding.mdc`) that link into
  it. Every write is a marked-block merge or an existence-gated whole-file write, never a blind
  overwrite — `install.sh`'s own `AGENTS.md` skill-catalog block is left untouched. Codex needs no
  separate stub, since its own root `AGENTS.md` is already its native onboarding format.
- **`ult-cep-wizard`**: the What/How boxes now list the actual files resolved into each box,
  grouped by L2/L1, instead of only the resolved directory path — the new `wizard_box_files.py`
  module (`list_files`, capped at `MAX_FILES_PER_PATH`) walks each resolved path and each
  `BoxPath` in `/api/status` now carries `files`/`total_file_count`/`truncated` alongside
  `path`/`source`. `wizard_stub_content.py`'s `_has_content()` now delegates to the same module
  instead of keeping its own duplicate walk, and its "run `ult-autoscaffold-content`" prompt copy
  now names that skill's newer artifact kinds (coding-standards, testing-guidelines,
  interface-boundary docs, tiered module depth).
- **`ult-autoscaffold-content`**: repo-wide `CODING-STANDARDS.md`/`TESTING-GUIDELINES.md`
  generation (existence-gated, Step 5c) and per-pair `interfaces/<module-a>-to-<module-b>.md`
  docs for graph-mode large-repo runs (Step 5d), grounded only in graph-observed
  relations/weight for that pair. Large-repo tiering also gains an explicit `probe-size`
  classification step, always stated to the user rather than picked silently, and per-module
  `CONTEXT.md` depth now varies by tier (`references/module-context-depth-by-tier.md`). New
  reference files (`generate-coding-standards.md`, `generate-interface-docs.md`,
  `generate-testing-guidelines.md`) and templates (`coding-standards-template.md`,
  `testing-guidelines-template.md`, `interface-boundary-template.md`, plus the existing
  overview/context templates split out from inline `SKILL.md` prose) back the three new
  artifact kinds. `compiling-project-guidelines` now auto-discovers this skill's How-L2 output
  and its `context-config.yaml`-resolved directory as additional guideline sources, and notes
  scaffold-generated drafts distinctly in its `Sources:` footer.

### Fixed

- **Private skill-library references scrubbed from public-facing content.** Several files
  named or linked skills that only exist in this maintainer's private, unpublished skill
  library — never shipped in this repo — as if they were real, installed producers/consumers:
  `layout-slots-registry.yaml`'s six illustrative `project_layout` slots (`plans_output`,
  `brainstorm_output`, `security_docs`, `security_report`, `project_plan_docs`, and their
  consumers) now use generic `example-*` names instead; four starter-kit drop-zone entries
  tied to those same private skills (`threat_modeling`, `secure_coding_guidelines`,
  `security_test_data`, `project_plan`) are removed outright, leaving only the one drop-zone
  (`project_guidelines`) actually read by a skill shipped here — `ult-repo-layout/SKILL.md`,
  `install.ps1`, and `install.sh` are updated to match (5 documented drop-zones → 1).
  `ROADMAP.md`'s PDF-ingestion item no longer describes `ult-read-pdf` as "this repo's existing
  PDF reader" (it isn't one — that's a private-repo tool); both candidate paths now correctly
  start from "no existing PDF reader here." `ult-cep-retrofit` and
  `ult-institutional-memory-distill`'s `SKILL.md`/script docstrings also drop private
  `CEP-1.0-ROADMAP.md` §-number citations that only resolve inside the maintainer's private
  design-doc set, in favor of self-contained prose. The mechanical `check_radisys_scrub.py`
  gate does not catch this class of leak (it greps for "Radisys"/telecom terms, not private
  skill names) — caught instead by a manual read-through of every touched file's diff.
- **`ult-institutional-memory-distill`'s frontmatter `name:` corrected** from the full
  `ult-institutional-memory-distill` to the bare `institutional-memory-distill` — `ult` is
  already this skill's `namespace:`, composed into the folder name and every invocation
  elsewhere in this repo (same split every other `ult-*` skill uses, e.g. `ult-repo-layout`'s
  `name:` is `repo-layout`); the old value duplicated the namespace inside the name itself.
- **`ult-repo-layout/SKILL.md`'s stale "Status: implemented — all 8 phases complete" sediment
  line removed**, along with several `§<N>`/`D21 §16.6, Phase 3d`-style citations into the
  private design-doc set scattered through its prose — replaced with self-contained
  explanations of the same behavior, or a pointer to `references/phase-history.md` for
  maintainers who want the historical build sequence.
- **`cep-retrofit-mattpocock-skills` case study restored.** `README.md` and `PROTOCOL.md` §8 have
  cited this write-up as live evidence since it was first published (`e6295a9`), but the
  `CASE-STUDY.md` file itself was later removed locally (`90a5cf46`) to make room for an unrelated
  Copilot cross-runtime experiment, and that removal was never reverted — leaving both citations
  pointing at a file that doesn't exist. Restored `CASE-STUDY.md` from its original commit, along
  with its own supporting evidence artifacts — `mode-1/2/3-*-output.md` and
  `decision-ledger-fixture/*.json`/`.yaml` — since those back the write-up's "Measured" claims
  about exact model output and trip-wire hits, and this repo has no other way to independently
  check them (unlike the claims checkable against the real `Textualize/textual` target repo).
  `vendored-skill/*.SKILL.md` (mattpocock's own third-party skill content, not this project's
  generated output) was deliberately left out — that's a separate, disclosed-obsolete Copilot
  experiment's concern, not this case's own supporting files. Also fixed an unrelated pre-existing
  bug found while verifying the fix: `PROTOCOL.md` §7/§8's case-study links used an extra `../`
  even though `PROTOCOL.md` lives at the repo root, breaking both the mattpocock and superpowers
  citations there. `case-studies/README.md`'s two summary tables and its closing paragraph, which
  previously said this write-up was "deliberately not kept," now include and correctly describe it.
- **Doc drift from the last two case studies and two wizard phases, closed across six files.**
  `README.md`, `EVIDENCE.md`, and `EVIDENCE-METHODOLOGY.md` still described the generation-quality
  evidence as a single vendored consuming skill run once or twice; it's now been run four times,
  across two independently-designed consuming skills (`spw-write-user-story` and the ground-up
  `demo-write-user-stories`) and four domains — the new `ripgrep-trim-user-stories` and
  `robotframework-wizard-ui` case studies are folded into all three docs' tables/prose, along with
  a disclosed tooling-only side-quest (`ripgrep-crlf-replace-terminator`, not a full protocol case)
  near the retrieval-cost table. `README.md`'s "five real-codebase cases" claim is corrected to ten,
  and a stale "seven prior cases" reference is corrected to eight. `CONFORMANCE.md` §4 now lists
  Trip-wire (`PROTOCOL.md` §7) and CEP-retrofit (`PROTOCOL.md` §8) among the optional capabilities —
  both real, shipped, piloting-status, and previously undocumented there.
  `consuming-a-context-package.md` gains a special-handling callout for `institutional_memory_hits[]`
  entries, mirroring the existing `what_l1_fallback: true` one, since a trip-wire hit's disposition
  is consumer-relevant in the same way. `project-setup-context-engineering.md`'s wizard description
  no longer says Phase 0 is "browse-only" — `ult-cep-wizard` has run a real in-browser Discover step
  and applied pending layout decisions since D24 Phase 1/2 shipped. `README.md` also gains a
  top-nav link and a Quickstart pointer to `FAQ.md`, which existed and was wired into the wizard's
  nav but wasn't linked from either. Verified: every new/changed relative link and heading anchor
  across all six files resolves against the wizard's own `_slugify`, all six render cleanly through
  `wizard_markdown.render()`, the full wizard test suite (371 tests) and all four catalog gates
  stayed green.
- **`ult-repo-layout/SKILL.md`'s slot-registry prose was out of sync with `SLOT_REGISTRY`
  itself** — it said "eight" path-slots while the registry actually defines eleven;
  `decision_ledger`, `autoscaffold_content_state`, and `autoscaffold_content_index` (added
  alongside their owning skills) were never folded into the documented `init` walkthrough, so a
  user following that walkthrough exactly would never register them. Corrected the count and
  added the three slots' own descriptions. Added a regression test
  (`TestSkillMdSlotRegistryTableConsistency`) that parses SKILL.md's "Slot registry" table
  directly and diffs its keys against `SLOT_REGISTRY`, so this class of doc/code drift fails a
  test run instead of sitting undetected.
- **`ult-cep-wizard`'s Trip-wire box had no "run this yourself" guidance card**, unlike What/How/
  Guidelines, which all point the user at the skill that populates them — a Trip-wire ledger
  that's missing or still empty (initialized but zero entries) left the user with no onboarding
  path at all for that box. Added `tripwire_card()` (`wizard_stub_content.py`), wired into
  `/api/status` and the existing stub-card rendering in `wizard.js`/`index.html`. Its guidance is
  deliberately different in kind from the other three cards: `ult-institutional-memory-distill`
  needs a human to choose and confirm real source streams before writing anything, so the card
  points at starting that human-in-the-loop process rather than promising the skill will write
  the file unattended.
- **`ult-cep-wizard`'s in-app docs viewer served the target repo's own README under CEP
  branding once installed into a consumer repo.** `wizard_docs.py`'s `install_root()` resolves to
  "whatever repo this skill's directory sits under" — correct while self-testing the wizard
  against its own repo, but once the skill directory is copied into an unrelated consumer repo
  (the normal way it reaches anyone else's project), it silently resolves to *that* repo's root
  instead, and the docs viewer would list and render whatever `README.md`/case-study-shaped
  content happened to exist there as though it were CEP's own documentation. Added
  `_bundle_verified()`: `list_docs()` now returns nothing at all unless both `CONCEPT.md` and
  `PROTOCOL.md` are present together at the resolved root — two files distinctly named after CEP
  itself, unlike `README.md` alone, which nearly every repo has. No frontend changes were needed:
  `wizard.js`'s nav already disables any doc button missing from `/api/docs`'s response.
- **`ult-cep-retrofit`'s inventory over-classified ordinary repository files as retrofit-skill
  candidates.** Root control files (`AGENTS.md`, `CLAUDE.md`, `CONTEXT.md`) and well-known
  repository-governance directories (`adr/` — Architecture Decision Records, `.changeset/`,
  `.out-of-scope/`) were being swept in by the existing flat-file/shape-based heuristics purely
  because they happen to hold `.md` files, presenting a human reviewer with a large, noisy
  mixed list of genuine skill candidates alongside governance/release content that was never
  meant to be retrofitted. Extended `cep_retrofit.py`'s existing `_NON_SKILL_FLAT_NAMES` and
  `DEFAULT_EXCLUDES` sets — the same class of broadly-known, non-library-specific naming
  convention already used there for `README.md`/`LICENSE.md`/`node_modules`/`.git` — to cover
  these too.

## [0.5.0]

33 commits since v0.4.0. Headline: two skills go from nonexistent to fully shipped —
`ult-autoscaffold-content` (fills empty-case skeleton content a repo's own layout can't supply,
in four phases: generation, large-repo triage, optional domain-pack consumption, wizard/CI
integration) and Journey 3 of `ult-cep-wizard` (mechanizes `ult-cep-retrofit`'s read → draft →
apply flow as a second, orthogonal wizard journey, also in four phases). `ult-layout-wizard` is
renamed `ult-cep-wizard` and gains a full visual design pass, a guided brownfield-onboarding
mode, and an in-app docs viewer. `ult-repo-layout` gains a standalone
`layout_decision_grammar.py` module. All of it is exercised together against a real, unrelated
55K-line OSS repo (`robotframework-wizard-ui` case study) plus two more UI bugs found via direct
Playwright walkthroughs and fixed.

### Added

- **`ult-autoscaffold-content` (new skill, four phases).** Generates skeleton content for the
  "empty case" — files a repo's own layout conventions can't supply on their own (a missing
  `CONTRIBUTING.md`, an undocumented module, a domain glossary with no source of truth) — so
  `ult-repo-layout`'s scaffolding doesn't leave placeholder gaps for a human to fill by hand.
  - **Phase A** — empty-case content generation: detects which scaffolded slots have no real
    source material behind them and generates first-draft content for each.
  - **Phase B** — large-repo triage/tiering + resume/checkpoint: `scaffold_state.py` tiers
    candidate modules by `in_degree` (graphify-derived), and a durable `TRIAGE-STATE.json`
    lets a long run against a large repo survive an interruption and resume rather than
    restart.
  - **Phase C** — domain-pack strawman schema + optional consumption: an optional structured
    domain-pack input a project can supply to steer generated content, consumed only if
    present.
  - **Phase D** — wizard integration + CI wiring: surfaced inside `ult-cep-wizard`'s
    onboarding flow and wired into `.github/workflows/ci.yml`.
- **`ult-cep-wizard`: Journey 3 (consumer/retrofit) wizard UI, shipped in four
  independently-mergeable phases.** Mechanizes `ult-cep-retrofit`'s read → select → draft →
  apply flow as a second, orthogonal wizard journey (not a fifth `wizard_onboarding_state`
  value — retrofit answers "does this other skill library know how to use what the project
  produced," a different question from the existing layout-onboarding journey). Two
  deliberate v1 scope limits, both documented rather than silently assumed: no LLM in the
  loop (every drafted sentence is a fixed, contract-specific template, always rendered into
  an editable textarea for a human to finish); retrofit target must be a subdirectory of the
  project's own repo root (the same containment boundary the picker already enforces
  everywhere else — an out-of-repo target is a flagged future extension, not built now).
  - **Phase A** — read-only inventory view: `wizard_retrofit_inventory.py` batches
    `cep_retrofit.py`'s `inventory()`/`describe()`/`recommend()` for every discovered unit
    into one round-trip; `GET /api/retrofit/inventory` (session-gated, read-only); a new
    top-level "Retrofit a Skill Library" nav entry with a target picker, inventory table,
    and per-row recommendation badges/matched terms/contract checkboxes.
  - **Phase B** — reference resolution + draft + batch diff preview:
    `wizard_retrofit_draft.py` (pure `resolve_reference()`/`draft_insertion_text()`/
    `detect_contract_locations()`) and `wizard_retrofit_state.py` (durable
    `cache/cep-retrofit/RETROFIT-STATE.json`, modeled on `ult-autoscaffold-content`'s
    `TRIAGE-STATE.json` convention, so a multi-round-trip run against a large library
    survives a browser refresh or wizard restart); `POST /api/retrofit/select`,
    `POST /api/retrofit/draft`, `POST /api/retrofit/draft-override`,
    `GET /api/retrofit/state`; editable draft textareas and a collapsible per-file batch
    diff-preview view (context-before / inserted-block / context-after, pure string-slicing
    around the insertion point — no diff algorithm needed since every change is an
    insertion).
  - **Phase C** — write path: `wizard_retrofit_apply.py`'s `apply_unit()`/`apply_batch()`
    (fast-path skip on nothing staged, freshness re-check against the draft-time hash, a
    last-instant `check_pointer()` idempotency guard immediately before writing, atomic
    splice-write, per-unit exception isolation so one file's failure never aborts the
    batch); `POST /api/retrofit/apply` behind the existing three-gate mutating-route chain;
    the wired-up "Apply changes" button with a live per-unit result list and an
    "N retrofitted, M skipped, K failed" summary. **Widens the wizard's write surface** —
    previously two fixed CEP-owned artifacts, now any file under the project the target
    picker can reach — with a `SECURITY.md` entry landing in the same change describing what
    stays the same (containment, atomicity, the three-gate chain) and what's new (blast
    radius, the freshness re-check, the v1 in-repo-only limit).
  - **Phase D** — docs/housekeeping: new
    `.github/skills/ult-cep-wizard/references/wizard-retrofit-flow.md` (Journey-3 analogue of
    the existing onboarding-journey reference docs); `catalog/check_radisys_scrub.py`'s
    `SKILL_DIRS` extended to cover `ult-cep-retrofit`.
  - Exercised end-to-end via 87 new automated tests (63 pure-function/state unit tests across
    the inventory/draft/state/apply modules plus 24 real-bound-socket route-wiring tests,
    including one full happy-path walk verifying the target file's actual on-disk content) and
    manual Playwright walkthroughs against fabricated fixture libraries.
- **`ult-cep-wizard`: renamed from `ult-layout-wizard`, Phase 2 (guided brownfield onboarding),
  and a full visual design pass.** The rename reflects the wizard's scope having grown beyond
  layout-only onboarding (it now also drives retrofit — see above). Phase 2 adds a four-state
  router and `POST /api/discover` so a brownfield repo gets a guided, question-by-question
  onboarding flow instead of a blank form; a parallel greenfield (init) guide-only flow keeps
  new-project onboarding equally structured. Design pass: a redesigned top bar with consistent
  section widths, a refined color scheme, the approved CEP ribbon logo integrated into both the
  wizard topbar and `hero.svg`, and an in-app docs viewer (renders `case-studies/README.md` as
  the Case Studies landing doc, with back-navigation and escaped-pipe-aware Markdown table
  rendering).
- **`ult-repo-layout`: `layout_decision_grammar.py` extraction.** Pulls the layout-decision
  grammar used by both `discover_layers.py` and `wizard_e2e_check.py` out into its own
  standalone module, with CI and docs updated to match.
- **`case-studies/robotframework-wizard-ui`**: a new case study exercising the redesigned
  wizard's layout-onboarding UI and `ult-autoscaffold-content` Phase B against a real,
  unrelated 55K-line OSS repo (RobotFramework's `libdoc` lazy-languages feature).

### Fixed

- **`ult-cep-wizard` docs viewer: scroll position not reset between docs, and an
  ordered/unordered-list continuation-line bug that broke numbering.** Found via a manual
  Playwright walkthrough of the docs viewer: switching docs left scroll position wherever it
  was on the previous doc instead of resetting to the top; and a list item whose text wrapped
  onto an indented continuation line (the convention used throughout `PROTOCOL.md`) broke the
  list after the first item, restarting the browser's auto-numbering (`1./1./1.` instead of
  `1./2./3.`) because the continuation line didn't match the list-item pattern and each
  subsequent item started a fresh `<ol>`/`<ul>`.
- **`ult-autoscaffold-content` Phase B: silent tiering corruption on graphify cwd/path-relativity
  mismatch.** If `graphify update` ran from a different working directory than `scan --repo-root`
  expected, every `source_file` in `graph.json` carried a different leading path segment, so
  `scaffold_state.py`'s `_module_of()` extracted the wrong module name for every node — every real
  module silently defaulted to `in_degree: 0` and landed Tier 3, with no error or warning anywhere.
  Found and self-corrected during the `robotframework-wizard-ui` case study; confirmed a recurrence
  of the same cwd-relativity footgun already known to affect `graphify query`/`explain`/`affected`.
  `scan --graph-mode graphify` now cross-checks the graph's own module names against `--repo-root`'s
  real directories before tiering: zero overlap raises `GraphRepoRootMismatchError` (ERROR, exit 1,
  no state written); partial overlap below 50% is a non-fatal `WARNING`, printed to stderr
  immediately, persisted to `TRIAGE-STATE.json`'s `repo_scan.graph_module_overlap_warning`, and
  echoed in `render-index`'s `CEP-INDEX.md` output — surfaced wherever an operator looks, never
  silent.
- **`ult-cep-retrofit` inventory: returned target-relative paths instead of repo-root-relative**,
  breaking any downstream consumer (including the wizard's own inventory view) that assumed
  paths were relative to the repo root.
- Doc-accuracy corrections found via self-review: a stale D24 glossary row still describing
  Phase 0 as read-only after later phases shipped write behavior; a stale `SECURITY.md` Scope
  claim written before the retrofit write path went live; README/user-guide updates to reflect
  `ult-autoscaffold-content` and `demo-write-user-stories` now existing.

## [0.4.0]

21 commits since v0.3.0. Headline: two full protocol capabilities go from planned to shipped and
field-validated — trip-wire / institutional memory (a persistent decision ledger that surfaces
prior-rejected paths before an agent repeats them) and `ult-cep-retrofit` (a metaskill that brings
an existing third-party skill library under this protocol without vendoring or rewriting it),
exercised together end-to-end against a real, unrelated 62-unit library. Also closes out runtime
field-validation (Cursor is the fourth and last of the supported runtimes confirmed working
end-to-end), ships an installable Claude Code plugin package, and fixes a real Windows PowerShell
CLI-ergonomics bug found via a cross-runtime (GitHub Copilot) re-run of the retrofit experiment.

### Added

- **`EVIDENCE.md`**: a headline-first, shareable Evidence page condensing the README's "Measured
  impact" section, `EVIDENCE-METHODOLOGY.md`, and `case-studies/SYNTHESIS.md` into one entry point
  — leads with the cross-domain hallucination-recurrence finding (26 real citations vs. 0, the same
  fabricated concept recurring identically in two unrelated codebases) rather than the token-cost
  numbers, since that's the sharper trust argument. Links out to the existing tables rather than
  duplicating them as a second source of truth.
- **README hero updated to two-pillar positioning**: the "in practice" paragraph now leads with the
  hallucination-recurrence finding and links to `EVIDENCE.md`; a new closing sentence names context
  engineering as "the substrate for a QMS in agentic mode" and previews a planned trip-wire layer
  (institutional-memory / decision-ledger concept), explicitly gated "on the roadmap" — not shipped,
  not implemented, matching this repo's own disclosure conventions.
- **`ROADMAP.md` item 16 — Trip-wire**: a planned-capability entry (design complete, not yet
  implemented) for a persistent, project-scoped decision ledger that surfaces prior-rejected paths
  to a human before an agent repeats them. Full design/adversarial review targeted for `1.2.0`.
- **Claude Code plugin package**: `claude-plugin/` packages every real skill under `.github/skills/`
  (`compiling-project-guidelines`, `demo-write-user-stories`, `ult-cep-retrofit`, `ult-codegraph`,
  `ult-context-generate`, `ult-institutional-memory-distill`, `ult-repo-layout`) as an installable
  Claude Code plugin, generated by `catalog/export_claude_plugin.py` from `.github/skills/` (the
  single source of truth) so the package can't silently drift from the real skills — `--check` runs
  in CI on every push. `demo-consume-context` is deliberately excluded — its own frontmatter marks it
  "do NOT use for real feature work". Listing copy foregrounds `ult-context-generate` as the skill to
  try first, the rest presented as supporting tools. Verified with a real local one-click install
  (`/plugin marketplace add` + `/plugin install`), not just `claude plugin validate`. **Not yet
  submitted to the public Claude Code marketplace listing** — that's a later, deliberate launch
  action, not a side effect of this package existing.
- **Cursor — field-validated** (closes [`ROADMAP.md`](ROADMAP.md) item 5): installed the real skill
  library into a scratch project via `install.ps1 -InitProject` and drove Cursor's chat directly.
  Positive-trigger prompt (worded against the rule's own `description`, not its name) correctly
  attached the `ult-context-generate` Agent Requested rule — Cursor read `SKILL.md`, ran the 4-question
  scope-clarification gate with context-aware recommended answers, produced real structured YAML
  context packages, and gated finalization on an explicit typed "approve" (correctly stamping
  `approved_by: - actor: human:<user>` and `generated_at`, matching the `approved_by` schema shipped
  in 0.3.0). Negative-control simple-lookup prompt correctly bypassed the rule entirely, per its own
  "Do NOT use for simple lookups" clause. Full report: [issue #35](https://github.com/linkpranay-ai/context-engineering-protocol/issues/35#issuecomment-5150441056).
- **Trip-wire — implemented** (closes the build half of [`ROADMAP.md`](ROADMAP.md) item 16, previewed
  as planned-only above): `ult-institutional-memory-distill` ships a real, tested decision-ledger
  mechanism (`decision_ledger.py`: `add-entry`, `alias`, `advance-cursor`, `reject-source`, `query`,
  `disposition`, `show`; 33 passing tests) integrated into `ult-context-generate`'s Step 7.7, per
  [`PROTOCOL.md` §7](PROTOCOL.md#7-trip-wire--institutional-memory-decision-ledger-piloting). Every
  `revise`/`escalate` hit requires an explicit human disposition before the package's own approval
  gate closes — never auto-applied, never auto-suppressed, matching this protocol's existing
  conflicts-surface-never-auto-resolve rule. **Not yet field-validated against a real corpus of actual
  PRs/design docs/postmortems** — see the case study below for its first real exercise, against a
  small, explicitly-disclosed fixture ledger rather than real project history.
- **`ult-cep-retrofit`**: a new metaskill that brings an existing, third-party skill library under
  this protocol — deterministic union-of-heuristics inventory across both flat-file and
  skill-directory conventions, per-unit code/task classification, a `recommend()` step for which
  `CONSUMING-*.md` contract fits, and idempotent frontmatter-pointer insertion, all without silently
  vendoring or rewriting the third-party library's own instructions. 32 passing tests (2 skipped —
  symlink privilege, Windows-only). See
  [`PROTOCOL.md` §8](PROTOCOL.md#8-cep-retrofit--bringing-an-existing-skill-library-under-this-protocol).
- **New case study validates both of the above against a real, unrelated skill library**:
  [`cep-retrofit-superpowers`](case-studies/cep-retrofit-superpowers/CASE-STUDY.md) (`obra/superpowers`,
  MIT, 62 units, a pristine clone rather than this repo's own already-adapted copies of the same
  skills) — 0 misclassifications across all 62 units, plus a deep with/without-CEP comparison of one
  retrofitted skill's (`writing-plans`) generated output, plus trip-wire exercised on top. Real,
  grep-verified defects found in the pristine (no-CEP) baseline that the retrofitted run avoided
  (a duplicate AVP dictionary declaration; a fabricated test target). This is the first case to close
  the `Trip-wire` and `Metaskill-retrofit origin` columns in
  [`case-studies/README.md`](case-studies/README.md#feature-coverage)'s feature-coverage table,
  previously ➖ across all seven prior cases. Its own scoring pass also surfaced a disclosed, humbling
  finding — a `tier: revise` trip-wire hit's `required_evidence` field is load-bearing, not
  decorative; accepting one without checking it produced a confidently wrong bitmask value that the
  honest CEP-package placeholder had avoided. A second `ult-cep-retrofit` case against
  `mattpocock/skills` was run and then deliberately not kept in this repo — see this file's own
  entry below under "Removed" — so this release ships one metaskill-retrofit case study, not two.

### Fixed

- **Installer no longer leaks `__pycache__`/`.pytest_cache` into installed projects.** Both
  `install.sh` and `install.ps1` mirrored whatever was physically present in the source clone's
  working tree, gitignored or not — anyone installing from a clone where the test suite had been run
  locally would copy those build-artifact directories into every target project. Found during the
  Cursor field-test above. Fixed by excluding both at copy time (`robocopy /XD` on Windows, post-copy
  cleanup on the non-robocopy paths); `test_install_scripts.py`'s tree-comparison helper updated to
  match the corrected invariant (it previously required an exact file-for-file mirror, silently
  encoding the leak as correct behavior). [PR #37](https://github.com/linkpranay-ai/context-engineering-protocol/pull/37).
- **`CONSUMING-CONTEXT-PACKAGE.md` didn't document how to consume `institutional_memory_hits[]`.**
  A consuming skill reading an approved package had no documented contract for the field trip-wire
  writes — discovery, disposition-echo, and citation rules were all unspecified. Fixed with a new
  addendum giving that field the same contract shape every other package field already has;
  `ult-context-generate`'s own reference docs updated to match. Found and fixed during the
  `ult-cep-retrofit` case studies' Mode 3 (trip-wire) rung, before it could produce a
  silently-ignored field in a real consuming skill.
- **`recommend --description` silently mangled on Windows PowerShell for descriptions containing
  embedded double-quotes.** Found via a GitHub Copilot cross-runtime re-run of the
  `mattpocock/skills` retrofit (see "Removed" below): two real skills' frontmatter descriptions each
  contain an embedded `"..."`, which PowerShell's argument quoting silently truncated/mangled before
  `cep_retrofit.py` ever saw it, producing a false "neither" classification with no error surfaced.
  The classification heuristic itself was confirmed correct via an independent ground-truth
  re-derivation (fresh pinned clone, direct Python import bypassing all shell argument-passing).
  Fixed by adding `recommend --description-file <path>` as a required, mutually-exclusive
  alternative to `--description`, documented as the Windows-recommended default in both the script's
  module docstring and `SKILL.md`'s Step 4. 4 new regression tests.

### Removed

- **`case-studies/cep-retrofit-mattpocock-skills/`** — a second `ult-cep-retrofit` case study
  (`mattpocock/skills`, MIT, 71 units), originally run alongside `cep-retrofit-superpowers` above but
  deliberately removed before this release. A follow-up GitHub Copilot cross-runtime re-run of the
  same experiment surfaced the real `recommend --description` bug fixed above, which was worth
  keeping; the case-study write-up itself was not kept, so this release ships one metaskill-retrofit
  case study (`cep-retrofit-superpowers`) rather than two. See this file's git history for the
  removed case study's content if needed.

## [0.3.0]

2 PRs since v0.2.0. Headline: two case studies close the "does CEP help retrieval only, or does it
help a downstream *generative* task too" evidence gap, and two research-informed protocol additions
(a corpus-scaling primitive, an ingested-content-safety rule) came out of a deliberate review of
external context-engineering prior art.

### Added

- **Consumer-output-quality case studies (2)**: `case-studies/consumer-benefit-user-stories/` runs a
  real, already-built consumer skill (`spw-write-user-story`, vendored read-only for reproducibility,
  outside `.github/skills/` and never installable — same demonstrated-against-not-adopted treatment
  as the FastAPI/Textual/Open5GS corpora) twice against the same real feature: once with an approved
  context package, once from a bare ticket-sized ask with no package. Scored both against a rubric
  fixed before either output was read (traceability, hallucination, actor coverage, NFR specificity,
  testability, convention adherence), each finding tagged Measured or Inference. Two features, two
  unrelated domains (Textual UI/accessibility, Open5GS telecom Diameter stack in C) — the second run
  checks the first wasn't a fluke, and the win is sharper there (18 real citations vs. 0; 0
  hallucinated mechanisms vs. 1; 5 distinct actors vs. 2 generic; full convention structure 7/7 vs.
  none). Both cases also trace the compounding benefit of a package's `[Context: ...]` tags past the
  user-story file itself into design/review, planning, test-writing, and implementation stages.
  `EVIDENCE-METHODOLOGY.md` gains a 4th evidence category (**consumer-output-quality**, alongside
  token-efficiency, fallback-relevance, and the naive-keyword-search baseline) and a bare-ask-baseline
  definition.
- **Progressive-disclosure skeleton mode**: `md_index.py skeleton` reformats an already-built
  `index.json` into a `doc_id` + heading/clause-ID tree only, no body text — zero re-parsing, since
  the index never stored body text. Measured 6.7x compression on the real `telecom-what-l1-demo`
  corpus (39,076 → 5,862 bytes). Wired into `what-l1-fallback-query.md`/`how-l1-fallback-query.md` as
  an opt-in first look at a large/unfamiliar corpus before a full `query`; zero behavior change for
  existing configs. Closes the scaling primitive `ROADMAP.md` item 13 was missing.
- **Ingested-content injection guardrail**: new MUST-level `PROTOCOL.md` §2.2 — ingested What-L1/
  How-L1/MCP-mirrored content is always data to cite, never instructions to follow. Backed by a new
  SHOULD-level heuristic script, `scripts/content_safety_scan.py` (a narrow, literal pattern list,
  deliberately scoped to avoid false-positiving on ordinary "shall"/"must" spec language),
  informational only, never auto-blocking. Surfaced as a new non-blocking line in
  `ult-context-generate/SKILL.md`'s Step 9 human-review-gate template. `CONFORMANCE.md` §4 records it
  as a SHOULD, not the enforcement mechanism itself.
- **`references/design-scratchpad-glossary.md`**: a plain-English index of every
  `CONTEXT-ENGINEERING-DESIGN.md` `D<N>`/`§<N>` label cited across this repo, so those citations
  resolve without the private, unpublished source document. Linked from `CONTRIBUTING.md`'s existing
  citation note and from the two most heavily-cited skills (`ult-context-generate`, `ult-repo-layout`).
  At the time this glossary shipped, `ROADMAP.md` item 15 logged the fuller pre-1.0 citation cleanup
  it stopped short of as deferred; see the `### Fixed` entry below — that cleanup is now done.
- **`approved_by` trust signal**: replaces the old `human_approved: true|false` boolean across the
  context-package mechanism. Now a list — empty until a human approves (Step 9), then exactly one
  `{actor: human:<id>, at: <ISO8601>}` entry is appended; v1 enforces at most one (multi-approver
  review is explicit future scope). Backed by a new hard-gate script, `scripts/validate_approved_by.py`
  (flags a missing field, more than one entry, or a malformed entry — exit code 1 on failure, unlike
  `content_safety_scan.py`'s informational-only exit 0), run as part of Step 9's approval flow.
- Three other externally-sourced ideas (session-level runtime compaction, a comment-anchored
  live-studio UI, multiple ranked search modes/a multi-bundle registry) were reviewed and rejected,
  each for a reason tied to this repo's own prior decisions — logged to `ROADMAP.md` "Not on this
  roadmap" rather than dropped silently.

### Fixed

- **Private-document citation leak**: skills and scripts across the repo cited unpublished sibling
  design docs by filename (`CONTEXT-ENGINEERING-DESIGN.md` and two others) or bare `D<N>`/`D-0NN`
  decision-log labels a reader has no way to resolve. Rewrote every site to state the substance
  inline instead of pointing at a document that doesn't exist in this repo, and updated
  `CONTRIBUTING.md`'s citation note to match. Closes out `ROADMAP.md` item 15. Also removed internal
  EngineeringOS work-package IDs (`CEP-DP-001*`) that had leaked into public docs, scripts, and
  tests — that governance mechanism is private and was never meant to be user-facing.

### Known limitations (disclosed, not regressions)

- A residual set of unsignposted-but-technically-resolvable citations (real in-repo section headers,
  or labels already covered by `references/design-scratchpad-glossary.md`) were intentionally left
  untouched — see `ROADMAP.md` §14's "Glossary-pointer consistency polish" item for the remaining,
  non-blocking follow-up.
- `content_safety_scan.py`'s pattern list is narrow and literal by design; it is not a general
  prompt-injection detector and makes no such claim.
- Consumer-output-quality evidence is two case studies, one skill, not a blind trial — ground truth
  for traceability checks is knowable because both real features already exist upstream.
- **`approved_by` is a breaking rename of `human_approved`, with no migration shim.** Acceptable
  pre-1.0 since no automated consumer ever read either field; the three real case-study runs
  recorded before this rename keep their original `human_approved: true` values as accurate history
  (see `EVIDENCE-METHODOLOGY.md`'s field-name-drift note) rather than being rewritten to match.

## [0.2.0]

37 commits since v0.1.0. Headline: How-L1 shipped, cross-file citation resolution (R9/Phase B)
closed the single-hop/same-file limitation, an installer exists, and the protocol's evidence base
grew from four synthetic demos to three real-world dogfood case studies with tool-measured
token-reduction and fallback-relevance numbers.

### Added

- **`install.sh` / `install.ps1`**: the installer promised by several `SKILL.md` files and
  `ROADMAP.md`'s former top-priority item. Copies `.github/skills/`, `.github/prompts/`,
  `.cursor/rules/`, and `AGENTS.md` (merged into a marked block, not overwritten wholesale) into
  a target project directory; with `--init-project`/`-InitProject`, also scaffolds
  `context-config.yaml` from the template and `starter_kit/project_guidelines/.pointer.md`, each
  only if not already present. Supports `--dry-run`/`-DryRun` and requires an explicit, existing
  `--target`/`-TargetPath`. Re-running is idempotent and never clobbers project-owned files.
  `--only`/`-Only` (ROADMAP item 2) narrows a run to specific skills instead of installing all of
  them.
- **How-L1 (piloting)**: deterministic, zero-LLM structural indexing of external org-wide
  process-standard `.md` references (CMMI/ISO 9001/IEEE, etc. — reuses `md_index.py`, the same
  mechanism as What-L1), gap-triggered off Step 2's existing How-L2 org-convention check and
  scoped once per package/task-type rather than per aspect, with no web-search fallback chain of
  its own — Step 2's existing best-practice-template prompt substitutes for one. Gated for human
  review at Step 9 like every other fallback layer.
- **Cross-file citation resolution (ROADMAP item 1 / R9, Phase B)**: a cross-ref naming a document
  designator (e.g. `IEEE 802.11-2020 §9.3.2`) now resolves across files, joined via each target
  file's `doc_id` front matter — closing 0.1.0's disclosed "single-hop/same-file only" limitation.
  Same-file refs are unaffected; a designator with no matching `doc_id` stays `resolved:false`
  with `resolution_status: "unresolved-doc-not-found"`. See `examples/cross-file-resolution-demo/`
  for the worked resolved/doc-not-found/doc-ambiguous/clause-not-found cases.
- **MCP-backed What-L1/How-L1 sourcing (ROADMAP items 9/11)**: `scripts/mcp_mirror.py` mirrors
  MCP-fetched content into local `.md` files gated by content-hash comparison instead of mtime, so
  `md_index.py`'s existing `--stale-check` picks up upstream changes with zero changes to
  `md_index.py` itself. Wired in as a new Step 0 in both `references/what-l1-fallback-query.md`
  and `references/how-l1-fallback-query.md`, gated on `what_l1.mcp_source`/`how_l1.mcp_source`
  (default `[]`) — a project that never configures an MCP source sees zero behavior change. See
  `examples/mcp-what-l1-demo/WALKTHROUGH.md` for a validated, real-command round trip.
- **Project memory feedback loop (ROADMAP item 6)** and **context-package usage aggregation report
  (ROADMAP item 7)** for `ult-context-generate` — `scripts/usage_report.py` scans real
  `contexts/<id>.yaml`/`.addenda.yaml` files to report whether assembled context items are actually
  cited downstream or sit unused.
- **`ult-repo-layout`**: layer-path discovery engine and `confirm-layers` human-approval step with
  drift tracking (D23 S17.2–S17.8), plus per-candidate `include_roots` validation and further
  drift tracking (S40).
- **Three real-world dogfood case studies** replacing/augmenting the four synthetic
  demos as the project's evidence base: [Open5GS + RFC 6733](case-studies/open5gs-ietf-rfc/CASE-STUDY.md)
  (S6a Error-Message AVP gap), [FastAPI + OpenAPI](case-studies/fastapi/CASE-STUDY.md)
  (callbacks/links parity gap), and [Textual](case-studies/textual/CASE-STUDY.md) (ordinary run +
  a deliberate negative-control run) — plus a shared [case-study methodology template](case-studies/TEMPLATE.md).
- **Real token-efficiency and fallback-relevance evidence**: `graphify benchmark` run for real for
  the first time against all three case studies' graphs (36.8x / 5.6x / 39.6x fewer tokens/query),
  and a new naive-keyword-search baseline (`EVIDENCE-METHODOLOGY.md` §4) measuring whether the
  naive search a developer would try first actually finds what CEP found — closing both evidence
  gaps §1 previously named as open. See [`case-studies/SYNTHESIS.md`](case-studies/SYNTHESIS.md)
  for the cross-case synthesis and the README's new "Measured impact" table.
- **`CONFORMANCE.md`**: a CEP Conformance Specification — how to check whether an implementation
  actually conforms to `PROTOCOL.md`.
- **`GLOSSARY.md`**, RFC 2119 (`MUST`/`SHOULD`/`MAY`) markup on the protocol's state machine, and
  new `PROTOCOL.md` sections on lifecycle, roles, and open questions.
- **`EVIDENCE-METHODOLOGY.md`**, a reproducibility guide, and an evidence-record template
  (`references/`) defining what "measured" vs. "self-reported" vs. "inference" means in this
  project's documentation, and how to reproduce every measurement named in it.
- **README hero banner and "Measured impact" table** summarizing the three case studies' real,
  tool-measured numbers up front.

### Fixed

- **`graphify merge-graphs` multi-root crash**: was a stale local install, not an unfixed upstream
  bug — `graphifyy >= 0.9.11` persists the `directed`/`multigraph` keys the merge needs and
  composes correctly. `ult-codegraph/SKILL.md` now documents multi-root indexing + merge as a
  supported path and requires `>= 0.9.11`. See `ROADMAP.md` item 4.
- **`md_index.py` query ranking**: fixed a ranking bug and added a warning on low heading density;
  a later fix boosts title matches so a heading whose own title contains the query terms ranks
  ahead of a same-count body match. Also documents a `graphify` ID-collision fix.
- **Same-file clause-id ambiguity** is now surfaced rather than silently resolved to whichever
  heading came first — a cross-ref matching two headings in the same file is kept with
  `resolved:false` / `resolution_status: unresolved-ambiguous`.
- **`install.ps1`'s directory copy** made cross-platform.
- **Doc-audit pass**: a full one-by-one review of every `.md` file in the repo for currency ahead
  of this release — reconciled stale node/edge counts and citations to files that don't exist,
  re-ran and recaptured every `examples/*/WALKTHROUGH.md`'s tool output against the current
  `md_index.py`/`mcp_mirror.py` behavior, fixed several docs that described R4/R9 as future work
  after they had already shipped, and added missing cross-references (`CONFORMANCE.md`, the 4th
  CI check, `ROADMAP.md` item 14) across `PROTOCOL.md`, `EVIDENCE-METHODOLOGY.md`, `CONTRIBUTING.md`,
  and several skill references.

### Known limitations (disclosed, not regressions)

- How-L1 is piloting, not yet field-validated against a real corpus (`ROADMAP.md` item 13).
- Cross-file citation resolution requires a `doc_id` join key on the target file's front matter;
  a target indexed without one can never be matched even if the clause exists.
- No capability-profile / tool-restriction frontmatter field exists yet on any skill
  (`ROADMAP.md` item 14).
- Cursor's adapter is generated and doc-verified but not field-tested against a live install.
- No real 3GPP corpus exists yet for a domain-specific `ult-codegraph` example (`ROADMAP.md`
  item 8); the Open5GS case study is real telecom code but general-purpose graph structure.

See [`README.md` "What's not yet done"](README.md#whats-not-yet-done) and
[`ROADMAP.md`](ROADMAP.md) for the full, current disclosure.

## [0.1.0]

Initial public release.

### Added

- **`ult-context-generate`**: the protocol's centerpiece skill — assembles a human-approved,
  source-attributed context package (code graph + requirements + org conventions + constraints)
  before a downstream generation task runs, gated on an explicit gap → conflict → staleness
  state machine per feature aspect.
- **`ult-codegraph`**: generates a codebase knowledge graph (`graphify`) so other skills can
  query cross-file relationships before touching code — the What-L3 layer.
- **`compiling-project-guidelines`**: compiles scattered guideline sources into one scope-aware
  `COMPILED-GUIDELINES.md`, feeding the How-L2 layer and any code-facing skill directly.
- **`ult-repo-layout`**: registers, resolves, and validates path-slots via `.layout-slots.yaml`
  markers, so relocating a project's conventional folders needs zero `SKILL.md` edits.
- **`demo-consume-context`**: a from-scratch worked example proving the produce/consume/tag loop
  end to end — discovers, loads, spot-checks, cites, and tags an approved context package per
  `CONSUMING-CONTEXT-PACKAGE.md`.
- **What-L1 (piloting)**: deterministic, zero-LLM structural indexing of external `.md`
  references (`md_index.py` — "the graphify for markdown") with bundled `generic`/`3gpp` pattern
  profiles, triggered as a gated fallback only for aspects with no What-L2/What-L3 coverage.
- **Cross-runtime adapters**, generated (never hand-duplicated) from each skill's `SKILL.md` by
  `catalog/export_adapters.py`: `.prompt.md` wrappers for GitHub Copilot, `.mdc` rules for
  Cursor, and an `AGENTS.md` table for OpenAI Codex.
- **Quality gates as OSS infra**: CI workflow, pytest coverage across skill scripts and the
  adapter generator, `--check` drift detection for generated adapter files.
- **Dogfood validation (Phase 9)**: all four real skills run end-to-end, by hand, against a
  freshly cloned, unrelated real-world repo (`Textualize/textual`) — not just read for
  correctness. Claude Code and GitHub Copilot are field-validated with real transcripts; Codex is
  field-validated via Codex Desktop (with one disclosed, unrelated VS Code extension caveat). See
  [`README.md` "Runtime support"](README.md#runtime-support) for details.
- **`PROTOCOL.md`**: the full layer model, gap/conflict/staleness state machine (with diagrams),
  human-approval gate, and How-L1's specified-but-not-yet-built design.
- **`user_guides/topics/consuming-a-context-package.md`**: a plain-language, 10-minute on-ramp
  for building a skill that consumes an approved context package.
- **`examples/telecom-what-l1-demo/`**: a worked, hand-run example of the What-L1 mechanism
  against a synthetic (clearly labeled, non-copyrighted) 3GPP-style spec fixture.
- **`ROADMAP.md`**: prioritized list of what's next — installer, How-L1 implementation,
  cross-file citation resolution, and more.

### Known limitations (disclosed, not regressions)

- How-L1 (org-wide process-standard ingestion) is specified but not implemented.
- Cross-file citation resolution is single-hop/same-file only.
- `graphify merge-graphs` is broken for multi-root repos (documented workaround: one root at a
  time).
- No installer script exists yet — setup today is manual file copying.
- Cursor's adapter is generated and doc-verified but not field-tested against a live install.

See [`README.md` "What's not yet done"](README.md#whats-not-yet-done) and
[`ROADMAP.md`](ROADMAP.md) for the full, current disclosure.
