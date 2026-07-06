---
name: demo-consume-context
description: "Worked example: discover, load, and tag an approved context package, then write a reverse-index addendum. Proves the produce/consume/tag loop end-to-end. Not for real feature work."
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
---

Read and follow the skill at `.github/skills/demo-consume-context/SKILL.md`.

When invoked directly by an engineer:
1. Ask for (or accept as an argument) the feature name to write a demo note
   about.
2. Follow the skill's 5 steps exactly — this exercises
   `ult-context-generate/CONSUMING-CONTEXT-PACKAGE.md`'s discovery, load,
   tag, and reverse-index-addendum steps against a trivial one-paragraph
   artifact.
3. Report back the note's path and which consumption mode was used (context
   package found vs. none found), so the engineer can see the loop actually
   ran.
