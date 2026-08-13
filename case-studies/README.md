# Case Studies

Real, reproducible reports of running this protocol against real codebases — including where it
adds little or no value. See [`TEMPLATE.md`](TEMPLATE.md) for the format every case follows and
[`../references/reproducibility-guide.md`](../references/reproducibility-guide.md) for how to
reproduce one.

Every case is either **measured** (backed by a real tool run whose output you can point to) or
explicitly marked as **inference** (a judgment call, not a tool's direct output) — see
`EVIDENCE-METHODOLOGY.md` §5-§6. None of these are marketing narratives: at least one case is a
deliberate negative control, chosen to show a situation where this protocol adds little value.

## Cases

| Case | Codebase | Negative control? | Summary |
| --- | --- | --- | --- |
| [textual-focus-chain-and-sparkline-baseline](textual/CASE-STUDY.md) | Textualize/textual (MIT) | Yes | Ordinary focus-chain feature-add finds real cross-file structure; a deliberately self-contained `Sparkline` task finds that CEP's context-assembly overhead surfaces almost nothing worth reporting. |
| [open5gs-s6a-error-message-avp](open5gs-ietf-rfc/CASE-STUDY.md) | open5gs/open5gs (AGPL-3.0) | No | First run against a real IETF RFC as a What-L1 source, paired with a genuine AVP-dictionary gap (Error-Message present on Gx, absent on S6a) — correctly surfaces the working exemplar, the confirmed gap, and the real error-answer integration point. |
| [fastapi-response-links-parity](fastapi/CASE-STUDY.md) | fastapi/fastapi (MIT) | No | Second real-external-spec run, this time genuine Markdown (OpenAPI 3.1.0) rather than converted RFC plaintext — paired with a genuine `callbacks=`/`links` parity gap, correctly surfaces the working exemplar, the confirmed gap, and the exact response-merge integration point; corroborates which prior tooling defect is plaintext-specific and which one generalizes. |
| [consumer-benefit-user-stories](consumer-benefit-user-stories/CASE-STUDY.md) | Textualize/textual (MIT) — reuses the package from the case above | No | A different kind of benefit than the other three: measures whether an approved context package improves a downstream *consuming skill's generated output* (fewer hallucinated APIs, more real citations, more actors, better convention adherence) rather than retrieval cost — first evidence for CEP's generative, not just retrieval, benefit. |
| [open5gs-gy-supported-features](open5gs-gy-supported-features/CASE-STUDY.md) | open5gs/open5gs (AGPL-3.0) | No | Repeats the consumer-benefit method above on an unrelated domain (telecom Diameter protocol stack) to check whether the generative-benefit finding holds outside UI/accessibility features — it does, and sharper, including the same fabricated accessibility concept resurfacing in a codebase with no UI at all. |
| [ripgrep-crlf-replace-terminator](ripgrep-crlf-replace/CASE-STUDY.md) ⚠️ tooling side-quest | BurntSushi/ripgrep (Unlicense OR MIT) | No | **Not a CEP protocol case** — evaluates `ult-codegraph`/`graphify` alone (no context package, no approval gate) against naive search on a real Rust bug fix (PR #3100). `graphify explain` cheaply resolves the right symbols (~84x fewer tokens than the naive-grep-narrowed file set), but `path`/`affected` starting from the CLI flag's own definition symbol fail outright — a disclosed, structural limitation of AST-only graphs against ripgrep's one-struct-per-flag pattern, plus a real Windows deep-path environment bug found along the way. A real CEP-protocol case in a new ecosystem is still owed. |
| [ripgrep-trim-user-stories](ripgrep-user-stories/CASE-STUDY.md) | BurntSushi/ripgrep (MIT/Unlicense) | No | A real CEP-protocol run (context package, self-approval, provenance) against a Rust CLI tool — distinct from `ripgrep-crlf-replace-terminator`'s tooling-only side-quest — using a brand-new, independently-designed consuming skill (`demo-write-user-stories`). Reproduces the generative-benefit finding a third time on a new ecosystem, and finds the hallucination-suppression benefit is conditional on how underspecified the input request is, not universal. |
| [cep-retrofit-superpowers](cep-retrofit-superpowers/CASE-STUDY.md) | obra/superpowers (MIT) + open5gs/open5gs (AGPL-3.0) | No | First test of the `ult-cep-retrofit` metaskill itself: a full-library retrofit pass across a real, unrelated 62-unit skill library (0 misclassifications, pristine clone rather than this repo's own already-adapted copies of the same skills), plus a deep with/without-CEP comparison of one retrofitted skill (`writing-plans`)'s generated output, plus a first-ever trip-wire (institutional-memory) rung on top. Finds real Mode 2 defects (duplicate AVP declarations, a fabricated test target) Mode 1 avoids, and a genuinely humbling trip-wire finding: a `tier: revise` hit accepted without checking its own `required_evidence` field produces a confidently wrong value. Closes this directory's `Trip-wire` and `Metaskill-retrofit origin` coverage gaps for the first time. |
| [robotframework-wizard-ui](robotframework-wizard-ui/CASE-STUDY.md) | robotframework/robotframework (Apache-2.0) | No | First case to drive `ult-cep-wizard`'s browser UI end-to-end via Playwright (real screenshots, not curl) and to exercise `ult-autoscaffold-content`'s Phase B large-repo triage/tiering path directly (13 modules tiered, 13/13 `CONTEXT.md` generated for both What-L2 and How-L2). Real before/after UI evidence that Phase D's empty-box wiring works; a real `graphify` cwd/path-relativity footgun found and fixed along the way; a genuine, disclosed finding that autoscaffolded content's module-granularity corroborates but doesn't substitute for issue-level grounding on a narrow task; and a validated stretch-goal code-change proposal (real unit tests pass 47/47 and 362/362, identically before and after). |

Both consumer-benefit cases also find that the generative benefit compounds past the user-story
file itself: an approved context package's grounding stays available, pre-identified, to whatever
later stage of work — design/review, planning, test-writing, or implementation — consumes the
tagged output next, instead of being re-derived from scratch at each stage. See either case's own
"Downstream compounding benefit" section, and the [top-level README](../README.md#measured-impact)
for the marketing-facing summary table.

## Feature coverage

Which CEP capability each case actually exercised — a cheap cross-check for gaps in what's been
proven, not a completeness scorecard.

Legend: ✅ exercised and reported on directly · ➖ not yet exercised by this case (derived-package
composition remains unimplemented everywhere; trip-wire and the CEP-retrofit metaskill are both now
implemented — see [`PROTOCOL.md` §7](../PROTOCOL.md#7-trip-wire--institutional-memory-decision-ledger-piloting)
and [§8](../PROTOCOL.md#8-cep-retrofit--bringing-an-existing-skill-library-under-this-protocol) — a
➖ in either of those two columns means this particular case didn't exercise it, not that the
capability doesn't exist) · N/A doesn't apply to this case's own scope.

| Case | Approval gate | Provenance tagging | Staleness / conflict checks | Derived-package composition | Trip-wire | Metaskill-retrofit origin | Benefit measured |
| --- | --- | --- | --- | --- | --- | --- | --- |
| textual-focus-chain-and-sparkline-baseline | ✅ (simulated, disclosed) | ✅ | ✅ (0 conflicts on Run A; Run B is the negative control) | ➖ | ➖ | N/A — no consuming skill | Retrieval |
| open5gs-s6a-error-message-avp | ✅ (simulated, disclosed) | ✅ | ✅ (0 conflicts) | ➖ | ➖ | N/A — no consuming skill | Retrieval |
| fastapi-response-links-parity | ✅ (simulated, disclosed) | ✅ | ✅ (0 conflicts) | ➖ | ➖ | N/A — no consuming skill | Retrieval |
| consumer-benefit-user-stories | ✅ (reuses a prior, already-approved package) | ✅ | N/A — reuses `textual` case's package, no new package generated | ➖ | ➖ | No — hand-built, vendored `spw-write-user-story` | Generative |
| open5gs-gy-supported-features | ✅ | ✅ | ✅ (0 conflicts) | ➖ | ➖ | No — same vendored `spw-write-user-story` | Generative |
| ripgrep-crlf-replace-terminator ⚠️ tooling side-quest | N/A — no package generated | N/A | N/A | ➖ | ➖ | N/A | N/A — not a protocol case |
| ripgrep-trim-user-stories | ✅ (self-approved, disclosed) | ✅ | ✅ (0 conflicts) | ➖ | ➖ | No — new, ground-up `demo-write-user-stories` | Generative |
| cep-retrofit-superpowers | ✅ (freshly regenerated package, disclosed) | ✅ | ✅ (0 conflicts, 1 gap) | ➖ | ✅ (3-entry fixture ledger, real `query`, 1 hit materially changed output — and shown, on independent re-verification, to itself be wrong) | Yes — metaskill-retrofitted `writing-plans`, machine-selected `recommend()` signal | Generative |
| robotframework-wizard-ui | ✅ (self-approved, disclosed) | ✅ | ✅ (0 conflicts) | ➖ | ➖ | No — reuses ground-up `demo-write-user-stories` from ripgrep-trim-user-stories | Generative |

All other cases above still show ➖ across derived-package composition, trip-wire, and
metaskill-retrofit origin — an honest gap that isn't fully closed yet either: derived-package
composition remains unimplemented everywhere. `cep-retrofit-superpowers` is the first case to
exercise **trip-wire** and **metaskill-retrofit origin**; a second `ult-cep-retrofit` case
(`mattpocock/skills`) was run and then deliberately not kept in this directory — a follow-up GitHub
Copilot cross-runtime re-run of that same experiment surfaced a real `cep_retrofit.py` CLI bug
(`CHANGELOG.md`'s `[Unreleased]` → Fixed), which was worth keeping, but the case-study write-up
itself was not; see this file's git history for the removed content. No second metaskill-retrofit
case study is currently planned. Derived-package composition still awaits its own first case.

None of the columns above track wizard-UI or large-repo-autoscaffold coverage, since no case before
`robotframework-wizard-ui` exercised either — that case closes both gaps directly (see its own
CASE-STUDY.md §2 and §4) without needing a new column here: `ult-cep-wizard`'s browser UI had only
ever been driven by curl/HTTP or unit/E2E tests, and `ult-autoscaffold-content`'s Phase B
large-repo triage/tiering path had only ever run against a scratch fixture, never a real, external,
50-100 KSLOC codebase.

## Synthesis

[`SYNTHESIS.md`](SYNTHESIS.md) compares the first five cases above — what held across cases, what
didn't, and what that implies for this protocol's actual claims. The two ripgrep cases and
`cep-retrofit-superpowers` were added later and aren't folded into that comparison yet;
`ripgrep-crlf-replace-terminator` is a tooling side-quest rather than a protocol case anyway, and
`ripgrep-trim-user-stories` and `cep-retrofit-superpowers` are candidates for the next synthesis
pass.
