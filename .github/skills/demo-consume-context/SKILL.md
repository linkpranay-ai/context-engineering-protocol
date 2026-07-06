---
name: demo-consume-context
description: Worked example that discovers, loads, and tags a context package per CONSUMING-CONTEXT-PACKAGE.md, then writes a reverse-index addendum — proves the produce/consume/tag loop end-to-end. Do NOT use for real feature work.
namespace: demo
version: 0.1.0
origin: ground-up
author: Pranay Mishra
maintainer: Pranay Mishra
adapted_from: ~
upstream_version: ~
released: 2026-07-06
tags: [demo, utility, context-engineering, worked-example, tagging]
bundle: utilities
tier: draft
---

# Demo: Consuming a Context Package (worked example)

## Overview

This is a minimal, from-scratch worked example — not a production skill. It
exists to prove `ult-context-generate/CONSUMING-CONTEXT-PACKAGE.md`'s
consumption contract end-to-end without depending on any larger downstream
skill set. Given a feature name, it produces a one-paragraph "demo note" and
demonstrates every step of the tag loop: discover an existing package (or
proceed without one), cite it while writing, tag the output, and write back
a reverse-index addendum so the package records who consulted it.

## Steps

1. **Follow `CONSUMING-CONTEXT-PACKAGE.md` steps 0–3** exactly, using
   whatever input you were given (a bare feature name is enough — it skips
   step 0's tag-discovery scan and goes straight to step 1's glob check
   against `contexts/`).

2. **Write the demo note** to `outputs/demo-notes/<feature-slug>.md` — a
   single paragraph in plain language describing the feature. If a package
   was loaded in step 1 above, the paragraph must name and paraphrase at
   least one `decisions_log`/`decisions` entry or `context_items` entry by
   its `summary`, so the loaded content is visibly used, not just fetched.
   If no package was found, write the paragraph from the feature name alone
   and say so explicitly in the note's first line.

3. **Tag the output** — per step 9 of the contract, add a
   `**Context package(s):** <id>@<hash8>` line at the top of the note for
   every package consulted (omit this line entirely if none was).

4. **Write the reverse-index addendum** — per step 9's "Reverse-index
   addendum" subsection, append a `kind: reference` entry to each consulted
   package's sibling `contexts/<package-id>_<date>.addenda.yaml`
   (`added_by: demo-consume-context`, `artifact:` the note's path).

5. **State which mode was used**, per step 8: `"Context package consulted:
   <id>@<hash8> (...)"`, or `"No context package found — proceeding without
   it."`

## Do NOT use for

Real feature work of any kind — this skill's only output is a one-paragraph
demo note used to exercise the consumption contract. For actual context
package generation, use `ult-context-generate`. For a real downstream
consumer, follow `CONSUMING-CONTEXT-PACKAGE.md` directly from whatever skill
is doing the real work, rather than routing through this demo.
