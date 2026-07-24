"""Regression suite for discover_layers.py (CONTEXT-ENGINEERING-DESIGN.md
§17.2-17.4, CEP-DP-001H Stage 3 PR 1).

Stdlib unittest only, same posture as test_validate_layout.py. Run with:

    python -m unittest discover -s scripts/tests -v

Test classes are grouped by §17.9 stress-scenario intent rather than by
function, since discovery's externally-observable unit is "what shows up in
the artifact for this repo layout" - matching how the design doc itself
frames the stress scenarios (S23-S27, S29-S40; S28 stays CEP-DP-001G's,
untouched).
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import discover_layers as dl  # noqa: E402
import validate_layout as vl  # noqa: E402


def write(path, content=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TempRepoTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo_root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def config(self, text=""):
        if text:
            write(self.repo_root / "context-config.yaml", text)
            return vl.load_yaml_file(self.repo_root / "context-config.yaml") or {}
        return {}


# ---------------------------------------------------------------------------
# S23-ish: step 1 precedence - hand-configured, non-default, populated path
# always wins, no scoring, no decision field (shape 2b NOTICE).
# ---------------------------------------------------------------------------

class TestPrecedenceCheck(TempRepoTestCase):
    def test_what_l2_hand_configured_path_wins_no_decision(self):
        write(self.repo_root / "my-specs" / "a.md", "# spec")
        config = self.config("layers:\n  what_l2:\n    path: my-specs/\n")
        section, path, roots = dl.discover_what_l2(self.repo_root, config)
        self.assertEqual(path, "my-specs/")
        self.assertIn("hand-configured", section.render())
        self.assertFalse(section.decision_lines)

    def test_how_l2_hand_configured_path_wins_no_decision(self):
        write(self.repo_root / "team-conventions" / "style.md", "# style")
        config = self.config("how_dimension:\n  how_l2:\n    path: team-conventions/\n")
        section, path = dl.discover_how_l2(self.repo_root, config)
        self.assertEqual(path, "team-conventions/")
        self.assertFalse(section.decision_lines)
        self.assertIn("hand-configured", section.render())

    def test_what_l1_hand_configured_path_wins_regardless_of_enabled(self):
        write(self.repo_root / "specs" / "external" / "rfc.md", "# rfc")
        config = self.config(
            "layers:\n  what_l1:\n    enabled: false\n    path: specs/external/\n"
        )
        section, path = dl.discover_what_l1(self.repo_root, config)
        self.assertEqual(path, "specs/external/")
        self.assertFalse(section.decision_lines)


# ---------------------------------------------------------------------------
# Step 2: CEP default path check (What-L2/How-L2 only).
# ---------------------------------------------------------------------------

class TestDefaultPathCheck(TempRepoTestCase):
    def test_what_l2_pre_d21_default_populated_is_notice_only(self):
        write(self.repo_root / "docs" / "requirements" / "a.md", "# reqs")
        config = self.config()
        section, path, roots = dl.discover_what_l2(self.repo_root, config)
        self.assertFalse(section.decision_lines)
        self.assertIn("NOTICE", section.render())

    def test_how_l2_default_org_populated_is_notice_only(self):
        write(self.repo_root / "org" / "a.md", "# org conventions")
        config = self.config()
        section, path = dl.discover_how_l2(self.repo_root, config)
        self.assertEqual(path, "org/")
        self.assertFalse(section.decision_lines)


# ---------------------------------------------------------------------------
# Step 3: scan-and-score, Requirements category found -> CONFIRM/CUSTOM/SKIP.
# ---------------------------------------------------------------------------

class TestWhatL2ScanAndScore(TempRepoTestCase):
    def test_requirements_named_dir_with_many_docs_is_high_confidence(self):
        for i in range(12):
            write(self.repo_root / "specification" / f"{i}.md", "# x")
        config = self.config()
        section, path, roots = dl.discover_what_l2(self.repo_root, config)
        rendered = section.render()
        self.assertIn("decision: PENDING", rendered)
        self.assertIn("CONFIRM: specification/", rendered)
        self.assertIn("High", rendered)

    def test_unnamed_dir_with_few_docs_is_low_confidence_but_still_a_candidate(self):
        # At MIN_DOC_COUNT_FOR_UNNAMED_MATCH (2) but below
        # MEDIUM_CONFIDENCE_FILE_FLOOR (3), no name match -> still a
        # candidate, just Low confidence.
        write(self.repo_root / "misc" / "0.md", "# x")
        write(self.repo_root / "misc" / "1.md", "# y")
        config = self.config()
        section, path, roots = dl.discover_what_l2(self.repo_root, config)
        rendered = section.render()
        self.assertIn("misc/", rendered)
        self.assertIn("Low", rendered)

    def test_single_stray_file_unnamed_dir_is_not_a_candidate(self):
        # Below MIN_DOC_COUNT_FOR_UNNAMED_MATCH (2) and no name match ->
        # not evidence of an authored corpus, excluded entirely.
        write(self.repo_root / "misc" / "0.md", "# x")
        config = self.config()
        section, path, roots = dl.discover_what_l2(self.repo_root, config)
        rendered = section.render()
        self.assertNotIn("misc/", rendered)

    def test_dot_prefixed_directory_excluded_from_candidates(self):
        # Simulates .pytest_cache/README.md - a tool-generated stray file
        # inside a hidden cache directory must never surface as a candidate,
        # regardless of file count or name match.
        write(self.repo_root / ".pytest_cache" / "README.md", "# pytest cache")
        write(self.repo_root / ".pytest_cache" / "v" / "cache" / "requirements.md", "# x")
        config = self.config()
        section, path, roots = dl.discover_what_l2(self.repo_root, config)
        rendered = section.render()
        self.assertNotIn("pytest_cache", rendered)
        self.assertIsNone(path)

    def test_no_requirements_match_never_auto_assigns_path_to_other_category(self):
        # H-2: a Design-only match (diagram file, no .md/.rst/.adoc so it
        # never also trips the Requirements doc-count signal) must not
        # silently become what_l2.path.
        write(self.repo_root / "architecture" / "0001-decision.drawio", "<diagram/>")
        config = self.config()
        section, path, roots = dl.discover_what_l2(self.repo_root, config)
        self.assertIsNone(path)
        rendered = section.render()
        self.assertIn("H-2", rendered)
        self.assertIn("architecture/", rendered)

    def test_design_and_api_matches_become_include_roots_when_requirements_found(self):
        for i in range(12):
            write(self.repo_root / "requirements" / f"{i}.md", "# req")
        write(self.repo_root / "architecture" / "0001-decision.md", "# adr")
        write(self.repo_root / "api-spec" / "openapi.yaml", "openapi: 3.0.0")
        config = self.config()
        section, path, roots = dl.discover_what_l2(self.repo_root, config)
        rendered = section.render()
        self.assertIn("include_roots_decision: PENDING   # ADD: architecture/", rendered)
        self.assertIn("include_roots_decision: PENDING   # ADD: api-spec/", rendered)

    def test_multi_category_dir_gets_exactly_one_include_roots_line(self):
        # M-2 dedup: a single directory matching Design AND API/spec must not
        # produce two competing include_roots_decision lines for one path.
        for i in range(12):
            write(self.repo_root / "requirements" / f"{i}.md", "# req")
        write(self.repo_root / "api-schema" / "0001-decision.md", "# adr-named, also api-named dir")
        write(self.repo_root / "api-schema" / "openapi.yaml", "openapi: 3.0.0")
        config = self.config()
        section, path, roots = dl.discover_what_l2(self.repo_root, config)
        rendered = section.render()
        self.assertEqual(rendered.count("include_roots_decision: PENDING   # ADD: api-schema/"), 1)

    def test_nothing_found_anywhere_escalates_to_custom_or_acknowledge(self):
        config = self.config()
        section, path, roots = dl.discover_what_l2(self.repo_root, config)
        rendered = section.render()
        self.assertIn("decision: PENDING   # CUSTOM: <path> | ACKNOWLEDGE", rendered)
        self.assertIsNone(path)

    def test_cep_bucket_dirs_excluded_from_scan(self):
        for i in range(12):
            write(self.repo_root / "contexts" / f"{i}.md", "# should never count")
        config = self.config()
        section, path, roots = dl.discover_what_l2(self.repo_root, config)
        rendered = section.render()
        self.assertNotIn("contexts/", rendered)


class TestWhatL2WorkspaceRootSet(TempRepoTestCase):
    def test_populated_workspace_root_after_exclude_is_notice_only(self):
        write(self.repo_root / "docs" / "a.md", "# doc")
        config = self.config(
            "layout:\n  workspace_root: docs/\n"
            "layers:\n  what_l2:\n    exclude:\n      - contexts/\n      - inputs/\n      - cache/\n"
        )
        section, path, roots = dl.discover_what_l2(self.repo_root, config)
        self.assertEqual(path, "docs/")
        self.assertFalse(any(d.startswith("decision:") for d in section.decision_lines))

    def test_sibling_composite_scan_runs_outside_workspace_root(self):
        write(self.repo_root / "docs" / "a.md", "# doc")
        write(self.repo_root / "openapi" / "openapi.yaml", "openapi: 3.0.0")
        config = self.config(
            "layout:\n  workspace_root: docs/\n"
            "layers:\n  what_l2:\n    exclude:\n      - contexts/\n      - inputs/\n      - cache/\n"
        )
        section, path, roots = dl.discover_what_l2(self.repo_root, config)
        self.assertIn("openapi/", roots)
        self.assertIn("include_roots_decision: PENDING   # ADD: openapi/", section.render())

    def test_vendor_looking_subdir_inside_workspace_root_proposed_for_exclude(self):
        write(self.repo_root / "docs" / "a.md", "# doc")
        for i in range(6):
            write(self.repo_root / "docs" / "vendor-snapshots" / f"file{i}.bin", "binary-ish, not a doc")
        config = self.config(
            "layout:\n  workspace_root: docs/\n"
            "layers:\n  what_l2:\n    exclude:\n      - contexts/\n      - inputs/\n      - cache/\n"
        )
        section, path, roots = dl.discover_what_l2(self.repo_root, config)
        rendered = section.render()
        self.assertIn("exclude_decision: PENDING   # ADD: docs/vendor-snapshots/", rendered)

    def test_m3_caution_note_when_excluded_candidate_equals_another_layers_path(self):
        write(self.repo_root / "docs" / "a.md", "# doc")
        for i in range(6):
            write(self.repo_root / "docs" / "legacy-conventions" / f"file{i}.bin", "not a doc")
        config = self.config(
            "layout:\n  workspace_root: docs/\n"
            "layers:\n  what_l2:\n    exclude:\n      - contexts/\n      - inputs/\n      - cache/\n"
            "how_dimension:\n  how_l2:\n    path: docs/legacy-conventions/\n"
        )
        section, path, roots = dl.discover_what_l2(self.repo_root, config)
        rendered = section.render()
        self.assertIn("CAUTION", rendered)
        self.assertIn("how_dimension.how_l2.path", rendered)


# ---------------------------------------------------------------------------
# How-L2: fixed candidate list, then root-signal fallback (H-3).
# ---------------------------------------------------------------------------

class TestHowL2CandidateScan(TempRepoTestCase):
    def test_docs_style_guide_candidate_found(self):
        write(self.repo_root / "docs" / "style-guide" / "a.md", "# style")
        config = self.config()
        section, path = dl.discover_how_l2(self.repo_root, config)
        self.assertIn("decision: PENDING   # CONFIRM: docs/style-guide/", section.render())

    def test_github_dir_is_a_candidate(self):
        write(self.repo_root / ".github" / "CODEOWNERS", "* @team")
        config = self.config()
        section, path = dl.discover_how_l2(self.repo_root, config)
        self.assertIn("CONFIRM: .github/", section.render())

    def test_root_signals_only_is_not_silent_default_to_dot(self):
        write(self.repo_root / "CONTRIBUTING.md", "# contributing")
        write(self.repo_root / ".editorconfig", "root = true")
        config = self.config()
        section, path = dl.discover_how_l2(self.repo_root, config)
        rendered = section.render()
        self.assertIn("CUSTOM: <path> | ACKNOWLEDGE", rendered)
        self.assertIn("CONTRIBUTING.md", rendered)
        self.assertIsNone(path)

    def test_nothing_at_all_escalates(self):
        config = self.config()
        section, path = dl.discover_how_l2(self.repo_root, config)
        self.assertIn("CUSTOM: <path> | ACKNOWLEDGE", section.render())


# ---------------------------------------------------------------------------
# What-L1 / How-L1: opt-in 4-case enabled/found matrix.
# ---------------------------------------------------------------------------

class TestOptInLayerMatrix(TempRepoTestCase):
    def test_disabled_and_found_gets_decision_and_enable_fields(self):
        write(self.repo_root / "standards" / "a.md", "# standard")
        config = self.config("layers:\n  what_l1:\n    enabled: false\n")
        section, path = dl.discover_what_l1(self.repo_root, config)
        rendered = section.render()
        self.assertIn("decision: PENDING   # CONFIRM: standards/", rendered)
        self.assertIn("enable: PENDING", rendered)

    def test_disabled_and_not_found_proposes_nothing(self):
        config = self.config("layers:\n  what_l1:\n    enabled: false\n")
        section, path = dl.discover_what_l1(self.repo_root, config)
        self.assertFalse(section.decision_lines)
        self.assertIn("Nothing proposed", section.render())

    def test_enabled_and_found_gets_decision_only_no_enable_field(self):
        write(self.repo_root / "vendor" / "docs" / "a.md", "# vendor doc")
        config = self.config("layers:\n  what_l1:\n    enabled: true\n")
        section, path = dl.discover_what_l1(self.repo_root, config)
        rendered = section.render()
        self.assertIn("CONFIRM: vendor/docs/", rendered)
        self.assertNotIn("enable: PENDING", rendered)

    def test_enabled_and_not_found_escalates_never_shape_3(self):
        config = self.config("layers:\n  what_l1:\n    enabled: true\n")
        section, path = dl.discover_what_l1(self.repo_root, config)
        rendered = section.render()
        self.assertIn("CUSTOM: <path> | DISABLE", rendered)

    def test_how_l1_uses_its_own_candidate_list(self):
        write(self.repo_root / "process" / "a.md", "# process doc")
        config = self.config("how_dimension:\n  how_l1:\n    enabled: false\n")
        section, path = dl.discover_how_l1(self.repo_root, config)
        self.assertIn("CONFIRM: process/", section.render())


# ---------------------------------------------------------------------------
# Cross-layer collision/nesting check (S30, D-017/D-018) - new to this
# package, algorithm not specified verbatim in the design doc.
# ---------------------------------------------------------------------------

class TestCrossLayerCollisionCheck(TempRepoTestCase):
    def test_equal_paths_collide(self):
        collisions = dl.check_cross_layer_collisions(
            {}, what_l2_path="docs/", how_l2_path="docs/",
        )
        self.assertEqual(len(collisions), 1)
        self.assertEqual({collisions[0][0], collisions[0][1]}, {"layers.what_l2.path", "how_dimension.how_l2.path"})

    def test_nested_paths_collide(self):
        collisions = dl.check_cross_layer_collisions(
            {}, what_l2_path="docs/", how_l1_path="docs/standards/",
        )
        self.assertEqual(len(collisions), 1)

    def test_sibling_paths_do_not_collide(self):
        collisions = dl.check_cross_layer_collisions(
            {}, what_l2_path="docs/requirements/", how_l2_path="docs/conventions/",
        )
        self.assertEqual(collisions, [])

    def test_include_root_candidate_participates_in_collision_check(self):
        collisions = dl.check_cross_layer_collisions(
            {}, what_l2_path="docs/", what_l2_roots=["standards/"], how_l1_path="standards/policy/",
        )
        self.assertEqual(len(collisions), 1)
        labels = {collisions[0][0], collisions[0][1]}
        self.assertIn("how_dimension.how_l1.path", labels)

    def test_render_collision_section_uses_pending_decision_field(self):
        collisions = [("layers.what_l2.path", "how_dimension.how_l2.path", "docs", "docs")]
        section = dl.render_collision_section(collisions)
        rendered = section.render()
        self.assertIn("collision_decision: PENDING", rendered)
        self.assertIn("ACKNOWLEDGE", rendered)
        self.assertIn("CUSTOM", rendered)

    def test_no_collisions_renders_no_section(self):
        self.assertIsNone(dl.render_collision_section([]))

    def test_end_to_end_discover_layers_surfaces_collision_section(self):
        write(self.repo_root / "org" / "a.md", "# org")  # resolves how_l2 to org/ by default
        config = self.config(
            "layers:\n  what_l1:\n    enabled: true\n    path: org/\n"
        )
        sections, cfg = dl.discover_layers(self.repo_root)
        titles = [s.title for s in sections]
        self.assertIn("Cross-layer path collisions (S30, D-017/D-018)", titles)


# ---------------------------------------------------------------------------
# Regression: dogfood-style already-correctly-configured project sees zero
# new decision fields anywhere (Success Criteria's true-negative case).
# ---------------------------------------------------------------------------

class TestAllFourLayersAlreadyCorrect(TempRepoTestCase):
    def test_zero_decisions_when_everything_hand_set_and_populated(self):
        write(self.repo_root / "reqs" / "a.md", "# req")
        write(self.repo_root / "conv" / "a.md", "# conv")
        write(self.repo_root / "ext" / "a.md", "# ext")
        write(self.repo_root / "proc" / "a.md", "# proc")
        config = self.config(
            "layers:\n"
            "  what_l2:\n    path: reqs/\n"
            "  what_l1:\n    enabled: true\n    path: ext/\n"
            "how_dimension:\n"
            "  how_l2:\n    path: conv/\n"
            "  how_l1:\n    enabled: true\n    path: proc/\n"
        )
        sections, cfg = dl.discover_layers(self.repo_root)
        for section in sections:
            self.assertFalse(section.decision_lines, msg=f"{section.title} had unexpected decisions:\n{section.render()}")


# ---------------------------------------------------------------------------
# Artifact rendering smoke test (§17.3's "how to confirm" tail).
# ---------------------------------------------------------------------------

class TestArtifactRendering(TempRepoTestCase):
    def test_render_discovery_artifact_includes_how_to_confirm(self):
        sections, cfg = dl.discover_layers(self.repo_root)
        artifact = dl.render_discovery_artifact("my-repo", sections)
        self.assertIn("How to confirm", artifact)
        self.assertIn("confirm-layers", artifact)

    def test_run_discovery_writes_file_at_repo_root_when_no_workspace_root(self):
        out_path, artifact = dl.run_discovery(self.repo_root)
        self.assertEqual(out_path, self.repo_root / "context-layout-discovery.md")
        self.assertTrue(out_path.is_file())

    def test_run_discovery_writes_file_under_workspace_root_when_set(self):
        write(self.repo_root / "docs" / "a.md", "# doc")
        write(
            self.repo_root / "context-config.yaml",
            "layout:\n  workspace_root: docs/\n"
            "layers:\n  what_l2:\n    exclude:\n      - contexts/\n      - inputs/\n      - cache/\n",
        )
        out_path, artifact = dl.run_discovery(self.repo_root)
        self.assertEqual(out_path, self.repo_root / "docs" / "context-layout-discovery.md")
        self.assertTrue(out_path.is_file())


if __name__ == "__main__":
    unittest.main()
