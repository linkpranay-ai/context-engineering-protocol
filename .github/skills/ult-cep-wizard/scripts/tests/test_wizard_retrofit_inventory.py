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
import json
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
        # No .cep-install.json in this fixture, so nothing was pruned - the
        # field is still present and empty, never absent.
        self.assertEqual(result.excluded_owned_paths, [])

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

    def test_manifest_owned_paths_are_passed_through_as_excluded(self):
        # A target with its own .cep-install.json has those paths pruned by
        # cep_retrofit.inventory(). build_inventory() must carry that list
        # through to the frontend, target-relative and unrewritten, the same
        # way unclaimed_dirs is - otherwise the wizard shows an inventory
        # with a silent hole in it.
        _write(
            self.root / ".cep-install.json",
            json.dumps({
                "schema_version": 1,
                "runtime": ["claude", "copilot"],
                "mode": "full",
                "only_skills": None,
                "owned_paths": [".github/skills"],
                "merged_paths": [],
                "installed_at": "2026-01-01T00:00:00Z",
            }),
        )
        result = wri.build_inventory(str(self.root), ".")
        self.assertIn(".github/skills", result.excluded_owned_paths)
        unit_ids = {u.unit_id for u in result.units}
        self.assertFalse(any(u.startswith(".github/skills") for u in unit_ids))
        self.assertIn(".github/skills", wri.to_json_dict(result)["excluded_owned_paths"])

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

    def test_flat_file_matching_skill_dir_name_is_flagged_not_dropped(self):
        # Regression test: cep_retrofit.inventory()'s union-of-heuristics
        # design (correct and intentional at that layer - see its docstring)
        # means a flat *.md file named after an existing skill directory
        # (e.g. a stray skills/implement.md sibling of
        # skills/implement/SKILL.md) surfaces as a second, independent
        # unit. Real library run returned 82 units instead of the true 37,
        # with duplicate "implement" entries. This wizard view flags that
        # unit rather than silently dropping it - see
        # _flag_stray_duplicate_flat_files's own docstring for why a drop
        # (an earlier version of this function) turned out to be the wrong
        # call. Sibling placement here (both directly under "skills") is
        # the easy case; test_separate_top_level_trees_with_matching_leaf_
        # name_are_flagged below covers the shape that a proximity-gated
        # version of this check used to miss entirely.
        _write(self.root / "library" / "skills" / "implement" / "SKILL.md", WIDGET_REVIEWER_SKILL_MD)
        _write(self.root / "library" / "skills" / "implement.md", SECOND_WIDGET_MD)

        result = wri.build_inventory(str(self.root), "library")

        by_id = {u.unit_id: u for u in result.units}
        self.assertEqual(set(by_id), {"skills/implement", "skills/implement.md"})

        skill_dir = by_id["skills/implement"]
        self.assertEqual(skill_dir.type, "skill-dir")
        self.assertEqual(skill_dir.tier, "canonical")
        self.assertEqual(skill_dir.note, "")

        flat_file = by_id["skills/implement.md"]
        self.assertEqual(flat_file.type, "flat-file")
        self.assertEqual(flat_file.tier, "supplementary")
        self.assertIn("duplicates skills/implement", flat_file.note)

    def test_root_adjacent_same_stem_flat_file_is_flagged_not_dropped(self):
        # A flat file sitting right outside the directory tree holding the
        # skill-dir it duplicates - same flag-not-drop treatment as the
        # sibling case above.
        _write(self.root / "library" / "skills" / "implement" / "SKILL.md", WIDGET_REVIEWER_SKILL_MD)
        _write(self.root / "library" / "implement.md", SECOND_WIDGET_MD)

        result = wri.build_inventory(str(self.root), "library")

        by_id = {u.unit_id: u for u in result.units}
        self.assertEqual(set(by_id), {"skills/implement", "implement.md"})

        flat_file = by_id["implement.md"]
        self.assertEqual(flat_file.tier, "supplementary")
        self.assertIn("duplicates skills/implement", flat_file.note)

    def test_separate_top_level_trees_with_matching_leaf_name_are_flagged(self):
        # The exact real-world shape a proximity-gated version of this check
        # used to miss: a documentation flat-file and its skill-dir
        # counterpart living in two entirely separate top-level trees
        # (docs/ vs. skills/), sharing only a leaf name ("implement") - not
        # siblings, not one level apart. Matching is unconditional on
        # location now, so this pair must be flagged, not silently missed.
        _write(self.root / "library" / "skills" / "engineering" / "implement" / "SKILL.md", WIDGET_REVIEWER_SKILL_MD)
        _write(self.root / "library" / "docs" / "engineering" / "implement.md", SECOND_WIDGET_MD)

        result = wri.build_inventory(str(self.root), "library")

        by_id = {u.unit_id: u for u in result.units}
        self.assertEqual(set(by_id), {"skills/engineering/implement", "docs/engineering/implement.md"})

        flat_file = by_id["docs/engineering/implement.md"]
        self.assertEqual(flat_file.tier, "supplementary")
        self.assertIn("duplicates skills/engineering/implement", flat_file.note)

    def test_double_suffix_companion_is_flagged_not_dropped(self):
        # A .prompt.md companion of a skill-dir must still be recognized as
        # a stem match - the double suffix has to be stripped before stem
        # comparison, or "widget.prompt" (the un-stripped stem) never
        # matches "widget".
        _write(self.root / "library" / "skills" / "widget" / "SKILL.md", WIDGET_REVIEWER_SKILL_MD)
        _write(self.root / "library" / "skills" / "widget.prompt.md", SECOND_WIDGET_MD)

        result = wri.build_inventory(str(self.root), "library")

        by_id = {u.unit_id: u for u in result.units}
        self.assertEqual(set(by_id), {"skills/widget", "skills/widget.prompt.md"})

        flat_file = by_id["skills/widget.prompt.md"]
        self.assertEqual(flat_file.tier, "supplementary")
        self.assertIn("duplicates skills/widget", flat_file.note)


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

    def test_result_reports_tier_counts_reflecting_all_units_including_flagged_duplicates(self):
        # tier_counts must reflect what's actually in result.units after
        # _flag_stray_duplicate_flat_files() runs. Nothing is dropped any
        # more, so all three units survive; the stem-matched flat file is
        # flagged supplementary with a duplicate note, and the unrelated
        # flat file is supplementary too (cep_retrofit.py's own default tier
        # for every flat-file unit) but carries no duplicate note.
        _write(self.root / "skills" / "widget" / "SKILL.md", WIDGET_REVIEWER_SKILL_MD)
        _write(self.root / "skills" / "widget.md", SECOND_WIDGET_MD)
        _write(self.root / "second-widget.md", SECOND_WIDGET_MD)

        result = wri.build_inventory(str(self.root), ".")

        self.assertEqual(len(result.units), 3)
        self.assertEqual(result.tier_counts, {"canonical": 1, "supplementary": 2})

        by_id = {u.unit_id: u for u in result.units}
        self.assertIn("duplicates skills/widget", by_id["skills/widget.md"].note)
        self.assertEqual(by_id["second-widget.md"].note, "")


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


class TestSourceDirectoryAndDirectoryCounts(RetrofitInventoryTestCase):
    """the 2026-08-31 Round-2 evaluation's finding on retrofit-inventory grouping and filtering by source directory: "grouped counts by source
    directory" - covers source_directory assignment for all three unit
    shapes (skill-dir, manifest-dir, flat-file), root-level flat files
    (no "/" in their target-relative path), the target-subdirectory case
    (source_directory must be target-relative, not repo-root-relative), and
    directory_counts' total/canonical/supplementary sort order."""

    def setUp(self):
        super().setUp()
        _install_ult_cep_retrofit(self.root)

    def test_source_directory_for_skill_dir_and_flat_file_units(self):
        _write(self.root / "skills" / "widget-reviewer" / "SKILL.md", WIDGET_REVIEWER_SKILL_MD)
        _write(self.root / "skills" / "second-widget.md", SECOND_WIDGET_MD)

        result = wri.build_inventory(str(self.root), ".")
        by_id = {u.unit_id: u for u in result.units}

        self.assertEqual(by_id["skills/widget-reviewer"].source_directory, "skills")
        self.assertEqual(by_id["skills/second-widget.md"].source_directory, "skills")

    def test_source_directory_for_root_level_flat_file_is_the_root_bucket_sentinel(self):
        # the 2026-08-31 Round-2 evaluation's finding on retrofit-inventory
        # grouping and filtering by source directory: no "/" in the
        # target-relative path at all means this unit sits directly at the
        # retrofit target root, not inside any subdirectory of it - it must
        # bucket under the shared ROOT_BUCKET_NAME sentinel, not under its
        # own filename (which would give every flat-target unit its own
        # bogus one-unit "directory").
        _write(self.root / "second-widget.md", SECOND_WIDGET_MD)

        result = wri.build_inventory(str(self.root), ".")
        unit = result.units[0]
        self.assertEqual(unit.source_directory, wri.ROOT_BUCKET_NAME)

    def test_flat_target_with_multiple_root_level_files_share_one_bucket(self):
        # A wholly flat/standalone target (every unit a loose top-level
        # file, no subdirectories at all) must produce exactly one shared
        # bucket, not one per file.
        _write(self.root / "second-widget.md", SECOND_WIDGET_MD)
        _write(self.root / "third-widget.md", SECOND_WIDGET_MD)

        result = wri.build_inventory(str(self.root), ".")

        self.assertEqual(len(result.directory_counts), 1)
        self.assertEqual(result.directory_counts[0]["directory"], wri.ROOT_BUCKET_NAME)
        self.assertEqual(result.directory_counts[0]["total"], 2)

    def test_source_directory_is_target_relative_not_repo_root_relative(self):
        # Same distinction test_inventory_against_a_library_subdirectory
        # draws for primary_file/path: source_directory must bucket by the
        # first segment *below the target*, not repo root, or grouping a
        # vendored subdirectory would show one giant "library" bucket
        # instead of the useful per-unit-directory breakdown.
        _write(self.root / "library" / "skills" / "widget-reviewer" / "SKILL.md", WIDGET_REVIEWER_SKILL_MD)
        _write(self.root / "library" / "second-widget.md", SECOND_WIDGET_MD)

        result = wri.build_inventory(str(self.root), "library")
        by_id = {u.unit_id: u for u in result.units}

        self.assertEqual(by_id["skills/widget-reviewer"].source_directory, "skills")
        self.assertEqual(by_id["second-widget.md"].source_directory, wri.ROOT_BUCKET_NAME)

    def test_mixed_target_gets_a_subdirectory_bucket_and_a_root_bucket(self):
        # the 2026-08-31 Round-2 evaluation's finding on retrofit-inventory
        # grouping and filtering by source directory: a target mixing a
        # real subdirectory with a loose top-level file must produce
        # exactly two buckets - the subdirectory's own name, and the shared
        # root-bucket sentinel for the flat file - not three (which the old
        # per-filename bucketing would have produced for two flat files).
        _write(self.root / "skills" / "widget-reviewer" / "SKILL.md", WIDGET_REVIEWER_SKILL_MD)
        _write(self.root / "second-widget.md", SECOND_WIDGET_MD)

        result = wri.build_inventory(str(self.root), ".")

        self.assertEqual(
            sorted(b["directory"] for b in result.directory_counts),
            sorted(["skills", wri.ROOT_BUCKET_NAME]),
        )

    def test_directory_counts_aggregates_and_sorts_by_total_desc_then_name(self):
        # "skills" gets 2 units (1 canonical, 1 supplementary); "docs" and
        # "z-notes" each get 1 supplementary unit. Expected order: "skills"
        # first (total=2), then "docs" before "z-notes" on name ascending
        # since both have total=1.
        _write(self.root / "skills" / "widget-reviewer" / "SKILL.md", WIDGET_REVIEWER_SKILL_MD)
        _write(self.root / "skills" / "widget-reviewer.md", SECOND_WIDGET_MD)
        _write(self.root / "z-notes" / "second-widget.md", SECOND_WIDGET_MD)
        _write(self.root / "docs" / "second-widget.md", SECOND_WIDGET_MD)

        result = wri.build_inventory(str(self.root), ".")

        self.assertEqual(
            [b["directory"] for b in result.directory_counts],
            ["skills", "docs", "z-notes"],
        )
        skills_bucket = result.directory_counts[0]
        self.assertEqual(skills_bucket["total"], 2)
        self.assertEqual(skills_bucket["canonical"], 1)
        self.assertEqual(skills_bucket["supplementary"], 1)

        docs_bucket = result.directory_counts[1]
        self.assertEqual(docs_bucket, {"directory": "docs", "total": 1, "canonical": 0, "supplementary": 1})

    def test_directory_counts_reflect_all_units_including_flagged_duplicates(self):
        # Mirrors test_result_reports_tier_counts_reflecting_all_units_
        # including_flagged_duplicates above - nothing _flag_stray_duplicate_
        # flat_files() flags gets dropped, so directory_counts must still
        # sum to len(result.units).
        _write(self.root / "skills" / "widget" / "SKILL.md", WIDGET_REVIEWER_SKILL_MD)
        _write(self.root / "skills" / "widget.md", SECOND_WIDGET_MD)
        _write(self.root / "second-widget.md", SECOND_WIDGET_MD)

        result = wri.build_inventory(str(self.root), ".")

        total_from_buckets = sum(b["total"] for b in result.directory_counts)
        self.assertEqual(total_from_buckets, len(result.units))
        self.assertEqual(total_from_buckets, 3)


class TestExternalRoot(RetrofitInventoryTestCase):
    """the 2026-08-31 Round-2 evaluation's finding on external (out-of-repo) retrofit-target containment - "Retrofit wizard cannot
    operate on sibling or standalone skill library". `self.root` here plays
    ctx.repo_root (only ult-cep-retrofit's engine lives under it); a second,
    entirely separate temp dir plays the external retrofit target - mirrors a
    cloned sibling library the way that evaluation's repro describes."""

    def setUp(self):
        super().setUp()
        _install_ult_cep_retrofit(self.root)
        self._ext_tmp = tempfile.TemporaryDirectory()
        self.external_root = Path(self._ext_tmp.name)

    def tearDown(self):
        self._ext_tmp.cleanup()
        super().tearDown()

    def test_inventory_scans_external_root_not_repo_root(self):
        _write(self.external_root / "widget-reviewer" / "SKILL.md", WIDGET_REVIEWER_SKILL_MD)
        _write(self.external_root / "second-widget.md", SECOND_WIDGET_MD)
        # Nothing under self.root (repo_root) except ult-cep-retrofit itself -
        # if build_inventory scanned repo_root instead of external_root by
        # mistake, this would come back empty.

        result = wri.build_inventory(
            str(self.root), ".", external_root=str(self.external_root)
        )

        self.assertEqual(result.target_root, str(self.external_root))
        by_id = {u.unit_id: u for u in result.units}
        self.assertEqual(set(by_id), {"widget-reviewer", "second-widget.md"})

    def test_unit_paths_are_relative_to_external_root_not_repo_root(self):
        # Same regression shape as test_inventory_against_a_library_
        # subdirectory above, but for the external-root axis: a select/apply
        # call must be able to resolve primary_file against external_root.
        _write(self.external_root / "library" / "second-widget.md", SECOND_WIDGET_MD)

        result = wri.build_inventory(
            str(self.root), "library", external_root=str(self.external_root)
        )

        self.assertEqual(result.target_rel_path, "library")
        unit = result.units[0]
        self.assertEqual(unit.primary_file, "library/second-widget.md")
        self.assertTrue((self.external_root / unit.primary_file).is_file())
        # And NOT resolvable against repo_root - proves this is really
        # external-root-relative, not accidentally repo-root-relative too.
        self.assertFalse((self.root / unit.primary_file).is_file())

    def test_target_outside_external_root_is_a_containment_error(self):
        with self.assertRaises(wri.RetrofitInventoryError):
            wri.build_inventory(
                str(self.root), "../escaped", external_root=str(self.external_root)
            )

    def test_no_external_root_keeps_target_root_none(self):
        # Backward-compatibility check: the ordinary in-repo call (no
        # external_root argument at all) must still report target_root=None,
        # not silently start requiring the new argument.
        _write(self.root / "second-widget.md", SECOND_WIDGET_MD)
        result = wri.build_inventory(str(self.root), ".")
        self.assertIsNone(result.target_root)

    def test_cep_retrofit_engine_is_still_imported_from_repo_root(self):
        # The engine import must stay anchored at repo_root even when
        # scanning an external target - it's a CEP-project asset, never part
        # of the target being retrofitted. Proven here by *not* installing
        # ult-cep-retrofit under external_root at all; if build_inventory
        # tried to import it from there instead, this would raise
        # RetrofitInventoryError("is ult-cep-retrofit installed") instead of
        # succeeding.
        _write(self.external_root / "second-widget.md", SECOND_WIDGET_MD)
        result = wri.build_inventory(
            str(self.root), ".", external_root=str(self.external_root)
        )
        self.assertEqual(len(result.units), 1)

    # the 2026-08-31 Round-2 evaluation's finding on external retrofit-root
    # breadth: wizard_containment.resolve_external_target refuses a
    # filesystem root or the user's home directory outright, but a
    # legitimate-looking external root can still be enormous - this soft cap
    # is the second, breadth-based gate, checked here at the build_inventory()
    # layer since resolve_external_target has no way to know unit count.
    def test_external_root_over_soft_cap_is_a_retrofit_inventory_error(self):
        for i in range(wri.EXTERNAL_ROOT_UNIT_SOFT_CAP + 100):
            _write(self.external_root / f"widget-{i:04d}.md", SECOND_WIDGET_MD)

        with self.assertRaises(wri.RetrofitInventoryError):
            wri.build_inventory(str(self.root), ".", external_root=str(self.external_root))

    def test_in_repo_target_is_not_subject_to_the_external_soft_cap(self):
        # The cap only applies when external_root is set - an ordinary
        # in-repo target must not start failing merely because it happens to
        # exceed the same unit count.
        for i in range(wri.EXTERNAL_ROOT_UNIT_SOFT_CAP + 10):
            _write(self.root / f"widget-{i:04d}.md", SECOND_WIDGET_MD)

        result = wri.build_inventory(str(self.root), ".")

        self.assertGreater(len(result.units), wri.EXTERNAL_ROOT_UNIT_SOFT_CAP)


if __name__ == "__main__":
    unittest.main()
