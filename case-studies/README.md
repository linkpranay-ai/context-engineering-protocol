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
| [textual-focus-chain-and-sparkline-baseline](textual/CASE-STUDY.md) | Textualize/textual (MIT) | Yes | Ordinary focus-chain feature-add finds real cross-file structure; a deliberately self-contained `Sparkline` task finds CEP's context-assembly overhead surfaces almost nothing worth reporting. |
| [open5gs-s6a-error-message-avp](open5gs-ietf-rfc/CASE-STUDY.md) | open5gs/open5gs (AGPL-3.0) | No | First run against a real IETF RFC as a What-L1 source, paired with a genuine AVP-dictionary gap (Error-Message present on Gx, absent on S6a) — correctly surfaces the working exemplar, the confirmed gap, and the real error-answer integration point. |
| [fastapi-response-links-parity](fastapi/CASE-STUDY.md) | fastapi/fastapi (MIT) | No | Second real-external-spec run, this time genuine Markdown (OpenAPI 3.1.0) rather than converted RFC plaintext — paired with a genuine `callbacks=`/`links` parity gap, correctly surfaces the working exemplar, the confirmed gap, and the exact response-merge integration point; corroborates which prior tooling defect is plaintext-specific and which one generalizes. |

## Synthesis

Once at least three cases are published, [`SYNTHESIS.md`](SYNTHESIS.md) will compare them —
what held across cases, what didn't, and what that implies for this protocol's actual claims.
