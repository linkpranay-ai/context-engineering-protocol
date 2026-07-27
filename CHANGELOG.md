# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project uses simple `MAJOR.MINOR.PATCH`
versioning without a formal SemVer API-compatibility guarantee yet (see [`ROADMAP.md`](ROADMAP.md)).

## [Unreleased]

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
- **`approved_by` trust signal**: replaces the old `human_approved: true|false` boolean across the
  context-package mechanism. Now a list — empty until a human approves (Step 9), then exactly one
  `{actor: human:<id>, at: <ISO8601>}` entry is appended; v1 enforces at most one (multi-approver
  review is explicit future scope). Backed by a new hard-gate script, `scripts/validate_approved_by.py`
  (flags a missing field, more than one entry, or a malformed entry — exit code 1 on failure, unlike
  `content_safety_scan.py`'s informational-only exit 0), run as part of Step 9's approval flow.
  At the time this glossary shipped, `ROADMAP.md` item 15 logged the fuller pre-1.0 citation cleanup
  it stopped short of as deferred; see the `### Fixed` entry below — that cleanup is now done.
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
