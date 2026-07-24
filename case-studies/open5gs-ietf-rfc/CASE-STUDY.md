# Case Study: Open5GS + RFC 6733 (Diameter Base Protocol)

```yaml
case: open5gs-s6a-error-message-avp
codebase: open5gs/open5gs, AGPL-3.0, ~150 MB C (5G Core / EPC network functions); scoped to
  src/ (7.4 MB) and lib/diameter/ (432 KB) for this run
date_run: 2026-07-24
author: dogfooding run, context-engineering-oss
negative_control: false
```

This case is CEP's first run against an external IETF specification as a What-L1 source, paired
with a real gap in Open5GS's own Diameter AVP dictionaries. Because Open5GS is AGPL-3.0, this case
follows the no-vendoring rule for copyleft corpora: no Open5GS source, no RFC text, and no
generated context package are committed alongside this write-up — every artifact below is
described narratively, with exact file/line/section pointers a reader can follow against their own
clone.

## Results at a glance

| Metric | Without CEP (naive keyword search) | With CEP | Kind |
| --- | --- | --- | --- |
| Found the Gx exemplar (`gx/dict.c:273`)? | Yes — one grep, one unambiguous hit | Yes | Measured |
| Found the S6a integration point (`hss-s6a-path.c`'s `air_cb`)? | No — `grep "Error-Message"` returns zero hits in that file; the correct callback must be found by reading among 6 candidate callbacks in a 2,343-line file | Yes — cited directly | Measured |
| Cost to locate that integration point via reading | ~2,555 words / ~3,407 tokens (the one right function, best case) to ~7,211 words / ~9,615 tokens (whole file) | Direct citation | Measured |
| Found RFC 6733 §7.3 (Error-Message AVP)? | No keyword search possible — the term isn't in the codebase at all; only a whole-document read finds it | Yes — direct `clause_id` lookup | Measured |
| Cost to locate RFC §7.3 by reading the spec | 43,599 words / ~58,132 tokens (the whole RFC) | 55 words / ~73 tokens (the section itself) — **~797x fewer tokens** | Measured |
| `graphify benchmark` reduction (whole scoped graph) | naive full-corpus-read baseline | 36.8x fewer tokens/query (191,500 words → ~255,333 naive tokens; 3,830 nodes / 10,236 edges; avg ~6,934 tokens/query) | Measured |

**Retrospective, not blind:** the naive queries above are the same ones this case's own
reproduction steps (§"Reproduction steps") already used to confirm the gap and exemplar — chosen
because the task's answer is already known, not reverse-engineered from CEP's own citations. This
is a real limitation, not hidden: see `EVIDENCE-METHODOLOGY.md` §7. The mixed result is the honest
finding — naive grep is genuinely competitive for the same-repo exemplar (a plain keyword hit), and
genuinely helpless for the external-spec lookup (no keyword exists to search for), and for the
in-repo integration point itself (absent, not misnamed — grep has nothing to match).

## 1. Environment

Open5GS was cloned to a sibling directory (`dogfood-open5gs/`), pinned to tag `v2.8.0` (commit
`157f611`). CEP scaffolding was applied via the canonical installer
(`context-engineering-oss/install.sh --target dogfood-open5gs --init-project`), then
`context-config.yaml` was hand-edited for Open5GS's real layout: What-L3 `path: .` scoped in
practice to two subdirectories (`src/`, `lib/diameter/`) rather than the whole repo — `lib/sbi/`
(88 MB) and `lib/asn1c/` (44 MB) are generated/vendored code irrelevant to this task and were
excluded per the reproducibility guide's own scoping advice. What-L2 `path: docs/_docs/`. What-L1
enabled for the first time in this program, `path: specs/external/`, `md_index_profile: rfc`. How-L2
`path: .`. Runtime: no live interactive coding agent session — all steps run directly via `graphify`
CLI, `md_index.py`, and manual `content_hash.py`, with every normally human-answered step
self-answered and flagged as simulated (see §6).

RFC 6733 (Diameter Base Protocol) was fetched directly from `https://www.rfc-editor.org/rfc/rfc6733.txt`
(the RFC Editor's own canonical, freely-republishable plaintext) and dropped into
`specs/external/rfc6733.md` for indexing, per D-010's link/section-number-only citation rule — the
full text exists only in the disposable local clone, never in this repo.

## 2. Task

Add Error-Message AVP (RFC 6733 §7.3) support to the S6a interface, so S6a error answers (e.g.
Authentication-Information-Answer on failure) can carry a human-readable diagnostic string
alongside the existing Result-Code AVP — matching the level of support Error-Message already has
on Gx.

This is a deliberate-gap task (D-012 methodology): Error-Message is genuinely registered in
Open5GS's Gx (PCRF) AVP dictionary but genuinely absent from S6a and the shared common dictionary,
confirmed by grep against the real source before the task was framed, not invented for the case
study.

## 3. Source set

What-L3: `src/` (3,670 nodes / 10,128 edges) and `lib/diameter/` (87 nodes / 110 edges) graphed
separately via two scoped `graphify update --no-cluster` runs, then merged into one queryable graph
(`graphify merge-graphs`) — 3,830 nodes / 10,236 edges combined. What-L2: `docs/_docs/` searched
directly (grep, matching the config's `path`) rather than indexed — see §5's gap finding. What-L1:
RFC 6733 (196 real headings after the markdown-conversion workaround described in §5) indexed via
`md_index.py index --profile rfc` into `specs-out/index.json`. How-L2: repo root README.md's
Contributing section, `.editorconfig`, `.clang-tidy`. No `discover`/`confirm-layers` workflow was
needed — layout was hand-confirmed against the real Open5GS tree up front.

## 4. Package generation

`ult-context-generate`'s methodology (invoked manually, script-by-script, in this no-live-agent run)
produced a context package (`content_hash: 9673f988`) with 10 context items across 5 aspects.
What-L3 hits: Gx's Error-Message registration (`lib/diameter/gx/dict.c:273`) as the working
exemplar; confirmed absence from S6a's and the common dictionary via grep; the real S6a
error-answer integration point (`hss_ogs_diam_s6a_air_cb`'s `out:` label,
`src/hss/hss-s6a-path.c:465-493`); and a `graphify affected` blast-radius check on
`ogs_diam_s6a_init()` (one caller within the graphed scope, no other dependents). What-L1 hits:
RFC 6733 §7.3 (Error-Message AVP definition) and §7.1 (Result-Code AVP, the AVP it always
accompanies), retrieved by direct `clause_id` lookup in the index rather than the ranked query
tool — see §5. What-L2: zero AVP-level or protocol-structure content in `docs/_docs/` — a complete,
expected gap for this kind of low-level protocol change.

## 5. Detected gaps, conflicts, staleness

No conflicts: What-L1 (RFC 6733's own description of Error-Message as optional and
human-readable-only) and What-L3 (Gx's actual registration, which likewise has no dedicated struct
field for it) agree on the AVP's scope and bounded the task's design decision (§6) accordingly.
Two gaps, both expected rather than tooling misses: the S6a/common dictionary gap itself (a2 — the
task's actual target) and a complete What-L2 gap (a5 — Open5GS's docs are build/ops guides, not
protocol reference material).

Two real tooling observations surfaced during What-L1 setup, logged separately per `TEMPLATE.md`'s
instruction rather than duplicated here in full: (1) `md_index.py`'s heading detector requires
markdown ATX/Setext syntax and produced only 8 false-positive headings against real,
unmodified RFC-editor plaintext — self-remediated by markdown-ifying the real numbered headings
before indexing (196 real headings, clean afterward); logged as `DEF-002` (Medium, **partially
fixed** — the tool now warns when a plaintext-house-style profile's heading count is anomalously
low, so this class of silent failure no longer goes unflagged, though the full plain-line detector
remains open). (2) `md_index.py query`'s ranking structurally favored ancestor headings over their
more specific descendants (querying "Error-Message AVP" never surfaced the actual §7.3 in the top
12 results) — worked around by looking up the target `clause_id` directly in the index rather than
trusting the ranked query; logged as `DEF-003` (Medium, **fixed** — re-running the identical query
against the rebuilt index confirms the ancestor-inflation mechanism is gone: the previously-dominant
top-level chapters no longer accumulate their descendants' matches, and §7.3's own rank improved
from 44th of 156 to 26th of 148). §7.3 still didn't crack the top 12, though — re-verifying surfaced
a distinct, separate limitation (raw term counts with no per-term specificity, logged fresh as
`DEF-004`, Low, deferred) that the direct `clause_id` lookup workaround below still fully covers.
Neither DEF-002 nor DEF-003 blocked this run or changed its conclusions, and the fixes did not
require re-running or altering this case's own package generation.

## 6. Approval decision

No live human reviewer was available (disposable dogfood clone). Step 1 scope clarification, the
Step 6 design decision (scope the fix to dictionary-level registration only, matching Gx's actual
level of support rather than inventing a struct field Gx itself lacks), and the Step 9-equivalent
approval were all self-answered by the operator running the tooling and are flagged as simulated
in the package's YAML — disclosed here rather than presented as genuine human-in-the-loop review.

## 7. Downstream use

The package was not handed to a downstream coding agent to actually implement the AVP addition —
this run stops at package generation, same as the Textual case's Run A/B. This measures the
context-assembly step in isolation.

## 8. Outcome

**Partially measured, partially inference:** the package correctly surfaced the exact working
exemplar (Gx's registration), the exact confirmed gap (S6a and common dictionaries), the exact
integration point in real, already-centralized error-handling code (`hss-s6a-path.c`'s `out:`
label), and the exact RFC section that bounds the fix's scope (§7.3's "not intended for automated
processing" language, which directly justified the §6 design decision). The token-cost side of this
is now measured, not inferred (see "Results at a glance" above): a naive keyword search finds the
Gx exemplar for free but finds nothing at all for the S6a integration point or the RFC section, and
reading to find those two costs real, counted tokens — ~9,615 for the integration point (worst
case) and ~58,132 for the RFC section, against CEP's ~73-token direct lookup for the latter.
Whether this token difference translates to less *developer* time is still a judgment call, not a
controlled user study — that narrower claim remains inference.

This case study is also CEP's first evidence that What-L1 (external spec ingestion) can genuinely
work end-to-end against a real, un-modified external document — RFC 6733's plaintext required a
workaround (DEF-002) to index at all, which is itself useful signal about the current state of that
pilot capability, not just about this task.

## 9. Limitations

Single-task, single-codebase, no-live-reviewer dogfood run, same caveats as the Textual case. The
naive-keyword-search baseline in "Results at a glance" is real but retrospective, not blind — the
queries reuse this case's own reproduction steps, run after the task's answer was already known
(`EVIDENCE-METHODOLOGY.md` §7). This is also the first real exercise of What-L1 against a genuine
external plaintext spec rather than a pre-formatted markdown source — the two defects originally found here (DEF-002, DEF-003) turned out
to generalize rather than being RFC-house-style-specific, confirmed once a second What-L1 corpus
(the FastAPI case's OpenAPI Spec) was available to compare against, and DEF-003 has since been fixed
at the tool level (see §5). A further, distinct ranking limitation (DEF-004) was found only while
verifying that fix, and remains open.

## 10. Lessons learned

CEP's gap/conflict checks and `graphify affected` blast-radius check behaved correctly and honestly
for a genuinely mixed-source-and-vendored codebase, once scoped away from the generated
`lib/sbi/`/`lib/asn1c/` subtrees per the reproducibility guide's own advice. The What-L1 pilot
surfaced two real, generalizable defects in `md_index.py` (`DEF-002`, `DEF-003`), both non-blocking
via workaround at the time. `DEF-003` has since been fixed (own-content-only ranking, verified by
re-running this case's exact query against the rebuilt index) and `DEF-002` partially fixed (a
low-heading-density warning); `DEF-004`, a distinct raw-term-specificity ranking limitation, was
found during that verification and remains open. None of the four invalidated this run's findings
or blocked forward progress.

## Reproduction steps

1. Clone the pinned corpus: `git clone https://github.com/open5gs/open5gs.git dogfood-open5gs &&
   cd dogfood-open5gs && git checkout v2.8.0` (commit `157f611`).
2. Apply this repo's CEP scaffolding via the canonical installer:
   `./install.sh --target dogfood-open5gs --init-project`, then hand-edit `context-config.yaml`
   per §1 above.
3. Fetch RFC 6733 directly from the RFC Editor: `curl -sS -o specs/external/rfc6733.txt
   https://www.rfc-editor.org/rfc/rfc6733.txt`, strip form-feed page breaks, rename to
   `specs/external/rfc6733.md`.
4. Markdown-ify the RFC's real dotted-numeric headings before indexing (see `DEF-002` — raw
   RFC-editor plaintext headings are not detected as-is): convert flush-left lines matching
   `^\d+(\.\d+)*\.?\s+\S` to ATX headings (`#`/`##`/`###` by depth).
5. Build the What-L1 index: `python .github/skills/ult-context-generate/scripts/md_index.py index
   specs/external/ -o specs-out/index.json --profile rfc`. Expect "Indexed 1 file(s), 196
   heading(s)".
6. Build the What-L3 graph, scoped (per §1's exclusion rationale):
   `graphify update src/ --no-cluster` (expect 3,670 nodes / 10,128 edges), then
   `graphify update lib/diameter/ --no-cluster` (expect 87 nodes / 110 edges), then merge:
   `graphify merge-graphs src/graphify-out/graph.json lib/diameter/graphify-out/graph.json --out
   graphify-out/graph.json` (expect 3,830 nodes / 10,236 edges combined).
7. Confirm the task's gap and exemplar directly: `grep -n "Error-Message"
   lib/diameter/gx/dict.c lib/diameter/s6a/dict.c lib/diameter/common/dict.c` — expect exactly one
   match, in `gx/dict.c`.
8. Look up RFC 6733 §7.3 directly by `clause_id` in `specs-out/index.json` (not via `query` — `DEF-003`
   itself is fixed, but `DEF-004`'s residual raw-term-specificity limitation still keeps §7.3 out of
   `query`'s top ranks) to confirm its `section_bounds` and read the Error-Message AVP definition at
   that line range.
9. Compare your package's `content_hash` against this case's recorded value
   (`s6a-error-message-avp_feature-add_20260724.yaml`: `9673f988`) by running
   `python .github/skills/ult-context-generate/scripts/content_hash.py contexts/<id>.yaml`.
