#!/usr/bin/env python3
"""Regression suite for wizard_retrofit_inventory.py (Journey 3, Phase A).

Stdlib unittest only. Calls build_inventory()/to_json_dict() directly rather than
driving a real socket - route-wiring for GET /api/retrofit/inventory is covered
separately in test_wizard_server.py's TestApiRetrofitInventory, following that
file's own module docstring on why only test_wizard_server.py needs the real-
bound-socket treatment.

Real-fixture-copy convention (matches test_wizard_decision_staging.py /
test_cep_retrofit.py): the real cep_retrofit.py is copied into a temp dir shaped
like .github/skills/ult-cep-retrofit/scripts/ so build_inventory()'s dynamic
import exercises the actual script, not a stand-in. The *retrofit target* itself
is always a fabricated placeholder library ("widget-reviewer", "second-widget")
never a real skill name, matching ult-cep-retrofit's own zero-hardcoded-knowledge
rule and this repo's established test-fixture naming.
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wizard_retrofit_inventory as wri  # noqa: E402


def _find_real_repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        marker = (
            candidate
            / ".github"
            / "skills"
            / "ult-cep-retrofit"
            / "scripts"
            / "cep_retrofit.py"
        )
        if marker.exists():
            return candidate
    raise RuntimeError(
        "could not locate context-engineering-oss repo root from this test "
        "file's location"
    )


REAL_REPO_ROOT = _find_real_repo_root()
REAL_CEP_RETROFIT_SCRIPT = (
    REAL_REPO_ROOT / ".github" / "skills" / "ult-cep-retrofit" / "scripts" / "cep_retrofit.py"
)


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _install_ult_cep_retrofit(repo_root: Path) -> None:
    """Copies the real cep_retrofit.py into a fixture repo, same shape
    test_wizard_decision_staging.py uses for ult-repo-layout - a SKILL.md isn't
    needed here (wizard_retrofit_inventory only ever imports the script)."""
    scripts_dir = repo_root / ".github" / "skills" / "ult-cep-retrofit" / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    import shutil

    shutil.copy(REAL_CEP_RETROFIT_SCRIPT, scripts_dir / "cep_retrofit.py")


WIDGET_REVIEWER_SKILL_MD = """---
name: widget-reviewer
description: Use this skill to review code changes and write tests before merging.
---

# Widget Reviewer

Reviews code changes.
"""

SECOND_WIDGET_MD = """# Second Widget

A helper that plans upcoming features and implements them.
"""


class RetrofitInventoryTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


class TestMissingInstall(RetrofitInventoryTestCase):
    def test_missing_ult_cep_retrofit_is_a_clear_error(self):
        # No .github/skills/ult-cep-retrofit installed at all.
        with self.assertRaises(wri.RetrofitInventoryError) as ctx:
            wri.build_inventory(str(self.root), ".")
        self.assertIn("ult-cep-retrofit", str(ctx.exception))
        self.assertIn("is ult-cep-retrofit installed", str(ctx.exception))


class TestContainmentAndTargetValidation(RetrofitInventoryTestCase):
    def setUp(self):
        super().setUp()
        _install_ult_cep_retrofit(self.root)

    def test_containment_violation_is_a_retrofit_inventory_error(self):
        with self.assertRaises(wri.RetrofitInventoryError):
            wri.build_inventory(str(self.root), "../escaped")

    def test_non_directory_target_is_a_retrofit_inventory_error(self):
        _write(self.root / "afile.txt", "not a directory\n")
        with self.assertRaises(wri.RetrofitInventoryError) as ctx:
            wri.build_inventory(str(self.root), "afile.txt")
        self.assertIn("is not a directory", str(ctx.exception))


class TestSuccessfulInventory(RetrofitInventoryTestCase):
    def setUp(self):
        super().setUp()
        _install_ult_cep_retrofit(self.root)
        _write(self.root / "widget-reviewer" / "SKILL.md", WIDGET_REVIEWER_SKILL_MD)
        _write(self.root / "second-widget.md", SECOND_WIDGET_MD)
        _write(self.root / "orphan-notes" / "config.yaml", "key: value\n")

    def test_inventory_reports_units_and_unclaimed_dirs(self):
        result = wri.build_inventory(str(self.root), ".")
        self.assertEqual(result.target_rel_path, ".")
        self.assertEqual(result.unclaimed_dirs, ["orphan-notes"])

        by_id = {u.unit_id: u for u in result.units}
        self.assertEqual(set(by_id), {"widget-reviewer", "second-widget.md"})

        skill_dir = by_id["widget-reviewer"]
        self.assertEqual(skill_dir.type, "skill-dir")
        self.assertEqual(skill_dir.name, "widget-reviewer")
        self.assertFalse(skill_dir.via_symlink)
        self.assertEqual(skill_dir.describe_error, "")
        self.assertTrue(skill_dir.code_related)
        self.assertTrue(skill_dir.task_related)
        self.assertIn("review", skill_dir.matched_code_terms)
        self.assertIn("changes", skill_dir.matched_task_terms)
        # target_rel_path is "." here, so repo-root-relative and
        # target-relative happen to coincide - see
        # test_inventory_against_a_library_subdirectory below for the case
        # where they don't.
        self.assertEqual(skill_dir.primary_file, "widget-reviewer/SKILL.md")

        flat_file = by_id["second-widget.md"]
        self.assertEqual(flat_file.type, "flat-file")
        self.assertEqual(flat_file.name, "Second Widget")
        self.assertFalse(flat_file.code_related)
        self.assertTrue(flat_file.task_related)
        self.assertIn("plans", flat_file.matched_task_terms)
        self.assertEqual(flat_file.primary_file, "second-widget.md")

    def test_to_json_dict_round_trips_as_plain_dict(self):
        result = wri.build_inventory(str(self.root), ".")
        payload = wri.to_json_dict(result)
        self.assertIsInstance(payload, dict)
        self.assertEqual(payload["target_rel_path"], ".")
        self.assertEqual(len(payload["units"]), 2)
        self.assertIsInstance(payload["units"][0], dict)

    def test_inventory_against_a_subdirectory_target(self):
        # Point the target at the skill-dir itself rather than the fixture root -
        # exercises the containment-then-relative-path math for a non-root target.
        result = wri.build_inventory(str(self.root), "widget-reviewer")
        self.assertEqual(result.target_rel_path, "widget-reviewer")
        # cep_retrofit.inventory()'s skill-dir heuristic only fires for a SKILL.md
        # found below the walk root, not the walk root itself (is_root guard) - so
        # here, with "widget-reviewer" as the root, its own SKILL.md instead falls
        # through to the flat-file heuristic and is reported as a flat-file unit.
        self.assertEqual(len(result.units), 1)
        unit = result.units[0]
        self.assertEqual(unit.unit_id, "SKILL.md")
        self.assertEqual(unit.type, "flat-file")
        self.assertEqual(unit.name, "widget-reviewer")
        self.assertEqual(result.unclaimed_dirs, [])
        self.assertEqual(unit.primary_file, "widget-reviewer/SKILL.md")

    def test_inventory_against_a_library_subdirectory(self):
        # Regression test: the real Journey 3 shape per the plan's own scope
        # decision #2 (v1 target must be a subdirectory of ctx.repo_root, e.g.
        # a vendored library) - target is a *container* directory holding
        # multiple units below it, distinct from test_inventory_against_a_
        # subdirectory_target above where target *is* a unit's own directory
        # (and so target-relative and repo-root-relative primary_file values
        # happened to coincide, masking this exact bug). Caught by a real
        # Playwright walkthrough against this exact shape (target =
        # "_manual-retrofit-fixture", not "."): every unit's primary_file was
        # returned target-relative (e.g. "second-widget.md") while
        # POST /api/retrofit/select's check_containment(repo_root,
        # primary_file) and wizard_retrofit_draft.build_draft() both assume
        # repo-root-relative, so every select/draft call 400'd with "<file>
        # is not a file".
        _write(self.root / "library" / "widget-reviewer" / "SKILL.md", WIDGET_REVIEWER_SKILL_MD)
        _write(self.root / "library" / "second-widget.md", SECOND_WIDGET_MD)

        result = wri.build_inventory(str(self.root), "library")
        self.assertEqual(result.target_rel_path, "library")

        by_id = {u.unit_id: u for u in result.units}
        self.assertEqual(set(by_id), {"widget-reviewer", "second-widget.md"})
        self.assertEqual(by_id["widget-reviewer"].primary_file, "library/widget-reviewer/SKILL.md")
        self.assertEqual(by_id["widget-reviewer"].path, "library/widget-reviewer")
        self.assertEqual(by_id["second-widget.md"].primary_file, "library/second-widget.md")
        self.assertEqual(by_id["second-widget.md"].path, "library/second-widget.md")

        # And the repo-root-relative value is exactly what a real select call
        # against repo_root (not `target`) must be able to resolve.
        for unit in result.units:
            self.assertTrue((self.root / unit.primary_file).is_file())

    def test_skill_directory_is_preferred_over_duplicate_flat_documentation(self):
        # Regression test: cep_retrofit.inventory()'s union-of-heuristics
        # design (correct and intentional at that layer - see its docstring)
        # means a flat *.md file named after an existing, *nearby* skill
        # directory (e.g. a stray skills/implement.md sibling of
        # skills/implement/SKILL.md) previously surfaced as a second,
        # independent unit. Real library run returned 82 units instead of
        # the true 37, with duplicate "implement" entries. The dedupe
        # belongs in this wizard view, not cep_retrofit.py itself - see
        # _dedupe_flat_file_units's own docstring. Sibling placement here
        # (both directly under "skills") is what makes the two "the same
        # directory" under _dirs_proximate() - see
        # test_distant_same_stem_flat_file_is_not_treated_as_duplicate below
        # for the case this must *not* fire on.
        _write(self.root / "library" / "skills" / "implement" / "SKILL.md", WIDGET_REVIEWER_SKILL_MD)
        _write(self.root / "library" / "skills" / "implement.md", SECOND_WIDGET_MD)

        result = wri.build_inventory(str(self.root), "library")

        self.assertEqual(
            [(unit.type, unit.primary_file) for unit in result.units],
            [("skill-dir", "library/skills/implement/SKILL.md")],
        )

    def test_root_adjacent_same_stem_flat_file_is_treated_as_duplicate(self):
        # One level apart (target-root vs. one directory down) also counts
        # as proximate - a flat file sitting right outside the directory
        # tree holding the skill-dir it duplicates.
        _write(self.root / "library" / "skills" / "implement" / "SKILL.md", WIDGET_REVIEWER_SKILL_MD)
        _write(self.root / "library" / "implement.md", SECOND_WIDGET_MD)

        result = wri.build_inventory(str(self.root), "library")

        self.assertEqual(
            [(unit.type, unit.primary_file) for unit in result.units],
            [("skill-dir", "library/skills/implement/SKILL.md")],
        )

    def test_distant_same_stem_flat_file_is_not_treated_as_duplicate(self):
        # Guards against the false-collision defect: two same-stem files in
        # unrelated parts of a larger tree (parents "rules" and "tools" here
        # satisfy none of _dirs_proximate()'s three relations) must both
        # survive as independent units, not get silently deduped just
        # because they share a filename.
        _write(self.root / "library" / "tools" / "build" / "SKILL.md", WIDGET_REVIEWER_SKILL_MD)
        _write(self.root / "library" / "rules" / "build.md", SECOND_WIDGET_MD)

        result = wri.build_inventory(str(self.root), "library")

        by_id = {u.unit_id: u for u in result.units}
        self.assertEqual(set(by_id), {"tools/build", "rules/build.md"})

    def test_double_suffix_companion_is_treated_as_duplicate(self):
        # A .prompt.md companion of a skill-dir must dedupe correctly - the
        # double suffix has to be stripped before stem comparison, or
        # "widget.prompt" (the un-stripped stem) never matches "widget".
        _write(self.root / "library" / "skills" / "widget" / "SKILL.md", WIDGET_REVIEWER_SKILL_MD)
        _write(self.root / "library" / "skills" / "widget.prompt.md", SECOND_WIDGET_MD)

        result = wri.build_inventory(str(self.root), "library")

        self.assertEqual(
            [(unit.type, unit.primary_file) for unit in result.units],
            [("skill-dir", "library/skills/widget/SKILL.md")],
        )


class TestTierPropagation(RetrofitInventoryTestCase):
    def setUp(self):
        super().setUp()
        _install_ult_cep_retrofit(self.root)

    def test_tier_and_note_propagate_onto_each_unit(self):
        _write(self.root / "widget-reviewer" / "SKILL.md", WIDGET_REVIEWER_SKILL_MD)
        _write(self.root / "docs" / "second-widget.md", SECOND_WIDGET_MD)

        result = wri.build_inventory(str(self.root), ".")
        by_id = {u.unit_id: u for u in result.units}

        skill_dir = by_id["widget-reviewer"]
        self.assertEqual(skill_dir.tier, "canonical")
        self.assertEqual(skill_dir.note, "")

        docs_flat_file = by_id["docs/second-widget.md"]
        self.assertEqual(docs_flat_file.tier, "supplementary")
        self.assertNotEqual(docs_flat_file.note, "")

    def test_result_reports_tier_counts_reflecting_dedupe(self):
        # tier_counts must reflect what's actually left in result.units after
        # _dedupe_flat_file_units() runs, not cep_retrofit's raw pre-dedupe
        # counts - the duplicate here is dropped, so it must not be counted.
        _write(self.root / "skills" / "widget" / "SKILL.md", WIDGET_REVIEWER_SKILL_MD)
        _write(self.root / "skills" / "widget.md", SECOND_WIDGET_MD)
        _write(self.root / "second-widget.md", SECOND_WIDGET_MD)

        result = wri.build_inventory(str(self.root), ".")

        self.assertEqual(len(result.units), 2)  # the duplicate was dropped
        self.assertEqual(result.tier_counts, {"canonical": 1, "supplementary": 1})


class TestDescribeErrorIsolation(RetrofitInventoryTestCase):
    def test_one_unit_failing_describe_does_not_drop_the_others(self):
        _install_ult_cep_retrofit(self.root)
        _write(self.root / "widget-reviewer" / "SKILL.md", WIDGET_REVIEWER_SKILL_MD)
        _write(self.root / "second-widget.md", SECOND_WIDGET_MD)

        cr = wri._import_cep_retrofit(str(self.root))
        original_describe = cr.describe

        def flaky_describe(path):
            if "second-widget" in path:
                raise OSError("simulated read failure")
            return original_describe(path)

        with mock.patch.object(cr, "describe", side_effect=flaky_describe):
            result = wri.build_inventory(str(self.root), ".")

        by_id = {u.unit_id: u for u in result.units}
        self.assertEqual(len(result.units), 2)

        flaky = by_id["second-widget.md"]
        self.assertNotEqual(flaky.describe_error, "")
        self.assertEqual(flaky.name, "")
        self.assertFalse(flaky.code_related)
        self.assertFalse(flaky.task_related)

        healthy = by_id["widget-reviewer"]
        self.assertEqual(healthy.describe_error, "")
        self.assertEqual(healthy.name, "widget-reviewer")
        self.assertTrue(healthy.code_related)


if __name__ == "__main__":
    unittest.main()
