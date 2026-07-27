# `layout-slots-registry.yaml` and path-conformance checking (D21 §16.8)

## `layout-slots-registry.yaml` — library-level superset registry

A library-level file at the skills library's repo root — **not** generated
by `init`/`reconcile`, **not** copied into consuming projects, and not itself
a `project_layout` path-slot. A superset registry, one row per path any skill
reads or writes outside its own code tree, mirroring §16.4's table in
structured YAML. Three top-level sections under `schema_version: 1`:

- **`slots:`** — the eight `project_layout` slots from the "Slot registry"
  table in `SKILL.md`, each with `id`, `project_layout_slot: true`, `kind`,
  `default_bucket`, `pre_d21_default`, `workspace_root_leaf`, `config_key`
  (only `context_packages` has one — `cache.product_context_path`; `~` for
  the rest), `producer`, and `consumers`.
- **`config_keys:`** — the six existing `layers.*`/`how_dimension.*`/
  `graphify.*`/`cache.*` config keys (`what_l2_path`, `what_l1_path`,
  `how_dimension_path`, `how_l2_cache_path`, `graphify_graph_path`,
  `index_paths`), each `project_layout_slot: false`, with `config_key`,
  `kind`, `pre_d21_default`, and `workspace_root_leaf`/`workspace_root_default`.
- **`starter_kit_dropzones:`** — the five drop-zones from
  `references/starter-kit-dropzones.md` (`threat_modeling`,
  `secure_coding_guidelines`, `security_test_data`, `project_plan`,
  `project_guidelines`), each `project_layout_slot: false`,
  `default_bucket: inputs`, with `consumers` where applicable.

Consumed by:

1. `validate_layout.py`'s registry-consistency check (#10, `SKILL.md`) — keeps
   `SLOT_REGISTRY` (code) and `layout-slots-registry.yaml` (registry) in sync;
   `FAIL` on drift.
2. `validate_path_conformance.py` (below) — the 7th path-dependency-review
   dimension's backend, which looks up a contributed skill's hardcoded path
   literals against this registry's `pre_d21_default`/`workspace_root_leaf`/
   `workspace_root_default` columns.

Since this file is library-level-only, both consumers treat its absence as a
no-op — every consuming project and every test fixture in this repo's own
suite simply skips the corresponding check/finding.

## `scripts/validate_path_conformance.py` — path-dependency conformance check

Deterministic, stdlib-only, sibling to `validate_layout.py` (whose
`load_yaml_file()` it reuses to read `layout-slots-registry.yaml`). Backs a
skill-contribution review's 7th dimension, "Path-dependency conformance" —
**entirely non-blocking/informational** (resolves H3), never exits non-zero
on findings:

```
python .github/skills/ult-repo-layout/scripts/validate_path_conformance.py --validate <skill-md-or-dir> [<repo-root>]
```

Scans every `.md` file under `<skill-md-or-dir>` for lines matching a
write-verb-object pattern (`sav(e|es|ed|ing) ... to`, `writ(e|es|ten|ing) ...
to`, `creat(e|es|ed|ing) ... at`, `output(s|ted|ting)? ... to`, verb and
preposition within 40 characters of each other) with a backtick-quoted,
path-shaped literal (contains `/`, no whitespace, not a URL) on the same line.
For each match:

- **Not in `layout-slots-registry.yaml`** — `"possible new path convention
  ('<literal>') - consider registering it in layout-slots-registry.yaml
  (§16.4)."`
- **Matches a registered slot's default** — `"slot '<id>' is registered
  (§16.4) - resolve its path via §15.5 instead of hardcoding '<literal>', so
  projects that relocate '<id>' aren't broken by this skill."`
- **Matches a registered config-key/dropzone default** — `"'<literal>'
  matches the registered default for '<id>' (§16.4) - resolve it via
  context-config.yaml's resolution algorithm for that key instead of
  hardcoding, ..."`

A skill-contribution review runs this against the contributed file(s) and
pastes findings verbatim into its review comment's "Path-dependency
conformance" section — `Clear` if the report is empty. Unit tests in
`scripts/tests/test_validate_path_conformance.py`.
