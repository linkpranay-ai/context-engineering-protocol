# `md_index.py` — deterministic markdown structural indexer

The "graphify for markdown." A standalone, **Python-3-stdlib-only** CLI that parses
markdown spec files into a structural index (headings, clause ids, section bounds,
resolved cross-references) and answers content queries against it — **with no LLM in
the loop**. This is the real, tested re-implementation of the deleted `ast_crossref.py`
prototype, built to close two gaps an internal review of external markdown-mining and
context-engineering prior art flagged: no regression coverage for the original
agent-simulated cross-file-resolution mechanism, and no deterministic index a consumer
could query without re-deriving it via an LLM each time.

Build-once → write JSON → skills query the JSON. Same contract graphify uses for code.

- **No third-party dependencies** — stdlib only (`argparse`, `re`, `json`, `hashlib`,
  `pathlib`, `datetime`), so it is vendorable for an OSS framework with no `pip install`
  step.
- **Runs on Windows** (developed/validated on Python 3.12.5 / PowerShell). Uses
  `pathlib`; normalises `\r\n` and lone `\r` line endings before parsing.
- **Domain-pluggable, not hardcoded to any one standards body.** Heading/clause-id
  conventions and cross-reference phrasings live in a small JSON "profile" file, not
  in the parser. Four ship today (`generic`/`3gpp`/`rfc`/`ieee`); adding a profile for
  your own domain's documents needs no code change — see **Profiles** below.

> Scope note: **R1, R2, R3, and R4** (including the `rfc.json`/`ieee.json` profiles, and the
> rewrite of `ult-context-generate/SKILL.md` Step 7.1 to shell out to this script) are all
> complete, with a regression suite in `tests/`. See `IMPLEMENTATION-NOTES.md` for the
> implementation history.

---

## Reuse beyond What-L1: large What-L2 corpora

This script is not specific to external specs. `ult-context-generate` Step 5
reuses the exact same `index`/`query`/`section_bounds` mechanism for a
project's **own** `what_l2.path` (default `docs/requirements/`) once it grows
past `what_l2.large_corpus_threshold` (default 10 `.md` files) — the `generic`
profile already indexes plain prose headings (with `clause_id: null` but real
`section_bounds`), so ordinary requirements docs need no profile of their own.
Only the output location differs: `what_l2.index_path` (default
`specs-out/l2_index.json`) instead of `what_l1.index_path`. No code changes —
same CLI, same schema, a different `-o`/index-path argument.

---

## CLI

```
python md_index.py index <dir-or-file> -o <output.json> [--profile generic|3gpp] [--stale-check]
python md_index.py query <index.json> "<term1> <term2> ..." [--top N]
python md_index.py query-batch <index.json> <queries.json> [--top N]
python md_index.py skeleton <index.json> [--max-depth N]
```

### `index`

Walks `<dir-or-file>` for `*.md` files (recursively for a directory; a single `.md`
file is also accepted), parses each, and writes the JSON index to `-o`.

- `--profile` selects the pattern pack (default `generic`). See **Profiles** below.
- `--stale-check`: if the output file already exists, is newer than every input file,
  **and** was built with the same profile, print "up to date" and exit 0 **without
  rewriting**. Otherwise rebuild. Mirrors graphify's build-once / incremental behaviour.

With a plaintext-house-style profile (`rfc`/`3gpp`/`ieee`), `index` also prints a warning
to stderr for any file whose heading count is anomalously low relative to its line count
(over 150 lines/heading, on files of 200+ lines). Those profiles only parse clause IDs and
cross-refs out of headings already written as real ATX (`#`)/Setext Markdown syntax — they
do not detect raw flush-left plaintext headings (e.g. unconverted RFC-editor `.txt`). A
warning here usually means the source needs markdown-ifying before indexing, not that the
profile is broken.

### `query`

Given a built index and a space-separated list of **OR'd** search terms (the gap topic
plus curated synonyms — exactly what `ult-context-generate` Step 7.1 does today via
grep), find sections whose **content** or title contains any term, ranked by total
match count (descending).

Content is scored against each heading's **own direct content only** — up to the next
heading of any level, not its full `section_bounds`. `section_bounds` (by the documented
convention below) extends through every nested child section too, so scoring the raw
match count over the full `section_bounds` range would make an ancestor heading
accumulate all of its descendants' matches and always outrank the specific subsection a
query is actually looking for. Since children are separately queryable/rankable as their
own results, narrowing the *scoring* window to a heading's own content loses no coverage
— it only stops that double-counting. The `section_bounds` value reported in each result
is unchanged; only what gets scanned for a match count is narrower.

The index does **not** store section text — `query` re-opens each source file and scans
only the relevant line ranges. Still zero-LLM, just file I/O. TOC-flagged headings
(`is_toc: true`) are skipped in query results.

Each result carries `file`, `clause_id`, `title`, `heading_id`, `line` (the heading
line), `section_bounds`, `match_count`, and the section's **resolved** `cross_refs` —
enough for the calling skill to `Read` just that line range and to follow citations.

### `query-batch` — R18

Same underlying `query_index()` as `query`, run once per entry of a JSON file mapping
an arbitrary key (e.g. an `aspect_id`) to its own list of search terms:

```json
{"1": ["session inactivity timeout", "re-keying"], "2": ["streaming", "incremental"]}
```

```powershell
python md_index.py query-batch specs-out\session.json queries.json --top 5
```

Output is a single JSON object on stdout, `{"<key>": [...results], ...}`, each
`results` list shaped exactly like `query`'s. This exists to let a single Python
process amortize the index-load + file-read cost across **multiple** aspects' queries
in one invocation, when a run has many gap topics to look up — see
`ult-context-generate/SKILL.md` Step 5/7.1 for when this is worth reaching for. It does
not change the documented per-aspect `query` default, and is not a guaranteed
token-reduction in itself (it shells out once instead of N times; whether that's worth
it depends on how many aspects a given run has).

### `skeleton` — ROADMAP item 13, progressive disclosure

```powershell
python md_index.py skeleton specs-out\session.json --max-depth 2
```

Reads an already-built `index.json` and prints `doc_id` + a compact heading/clause-ID
tree per file — `id`, `level`, `title`, `clause_id`, `line` only, with `is_toc` headings
suppressed. No `section_bounds`, no `cross_refs`, no body text, and no re-read of the
original `.md` source (the index never stored body text either — see `query`'s
docstring — so this is a pure reformat of what's already on disk, not a new parse
pass). `--max-depth N` further trims the tree to headings at or above level `N`.

This is a cheap "what does this corpus look like" pass for a large What-L1/How-L1
corpus, before spending a full `query` on it — skim the shape first, fetch a specific
section only once you know which one matters. It is opt-in and additive: nothing else
in this script's behavior changes if you never call it. On this repo's own
`examples/telecom-what-l1-demo/specs-out/index.json`, the skeleton is ~6.7x smaller than
the full index (measured: 39,076 bytes vs. 5,862 bytes) — the gap widens with corpus
size, since `section_bounds`/`cross_refs` overhead grows with heading count while the
skeleton's per-heading footprint stays fixed.

### Examples (using the two real validation files)

```powershell
# Build a 3GPP-profile index of TS 33.401
python md_index.py index `
  corpus\3gpp-ts33401-security-architecture-rel17.md `
  -o specs-out\ts33401.json --profile 3gpp

# Build a generic-profile index of the NIST excerpt
python md_index.py index `
  corpus\session-management.md `
  -o specs-out\session.json --profile generic

# Query the gap topic + synonyms (D13/D14)
python md_index.py query specs-out\session.json `
  "session inactivity timeout re-keying expir termination" --top 5
```

---

## Output schema (`index.json`) — v1.2, as implemented

```jsonc
{
  "schema_version": "1.2",
  "generated_at": "2026-06-11T...Z",   // ISO-8601 UTC
  "profile": "3gpp",
  "root": "C:/.../specs/external",       // absolute dir the file paths are relative to;
                                          // query re-opens sources via this root
  "files": [
    {
      "path": "session-management.md",   // POSIX-style, relative to "root"
      "sha256": "<sha256 of the file's ORIGINAL bytes>",
      "front_matter_lines": [1, 10],     // 1-based inclusive [start,end], or null
      "doc_id": "IEEE 802.11-2020",      // optional front-matter `doc_id:` scalar; null if absent.
                                          // corpus-wide join key for cross-file resolution (R9/Phase B)
      "headings": [
        {
          "id": "h_0042",                // stable within a file: h_ + zero-padded ordinal
          "style": "atx",                // "atx" | "setext"
          "level": 4,                    // 1..6 (setext is 1 or 2)
          "title": "7.2.9.2 K~eNB~ re-keying",  // pandoc {#...} attr tails stripped
          "clause_id": "7.2.9.2",        // profile-parsed; null if none
          "is_toc": false,               // true for a "Contents"/"Table of Contents" heading
          "line": 3509,                  // 1-based line of the heading TEXT
          "section_bounds": [3510, 3577],// [content_start, content_end], 1-based inclusive
          "cross_refs": [
            {
              "raw": "clause 7.5",
              "kind": "clause",          // clause | annex | see (from the profile pattern)
              "target_doc": null,        // non-null doc-designator (e.g. "IEEE 802.11-2020")
                                          // for a cross-file ref; null means same-file, as in v1.1
              "target_clause": "7.5",
              "resolved_file": null,     // matched file's "path", set only when target_doc
                                          // resolved to exactly one file
              "resolved_heading_id": "h_0107",  // null unless resolution_status == "resolved"
              "resolved": true,          // derived: true iff resolution_status == "resolved"
              "resolution_status": "resolved"
              // one of: resolved | unresolved-not-found | unresolved-ambiguous
              //       | unresolved-doc-not-found | unresolved-doc-ambiguous
              //       | unresolved-cross-file-pending (transient Pass-1 state, never
              //         present once build_index() completes Pass 2)
            }
          ]
        }
      ]
    }
  ]
}
```

### Line-numbering & `section_bounds` convention (read this — it reconciles D14)

- **All line numbers are 1-based.** `line` is the heading's **text** line.
- `section_bounds = [content_start, content_end]`, **1-based inclusive**, where:
  - `content_start = line + 1` for ATX; `= underline_line + 1` for Setext (so the bound
    begins at the first **body** line, **excluding** the heading title and, for Setext,
    its `===`/`---` underline).
  - `content_end = (line of the next heading at the same-or-higher level) − 1`,
    EOF-clamped. "Higher level" = numerically smaller `level` (H2 closes at the next H1
    or H2).
  - A section with no body is emitted as an empty range `[content_start, content_start−1]`.

  **Reconciliation with D14.** D14 wrote §7.2.9.2 as `[3509,3577]` and E.2.7 as
  `[10092,10106]`, phrasings that conflate the heading line (and, for Setext, the
  underline) with the section body. This schema keeps `line` and `section_bounds`
  **separate**, so:
  - §7.2.9.2 (ATX): `line: 3509`, `section_bounds: [3510, 3577]`. Same span as D14's
    `[3509,3577]`, minus the heading line which now lives in `line`.
  - E.2.7 (Setext): `line: 10091`, `underline at 10092`, `section_bounds: [10093, 10106]`
    = **14 body lines** — the *correct* count D14's deterministic script produced, **not**
    the wrong 28-line manual bound `[10085,10119]`. (D14's `[10092,10106]` started at the
    underline; we start one line later at the first real body line. Same 14-line section.)

### Source-file resolution & portability (`query`) — R15

`"root"` is the **absolute** path of the directory `index` was run against, recorded
at build time. `query` resolves each indexed file's source in this order:
`root / path` → `index_dir / path` (the directory containing `index.json` itself) →
`path` as literal (for absolute paths).

This means an `index.json` stays queryable if **copied or moved together with** its
source `.md` files, as long as their relative layout to each other is preserved (the
`index_dir / path` fallback covers this case even though `root` no longer exists on
the new machine). If a source file genuinely can't be found under any of the three
candidates — moved independently, deleted, or the index is stale — `query` prints a
`Warning: source file not found for indexed path '<path>' (tried: <candidates>) -
skipping` line to **stderr** and continues with the remaining files. It does not
crash; results for every file that *does* resolve are still returned, just with that
file's headings absent from the ranked output.

---

## Profiles (pattern packs) — R3

Domain conventions are **pluggable**, not hardcoded. A profile is a small JSON file in
`profiles/`; `--profile <name>` loads `profiles/<name>.json`. Four ship today:

- `generic.json` — the **default**. Permissive but conservative: parses dotted-numeric
  heading prefixes (`4.2.1 Title`) but will **not** invent clause ids from ordinary prose
  headings, and only matches the widest-common cross-ref phrasings (`clause/section …`,
  `(see …)`). Safe for internal docs / unknown standards bodies.
- `3gpp.json` — 3GPP/ETSI house style: clause ids like `7.2.9.2`, `E.2.7`, `5.3.4a`,
  `A.5`; cross-refs `clause(s)/subclause(s)/section(s) <id>`, `Annex <Letter>(.<id>)*`,
  `(see <id>)`.
- `rfc.json` — IETF RFC house style: dotted-numeric headings with an optional trailing
  `.` (`5.2.2.  Title`); cross-refs `Section(s) N.M`, `(see Section N.M)`.
- `ieee.json` — IEEE standard house style: dotted-numeric headings (`9.3.2 Title`);
  cross-refs `§9.3.2` (section-sign, with an optional leading document designator, e.g.
  `IEEE 802.11-2020 §9.3.2`, resolved cross-file against another indexed file's
  `doc_id` — see R9/Phase B below) and `Clause/subclause N.M`.

### Profile schema (so your own `<name>.json` is trivial to add)

```jsonc
{
  "name": "3gpp",
  "description": "Human-readable note on what this profile targets.",
  "clause_id_regex": "^([A-Z](?:\\.\\d+)+|[A-Z]?\\d+(?:\\.\\d+)*[a-z]?)\\s+(.+)$",
  // ^ Group 1 = the clause id; group 2 = the remaining title. Applied to a heading's
  //   (attribute-stripped) title. If it does not match, clause_id is null.
  "cross_ref_patterns": [
    {"regex": "...", "kind": "clause"}
    // Same-file form: group 1 must capture the target clause id. `kind` is a free-form
    // label copied into each cross_ref ("clause" | "annex" | "see" | <your-kind>).
    // Matched case-insensitively. Resolution is single-hop, same-file: the captured id
    // is looked up in THIS file's clause-id table only. resolution_status is one of
    // resolved | unresolved-not-found | unresolved-ambiguous (a clause id shared by more
    // than one heading is never guessed); resolved:false + resolved_heading_id:null for
    // either unresolved case.
    //
    // Cross-file form (R9/Phase B): use named groups `(?P<doc>...)` and
    // `(?P<clause>...)` instead of a bare group 1. `find_cross_refs()` detects named
    // groups via `m.groupdict()` and, when present, extracts `target_doc` from `doc`
    // (may be None if that part of the pattern didn't match — make the designator
    // group optional with `(?:...)?` so one pattern handles both same-file and
    // cross-file phrasings, e.g.
    // "(?:(?P<doc>IEEE\\s+[\\w.-]+)\\s+)?§\\s*(?P<clause>\\d+(?:\\.\\d+)*)"). A
    // non-null `target_doc` is matched against every other indexed file's `doc_id`
    // (exact string equality only, never fuzzy) to find `resolved_file`; patterns
    // with no named groups (all other shipped patterns) are unaffected and keep
    // resolving same-file exactly as v1.1.
  ],
  "toc_titles_to_suppress": ["contents", "table of contents"]
  // Case-insensitive exact-title match. A matching heading still appears in the list
  // (so ids/ordinals don't shift) but is flagged is_toc:true and skipped by `query`.
}
```

**To add a profile for another standards body** (e.g. ISO/ANSI): copy `generic.json`,
adjust `clause_id_regex` to match that body's heading-numbering convention, and add a
`cross_ref_patterns` entry per cross-reference phrasing it uses in prose. `rfc.json` and
`ieee.json` are worked examples of exactly this — `rfc.json` adds the optional trailing
`.` after the clause number (`5.2.2.  Title`) and the `Section N.M` cross-ref phrasing;
`ieee.json` keeps the plain dotted-numeric heading regex but adds the `§9.3.2`
section-sign and `Clause/subclause N.M` cross-ref phrasings. No code change is needed —
only a new JSON file plus, ideally, a fixture in `tests/fixtures/` (see "Testing" below).

---

## Parsing rules (what the script does, so you can trust the output)

1. **Mask code & front matter first.** Fenced code blocks (` ``` ` / `~~~`), indented
   code blocks (4-space / tab, requiring a preceding blank line per CommonMark), YAML
   `---…---` front matter at the file head, and an HTML-comment `<!-- … -->` header at
   the file head are all masked out **before** any heading/table detection. Nothing
   inside them can become a heading, Setext underline, or table separator.
2. **ATX headings:** `^#{1,6}\s+…`, trailing `#` run stripped.
3. **Setext headings:** a non-empty, non-masked text line immediately followed by a line
   of **only** `=` (→ level 1) or **only** `-` (→ level 2). A dashed line containing a
   `|` or `:` is treated as a **table separator**, never a Setext underline — this
   excludes `|---|---|` and alignment-colon variants `|:--|--:|` (and pipe-less colon
   variants).
4. **Clause id:** profile `clause_id_regex` applied to the (attribute-stripped) title.
5. **Section bounds:** the same-or-higher-level walk described above.
6. **Cross-refs:** profile `cross_ref_patterns` run over each section's body (scoped to
   its own bounds), de-duplicated, resolved single-hop against this file's clause-id
   table. Unresolved refs are kept with `resolved:false` (never dropped silently, never
   guessed) so a reviewer can see a dangling citation. `resolution_status` distinguishes
   *why* a ref is unresolved: `unresolved-not-found` (no heading in this file has that
   clause id) vs `unresolved-ambiguous` (more than one heading shares it — never guessed
   which one is meant).

See `IMPLEMENTATION-NOTES.md` for validation results and deferred work.

---

## Testing — R2

```
python -m unittest discover -s tests -v
```

`tests/fixtures/*.md` are small, hand-built `.md` files, each targeting one parsing edge
case the original agent-simulated mechanism never had a regression test for:

| Fixture | What it covers |
|---|---|
| `mixed_atx_setext.md` | ATX subclauses nested under Setext top-level clauses (the TS 33.401 shape); `Contents` Setext heading is TOC-suppressed; cross-ref resolves across the style switch. |
| `front_matter_and_code_fences.md` | YAML front matter; a fenced code block containing `# not a heading`, `---`, `\|---\|---\|` — none detected as structure. |
| `non_3gpp_numbering.md` | A trailing-period RFC heading (`5.2.2.  Title`) parses its clause id **only** under `rfc`; `generic`/`3gpp`/`ieee` correctly return `null` (no hallucinated clause id). A plain dotted-numeric heading (`9.3.2 Title`) parses identically under all four profiles. Also exercises the `ieee` `§` cross-ref. |
| `alignment_colon_tables.md` | `\|:--\|--:\|` alignment tables, plus a table-separator row immediately followed by a bare `---` — neither produces a spurious heading. |
| `cross_refs.md` | `clause`, `Annex`, and `(see …)` cross-refs, including one **dangling** ref to a clause id that doesn't exist — kept with `resolved:false` / `resolution_status: unresolved-not-found`, never dropped. |
| `cross_refs_ambiguous.md` | A clause id (`6.1`) shared by two headings in the same file (main body + annex) — a ref targeting it is kept with `resolved:false` / `resolution_status: unresolved-ambiguous`, never resolved to either heading by guessing. |
| `deep_nesting.md` | Clause ids 6 levels deep (`7.2.9.2.1.3`) parse correctly and the deepest section's bounds don't collapse to empty. |
| `golden_session_management.md` | Verbatim copy of the real 53-line NIST excerpt used to validate D13/D14; full `parse_file()` output snapshot-tested against `golden_session_management.expected.json`. |

`test_md_index.py` also covers `query_index` (ranking, TOC exclusion), the R15
missing-source-file stderr warning (still returns results for files that DO resolve),
`is_stale` (the `--stale-check` build-once contract, including profile-change
invalidation), `query-batch` (R18 — per-key results match an equivalent `query`), and
`skeleton` (ROADMAP item 13 — TOC exclusion, no body/structural fields, `--max-depth`
filtering, and CLI output matching the underlying `build_skeleton()` call directly).

The real TS 33.401 file (524 KB, external 3GPP copyright) is intentionally **not**
vendored as a fixture; `mixed_atx_setext.md` captures the same Setext/ATX structural
shape for the regression suite, and `IMPLEMENTATION-NOTES.md` records the full-file
validation run against the real spec.

---

## Cross-file citation resolution (R9) — implemented (Phase B)

`cross_refs` resolution now spans the whole indexed corpus, not just the
referencing file. A reference like `IEEE 802.11-2020 §9.3.2` written inside a
different file (e.g. an 802.1X spec) resolves to the heading in
`spec-802-11-mac.md` using `index.json`'s corpus-wide view — never guessing.
References with no document designator (`§9.3.2`, `clause 7.5`) keep resolving
within the same file exactly as v1.1.

**Mechanism.** No new top-level structure — cross-file resolution reuses the
same `cross_refs` array, with two new per-ref fields: `target_doc` (string or
`null`) and `resolved_file` (the matched file's `path`, or `null`). A new
file-level `doc_id` field (parsed from a `doc_id: <value>` line in front
matter, `null` if absent) is the corpus-wide join key.

**Backward-compatible pattern extension via named groups.** Rather than a new
JSON schema flag, profiles opt into cross-file capture with Python regex named
groups: `(?P<doc>...)` and `(?P<clause>...)`. `find_cross_refs()` checks
`m.groupdict()` — if `"clause"` is present, it extracts `target_doc`/
`target_clause` from the named groups (`doc` may be `None` when the
designator part of the pattern didn't match); otherwise it falls back to the
legacy `m.group(1)` extraction with `target_doc` always `None`. This is why
`generic.json`, `3gpp.json`, `rfc.json`, and `ieee.json`'s "Clause/subclause"
pattern needed **zero changes** — only `ieee.json`'s bare-`§` pattern was
extended (by replacement, to avoid duplicate matches) to
`"(?:(?P<doc>IEEE\\s+[\\w.-]+)\\s+)?§\\s*(?P<clause>\\d+(?:\\.\\d+)*)"`.

**Two-pass resolution.** Pass 1 (`parse_file()` → `find_cross_refs()`, per
file): same-file refs resolve exactly as before; a ref with a non-null
`target_doc` skips the local clause-id lookup entirely and is left as
`resolution_status: "unresolved-cross-file-pending"` (a transient state, never
present in a finished `index.json`). Pass 2 (`resolve_cross_file_refs()`,
called once from `build_index()` after every file is parsed, with full-corpus
visibility): for each pending ref, matches `target_doc` against every file's
`doc_id` by **exact string equality only** (never fuzzy) — zero matches gives
`"unresolved-doc-not-found"`, more than one gives `"unresolved-doc-ambiguous"`,
exactly one match proceeds to a `target_clause` lookup in that file (reusing
the existing `build_clause_index()`) with the same
`resolved` / `unresolved-not-found` / `unresolved-ambiguous` outcomes as
same-file resolution.

**Deliberate deviations from the original R9 spec text.** The original spec
said to defer implementation "until a real multi-spec corpus exists" and to
build the fixture suite from one, not an invented corpus, and to ship
unit-tests-only. Both were overridden by the project owner: a small synthetic
2-3 file corpus was used to drive `TestCrossFileResolution` in
`test_md_index.py` now, rather than waiting, and a runnable
`examples/cross-file-resolution-demo/` (with `WALKTHROUGH.md`, mirroring
`examples/how-l1-dogfood-demo/`) was built alongside the unit tests so the
mechanism can be seen end-to-end without a real multi-spec corpus on hand.

**Still not LLM-simulated parsing.** Per the original adversarial review (R9):
resolution is a deterministic lookup against `doc_id` values already present
in the index — never an LLM guessing which file a designator refers to.

---

## `content_hash.py` — context-package content-hash helper

A second small, **Python-3-stdlib-only** CLI, unrelated to markdown indexing:
computes the `content_hash` field for a `contexts/<package-id>.yaml` context
package, so a package's traceability tag can be checked for drift against its
current content without re-reading the whole file. A
`<package-id>@<hash8>` traceability tag embeds this value at tagging time;
`CONSUMING-CONTEXT-PACKAGE.md` item 0 compares a tag's `<hash8>` against the
package's *current* `content_hash` field (a plain field read) to detect drift
non-blockingly.

```
python content_hash.py <path-to-yaml>
```

Prints the 8-hex-char hash to stdout. Used on the **write path** only —
whenever `ult-context-generate` (Step 3 fold-addenda/regenerate, Step 10
initial save) or a consumer skill's domain-enrichment write-back rewrites
`contexts/<package-id>.yaml`, it re-runs this script and patches the resulting
`<hash8>` into the file's `content_hash` field (two-pass save).

The hash is computed over the file's content with all line endings normalized
to `\n` (so a Windows CRLF checkout doesn't produce false drift) and with the
file's own top-level `content_hash:` line excluded (so the field is a fixed
point — hashing a file that already carries its correct `content_hash` value
reproduces that same value). See `tests/test_content_hash.py`.

---

## `usage_report.py` — context-package usage aggregation report

A third small, **Python-3-stdlib-only** CLI (ROADMAP item 7): reads back the
citation data `CONSUMING-CONTEXT-PACKAGE.md` step 9 already writes on every
consuming run — each `kind: reference` addendum's `cites.ctx_ids` — and
aggregates it across every package under `contexts/`, so you can see which
`context_items` never get cited by any downstream artifact.

```
python usage_report.py [--dir contexts/]
```

Writes `<dir>/USAGE_REPORT.md` with: overall cited/never-cited totals, a
by-layer never-cited breakdown, a fallback-items-specifically breakdown
(`what_l1_fallback`/`how_l1_fallback` items — the lower-confidence,
human-reviewed ones where "generated but then ignored" is most actionable), a
per-package table, and a token-data section reporting count/min/max/avg of
any `tokens_used` values found on addenda — explicitly labeled as measured,
never estimated; it prints "no measured runs yet" if none exist. Handles zero
packages found gracefully (exit 0 — a repo that hasn't run
`ult-context-generate` yet is a normal state, not an error).

Like `content_hash.py`, this hand-parses the fixed, documented package/addenda
shapes (`references/context-package-schema.md`,
`CONSUMING-CONTEXT-PACKAGE.md` step 9) with a targeted line-scanner rather
than a general YAML parser — this repo has zero third-party Python
dependencies by design. See `tests/test_usage_report.py`.

---

## `mcp_mirror.py` — MCP-backed What-L1/How-L1 sourcing (ROADMAP items 9/11)

A fourth **Python-3-stdlib-only** CLI, called from `references/what-l1-fallback-query.md` and
`references/how-l1-fallback-query.md` Step 0, gated on `what_l1.mcp_source`/`how_l1.mcp_source`
being set and non-empty in `context-config.yaml` (see `context-config.yaml.template`). If
`mcp_source` is absent/empty (the default), Step 0 is a no-op and this script is never invoked —
What-L1/How-L1 behave exactly as they do with only hand-dropped `.md` files.

```
python mcp_mirror.py mirror --spec-file <fetch-specs.json> \
    --mirror-dir <dir> --manifest <manifest.json> [--content-dir <dir>]
```

The design: an MCP-fetched source has no file and no mtime, so it can't satisfy `md_index.py`'s
existing mtime-based `--stale-check` the way a local `.md` file does. Rather than teaching
`md_index.py` a second staleness model, `mcp_mirror.py` mirrors fetched content to local `.md`
files under `<layer>.mcp_mirror_path` (a subdirectory of `<layer>.path`, so `md_index.py`'s
existing recursive `index <layer.path>` call picks mirrored files up automatically — no
index-command change) and lets `md_index.py` index that directory completely unmodified. A mirror
file is only rewritten (and so only picks up a fresh mtime) when its `content_hash8` — reused
directly from `content_hash.py`, not reimplemented — differs from what the last run recorded for
that source; unchanged upstream content leaves the mirror file's mtime untouched, so
`--stale-check` correctly no-ops downstream with zero code changes.

This script never calls an MCP tool itself — that would need an MCP client dependency this repo
deliberately doesn't take on. Instead, the calling procedure (the agent, following Step 0) makes
the MCP tool call directly (it already has that capability in-session) and writes the result to a
scratchpad JSON file (`{"body": "<fetched text>"}`) per `mcp_source` entry; `mcp_mirror.py` only
reads those files (`read_content_file()`), hashes, mirrors, and manifests. See
`examples/mcp-what-l1-demo/WALKTHROUGH.md` for a validated, real-command round trip against
synthetic fixtures standing in for that fetched content, and `tests/test_mcp_mirror.py`.

---

## `content_safety_scan.py` — ingested-content injection guardrail (`PROTOCOL.md` §2.2)

A fifth **Python-3-stdlib-only** CLI. `PROTOCOL.md` §2.2 states that ingested What-L1/How-L1/MCP-
mirrored content MUST always be treated as data to cite, never as instructions to follow. This
script is `CONFORMANCE.md` §4's SHOULD-level (not MUST) heuristic aid to that rule: it flags `.md`
files containing imperative/instruction-like phrasing worth a second look before a package
assembler or human reviewer reads them.

```
python content_safety_scan.py <dir-or-file> [--exclude <subpath> ...]
```

Reuses `md_index.py`'s own `gather_md_files()` for directory walking and `--exclude` semantics —
same file-discovery behavior a `md_index.py index` run over the same target would use. Scans each
file's lines against a short, deliberately narrow list of literal injection-style patterns (e.g.
"ignore all previous instructions", "reveal your system prompt") and prints at most one flagged
line per hit, grouped by file. A clean corpus prints a single "no suspicious phrasing found." line;
nothing else changes and nothing is blocked either way — **this is informational only.** Exit code
is always `0` regardless of what's flagged, consistent with `PROTOCOL.md` §3.1's
no-automatic-resolution stance: a flag is a candidate for human review, not evidence of an actual
injection attempt, since ordinary process standards and specs legitimately use imperative language
("shall", "must") to describe their own subject matter — this script does not attempt to
distinguish that from an injection attempt. See `tests/test_content_safety_scan.py` for the clean
vs. planted-phrase cases, including the explicit non-flag case for ordinary "shall"/"must" wording.
