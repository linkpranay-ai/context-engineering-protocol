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

## Synthesis

Once at least three cases are published, [`SYNTHESIS.md`](SYNTHESIS.md) will compare them —
what held across cases, what didn't, and what that implies for this protocol's actual claims.
