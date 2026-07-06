"""Regression suite for validate_path_conformance.py (D21 v3 §16.8, Phase 3e).

Stdlib unittest only -- no pytest dependency, so this stays vendorable along
with validate_path_conformance.py itself. Run with:

    python -m unittest discover -s scripts/tests -v
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import validate_path_conformance as vpc  # noqa: E402


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


REGISTRY_TEXT = (
    "schema_version: 1\n"
    "slots:\n"
    "  - id: security_report\n"
    "    project_layout_slot: true\n"
    "    kind: directory\n"
    "    pre_d21_default: output_docs/security_report/\n"
    "    workspace_root_leaf: outputs/security_report/\n"
    "config_keys:\n"
    "  - id: graphify_graph_path\n"
    "    project_layout_slot: false\n"
    "    kind: file\n"
    "    pre_d21_default: graphify-out/graph.json\n"
    "    workspace_root_leaf: cache/graphify-out/graph.json\n"
)


class TestWriteVerbRegex(unittest.TestCase):
    def test_matches_save_to(self):
        self.assertTrue(vpc.WRITE_VERB_RE.search("Save the report to `output_docs/foo/`."))

    def test_matches_write_to(self):
        self.assertTrue(vpc.WRITE_VERB_RE.search("Writes the index to `cache/specs-out/index.json`."))

    def test_matches_create_at(self):
        self.assertTrue(vpc.WRITE_VERB_RE.search("Create the marker at `.layout-slots.yaml`."))

    def test_matches_output_to(self):
        self.assertTrue(vpc.WRITE_VERB_RE.search("Output the summary to `output_docs/foo/summary.json`."))

    def test_no_match_for_plain_cross_reference(self):
        self.assertFalse(vpc.WRITE_VERB_RE.search("See `ult-context-generate/CONSUMING-CONTEXT-PACKAGE.md` for details."))


class TestIsPathShaped(unittest.TestCase):
    def test_plain_path_is_shaped(self):
        self.assertTrue(vpc._is_path_shaped("output_docs/foo/"))

    def test_no_slash_is_not_shaped(self):
        self.assertFalse(vpc._is_path_shaped("README.md"))

    def test_url_is_not_shaped(self):
        self.assertFalse(vpc._is_path_shaped("https://example.com/path"))

    def test_literal_with_whitespace_is_not_shaped(self):
        self.assertFalse(vpc._is_path_shaped("some text with spaces/here"))


class TestNormalize(unittest.TestCase):
    def test_strips_workspace_root_prefix_and_trailing_slash(self):
        self.assertEqual(vpc._normalize("{workspace_root}/outputs/security_docs/"), "outputs/security_docs")

    def test_bare_workspace_root_becomes_empty(self):
        self.assertEqual(vpc._normalize("{workspace_root}/"), "")

    def test_pre_d21_default_normalizes(self):
        self.assertEqual(vpc._normalize("output_docs/security_docs/"), "output_docs/security_docs")


class TestLoadRegistryEntries(unittest.TestCase):
    def test_absent_file_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(vpc.load_registry_entries(tmp), [])

    def test_flattens_all_three_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "layout-slots-registry.yaml", REGISTRY_TEXT)
            entries = vpc.load_registry_entries(root)
            ids = {e["id"] for e in entries}
            self.assertEqual(ids, {"security_report", "graphify_graph_path"})


class TestRegisteredMatch(unittest.TestCase):
    def setUp(self):
        self.entries = [
            {
                "id": "security_report",
                "project_layout_slot": True,
                "pre_d21_default": "output_docs/security_report/",
                "workspace_root_leaf": "outputs/security_report/",
            },
            {
                "id": "graphify_graph_path",
                "project_layout_slot": False,
                "pre_d21_default": "graphify-out/graph.json",
                "workspace_root_leaf": "cache/graphify-out/graph.json",
            },
        ]

    def test_matches_pre_d21_default(self):
        entry = vpc._registered_match("output_docs/security_report/", self.entries)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["id"], "security_report")

    def test_matches_workspace_root_leaf_with_placeholder_prefix(self):
        entry = vpc._registered_match("{workspace_root}/outputs/security_report/", self.entries)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["id"], "security_report")

    def test_unregistered_literal_returns_none(self):
        self.assertIsNone(vpc._registered_match("output_docs/my_new_thing/", self.entries))


class TestScanFile(unittest.TestCase):
    def test_registered_slot_hardcode_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root / "SKILL.md",
                "1. **Save the report** to `output_docs/security_report/` for review.\n",
            )
            write(root / "layout-slots-registry.yaml", REGISTRY_TEXT)
            entries = vpc.load_registry_entries(root)
            findings = vpc.scan_file(root / "SKILL.md", entries)
            self.assertEqual(len(findings), 1)
            line_no, message = findings[0]
            self.assertEqual(line_no, 1)
            self.assertIn("slot 'security_report' is registered", message)
            self.assertIn("§15.5", message)

    def test_unregistered_path_is_flagged_as_new_convention(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root / "SKILL.md",
                "2. Save the summary to `output_docs/my_new_thing/summary.json`.\n",
            )
            entries = vpc.load_registry_entries(root)  # no registry file -> []
            findings = vpc.scan_file(root / "SKILL.md", entries)
            self.assertEqual(len(findings), 1)
            line_no, message = findings[0]
            self.assertEqual(line_no, 1)
            self.assertIn("possible new path convention", message)
            self.assertIn("output_docs/my_new_thing/summary.json", message)

    def test_config_key_hardcode_is_flagged_with_resolution_algorithm_wording(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root / "SKILL.md",
                "Write the graph to `graphify-out/graph.json` once analysis completes.\n",
            )
            write(root / "layout-slots-registry.yaml", REGISTRY_TEXT)
            entries = vpc.load_registry_entries(root)
            findings = vpc.scan_file(root / "SKILL.md", entries)
            self.assertEqual(len(findings), 1)
            _, message = findings[0]
            self.assertIn("graphify_graph_path", message)
            self.assertIn("resolution algorithm", message)

    def test_prose_without_write_verb_is_not_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root / "SKILL.md",
                "See `output_docs/security_report/` for the existing report layout.\n",
            )
            entries = vpc.load_registry_entries(root)
            self.assertEqual(vpc.scan_file(root / "SKILL.md", entries), [])

    def test_write_verb_without_path_literal_is_not_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "SKILL.md", "Save your work before continuing to the next phase.\n")
            entries = vpc.load_registry_entries(root)
            self.assertEqual(vpc.scan_file(root / "SKILL.md", entries), [])

    def test_file_tree_block_is_not_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root / "SKILL.md",
                "## Output Structure\n\n"
                "output_docs/security_report/\n"
                "  summary.json   <- machine-readable summary\n",
            )
            entries = vpc.load_registry_entries(root)
            self.assertEqual(vpc.scan_file(root / "SKILL.md", entries), [])


class TestValidateAndMain(unittest.TestCase):
    def test_validate_scans_all_md_files_in_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "skill"
            write(
                skill_dir / "SKILL.md",
                "1. Save the report to `output_docs/security_report/`.\n",
            )
            write(
                skill_dir / "references" / "extra.md",
                "2. Output the index to `output_docs/my_new_thing/`.\n",
            )
            write(root / "layout-slots-registry.yaml", REGISTRY_TEXT)
            report = vpc.validate(skill_dir, root)
            self.assertEqual(len(report), 2)
            self.assertTrue(all(line.startswith("INFO: ") for line in report))

    def test_validate_with_no_findings_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "SKILL.md", "Nothing to see here.\n")
            self.assertEqual(vpc.validate(root / "SKILL.md", root), [])

    def test_main_always_exits_zero_even_with_findings(self):
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root / "SKILL.md",
                "1. Save the report to `output_docs/my_new_thing/`.\n",
            )
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = vpc.main(["--validate", str(root / "SKILL.md"), str(root)])
            self.assertEqual(rc, 0)
            self.assertIn("possible new path convention", buf.getvalue())

    def test_no_validate_flag_returns_usage_error(self):
        self.assertEqual(vpc.main([str(Path(tempfile.gettempdir()))]), 2)


class TestRealSkillFiles(unittest.TestCase):
    """Smoke test against real SKILL.md files (§16.10 Phase 3e validation
    gate: confirm the 7th dimension's backend runs cleanly, informational
    only, on existing skills - zero crashes, zero false-positive blocks
    (there's no blocking mode to begin with))."""

    def test_runs_cleanly_against_existing_skills(self):
        repo_root = Path(__file__).resolve().parents[5]
        for skill_dir in (
            "security-test-report",
            "pm-project-plan",
            "ult-repo-layout",
        ):
            target = repo_root / ".github" / "skills" / skill_dir / "SKILL.md"
            self.assertTrue(target.exists(), f"{target} is missing")
            report = vpc.validate(target, repo_root)
            self.assertIsInstance(report, list)
            for line in report:
                self.assertTrue(line.startswith("INFO: "))


if __name__ == "__main__":
    unittest.main()
