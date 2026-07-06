"""Regression suite for validate_layout.py (D20 v2 §15.9, Phase 1).

Stdlib unittest only -- no pytest dependency, so this stays vendorable along
with validate_layout.py itself. Run with:

    python -m unittest discover -s scripts/tests -v
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import validate_layout as vl  # noqa: E402


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# D21 §16.5 M3 invariant (Phase 3c): a workspace_root config that widens
# what_l2.path to {workspace_root}/ without excluding cache/ would let
# What-L2 index its own derived artifacts (e.g. cache/.../*.md) - so any
# fixture that just needs a *valid*, workspace_root-opted-in config (tests
# that aren't themselves exercising the M3 check) pairs workspace_root with
# the recommended what_l2.exclude list.
WORKSPACE_ROOT_DOCS_WITH_WHAT_L2_EXCLUDE = (
    "layout:\n"
    "  workspace_root: docs/\n"
    "layers:\n"
    "  what_l2:\n"
    "    exclude:\n"
    "      - contexts/\n"
    "      - inputs/\n"
    "      - cache/\n"
)


class TestYamlLite(unittest.TestCase):
    def test_simple_mapping(self):
        data = vl.load_yaml_lite("a: 1\nb: two\nc: true\nd: false\ne:\n")
        self.assertEqual(data, {"a": 1, "b": "two", "c": True, "d": False, "e": None})

    def test_nested_mapping(self):
        text = (
            "project_layout:\n"
            "  version: 1\n"
            "  initialized: true\n"
            "  slots:\n"
            "    context_packages:\n"
            "      path: contexts/\n"
            "      kind: directory\n"
        )
        data = vl.load_yaml_lite(text)
        self.assertEqual(data["project_layout"]["version"], 1)
        self.assertTrue(data["project_layout"]["initialized"])
        self.assertEqual(
            data["project_layout"]["slots"]["context_packages"]["path"], "contexts/"
        )

    def test_sequence_of_mappings(self):
        text = (
            "slots:\n"
            "  - slot: context_packages\n"
            "    kind: directory\n"
            "    schema_version: 1\n"
            "  - slot: plans_output\n"
            "    kind: directory\n"
        )
        data = vl.load_yaml_lite(text)
        self.assertEqual(len(data["slots"]), 2)
        self.assertEqual(data["slots"][0]["slot"], "context_packages")
        self.assertEqual(data["slots"][0]["schema_version"], 1)
        self.assertEqual(data["slots"][1]["slot"], "plans_output")

    def test_sequence_of_scalars(self):
        data = vl.load_yaml_lite("exclude:\n  - contexts/\n  - cache/\n")
        self.assertEqual(data["exclude"], ["contexts/", "cache/"])

    def test_comments_and_inline_comments(self):
        text = (
            "# top comment\n"
            "a: 1  # inline\n"
            "# another\n"
            "b: two\n"
        )
        data = vl.load_yaml_lite(text)
        self.assertEqual(data, {"a": 1, "b": "two"})

    def test_quoted_strings(self):
        data = vl.load_yaml_lite('a: "hello # not a comment"\nb: \'single\'\n')
        self.assertEqual(data["a"], "hello # not a comment")
        self.assertEqual(data["b"], "single")


class TestPathWellformedness(unittest.TestCase):
    def test_clean_path_has_no_problems(self):
        self.assertEqual(vl.check_path_wellformedness(Path("contexts")), [])
        self.assertEqual(vl.check_path_wellformedness(Path("output_docs/user-stories")), [])

    def test_windows_reserved_name(self):
        problems = vl.check_path_wellformedness(Path("output_docs/com1"))
        self.assertTrue(any("reserved device name" in p for p in problems))

    def test_reserved_name_substring_is_not_flagged(self):
        # "COM1-migration" is a valid Windows folder name - only an exact
        # "COM1" (optionally with an extension) is reserved.
        self.assertEqual(vl.check_path_wellformedness(Path("output_docs/com1-migration")), [])

    def test_reserved_name_with_extension(self):
        problems = vl.check_path_wellformedness(Path("NUL.yaml"))
        self.assertTrue(any("reserved device name" in p for p in problems))

    def test_trailing_space_and_dot(self):
        problems = vl.check_path_wellformedness(Path("output_docs/staging ./x"))
        self.assertTrue(any("trailing space" in p for p in problems))

    def test_dotdot_segment_flagged(self):
        # Path(".." ) collapses oddly via pathlib, so build parts directly.
        rel = Path("a/../b")
        problems = vl.check_path_wellformedness(rel)
        self.assertTrue(any("'..'" in p for p in problems))


class TestWorkspaceRootWellformedness(unittest.TestCase):
    def test_absent_key_is_fine(self):
        self.assertEqual(vl.check_workspace_root_wellformedness({}), [])
        self.assertEqual(vl.check_workspace_root_wellformedness({"layout": {}}), [])

    def test_dot_is_rejected(self):
        problems = vl.check_workspace_root_wellformedness({"layout": {"workspace_root": "."}})
        self.assertTrue(any("S22" in p for p in problems))

    def test_dot_slash_is_rejected(self):
        problems = vl.check_workspace_root_wellformedness({"layout": {"workspace_root": "./"}})
        self.assertTrue(any("S22" in p for p in problems))

    def test_empty_string_is_rejected(self):
        problems = vl.check_workspace_root_wellformedness({"layout": {"workspace_root": ""}})
        self.assertTrue(any("S22" in p for p in problems))

    def test_valid_value_is_fine(self):
        self.assertEqual(
            vl.check_workspace_root_wellformedness({"layout": {"workspace_root": "docs/"}}), []
        )

    def test_windows_reserved_workspace_root_is_rejected(self):
        problems = vl.check_workspace_root_wellformedness({"layout": {"workspace_root": "com1/"}})
        self.assertTrue(any("reserved device name" in p for p in problems))


class TestResolveDefault(unittest.TestCase):
    def test_default_without_config(self):
        self.assertEqual(vl.resolve_default("context_packages", {}), "contexts/")

    def test_default_from_cache_product_context_path(self):
        config = {"cache": {"product_context_path": "my-contexts/"}}
        self.assertEqual(vl.resolve_default("context_packages", config), "my-contexts/")

    def test_workspace_root_relative_default(self):
        # D21 §16.2 step 3: workspace_root set, no marker, no explicit
        # project_layout.slots path -> {workspace_root}/contexts/.
        config = {"layout": {"workspace_root": "docs/"}}
        self.assertEqual(vl.resolve_default("context_packages", config), "docs/contexts/")

    def test_workspace_root_without_trailing_slash(self):
        config = {"layout": {"workspace_root": "docs"}}
        self.assertEqual(vl.resolve_default("context_packages", config), "docs/contexts/")

    def test_workspace_root_overrides_cache_product_context_path(self):
        # §16.2 step 3 takes precedence over step 4 (cache.product_context_path).
        config = {
            "layout": {"workspace_root": "docs/"},
            "cache": {"product_context_path": "my-contexts/"},
        }
        self.assertEqual(vl.resolve_default("context_packages", config), "docs/contexts/")

    def test_malformed_workspace_root_dot_falls_back_to_pre_d21(self):
        # S22: '.' is invalid (flagged separately) - resolve_default treats
        # it as absent rather than producing './contexts/'.
        config = {"layout": {"workspace_root": "."}}
        self.assertEqual(vl.resolve_default("context_packages", config), "contexts/")

    def test_malformed_workspace_root_empty_falls_back_to_pre_d21(self):
        config = {"layout": {"workspace_root": ""}}
        self.assertEqual(vl.resolve_default("context_packages", config), "contexts/")

    # -- D21 §16.4 / Phase 3b (Gap-B new slots) --------------------------

    def test_plans_output_pre_d21_default_without_config(self):
        self.assertEqual(vl.resolve_default("plans_output", {}), "docs/superpowers/plans/")

    def test_plans_output_workspace_root_relative_default(self):
        config = {"layout": {"workspace_root": "docs/"}}
        self.assertEqual(vl.resolve_default("plans_output", config), "docs/outputs/plans/")

    def test_brainstorm_output_pre_d21_default_without_config(self):
        self.assertEqual(vl.resolve_default("brainstorm_output", {}), "docs/superpowers/specs/")

    def test_brainstorm_output_workspace_root_relative_default(self):
        config = {"layout": {"workspace_root": "docs/"}}
        self.assertEqual(vl.resolve_default("brainstorm_output", config), "docs/outputs/specs/")

    # -- D20 §15.11 / Phase 2 (compiled_guidelines, user_stories_output,
    # security_docs, security_report, project_plan_docs) -----------------

    def test_compiled_guidelines_pre_d21_default_without_config(self):
        self.assertEqual(
            vl.resolve_default("compiled_guidelines", {}),
            "starter_kit/project_guidelines/COMPILED-GUIDELINES.md",
        )

    def test_compiled_guidelines_workspace_root_relative_default(self):
        # D21 §16.4: bucket-reassigned inputs -> cache (derived artifact) as
        # well as re-rooted.
        config = {"layout": {"workspace_root": "docs/"}}
        self.assertEqual(
            vl.resolve_default("compiled_guidelines", config),
            "docs/cache/project-guidelines/COMPILED-GUIDELINES.md",
        )

    def test_user_stories_output_pre_d21_default_without_config(self):
        self.assertEqual(vl.resolve_default("user_stories_output", {}), "output_docs/user-stories/")

    def test_user_stories_output_workspace_root_relative_default(self):
        config = {"layout": {"workspace_root": "docs/"}}
        self.assertEqual(vl.resolve_default("user_stories_output", config), "docs/outputs/user-stories/")

    def test_security_docs_pre_d21_default_without_config(self):
        self.assertEqual(vl.resolve_default("security_docs", {}), "output_docs/security_docs/")

    def test_security_docs_workspace_root_relative_default(self):
        config = {"layout": {"workspace_root": "docs/"}}
        self.assertEqual(vl.resolve_default("security_docs", config), "docs/outputs/security_docs/")

    def test_security_report_pre_d21_default_without_config(self):
        self.assertEqual(vl.resolve_default("security_report", {}), "output_docs/security_report/")

    def test_security_report_workspace_root_relative_default(self):
        config = {"layout": {"workspace_root": "docs/"}}
        self.assertEqual(vl.resolve_default("security_report", config), "docs/outputs/security_report/")

    def test_project_plan_docs_pre_d21_default_without_config(self):
        self.assertEqual(vl.resolve_default("project_plan_docs", {}), "output_docs/project_plan_docs/")

    def test_project_plan_docs_workspace_root_relative_default(self):
        config = {"layout": {"workspace_root": "docs/"}}
        self.assertEqual(vl.resolve_default("project_plan_docs", config), "docs/outputs/project_plan_docs/")


class TestWhatL2Resolution(unittest.TestCase):
    """D21 §16.5/§16.7 (Phase 3c): resolve_what_l2_path/exclude/index_path -
    config-key resolution helpers, architecturally separate from
    SLOT_REGISTRY (what_l2 has no marker file)."""

    # -- resolve_what_l2_path ---------------------------------------------

    def test_path_default_without_config(self):
        self.assertEqual(vl.resolve_what_l2_path({}), "docs/requirements/")

    def test_path_explicit_config_value_wins(self):
        config = {"layers": {"what_l2": {"path": "docs/reqs/"}}}
        self.assertEqual(vl.resolve_what_l2_path(config), "docs/reqs/")

    def test_path_widens_to_workspace_root_when_unset(self):
        config = {"layout": {"workspace_root": "docs/"}}
        self.assertEqual(vl.resolve_what_l2_path(config), "docs/")

    def test_path_explicit_value_overrides_workspace_root(self):
        config = {
            "layout": {"workspace_root": "docs/"},
            "layers": {"what_l2": {"path": "docs/requirements/"}},
        }
        self.assertEqual(vl.resolve_what_l2_path(config), "docs/requirements/")

    def test_path_malformed_workspace_root_falls_back_to_pre_d21(self):
        config = {"layout": {"workspace_root": "."}}
        self.assertEqual(vl.resolve_what_l2_path(config), "docs/requirements/")

    # -- resolve_what_l2_exclude -------------------------------------------

    def test_exclude_default_is_empty(self):
        self.assertEqual(vl.resolve_what_l2_exclude({}), [])
        self.assertEqual(
            vl.resolve_what_l2_exclude({"layout": {"workspace_root": "docs/"}}), []
        )

    def test_exclude_returns_configured_list(self):
        config = {"layers": {"what_l2": {"exclude": ["contexts/", "inputs/", "cache/"]}}}
        self.assertEqual(
            vl.resolve_what_l2_exclude(config), ["contexts/", "inputs/", "cache/"]
        )

    # -- resolve_what_l2_index_path -----------------------------------------

    def test_index_path_default_without_config(self):
        self.assertEqual(vl.resolve_what_l2_index_path({}), "specs-out/l2_index.json")

    def test_index_path_re_roots_under_workspace_root(self):
        config = {"layout": {"workspace_root": "docs/"}}
        self.assertEqual(
            vl.resolve_what_l2_index_path(config), "docs/cache/specs-out/l2_index.json"
        )

    def test_index_path_explicit_value_wins(self):
        config = {
            "layout": {"workspace_root": "docs/"},
            "layers": {"what_l2": {"index_path": "specs-out/custom.json"}},
        }
        self.assertEqual(vl.resolve_what_l2_index_path(config), "specs-out/custom.json")


class TestWhatL2IndexPathExcluded(unittest.TestCase):
    """D21 §16.5 M3 invariant: what_l2.index_path must resolve under an
    excluded subtree of what_l2.path, if it resolves under what_l2.path at
    all."""

    def test_absent_config_is_a_no_op(self):
        # Control check: index_path (specs-out/...) is outside path
        # (docs/requirements/) entirely - nothing to exclude.
        self.assertEqual(vl.check_what_l2_index_path_excluded({}), [])

    def test_workspace_root_without_exclude_is_a_violation(self):
        # index_path defaults to docs/cache/specs-out/l2_index.json, which is
        # under what_l2.path (docs/), but what_l2.exclude is empty - M3
        # violated.
        config = {"layout": {"workspace_root": "docs/"}}
        problems = vl.check_what_l2_index_path_excluded(config)
        self.assertEqual(len(problems), 1)
        self.assertIn("M3", problems[0])

    def test_workspace_root_with_recommended_exclude_is_clean(self):
        config = {
            "layout": {"workspace_root": "docs/"},
            "layers": {"what_l2": {"exclude": ["contexts/", "inputs/", "cache/"]}},
        }
        self.assertEqual(vl.check_what_l2_index_path_excluded(config), [])

    def test_exclude_missing_cache_is_still_a_violation(self):
        config = {
            "layout": {"workspace_root": "docs/"},
            "layers": {"what_l2": {"exclude": ["contexts/", "inputs/"]}},
        }
        problems = vl.check_what_l2_index_path_excluded(config)
        self.assertEqual(len(problems), 1)
        self.assertIn("M3", problems[0])

    def test_narrowed_path_keeps_index_path_outside(self):
        # what_l2.path explicitly narrowed back to docs/requirements/ even
        # though workspace_root is set - index_path (docs/cache/...) isn't
        # under docs/requirements/, so no exclude entry is needed.
        config = {
            "layout": {"workspace_root": "docs/"},
            "layers": {"what_l2": {"path": "docs/requirements/"}},
        }
        self.assertEqual(vl.check_what_l2_index_path_excluded(config), [])


class TestWhatL2ExcludeTypos(unittest.TestCase):
    """D21 §16.11 S21 / round-2 L2: what_l2.exclude entries that don't
    prefix-match an existing subtree under what_l2.path are likely-typo'd."""

    def test_empty_exclude_is_a_no_op(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(vl.check_what_l2_exclude_typos(root, {}), [])

    def test_nonexistent_what_l2_path_is_a_no_op(self):
        # what_l2.path itself doesn't exist on disk - nothing to compare
        # against (S17-style: no retroactive checks).
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = {"layers": {"what_l2": {"exclude": ["cache/"]}}}
            self.assertEqual(vl.check_what_l2_exclude_typos(root, config), [])

    def test_exclude_matching_existing_subtree_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "cache").mkdir(parents=True)
            (root / "docs" / "contexts").mkdir(parents=True)
            config = {
                "layout": {"workspace_root": "docs/"},
                "layers": {"what_l2": {"exclude": ["contexts/", "cache/"]}},
            }
            self.assertEqual(vl.check_what_l2_exclude_typos(root, config), [])

    def test_exclude_entry_with_no_match_is_flagged(self):
        # 'cache/' exists and is correctly excluded; 'extra-stuff/' matches
        # nothing under docs/ - likely-typo'd (S21) or not-yet-created (S19);
        # either way, WARN.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "cache").mkdir(parents=True)
            config = {
                "layout": {"workspace_root": "docs/"},
                "layers": {"what_l2": {"exclude": ["cache/", "extra-stuff/"]}},
            }
            problems = vl.check_what_l2_exclude_typos(root, config)
            self.assertEqual(len(problems), 1)
            self.assertIn("extra-stuff/", problems[0])
            self.assertIn("S21", problems[0])

    def test_case_mismatch_is_flagged(self):
        # Configured 'cache/' but the actual on-disk directory is 'Cache/' -
        # a case mismatch that would fail open on case-sensitive Linux CI.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "Cache").mkdir(parents=True)
            config = {
                "layout": {"workspace_root": "docs/"},
                "layers": {"what_l2": {"exclude": ["cache/"]}},
            }
            problems = vl.check_what_l2_exclude_typos(root, config)
            self.assertEqual(len(problems), 1)
            self.assertIn("cache/", problems[0])


class TestFindMarkers(unittest.TestCase):
    def test_finds_marker_and_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root / "contexts" / ".layout-slots.yaml",
                "slots:\n  - slot: context_packages\n    kind: directory\n    schema_version: 1\n",
            )
            markers = vl.find_markers(root)
            self.assertEqual(len(markers), 1)
            matches = vl.find_slot_markers(markers, "context_packages")
            self.assertEqual(len(matches), 1)
            marker_path, entry = matches[0]
            self.assertEqual(marker_path.parent, root / "contexts")
            self.assertEqual(entry["kind"], "directory")

    def test_ignores_dotgit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root / ".git" / "modules" / ".layout-slots.yaml",
                "slots:\n  - slot: context_packages\n    kind: directory\n",
            )
            self.assertEqual(vl.find_markers(root), [])


class TestOwningSkillInstalled(unittest.TestCase):
    """D20 §15.8 S8 (Phase 2): _owning_skill_installed gates a slot's checks
    on whether its owning_skill is part of this project's installed skill
    set."""

    def test_no_skills_dir_is_a_no_op(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertTrue(vl._owning_skill_installed(root, "compiling-project-guidelines"))

    def test_skills_dir_without_owning_skill_is_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".github" / "skills" / "ult-context-generate").mkdir(parents=True)
            self.assertFalse(vl._owning_skill_installed(root, "compiling-project-guidelines"))
            self.assertTrue(vl._owning_skill_installed(root, "ult-context-generate"))


class TestValidate(unittest.TestCase):
    def test_not_initialized_is_clean_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            ok, report = vl.validate(tmp)
            self.assertTrue(ok)
            self.assertTrue(any("not initialized" in line for line in report))
            self.assertTrue(any("context_packages" in line and "using default" in line for line in report))

    def test_single_marker_directory_matches_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root / "contexts" / ".layout-slots.yaml",
                "slots:\n  - slot: context_packages\n    kind: directory\n    schema_version: 1\n",
            )
            ok, report = vl.validate(root)
            self.assertTrue(ok)
            self.assertFalse(any(line.startswith("FAIL") for line in report))

    def test_type_mismatch_is_a_failure(self):
        # Marker lives in a directory, but declares kind: file with a 'file:'
        # entry that is itself a directory on disk.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root / "contexts" / ".layout-slots.yaml",
                "slots:\n  - slot: context_packages\n    kind: file\n    file: pkg\n    schema_version: 1\n",
            )
            (root / "contexts" / "pkg").mkdir()
            ok, report = vl.validate(root)
            self.assertFalse(ok)
            self.assertTrue(any("type-consistency violation" in line for line in report))

    def test_two_markers_same_slot_is_bijectivity_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root / "contexts" / ".layout-slots.yaml",
                "slots:\n  - slot: context_packages\n    kind: directory\n    schema_version: 1\n",
            )
            write(
                root / "other-contexts" / ".layout-slots.yaml",
                "slots:\n  - slot: context_packages\n    kind: directory\n    schema_version: 1\n",
            )
            ok, report = vl.validate(root)
            self.assertFalse(ok)
            self.assertTrue(any("bijectivity violation (S15)" in line for line in report))

    def test_stale_index_is_non_blocking_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root / "my-contexts" / ".layout-slots.yaml",
                "slots:\n  - slot: context_packages\n    kind: directory\n    schema_version: 1\n",
            )
            write(
                root / "context-config.yaml",
                "project_layout:\n"
                "  version: 1\n"
                "  initialized: true\n"
                "  slots:\n"
                "    context_packages:\n"
                "      path: contexts/\n"
                "      kind: directory\n"
                "      owning_skill: ult-context-generate\n",
            )
            ok, report = vl.validate(root)
            self.assertTrue(ok)
            self.assertTrue(any("index is stale (S5)" in line for line in report))

    def test_windows_reserved_marker_path_is_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root / "output_docs" / "com1" / ".layout-slots.yaml",
                "slots:\n  - slot: context_packages\n    kind: directory\n    schema_version: 1\n",
            )
            ok, report = vl.validate(root)
            self.assertFalse(ok)
            self.assertTrue(any("reserved device name" in line for line in report))

    def test_backslash_in_project_layout_path_is_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root / "contexts" / ".layout-slots.yaml",
                "slots:\n  - slot: context_packages\n    kind: directory\n    schema_version: 1\n",
            )
            write(
                root / "context-config.yaml",
                "project_layout:\n"
                "  version: 1\n"
                "  initialized: true\n"
                "  slots:\n"
                "    context_packages:\n"
                "      path: contexts\\\\sub\n"
                "      kind: directory\n",
            )
            ok, report = vl.validate(root)
            self.assertFalse(ok)
            self.assertTrue(any("must be POSIX-style" in line for line in report))

    # -- D21 §16.2 / Phase 3a -------------------------------------------

    def test_workspace_root_dot_is_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "context-config.yaml", "layout:\n  workspace_root: .\n")
            ok, report = vl.validate(root)
            self.assertFalse(ok)
            self.assertTrue(any("S22" in line for line in report))

    def test_workspace_root_empty_string_is_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "context-config.yaml", "layout:\n  workspace_root: ''\n")
            ok, report = vl.validate(root)
            self.assertFalse(ok)
            self.assertTrue(any("S22" in line for line in report))

    def test_workspace_root_relative_default_used_in_info_message(self):
        # M4: the "no marker, using default '<path>'" note names the
        # resolved (workspace_root-relative) default, not the pre-D21 one.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "context-config.yaml", WORKSPACE_ROOT_DOCS_WITH_WHAT_L2_EXCLUDE)
            ok, report = vl.validate(root)
            self.assertTrue(ok)
            self.assertTrue(
                any(
                    "context_packages" in line and "using default 'docs/contexts/'" in line
                    for line in report
                )
            )

    def test_s18_partial_migration_is_a_non_blocking_warn(self):
        # Both the pre-D21 default ('contexts/') and the workspace_root-
        # relative default ('docs/contexts/') exist on disk, no marker.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "context-config.yaml", WORKSPACE_ROOT_DOCS_WITH_WHAT_L2_EXCLUDE)
            (root / "contexts").mkdir()
            (root / "docs" / "contexts").mkdir(parents=True)
            ok, report = vl.validate(root)
            self.assertTrue(ok)  # non-blocking
            self.assertTrue(
                any("S18" in line and "partial migration" in line for line in report)
            )

    def test_s18_not_flagged_when_only_resolved_location_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "context-config.yaml", WORKSPACE_ROOT_DOCS_WITH_WHAT_L2_EXCLUDE)
            (root / "docs" / "contexts").mkdir(parents=True)
            ok, report = vl.validate(root)
            self.assertTrue(ok)
            self.assertFalse(any("S18" in line for line in report))

    def test_s18_not_flagged_when_workspace_root_absent(self):
        # Only contexts/ exists, no workspace_root set - clean default,
        # not a "partial migration" (nothing to migrate to/from).
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "contexts").mkdir()
            ok, report = vl.validate(root)
            self.assertTrue(ok)
            self.assertFalse(any("S18" in line for line in report))

    def test_s16_marker_wins_regardless_of_workspace_root(self):
        # An existing marker resolves the slot normally even when
        # layout.workspace_root is set - workspace_root changes defaults
        # only, never an existing marker's location.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root / "my-contexts" / ".layout-slots.yaml",
                "slots:\n  - slot: context_packages\n    kind: directory\n    schema_version: 1\n",
            )
            write(root / "context-config.yaml", WORKSPACE_ROOT_DOCS_WITH_WHAT_L2_EXCLUDE)
            ok, report = vl.validate(root)
            self.assertTrue(ok)
            self.assertFalse(any("context_packages' has no marker" in line for line in report))

    # -- D21 §16.4 / Phase 3b (Gap-B new slots) --------------------------

    def test_not_initialized_reports_all_registered_slots(self):
        with tempfile.TemporaryDirectory() as tmp:
            ok, report = vl.validate(tmp)
            self.assertTrue(ok)
            self.assertTrue(
                any("plans_output" in line and "using default 'docs/superpowers/plans/'" in line for line in report)
            )
            self.assertTrue(
                any("brainstorm_output" in line and "using default 'docs/superpowers/specs/'" in line for line in report)
            )

    def test_brainstorm_output_workspace_root_relative_default_used_in_info_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "context-config.yaml", WORKSPACE_ROOT_DOCS_WITH_WHAT_L2_EXCLUDE)
            ok, report = vl.validate(root)
            self.assertTrue(ok)
            self.assertTrue(
                any(
                    "brainstorm_output" in line and "using default 'docs/outputs/specs/'" in line
                    for line in report
                )
            )

    def test_plans_output_marker_resolves_to_marked_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root / "my-plans" / ".layout-slots.yaml",
                "slots:\n  - slot: plans_output\n    kind: directory\n    schema_version: 1\n",
            )
            ok, report = vl.validate(root)
            self.assertTrue(ok)
            self.assertFalse(any("plans_output' has no marker" in line for line in report))
            # The other two slots are still unmarked and report their defaults.
            self.assertTrue(any("context_packages" in line and "using default" in line for line in report))
            self.assertTrue(any("brainstorm_output" in line and "using default" in line for line in report))

    def test_cross_slot_bijectivity_violation(self):
        # Two different slots both marked at the same directory.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root / "shared" / ".layout-slots.yaml",
                "slots:\n"
                "  - slot: context_packages\n    kind: directory\n    schema_version: 1\n"
                "  - slot: plans_output\n    kind: directory\n    schema_version: 1\n",
            )
            ok, report = vl.validate(root)
            self.assertFalse(ok)
            self.assertTrue(any("bijectivity violation" in line for line in report))

    # -- D20 §15.11 / Phase 2 (compiled_guidelines, user_stories_output,
    # security_docs, security_report, project_plan_docs) -----------------

    def test_not_initialized_reports_phase2_slots(self):
        with tempfile.TemporaryDirectory() as tmp:
            ok, report = vl.validate(tmp)
            self.assertTrue(ok)
            self.assertTrue(
                any(
                    "compiled_guidelines" in line
                    and "using default 'starter_kit/project_guidelines/COMPILED-GUIDELINES.md'" in line
                    for line in report
                )
            )
            self.assertTrue(
                any("user_stories_output" in line and "using default 'output_docs/user-stories/'" in line for line in report)
            )
            self.assertTrue(
                any("security_docs" in line and "using default 'output_docs/security_docs/'" in line for line in report)
            )
            self.assertTrue(
                any("security_report" in line and "using default 'output_docs/security_report/'" in line for line in report)
            )
            self.assertTrue(
                any("project_plan_docs" in line and "using default 'output_docs/project_plan_docs/'" in line for line in report)
            )

    def test_compiled_guidelines_kind_file_marker_resolves(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root / "starter_kit" / "project_guidelines" / ".layout-slots.yaml",
                "slots:\n  - slot: compiled_guidelines\n    kind: file\n    file: COMPILED-GUIDELINES.md\n    schema_version: 2\n",
            )
            write(root / "starter_kit" / "project_guidelines" / "COMPILED-GUIDELINES.md", "# Guidelines\n")
            ok, report = vl.validate(root)
            self.assertTrue(ok)
            self.assertFalse(any(line.startswith("FAIL") for line in report))
            self.assertFalse(any("compiled_guidelines' has no marker" in line for line in report))

    def test_compiled_guidelines_type_mismatch_when_directory(self):
        # Marker declares kind: file, but COMPILED-GUIDELINES.md is itself a
        # directory on disk - type-consistency violation.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root / "starter_kit" / "project_guidelines" / ".layout-slots.yaml",
                "slots:\n  - slot: compiled_guidelines\n    kind: file\n    file: COMPILED-GUIDELINES.md\n    schema_version: 2\n",
            )
            (root / "starter_kit" / "project_guidelines" / "COMPILED-GUIDELINES.md").mkdir(parents=True)
            ok, report = vl.validate(root)
            self.assertFalse(ok)
            self.assertTrue(any("type-consistency violation" in line for line in report))

    def test_user_stories_output_marker_resolves_to_marked_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root / "my-stories" / ".layout-slots.yaml",
                "slots:\n  - slot: user_stories_output\n    kind: directory\n    schema_version: 2\n",
            )
            ok, report = vl.validate(root)
            self.assertTrue(ok)
            self.assertFalse(any("user_stories_output' has no marker" in line for line in report))

    def test_phase2_workspace_root_relative_defaults_used_in_info_messages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "context-config.yaml", WORKSPACE_ROOT_DOCS_WITH_WHAT_L2_EXCLUDE)
            ok, report = vl.validate(root)
            self.assertTrue(ok)
            self.assertTrue(
                any(
                    "compiled_guidelines" in line
                    and "using default 'docs/cache/project-guidelines/COMPILED-GUIDELINES.md'" in line
                    for line in report
                )
            )
            self.assertTrue(
                any("user_stories_output" in line and "using default 'docs/outputs/user-stories/'" in line for line in report)
            )
            self.assertTrue(
                any("security_docs" in line and "using default 'docs/outputs/security_docs/'" in line for line in report)
            )
            self.assertTrue(
                any("security_report" in line and "using default 'docs/outputs/security_report/'" in line for line in report)
            )
            self.assertTrue(
                any("project_plan_docs" in line and "using default 'docs/outputs/project_plan_docs/'" in line for line in report)
            )

    # -- D20 §15.8 / Phase 2 (S8 partial-install gate) --------------------

    def test_s8_missing_owning_skill_dir_skips_slot_entirely(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".github" / "skills" / "ult-context-generate").mkdir(parents=True)
            ok, report = vl.validate(root)
            self.assertTrue(ok)
            # context_packages' owning skill is installed -> still reported.
            self.assertTrue(any("context_packages" in line and "using default" in line for line in report))
            # No other owning skill is installed -> every other slot skipped.
            for slot in (
                "plans_output", "brainstorm_output", "compiled_guidelines",
                "user_stories_output", "security_docs", "security_report",
                "project_plan_docs",
            ):
                self.assertFalse(any(slot in line for line in report), f"{slot} should be skipped (S8)")

    def test_s8_all_owning_skills_present_reports_everything(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for skill in (
                "ult-context-generate", "writing-plans", "brainstorming",
                "compiling-project-guidelines", "example-consumer",
                "sec-threat-model", "security-test-report", "pm-project-plan",
            ):
                (root / ".github" / "skills" / skill).mkdir(parents=True)
            ok, report = vl.validate(root)
            self.assertTrue(ok)
            for slot in vl.SLOT_REGISTRY:
                self.assertTrue(any(slot in line for line in report), f"{slot} should be reported")

    # -- D21 §16.5/§16.11 / Phase 3c (what_l2.exclude / index_path) ------

    def test_what_l2_checks_are_a_no_op_without_workspace_root(self):
        # Control check: no context-config.yaml at all -> neither the M3
        # (index_path exclusion) nor the S21 (exclude typo) check fires.
        with tempfile.TemporaryDirectory() as tmp:
            ok, report = vl.validate(tmp)
            self.assertTrue(ok)
            self.assertFalse(any("M3" in line for line in report))
            self.assertFalse(any("S21" in line for line in report))

    def test_workspace_root_without_what_l2_exclude_fails_m3(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "context-config.yaml", "layout:\n  workspace_root: docs/\n")
            ok, report = vl.validate(root)
            self.assertFalse(ok)
            self.assertTrue(any("M3" in line and "FAIL" in line for line in report))

    def test_workspace_root_with_recommended_exclude_passes_m3(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root / "context-config.yaml",
                "layout:\n"
                "  workspace_root: docs/\n"
                "layers:\n"
                "  what_l2:\n"
                "    exclude:\n"
                "      - contexts/\n"
                "      - inputs/\n"
                "      - cache/\n",
            )
            ok, report = vl.validate(root)
            self.assertTrue(ok)
            self.assertFalse(any("M3" in line for line in report))

    def test_what_l2_exclude_typo_is_a_non_blocking_warn(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "cache").mkdir(parents=True)
            (root / "docs" / "contexts").mkdir(parents=True)
            (root / "docs" / "inputs").mkdir(parents=True)
            write(
                root / "context-config.yaml",
                "layout:\n"
                "  workspace_root: docs/\n"
                "layers:\n"
                "  what_l2:\n"
                "    exclude:\n"
                "      - contexts/\n"
                "      - inputs/\n"
                "      - cache/\n"
                "      - extra-stuff/\n",
            )
            ok, report = vl.validate(root)
            self.assertTrue(ok)  # non-blocking
            self.assertTrue(any("S21" in line and "WARN" in line for line in report))


class TestRegistryConsistency(unittest.TestCase):
    """D21 §16.8, Phase 3e: layout-slots-registry.yaml's `slots:` entries with
    project_layout_slot: true must match SLOT_REGISTRY's keys exactly. The
    file is library-level-only (never copied into consuming projects), so an
    absent file is always a no-op."""

    def _registry_text(self, slot_ids, extra_ids=()):
        lines = ["slots:\n"]
        for slot_id in list(slot_ids) + list(extra_ids):
            lines.append(f"  - id: {slot_id}\n")
            lines.append("    project_layout_slot: true\n")
        return "".join(lines)

    def test_absent_file_is_a_no_op(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(vl.check_registry_consistency(Path(tmp)), [])

    def test_matching_registry_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "layout-slots-registry.yaml", self._registry_text(vl.SLOT_REGISTRY.keys()))
            self.assertEqual(vl.check_registry_consistency(root), [])

    def test_missing_slot_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            slot_ids = list(vl.SLOT_REGISTRY.keys())
            write(root / "layout-slots-registry.yaml", self._registry_text(slot_ids[1:]))
            problems = vl.check_registry_consistency(root)
            self.assertEqual(len(problems), 1)
            self.assertIn(slot_ids[0], problems[0])
            self.assertIn("registry/code drift", problems[0])

    def test_extra_slot_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(
                root / "layout-slots-registry.yaml",
                self._registry_text(vl.SLOT_REGISTRY.keys(), extra_ids=["made_up_slot"]),
            )
            problems = vl.check_registry_consistency(root)
            self.assertEqual(len(problems), 1)
            self.assertIn("made_up_slot", problems[0])
            self.assertIn("registry/code drift", problems[0])

    def test_non_slot_entries_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            text = self._registry_text(vl.SLOT_REGISTRY.keys())
            text += (
                "config_keys:\n"
                "  - id: what_l2_path\n"
                "    project_layout_slot: false\n"
            )
            write(root / "layout-slots-registry.yaml", text)
            self.assertEqual(vl.check_registry_consistency(root), [])

    def test_validate_fails_on_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            slot_ids = list(vl.SLOT_REGISTRY.keys())
            write(root / "layout-slots-registry.yaml", self._registry_text(slot_ids[1:]))
            ok, report = vl.validate(root)
            self.assertFalse(ok)
            self.assertTrue(
                any("registry/code drift" in line and line.startswith("FAIL") for line in report)
            )

    def test_validate_passes_when_registry_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "layout-slots-registry.yaml", self._registry_text(vl.SLOT_REGISTRY.keys()))
            ok, report = vl.validate(root)
            self.assertTrue(ok)
            self.assertFalse(any("registry/code drift" in line for line in report))

    def test_real_registry_file_is_consistent_with_slot_registry(self):
        # The actual repo-root layout-slots-registry.yaml (§16.8)
        # must stay in sync with SLOT_REGISTRY above - this is the direct
        # regression check for that.
        repo_root = Path(__file__).resolve().parents[5]
        registry_path = repo_root / "layout-slots-registry.yaml"
        self.assertTrue(registry_path.exists(), "layout-slots-registry.yaml is missing from the repo root")
        self.assertEqual(vl.check_registry_consistency(repo_root), [])


class TestGitHistoryCheck(unittest.TestCase):
    def _git_repo(self, tmp):
        root = Path(tmp)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
        return root

    def test_no_history_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._git_repo(tmp)
            write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True)
            self.assertIsNone(vl.check_git_history(root, {}))

    def test_vanished_project_layout_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._git_repo(tmp)
            write(
                root / "context-config.yaml",
                "project_layout:\n  version: 1\n  initialized: true\n",
            )
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "add project_layout"], cwd=root, check=True)

            write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "remove project_layout"], cwd=root, check=True)

            config = vl.load_yaml_file(root / "context-config.yaml")
            result = vl.check_git_history(root, config)
            self.assertIsNotNone(result)
            self.assertIn("S4", result)


class TestMain(unittest.TestCase):
    def test_validate_clean_repo_exits_zero(self):
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = vl.main(["--validate", tmp])
            self.assertEqual(rc, 0)
            self.assertIn("PASS", buf.getvalue())

    def test_no_validate_flag_returns_usage_error(self):
        self.assertEqual(vl.main([tempfile.gettempdir()]), 2)


if __name__ == "__main__":
    unittest.main()
