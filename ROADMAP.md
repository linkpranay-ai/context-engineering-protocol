# Roadmap

What's planned beyond v0.1.0, roughly prioritized. Nothing here has a committed date — this is a
disclosure of known gaps and candidate next work, not a promise. Open an issue if one of these
would unblock your project; that's the signal used to reprioritize this list.

## 1. Installer script

**Status: not started — top priority.** Several `SKILL.md` files already reference
`install.ps1` / `install.sh -InitProject` as how a consuming project gets set up, but no such
script exists yet. Today, adopting this protocol in a new project means manually copying
`.github/skills/`, `.github/prompts/`, and the generated `AGENTS.md`/`.cursor/rules/` files into
the target repo. Confirmed workable but tedious during the Phase 9 dogfood run against
`Textualize/textual`. Scope: a script that copies the skill set, optionally scaffolds
`context-config.yaml` from the template, and reports what it did — not a package-manager-style
installer with version pinning (that's a later concern, if this ever needs to support multiple
protocol versions coexisting).

## 2. How-L1 implementation

**Status: specified, not built.** The intended design — what it ingests (org-wide process
standards: CMMI, ISO 9001, IEEE process standards), where it slots into `ult-context-generate`'s
flow, how it would be gated — is written out in
[`PROTOCOL.md §5`](PROTOCOL.md#5-how-l1--specified-now-built-later-phase-2). Building it means a
`context-config.yaml` schema addition (`how_l1.path`, `how_l1.md_index_profile`, etc.) and a new
query step between the existing How-L2 check and the What-layer gap detection. Reuses the same
`md_index.py` indexing mechanism What-L1 already uses — this is largely a wiring/gating task, not
new infrastructure.

## 3. Cross-file citation resolution

**Status: spec written, not implemented.** Today's `cross_refs` resolution in `md_index.py` is
single-hop and same-file — `(see clause 7.5)` resolves if `7.5` is a heading in the *same* file,
but a reference that spans files (`"see TS 38.214 clause 5.2.2"` from a different indexed
document) isn't followed. The design for multi-hop, cross-file resolution is already written:
see [`scripts/README.md` §"Future work (R9): cross-file citation resolution"](.github/skills/ult-context-generate/scripts/README.md)
for the full spec, including why it's deliberately deferred until confidence-scoring on
single-file resolution is solid first.

## 4. `graphify merge-graphs` multi-root fix

**Status: known broken, documented workaround.** Multi-root repos (more than one independent
source tree) can't currently merge their per-root graphs into one. Workaround: point
`ult-codegraph` at one root at a time and treat each as independent for now. Root-caused but not
yet fixed.

## 5. Cursor live-install validation

**Status: generated, doc-verified, not field-tested.** `catalog/export_adapters.py` generates
`.cursor/rules/*.mdc` deterministically from each skill's `SKILL.md` frontmatter, checked against
Cursor's currently published docs for format correctness — but never confirmed against a real
Cursor install actually picking up and invoking a skill end-to-end (Claude Code and GitHub
Copilot both have this field validation already; Codex has it via Codex Desktop — see
[`README.md` "Runtime support"](README.md#runtime-support)). Needs someone with a Cursor
installation to run the same kind of dogfood pass Phase 9 already did for the other three
runtimes.

## 6. Real-corpus telecom example

**Status: interim synthetic version shipped.** [`examples/telecom-what-l1-demo/`](examples/telecom-what-l1-demo/)
demonstrates the What-L1 mechanism against a hand-authored, clearly-labeled synthetic 3GPP-style
fixture — real 3GPP spec text is gated/copyrighted and isn't freely redistributable into this
Apache-2.0 repo. If a properly-licensed, redistributable real-spec corpus becomes available (or
someone wants to run the same commands against their own licensed corpus and contribute a
sanitized writeup), swapping it in is a documentation-only change — see that demo's "Using your
own real corpus" section for the exact steps, which already work today with no code changes.

## 7. Smaller, lower-priority items

- **Independent token-cost measurement.** `ult-context-generate`'s token-cost/savings claims are
  currently partly self-reported from the tool's own runs, not independently measured against a
  large, real-world repo at scale.
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
