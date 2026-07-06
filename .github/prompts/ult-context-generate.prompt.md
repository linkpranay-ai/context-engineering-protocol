---
name: context-generate
description: "Assemble a structured, source-attributed, human-approved context package (code graph, requirements, constraints, blast radius) before any spw artifact-generation skill runs. Piloting."
namespace: ult
version: 0.1.0
origin: ground-up
author: Pranay Mishra
maintainer: Pranay Mishra
adapted_from: ~
upstream_version: ~
released: 2026-06-10
tags: [utility, context-engineering, code-graph, requirements, constraints, blast-radius, pilot]
bundle: utilities
---

Read and follow the skill at `.github/skills/ult-context-generate/SKILL.md`.

When invoked directly by an engineer:
1. Read `context-config.yaml` at the project root for layer paths and budget settings.
   If it does not exist, copy
   `starter_kits/context_engineering/context-config.yaml.template` to the project
   root as `context-config.yaml` and adjust the layer paths, or proceed with the
   documented defaults.
2. Answer the Step 1 scope-clarification questions (feature/subsystem, task type, new
   vs. existing, scope boundary, known gaps) — all five are required.
3. The skill queries the code graph via `ult-codegraph` (`graphify-out/graph.json` —
   run `/ult-codegraph` first if it doesn't exist yet), reads `docs/requirements/` for
   What-L2, and — if `starter_kit/project_guidelines/COMPILED-GUIDELINES.md` exists —
   loads it as the Constraints layer (D11).
4. Resolve every open question and domain-enrichment suggestion one at a time; don't
   batch them.
5. Review the assembled product context package and org convention package, and say
   APPROVE for both — nothing downstream proceeds without explicit approval.
6. Once approved, hand off to the artifact-generation skill for the chosen task type
   (e.g. `/spw-write-user-story` for `user-story`).
