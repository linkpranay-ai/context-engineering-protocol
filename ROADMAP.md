# Roadmap

What's planned beyond v0.1.0, roughly prioritized. Nothing here has a committed date — this is a
disclosure of known gaps and candidate next work, not a promise. Open an issue if one of these
would unblock your project; that's the signal used to reprioritize this list.

Some items below draw on
[Meirtz/Awesome-Context-Engineering](https://github.com/Meirtz/Awesome-Context-Engineering)
(survey: arXiv:2507.13334) for patterns worth adapting into this protocol — see the inline
citations on items 1 and 9. See "Not on this roadmap" for patterns considered and deliberately
left out.

## 1. Cross-file citation resolution

**Status: implemented (Phase A + Phase B).** `md_index.py`'s `cross_refs` resolution now spans
the whole indexed corpus, not just the referencing file. Phase A (schema v1.1) made same-file
resolution distinguish `resolved` / `unresolved-not-found` / `unresolved-ambiguous` instead of
silently guessing. Phase B (schema v1.2) added the cross-file hop itself: a reference like
`IEEE 802.11-2020 §9.3.2` in one file resolves to a heading in a *different* indexed file, joined
on a new file-level `doc_id` front-matter field, matched by exact string equality only (never
fuzzy). See [`scripts/README.md` §"Cross-file citation resolution (R9) — implemented (Phase
B)"](.github/skills/ult-context-generate/scripts/README.md) for the full mechanism, and
[`examples/cross-file-resolution-demo/`](examples/cross-file-resolution-demo/) for a runnable,
verified demo. Built against a small synthetic 2-3 file corpus rather than waiting for a real
multi-spec corpus (a deliberate override of the original spec text, approved by the project
owner). The confidence-scoring ideas below (SelfCite, GraphRAG) were considered as a possible
gate before implementing this; they were not needed in practice — the deterministic
exact-match-or-fail approach was sufficient and is kept for reference as related prior art, not
as a design that was adopted.

## 2. Selective/granular install

**Status: implemented.** `install.sh`/`install.ps1` now accept `--only <skill1,skill2>`/
`-Only <skill1,skill2>` — a comma-separated list of skill directory names (validated against the
real `.github/skills/*` directories; an unknown name is a clear, immediate error) that installs
just those skills' `.github/skills/<name>/`, `.github/prompts/<name>.prompt.md`, and
`.cursor/rules/<name>.mdc`, instead of the full set. The merged `AGENTS.md` block is filtered down
to just the selected skills' rows too, so a partial install never advertises a skill it didn't
actually copy in. Full install (no `--only`/`-Only`) is unchanged. Covered by three new cases in
`test_install_scripts.py`, run against both installers.

## 3. `SKILL.md` / agentskills.io compatibility check

**Status: spike done (2026-07-09), closed as known/accepted divergence.** Diffed all 5 skills'
frontmatter against [agentskills.io's specification](https://agentskills.io/specification).
`description` is fully compliant (177-219 chars observed, well under the spec's 1024-char cap and
inside our own stricter 200-char house rule). Two real divergences found, both judged intentional
rather than accidental:

- **`name` doesn't always equal the directory name.** The spec requires exact equality; 3 of 5
  skills (`ult-codegraph` → `name: codegraph`, `ult-context-generate` → `name: context-generate`,
  `ult-repo-layout` → `name: repo-layout`) drop the namespace prefix. This is this repo's
  documented convention, not a slip — `CONTRIBUTING.md`'s own frontmatter example shows
  `name: context-generate`, and the `namespace`/`name` split exists specifically so a short name
  can be reused across namespaces.
- **11 custom top-level fields** (`namespace`, `version`, `origin`, `author`, `maintainer`,
  `adapted_from`, `upstream_version`, `released`, `tags`, `bundle`, `tier`, and one skill's
  `dependencies`) aren't in the spec's defined set. The spec's own `metadata` field exists for
  exactly this, but it's strictly flat string→string, and `tags` (a list) / `dependencies` (a
  nested map) don't fit that shape without lossy flattening.

**Why this is closed, not deferred as a fix-it item:** neither divergence is currently live —
none of the 4 runtimes this repo supports (Claude Code, GitHub Copilot, Cursor, Codex) read
`SKILL.md` frontmatter directly per the agentskills.io spec; `catalog/export_adapters.py`
generates each runtime's actual input from it and keys off the **directory name**, never the
`name:` field. "Fixing" `name` would mean reversing a documented convention (rewriting
`CONTRIBUTING.md`'s contract and dropping namespace/name reuse for every future skill) to satisfy
a compliance need nobody has yet — a bigger, more disruptive change than the divergence itself.
**Revisit trigger:** if this repo ever adds support for a runtime that reads `SKILL.md` frontmatter
directly per the agentskills.io spec (none currently planned), re-open this as a real item then —
cheap to fix at that point since nothing depends on the current shape either way.

## 4. `graphify merge-graphs` multi-root fix

**Status: resolved via upstream fix, verified empirically (2026-07-09).** The documented crash
(`NetworkXError: All graphs must be graphs or multigraphs`) reproduced exactly as described on
the then-installed `graphifyy` 0.8.35: `graph.json` carried no `directed`/`multigraph` keys at
all. Upgrading to the latest PyPI release, `graphifyy` 0.9.11, fixes it — `graph.json` now
persists both keys, and `graphify merge-graphs` correctly composed a synthetic two-root repro
(3 nodes/3 edges per root) into one 6-node/6-edge graph with repo-tag-prefixed node IDs and no
collisions. The true minimum fixed version between 0.8.35 and 0.9.11 wasn't bisected (not worth
it for a doc pin); `ult-codegraph/SKILL.md` now requires `>= 0.9.11`. No upstream issue/PR was
needed — this was purely a stale local install. All references to the old workaround
(`SKILL.md`, `CONSUMING-CODE-GRAPH.md`, `README.md`, `CHANGELOG.md`) have been updated, and
`SKILL.md` Step 0 now documents multi-root indexing + merge as a supported path.

## 5. Cursor live-install validation

**Status: generated, doc-verified, not field-tested.** `catalog/export_adapters.py` generates
`.cursor/rules/*.mdc` deterministically from each skill's `SKILL.md` frontmatter, checked against
Cursor's currently published docs for format correctness — but never confirmed against a real
Cursor install actually picking up and invoking a skill end-to-end (Claude Code and GitHub
Copilot both have this field validation already; Codex has it via Codex Desktop — see
[`README.md` "Runtime support"](README.md#runtime-support)). Needs someone with a Cursor
installation to run the same kind of dogfood pass Phase 9 already did for the other three
runtimes.

## 6. Project memory feedback loop

**Status: implemented (2026-07-09).** `ult-context-generate/SKILL.md` now has a
`### Step 9.5 — Optional: persist corrections to project guidelines`, running right after the
Step 9 human-approval gate. It reuses the mechanism `compiling-project-guidelines` already had —
the `## Recent Observations (pending compile)` inbox in `COMPILED-GUIDELINES.md`, previously
written only by consuming skills per `CONSUMING-COMPILED-GUIDELINES.md` step 5 — rather than
inventing a second state store. Two triggers, both asked as one explicit opt-in question per
item, never written silently:

1. A resolved `constraint-lateral` conflict (two `COMPILED-GUIDELINES.md` scoped sections
   disagreeing at an interaction point this feature touched).
2. A rejected fallback item (What-L1/LLM-knowledge/web/How-L1) whose stated rejection reason
   reads as general, reusable project guidance rather than feature-specific judgment.

`compiling-project-guidelines/SKILL.md`'s "On re-run" step 1 now folds entries attributed
`[ult-context-generate]` in as pre-resolved `## Noted Tensions`, rather than re-running them
through the conflict Q&A — the human already made that call once.

**Deliberately out of scope for v1** (revisit only if a real need surfaces): L2-vs-L3
contradictions (code vs. requirements — wrong artifact, not a How-L2 convention) and
`constraint-vertical` conflicts (already `compiling-project-guidelines`'s own turf via its Step
4/5; `ult-context-generate` only ever carries forward an already-existing unresolved one, it
never mints a new one). Still stays inside the human-gate philosophy — this persists an
*already-human-made* decision, never auto-infers one from agent behavior; no keyword-triggered
auto-reflection hook was added.

## 7. Context-package usage telemetry

**Status: implemented (2026-07-09) — aggregation-report slice only.** Supersedes and folds in
the earlier "independent token-cost measurement" item. The consume/tag loop
(`CONSUMING-CONTEXT-PACKAGE.md` step 9) already records, per addendum, exactly which
`context_items` a downstream artifact actually cited — that write side was already shipping, but
nothing read it back. `scripts/usage_report.py` is the missing read/aggregate side: it scans
every `contexts/<id>.yaml` package and its sibling `<id>_*.addenda.yaml` files and writes
`contexts/USAGE_REPORT.md` with overall cited/never-cited totals, a by-layer never-cited
breakdown (the "which layers go unused, suggesting over-inclusion" signal), a
fallback-items-specifically breakdown, and a per-package table. The addendum schema also gained
two optional fields, `session_id` and `tokens_used` (`CONSUMING-CONTEXT-PACKAGE.md` step 9), so
real per-run token counts can start being collected the same way citations already are.

**Deliberately out of scope for v1** (revisit only if a real need surfaces):

- **OpenTelemetry GenAI semantic-convention export.** Grepped repo-wide: zero existing OTel
  infrastructure or demand. Building an exporter with no consumer is the speculative-infrastructure
  trap this project otherwise avoids by doing a design pass before committing (the same discipline
  items 9/11's MCP-backed sources went through before shipping) — a plain markdown report is the
  right v1 shape until an actual observability pipeline wants to ingest this.
- **An independently-measured token-cost/savings number.** `README.md` already discloses this is
  "partly self-reported... not yet independently measured against a real, large repo," and that
  remains true — a real number needs real harness-level session data collected across pilot runs,
  which doesn't exist yet. This pass adds the `tokens_used` field needed to *start* collecting
  that data for real; `usage_report.py` reports "no measured runs yet" rather than fabricate a
  figure, and will keep saying so until an operator actually records one.

## 8. Real-corpus telecom example

**Status: interim synthetic version shipped.** [`examples/telecom-what-l1-demo/`](examples/telecom-what-l1-demo/)
demonstrates the What-L1 mechanism against a hand-authored, clearly-labeled synthetic 3GPP-style
fixture — real 3GPP spec text is gated/copyrighted and isn't freely redistributable into this
Apache-2.0 repo. If a properly-licensed, redistributable real-spec corpus becomes available (or
someone wants to run the same commands against their own licensed corpus and contribute a
sanitized writeup), swapping it in is a documentation-only change — see that demo's "Using your
own real corpus" section for the exact steps, which already work today with no code changes.

## 9. MCP-backed What-L1 source

**Status: implemented (2026-07-09).** Resolves the open design question below with a
mirror-then-index design: MCP becomes a way to *populate* `what_l1.path`, not a new content-item
type reaching `md_index.py`. `references/what-l1-fallback-query.md` Step 0 (only runs if
`what_l1.mcp_source` is set — default `[]`, so an unconfigured project sees zero behavior change)
has the agent call each configured MCP tool directly, then hands the fetched text to
`scripts/mcp_mirror.py`, which mirrors it to a local `.md` file under `what_l1.mcp_mirror_path`
(default `<what_l1.path>/.mcp-mirror/`) and only rewrites that file — bumping its mtime — when its
content hash (`content_hash8`, reused from `content_hash.py`) differs from the last run's recorded
hash. Because `md_index.py`'s `gather_md_files()` already recurses (`target.rglob("*.md")`),
mirrored files are picked up by the existing `md_index.py index <what_l1.path>` call with **zero
changes to `md_index.py` itself** — content-hash comparison substitutes for mtime as the
fetch-layer change signal, and composes cleanly with the existing mtime-based `--stale-check` one
layer down. See [`examples/mcp-what-l1-demo/WALKTHROUGH.md`](examples/mcp-what-l1-demo/WALKTHROUGH.md)
for a real, run command sequence validating this end-to-end (mirror → index → query →
citation-following, then a simulated upstream change triggering a correct rebuild), and
`scripts/README.md`'s `mcp_mirror.py` section for the CLI reference.

<details>
<summary>Original open design question (resolved above)</summary>

Today What-L1 (external references) is static `.md` files under a local directory, indexed once by
`md_index.py`. [MCP](https://modelcontextprotocol.io) is increasingly treated as a first-class
context source in comparable tooling — the Awesome-Context-Engineering survey lists MCP/A2A under
"Open Agent Protocols". Letting `context-config.yaml`'s `what_l1` section point at an MCP resource
URI, in addition to a local directory, would make external references live instead of a manual
drop-zone. The open design question: every MCP call would need the same
source-attribution/content-hash discipline as every other source, or it breaks staleness
detection's entire premise (§3.3) — that has to be solved before this becomes a real backlog item,
not just bolted on.

</details>

## 10. Runtime scope-filtering at consumption time

**Status: speculative, pending confirmed need.** `compiling-project-guidelines` already tags scope
(path glob / language boundary) while compiling `COMPILED-GUIDELINES.md` — that part is done. What
it explicitly does *not* do (per its own `SKILL.md`) is enforce those scopes at runtime; a
consuming skill has to filter by scope itself today. Auto-filtering the compiled file down to the
scopes touched by a given change, at consumption time, is plausible — but nobody has yet hit a
concrete case where manual filtering wasn't good enough. Don't build this speculatively; revisit
if/when a real consuming skill needs it.

## 11. MCP-backed How-L1 source

**Status: implemented (2026-07-09).** Same mechanism as item 9, applied to How-L1
(`references/how-l1-fallback-query.md` Step 0, `how_l1.mcp_source`/`how_l1.mcp_mirror_path`/
`how_l1.mcp_manifest_path`, default `mcp_source: []` — zero behavior change when unset). The
sharper-edged open question below turned out not to need two treatments: content-hash comparison
is agnostic to how often the underlying source revises — an org's QMS document-management system
(frequently-revised) just means its mirror file rewrites more often, and a published
industry-standards body (CMMI, ISO, SAFe; infrequently-revised) means its mirror file rewrites
less often. One mechanism correctly handles both with no special-casing. See
[`examples/mcp-what-l1-demo/WALKTHROUGH.md`](examples/mcp-what-l1-demo/WALKTHROUGH.md)'s closing
"How-L1 works identically" section — no separate demo directory, since the only difference from
What-L1's demo is which `context-config.yaml` block and fallback-query doc supplies the paths.

<details>
<summary>Original open design question (resolved above)</summary>

The same MCP-as-source question raised in item 9 for What-L1 applies to How-L1 (now shipped in its
gap-triggered, file-based form — see
[`PROTOCOL.md §5`](PROTOCOL.md#5-how-l1--gap-triggered-task-type-scoped-piloting)): an org's QMS
document-management system and published industry-standards bodies (CMMI, ISO, SAFe) are natural
candidates for a live MCP resource rather than a static local directory of `.md` files. The open
question from item 9 likely has sharper edges here: an org QMS system and a standards body are two
very different kinds of source (internal, frequently-revised policy vs. externally-versioned,
infrequently-revised standard), so this may need two different staleness/attribution treatments
rather than one. Needs a design pass before it's a committed item.

</details>

## 12. Three-tier How dimension (mirroring What-L1/L2/L3)

**Status: idea, not yet designed — needs its own dedicated brainstorm before it's a roadmap
commitment.** Today's How dimension is two-tier: How-L2 (this project's own compiled conventions)
and How-L1 (external process standards — CMMI, ISO 9001, IEEE, SAFe). That collapses two distinct
things into one tier: the *external* standard itself, and *this organization's own* QMS/policy
instantiation of it — closer in spirit to how the What dimension already separates "external
reference" (What-L1) from "this product's own requirements" (What-L2) from "the code itself"
(What-L3). A candidate 3-tier remapping: today's How-L2 (project-specific conventions) becomes
How-L3; a new How-L2 covers org-wide QMS, policies, and processes (this organization's own
authoritative process documentation — distinct from both the project-level conventions below it
and the external standard above it); How-L1 becomes the external standard itself (CMMI, ISO, SAFe),
unchanged in content from what How-L1 already ingests today. Not blocking on anything else: the
content How-L1 ingests (external process standards) maps directly onto whatever the final top tier
is named, so keeping today's shipped 2-tier version and revisiting the tier split later is a
low-cost path, not throwaway work. Needs a dedicated design pass (would touch `PROTOCOL.md`'s
layer-model table, §2) before this is more than an idea.

## 13. Comprehensive How-L1 validation (pre-1.0 gate)

**Status: light smoke-test done (2026-07-08), full validation deferred.** How-L1's mechanism has
been proven end-to-end against a small synthetic corpus — see
[`examples/how-l1-dogfood-demo/WALKTHROUGH.md`](examples/how-l1-dogfood-demo/WALKTHROUGH.md), which
confirms indexing, task-type querying, D14 citation-following, and the resulting `layer: how-l1`
context-item shape all work against real `md_index.py` output using the `generic` profile. What
that pass deliberately didn't cover: a real or representative CMMI/ISO/IEEE-style corpus (licensing
permitting) or a larger synthetic one exercising multiple clause depths and several
cross-references within a file; more than one task type queried against the same corpus, to confirm
ranking/relevance holds up beyond a single demo query; and — most importantly — an actual live
`ult-context-generate` run where an agent walks Step 2's D8 branch into Step 2.1 and Step 9's
`[HOW-L1 FALLBACK ITEMS — REVIEW]` block itself, the way Phase 9 dogfooded the other four skills
end-to-end against `Textualize/textual`, rather than a hand-simulated CLI sequence. This is the
recommended gate before flipping any project's `how_l1.enabled` default guidance from "leave false
until you've verified it yourself" to something more confident — a natural fit for a pre-1.0
release checklist.

## 14. Smaller, lower-priority items

- **Capability-profile / tool-restriction frontmatter.** No skill currently declares an
  `allowed-tools`-style field constraining what it's permitted to call — every skill assumes full
  tool access from its runtime. Worth adding once there's a concrete use case (e.g. a read-only
  variant of a skill) rather than speculatively.

## Not on this roadmap

Some things are deliberately out of scope rather than deferred:

- **A hosted/managed version of this protocol.** This repo ships skills you run inside your own
  agent runtime — there's no plan for a hosted service.
- **Automatic conflict resolution.** The protocol's whole premise is that genuine contradictions
  get a human decision, not a heuristic pick. That's not a gap to close later — see
  [`PROTOCOL.md §3.1`](PROTOCOL.md#31-conflict-detection--blocks).
- **Kaizen-style debugging prompts** (5 Whys, root-cause-tracing, PDCA). A reasoning-technique
  library is a different product surface from a context-provenance protocol; out of scope here.
- **Full spec-driven task lifecycle management** (`/add-task`/`/plan-task`/`/implement-task`,
  draft/todo/done folders, Arc42). Overlaps with generic project-management tooling. The one
  kernel worth keeping — an aspect-scoped context package optionally citing an Arc42-style ADR as
  a What-L2 input — doesn't require building a task tracker, so it's not on this list as its own
  item.
- **Automatic reflection or self-generated context without a human gate.** Several reviewed
  patterns (auto-triggered reflection hooks, self-generated context) skip the human decision this
  protocol treats as load-bearing (§3.4, and `PROTOCOL.md §3.1`'s no-automatic-conflict-resolution
  stance). Item 6 above takes the useful part of this idea — persisting lessons learned — but only
  after a human has already made the call, never automatically.
