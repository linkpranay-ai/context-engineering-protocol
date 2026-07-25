# Glossary

Terms as used throughout this repository — [`PROTOCOL.md`](PROTOCOL.md), `SKILL.md` files, and
`user_guides/`. This is the authoritative definition of each term for this project; if a shorter
gloss appears elsewhere in the docs, this file wins.

See [Interpretation of MUST/SHOULD/MAY](PROTOCOL.md#interpretation-of-mustshouldmay) for how
normative keywords in this glossary and in `PROTOCOL.md` should be read.

| Term | Meaning |
| --- | --- |
| **Authoritative context** | Engineering information whose source, ownership, and applicability can be assessed for a task. This does not imply universal truth — What-L1 items, for example, are sourced and assessable but explicitly not authoritative for this product (§2). |
| **What-L3** | The code itself, represented as a generated cross-file knowledge graph (`ult-codegraph` / `graphify`). |
| **What-L2** | This product's own requirements and specification documents. |
| **What-L1** | External reference context — industry standards, competitor docs, architecture whitepapers. An informative fallback, never product authority, surfaced only when What-L3 and What-L2 both have no coverage for an aspect (§3.2). |
| **How-L2** | An org or project's compiled, scope-aware conventions — style guides, templates, examples. |
| **How-L1** | Org-wide **process** standards (e.g. CMMI, ISO 9001, IEEE process standards), distinct from How-L2's project-specific conventions. Piloting; see §5. |
| **Constraints** | The cross-cutting third dimension (§2.1): coding/design conventions, compliance/regulatory requirements, and scheduling/dependency constraints that bound a solution without belonging to a specific What or How layer. Optional infrastructure, not a gap when absent. |
| **Context discovery** | Locating potentially relevant engineering artifacts or sources before packaging. |
| **Context package** | A structured, source-attributed package of context assembled for a bounded task and explicitly approved by a human before downstream use. |
| **Packaging** | Assembling context for a bounded task while retaining source boundaries and metadata (§3). |
| **Addendum** | A consumer-written, append-only companion record that adds discovered context or decisions without rewriting an approved package. |
| **Gap detection** | Per-aspect classification of whether What-L3/What-L2 coverage exists for a piece of work; a complete gap is surfaced to a human rather than silently filled (§3.2). |
| **Conflict detection** | Identification of a genuine requirement-versus-code contradiction, or an unresolved Constraints conflict (`constraint-lateral` / `constraint-vertical`). Conflicts block approval until a human resolves them (§3.1). |
| **Staleness detection** | A signal that a derived source (code graph, compiled-guidelines cache) may predate the current repository state. Non-blocking — it nudges, it does not stop assembly (§3.3). |
| **Human approval** | Explicit reviewer confirmation that a context package may be used as primary context by downstream work. Mandatory, not configurable away (§3.4, §4). |
| **Provenance** | Information identifying an artifact's source, lineage, ownership, and relevant change history — required on every `context_items` entry (§4). |
| **Delivery** | Making an approved, packaged context available to a consumer through an implementation-specific mechanism. |
| **Lifecycle** | Creation, review, change, deprecation, and retirement behavior for context or its governing rules. |
| **Protocol** | A documented behavioral process and consumer contract. This repository does not define a universal data model, transport, storage, or interoperability standard (§4). |
| **Conformance** | Whether a system's actual behavior satisfies the mandatory requirements this protocol defines, for a specific conformance subject. See [`CONFORMANCE.md`](CONFORMANCE.md). |
| **Conformance subject** | One of implementation, consumer, runtime adapter, or workflow (below) — the kind of thing a conformance claim is made about. Orthogonal to the Roles below: Roles describe who is accountable during package assembly; conformance subjects describe what kind of artifact can claim conformance. See [`CONFORMANCE.md`](CONFORMANCE.md) §2. |
| **Implementation (conformance subject)** | A concrete system that implements this protocol's behavioral state machine end-to-end (discovery, gap/conflict/staleness detection, package assembly, human-approval gate). See [`CONFORMANCE.md`](CONFORMANCE.md) §2. |
| **Consumer (conformance subject)** | A downstream skill, tool, or workflow that uses an approved context package as primary context, following the discover→confirm→load→spot-check→cite→tag contract (§4). See [`CONFORMANCE.md`](CONFORMANCE.md) §2. |
| **Runtime adapter** | A generated, runtime-specific artifact (e.g. `.cursor/rules/*.mdc`, a merged `AGENTS.md` block) that surfaces this protocol's skills inside a particular agent runtime. A conformance subject in its own right. See [`CONFORMANCE.md`](CONFORMANCE.md) §2. |
| **Workflow (conformance subject)** | The broader process — design, planning, test generation, review, etc. — that consumes an approved context package as input but is not itself part of context assembly. See [`CONFORMANCE.md`](CONFORMANCE.md) §2. |

Terms here describe the protocol's current, implemented behavior.
