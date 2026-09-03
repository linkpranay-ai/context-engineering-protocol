"""Regression suite for validate_layout.py (D20 v2 §15.9, Phase 1).

Stdlib unittest only -- no pytest dependency, so this stays vendorable along
with validate_layout.py itself. Run with:

    python -m unittest discover -s scripts/tests -v
"""

import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path, PureWindowsPath

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

    def test_posix_absolute_path_flagged(self):
        problems = vl.check_path_wellformedness(Path("/abs/posix"))
        self.assertTrue(any("absolute path" in p for p in problems))

    def test_windows_drive_absolute_path_flagged(self):
        problems = vl.check_path_wellformedness(PureWindowsPath("C:/OUTSIDE"))
        self.assertTrue(any("absolute path" in p for p in problems))

    def test_unc_path_flagged(self):
        problems = vl.check_path_wellformedness(PureWindowsPath("//server/share/x"))
        self.assertTrue(any("absolute path" in p for p in problems))

    def test_relative_path_with_drive_letter_like_segment_still_ok(self):
        # A relative path segment that merely contains a colon-free, non-drive
        # string must not be caught by the absolute-path short-circuit.
        self.assertEqual(vl.check_path_wellformedness(Path("docs/x")), [])


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
        self.assertEqual(vl.resolve_default("plans_output", {}), "output_docs/plans/")

    def test_plans_output_workspace_root_relative_default(self):
        config = {"layout": {"workspace_root": "docs/"}}
        self.assertEqual(vl.resolve_default("plans_output", config), "docs/outputs/plans/")

    def test_brainstorm_output_pre_d21_default_without_config(self):
        self.assertEqual(vl.resolve_default("brainstorm_output", {}), "output_docs/brainstorm/")

    def test_brainstorm_output_workspace_root_relative_default(self):
        config = {"layout": {"workspace_root": "docs/"}}
        self.assertEqual(vl.resolve_default("brainstorm_output", config), "docs/outputs/brainstorm/")

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

    # -- resolve_what_l2_include_roots --------------------------------------

    def test_include_roots_default_is_empty(self):
        self.assertEqual(vl.resolve_what_l2_include_roots({}), [])
        self.assertEqual(
            vl.resolve_what_l2_include_roots({"layers": {"what_l2": {}}}), []
        )

    def test_include_roots_non_list_value_is_ignored(self):
        config = {"layers": {"what_l2": {"include_roots": "specs/legacy/"}}}
        self.assertEqual(vl.resolve_what_l2_include_roots(config), [])

    def test_include_roots_returns_configured_list(self):
        config = {
            "layers": {"what_l2": {"include_roots": ["specs/legacy/", "specs/archive/"]}}
        }
        self.assertEqual(
            vl.resolve_what_l2_include_roots(config),
            ["specs/legacy/", "specs/archive/"],
        )

    def test_include_roots_drops_non_string_entries(self):
        config = {"layers": {"what_l2": {"include_roots": ["specs/legacy/", 3, None]}}}
        self.assertEqual(vl.resolve_what_l2_include_roots(config), ["specs/legacy/"])

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


class TestHowL2WhatL1HowL1Resolution(unittest.TestCase):
    """D23 §17.8: resolve_how_l2_path/resolve_what_l1_*/
    resolve_how_l1_* - unlike what_l2, none of these widen to workspace_root
    (§16.5's widening is What-L2-specific)."""

    def test_how_l2_path_default_without_config(self):
        self.assertEqual(vl.resolve_how_l2_path({}), "org/")

    def test_how_l2_path_explicit_config_value_wins(self):
        config = {"how_dimension": {"how_l2": {"path": "conventions/"}}}
        self.assertEqual(vl.resolve_how_l2_path(config), "conventions/")

    def test_what_l1_path_absent_without_config(self):
        self.assertIsNone(vl.resolve_what_l1_path({}))

    def test_what_l1_path_explicit_config_value(self):
        config = {"layers": {"what_l1": {"path": "specs/external/"}}}
        self.assertEqual(vl.resolve_what_l1_path(config), "specs/external/")

    def test_what_l1_enabled_defaults_to_false(self):
        self.assertFalse(vl.resolve_what_l1_enabled({}))

    def test_what_l1_enabled_explicit_true(self):
        config = {"layers": {"what_l1": {"enabled": True}}}
        self.assertTrue(vl.resolve_what_l1_enabled(config))

    def test_how_l1_path_absent_without_config(self):
        self.assertIsNone(vl.resolve_how_l1_path({}))

    def test_how_l1_path_explicit_config_value(self):
        config = {"how_dimension": {"how_l1": {"path": "org/process-standards/"}}}
        self.assertEqual(vl.resolve_how_l1_path(config), "org/process-standards/")

    def test_how_l1_enabled_defaults_to_false(self):
        self.assertFalse(vl.resolve_how_l1_enabled({}))

    def test_how_l1_enabled_explicit_true(self):
        config = {"how_dimension": {"how_l1": {"enabled": True}}}
        self.assertTrue(vl.resolve_how_l1_enabled(config))


class TestLayerPathsPopulated(unittest.TestCase):
    """D23 §17.8 (S28): WARN if an enabled layer's
    resolved path doesn't exist or contains no files. What-L2/How-L2 are
    always checked; What-L1/How-L1 only when their own enabled: true is set -
    a disabled opt-in layer is never checked at all."""

    def test_what_l2_missing_default_path_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            problems = vl.check_layer_paths_populated(root, {})
            what_l2_problems = [p for p in problems if "what_l2" in p]
            self.assertEqual(len(what_l2_problems), 1)
            self.assertIn("S28", what_l2_problems[0])

    def test_how_l2_missing_default_path_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            problems = vl.check_layer_paths_populated(root, {})
            how_l2_problems = [p for p in problems if "how_l2" in p]
            self.assertEqual(len(how_l2_problems), 1)
            self.assertIn("S28", how_l2_problems[0])

    def test_what_l2_and_how_l2_populated_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "docs" / "requirements" / "reqs.md", "# reqs\n")
            write(root / "org" / "conventions.md", "# conventions\n")
            self.assertEqual(vl.check_layer_paths_populated(root, {}), [])

    def test_what_l2_empty_directory_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "requirements").mkdir(parents=True)
            write(root / "org" / "conventions.md", "# conventions\n")
            problems = vl.check_layer_paths_populated(root, {})
            self.assertEqual(len(problems), 1)
            self.assertIn("what_l2", problems[0])
            self.assertIn("empty", problems[0])

    def test_disabled_what_l1_with_no_path_is_not_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "docs" / "requirements" / "reqs.md", "# reqs\n")
            write(root / "org" / "conventions.md", "# conventions\n")
            config = {"layers": {"what_l1": {"enabled": False}}}
            self.assertEqual(vl.check_layer_paths_populated(root, config), [])

    def test_disabled_what_l1_with_nonexistent_path_is_not_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "docs" / "requirements" / "reqs.md", "# reqs\n")
            write(root / "org" / "conventions.md", "# conventions\n")
            config = {
                "layers": {"what_l1": {"enabled": False, "path": "specs/external/"}},
            }
            self.assertEqual(vl.check_layer_paths_populated(root, config), [])

    def test_enabled_what_l1_missing_path_key_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "docs" / "requirements" / "reqs.md", "# reqs\n")
            write(root / "org" / "conventions.md", "# conventions\n")
            config = {"layers": {"what_l1": {"enabled": True}}}
            problems = vl.check_layer_paths_populated(root, config)
            self.assertEqual(len(problems), 1)
            self.assertIn("what_l1", problems[0])
            self.assertIn("no path is configured", problems[0])

    def test_enabled_what_l1_nonexistent_path_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "docs" / "requirements" / "reqs.md", "# reqs\n")
            write(root / "org" / "conventions.md", "# conventions\n")
            config = {
                "layers": {"what_l1": {"enabled": True, "path": "specs/external/"}},
            }
            problems = vl.check_layer_paths_populated(root, config)
            self.assertEqual(len(problems), 1)
            self.assertIn("what_l1.path", problems[0])
            self.assertIn("does not exist", problems[0])

    def test_enabled_what_l1_populated_path_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "docs" / "requirements" / "reqs.md", "# reqs\n")
            write(root / "org" / "conventions.md", "# conventions\n")
            write(root / "specs" / "external" / "rfc.md", "# rfc\n")
            config = {
                "layers": {"what_l1": {"enabled": True, "path": "specs/external/"}},
            }
            self.assertEqual(vl.check_layer_paths_populated(root, config), [])

    def test_disabled_how_l1_with_no_path_is_not_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "docs" / "requirements" / "reqs.md", "# reqs\n")
            write(root / "org" / "conventions.md", "# conventions\n")
            config = {"how_dimension": {"how_l1": {"enabled": False}}}
            self.assertEqual(vl.check_layer_paths_populated(root, config), [])

    def test_enabled_how_l1_nonexistent_path_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "docs" / "requirements" / "reqs.md", "# reqs\n")
            write(root / "org" / "conventions.md", "# conventions\n")
            config = {
                "how_dimension": {
                    "how_l1": {"enabled": True, "path": "org/process-standards/"}
                },
            }
            problems = vl.check_layer_paths_populated(root, config)
            self.assertEqual(len(problems), 1)
            self.assertIn("how_l1.path", problems[0])


class TestLayerCandidatePathsPopulated(unittest.TestCase):
    """D23 §17.8 C-2 addendum (per-candidate extension, second adversarial
    review): once `include_roots` entries exist, WARN if any of them
    individually doesn't exist or is empty - the primary-path check above
    never inspects them. `exclude` entries are out of scope for this
    function (covered solely by check_what_l2_exclude_typos)."""

    def test_no_include_roots_configured_is_a_no_op(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(vl.check_layer_candidate_paths_populated(root, {}), [])

    def test_single_populated_entry_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "specs" / "legacy" / "old.md", "# old\n")
            config = {"layers": {"what_l2": {"include_roots": ["specs/legacy/"]}}}
            self.assertEqual(vl.check_layer_candidate_paths_populated(root, config), [])

    def test_missing_entry_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = {"layers": {"what_l2": {"include_roots": ["specs/legacy/"]}}}
            problems = vl.check_layer_candidate_paths_populated(root, config)
            self.assertEqual(len(problems), 1)
            self.assertIn("include_roots[0]", problems[0])
            self.assertIn("does not exist", problems[0])

    def test_empty_entry_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "specs" / "legacy").mkdir(parents=True)
            config = {"layers": {"what_l2": {"include_roots": ["specs/legacy/"]}}}
            problems = vl.check_layer_candidate_paths_populated(root, config)
            self.assertEqual(len(problems), 1)
            self.assertIn("include_roots[0]", problems[0])
            self.assertIn("empty", problems[0])

    def test_multiple_entries_only_bad_one_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "specs" / "legacy" / "old.md", "# old\n")
            config = {
                "layers": {
                    "what_l2": {
                        "include_roots": ["specs/legacy/", "specs/archive/"]
                    }
                }
            }
            problems = vl.check_layer_candidate_paths_populated(root, config)
            self.assertEqual(len(problems), 1)
            self.assertIn("include_roots[1]", problems[0])
            self.assertIn("specs/archive/", problems[0])

    def test_exclude_entries_never_flagged_by_this_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = {"layers": {"what_l2": {"exclude": ["nonexistent/"]}}}
            self.assertEqual(vl.check_layer_candidate_paths_populated(root, config), [])


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
                any("plans_output" in line and "using default 'output_docs/plans/'" in line for line in report)
            )
            self.assertTrue(
                any("brainstorm_output" in line and "using default 'output_docs/brainstorm/'" in line for line in report)
            )

    def test_brainstorm_output_workspace_root_relative_default_used_in_info_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "context-config.yaml", WORKSPACE_ROOT_DOCS_WITH_WHAT_L2_EXCLUDE)
            ok, report = vl.validate(root)
            self.assertTrue(ok)
            self.assertTrue(
                any(
                    "brainstorm_output" in line and "using default 'docs/outputs/brainstorm/'" in line
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
                "ult-context-generate", "example-plan-writer", "example-brainstorm-writer",
                "compiling-project-guidelines", "example-consumer",
                "example-threat-modeler", "example-report-writer", "example-project-planner",
                "ult-institutional-memory-distill", "ult-autoscaffold-content",
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


class TestSkillMdSlotRegistryTableConsistency(unittest.TestCase):
    """Regression guard for the documented `init` walkthrough silently
    covering fewer slots than SLOT_REGISTRY: a slot added to SLOT_REGISTRY
    without a matching row in SKILL.md's own "## Slot registry" markdown
    table means `init`'s own instructions never mention it, so a
    fully-compliant documented `init` run leaves it unregistered even though
    it's a real, shipped slot. Parses the table directly out of SKILL.md
    rather than trusting prose elsewhere in the file (e.g. the "Eleven slots
    are registered" sentence), since prose can drift out of sync with the
    table just as easily as the table can drift from the code."""

    def _table_slot_keys(self):
        skill_md = Path(__file__).resolve().parents[2] / "SKILL.md"
        text = skill_md.read_text(encoding="utf-8")
        section_start = text.index("## Slot registry")
        section_end = text.index("\n## ", section_start + 1)
        section = text.splitlines()[
            text[:section_start].count("\n"):text[:section_end].count("\n")
        ]
        keys = []
        for line in section:
            m = re.match(r"\|\s*`([a-z_]+)`\s*\|", line)
            if m:
                keys.append(m.group(1))
        return keys

    def test_skill_md_exists(self):
        skill_md = Path(__file__).resolve().parents[2] / "SKILL.md"
        self.assertTrue(skill_md.exists(), "SKILL.md is missing from the ult-repo-layout skill directory")

    def test_table_has_no_duplicate_or_unknown_looking_rows(self):
        keys = self._table_slot_keys()
        self.assertTrue(keys, "found no slot rows in SKILL.md's Slot registry table - table format may have changed")
        self.assertEqual(len(keys), len(set(keys)), "SKILL.md's Slot registry table lists the same slot key twice")

    def test_table_matches_slot_registry_exactly(self):
        # The direct regression check: every SLOT_REGISTRY key must have a
        # row in SKILL.md's table, and vice versa. This is what would have
        # caught decision_ledger/autoscaffold_content_state/
        # autoscaffold_content_index being added to SLOT_REGISTRY without a
        # corresponding table row (and without updating init's "all N slots"
        # walkthrough text alongside it).
        table_keys = set(self._table_slot_keys())
        code_keys = set(vl.SLOT_REGISTRY.keys())
        missing_from_docs = code_keys - table_keys
        extra_in_docs = table_keys - code_keys
        self.assertEqual(
            missing_from_docs, set(),
            f"SLOT_REGISTRY has slot(s) {sorted(missing_from_docs)} with no row in "
            f"SKILL.md's Slot registry table - init's documented walkthrough will "
            f"never mention them (doc/code drift).",
        )
        self.assertEqual(
            extra_in_docs, set(),
            f"SKILL.md's Slot registry table lists slot(s) {sorted(extra_in_docs)} "
            f"that SLOT_REGISTRY doesn't have (doc/code drift).",
        )


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


class TestRunInit(unittest.TestCase):
    """run_init() backs the mechanical half of SKILL.md's `init` mode. See
    SKILL.md's own note that steps 1-3 and 5 are backed by
    `validate_layout.py --init`."""

    def _install_skills(self, root, *names):
        for name in names:
            (root / ".github" / "skills" / name).mkdir(parents=True, exist_ok=True)

    def test_missing_config_yaml_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install_skills(root, "ult-context-generate")
            code, messages = vl.run_init(root)
            self.assertEqual(code, 1)
            self.assertTrue(any("context-config.yaml not found" in m for m in messages))

    def test_already_initialized_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install_skills(root, "ult-context-generate")
            write(
                root / "context-config.yaml",
                "project_layout:\n  version: 1\n  initialized: true\n",
            )
            code, messages = vl.run_init(root)
            self.assertEqual(code, 1)
            self.assertTrue(any("Already initialized" in m for m in messages))
            # The refusal has to point at the one thing a repeat call can
            # still do, or --ci-hook looks unreachable after the first init.
            self.assertTrue(any("--ci-hook" in m for m in messages))

    def test_repeat_init_with_ci_hook_scaffolds_hook_on_initialized_repo(self):
        # The pre-commit hook is opt-in, so an adopter who ran init once
        # without it has no other way to ask for it later. A repeat
        # --init --ci-hook must scaffold the hook and succeed rather than
        # refuse outright - and must leave project_layout exactly as the
        # first init wrote it.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install_skills(root, "ult-context-generate")
            write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")
            (root / ".git" / "hooks").mkdir(parents=True)

            first_code, _first_messages = vl.run_init(root)
            self.assertEqual(first_code, 0)
            hook = root / ".git" / "hooks" / "pre-commit"
            self.assertFalse(hook.exists())
            after_first_init = (root / "context-config.yaml").read_text(encoding="utf-8")

            code, messages = vl.run_init(root, ci_hook=True)
            self.assertEqual(code, 0, messages)
            self.assertTrue(hook.exists())
            self.assertIn("validate_layout.py --validate", hook.read_text(encoding="utf-8"))
            self.assertTrue(any("Already initialized" in m for m in messages))
            self.assertTrue(any("Scaffolded pre-commit hook" in m for m in messages))
            self.assertEqual(
                (root / "context-config.yaml").read_text(encoding="utf-8"),
                after_first_init,
            )

    def test_repeat_init_with_ci_hook_never_overwrites_existing_hook(self):
        # The already-initialized branch calls the same scaffolding helper
        # a fresh init does, so its never-overwrite rule has to hold here
        # too - and a skipped hook is still a success, not a refusal.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install_skills(root, "ult-context-generate")
            write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")
            hooks_dir = root / ".git" / "hooks"
            hooks_dir.mkdir(parents=True)

            self.assertEqual(vl.run_init(root)[0], 0)
            write(hooks_dir / "pre-commit", "#!/bin/sh\necho custom hook\n")

            code, messages = vl.run_init(root, ci_hook=True)
            self.assertEqual(code, 0, messages)
            self.assertIn("custom hook", (hooks_dir / "pre-commit").read_text(encoding="utf-8"))
            self.assertTrue(any("already exists" in m for m in messages))

    def test_zero_installed_skills_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".github" / "skills").mkdir(parents=True)
            write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")
            code, messages = vl.run_init(root)
            self.assertEqual(code, 1)
            self.assertTrue(any("nothing to initialize" in m for m in messages))

    def test_partial_install_gate_scaffolds_only_installed_slots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install_skills(root, "ult-context-generate", "ult-autoscaffold-content")
            write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")

            code, messages = vl.run_init(root)
            self.assertEqual(code, 0, messages)

            # context_packages (ult-context-generate, directory kind) scaffolded.
            self.assertTrue((root / "contexts").is_dir())
            self.assertTrue((root / "contexts" / ".layout-slots.yaml").exists())

            # autoscaffold_content_state + autoscaffold_content_index
            # (ult-autoscaffold-content, both file kind) share one directory
            # and therefore one marker file. The artifacts themselves are
            # derived/regenerable (only ever written by scaffold_state.py),
            # so init scaffolds the containing directory + marker only, not
            # the files - they don't exist yet.
            shared_dir = root / "starter_kit" / "autoscaffold-content"
            self.assertTrue(shared_dir.is_dir())
            self.assertFalse((shared_dir / "TRIAGE-STATE.json").exists())
            self.assertFalse((shared_dir / "CEP-INDEX.md").exists())
            marker = vl.load_yaml_file(shared_dir / ".layout-slots.yaml")
            marker_slots = {e["slot"] for e in marker["slots"]}
            self.assertEqual(
                marker_slots, {"autoscaffold_content_state", "autoscaffold_content_index"}
            )

            # decision_ledger's owning skill (ult-institutional-memory-distill)
            # was never installed - nothing scaffolded for it.
            self.assertFalse((root / "starter_kit" / "decision_ledger").exists())

    def test_marker_round_trips_for_directory_and_file_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install_skills(root, "ult-context-generate", "ult-institutional-memory-distill")
            write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")
            code, _ = vl.run_init(root)
            self.assertEqual(code, 0)

            markers = vl.find_markers(root)
            dir_hits = vl.find_slot_markers(markers, "context_packages")
            self.assertEqual(len(dir_hits), 1)
            marker_path, entry = dir_hits[0]
            resolved, kind = vl.resolved_path_for_marker(
                marker_path, entry, vl.SLOT_REGISTRY["context_packages"], root
            )
            self.assertEqual(resolved, Path("contexts"))
            self.assertEqual(kind, "directory")

            file_hits = vl.find_slot_markers(markers, "decision_ledger")
            self.assertEqual(len(file_hits), 1)
            marker_path, entry = file_hits[0]
            resolved, kind = vl.resolved_path_for_marker(
                marker_path, entry, vl.SLOT_REGISTRY["decision_ledger"], root
            )
            self.assertEqual(resolved, Path("starter_kit/decision_ledger/DECISION-LEDGER.json"))
            self.assertEqual(kind, "file")

    def test_project_layout_block_correctness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install_skills(root, "ult-context-generate")
            write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")
            code, _ = vl.run_init(root)
            self.assertEqual(code, 0)

            config = vl.load_yaml_file(root / "context-config.yaml")
            layout = config["project_layout"]
            self.assertEqual(layout["version"], 1)
            self.assertTrue(layout["initialized"])
            slot = layout["slots"]["context_packages"]
            self.assertEqual(slot["path"], "contexts/")
            self.assertEqual(slot["kind"], "directory")
            self.assertEqual(slot["owning_skill"], "ult-context-generate")

    def test_workspace_root_success_and_exclude_triad_dedup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install_skills(root, "ult-context-generate")
            write(
                root / "context-config.yaml",
                "cache:\n  product_context_path: contexts/\n"
                "layers:\n  what_l2:\n    exclude:\n      - contexts/\n",
            )
            code, messages = vl.run_init(root, workspace_root="docs/")
            self.assertEqual(code, 0, messages)

            config = vl.load_yaml_file(root / "context-config.yaml")
            self.assertEqual(vl._normalize_workspace_root(config), "docs")
            exclude = vl.resolve_what_l2_exclude(config)
            self.assertEqual(exclude.count("contexts/"), 1)
            self.assertIn("inputs/", exclude)
            self.assertIn("cache/", exclude)
            # workspace_root-relative default, not the pre-D21 "contexts/" default.
            self.assertEqual(config["project_layout"]["slots"]["context_packages"]["path"], "docs/contexts/")

    def test_workspace_root_already_set_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install_skills(root, "ult-context-generate")
            write(root / "context-config.yaml", "layout:\n  workspace_root: docs/\n")
            code, messages = vl.run_init(root, workspace_root="other/")
            self.assertEqual(code, 1)
            self.assertTrue(any("already set" in m for m in messages))

    def test_workspace_root_invalid_value_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install_skills(root, "ult-context-generate")
            write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")
            code, messages = vl.run_init(root, workspace_root=".")
            self.assertEqual(code, 1)
            self.assertTrue(any("S22" in m for m in messages))

    def test_workspace_root_absolute_value_refuses(self):
        # An absolute --workspace-root must be rejected before any scaffold
        # target is computed - repo_root / <absolute rel> silently discards
        # repo_root, so this is the one input that could otherwise cause
        # init to write outside the affirmed repo root.
        outside_marker = "definitely-not-created"
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp)
            self._install_skills(root, "ult-context-generate")
            write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")
            absolute_target = str(Path(outside) / outside_marker)
            code, messages = vl.run_init(root, workspace_root=absolute_target)
            self.assertEqual(code, 1)
            self.assertTrue(any("M3" in m for m in messages), messages)
            self.assertFalse((Path(outside) / outside_marker).exists())
            config = vl.load_yaml_file(root / "context-config.yaml")
            self.assertNotIn("workspace_root", config.get("layout", {}))

    def test_default_omits_hook_scaffold(self):
        # ci_hook defaults to False - init never touches .git/hooks/ unless
        # explicitly asked to, even when a hooks dir is present.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install_skills(root, "ult-context-generate")
            write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")
            (root / ".git" / "hooks").mkdir(parents=True)
            code, messages = vl.run_init(root)
            self.assertEqual(code, 0, messages)
            self.assertFalse((root / ".git" / "hooks" / "pre-commit").exists())
            self.assertFalse(any("pre-commit" in m for m in messages))

    def test_ci_hook_true_scaffolds_hook_when_git_hooks_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install_skills(root, "ult-context-generate")
            write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")
            (root / ".git" / "hooks").mkdir(parents=True)
            code, messages = vl.run_init(root, ci_hook=True)
            self.assertEqual(code, 0, messages)
            hook = root / ".git" / "hooks" / "pre-commit"
            self.assertTrue(hook.exists())
            hook_text = hook.read_text(encoding="utf-8")
            self.assertIn("validate_layout.py --validate", hook_text)
            self.assertTrue(any("Scaffolded pre-commit hook" in m for m in messages))

    def test_ci_hook_writes_fail_open_hook_text(self):
        # The hook must never block a commit outright: no python3/python on
        # PATH, or a non-zero --validate exit, both fall through to exit 0.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install_skills(root, "ult-context-generate")
            write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")
            (root / ".git" / "hooks").mkdir(parents=True)
            code, messages = vl.run_init(root, ci_hook=True)
            self.assertEqual(code, 0, messages)
            hook_text = (root / ".git" / "hooks" / "pre-commit").read_text(encoding="utf-8")
            self.assertIn("command -v python3 || command -v python", hook_text)
            self.assertIn("|| exit 0", hook_text)

    def test_hook_skipped_when_git_hooks_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install_skills(root, "ult-context-generate")
            write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")
            code, messages = vl.run_init(root, ci_hook=True)
            self.assertEqual(code, 0, messages)
            self.assertTrue(any("Skipped pre-commit hook" in m for m in messages))

    def test_existing_hook_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install_skills(root, "ult-context-generate")
            write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")
            hooks_dir = root / ".git" / "hooks"
            hooks_dir.mkdir(parents=True)
            write(hooks_dir / "pre-commit", "#!/bin/sh\necho custom hook\n")
            code, messages = vl.run_init(root, ci_hook=True)
            self.assertEqual(code, 0, messages)
            self.assertIn("custom hook", (hooks_dir / "pre-commit").read_text(encoding="utf-8"))
            self.assertTrue(any("already exists" in m for m in messages))

    def test_ci_hook_fails_open_when_only_python3_on_path(self):
        # Fabricated PATH with only a `python3` shim (no `python`) - the
        # hook must still exit 0, whether it's because it found python3 and
        # validate passed/failed, or because neither interpreter existed.
        import os
        import shutil
        import stat
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install_skills(root, "ult-context-generate")
            write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")
            (root / ".git" / "hooks").mkdir(parents=True)
            code, messages = vl.run_init(root, ci_hook=True)
            self.assertEqual(code, 0, messages)
            hook = root / ".git" / "hooks" / "pre-commit"
            hook.chmod(hook.stat().st_mode | stat.S_IEXEC)

            fake_bin = Path(tmp) / "fakebin"
            fake_bin.mkdir()
            python3_shim = fake_bin / "python3"
            # A shim that always fails, standing in for a validate error -
            # the hook must still exit 0 (fail-open), not propagate this.
            write(python3_shim, "#!/bin/sh\nexit 1\n")
            python3_shim.chmod(python3_shim.stat().st_mode | stat.S_IEXEC)

            # Resolve `sh` to an absolute path *before* fabricating PATH below.
            # On POSIX, subprocess locates a bare command name using the PATH
            # of the `env` passed to it (not the real process PATH) - so once
            # PATH is trimmed to fake_bin-only, a bare "sh" argv[0] can no
            # longer be found and raises FileNotFoundError. Windows resolves
            # the executable via the OS's own search instead of the child
            # env block, which is why this never surfaced there. The fix
            # only needs to make launching `sh` itself PATH-independent; the
            # fabricated PATH below still correctly limits what the *hook's
            # own* interpreter lookup sees (python3 shim only, no python).
            sh_path = shutil.which("sh") or "sh"

            env = dict(os.environ)
            env["PATH"] = str(fake_bin)
            result = subprocess.run(
                [sh_path, str(hook)], cwd=str(root), env=env,
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_init_registers_file_kind_slots_without_claiming_scaffolded(self):
        # kind: file slots only ever get a marker at init time - the file
        # itself is written by the owning skill on its own first run.
        # "Scaffolded" would be a false claim; init must say "Registered".
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install_skills(root, "ult-institutional-memory-distill")
            write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")
            code, messages = vl.run_init(root)
            self.assertEqual(code, 0, messages)
            registered = [m for m in messages if "decision_ledger" in m]
            self.assertTrue(registered, messages)
            self.assertTrue(all("Registered" in m for m in registered), messages)
            self.assertFalse(any("Scaffolded 'decision_ledger'" in m for m in messages), messages)
            self.assertFalse(
                (root / "starter_kit" / "decision_ledger" / "DECISION-LEDGER.json").exists()
            )

    def test_validate_after_init_is_silent_for_unwritten_file_slots(self):
        # A fresh init claims success; --validate immediately after must
        # not contradict it by flagging the file-kind slot it just
        # correctly registered (not scaffolded) as a problem.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install_skills(root, "ult-institutional-memory-distill")
            write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")
            code, _ = vl.run_init(root)
            self.assertEqual(code, 0)

    def test_init_disables_what_l2_and_how_l2_when_shipped_defaults_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install_skills(root, "ult-context-generate")
            write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")
            code, messages = vl.run_init(root)
            self.assertEqual(code, 0, messages)
            self.assertTrue(any("layers.what_l2.enabled = false" in m for m in messages), messages)
            self.assertTrue(
                any("how_dimension.how_l2.enabled = false" in m for m in messages), messages
            )
            config = vl.load_yaml_file(root / "context-config.yaml")
            self.assertFalse(vl.resolve_what_l2_enabled(config))
            self.assertFalse(vl.resolve_how_l2_enabled(config))

            ok, report = vl.validate(root)
            self.assertFalse(any("what_l2" in line and "S28" in line for line in report), report)
            self.assertFalse(any("how_l2" in line and "S28" in line for line in report), report)

    def test_init_leaves_explicit_what_l2_path_alone_even_if_absent(self):
        # An explicitly-configured path (even one that doesn't exist yet)
        # is the user's own decision - init must never silently disable it.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install_skills(root, "ult-context-generate")
            write(
                root / "context-config.yaml",
                "cache:\n  product_context_path: contexts/\n"
                "layers:\n  what_l2:\n    path: docs/spec/\n",
            )
            code, messages = vl.run_init(root)
            self.assertEqual(code, 0, messages)
            self.assertFalse(any("layers.what_l2.enabled" in m for m in messages), messages)
            config = vl.load_yaml_file(root / "context-config.yaml")
            self.assertTrue(vl.resolve_what_l2_enabled(config))

    def test_init_leaves_what_l2_enabled_when_shipped_default_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install_skills(root, "ult-context-generate")
            write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")
            (root / "docs" / "requirements").mkdir(parents=True)
            write(root / "docs" / "requirements" / "spec.md", "# spec\n")
            code, messages = vl.run_init(root)
            self.assertEqual(code, 0, messages)
            self.assertFalse(any("layers.what_l2.enabled" in m for m in messages), messages)
            config = vl.load_yaml_file(root / "context-config.yaml")
            self.assertTrue(vl.resolve_what_l2_enabled(config))

    def test_freshly_scaffolded_repo_validates_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install_skills(root, "ult-context-generate")
            write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")
            code, _ = vl.run_init(root)
            self.assertEqual(code, 0)

            ok, report = vl.validate(root)
            fails = [line for line in report if line.startswith("FAIL")]
            self.assertEqual(fails, [])
            self.assertTrue(ok)


class TestRunInitDryRun(unittest.TestCase):
    """the 2026-08-31 Round-2 evaluation's finding on first-run workspace-root namespacing during init: `dry_run=True` previews
    exactly what a real `run_init(...)` call would do - same eligibility
    checks, same slot-resolution loop - without writing anything, so the
    wizard's first-run workspace_root offer can show a tree preview before
    the human commits to it."""

    def _install_skills(self, root, *names):
        for name in names:
            (root / ".github" / "skills" / name).mkdir(parents=True, exist_ok=True)

    def test_dry_run_writes_nothing_to_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install_skills(root, "ult-context-generate")
            write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")
            before = (root / "context-config.yaml").read_text(encoding="utf-8")

            code, messages = vl.run_init(root, workspace_root="docs/", dry_run=True)
            self.assertEqual(code, 0, messages)

            after = (root / "context-config.yaml").read_text(encoding="utf-8")
            self.assertEqual(before, after)
            self.assertFalse((root / "docs").exists())
            self.assertFalse((root / "contexts").exists())
            config = vl.load_yaml_file(root / "context-config.yaml")
            self.assertNotIn("project_layout", config or {})

    def test_dry_run_messages_use_would_phrasing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install_skills(root, "ult-context-generate")
            write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")

            code, messages = vl.run_init(root, workspace_root="docs/", dry_run=True)
            self.assertEqual(code, 0, messages)
            self.assertTrue(
                any("Would scaffold 'context_packages' at 'docs/contexts/'." in m for m in messages),
                messages,
            )
            self.assertTrue(
                any(m.startswith("Would set layout.workspace_root = 'docs'") for m in messages),
                messages,
            )
            self.assertTrue(any("Would write project_layout" in m for m in messages), messages)
            # Never the real, past-tense phrasing a completed run would use.
            self.assertFalse(any(m.startswith("Scaffolded ") for m in messages), messages)
            self.assertFalse(any(m.startswith("Set layout.workspace_root") for m in messages), messages)
            self.assertFalse(any(m.startswith("Wrote project_layout") for m in messages), messages)

    def test_dry_run_matches_real_run_entries_for_same_inputs(self):
        # The preview must agree with reality: calling dry_run=True and then
        # dry_run=False against the same untouched directory with identical
        # inputs must produce the same number of messages (one "Would ..."
        # per real-run message) - including the what_l2/how_l2 disable
        # messages, which regressed before the fix that snapshots shipped-
        # default existence *before* the scaffold loop's own mkdir() calls
        # can create the workspace root as a side effect.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install_skills(root, "ult-context-generate")
            write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")
            preview_code, preview_messages = vl.run_init(root, workspace_root="docs/", dry_run=True)
            self.assertEqual(preview_code, 0, preview_messages)
            real_code, real_messages = vl.run_init(root, workspace_root="docs/", dry_run=False)
            self.assertEqual(real_code, 0, real_messages)
            self.assertTrue((root / "docs" / "contexts").is_dir())
            self.assertEqual(len(preview_messages), len(real_messages))

    def test_dry_run_still_refuses_when_already_initialized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install_skills(root, "ult-context-generate")
            write(
                root / "context-config.yaml",
                "project_layout:\n  version: 1\n  initialized: true\n",
            )
            code, messages = vl.run_init(root, dry_run=True)
            self.assertEqual(code, 1)
            self.assertTrue(any("Already initialized" in m for m in messages))

    def test_dry_run_with_ci_hook_on_initialized_repo_previews_hook_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install_skills(root, "ult-context-generate")
            write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")
            (root / ".git" / "hooks").mkdir(parents=True)
            self.assertEqual(vl.run_init(root)[0], 0)

            code, messages = vl.run_init(root, ci_hook=True, dry_run=True)
            self.assertEqual(code, 0, messages)
            self.assertFalse((root / ".git" / "hooks" / "pre-commit").exists())
            self.assertTrue(any("Would scaffold pre-commit hook" in m for m in messages), messages)

    def test_dry_run_invalid_workspace_root_still_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install_skills(root, "ult-context-generate")
            write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")
            code, messages = vl.run_init(root, workspace_root=".", dry_run=True)
            self.assertEqual(code, 1)
            self.assertTrue(any("S22" in m for m in messages))

            ok, report = vl.validate(root)
            self.assertFalse(any("decision_ledger" in line for line in report), report)

    def test_init_disables_what_l2_and_how_l2_when_shipped_defaults_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install_skills(root, "ult-context-generate")
            write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")
            code, messages = vl.run_init(root)
            self.assertEqual(code, 0, messages)
            self.assertTrue(any("layers.what_l2.enabled = false" in m for m in messages), messages)
            self.assertTrue(
                any("how_dimension.how_l2.enabled = false" in m for m in messages), messages
            )
            config = vl.load_yaml_file(root / "context-config.yaml")
            self.assertFalse(vl.resolve_what_l2_enabled(config))
            self.assertFalse(vl.resolve_how_l2_enabled(config))

            ok, report = vl.validate(root)
            self.assertFalse(any("what_l2" in line and "S28" in line for line in report), report)
            self.assertFalse(any("how_l2" in line and "S28" in line for line in report), report)

    def test_init_leaves_explicit_what_l2_path_alone_even_if_absent(self):
        # An explicitly-configured path (even one that doesn't exist yet)
        # is the user's own decision - init must never silently disable it.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install_skills(root, "ult-context-generate")
            write(
                root / "context-config.yaml",
                "cache:\n  product_context_path: contexts/\n"
                "layers:\n  what_l2:\n    path: docs/spec/\n",
            )
            code, messages = vl.run_init(root)
            self.assertEqual(code, 0, messages)
            self.assertFalse(any("layers.what_l2.enabled" in m for m in messages), messages)
            config = vl.load_yaml_file(root / "context-config.yaml")
            self.assertTrue(vl.resolve_what_l2_enabled(config))

    def test_init_leaves_what_l2_enabled_when_shipped_default_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install_skills(root, "ult-context-generate")
            write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")
            (root / "docs" / "requirements").mkdir(parents=True)
            write(root / "docs" / "requirements" / "spec.md", "# spec\n")
            code, messages = vl.run_init(root)
            self.assertEqual(code, 0, messages)
            self.assertFalse(any("layers.what_l2.enabled" in m for m in messages), messages)
            config = vl.load_yaml_file(root / "context-config.yaml")
            self.assertTrue(vl.resolve_what_l2_enabled(config))

    def test_freshly_scaffolded_repo_validates_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._install_skills(root, "ult-context-generate")
            write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")
            code, _ = vl.run_init(root)
            self.assertEqual(code, 0)

            ok, report = vl.validate(root)
            fails = [line for line in report if line.startswith("FAIL")]
            self.assertEqual(fails, [])
            self.assertTrue(ok)


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

    def test_init_flag_scaffolds_and_exits_zero(self):
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".github" / "skills" / "ult-context-generate").mkdir(parents=True)
            write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = vl.main(["--init", "--no-ci-hook", str(root)])
            self.assertEqual(rc, 0)
            self.assertIn("Scaffolded 'context_packages'", buf.getvalue())
            self.assertTrue((root / "contexts").is_dir())

    def test_init_flag_default_omits_hook_and_no_ci_hook_flag_is_noop(self):
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".github" / "skills" / "ult-context-generate").mkdir(parents=True)
            (root / ".git" / "hooks").mkdir(parents=True)
            write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = vl.main(["--init", "--no-ci-hook", str(root)])
            self.assertEqual(rc, 0)
            self.assertIn("deprecated", buf.getvalue())
            self.assertIn("no-op", buf.getvalue())
            self.assertFalse((root / ".git" / "hooks" / "pre-commit").exists())

    def test_init_flag_ci_hook_scaffolds_hook(self):
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".github" / "skills" / "ult-context-generate").mkdir(parents=True)
            (root / ".git" / "hooks").mkdir(parents=True)
            write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = vl.main(["--init", "--ci-hook", str(root)])
            self.assertEqual(rc, 0)
            self.assertTrue((root / ".git" / "hooks" / "pre-commit").exists())

    def test_init_flag_with_workspace_root(self):
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".github" / "skills" / "ult-context-generate").mkdir(parents=True)
            write(root / "context-config.yaml", "cache:\n  product_context_path: contexts/\n")

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = vl.main(["--init", "--workspace-root", "docs/", "--no-ci-hook", str(root)])
            self.assertEqual(rc, 0)
            config = vl.load_yaml_file(root / "context-config.yaml")
            self.assertEqual(vl._normalize_workspace_root(config), "docs")

    def test_init_flag_refuses_when_already_initialized(self):
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".github" / "skills" / "ult-context-generate").mkdir(parents=True)
            write(
                root / "context-config.yaml",
                "project_layout:\n  version: 1\n  initialized: true\n",
            )

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = vl.main(["--init", str(root)])
            self.assertEqual(rc, 1)
            self.assertIn("Already initialized", buf.getvalue())

    def test_init_flag_with_ci_hook_succeeds_when_already_initialized(self):
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".github" / "skills" / "ult-context-generate").mkdir(parents=True)
            (root / ".git" / "hooks").mkdir(parents=True)
            write(
                root / "context-config.yaml",
                "project_layout:\n  version: 1\n  initialized: true\n",
            )

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = vl.main(["--init", "--ci-hook", str(root)])
            self.assertEqual(rc, 0, buf.getvalue())
            self.assertTrue((root / ".git" / "hooks" / "pre-commit").exists())
            self.assertIn("Already initialized", buf.getvalue())
            self.assertIn("Scaffolded pre-commit hook", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
