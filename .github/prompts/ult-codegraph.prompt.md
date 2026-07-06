---
name: codegraph
description: "Generate or refresh a codebase knowledge graph (graphify) at its fixed graphify-out/ location so spw-* skills can query cross-file relationships. Piloting — re-run after code changes."
namespace: ult
version: 0.1.0
origin: ground-up
author: Pranay Mishra
maintainer: Pranay Mishra
adapted_from: ~
upstream_version: ~
released: 2026-06-08
tags: [utility, code-graph, graphify, codebase-analysis, pilot]
bundle: utilities
---

Read and follow the skill at `.github/skills/ult-codegraph/SKILL.md`.

When invoked directly by an engineer:
1. Check whether `graphify` is installed (`graphify --help`); if not, run
   `uv tool install graphifyy` (or `pipx install graphifyy`).
2. Run `graphify update . --no-cluster` to (re)generate the graph (no LLM
   needed — incremental on subsequent runs, only re-parsing changed files).
3. Optionally run `graphify cluster-only . --no-label` to also produce
   `GRAPH_REPORT.md` (community *names* stay generic without a configured
   LLM backend — that's fine, the graph data itself is unaffected and the
   report's God Nodes / Surprising Connections / Import Cycles sections are
   useful either way).
4. Report back: how many nodes/edges were generated, and point the user at
   `graphify-out/GRAPH_REPORT.md` for the human-readable summary. Nothing to
   copy or normalize — `graphify-out/` is graphify's own fixed, predictable
   output location, and `spw-*` skills query it there directly (see
   `CONSUMING-CODE-GRAPH.md`).
