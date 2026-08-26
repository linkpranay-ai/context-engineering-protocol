#!/usr/bin/env python3
"""Tests for cep_retrofit.py.

Every fixture built here is synthetic and generic on purpose (see the design
draft's binding constraint, 3): no real library's name or shape, private or
public, appears anywhere below -- only fabricated placeholders like
example-skill/, widget-reviewer/, second-widget/.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import cep_retrofit  # noqa: E402


def _write(path, content=""):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class InventoryHeuristicAUnionTest(unittest.TestCase):
    """Heuristic (a): SKILL.md-style subdirectories."""

    def test_single_skill_dir_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp) / "widget-reviewer" / "SKILL.md", "---\nname: widget-reviewer\n---\n# Widget Reviewer\n")
            result = cep_retrofit.inventory(tmp)
            self.assertEqual(len(result["units"]), 1)
            unit = result["units"][0]
            self.assertEqual(unit["type"], "skill-dir")
            self.assertEqual(unit["unit_id"], "widget-reviewer")
            self.assertEqual(unit["primary_file"], "widget-reviewer/SKILL.md")

    def test_skill_dir_children_not_separate_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp) / "widget-reviewer" / "SKILL.md", "# Widget Reviewer\n")
            _write(Path(tmp) / "widget-reviewer" / "references" / "NOTES.md", "notes")
            _write(Path(tmp) / "widget-reviewer" / "scripts" / "helper.py", "pass")
            result = cep_retrofit.inventory(tmp)
            self.assertEqual(len(result["units"]), 1)
            self.assertEqual(result["units"][0]["type"], "skill-dir")

    def test_lowercase_skill_md_also_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp) / "example-skill" / "skill.md", "# Example\n")
            result = cep_retrofit.inventory(tmp)
            self.assertEqual(result["units"][0]["type"], "skill-dir")


class InventoryHeuristicBTest(unittest.TestCase):
    """Heuristic (b): single recognizable manifest file."""

    def test_manifest_yaml_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp) / "example-skill" / "skill.yaml", "name: example-skill\n")
            result = cep_retrofit.inventory(tmp)
            self.assertEqual(len(result["units"]), 1)
            self.assertEqual(result["units"][0]["type"], "manifest-dir")

    def test_ambiguous_multiple_manifests_falls_to_unclaimed(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp) / "example-skill" / "skill.yaml", "name: a\n")
            _write(Path(tmp) / "example-skill" / "skill.json", "{}")
            result = cep_retrofit.inventory(tmp)
            self.assertEqual(result["units"], [])
            self.assertIn("example-skill", result["unclaimed_dirs"])


class InventoryHeuristicCTest(unittest.TestCase):
    """Heuristic (c): flat *.md/*.mdc/*.prompt.md files."""

    def test_flat_prompt_file_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp) / "review.prompt.md", "# Review\n")
            result = cep_retrofit.inventory(tmp)
            self.assertEqual(len(result["units"]), 1)
            self.assertEqual(result["units"][0]["type"], "flat-file")
            self.assertEqual(result["units"][0]["unit_id"], "review.prompt.md")

    def test_flat_mdc_file_nested_under_subdir_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp) / "rules" / "widget.mdc", "widget rule")
            result = cep_retrofit.inventory(tmp)
            self.assertEqual(len(result["units"]), 1)
            self.assertEqual(result["units"][0]["unit_id"], "rules/widget.mdc")

    def test_readme_license_excluded_from_flat_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp) / "README.md", "readme")
            _write(Path(tmp) / "LICENSE.md", "license")
            result = cep_retrofit.inventory(tmp)
            self.assertEqual(result["units"], [])

    def test_root_control_files_excluded_from_flat_units(self):
        # AGENTS.md/CLAUDE.md/CONTEXT.md describe how to work in a repo as a
        # whole - not retrofittable skill units, same class as README/LICENSE.
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp) / "AGENTS.md", "agents")
            _write(Path(tmp) / "CLAUDE.md", "claude")
            _write(Path(tmp) / "CONTEXT.md", "context")
            result = cep_retrofit.inventory(tmp)
            self.assertEqual(result["units"], [])


class InventoryUnionNotWinnerTakeAllTest(unittest.TestCase):
    """The blocking review finding: mixed conventions must not swallow each other."""

    def test_skill_dirs_and_flat_files_coexist(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp) / "example-skill" / "SKILL.md", "# Example\n")
            _write(Path(tmp) / "widget.prompt.md", "widget prompt")
            result = cep_retrofit.inventory(tmp)
            types = sorted(u["type"] for u in result["units"])
            self.assertEqual(types, ["flat-file", "skill-dir"])

    def test_all_three_heuristics_coexist(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp) / "example-skill" / "SKILL.md", "# Example\n")
            _write(Path(tmp) / "second-widget" / "skill.yaml", "name: second-widget\n")
            _write(Path(tmp) / "flat-rule.prompt.md", "flat rule")
            result = cep_retrofit.inventory(tmp)
            ids = sorted(u["unit_id"] for u in result["units"])
            self.assertEqual(ids, ["example-skill", "flat-rule.prompt.md", "second-widget"])


class InventoryExclusionsTest(unittest.TestCase):
    def test_generated_dirs_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp) / "node_modules" / "some-pkg" / "SKILL.md", "# Not real\n")
            _write(Path(tmp) / ".git" / "hooks" / "SKILL.md", "# Not real\n")
            result = cep_retrofit.inventory(tmp)
            self.assertEqual(result["units"], [])

    def test_governance_directories_excluded(self):
        # ADRs, changesets, and content a repo has already marked
        # out-of-scope are repository-governance shapes, not skill units -
        # even when they hold *.md files that would otherwise match
        # heuristic (c), and even nested under another directory (e.g. an
        # "adr" folder under some other parent), same as node_modules/.git
        # above.
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp) / "adr" / "0001-decision.md", "# ADR 1\n")
            _write(Path(tmp) / "nested" / "adr" / "0002-decision.md", "# ADR 2\n")
            _write(Path(tmp) / ".changeset" / "some-change.md", "# Change\n")
            _write(Path(tmp) / ".out-of-scope" / "draft.md", "# Draft\n")
            result = cep_retrofit.inventory(tmp)
            self.assertEqual(result["units"], [])

    def test_missing_root_raises(self):
        with self.assertRaises(NotADirectoryError):
            cep_retrofit.inventory("/definitely/does/not/exist/anywhere")

    def test_governance_shaped_name_holding_a_real_skill_is_still_inventoried(self):
        # Negative control for test_governance_directories_excluded above:
        # name-based exclusion must be strictly weaker than the shape
        # check. A directory that happens to be named "adr" (or any other
        # DEFAULT_EXCLUDES entry) but actually holds a SKILL.md is a real,
        # legitimate skill-dir -- it must never be silently dropped just
        # because its name matches a governance-directory convention.
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp) / "adr" / "SKILL.md", "# ADR skill\n")
            _write(Path(tmp) / "review" / "SKILL.md", "# Review skill\n")
            result = cep_retrofit.inventory(tmp)
            unit_ids = {u["unit_id"] for u in result["units"]}
            self.assertEqual(unit_ids, {"adr", "review"})


class InventoryManifestExclusionTest(unittest.TestCase):
    def _write_manifest(self, tmp, owned_paths, mode="full", only_skills=None):
        _write(
            Path(tmp) / ".cep-install.json",
            json.dumps({
                "schema_version": 1,
                "runtime": ["claude", "copilot"],
                "mode": mode,
                "only_skills": only_skills,
                "owned_paths": owned_paths,
                "installed_at": "2026-01-01T00:00:00Z",
            }),
        )

    def test_manifest_owned_container_excluded_from_units_and_unclaimed(self):
        # Common full-install shape: manifest owns ".github/skills" itself
        # (a container), which holds a real SKILL.md-bearing subdirectory.
        # The whole subtree is CEP's own installed content and must not be
        # surfaced as a retrofit candidate, or leak into unclaimed_dirs.
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp) / ".github" / "skills" / "installed-skill" / "SKILL.md", "# Installed\n")
            _write(Path(tmp) / "widget-reviewer" / "SKILL.md", "# Widget Reviewer\n")
            self._write_manifest(tmp, [".github/skills", ".github/prompts"])
            result = cep_retrofit.inventory(tmp)
            unit_ids = {u["unit_id"] for u in result["units"]}
            self.assertEqual(unit_ids, {"widget-reviewer"})
            self.assertNotIn(".github/skills/installed-skill", result.get("unclaimed_dirs", []))

    def test_manifest_absent_leaves_behavior_unchanged(self):
        # No .cep-install.json in this fixture -- _read_cep_manifest must
        # return None (not raise), and inventory() must fall back to
        # today's DEFAULT_EXCLUDES-only behavior: an un-manifested ".github/
        # skills" subtree is a real candidate like any other directory.
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(cep_retrofit._read_cep_manifest(tmp))
            _write(Path(tmp) / ".github" / "skills" / "installed-skill" / "SKILL.md", "# Installed\n")
            result = cep_retrofit.inventory(tmp)
            unit_ids = {u["unit_id"] for u in result["units"]}
            self.assertIn(".github/skills/installed-skill", unit_ids)

    def test_only_mode_manifest_naming_a_skill_dir_directly_is_still_inventoried(self):
        # Shape-aware precedence: an -Only install's manifest can name a
        # skill-dir *directly* as owned_paths (rather than a container). The
        # shape check (heuristic a) must still win -- this is a legitimate,
        # CEP-installed unit, correctly inventoried, never silently dropped
        # just because it matches owned_paths.
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp) / ".github" / "skills" / "example-skill" / "SKILL.md", "# Example\n")
            self._write_manifest(
                tmp,
                [".github/skills/example-skill"],
                mode="only",
                only_skills=["example-skill"],
            )
            result = cep_retrofit.inventory(tmp)
            unit_ids = {u["unit_id"] for u in result["units"]}
            self.assertIn(".github/skills/example-skill", unit_ids)

    def test_manifest_owned_param_overrides_autodetection(self):
        # Passing manifest_owned explicitly (e.g. manifest_owned=set())
        # disables manifest-based exclusion entirely, even when a real
        # .cep-install.json is present on disk -- documented override,
        # mainly for tests.
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp) / ".github" / "skills" / "installed-skill" / "SKILL.md", "# Installed\n")
            self._write_manifest(tmp, [".github/skills"])
            result = cep_retrofit.inventory(tmp, manifest_owned=set())
            unit_ids = {u["unit_id"] for u in result["units"]}
            self.assertIn(".github/skills/installed-skill", unit_ids)


@unittest.skipUnless(hasattr(os, "symlink"), "symlinks not supported on this platform/permission level")
class InventorySymlinkTest(unittest.TestCase):
    def test_symlinked_skill_dir_is_inventoried_with_real_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            real_dir = Path(tmp) / "_real" / "example-skill"
            _write(real_dir / "SKILL.md", "# Example\n")
            link_root = Path(tmp) / "workspace"
            link_root.mkdir()
            link_path = link_root / "example-skill"
            try:
                os.symlink(str(real_dir), str(link_path), target_is_directory=True)
            except OSError:
                self.skipTest("insufficient privilege to create symlinks in this environment")
            result = cep_retrofit.inventory(link_root)
            self.assertEqual(len(result["units"]), 1)
            unit = result["units"][0]
            self.assertTrue(unit["via_symlink"])
            self.assertEqual(os.path.realpath(unit["real_path"]), os.path.realpath(str(real_dir)))

    def test_symlink_does_not_recurse_further(self):
        with tempfile.TemporaryDirectory() as tmp:
            real_dir = Path(tmp) / "_real"
            _write(real_dir / "nested" / "example-skill" / "SKILL.md", "# Example\n")
            link_root = Path(tmp) / "workspace"
            link_root.mkdir()
            link_path = link_root / "linked"
            try:
                os.symlink(str(real_dir), str(link_path), target_is_directory=True)
            except OSError:
                self.skipTest("insufficient privilege to create symlinks in this environment")
            result = cep_retrofit.inventory(link_root)
            # The nested skill-dir one level beneath the symlink is never reached --
            # bounded traversal, not a cycle-prone deep follow.
            self.assertEqual(result["units"], [])


class DescribeTest(unittest.TestCase):
    def test_frontmatter_name_and_description(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "SKILL.md"
            _write(path, "---\nname: widget-reviewer\ndescription: Reviews widgets for defects.\n---\n# Body\n")
            result = cep_retrofit.describe(path)
            self.assertEqual(result["name"], "widget-reviewer")
            self.assertEqual(result["description"], "Reviews widgets for defects.")

    def test_frontmatter_summary_field_used_as_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "skill.md"
            _write(path, "---\nsummary: Summarizes things.\n---\n# Body\n")
            result = cep_retrofit.describe(path)
            self.assertEqual(result["description"], "Summarizes things.")

    def test_heading_and_paragraph_fallback_no_frontmatter(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.prompt.md"
            _write(path, "# Widget Review\n\nThis prompt reviews widgets for structural defects.\nSecond line of the same paragraph.\n\nUnrelated later paragraph.\n")
            result = cep_retrofit.describe(path)
            self.assertEqual(result["name"], "Widget Review")
            self.assertIn("reviews widgets", result["description"])
            self.assertNotIn("Unrelated", result["description"])

    def test_first_nonblank_line_fallback_no_heading_no_frontmatter(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.md"
            _write(path, "\n\nJust a plain first line.\nMore text.\n")
            result = cep_retrofit.describe(path)
            self.assertEqual(result["description"], "Just a plain first line.")
            self.assertEqual(result["name"], "notes")  # falls back to filename stem


class RecommendTest(unittest.TestCase):
    def test_code_related_terms_detected(self):
        result = cep_retrofit.recommend("Reviews and refactors code before merge.")
        self.assertTrue(result["code_related"])
        self.assertIn("code", result["matched_code_terms"])
        self.assertIn("refactors", result["matched_code_terms"])

    def test_task_related_terms_detected(self):
        result = cep_retrofit.recommend("Helps design and plan a new feature end to end.")
        self.assertTrue(result["task_related"])
        self.assertIn("design", result["matched_task_terms"])
        self.assertIn("plan", result["matched_task_terms"])
        self.assertIn("feature", result["matched_task_terms"])

    def test_neither_matches_on_unrelated_description(self):
        result = cep_retrofit.recommend("Formats currency values for display in reports.")
        self.assertFalse(result["code_related"])
        self.assertFalse(result["task_related"])

    def test_both_can_match_simultaneously(self):
        result = cep_retrofit.recommend("Plans and implements a fix, then reviews the code.")
        self.assertTrue(result["code_related"])
        self.assertTrue(result["task_related"])


class CheckPointerTest(unittest.TestCase):
    def test_detects_pointer_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "SKILL.md"
            _write(path, "See ../cep/CONSUMING-CONTEXT-PACKAGE.md for how to consume a package.\n")
            result = cep_retrofit.check_pointer(path, ["CONSUMING-CONTEXT-PACKAGE.md", "CONSUMING-CODE-GRAPH.md"])
            self.assertTrue(result["CONSUMING-CONTEXT-PACKAGE.md"])
            self.assertFalse(result["CONSUMING-CODE-GRAPH.md"])

    def test_matches_regardless_of_reference_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "SKILL.md"
            _write(path, "See /context-engineering-protocol:CONSUMING-CONTEXT-PACKAGE.md (plugin-qualified).\n")
            result = cep_retrofit.check_pointer(path, ["CONSUMING-CONTEXT-PACKAGE.md"])
            self.assertTrue(result["CONSUMING-CONTEXT-PACKAGE.md"])


class FindInsertionPointTest(unittest.TestCase):
    def test_see_also_section_preferred(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "SKILL.md"
            _write(path, "---\nname: x\n---\n# Overview\nSome text.\n\n## See Also\n- a link\n")
            result = cep_retrofit.find_insertion_point(path)
            self.assertEqual(result["method"], "see-also")

    def test_frontmatter_end_used_when_no_see_also(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "SKILL.md"
            _write(path, "---\nname: x\n---\n## License\nMIT\n")
            result = cep_retrofit.find_insertion_point(path)
            self.assertEqual(result["method"], "frontmatter")

    def test_qualifying_heading_used_when_no_frontmatter(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.prompt.md"
            _write(path, "# Widget Review\n\n## Overview\nDoes review things.\n\n## Examples\nstuff\n")
            result = cep_retrofit.find_insertion_point(path)
            self.assertEqual(result["method"], "heading")
            self.assertEqual(result["heading"], "Overview")

    def test_disqualifying_headings_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.prompt.md"
            _write(path, "# Widget Review\n\n## License\nMIT\n\n## Changelog\nv1\n")
            result = cep_retrofit.find_insertion_point(path)
            self.assertEqual(result["method"], "prepend")

    def test_prepend_fallback_when_nothing_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.md"
            _write(path, "Just plain prose with no headings at all.\n")
            result = cep_retrofit.find_insertion_point(path)
            self.assertEqual(result, {"method": "prepend", "line": 0, "heading": None})


class CliSmokeTest(unittest.TestCase):
    """Each subcommand runs end-to-end and prints valid JSON."""

    def test_inventory_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp) / "example-skill" / "SKILL.md", "# Example\n")
            argv = ["inventory", tmp]
            import io
            import contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = cep_retrofit.main(argv)
            self.assertEqual(rc, 0)
            data = json.loads(buf.getvalue())
            self.assertEqual(len(data["units"]), 1)

    def test_recommend_cli(self):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cep_retrofit.main(["recommend", "--description", "Designs and plans a change."])
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertTrue(data["task_related"])

    def test_recommend_cli_description_file(self):
        """--description-file reads the same text a shell would otherwise have to quote.

        Regression test for a real cross-runtime finding: mattpocock/skills'
        code-review and diagnosing-bugs both have descriptions containing embedded
        double-quotes (e.g. `asks to "review since X"`). Passing that text inline via
        --description on Windows PowerShell mangles/truncates it before this script
        ever sees it, silently producing a false "neither" classification with no
        error. --description-file sidesteps shell quoting entirely.
        """
        import io
        import contextlib
        with tempfile.TemporaryDirectory() as tmp:
            desc_path = Path(tmp) / "description.txt"
            _write(
                desc_path,
                'Use when the user wants to review a branch, a PR, work-in-progress '
                'changes, or asks to "review since X".',
            )
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = cep_retrofit.main(["recommend", "--description-file", str(desc_path)])
            self.assertEqual(rc, 0)
            data = json.loads(buf.getvalue())
            self.assertTrue(data["task_related"])

    def test_recommend_cli_description_file_missing_exits_nonzero(self):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            rc = cep_retrofit.main(
                ["recommend", "--description-file", "/definitely/does/not/exist.txt"]
            )
        self.assertEqual(rc, 1)

    def test_recommend_cli_rejects_both_description_flags(self):
        with self.assertRaises(SystemExit):
            cep_retrofit.main(
                ["recommend", "--description", "x", "--description-file", "y.txt"]
            )

    def test_recommend_cli_rejects_neither_description_flag(self):
        with self.assertRaises(SystemExit):
            cep_retrofit.main(["recommend"])

    def test_inventory_cli_missing_root_exits_nonzero(self):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            rc = cep_retrofit.main(["inventory", "/definitely/does/not/exist/anywhere"])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
