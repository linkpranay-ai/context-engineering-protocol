# Cross-case synthesis

Compares the three published cases now that all three carry real, measured "Results at a glance"
tables (not just "inference, not measured"). See [`README.md`](README.md) for the case list and
[`EVIDENCE-METHODOLOGY.md`](EVIDENCE-METHODOLOGY.md) §5-§6 for the measured-vs-inference
distinction this document relies on throughout. Three cases is not a large sample — this is a
first read of a pattern, not a statistically grounded claim.

## Results across cases, at a glance

| Case | Corpus | Task-level token reduction | `graphify benchmark` reduction | Graph size | Negative control? |
| --- | --- | --- | --- | --- | --- |
| [open5gs-s6a-error-message-avp](open5gs-ietf-rfc/CASE-STUDY.md) | open5gs/open5gs, C, AGPL-3.0 | ~797x (RFC 6733 §7.3 clause lookup: 43,599 words naive vs. 55 words CEP) | 36.8x (191,500 words → ~255,333 naive tokens) | 3,830 nodes / 10,236 edges | No |
| [fastapi-response-links-parity](fastapi/CASE-STUDY.md) | fastapi/fastapi, Python, MIT | ~15.3x (15,767 words naive vs. 1,030 words CEP) | 5.6x (45,550 words → ~60,733 naive tokens) — smallest of the three | 911 nodes / 2,568 edges | No |
| [textual-focus-chain-and-sparkline-baseline](textual/CASE-STUDY.md) | Textualize/textual, Python, MIT | Run A: ~17.6x (23,751 words naive vs. 1,346 words CEP). Run B (negative control): naive **cheaper** — 551 words vs. 902 words CEP | 39.6x (1,005,800 words → ~1,341,066 naive tokens) — largest of the three | 20,116 nodes / 59,448 edges | Yes |

All figures above are Measured, per each case's own §8/§9, using the naive-keyword-search and
`graphify benchmark` baselines defined in `EVIDENCE-METHODOLOGY.md` §4.

## Where CEP helped

**External-spec clause lookup is CEP's largest, most consistent measured win.** Open5GS's RFC 6733
§7.3 lookup — which numbered clause of an ~8,500-line prose RFC defines the AVP the task
needed — has no keyword to grep for; a developer either already knows the clause number or reads
the spec. CEP's What-L1 layer resolves it as a direct clause_id lookup, at roughly 1/800th the
token cost of fetching and skimming the document. This is categorically different from a code-side
search problem, and it is the single largest reduction across all three cases.

**In-repo, keyword-bridgeable code is where naive grep is genuinely competitive — CEP's edge there
narrows to disambiguation, not discovery.** FastAPI's `callbacks=` exemplar and Textual's
`focus_chain` exemplar are both grep-clean: naive search finds them with no help from CEP. But the
real integration points next to each exemplar are not: FastAPI's actual merge site
(`openapi/utils.py:410-453`) has zero "callbacks" occurrences to search for, and Textual's
`_check_disabled()` has no term in the task's own wording ("disabled widgets shouldn't be
focusable") that bridges to the function name — broadening the grep to "disabled" returns 10
undifferentiated files instead of one. CEP found both real integration points directly; naive
search, even when it got close, did not.

**Blast-radius certainty is a distinct, smaller win from discovery.** FastAPI's
`get_openapi_path()` caller disambiguation is where naive grep gets partway there on its own —
"Partial," per the case's own table, missing one real caller (`applications.py:1086`) that
`graphify affected` names exactly, alongside its counterpart, with nothing extra. This is the
case's own explanation for why its task-level reduction (~15.3x) is the smallest of the three: grep
already does most of the work, so CEP's contribution is confidence rather than access.

**Reduction magnitude tracks how spec-shaped the missing information is, not how large the
codebase is.** The `graphify benchmark` reductions run 36.8x (Open5GS), 5.6x (FastAPI), 39.6x
(Textual) — FastAPI's corpus sits between the other two in size (911 nodes) yet has the lowest
reduction, self-reported in its own case study as "the smallest, most honest" of the three. Graph
size does not predict benefit; how much of the task's answer lives in prose spec versus
keyword-findable code does.

## Where CEP didn't help

Textual's Run B is the one measured case, across all three, where the full CEP pipeline cost more
than the alternative: reading `sparkline.py` directly (551 words / ~735 tokens) is cheaper than
the generated context package (902 words / ~1,203 tokens). This is not a tooling failure —
`graphify explain` correctly reported a low-degree, self-contained node; `graphify affected`'s
fallback pivot correctly reported a single generic dependent; the What-L2 gap check correctly
reported zero documentation coverage. All three tool outputs agreed, correctly, that there was
nothing here worth assembling context for. CEP's own assembly overhead was the cost, and there was
nothing on the other side of the ledger to buy back with it.

This result was deliberately produced — Textual was chosen for the negative-control role
specifically because Run A had already established real familiarity, making it possible to pick a
genuinely self-contained target with confidence rather than guessing blind — not stumbled into. The
case study itself names the limit of the finding: it is about one specific low-connectivity
renderable class, not "CEP adds nothing to small modules" in general. Generalizing that would need
more negative controls across different codebases, which this project does not yet have.

## Limitations across all three

- **Retrospective, not blind, in every case.** Every naive-search baseline reused a query each
  case's own reproduction steps had already run to confirm the gap — the "naive" searcher already
  effectively knew where to look. All three §9 sections name this individually; it does not wash
  out in aggregate. Three retrospective comparisons are still zero blind trials.
- **No live human reviewer in any of the three.** Every approval, gap-handling, and open-question
  step that normally requires a human was self-answered by the operator and explicitly flagged as
  simulated in each package's YAML. Across all three cases combined, CEP's actual
  human-in-the-loop behavior remains untested — only its unattended mechanics have been measured.
- **Narrow task and corpus diversity.** Only one task type (feature-add) and one negative-control
  axis (a single self-contained, low-degree class) have been tried. Two of the three corpora
  (FastAPI, Textual) are MIT-licensed Python frameworks in a similar size band; Open5GS is the
  outlier — C, AGPL-3.0, telecom protocol stack — and also the case with the single largest
  measured win. Three cases isn't enough to know whether that's because of the language/domain
  difference or because Open5GS happened to have the most spec-shaped gap.
- **Developer-time translation is still inference in all three.** Only token cost is measured;
  "costs fewer tokens" and "saves developer time" are different claims, and none of the three cases
  collapses that distinction — each says so directly in its own §8.

## What this implies for the protocol's actual claims

The claim these three cases actually support: for a task whose missing piece is a specific
clause or definition in an external prose spec with no natural keyword bridge to the code, CEP's
context assembly is measured to cost dramatically fewer tokens than the naive alternative — up to
~797x in the strongest case so far. For a task whose missing piece is itself keyword-findable
in-repo, the measured advantage narrows to certainty and disambiguation rather than discovery, and
in at least one deliberately chosen case, reverses — the naive read is measured cheaper.

This is not a claim that CEP is unconditionally net-positive. Three cases, one of them a
deliberate negative control, is evidence of a pattern worth continuing to test, not a guarantee.
