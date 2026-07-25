# Case Study Template

Copy this file to `case-studies/<short-name>.md` and fill in every section with what actually
happened on a real run against a real, named codebase — not a hypothetical or a composite of
several runs. Per `EVIDENCE-METHODOLOGY.md` §5-§6, every outcome below is either **measured**
(produced by actually running a tool and reading its output) or explicitly marked as **inference**
(the author's judgment call, not a tool's direct output) — never blur the two.

A case study exists to show what CEP actually does on a real repository, including where it fails
or adds nothing. A case that only reports success is not a complete case study.

## Header

```yaml
case: <short name, e.g. "open5gs-rfc6733">
codebase: <name, license, approximate size/language>
date_run: <YYYY-MM-DD>
author: <name>
negative_control: <true|false>   # true if this case is deliberately chosen to show
                                   # where CEP adds little or no value
```

## Results at a glance

A short table, placed immediately after the header (before §1), giving a reader the numbers
without reading the full case. One row per comparison actually measured — no placeholder rows, and
no row for a comparison you didn't run:

| Metric | Without CEP (naive keyword search) | With CEP | Kind |
| --- | --- | --- | --- |
| Did the naive baseline find the real integration point? | Yes / No / Partial | Found (What-Lx) | Measured |
| Naive read cost to confirm the same finding | `<file>` in full, `<N>` words (~`<M>` tokens) | `<N>` words (~`<M>` tokens) — the generated context package | Measured |
| `graphify benchmark` reduction (if run) | naive-full-corpus-read baseline | `<N>`x fewer tokens/query (`<node/edge counts>`) | Measured |

Every cell is tagged `Measured` or `Inference` per §5-§6 of `../EVIDENCE-METHODOLOGY.md` — never
leave a number untagged. If a comparison wasn't run for this case, omit the row rather than
guessing.

## 1. Environment

What was installed, which CEP version/commit, which runtime (Claude Code, Copilot, Codex, etc.),
and any environment-specific setup (e.g. `context-config.yaml` hand-edits, `discover`/
`confirm-layers` runs) needed before the task began.

## 2. Task

The concrete task attempted — a real feature, bug fix, or question, stated the way a developer
would actually phrase it. Not "test the tool" — the actual work item.

## 3. Source set

Which layers were populated and how (What-L3/L2/L1, How-L2/L1), what each layer's `path`/
`include_roots`/`exclude` resolved to, and whether population required the `discover`/
`confirm-layers` workflow or hand-editing `context-config.yaml`.

## 4. Package generation

What command(s) were actually run (`graphify update`, `ult-context-generate`, etc.), and what the
generated context package contained — real counts (nodes/edges, files indexed, package size), not
estimates.

## 5. Detected gaps, conflicts, staleness

What the protocol's gap/conflict/staleness checks actually reported for this run. If nothing was
detected, say so explicitly and note whether that's expected (a clean, well-covered task) or itself
a finding (a check that should have fired but didn't — log that separately in the governance-side
defect log, not here).

## 6. Approval decision

What a human reviewer actually decided when presented with the package (approve as-is, approve with
addenda, reject/regenerate), and why.

## 7. Downstream use

How the approved package was actually used — e.g. handed to a coding agent, used to write a design
doc, used to answer a question directly. Quote or summarize what the package changed about the
downstream output, if anything.

## 8. Outcome

What happened, in concrete terms (a PR merged, a question answered correctly/incorrectly, time
saved or not). State plainly whether this outcome is **measured** (you can point to the artifact)
or **inference** (your judgment that the package helped/didn't, without a controlled comparison).

## 9. Limitations

What this case does *not* show — corpus size, task type, runtime, anything that limits how far the
outcome generalizes. Do not extrapolate from a small case to enterprise scale.

## 10. Lessons learned

What this case suggests CEP should keep doing, change, or investigate further — including any
tooling defect observed during the run (cross-reference the governance-side defect log entry ID
rather than duplicating detail here).

## Reproduction steps

Numbered, copy-pasteable steps (repo URL + pinned tag/commit, exact commands run, in order) so a
reader can reproduce this case study's package-generation and outcome sections independently, per
`references/reproducibility-guide.md`.
