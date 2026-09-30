"""Regression suite for scaffold_state.py (D24 Phase B, ult-autoscaffold-content).

Stdlib unittest only -- no pytest dependency, so this stays vendorable along
with scaffold_state.py itself. Run with:

    python -m unittest discover -s scripts/tests -v
"""

import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scaffold_state as ss  # noqa: E402


def _write(path, content=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# A synthetic graph.json fixture in the real, empirically-verified graphify
# 0.9.11 schema -- top-level keys input_tokens/output_tokens/nodes/links;
# node id/label/file_type/source_file/source_location/_origin; link
# source/target/relation/context/confidence/source_file/source_location/
# weight. Mirrors a 3-module repo: core/ depends heavily on utils/ (many
# distinct call/import edges from several core symbols), legacy/ has
# exactly one caller (core/), and orphan/ has none.
def _fixture_graph():
    def node(id_, source_file):
        return {"id": id_, "label": id_, "file_type": "code",
                "source_file": source_file, "source_location": "L1", "_origin": "ast"}

    def link(source, target, relation):
        return {"source": source, "target": target, "relation": relation,
                "context": relation, "confidence": "EXTRACTED",
                "source_file": "x", "source_location": "L1", "weight": 1.0}

    nodes = [
        node("core_main", "core/main.py"),
        node("core_main_run", "core/main.py"),
        node("core_service", "core/service.py"),
        node("utils_helpers_add", "utils/helpers.py"),
        node("utils_helpers_mul", "utils/helpers.py"),
        node("legacy_old", "legacy/old.py"),
        node("orphan_thing", "orphan/thing.py"),
        node("root_readme", "README.py"),  # repo-root file, no module
    ]
    links = [
        link("core_main", "utils_helpers_add", "imports_from"),
        link("core_main_run", "utils_helpers_add", "calls"),
        link("core_main_run", "utils_helpers_mul", "calls"),
        link("core_service", "utils_helpers_add", "imports"),
        link("core_main", "legacy_old", "imports_from"),
        # structural relation -- must NOT count toward in-degree
        link("core_main", "core_main_run", "contains"),
        # same-module edge -- must NOT count toward in-degree
        link("utils_helpers_add", "utils_helpers_mul", "calls"),
    ]
    return {"input_tokens": 0, "output_tokens": 0, "nodes": nodes, "links": links}


class LoadSaveRoundtripTests(unittest.TestCase):
    def test_missing_file_returns_empty_skeleton(self):
        with tempfile.TemporaryDirectory() as d:
            state = ss.load_state(Path(d) / "TRIAGE-STATE.json")
        self.assertEqual(state["modules"], [])
        self.assertIsNone(state["repo_scan"]["graph_source"])
        self.assertEqual(state["schema_version"], ss.SCHEMA_VERSION)

    def test_save_then_load_roundtrips(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "nested" / "TRIAGE-STATE.json"
            state = ss.empty_state()
            state["modules"].append({
                "id": "core/", "tier": 1, "in_degree": 12, "file_count": 4,
                "basis": "graph:in-degree", "status": "pending",
                "generated_at": None, "output_path": None, "skip_reason": None,
            })
            ss.save_state(path, state)
            self.assertTrue(path.exists(), "save_state must create parent dirs")
            reloaded = ss.load_state(path)
            self.assertEqual(len(reloaded["modules"]), 1)
            self.assertEqual(reloaded["modules"][0]["id"], "core/")

    def test_empty_file_treated_as_empty_skeleton(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "TRIAGE-STATE.json"
            path.write_text("", encoding="utf-8")
            state = ss.load_state(path)
            self.assertEqual(state["modules"], [])


class FilesystemScanHelperTests(unittest.TestCase):
    def test_top_level_candidate_dirs_prunes_ignored_and_dot_dirs(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for name in ("core", "utils", "node_modules", ".git", ".venv", "cache"):
                (root / name).mkdir()
            self.assertEqual(ss._top_level_candidate_dirs(root), ["core", "utils"])

    def test_top_level_candidate_dirs_prunes_graphify_out(self):
        # ult-codegraph's own fixed, always-gitignored output directory --
        # never a real module candidate. See scaffold_state.py's
        # SCAN_IGNORED_DIR_NAMES comment for why this needs its own entry.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for name in ("core", "graphify-out"):
                (root / name).mkdir()
            self.assertEqual(ss._top_level_candidate_dirs(root), ["core"])

    def test_top_level_candidate_dirs_prunes_vendor_and_cep_scaffold_stopgap_names(self):
        # The seven name-based stopgap entries SCAN_IGNORED_DIR_NAMES adds on
        # top of graphify-out: "starter_kit"/"output_docs" (CEP's own
        # scaffolded locations, kept as a fallback for manifest-unaware
        # repos -- see test_top_level_candidate_dirs_keeps_manifest_owned_
        # name_without_manifest_when_not_denylisted below for the case a
        # manifest-unaware repo still needs) and "third_party"/"extern"/
        # "external"/"deps"/"submodules" (a project's own vendored code, a
        # problem the manifest can never see at all).
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            stopgap_names = (
                "third_party", "starter_kit", "output_docs", "extern",
                "external", "deps", "submodules",
            )
            for name in ("core",) + stopgap_names:
                (root / name).mkdir()
            self.assertEqual(ss._top_level_candidate_dirs(root), ["core"])

    def test_top_level_candidate_dirs_missing_root_returns_empty(self):
        self.assertEqual(ss._top_level_candidate_dirs("/does/not/exist/anywhere"), [])

    def test_top_level_candidate_dirs_excludes_manifest_owned_top_level_name(self):
        # custom_output_bucket/ has no dot prefix and isn't in
        # SCAN_IGNORED_DIR_NAMES, so without manifest awareness it would be
        # walked and tiered like a real application module -- the exact
        # false-positive _manifest_owned_top_level_names exists to close.
        # Deliberately not "starter_kit" here (that name is covered by the
        # denylist stopgap test above regardless of manifest presence) --
        # this fixture isolates manifest-driven exclusion from the
        # name-based denylist, so a regression in either one shows up as
        # exactly one of these two test pairs failing, not both.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "core").mkdir()
            _write(
                root / "custom_output_bucket" / "project_guidelines" / "GUIDE.md",
                "# guide",
            )
            _write(
                root / ".cep-install.json",
                json.dumps({
                    "schema_version": 1,
                    "runtime": ["claude", "copilot"],
                    "mode": "full",
                    "only_skills": None,
                    "owned_paths": [
                        ".github/skills",
                        ".github/prompts",
                        "custom_output_bucket/project_guidelines",
                    ],
                    "installed_at": "2026-01-01T00:00:00Z",
                }),
            )
            self.assertEqual(ss._top_level_candidate_dirs(root), ["core"])

    def test_top_level_candidate_dirs_keeps_manifest_owned_name_without_manifest_when_not_denylisted(self):
        # Same custom_output_bucket/ fixture as above, but with no
        # .cep-install.json present -- _read_cep_manifest must return None
        # (not raise), and scaffold_state falls back to pre-manifest
        # behavior: custom_output_bucket/ still surfaces as a real
        # candidate module, exactly as it always has for a manually
        # installed or unmanifested repo. (A name actually in
        # SCAN_IGNORED_DIR_NAMES, like starter_kit, would stay pruned even
        # here -- that's the point of the denylist stopgap; this test picks
        # a name outside it specifically to isolate manifest-only behavior.)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "core").mkdir()
            _write(
                root / "custom_output_bucket" / "project_guidelines" / "GUIDE.md",
                "# guide",
            )
            self.assertIsNone(ss._read_cep_manifest(root))
            self.assertEqual(
                ss._top_level_candidate_dirs(root), ["core", "custom_output_bucket"]
            )

    def test_iter_files_prunes_nested_ignored_dirs(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _write(root / "core" / "main.py", "x")
            _write(root / "core" / "__pycache__" / "main.cpython.pyc", "x")
            found = sorted(p.name for p in ss._iter_files(root / "core"))
            self.assertEqual(found, ["main.py"])


def _make_dir_with_files(root, name, n):
    for i in range(n):
        _write(root / name / "f{}.py".format(i), "x")


class ProbeSizeTests(unittest.TestCase):
    # SKILL.md Step 4's small/large repo-size gate. Thresholds under test:
    # MIN_FILES_FOR_SIZE_GATE=5, SMALL_REPO_MAX_MODULES=2,
    # LARGE_REPO_MIN_MODULES=8.

    def test_no_directories_classifies_small(self):
        with tempfile.TemporaryDirectory() as d:
            result = ss.probe_size(Path(d))
            self.assertEqual(result["count"], 0)
            self.assertEqual(result["classification"], "small")
            self.assertEqual(result["substantive_modules"], [])

    def test_directory_below_min_files_does_not_count(self):
        # A conventionally near-empty structural dir (docs/ with one file)
        # must not inflate the count -- this is the whole point of
        # MIN_FILES_FOR_SIZE_GATE.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _make_dir_with_files(root, "docs", ss.MIN_FILES_FOR_SIZE_GATE - 1)
            result = ss.probe_size(root)
            self.assertEqual(result["count"], 0)
            self.assertEqual(result["classification"], "small")

    def test_small_repo_at_upper_boundary(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for i in range(ss.SMALL_REPO_MAX_MODULES):
                _make_dir_with_files(root, "mod{}".format(i), ss.MIN_FILES_FOR_SIZE_GATE)
            result = ss.probe_size(root)
            self.assertEqual(result["count"], ss.SMALL_REPO_MAX_MODULES)
            self.assertEqual(result["classification"], "small")

    def test_ambiguous_band_just_above_small(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for i in range(ss.SMALL_REPO_MAX_MODULES + 1):
                _make_dir_with_files(root, "mod{}".format(i), ss.MIN_FILES_FOR_SIZE_GATE)
            result = ss.probe_size(root)
            self.assertEqual(result["classification"], "ambiguous")

    def test_ambiguous_band_just_below_large(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for i in range(ss.LARGE_REPO_MIN_MODULES - 1):
                _make_dir_with_files(root, "mod{}".format(i), ss.MIN_FILES_FOR_SIZE_GATE)
            result = ss.probe_size(root)
            self.assertEqual(result["classification"], "ambiguous")

    def test_large_repo_at_lower_boundary(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for i in range(ss.LARGE_REPO_MIN_MODULES):
                _make_dir_with_files(root, "mod{}".format(i), ss.MIN_FILES_FOR_SIZE_GATE)
            result = ss.probe_size(root)
            self.assertEqual(result["count"], ss.LARGE_REPO_MIN_MODULES)
            self.assertEqual(result["classification"], "large")

    def test_ignored_and_cep_bucket_dirs_never_count_regardless_of_size(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            # node_modules alone has enough files to swing "large" on its
            # own if it weren't pruned -- same SCAN_IGNORED_DIR_NAMES/
            # CEP_BUCKET_DIR_NAMES pruning _top_level_candidate_dirs() uses.
            for i in range(ss.LARGE_REPO_MIN_MODULES):
                _make_dir_with_files(root, "node_modules/pkg{}".format(i), ss.MIN_FILES_FOR_SIZE_GATE)
            _make_dir_with_files(root, "cache", ss.MIN_FILES_FOR_SIZE_GATE)
            result = ss.probe_size(root)
            self.assertEqual(result["count"], 0)
            self.assertEqual(result["classification"], "small")


class ProbeSizeEvidenceSignalsTests(unittest.TestCase):
    """The evidence gate: probe-size grows a `signals` dict
    (formatter/linter config, dev-workflow wrapper scripts, test config,
    ci, contributing, tool_versions) plus `grounded_viable` (a dict keyed
    by GROUNDED_VIABLE_KINDS) and `greenfield` (a bool). TASK-0101/0102.
    Field names/shapes here match the evidence gate's own illustration
    exactly -- coding_standards/testing_guidelines/requirements_overview
    each depend only on whether their own signals are present, never a
    count threshold (unlike classification/count
    above), so several tests here specifically pin that independence from
    MIN_FILES_FOR_SIZE_GATE and friends.
    """

    def test_signals_all_empty_and_greenfield_true_on_source_free_repo(self):
        # A source-free repo (nothing at all, not even a .git) must return
        # fully deterministic, non-crashing values -- every signal list
        # empty, tool_versions an empty dict, greenfield True, every
        # grounded_viable kind False.
        with tempfile.TemporaryDirectory() as d:
            result = ss.probe_size(Path(d))
            self.assertTrue(result["greenfield"])
            signals = result["signals"]
            for key in (
                "formatter_config", "linter_config", "wrapper_scripts",
                "test_config", "ci", "contributing",
            ):
                self.assertEqual(signals[key], [], key)
            self.assertEqual(signals["tool_versions"], {})
            self.assertEqual(
                result["grounded_viable"],
                {"coding_standards": False, "testing_guidelines": False,
                 "requirements_overview": False},
            )

    def test_existing_fields_unchanged_shape_alongside_new_ones(self):
        # Backward compatibility: TASK-0102 must not disturb probe_size()'s
        # pre-existing return shape for callers that only look at these.
        with tempfile.TemporaryDirectory() as d:
            result = ss.probe_size(Path(d))
            self.assertEqual(result["count"], 0)
            self.assertEqual(result["classification"], "small")
            self.assertEqual(result["substantive_modules"], [])

    def test_greenfield_false_when_any_real_file_exists_under_a_module_dir(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _write(root / "core" / "main.py", "print('hi')")
            result = ss.probe_size(root)
            self.assertFalse(result["greenfield"])
            self.assertTrue(result["grounded_viable"]["requirements_overview"])

    def test_requirements_overview_viability_independent_of_size_gate_threshold(self):
        # A single loose top-level file is real evidence even though it
        # never clears MIN_FILES_FOR_SIZE_GATE and count/classification
        # stay at their all-empty defaults -- grounded_viable must not be
        # gated by that threshold at all (TASK-0102's explicit requirement).
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _write(root / "README.md", "# hello")
            result = ss.probe_size(root)
            self.assertEqual(result["count"], 0)
            self.assertEqual(result["classification"], "small")
            self.assertTrue(result["grounded_viable"]["requirements_overview"])
            self.assertFalse(result["greenfield"])

    def test_dotfile_only_repo_still_counts_as_greenfield(self):
        # A lone tooling dotfile (.clang-format) with no real project
        # content anywhere is still "greenfield" for requirements_overview
        # purposes -- it shows up in signals.formatter_config (real
        # evidence for a must_cite list, and enough on its own to make
        # coding_standards viable), but does not by itself supply general
        # project content. Mirrors _prune_ignored()'s existing
        # dot-directory exclusion for the same underlying reason (tooling
        # scaffolding isn't project content).
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _write(root / ".clang-format", "BasedOnStyle: Google")
            result = ss.probe_size(root)
            self.assertTrue(result["greenfield"])
            self.assertFalse(result["grounded_viable"]["requirements_overview"])
            self.assertTrue(result["grounded_viable"]["coding_standards"])
            self.assertEqual(result["signals"]["formatter_config"], [".clang-format"])

    def test_formatter_config_detected_and_makes_coding_standards_viable(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _write(root / "core" / "main.py", "x")
            _write(root / ".clang-format", "BasedOnStyle: Google")
            _write(root / ".prettierrc", "{}")
            result = ss.probe_size(root)
            self.assertEqual(
                result["signals"]["formatter_config"], [".clang-format", ".prettierrc"]
            )
            self.assertTrue(result["grounded_viable"]["coding_standards"])

    def test_linter_config_detected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _write(root / "core" / "main.cc", "x")
            _write(root / "CPPLINT.cfg", "set noparent")
            result = ss.probe_size(root)
            self.assertEqual(result["signals"]["linter_config"], ["CPPLINT.cfg"])
            self.assertTrue(result["grounded_viable"]["coding_standards"])

    def test_wrapper_scripts_detected_includes_test_sh_not_test_config(self):
        # Sec 4.3's own illustration groups "test.sh" under wrapper_scripts
        # alongside "format.sh", distinct from test_config's build-system
        # registration markers -- pinned here so a future edit can't
        # silently move it back.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _write(root / "core" / "main.cc", "x")
            _write(root / "format.sh", "#!/bin/sh\nclang-format -i")
            _write(root / "test.sh", "#!/bin/sh\nctest")
            result = ss.probe_size(root)
            self.assertEqual(result["signals"]["wrapper_scripts"], ["format.sh", "test.sh"])
            self.assertEqual(result["signals"]["test_config"], [])

    def test_test_config_detected_from_conventional_filenames(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _write(root / "core" / "main.cc", "x")
            _write(root / "pytest.ini", "[pytest]")
            result = ss.probe_size(root)
            self.assertEqual(result["signals"]["test_config"], ["pytest.ini"])
            self.assertTrue(result["grounded_viable"]["testing_guidelines"])

    def test_test_config_detects_cmake_enable_testing_convention(self):
        # Matches Sec 4.3's own worked-example illustration literally:
        # test_config for a CMake project surfaces as
        # "CMakeLists.txt:enable_testing", not a filename.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _write(root / "core" / "main.cc", "x")
            _write(root / "CMakeLists.txt", "project(example_app)\nenable_testing()\n")
            result = ss.probe_size(root)
            self.assertEqual(
                result["signals"]["test_config"], ["CMakeLists.txt:enable_testing"]
            )
            self.assertTrue(result["grounded_viable"]["testing_guidelines"])

    def test_cmake_without_enable_testing_yields_no_test_config_signal(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _write(root / "core" / "main.cc", "x")
            _write(root / "CMakeLists.txt", "project(example_app)\n")
            result = ss.probe_size(root)
            self.assertEqual(result["signals"]["test_config"], [])
            self.assertFalse(result["grounded_viable"]["testing_guidelines"])

    def test_ci_signal_detected_from_workflows_dir_and_root_filenames(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _write(root / "core" / "main.cc", "x")
            _write(root / ".github" / "workflows" / "cpp.yml", "name: cpp")
            _write(root / ".gitlab-ci.yml", "stages: []")
            result = ss.probe_size(root)
            # Sorted lexicographically: ".github/..." precedes ".gitlab-ci.yml"
            # ('h' < 'l' at the first differing character).
            self.assertEqual(
                result["signals"]["ci"],
                [".github/workflows/cpp.yml", ".gitlab-ci.yml"],
            )

    def test_contributing_signal_detected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _write(root / "core" / "main.cc", "x")
            _write(root / "CONTRIBUTING.md", "# Contributing\nclang-format >= 8.0.0 required")
            result = ss.probe_size(root)
            self.assertEqual(result["signals"]["contributing"], ["CONTRIBUTING.md"])

    def test_tool_versions_cites_locations_mentioning_a_detected_formatter(self):
        # worked-example-style evidence: .clang-format present, and its name is
        # mentioned in format.sh, a CI workflow, and CONTRIBUTING.md --
        # tool_versions should cite every one of those lines, "path:Lline",
        # not a parsed version number.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _write(root / "core" / "main.cc", "x")
            _write(root / ".clang-format", "BasedOnStyle: Google")
            _write(root / "format.sh", "#!/bin/sh\nclang-format -i $(find . -name '*.cc')\n")
            _write(
                root / ".github" / "workflows" / "cpp.yml",
                "name: cpp\nrun: clang-format --version\n",
            )
            _write(
                root / "CONTRIBUTING.md",
                "# Contributing\nRequires clang-format >= 8.0.0\n",
            )
            result = ss.probe_size(root)
            self.assertEqual(
                result["signals"]["tool_versions"],
                {
                    "clang-format": [
                        "format.sh:L2",
                        ".github/workflows/cpp.yml:L2",
                        "CONTRIBUTING.md:L2",
                    ]
                },
            )

    def test_tool_versions_empty_when_no_mapped_formatter_or_linter_present(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _write(root / "core" / "main.cc", "x")
            _write(root / "format.sh", "#!/bin/sh\nclang-format -i\n")
            result = ss.probe_size(root)
            # format.sh mentions clang-format, but with no .clang-format
            # (or other mapped config) present there is no tool to cite
            # locations for -- tool_versions stays empty, not guessed.
            self.assertEqual(result["signals"]["tool_versions"], {})

    def test_tool_versions_empty_when_tool_name_mentioned_nowhere(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _write(root / "core" / "main.cc", "x")
            _write(root / ".clang-format", "BasedOnStyle: Google")
            _write(root / "format.sh", "#!/bin/sh\necho building\n")
            result = ss.probe_size(root)
            self.assertEqual(result["signals"]["tool_versions"], {})

    def test_missing_repo_root_returns_deterministic_greenfield_signals(self):
        # Mirrors _top_level_candidate_dirs()'s own "missing root returns
        # empty" posture -- probe_size must not raise for a nonexistent
        # --repo-root, same as the pre-existing count/classification path.
        result = ss.probe_size("/does/not/exist/anywhere")
        self.assertTrue(result["greenfield"])
        self.assertEqual(
            result["grounded_viable"],
            {"coding_standards": False, "testing_guidelines": False,
             "requirements_overview": False},
        )
        self.assertEqual(result["signals"]["tool_versions"], {})


class GeneratedDetectionTests(unittest.TestCase):
    def test_generated_dir_name_matches(self):
        self.assertTrue(ss.GENERATED_DIR_NAME_RE.match("generated"))
        self.assertTrue(ss.GENERATED_DIR_NAME_RE.match("gen"))
        self.assertFalse(ss.GENERATED_DIR_NAME_RE.match("genesis"))

    def test_is_generated_module_by_dir_name(self):
        with tempfile.TemporaryDirectory() as d:
            module_path = Path(d) / "generated"
            module_path.mkdir()
            self.assertTrue(ss._is_generated_module(module_path, []))

    def test_is_generated_module_by_file_suffix_majority(self):
        with tempfile.TemporaryDirectory() as d:
            module_path = Path(d) / "proto"
            files = [module_path / "a_pb2.py", module_path / "b_pb2.py", module_path / "readme.md"]
            self.assertTrue(ss._is_generated_module(module_path, files))

    def test_is_generated_module_false_for_ordinary_code(self):
        with tempfile.TemporaryDirectory() as d:
            module_path = Path(d) / "core"
            files = [module_path / "main.py", module_path / "service.py"]
            self.assertFalse(ss._is_generated_module(module_path, files))

    def test_is_generated_module_empty_dir_is_false(self):
        with tempfile.TemporaryDirectory() as d:
            module_path = Path(d) / "empty"
            self.assertFalse(ss._is_generated_module(module_path, []))


_CEP_OUTPUT_FRONTMATTER = """---
generated_by: ult-autoscaffold-content
generated_at: 2026-01-01
status: draft
content_mode: grounded
doc_kind: context_md
skill_version: 0.5.0
---

# Some module

Body text.
"""


class OrphanedCepOutputDetectionTests(unittest.TestCase):
    """Bug: a directory of this skill's own prior output, generated by a
    DIFFERENT (or reset, or side/test) state file than the one currently
    scanning, was silently treated as a brand-new real module -- neither
    _settled_output_subtrees() (state-based) nor
    _check_graph_cep_contamination() (installed-footprint-based) covers
    this, since both require either the current state or the CEP install
    manifest to already know about the directory. Fixed via a third,
    state-independent, content-sniffed signal keyed on the `generated_by`
    frontmatter every content-mode template emits."""

    def test_looks_like_orphaned_cep_output_true_for_own_frontmatter(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "CONTEXT.md"
            _write(path, _CEP_OUTPUT_FRONTMATTER)
            self.assertTrue(ss._looks_like_orphaned_cep_output(path))

    def test_looks_like_orphaned_cep_output_false_for_ordinary_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "main.py"
            _write(path, "def main():\n    pass\n")
            self.assertFalse(ss._looks_like_orphaned_cep_output(path))

    def test_looks_like_orphaned_cep_output_false_for_other_tools_frontmatter(self):
        # A different tool's own "generated_by" marker must not false-match
        # -- this signal is specific to THIS skill's own output, not a
        # generic "has frontmatter" test.
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "CHANGELOG.md"
            _write(path, "---\ngenerated_by: some-other-tool\n---\n\nbody\n")
            self.assertFalse(ss._looks_like_orphaned_cep_output(path))

    def test_looks_like_orphaned_cep_output_false_for_unreadable_path(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "does-not-exist.md"
            self.assertFalse(ss._looks_like_orphaned_cep_output(path))

    def test_is_orphaned_cep_output_module_majority(self):
        with tempfile.TemporaryDirectory() as d:
            module_path = Path(d) / "org"
            files = [module_path / "a.md", module_path / "b.md", module_path / "README.md"]
            _write(files[0], _CEP_OUTPUT_FRONTMATTER)
            _write(files[1], _CEP_OUTPUT_FRONTMATTER)
            _write(files[2], "# just a readme\n")
            self.assertTrue(ss._is_orphaned_cep_output_module(files))

    def test_is_orphaned_cep_output_module_false_below_majority(self):
        with tempfile.TemporaryDirectory() as d:
            module_path = Path(d) / "mixed"
            files = [module_path / "a.md", module_path / "b.py", module_path / "c.py"]
            _write(files[0], _CEP_OUTPUT_FRONTMATTER)
            _write(files[1], "x = 1\n")
            _write(files[2], "y = 2\n")
            self.assertFalse(ss._is_orphaned_cep_output_module(files))

    def test_is_orphaned_cep_output_module_empty_is_false(self):
        self.assertFalse(ss._is_orphaned_cep_output_module([]))


class GraphInDegreeTests(unittest.TestCase):
    def test_module_of_extracts_top_level_dir(self):
        self.assertEqual(ss._module_of("core/main.py"), "core")
        self.assertEqual(ss._module_of("core/sub/deep.py"), "core")
        self.assertIsNone(ss._module_of("README.py"))
        self.assertIsNone(ss._module_of(None))

    def test_graph_in_degrees_counts_distinct_modules_not_raw_edges(self):
        degrees = ss._graph_in_degrees(_fixture_graph())
        # utils/ is called from core/ via 4 separate edges but only 1
        # distinct sending module -- in-degree must be 1, not 4.
        self.assertEqual(degrees.get("utils"), 1)
        self.assertEqual(degrees.get("legacy"), 1)
        # orphan/ has no incoming dependency edges at all.
        self.assertNotIn("orphan", degrees)

    def test_graph_in_degrees_excludes_structural_and_same_module_edges(self):
        degrees = ss._graph_in_degrees(_fixture_graph())
        # "contains" (core_main -> core_main_run) is structural, same
        # module anyway -- must not appear as a self-referential in-degree.
        self.assertNotIn("core", degrees)


class GraphCrossingEdgesTests(unittest.TestCase):
    """_graph_crossing_edges() / _interface_id() -- the interface-boundary
    counterpart to GraphInDegreeTests above, built from the same
    _fixture_graph() so the two stay consistent with each other."""

    def test_crossing_edges_deduplicated_and_weighted(self):
        edges = ss._graph_crossing_edges(_fixture_graph())
        by_pair = {(e["module_a"], e["module_b"]): e for e in edges}
        # core/utils: 4 qualifying edges (imports_from, calls x2, imports).
        self.assertIn(("core", "utils"), by_pair)
        self.assertEqual(by_pair[("core", "utils")]["weight"], 4)
        self.assertEqual(
            by_pair[("core", "utils")]["relations"], ["calls", "imports", "imports_from"]
        )
        # core/legacy: 1 qualifying edge.
        self.assertIn(("core", "legacy"), by_pair)
        self.assertEqual(by_pair[("core", "legacy")]["weight"], 1)
        # orphan/ has no crossing edges at all.
        self.assertNotIn(("core", "orphan"), by_pair)
        self.assertNotIn(("orphan", "core"), by_pair)

    def test_crossing_edges_excludes_structural_and_same_module_edges(self):
        edges = ss._graph_crossing_edges(_fixture_graph())
        pairs = {(e["module_a"], e["module_b"]) for e in edges}
        # "contains" (core_main -> core_main_run) and the same-module
        # utils_helpers_add -> utils_helpers_mul "calls" edge must not
        # produce any pair at all -- same exclusion as in-degree's.
        for pair in pairs:
            self.assertNotEqual(pair[0], pair[1])

    def test_crossing_edges_pair_order_independent_of_edge_direction(self):
        # A reversed graph (utils -> core instead of core -> utils) must
        # still produce the exact same sorted (module_a, module_b) pair --
        # an interface boundary is the pair, not the direction.
        graph = {
            "input_tokens": 0, "output_tokens": 0,
            "nodes": [
                {"id": "u", "label": "u", "file_type": "code", "source_file": "utils/u.py",
                 "source_location": "L1", "_origin": "ast"},
                {"id": "c", "label": "c", "file_type": "code", "source_file": "core/c.py",
                 "source_location": "L1", "_origin": "ast"},
            ],
            "links": [
                {"source": "u", "target": "c", "relation": "calls", "context": "calls",
                 "confidence": "EXTRACTED", "source_file": "x", "source_location": "L1",
                 "weight": 1.0},
            ],
        }
        edges = ss._graph_crossing_edges(graph)
        self.assertEqual(len(edges), 1)
        self.assertEqual((edges[0]["module_a"], edges[0]["module_b"]), ("core", "utils"))

    def test_interface_id_joins_sorted_pair(self):
        self.assertEqual(ss._interface_id("core", "utils"), "core--utils")


class NodeLevelCrossingEdgesTests(unittest.TestCase):
    """_node_level_crossing_edges() -- the node-identity-preserving sibling
    of _graph_crossing_edges() that _interface_call_sites() walks. Same
    _fixture_graph() as GraphCrossingEdgesTests, so the module-pair weights
    asserted there are the edge counts asserted here."""

    def test_endpoint_matching_returns_only_this_pairs_edges(self):
        # core/utils has 4 qualifying node-level edges per
        # test_crossing_edges_deduplicated_and_weighted; none of them may be
        # a core/legacy or same-module edge.
        edges = ss._node_level_crossing_edges(_fixture_graph(), "core", "utils")
        self.assertEqual(len(edges), 4)
        pairs = {(src["id"], dst["id"]) for src, dst in edges}
        self.assertEqual(
            pairs,
            {
                ("core_main", "utils_helpers_add"),
                ("core_main_run", "utils_helpers_add"),
                ("core_main_run", "utils_helpers_mul"),
                ("core_service", "utils_helpers_add"),
            },
        )

    def test_endpoint_matching_excludes_other_pairs(self):
        # core/legacy has exactly 1 edge; it must never show up when asking
        # for core/utils, and vice versa.
        edges = ss._node_level_crossing_edges(_fixture_graph(), "core", "legacy")
        self.assertEqual(len(edges), 1)
        src, dst = edges[0]
        self.assertEqual((src["id"], dst["id"]), ("core_main", "legacy_old"))

    def test_direction_independent_pair_lookup(self):
        # Asking for ("utils", "core") must return the exact same edges as
        # ("core", "utils") -- an interface pair has no inherent direction.
        forward = ss._node_level_crossing_edges(_fixture_graph(), "core", "utils")
        reverse = ss._node_level_crossing_edges(_fixture_graph(), "utils", "core")
        forward_pairs = {(s["id"], d["id"]) for s, d in forward}
        reverse_pairs = {(s["id"], d["id"]) for s, d in reverse}
        self.assertEqual(forward_pairs, reverse_pairs)

    def test_no_edges_for_unrelated_pair(self):
        self.assertEqual(ss._node_level_crossing_edges(_fixture_graph(), "core", "orphan"), [])


class InterfaceCallSitesTests(unittest.TestCase):
    """_interface_call_sites() -- closes F18 by deriving "path:Lline"
    citations from a targeted text search of each crossing edge's own
    source file, using the already-loaded graph (no re-running graphify).
    Fixture files/repo are entirely generic/synthetic, never modeled on
    any specific real repo's actual layout."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo_root = Path(self.tmp.name)

    def test_finds_textual_call_site_and_cites_the_source_edges_file(self):
        # core_main_run -> utils_helpers_add is one of the core/utils edges;
        # the citation must be against core/main.py (the SOURCE node's own
        # file), at the line where the TARGET's name actually appears.
        _write(
            self.repo_root / "core" / "main.py",
            "def run():\n    utils_helpers_add(1, 2)\n",
        )
        _write(self.repo_root / "utils" / "helpers.py", "def add():\n    pass\n")
        sites = ss._interface_call_sites(self.repo_root, _fixture_graph(), "core", "utils")
        self.assertIn("core/main.py:L2", sites)

    def test_stable_ordering_sorted_and_deduplicated(self):
        _write(
            self.repo_root / "core" / "main.py",
            "def run():\n"
            "    utils_helpers_add(1, 2)\n"
            "    utils_helpers_mul(3, 4)\n"
            "    utils_helpers_add(5, 6)\n",  # second mention -- must not duplicate
        )
        _write(self.repo_root / "core" / "service.py", "utils_helpers_add()\n")
        _write(self.repo_root / "utils" / "helpers.py", "pass\n")
        first = ss._interface_call_sites(self.repo_root, _fixture_graph(), "core", "utils")
        second = ss._interface_call_sites(self.repo_root, _fixture_graph(), "core", "utils")
        self.assertEqual(first, second)  # deterministic across repeated calls
        self.assertEqual(first, sorted(set(first)))  # sorted, no duplicates
        self.assertIn("core/main.py:L2", first)
        self.assertIn("core/main.py:L4", first)

    def test_endpoint_matching_never_cites_an_unrelated_pairs_file(self):
        _write(
            self.repo_root / "core" / "main.py",
            "def run():\n    legacy_old()\n    utils_helpers_add()\n",
        )
        sites = ss._interface_call_sites(self.repo_root, _fixture_graph(), "core", "utils")
        # legacy_old is core/legacy's target, not core/utils's -- must not
        # leak in even though it's textually present in the same file.
        self.assertTrue(all("legacy" not in s for s in sites))

    def test_absent_site_returns_empty_list_no_crash(self):
        # Source files exist but never mention the target names at all.
        _write(self.repo_root / "core" / "main.py", "def run():\n    pass\n")
        _write(self.repo_root / "utils" / "helpers.py", "def add():\n    pass\n")
        sites = ss._interface_call_sites(self.repo_root, _fixture_graph(), "core", "utils")
        self.assertEqual(sites, [])

    def test_missing_source_file_skipped_without_crash(self):
        # core/main.py and core/service.py are never written to disk at all.
        sites = ss._interface_call_sites(self.repo_root, _fixture_graph(), "core", "utils")
        self.assertEqual(sites, [])

    def test_no_edges_for_unrelated_pair_returns_empty_list(self):
        self.assertEqual(
            ss._interface_call_sites(self.repo_root, _fixture_graph(), "core", "orphan"), []
        )


class MergeInterfacesTests(unittest.TestCase):
    def test_new_pairs_added_as_pending(self):
        merged = ss._merge_interfaces([], [
            {"module_a": "core", "module_b": "utils", "relations": ["calls"], "weight": 2},
        ])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["id"], "core--utils")
        self.assertEqual(merged[0]["status"], "pending")
        self.assertEqual(merged[0]["weight"], 2)

    def test_settled_pair_never_overwritten(self):
        existing = [{
            "id": "core--utils", "module_a": "core", "module_b": "utils",
            "relations": ["calls"], "weight": 2, "status": "generated",
            "output_path": "docs/interfaces/core-to-utils.md",
            "generated_at": "2026-08-12T00:00:00Z", "defer_reason": None,
        }]
        # Fresh scan reports a different weight -- must not touch the
        # already-settled entry.
        merged = ss._merge_interfaces(existing, [
            {"module_a": "core", "module_b": "utils", "relations": ["calls", "imports"], "weight": 9},
        ])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["status"], "generated")
        self.assertEqual(merged[0]["weight"], 2)

    def test_pending_pair_refreshed_with_latest_weight(self):
        existing = [{
            "id": "core--utils", "module_a": "core", "module_b": "utils",
            "relations": ["calls"], "weight": 2, "status": "pending",
            "output_path": None, "generated_at": None, "defer_reason": None,
        }]
        merged = ss._merge_interfaces(existing, [
            {"module_a": "core", "module_b": "utils", "relations": ["calls", "imports"], "weight": 5},
        ])
        self.assertEqual(merged[0]["weight"], 5)
        self.assertEqual(merged[0]["relations"], ["calls", "imports"])

    def test_pair_no_longer_present_keeps_history(self):
        existing = [{
            "id": "legacy--orphan", "module_a": "legacy", "module_b": "orphan",
            "relations": ["calls"], "weight": 1, "status": "deferred",
            "output_path": None, "generated_at": None, "defer_reason": "endpoint not generated yet",
        }]
        merged = ss._merge_interfaces(existing, [])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["id"], "legacy--orphan")
        self.assertEqual(merged[0]["status"], "deferred")


class GraphRepoRootAlignmentTests(unittest.TestCase):
    """_graph_module_names() / _check_graph_repo_root_alignment() --
    defends against the graphify cwd/path-relativity footgun (see
    scaffold_state.py's own docstring for the mechanism): if `graphify
    update` ran from the wrong cwd relative to --repo-root, every
    source_file carries a different leading path segment, _module_of()
    extracts the wrong module name for every node, and every module
    silently defaults to in_degree 0 / Tier 3 with no signal anything went
    wrong. These tests cover the unit-level detection logic; ScanTests
    below covers the same footgun through the real scan() entry point."""

    def test_graph_module_names_extracts_all_distinct_modules(self):
        names = ss._graph_module_names(_fixture_graph())
        self.assertEqual(names, {"core", "utils", "legacy", "orphan"})

    def test_alignment_ok_when_overlap_is_full(self):
        warning = ss._check_graph_repo_root_alignment(
            {"core", "utils"}, ["core", "utils"], "graph.json"
        )
        self.assertIsNone(warning)

    def test_alignment_returns_none_when_either_set_is_empty(self):
        # Nothing to cross-check (empty graph, or no on-disk module
        # candidates yet) -- not this footgun's signature.
        self.assertIsNone(ss._check_graph_repo_root_alignment(set(), ["core"], "graph.json"))
        self.assertIsNone(ss._check_graph_repo_root_alignment({"core"}, [], "graph.json"))

    def test_alignment_warns_on_partial_overlap_below_threshold(self):
        # 1 of 5 disk modules found in the graph -- 20% < 50% threshold.
        warning = ss._check_graph_repo_root_alignment(
            {"core", "mystery1", "mystery2"},
            ["core", "utils", "legacy", "orphan", "generated"],
            "graph.json",
        )
        self.assertIsNotNone(warning)
        self.assertIn("20%", warning)
        self.assertIn("graph.json", warning)

    def test_alignment_ok_when_overlap_meets_threshold_exactly(self):
        # 1 of 2 -- exactly 50%. The check is a strict "<", so this must
        # NOT warn (matches TierAssignmentTests' own >= convention for
        # threshold boundaries).
        warning = ss._check_graph_repo_root_alignment(
            {"core"}, ["core", "utils"], "graph.json"
        )
        self.assertIsNone(warning)

    def test_alignment_raises_on_zero_overlap(self):
        with self.assertRaises(ss.GraphRepoRootMismatchError) as ctx:
            ss._check_graph_repo_root_alignment(
                {"src"}, ["core", "utils", "legacy"], "graph.json"
            )
        message = str(ctx.exception)
        self.assertIn("ZERO", message)
        self.assertIn("core", message)
        self.assertIn("src", message)


class GraphCepContaminationTests(unittest.TestCase):
    """_check_graph_cep_contamination() -- a different, thinner footgun
    than GraphRepoRootAlignmentTests above: the graph points at the right
    repo, but graphify was never scoped away from CEP's own installed
    footprint (skills/, docs, wizard scripts -- whatever this repo's own
    .cep-install.json manifest lists under owned_paths), so a slice of the
    graph's nodes are CEP's own internal wiring, not the target's code."""

    @staticmethod
    def _graph(*source_files):
        return {
            "nodes": [
                {"id": "n{}".format(i), "source_file": sf}
                for i, sf in enumerate(source_files)
            ]
        }

    def test_returns_none_when_no_manifest_present(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            root.mkdir()
            graph = self._graph("legacy/old.py", "core/main.py")
            self.assertIsNone(ss._check_graph_cep_contamination(root, graph))

    def test_returns_none_when_manifest_has_no_owned_paths(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            root.mkdir()
            _write(root / ".cep-install.json", json.dumps({}))
            graph = self._graph("legacy/old.py", "core/main.py")
            self.assertIsNone(ss._check_graph_cep_contamination(root, graph))

    def test_returns_none_when_graph_has_no_nodes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            root.mkdir()
            _write(
                root / ".cep-install.json", json.dumps({"owned_paths": ["legacy"]})
            )
            self.assertIsNone(ss._check_graph_cep_contamination(root, {"nodes": []}))

    def test_returns_none_when_contamination_is_below_threshold(self):
        # 1 of 20 nodes owned -- 5%, not strictly greater than the 5%
        # threshold, so this must NOT warn (matches the rest of this
        # module's own ">" -- not ">=" -- convention for a warn threshold).
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            root.mkdir()
            _write(
                root / ".cep-install.json", json.dumps({"owned_paths": ["legacy"]})
            )
            source_files = ["legacy/old.py"] + [
                "core/f{}.py".format(i) for i in range(19)
            ]
            warning = ss._check_graph_cep_contamination(root, self._graph(*source_files))
            self.assertIsNone(warning)

    def test_warns_when_contamination_exceeds_threshold(self):
        # 2 of 20 nodes owned -- 10% > 5% threshold.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            root.mkdir()
            _write(
                root / ".cep-install.json", json.dumps({"owned_paths": ["legacy"]})
            )
            source_files = ["legacy/old.py", "legacy/older.py"] + [
                "core/f{}.py".format(i) for i in range(18)
            ]
            warning = ss._check_graph_cep_contamination(root, self._graph(*source_files))
            self.assertIsNotNone(warning)
            self.assertIn("2/20", warning)
            self.assertIn(".cep-install.json", warning)

    def test_owned_file_path_counts_toward_contamination_too(self):
        # owned_paths isn't only directories -- a manifest-owned single
        # file (e.g. AGENTS.md, context-config.yaml) must count too if the
        # graph somehow indexed it.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            root.mkdir()
            _write(
                root / ".cep-install.json",
                json.dumps({"owned_paths": ["AGENTS.md"]}),
            )
            source_files = ["AGENTS.md"] + ["core/f{}.py".format(i) for i in range(18)]
            warning = ss._check_graph_cep_contamination(root, self._graph(*source_files))
            self.assertIsNotNone(warning)
            self.assertIn("1/19", warning)


class TierAssignmentTests(unittest.TestCase):
    def test_tier_for_graph_thresholds(self):
        # node_count > 0 in every non-empty case below -- a real module with
        # its own nodes, regardless of in-degree.
        self.assertEqual(ss._tier_for_graph(10, False, 5, 5), (1, "graph:in-degree"))
        self.assertEqual(ss._tier_for_graph(9, False, 5, 5), (2, "graph:in-degree"))
        self.assertEqual(ss._tier_for_graph(1, False, 5, 5), (2, "graph:in-degree"))
        # in_degree 0 with node_count > 0 -- a real tier-3 leaf (has its own
        # nodes, nothing else just imports it), not empty.
        self.assertEqual(ss._tier_for_graph(0, False, 5, 5), (3, "graph:in-degree"))
        self.assertEqual(ss._tier_for_graph(62, True, 5, 5), (0, "generated"))

    def test_tier_for_graph_zero_nodes_and_zero_files_is_empty_not_leaf(self):
        # node_count == 0 AND file_count == 0 -- nothing under this
        # directory at all. Distinct from the in_degree==0-but-has-nodes
        # leaf case above: this must never be offered as a selectable
        # tier-3 module.
        self.assertEqual(ss._tier_for_graph(0, False, 0, 0), (None, "empty"))
        # generated still takes priority over empty, same as it does over
        # every other tier.
        self.assertEqual(ss._tier_for_graph(0, True, 0, 0), (0, "generated"))

    def test_tier_for_graph_zero_nodes_with_files_falls_back_to_file_count(self):
        # Zero graph nodes but real files on disk -- a directory graphify
        # never walked, or one holding assets it doesn't traverse. That's
        # not empty: tier it off file_count exactly as heuristic mode
        # would, but with a basis string that records the fallback so the
        # state file never claims a graph signal it didn't have.
        fallback = "heuristic:file-count (no graph nodes)"
        self.assertEqual(ss._tier_for_graph(0, False, 0, 50), (1, fallback))
        self.assertEqual(ss._tier_for_graph(0, False, 0, 49), (2, fallback))
        self.assertEqual(ss._tier_for_graph(0, False, 0, 1), (2, fallback))
        # in_degree is irrelevant on this branch -- there are no nodes for
        # anything to point at, so the file-count tier stands either way.
        self.assertEqual(ss._tier_for_graph(12, False, 0, 1), (2, fallback))
        # generated still wins over the fallback, same as over empty.
        self.assertEqual(ss._tier_for_graph(0, True, 0, 7), (0, "generated"))
        # The tier must agree with what heuristic mode would have said --
        # only the basis label differs.
        for file_count in (1, 49, 50, 500):
            self.assertEqual(
                ss._tier_for_graph(0, False, 0, file_count)[0],
                ss._tier_for_heuristic(file_count, False)[0],
            )

    def test_tier_for_heuristic_thresholds(self):
        self.assertEqual(ss._tier_for_heuristic(50, False), (1, "heuristic:file-count"))
        self.assertEqual(ss._tier_for_heuristic(49, False), (2, "heuristic:file-count"))
        self.assertEqual(ss._tier_for_heuristic(1, False), (2, "heuristic:file-count"))
        self.assertEqual(ss._tier_for_heuristic(5, True), (0, "generated"))

    def test_tier_for_heuristic_zero_files_is_empty_not_leaf(self):
        self.assertEqual(ss._tier_for_heuristic(0, False), (None, "empty"))
        # generated still takes priority over empty.
        self.assertEqual(ss._tier_for_heuristic(0, True), (0, "generated"))


class ScanTests(unittest.TestCase):
    def _make_repo(self, root):
        _write(root / "core" / "main.py", "x")
        _write(root / "core" / "service.py", "x")
        _write(root / "utils" / "helpers.py", "x")
        _write(root / "legacy" / "old.py", "x")
        _write(root / "orphan" / "thing.py", "x")
        _write(root / "generated" / "stub.py", "x")

    def test_scan_heuristic_mode_recognizes_orphaned_cep_output_from_other_state(self):
        # Regression for the phantom-module contamination gap: a directory
        # of this skill's own prior output already sits in repo_root (e.g.
        # written by an earlier run, or a different/parallel state file),
        # but the state object passed to THIS scan() call has never heard
        # of it -- _settled_output_subtrees() is state-based and finds
        # nothing to exclude. Before the content-sniffed fallback existed,
        # this landed as an ordinary pending module full of "real" content;
        # it must now land as tier 0/skipped via the orphaned-output signal
        # instead, regardless of which state file is doing the scanning.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            self._make_repo(root)
            _write(root / "docs_out" / "core" / "CONTEXT.md", _CEP_OUTPUT_FRONTMATTER)
            _write(root / "docs_out" / "CODING-STANDARDS.md", _CEP_OUTPUT_FRONTMATTER)

            fresh_state = ss.empty_state()  # never recorded docs_out/ as output
            ss.scan(fresh_state, root, "heuristic")

            by_id = {m["id"]: m for m in fresh_state["modules"]}
            self.assertEqual(by_id["docs_out/"]["tier"], 0)
            self.assertEqual(by_id["docs_out/"]["status"], "skipped")
            self.assertIn("orphaned CEP-generated output", by_id["docs_out/"]["skip_reason"])
            pending_ids = {m["id"] for m in fresh_state["modules"] if m["status"] == "pending"}
            self.assertNotIn("docs_out/", pending_ids)

    def test_scan_graph_mode_assigns_expected_tiers(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            self._make_repo(root)
            graph_path = Path(d) / "graph.json"
            import json
            graph_path.write_text(json.dumps(_fixture_graph()), encoding="utf-8")

            state = ss.empty_state()
            ss.scan(state, root, "graphify", graph_path=graph_path)

            by_id = {m["id"]: m for m in state["modules"]}
            self.assertEqual(by_id["utils/"]["tier"], 2)
            self.assertEqual(by_id["legacy/"]["tier"], 2)
            self.assertEqual(by_id["orphan/"]["tier"], 3)
            self.assertEqual(by_id["generated/"]["tier"], 0)
            self.assertEqual(by_id["generated/"]["status"], "skipped")
            self.assertEqual(state["repo_scan"]["graph_source"], "graphify")
            # _fixture_graph()'s modules (core/utils/legacy/orphan) overlap
            # 4/5 = 80% with this repo's disk modules -- above the 50%
            # warn threshold, so alignment must be reported clean.
            self.assertIsNone(state["repo_scan"]["graph_module_overlap_warning"])

    def test_scan_heuristic_mode_labels_basis_lower_confidence(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            self._make_repo(root)
            state = ss.empty_state()
            ss.scan(state, root, "heuristic")
            by_id = {m["id"]: m for m in state["modules"]}
            for module_id in ("core/", "utils/", "legacy/", "orphan/"):
                self.assertEqual(by_id[module_id]["basis"], "heuristic:file-count")
            self.assertEqual(state["repo_scan"]["graph_source"], "heuristic")

    def test_scan_empty_directory_is_skipped_not_offered_pending(self):
        # A genuinely empty top-level directory (zero files, zero graph
        # nodes) must never be offered as a selectable "pending" module in
        # either mode -- it lands in the tier=None empty-skip bucket
        # instead, distinct from tier 0 generated/vendor.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            self._make_repo(root)
            (root / "trantor").mkdir()

            state = ss.empty_state()
            ss.scan(state, root, "heuristic")
            by_id = {m["id"]: m for m in state["modules"]}
            self.assertIsNone(by_id["trantor/"]["tier"])
            self.assertEqual(by_id["trantor/"]["status"], "skipped")
            self.assertEqual(by_id["trantor/"]["basis"], "empty")
            self.assertIn("empty", by_id["trantor/"]["skip_reason"])
            pending_ids = {m["id"] for m in state["modules"] if m["status"] == "pending"}
            self.assertNotIn("trantor/", pending_ids)

            graph_path = Path(d) / "graph.json"
            import json
            graph_path.write_text(json.dumps(_fixture_graph()), encoding="utf-8")
            graph_state = ss.empty_state()
            ss.scan(graph_state, root, "graphify", graph_path=graph_path)
            by_id_graph = {m["id"]: m for m in graph_state["modules"]}
            self.assertIsNone(by_id_graph["trantor/"]["tier"])
            self.assertEqual(by_id_graph["trantor/"]["status"], "skipped")
            self.assertEqual(by_id_graph["trantor/"]["basis"], "empty")
            pending_ids_graph = {
                m["id"] for m in graph_state["modules"] if m["status"] == "pending"
            }
            self.assertNotIn("trantor/", pending_ids_graph)

    def test_scan_graph_mode_keeps_directory_with_files_but_no_graph_nodes(self):
        # A directory with real files that graphify never indexed -- here a
        # folder of non-code assets, the shape _fixture_graph() has no
        # nodes for. Zero graph nodes on its own must NOT read as "empty":
        # the directory has content, so it stays a normal, selectable
        # module tiered off its file count, not a skipped one.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            self._make_repo(root)
            _write(root / "assets" / "logo.svg", "<svg/>")
            _write(root / "assets" / "theme.css", "body{}")
            _write(root / "assets" / "icons" / "check.svg", "<svg/>")

            graph_path = Path(d) / "graph.json"
            graph_path.write_text(json.dumps(_fixture_graph()), encoding="utf-8")

            state = ss.empty_state()
            ss.scan(state, root, "graphify", graph_path=graph_path)

            by_id = {m["id"]: m for m in state["modules"]}
            entry = by_id["assets/"]
            self.assertIsNotNone(entry["tier"])
            self.assertEqual(entry["tier"], 2)
            self.assertEqual(entry["file_count"], 3)
            self.assertEqual(entry["basis"], "heuristic:file-count (no graph nodes)")
            self.assertEqual(entry["status"], "pending")
            self.assertIsNone(entry["skip_reason"])
            pending_ids = {m["id"] for m in state["modules"] if m["status"] == "pending"}
            self.assertIn("assets/", pending_ids)
            skipped_ids = {m["id"] for m in state["modules"] if m["status"] == "skipped"}
            self.assertNotIn("assets/", skipped_ids)

    def test_scan_rejects_bad_graph_mode(self):
        with tempfile.TemporaryDirectory() as d:
            state = ss.empty_state()
            with self.assertRaises(ValueError):
                ss.scan(state, d, "made-up-mode")

    def test_scan_graphify_mode_without_graph_path_raises(self):
        with tempfile.TemporaryDirectory() as d:
            state = ss.empty_state()
            with self.assertRaises(ValueError):
                ss.scan(state, d, "graphify")

    def test_scan_never_overwrites_settled_module(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            self._make_repo(root)
            state = ss.empty_state()
            ss.scan(state, root, "heuristic")
            ss.mark_generated(state, "core/", "docs/core/CONTEXT.md")

            # Re-scan (no --rescan) must leave the generated module alone.
            ss.scan(state, root, "heuristic")
            by_id = {m["id"]: m for m in state["modules"]}
            self.assertEqual(by_id["core/"]["status"], "generated")
            self.assertEqual(by_id["core/"]["output_path"], "docs/core/CONTEXT.md")

    def test_scan_without_rescan_leaves_pending_tier_data_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            self._make_repo(root)
            state = ss.empty_state()
            ss.scan(state, root, "heuristic")
            first_pass = {m["id"]: dict(m) for m in state["modules"]}

            # Add a new file to utils/ -- without --rescan this must not
            # change utils/'s already-recorded file_count.
            _write(root / "utils" / "extra.py", "x")
            ss.scan(state, root, "heuristic")
            by_id = {m["id"]: m for m in state["modules"]}
            self.assertEqual(by_id["utils/"]["file_count"], first_pass["utils/"]["file_count"])

    def test_scan_with_rescan_recomputes_pending_modules(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            self._make_repo(root)
            state = ss.empty_state()
            ss.scan(state, root, "heuristic")

            _write(root / "utils" / "extra.py", "x")
            ss.scan(state, root, "heuristic", rescan=True)
            by_id = {m["id"]: m for m in state["modules"]}
            self.assertEqual(by_id["utils/"]["file_count"], 2)

    def test_scan_preserves_removed_module_history(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            self._make_repo(root)
            state = ss.empty_state()
            ss.scan(state, root, "heuristic")
            ss.mark_skipped(state, "orphan/", "not worth covering")

            import shutil
            shutil.rmtree(root / "orphan")
            ss.scan(state, root, "heuristic")
            by_id = {m["id"]: m for m in state["modules"]}
            self.assertIn("orphan/", by_id)
            self.assertEqual(by_id["orphan/"]["status"], "skipped")

    def test_scan_raises_and_writes_no_state_on_total_graph_mismatch(self):
        # Reproduces the graphify cwd/path-relativity footgun end-to-end:
        # every node's source_file carries an extra unexpected "src/"
        # segment (the exact shape produced when `graphify update` runs
        # from the wrong cwd relative to --repo-root).
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            self._make_repo(root)
            graph = _fixture_graph()
            for node in graph["nodes"]:
                if node["source_file"]:
                    node["source_file"] = "src/" + node["source_file"]
            graph_path = Path(d) / "graph.json"
            import json
            graph_path.write_text(json.dumps(graph), encoding="utf-8")

            state = ss.empty_state()
            with self.assertRaises(ss.GraphRepoRootMismatchError):
                ss.scan(state, root, "graphify", graph_path=graph_path)
            # No partial/corrupt state written on the failure path -- same
            # posture as _load_graph()'s own missing-file failure.
            self.assertEqual(state["modules"], [])
            # repo_scan is untouched too -- the raise happens before scan()
            # assigns its new value, so it's still the pre-scan default.
            self.assertIsNone(state["repo_scan"]["scanned_at"])

    def test_scan_persists_and_reports_warning_on_partial_graph_mismatch(self):
        # Only core/'s nodes keep their real path; every other node moves
        # under an unrelated "mystery/" segment -- 1 of 5 disk modules
        # (20%) overlaps, below the 50% warn threshold.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            self._make_repo(root)
            graph = _fixture_graph()
            for node in graph["nodes"]:
                sf = node["source_file"]
                if sf and not sf.startswith("core/"):
                    node["source_file"] = "mystery/" + sf
            graph_path = Path(d) / "graph.json"
            import json
            graph_path.write_text(json.dumps(graph), encoding="utf-8")

            state = ss.empty_state()
            ss.scan(state, root, "graphify", graph_path=graph_path)  # must not raise

            warning = state["repo_scan"]["graph_module_overlap_warning"]
            self.assertIsNotNone(warning)
            self.assertIn("20%", warning)
            # Non-fatal: tiering still ran and state was still written.
            self.assertTrue(len(state["modules"]) > 0)

    def test_scan_reports_contamination_warning_when_manifest_owned_path_dominates_graph(self):
        # legacy/'s single node is 1 of the fixture graph's 8 total nodes
        # (12.5%) -- above the 5% contamination warn threshold once
        # legacy/ is marked CEP-owned in the manifest.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            self._make_repo(root)
            _write(
                root / ".cep-install.json",
                json.dumps({"owned_paths": ["legacy"]}),
            )
            graph_path = Path(d) / "graph.json"
            graph_path.write_text(json.dumps(_fixture_graph()), encoding="utf-8")

            state = ss.empty_state()
            ss.scan(state, root, "graphify", graph_path=graph_path)  # must not raise

            warning = state["repo_scan"]["graph_cep_contamination_warning"]
            self.assertIsNotNone(warning)
            self.assertIn("1/8", warning)
            # Non-fatal: tiering still ran and state was still written.
            self.assertTrue(len(state["modules"]) > 0)

    def test_scan_stays_silent_on_contamination_below_threshold(self):
        # A manifest whose owned_paths never intersect the graph at all
        # contaminates 0 of 8 nodes -- well under the 5% threshold, so no
        # warning at all (None, not an empty string).
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            self._make_repo(root)
            _write(
                root / ".cep-install.json",
                json.dumps({"owned_paths": ["nonexistent-dir"]}),
            )
            graph_path = Path(d) / "graph.json"
            graph_path.write_text(json.dumps(_fixture_graph()), encoding="utf-8")

            state = ss.empty_state()
            ss.scan(state, root, "graphify", graph_path=graph_path)

            self.assertIsNone(state["repo_scan"]["graph_cep_contamination_warning"])

    def test_scan_stays_silent_on_contamination_with_no_manifest(self):
        # No .cep-install.json at all -- nothing to check against, so this
        # must stay silent rather than guess (same "None means no signal"
        # convention _read_cep_manifest() itself documents).
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            self._make_repo(root)
            graph_path = Path(d) / "graph.json"
            graph_path.write_text(json.dumps(_fixture_graph()), encoding="utf-8")

            state = ss.empty_state()
            ss.scan(state, root, "graphify", graph_path=graph_path)

            self.assertIsNone(state["repo_scan"]["graph_cep_contamination_warning"])

    def test_scan_graphify_mode_populates_interfaces(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            self._make_repo(root)
            graph_path = Path(d) / "graph.json"
            import json
            graph_path.write_text(json.dumps(_fixture_graph()), encoding="utf-8")

            state = ss.empty_state()
            ss.scan(state, root, "graphify", graph_path=graph_path)

            by_id = {i["id"]: i for i in state["interfaces"]}
            self.assertIn("core--utils", by_id)
            self.assertIn("core--legacy", by_id)
            self.assertEqual(by_id["core--utils"]["status"], "pending")

    def test_scan_heuristic_mode_leaves_interfaces_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            self._make_repo(root)
            state = ss.empty_state()
            state["interfaces"] = [{"id": "prior--entry", "status": "pending"}]
            ss.scan(state, root, "heuristic")
            self.assertEqual(state["interfaces"], [{"id": "prior--entry", "status": "pending"}])

    def test_settled_output_root_is_excluded_from_rescan(self):
        # The exact reclassification bug: core/'s draft is generated to
        # org/core/CONTEXT.md (a resolved How-L2 output root sitting at the
        # repo's own top level). A later rescan must not enumerate "org/"
        # as a brand-new pending module just because it now exists on disk.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            self._make_repo(root)
            state = ss.empty_state()
            ss.scan(state, root, "heuristic")
            ss.mark_generated(state, "core/", "org/core/CONTEXT.md")
            _write(root / "org" / "core" / "CONTEXT.md", "# core")

            ss.scan(state, root, "heuristic")
            ids = {m["id"] for m in state["modules"]}
            self.assertNotIn("org/", ids)

            # Idempotent: running the same rescan again changes nothing.
            ss.scan(state, root, "heuristic", rescan=True)
            ids_again = {m["id"] for m in state["modules"]}
            self.assertNotIn("org/", ids_again)

    def test_settled_output_root_survives_rescan_alongside_a_rendered_router_file(self):
        # Real-world shape the synthetic fixture above misses: SKILL.md
        # Step 5b writes CEP-INDEX.md straight to disk under the resolved
        # How-L2 root on every `render-index` call, alongside the tracked
        # module/repo_doc/interface drafts -- not just the drafts alone.
        # That router file is real content sitting under "org/" that the
        # settled-output-root purity check must also account for, or the
        # whole directory fails purity and "org/" comes back as a pending
        # module on the very next scan even though every module inside it
        # was properly marked generated. This is the exact gap the fixed
        # regression test (`test_settled_output_root_is_excluded_from_rescan`)
        # did not cover: it never wrote a router file to disk at all, so a
        # build of this file that dropped index tracking still passed it.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            self._make_repo(root)
            state = ss.empty_state()
            ss.scan(state, root, "heuristic")
            ss.mark_generated(state, "core/", "org/core/CONTEXT.md")
            _write(root / "org" / "core" / "CONTEXT.md", "# core")
            ss.mark_index_rendered(state, "org/CEP-INDEX.md")
            _write(root / "org" / "CEP-INDEX.md", "# CEP Index")

            ss.scan(state, root, "heuristic")
            ids = {m["id"] for m in state["modules"]}
            self.assertNotIn("org/", ids)

            # SKILL.md re-renders the index after every module, so the
            # router file keeps being (re)written between scans too.
            ss.scan(state, root, "heuristic", rescan=True)
            ids_again = {m["id"] for m in state["modules"]}
            self.assertNotIn("org/", ids_again)

    def test_settled_output_root_from_repo_doc_excluded_from_rescan(self):
        # A repo-wide doc's output_path carries the exact same exposure as
        # a module's -- e.g. coding_standards resolved to org/docs/....
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            self._make_repo(root)
            state = ss.empty_state()
            ss.scan(state, root, "heuristic")
            ss.mark_repo_doc_generated(state, "coding_standards", "org/docs/CODING-STANDARDS.md")
            _write(root / "org" / "docs" / "CODING-STANDARDS.md", "# standards")

            ss.scan(state, root, "heuristic")
            ids = {m["id"] for m in state["modules"]}
            self.assertNotIn("org/", ids)

    def test_bare_top_level_output_file_does_not_suppress_a_real_module(self):
        # A repo doc's output_path with no subdirectory nesting (e.g. a
        # root-level CEP-INDEX.md) has nothing underneath it to protect --
        # it must not suppress an unrelated same-named top-level module.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            self._make_repo(root)
            _write(root / "docs" / "readme.md", "x")
            state = ss.empty_state()
            ss.mark_repo_doc_generated(state, "coding_standards", "docs")
            ss.scan(state, root, "heuristic")
            ids = {m["id"] for m in state["modules"]}
            self.assertIn("docs/", ids)

    def test_stale_pending_entry_at_settled_output_root_is_dropped_on_rescan(self):
        # Self-healing: a TRIAGE-STATE.json produced by an older, buggy
        # build of this file may already have "org/" recorded as a
        # mistaken "pending" module entry. A fixed rescan must drop that
        # stale entry rather than carry it forward forever.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            self._make_repo(root)
            state = ss.empty_state()
            ss.scan(state, root, "heuristic")
            ss.mark_generated(state, "core/", "org/core/CONTEXT.md")
            _write(root / "org" / "core" / "CONTEXT.md", "# core")
            # Simulate the pre-fix corruption directly, bypassing scan().
            state["modules"].append({
                "id": "org/", "tier": 2, "in_degree": None, "file_count": 1,
                "basis": "heuristic:file-count", "status": "pending",
                "generated_at": None, "output_path": None, "skip_reason": None,
            })

            ss.scan(state, root, "heuristic")
            ids = {m["id"] for m in state["modules"]}
            self.assertNotIn("org/", ids)

    def test_stale_settled_entry_at_output_root_is_still_preserved(self):
        # A settled ("generated"/"skipped") entry is real decision history
        # even if its id happens to collide with a settled output root --
        # only "pending" (never a real decision) is dropped, per the
        # docstring's own distinction.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            self._make_repo(root)
            state = ss.empty_state()
            ss.scan(state, root, "heuristic")
            ss.mark_generated(state, "core/", "org/core/CONTEXT.md")
            _write(root / "org" / "core" / "CONTEXT.md", "# core")
            state["modules"].append({
                "id": "org/", "tier": 2, "in_degree": None, "file_count": 1,
                "basis": "heuristic:file-count", "status": "skipped",
                "generated_at": None, "output_path": None,
                "skip_reason": "manually reviewed",
            })

            ss.scan(state, root, "heuristic")
            by_id = {m["id"]: m for m in state["modules"]}
            self.assertIn("org/", by_id)
            self.assertEqual(by_id["org/"]["status"], "skipped")

    def test_settled_output_sharing_an_ancestor_with_a_real_module_is_not_dropped(self):
        # The over-broad-exclusion-key bug: an earlier, buggy build keyed
        # exclusion purely off output_path's first path segment, so a
        # generation output resolved to e.g. "docs/style-guide/core/
        # CONTEXT.md" would silently and unrecoverably delete any
        # unrelated *pending* module that happened to already be named
        # "docs/" -- with no skip_reason, no message, and (because the
        # exclusion also removed "docs" from module_names) no way back via
        # --rescan either. Unlike every other settled-output-root fixture
        # above, "docs" here holds REAL, unrelated content of its own
        # (architecture.md) alongside the nested generated file, so it
        # must survive as a normal, still-pending module.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            self._make_repo(root)
            _write(root / "docs" / "architecture.md", "# architecture")
            state = ss.empty_state()

            ss.scan(state, root, "heuristic")
            self.assertIn("docs/", {m["id"] for m in state["modules"]})

            ss.mark_generated(state, "core/", "docs/style-guide/core/CONTEXT.md")
            _write(root / "docs" / "style-guide" / "core" / "CONTEXT.md", "# core")

            ss.scan(state, root, "heuristic")
            by_id = {m["id"]: m for m in state["modules"]}
            self.assertIn("docs/", by_id)
            self.assertEqual(by_id["docs/"]["status"], "pending")

            # Rescanning must re-tier "docs/" from its real content alone
            # -- the generated CONTEXT.md sitting inside it must not count
            # toward its own file_count/tier basis.
            ss.scan(state, root, "heuristic", rescan=True)
            by_id = {m["id"]: m for m in state["modules"]}
            self.assertIn("docs/", by_id)
            self.assertEqual(by_id["docs/"]["file_count"], 1)

    def test_settled_output_at_top_level_does_not_swallow_its_own_directory(self):
        # The same over-broad-exclusion bug as above, but in the narrower
        # shape an adversarial review found survives the first fix: a
        # repo doc's output_path with exactly TWO path components (e.g.
        # "conventions/CODING-STANDARDS.md") has no intermediate directory
        # of its own -- "the directory it lives in" IS the top-level
        # directory itself. Treating that like the 3+-component case
        # (recording resolved.parent, i.e. the top-level directory, as a
        # "protected subtree") makes the purity check trivially true for
        # ANY content under that name, so a real, pre-existing
        # "conventions/" directory holding unrelated real files (e.g. a
        # hand-written naming.md) would be silently misclassified as pure
        # settled output and dropped, right along with its real content.
        # "conventions/" must survive as a normal, still-pending module,
        # with only the one generated file excluded from its tiering.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            self._make_repo(root)
            _write(root / "conventions" / "naming.md", "# naming")
            state = ss.empty_state()

            ss.scan(state, root, "heuristic")
            self.assertIn("conventions/", {m["id"] for m in state["modules"]})

            ss.mark_repo_doc_generated(
                state, "coding_standards", "conventions/CODING-STANDARDS.md"
            )
            _write(root / "conventions" / "CODING-STANDARDS.md", "# standards")

            ss.scan(state, root, "heuristic")
            by_id = {m["id"]: m for m in state["modules"]}
            self.assertIn("conventions/", by_id)
            self.assertEqual(by_id["conventions/"]["status"], "pending")

            # Rescanning must re-tier "conventions/" from its real content
            # alone -- the generated CODING-STANDARDS.md sitting inside it
            # must not count toward its own file_count/tier basis.
            ss.scan(state, root, "heuristic", rescan=True)
            by_id = {m["id"]: m for m in state["modules"]}
            self.assertIn("conventions/", by_id)
            self.assertEqual(by_id["conventions/"]["file_count"], 1)

    def test_settled_output_root_tolerates_pre_existing_repo_doc_never_marked(self):
        # Adversarial-review finding F1 against the router-file-tracking
        # fix: SKILL.md Step 5c's "already exists: skip it silently"
        # branch for CODING-STANDARDS.md/TESTING-GUIDELINES.md calls no
        # mark-* command at all when the doc was already on disk before
        # this run started -- so its output_path is never recorded in
        # state, even though the file is real, CEP-authored content
        # sitting right under the resolved output root. A later
        # same-state rescan must not reclassify that output root as
        # pending just because this one conventionally-named file was
        # never tracked.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            self._make_repo(root)
            state = ss.empty_state()
            ss.scan(state, root, "heuristic")
            ss.mark_generated(state, "core/", "org/core/CONTEXT.md")
            _write(root / "org" / "core" / "CONTEXT.md", "# core")
            # Already on disk but never tracked via
            # mark-repo-doc-generated -- the exact Step 5c gap.
            _write(root / "org" / "CODING-STANDARDS.md", "# standards")

            ss.scan(state, root, "heuristic")
            ids = {m["id"] for m in state["modules"]}
            self.assertNotIn("org/", ids)

    def test_settled_output_root_tolerates_dotfiles(self):
        # A ".gitkeep" (or similar) placeholder is essentially guaranteed
        # to exist in any git-tracked repo's output directory (adversarial
        # review finding F1c) and is never a reason to reclassify a
        # resolved output root as pending -- mirrors the existing
        # precedent that dot-*directories* are already invisible to this
        # whole mechanism (see _prune_ignored()).
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            self._make_repo(root)
            state = ss.empty_state()
            ss.scan(state, root, "heuristic")
            ss.mark_generated(state, "core/", "org/core/CONTEXT.md")
            _write(root / "org" / "core" / "CONTEXT.md", "# core")
            _write(root / "org" / ".gitkeep", "")

            ss.scan(state, root, "heuristic")
            ids = {m["id"] for m in state["modules"]}
            self.assertNotIn("org/", ids)

    def test_settled_output_root_does_not_tolerate_nested_dotfile(self):
        # The dotfile tolerance above is deliberately scoped to this
        # directory's own top level only (round-2 adversarial review
        # finding C1). A dotfile several levels *below* the output root's
        # top level -- e.g. a config/ subdirectory's own .eslintrc/.env,
        # real human-authored project content, not an inert CEP-adjacent
        # placeholder -- must still fail purity like any other untracked
        # file, so the directory correctly stays a pending candidate.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            self._make_repo(root)
            state = ss.empty_state()
            ss.scan(state, root, "heuristic")
            ss.mark_generated(state, "core/", "org/core/CONTEXT.md")
            _write(root / "org" / "core" / "CONTEXT.md", "# core")
            _write(root / "org" / "nested" / ".env", "SECRET=1")

            ss.scan(state, root, "heuristic")
            ids = {m["id"] for m in state["modules"]}
            self.assertIn("org/", ids)

    def test_settled_output_root_still_flags_untracked_unconventional_file(self):
        # Control for the two tolerances directly above: an untracked
        # file with an ordinary, non-CEP-conventional name must still
        # fail purity. Both new tolerances are deliberately narrow --
        # they must not swallow arbitrary real, unrelated content, the
        # same design intent that already governs the 2-component
        # "files" tracking above.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            self._make_repo(root)
            state = ss.empty_state()
            ss.scan(state, root, "heuristic")
            ss.mark_generated(state, "core/", "org/core/CONTEXT.md")
            _write(root / "org" / "core" / "CONTEXT.md", "# core")
            _write(root / "org" / "README.md", "# untracked, unrelated")

            ss.scan(state, root, "heuristic")
            ids = {m["id"] for m in state["modules"]}
            self.assertIn("org/", ids)

    def test_settled_output_root_survives_rescan_with_legacy_state_missing_index_key(self):
        # Adversarial-review finding F2: a TRIAGE-STATE.json written by a
        # run that predates the "index" key entirely (i.e. before the
        # router-file-tracking fix existed) has no record of CEP-INDEX.md
        # at all -- not even a null placeholder, the key is simply
        # absent -- even though the file is already on disk from that
        # earlier run's own render-index calls. A finished run never gets
        # a second chance to record it, since render-index is only called
        # during generation, not on a mere resumed/continued scan. That
        # must not perpetually reclassify the output root as pending on
        # every subsequent same-state rescan.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            self._make_repo(root)
            state = ss.empty_state()
            ss.scan(state, root, "heuristic")
            ss.mark_generated(state, "core/", "org/core/CONTEXT.md")
            _write(root / "org" / "core" / "CONTEXT.md", "# core")
            _write(root / "org" / "CEP-INDEX.md", "# CEP Index")
            # Simulate a pre-fix state file: no "index" key present.
            self.assertIn("index", state)
            del state["index"]

            ss.scan(state, root, "heuristic")
            ids = {m["id"] for m in state["modules"]}
            self.assertNotIn("org/", ids)

    def test_settled_output_root_requires_tracking_for_nonconventional_router_filename(self):
        # Negative control isolating what actually does the work for the
        # general case (responds to F4's critique that the original
        # router-file regression test's negative control was weak -- it
        # failed pre-fix with AttributeError, not a behavioral assertion
        # failure): a router file rendered to a *non*-default filename
        # (an --out override) is NOT covered by the narrow
        # conventional-filename tolerance above, so it must still be
        # tracked via mark_index_rendered. This proves that mechanism,
        # not the tolerance list, is what makes the router-file fix hold
        # in the general case -- the tolerance list only ever helps the
        # one default filename.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            self._make_repo(root)
            state = ss.empty_state()
            ss.scan(state, root, "heuristic")
            ss.mark_generated(state, "core/", "org/core/CONTEXT.md")
            _write(root / "org" / "core" / "CONTEXT.md", "# core")
            # On disk but never tracked, and not a conventional filename.
            _write(root / "org" / "ROUTER.md", "# router")

            ss.scan(state, root, "heuristic")
            ids = {m["id"] for m in state["modules"]}
            self.assertIn("org/", ids)

            # Tracking it via mark_index_rendered fixes it, same as the
            # conventional CEP-INDEX.md case above.
            ss.mark_index_rendered(state, "org/ROUTER.md")
            ss.scan(state, root, "heuristic", rescan=True)
            ids_again = {m["id"] for m in state["modules"]}
            self.assertNotIn("org/", ids_again)


class SettledOutputRootNamesTests(unittest.TestCase):
    def test_multi_component_module_output_path_yields_first_segment(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            state = ss.empty_state()
            state["modules"].append({"id": "core/", "output_path": "org/core/CONTEXT.md"})
            self.assertEqual(ss._settled_output_root_names(root, state), {"org"})

    def test_bare_top_level_output_path_yields_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            state = ss.empty_state()
            state["modules"].append({"id": "core/", "output_path": "CONTEXT.md"})
            self.assertEqual(ss._settled_output_root_names(root, state), set())

    def test_missing_or_none_output_path_is_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            state = ss.empty_state()
            state["modules"].append({"id": "core/", "output_path": None})
            state["modules"].append({"id": "utils/"})
            self.assertEqual(ss._settled_output_root_names(root, state), set())

    def test_output_path_escaping_repo_root_is_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            root.mkdir()
            state = ss.empty_state()
            state["modules"].append({"id": "core/", "output_path": "../outside/deep/file.md"})
            self.assertEqual(ss._settled_output_root_names(root, state), set())

    def test_repo_doc_output_path_counts(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            state = ss.empty_state()
            state["repo_docs"]["coding_standards"]["output_path"] = "org/docs/CODING-STANDARDS.md"
            self.assertEqual(ss._settled_output_root_names(root, state), {"org"})

    def test_interface_output_path_counts(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            state = ss.empty_state()
            state["interfaces"].append({
                "id": "core--utils", "output_path": "org/interfaces/core--utils.md",
            })
            self.assertEqual(ss._settled_output_root_names(root, state), {"org"})


class MarkGeneratedSkippedTests(unittest.TestCase):
    def _state_with_pending_module(self):
        state = ss.empty_state()
        state["modules"].append({
            "id": "core/", "tier": 1, "in_degree": 12, "file_count": 4,
            "basis": "graph:in-degree", "status": "pending",
            "generated_at": None, "output_path": None, "skip_reason": None,
        })
        return state

    def test_mark_generated_sets_fields(self):
        state = self._state_with_pending_module()
        module = ss.mark_generated(state, "core/", "docs/core/CONTEXT.md")
        self.assertEqual(module["status"], "generated")
        self.assertEqual(module["output_path"], "docs/core/CONTEXT.md")
        self.assertIsNotNone(module["generated_at"])

    def test_mark_generated_refuses_if_not_pending(self):
        state = self._state_with_pending_module()
        ss.mark_generated(state, "core/", "docs/core/CONTEXT.md")
        with self.assertRaises(ValueError):
            ss.mark_generated(state, "core/", "docs/core/CONTEXT.md")

    def test_mark_skipped_sets_reason(self):
        state = self._state_with_pending_module()
        module = ss.mark_skipped(state, "core/", "out of scope this run")
        self.assertEqual(module["status"], "skipped")
        self.assertEqual(module["skip_reason"], "out of scope this run")

    def test_mark_unknown_module_raises(self):
        state = ss.empty_state()
        with self.assertRaises(ValueError):
            ss.mark_generated(state, "does-not-exist/", "x")


class RepoDocStateTests(unittest.TestCase):
    def test_empty_state_has_both_kinds_pending(self):
        state = ss.empty_state()
        self.assertEqual(state["repo_docs"]["coding_standards"]["status"], "pending")
        self.assertEqual(state["repo_docs"]["testing_guidelines"]["status"], "pending")

    def test_mark_repo_doc_generated_sets_fields(self):
        state = ss.empty_state()
        doc = ss.mark_repo_doc_generated(state, "coding_standards", "org/CODING-STANDARDS.md")
        self.assertEqual(doc["status"], "generated")
        self.assertEqual(doc["output_path"], "org/CODING-STANDARDS.md")
        self.assertIsNotNone(doc["generated_at"])

    def test_mark_repo_doc_generated_refuses_if_not_pending(self):
        state = ss.empty_state()
        ss.mark_repo_doc_generated(state, "coding_standards", "org/CODING-STANDARDS.md")
        with self.assertRaises(ValueError):
            ss.mark_repo_doc_generated(state, "coding_standards", "org/CODING-STANDARDS.md")

    def test_mark_repo_doc_skipped_sets_reason(self):
        state = ss.empty_state()
        doc = ss.mark_repo_doc_skipped(state, "testing_guidelines", "already covered elsewhere")
        self.assertEqual(doc["status"], "skipped")
        self.assertEqual(doc["skip_reason"], "already covered elsewhere")

    def test_unknown_repo_doc_kind_raises(self):
        state = ss.empty_state()
        with self.assertRaises(ValueError):
            ss.mark_repo_doc_generated(state, "not-a-real-kind", "x")

    def test_load_state_backfills_repo_docs_on_older_schema(self):
        state = {"schema_version": 1, "repo_scan": {}, "modules": []}
        filled = ss._ensure_repo_docs(state.get("repo_docs"))
        self.assertIn("coding_standards", filled)
        self.assertIn("testing_guidelines", filled)


class InterfaceDocStateTests(unittest.TestCase):
    def _state_with_interfaces(self):
        state = ss.empty_state()
        state["modules"] = [
            {"id": "core/", "tier": 1, "in_degree": 12, "file_count": 4,
             "basis": "graph:in-degree", "status": "generated",
             "generated_at": "now", "output_path": "org/core/CONTEXT.md", "skip_reason": None},
            {"id": "utils/", "tier": 2, "in_degree": 1, "file_count": 2,
             "basis": "graph:in-degree", "status": "pending",
             "generated_at": None, "output_path": None, "skip_reason": None},
        ]
        state["interfaces"] = [
            {"id": "core--utils", "module_a": "core", "module_b": "utils",
             "relations": ["calls"], "weight": 4, "status": "pending",
             "output_path": None, "generated_at": None, "defer_reason": None},
        ]
        return state

    def test_mark_interface_generated_sets_fields(self):
        state = self._state_with_interfaces()
        interface = ss.mark_interface_generated(state, "core--utils", "org/interfaces/core-to-utils.md")
        self.assertEqual(interface["status"], "generated")
        self.assertEqual(interface["output_path"], "org/interfaces/core-to-utils.md")
        self.assertIsNotNone(interface["generated_at"])

    def test_mark_interface_generated_refuses_if_not_pending(self):
        state = self._state_with_interfaces()
        ss.mark_interface_generated(state, "core--utils", "org/interfaces/core-to-utils.md")
        with self.assertRaises(ValueError):
            ss.mark_interface_generated(state, "core--utils", "org/interfaces/core-to-utils.md")

    def test_mark_interface_deferred_sets_reason(self):
        state = self._state_with_interfaces()
        interface = ss.mark_interface_deferred(state, "core--utils", "utils/ not yet generated this run")
        self.assertEqual(interface["status"], "deferred")
        self.assertEqual(interface["defer_reason"], "utils/ not yet generated this run")

    def test_mark_unknown_interface_raises(self):
        state = ss.empty_state()
        with self.assertRaises(ValueError):
            ss.mark_interface_generated(state, "does-not-exist--either", "x")

    def test_list_interfaces_eligible_only_requires_both_endpoints_generated(self):
        state = self._state_with_interfaces()
        # utils/ is still "pending" (not generated) -- core--utils must not
        # be eligible yet.
        self.assertEqual(ss.list_interfaces(state, eligible_only=True), [])

        ss.mark_generated(state, "utils/", "org/utils/CONTEXT.md")
        eligible = ss.list_interfaces(state, eligible_only=True)
        self.assertEqual([i["id"] for i in eligible], ["core--utils"])

    def test_list_interfaces_without_filter_returns_everything(self):
        state = self._state_with_interfaces()
        self.assertEqual(len(ss.list_interfaces(state)), 1)

    def test_list_interfaces_eligible_only_accepts_tier3_leaf_endpoint(self):
        # Bug: a tier-3 leaf never gets a context_md packet by design
        # (PACKET_ELIGIBLE_MODULE_TIERS = (1, 2)) and goes straight from
        # "pending" to "skipped" -- so it can never reach "generated", full
        # stop. Any interface pair touching it was therefore structurally
        # unable to ever become eligible. A tier-3 "skipped" endpoint must
        # now count as settled for eligibility purposes, same as a
        # "generated" one.
        state = ss.empty_state()
        state["modules"] = [
            {"id": "core/", "tier": 1, "in_degree": 12, "file_count": 4,
             "basis": "graph:in-degree", "status": "generated",
             "generated_at": "now", "output_path": "org/core/CONTEXT.md", "skip_reason": None},
            {"id": "leaf/", "tier": 3, "in_degree": 0, "file_count": 1,
             "basis": "graph:in-degree", "status": "skipped",
             "generated_at": None, "output_path": None,
             "skip_reason": "tier 3 -- no context_md packet planned by design"},
        ]
        state["interfaces"] = [
            {"id": "core--leaf", "module_a": "core", "module_b": "leaf",
             "relations": ["calls"], "weight": 1, "status": "pending",
             "output_path": None, "generated_at": None, "defer_reason": None},
        ]
        eligible = ss.list_interfaces(state, eligible_only=True)
        self.assertEqual([i["id"] for i in eligible], ["core--leaf"])

    def test_list_interfaces_eligible_only_still_rejects_non_tier3_skipped_endpoint(self):
        # The tier-3 widening must stay narrow: a "skipped" endpoint that's
        # tier 0 (generated/vendor code) or tier None (empty directory) has
        # no real content and must NOT be treated as a settled interface
        # endpoint just because its status happens to also be "skipped".
        state = ss.empty_state()
        state["modules"] = [
            {"id": "core/", "tier": 1, "in_degree": 12, "file_count": 4,
             "basis": "graph:in-degree", "status": "generated",
             "generated_at": "now", "output_path": "org/core/CONTEXT.md", "skip_reason": None},
            {"id": "vendor/", "tier": 0, "in_degree": 0, "file_count": 3,
             "basis": "generated", "status": "skipped",
             "generated_at": None, "output_path": None,
             "skip_reason": "generated/vendor code (auto-detected)"},
        ]
        state["interfaces"] = [
            {"id": "core--vendor", "module_a": "core", "module_b": "vendor",
             "relations": ["calls"], "weight": 1, "status": "pending",
             "output_path": None, "generated_at": None, "defer_reason": None},
        ]
        self.assertEqual(ss.list_interfaces(state, eligible_only=True), [])


class RenderIndexTests(unittest.TestCase):
    def test_render_index_groups_by_tier_and_reports_progress(self):
        state = self._state_with_pending_module = ss.empty_state()
        state["modules"] = [
            {"id": "core/", "tier": 1, "in_degree": 12, "file_count": 4,
             "basis": "graph:in-degree", "status": "generated",
             "generated_at": "2026-08-12T00:00:00Z", "output_path": "docs/core/CONTEXT.md",
             "skip_reason": None},
            {"id": "orphan/", "tier": 3, "in_degree": 0, "file_count": 1,
             "basis": "graph:in-degree", "status": "pending",
             "generated_at": None, "output_path": None, "skip_reason": None},
            {"id": "generated/", "tier": 0, "in_degree": None, "file_count": 3,
             "basis": "generated", "status": "skipped",
             "generated_at": None, "output_path": None,
             "skip_reason": "generated/vendor code (auto-detected)"},
        ]
        state["repo_scan"] = {"graph_source": "graphify", "graph_path": "x", "scanned_at": "now"}
        text = ss.render_index(state, "demo-repo")
        self.assertIn("# CEP Index - demo-repo", text)
        self.assertIn("Tier 1", text)
        self.assertIn("core/", text)
        self.assertIn("docs/core/CONTEXT.md", text)
        self.assertIn("1 generated, 1 pending, 1 skipped, 0 failed (3 modules total)", text)

    def test_render_index_heuristic_mode_carries_confidence_caveat(self):
        state = ss.empty_state()
        state["repo_scan"] = {"graph_source": "heuristic", "graph_path": None, "scanned_at": "now"}
        text = ss.render_index(state, "demo-repo")
        self.assertIn("lower-confidence", text)

    def test_render_index_surfaces_graph_module_overlap_warning(self):
        # A persisted partial-overlap warning (see ScanTests) must reach
        # anyone reading the generated CEP-INDEX.md, not just whoever ran
        # `scan` and saw the stderr line at the time.
        state = ss.empty_state()
        state["repo_scan"] = {
            "graph_source": "graphify", "graph_path": "x", "scanned_at": "now",
            "graph_module_overlap_warning": "only 20% of on-disk modules matched the graph",
        }
        text = ss.render_index(state, "demo-repo")
        self.assertIn("**WARNING:**", text)
        self.assertIn("only 20% of on-disk modules matched the graph", text)

    def test_render_index_surfaces_graph_cep_contamination_warning(self):
        # Same "must reach CEP-INDEX.md readers, not just scan-time stderr"
        # reasoning as the overlap-warning test above, for the other
        # non-fatal graph warning.
        state = ss.empty_state()
        state["repo_scan"] = {
            "graph_source": "graphify", "graph_path": "x", "scanned_at": "now",
            "graph_cep_contamination_warning": "12% of graph.json's nodes (1/8) live under CEP-owned paths",
        }
        text = ss.render_index(state, "demo-repo")
        self.assertIn("**WARNING:**", text)
        self.assertIn("12% of graph.json's nodes (1/8) live under CEP-owned paths", text)

    def test_render_index_repo_docs_section_reports_each_kind(self):
        state = ss.empty_state()
        ss.mark_repo_doc_generated(state, "coding_standards", "org/CODING-STANDARDS.md")
        text = ss.render_index(state, "demo-repo")
        self.assertIn("## Repo-wide docs", text)
        self.assertIn("Coding Standards", text)
        self.assertIn("**generated** -> `org/CODING-STANDARDS.md`", text)
        self.assertIn("Testing Guidelines", text)
        self.assertIn("**pending**", text)

    def test_render_index_interfaces_section_empty_placeholder(self):
        state = ss.empty_state()
        text = ss.render_index(state, "demo-repo")
        self.assertIn("## Interface boundaries", text)
        self.assertIn("_none", text)

    def test_render_index_interfaces_section_lists_pairs_and_progress(self):
        state = ss.empty_state()
        state["interfaces"] = [
            {"id": "core--utils", "module_a": "core", "module_b": "utils",
             "relations": ["calls"], "weight": 4, "status": "generated",
             "output_path": "org/interfaces/core-to-utils.md", "generated_at": "now",
             "defer_reason": None},
            {"id": "core--legacy", "module_a": "core", "module_b": "legacy",
             "relations": ["imports_from"], "weight": 1, "status": "pending",
             "output_path": None, "generated_at": None, "defer_reason": None},
        ]
        text = ss.render_index(state, "demo-repo")
        self.assertIn("`core` <-> `utils`", text)
        self.assertIn("org/interfaces/core-to-utils.md", text)
        self.assertIn("1 generated, 1 pending, 0 deferred, 0 failed (2 interfaces total)", text)


class SummarizeTests(unittest.TestCase):
    def test_summarize_counts_by_tier_and_status(self):
        state = ss.empty_state()
        state["modules"] = [
            {"id": "a/", "tier": 1, "status": "generated"},
            {"id": "b/", "tier": 1, "status": "pending"},
            {"id": "c/", "tier": 2, "status": "pending"},
            {"id": "d/", "tier": 0, "status": "skipped"},
        ]
        summary = ss.summarize(state)
        self.assertEqual(summary["total_modules"], 4)
        self.assertEqual(summary["generated"], 1)
        self.assertEqual(summary["pending"], 2)
        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(summary["by_tier"]["1"], {"pending": 1, "generated": 1, "skipped": 0})

    def test_summarize_includes_repo_docs_and_interfaces(self):
        state = ss.empty_state()
        ss.mark_repo_doc_generated(state, "coding_standards", "org/CODING-STANDARDS.md")
        state["interfaces"] = [
            {"id": "core--utils", "module_a": "core", "module_b": "utils",
             "relations": ["calls"], "weight": 4, "status": "pending",
             "output_path": None, "generated_at": None, "defer_reason": None},
        ]
        summary = ss.summarize(state)
        self.assertEqual(summary["repo_docs"]["coding_standards"], "generated")
        self.assertEqual(summary["repo_docs"]["testing_guidelines"], "pending")
        self.assertEqual(summary["interfaces"], {"total": 1, "generated": 0, "pending": 1, "deferred": 0})


class TestScanIgnoredDirNamesParity(unittest.TestCase):
    """scaffold_state.SCAN_IGNORED_DIR_NAMES and ult-repo-layout's
    discover_layers.SCAN_IGNORED_DIR_NAMES are deliberately kept as two
    small local duplicates rather than a shared import (house convention -
    see either module's own comment on the pair). This is the mirror of
    test_discover_layers.py's own parity check: without it, an edit made
    from this side only failed once somebody happened to run the other
    skill's suite.
    """

    def test_scan_ignored_dir_names_match_ult_repo_layout(self):
        repo_layout_scripts = (
            Path(__file__).resolve().parent.parent.parent.parent
            / "ult-repo-layout"
            / "scripts"
        )
        if not repo_layout_scripts.is_dir():
            # A partial checkout / install without the sibling skill has
            # nothing to compare against. That is not this test's own
            # failure to report - skip rather than fail.
            self.skipTest(
                f"sibling skill scripts dir not present at {repo_layout_scripts}"
            )
        sys.path.insert(0, str(repo_layout_scripts))
        try:
            import discover_layers as dl  # noqa: E402
        finally:
            sys.path.remove(str(repo_layout_scripts))

        self.assertEqual(
            ss.SCAN_IGNORED_DIR_NAMES,
            dl.SCAN_IGNORED_DIR_NAMES,
            "scaffold_state.SCAN_IGNORED_DIR_NAMES and "
            "discover_layers.SCAN_IGNORED_DIR_NAMES have drifted apart - "
            "keep the two sets content-identical (see either module's "
            "comment on this pair).",
        )


class TestPruneIgnoredCasing(unittest.TestCase):
    """Direct unit coverage for _prune_ignored's case-insensitive matching,
    mirroring ult-repo-layout's own test of the same fix (see that module's
    discover_layers.py for the shared rationale).
    """

    def test_scan_ignored_dir_names_matched_case_insensitively(self):
        self.assertEqual(ss._prune_ignored(["node_modules", "src"]), ["src"])
        self.assertEqual(ss._prune_ignored(["Node_Modules", "src"]), ["src"])
        self.assertEqual(ss._prune_ignored(["NODE_MODULES", "src"]), ["src"])

    def test_cep_bucket_dir_names_are_case_sensitive_by_design(self):
        self.assertEqual(ss._prune_ignored(["contexts", "src"]), ["src"])
        self.assertEqual(ss._prune_ignored(["Contexts", "src"]), ["Contexts", "src"])

    def test_dot_prefixed_dirs_still_pruned_regardless_of_casing(self):
        self.assertEqual(ss._prune_ignored([".git", ".Idea", "src"]), ["src"])


# --------------------------------------------------------------------------- #
# TASK-0103: build_work_packets() / `plan` (Sec 5.2 work-packet schema)      #
# --------------------------------------------------------------------------- #

def _module(module_id, tier, status="pending"):
    return {
        "id": module_id,
        "tier": tier,
        "status": status,
        "basis": "test-fixture",
        "in_degree": None,
        "output_path": None,
        "generated_at": None,
        "skip_reason": None,
    }


def _repo_docs(coding_standards="pending", testing_guidelines="pending"):
    docs = ss._ensure_repo_docs({})
    docs["coding_standards"]["status"] = coding_standards
    docs["testing_guidelines"]["status"] = testing_guidelines
    return docs


def _interface(module_a, module_b, status="pending"):
    return {
        "id": ss._interface_id(module_a, module_b),
        "module_a": module_a,
        "module_b": module_b,
        "relations": ["calls"],
        "weight": 1,
        "status": status,
        "output_path": None,
        "generated_at": None,
        "defer_reason": None,
    }


class WorkPacketPlanningTests(unittest.TestCase):
    """TASK-0103: deterministic packet IDs/content, per-packet content-mode
    resolution (TASK-0303 -- resolve_content_mode() wired through real
    probe_size() evidence, so a greenfield fixture downgrades every kind to
    skeleton), output-path uniqueness/containment, must_cite derivation,
    tier-based soft read budgets, and recorded HEAD commit -- against
    build_work_packets()/`plan` (Sec 5.2)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo_root = Path(self.tmp.name)

    def _state(self, modules=(), coding_standards="generated",
               testing_guidelines="generated", interfaces=()):
        # Repo docs default to already-settled so module-only/interface-only
        # tests get exactly the packets they ask for -- tests that care
        # about coding_standards/testing_guidelines planning pass
        # coding_standards="pending"/testing_guidelines="pending" explicitly.
        state = ss.empty_state()
        state["modules"] = list(modules)
        state["repo_docs"] = _repo_docs(coding_standards, testing_guidelines)
        state["interfaces"] = list(interfaces)
        return state

    # -- determinism -------------------------------------------------- #

    def test_same_inputs_produce_identical_packet_list(self):
        state = self._state(modules=[_module("core/", 1), _module("utils/", 2)])
        first = ss.build_work_packets(state, self.repo_root, "org")
        second = ss.build_work_packets(state, self.repo_root, "org")
        self.assertEqual(first, second)

    def test_packets_sorted_by_packet_id(self):
        state = self._state(modules=[_module("zeta/", 1), _module("alpha/", 1)])
        packets = ss.build_work_packets(state, self.repo_root, "org")
        self.assertEqual([p["packet_id"] for p in packets], sorted(p["packet_id"] for p in packets))

    # -- context_md packet content ------------------------------------- #

    def test_context_md_packet_id_and_output_path(self):
        state = self._state(modules=[_module("core/", 1)])
        packets = ss.build_work_packets(state, self.repo_root, "org")
        self.assertEqual(len(packets), 1)
        packet = packets[0]
        self.assertEqual(packet["packet_id"], "how-l2--core--context")
        self.assertEqual(packet["kind"], "context_md")
        self.assertEqual(packet["layer"], "how_l2")
        self.assertEqual(packet["module_id"], "core/")
        self.assertEqual(packet["tier"], 1)
        self.assertEqual(packet["output_path"], "org/core/CONTEXT.md")
        self.assertEqual(packet["template"], "templates/context-md-template.md")
        self.assertEqual(
            packet["required_sections"],
            [
                "Purpose", "Inputs", "Outputs", "Key abstractions",
                "Dependencies", "Design invariants", "Gotchas",
            ],
        )

    def test_tier_3_modules_are_not_planned(self):
        # Proposal line 39: "Tier-3 modules were generated. The skill skips
        # Tier 3 by default." -- stated as the general planning rule.
        state = self._state(modules=[_module("vendor/", 3)])
        packets = ss.build_work_packets(state, self.repo_root, "org")
        self.assertEqual(packets, [])

    def test_only_pending_modules_are_planned(self):
        state = self._state(modules=[
            _module("core/", 1, status="pending"),
            _module("done/", 1, status="generated"),
            _module("skipped/", 1, status="skipped"),
        ])
        packets = ss.build_work_packets(state, self.repo_root, "org")
        self.assertEqual([p["module_id"] for p in packets], ["core/"])

    # -- TASK-0303 real content-mode resolution ------------------------- #

    def test_greenfield_repo_downgrades_every_packet_to_skeleton(self):
        # self.repo_root is a genuinely empty tmp dir, so probe_size()
        # reports greenfield=True and resolve_content_mode() collapses
        # every kind's default ("grounded" for how_l2) down to skeleton,
        # recording a non-None mode_reason (Sec 6.2, TASK-0303).
        state = self._state(
            modules=[_module("core/", 1)],
            interfaces=[_interface("core", "utils")],
        )
        packets = ss.build_work_packets(state, self.repo_root, "org")
        self.assertEqual(len(packets), 2)
        for packet in packets:
            self.assertEqual(packet["content_mode_requested"], "grounded")
            self.assertEqual(packet["content_mode"], "skeleton")
            self.assertIsNotNone(packet["mode_reason"])

    # -- repo docs (coding_standards / testing_guidelines) --------------- #

    def test_repo_doc_packets_use_repo_level_output_paths_and_budget(self):
        _write(self.repo_root / ".clang-format", "x")
        _write(self.repo_root / ".flake8", "x")
        state = self._state(coding_standards="pending", testing_guidelines="pending")
        packets = ss.build_work_packets(state, self.repo_root, "org")
        by_kind = {p["kind"]: p for p in packets}
        self.assertEqual(set(by_kind), {"coding_standards", "testing_guidelines"})
        cs = by_kind["coding_standards"]
        self.assertEqual(cs["packet_id"], "how-l2--coding-standards")
        self.assertEqual(cs["output_path"], "org/CODING-STANDARDS.md")
        self.assertEqual(cs["module_id"], None)
        self.assertEqual(cs["tier"], None)
        self.assertEqual(cs["read_budget"], ss.READ_BUDGET_REPO_DOC)
        self.assertIn(".clang-format", cs["must_cite"])
        tg = by_kind["testing_guidelines"]
        self.assertEqual(tg["output_path"], "org/TESTING-GUIDELINES.md")
        self.assertEqual(tg["read_budget"], ss.READ_BUDGET_REPO_DOC)

    def test_repo_doc_must_cite_includes_ci_config(self):
        # Sec 5.2's worked example lists .github/workflows/cpp.yml
        # (a CI file) alongside .clang-format/CPPLINT.cfg/format.sh in
        # CODING-STANDARDS.md's must_cite -- ci signals must be included.
        _write(self.repo_root / ".github" / "workflows" / "cpp.yml", "x")
        state = self._state(coding_standards="pending", testing_guidelines="pending")
        packets = ss.build_work_packets(state, self.repo_root, "org")
        cs = next(p for p in packets if p["kind"] == "coding_standards")
        self.assertTrue(
            any(".github/workflows/cpp.yml" in c.replace("\\", "/") for c in cs["must_cite"])
        )

    def test_settled_repo_docs_are_not_replanned(self):
        state = self._state(coding_standards="generated", testing_guidelines="deferred")
        packets = ss.build_work_packets(state, self.repo_root, "org")
        self.assertEqual(packets, [])

    # -- interfaces -------------------------------------------------- #

    def test_interface_packet_output_path_and_budget(self):
        state = self._state(interfaces=[_interface("core", "utils")])
        packets = ss.build_work_packets(state, self.repo_root, "org")
        self.assertEqual(len(packets), 1)
        packet = packets[0]
        self.assertEqual(packet["kind"], "interface_boundary")
        self.assertEqual(packet["output_path"], "org/interfaces/core-to-utils.md")
        self.assertEqual(packet["read_budget"], ss.READ_BUDGET_INTERFACE)

    def test_only_pending_interfaces_are_planned(self):
        state = self._state(interfaces=[
            _interface("core", "utils", status="pending"),
            _interface("core", "legacy", status="generated"),
            _interface("utils", "legacy", status="deferred"),
        ])
        packets = ss.build_work_packets(state, self.repo_root, "org")
        self.assertEqual(len(packets), 1)
        self.assertEqual(packets[0]["output_path"], "org/interfaces/core-to-utils.md")

    # -- must_cite / evidence_hints from graph.json ----------------------- #

    def test_context_md_evidence_hints_and_must_cite_from_graph(self):
        graph_path = self.repo_root / "graph.json"
        _write(graph_path, json.dumps(_fixture_graph()))
        state = self._state(modules=[_module("core/", 1), _module("utils/", 1)])
        packets = ss.build_work_packets(
            state, self.repo_root, "org", graph_path=graph_path,
        )
        by_module = {p["module_id"]: p for p in packets}

        core = by_module["core/"]
        self.assertEqual(core["evidence_hints"]["depends_on"], ["legacy/", "utils/"])
        self.assertEqual(core["evidence_hints"]["depended_on_by"], [])
        self.assertEqual(core["evidence_hints"]["top_symbols_by_in_degree"], [])
        self.assertEqual(core["evidence_hints"]["call_sites"], [])
        self.assertEqual(core["must_cite"], [])

        utils = by_module["utils/"]
        self.assertEqual(utils["evidence_hints"]["depends_on"], [])
        self.assertEqual(utils["evidence_hints"]["depended_on_by"], ["core/"])
        self.assertEqual(
            utils["evidence_hints"]["top_symbols_by_in_degree"],
            ["utils_helpers_add", "utils_helpers_mul"],
        )
        self.assertEqual(utils["must_cite"], ["utils/helpers.py"])

    def test_context_md_evidence_hints_empty_without_graph_path(self):
        state = self._state(modules=[_module("core/", 1)])
        packets = ss.build_work_packets(state, self.repo_root, "org", graph_path=None)
        self.assertEqual(packets[0]["evidence_hints"], ss._EMPTY_EVIDENCE_HINTS)
        self.assertEqual(packets[0]["must_cite"], [])

    # -- tier-based soft read budgets -------------------------------------- #

    def test_read_budget_by_tier(self):
        state = self._state(modules=[_module("core/", 1), _module("utils/", 2)])
        packets = ss.build_work_packets(state, self.repo_root, "org")
        by_module = {p["module_id"]: p for p in packets}
        self.assertEqual(by_module["core/"]["read_budget"], ss.READ_BUDGET_BY_TIER[1])
        self.assertEqual(by_module["utils/"]["read_budget"], ss.READ_BUDGET_BY_TIER[2])
        self.assertEqual(ss.READ_BUDGET_BY_TIER[1], 40)
        self.assertEqual(ss.READ_BUDGET_BY_TIER[2], 20)

    # -- output-path uniqueness / containment ------------------------------ #

    def test_duplicate_output_path_raises_value_error(self):
        # Two module ids that collapse to the same output_path once
        # slashes are normalized -- must be refused, not silently planned.
        state = self._state(modules=[_module("core/", 1), _module("core//", 1)])
        with self.assertRaises(ValueError):
            ss.build_work_packets(state, self.repo_root, "org")

    def test_output_path_escaping_how_l2_path_raises_value_error(self):
        state = self._state(modules=[_module("../evil/", 1)])
        with self.assertRaises(ValueError):
            ss.build_work_packets(state, self.repo_root, "org")

    def test_path_is_contained_helper(self):
        self.assertTrue(ss._path_is_contained("org/core/CONTEXT.md", "org"))
        self.assertTrue(ss._path_is_contained("org", "org"))
        self.assertFalse(ss._path_is_contained("orgy/core/CONTEXT.md", "org"))
        self.assertFalse(ss._path_is_contained("evil/CONTEXT.md", "org"))

    # -- recorded HEAD commit -------------------------------------------- #

    def test_head_commit_recorded_when_repo_root_is_a_git_repo(self):
        subprocess.run(["git", "init", "-q"], cwd=self.repo_root, check=True)
        subprocess.run(
            ["git", "-c", "user.email=t@example.com", "-c", "user.name=t",
             "commit", "--allow-empty", "-q", "-m", "init"],
            cwd=self.repo_root, check=True,
        )
        expected = subprocess.run(
            ["git", "-C", str(self.repo_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        state = self._state(modules=[_module("core/", 1)])
        packets = ss.build_work_packets(state, self.repo_root, "org")
        self.assertEqual(packets[0]["head_commit"], expected)
        self.assertTrue(expected)

    def test_head_commit_none_outside_a_git_repo(self):
        state = self._state(modules=[_module("core/", 1)])
        packets = ss.build_work_packets(state, self.repo_root, "org")
        self.assertIsNone(packets[0]["head_commit"])

    # -- validation_floor wiring ------------------------------------------ #

    def test_validation_floor_keyed_by_kind_and_tier(self):
        state = self._state(modules=[_module("core/", 1), _module("utils/", 2)])
        packets = ss.build_work_packets(state, self.repo_root, "org")
        by_module = {p["module_id"]: p for p in packets}
        self.assertEqual(
            by_module["core/"]["validation_floor"],
            ss.VALIDATION_FLOORS[("context_md", 1)],
        )
        self.assertEqual(
            by_module["utils/"]["validation_floor"],
            ss.VALIDATION_FLOORS[("context_md", 2)],
        )


# --------------------------------------------------------------------------- #
# TASK-0105: ss.validate() (Sec 6's P0a validator table)                     #
#                                                                             #
# Written and run BEFORE ss.validate exists -- confirmed red (AttributeError #
# on every test) per the test-first discipline, then TASK-0106 implements   #
# the smallest thing that turns these green. Deliberately excludes the two  #
# checks the plan defers: external-block validation (P2) and skeleton       #
# byte-identity (P1) -- per the plan's own already-recorded scoping note.    #
# --------------------------------------------------------------------------- #

def _prose(file_path):
    """One citation-bearing sentence, long enough that 7-8 of them clear
    every VALIDATION_FLOORS min_body_bytes entry with margin, short enough
    that tests stay readable."""
    return (
        "This section reflects real, currently-observed behavior in the "
        "code, described in enough detail for a new contributor to act on "
        "without re-reading the source themselves. [src: {}#L1-L2]"
    ).format(file_path)


def _full_sections(required_sections, citable_files):
    """One evidenced paragraph per required heading, citations rotated
    across `citable_files` so every file gets cited at least once whenever
    there are at least as many headings as files -- the shape every
    failure test starts from and mutates exactly one heading of, so a
    test's only failure is the one it's isolating."""
    files = list(citable_files)
    return {
        heading: _prose(files[i % len(files)])
        for i, heading in enumerate(required_sections)
    }


def _make_doc(packet, sections, frontmatter_overrides=None):
    """Render a full, syntactically-valid document for `packet`: six-field
    frontmatter (any field can be dropped by passing it as None in
    `frontmatter_overrides`, or overridden to a bad value) followed by one
    "## <heading>" block per packet['required_sections'], body text taken
    from `sections[heading]` verbatim."""
    frontmatter = {
        "generated_by": "ult-autoscaffold-content",
        "generated_at": "2026-09-28",
        "status": "draft",
        "content_mode": packet["content_mode"],
        "doc_kind": packet["kind"],
        "skill_version": "2.0.0-dev",
    }
    if frontmatter_overrides:
        for key, value in frontmatter_overrides.items():
            if value is None:
                frontmatter.pop(key, None)
            else:
                frontmatter[key] = value
    lines = ["---"]
    for key, value in frontmatter.items():
        lines.append("{}: {}".format(key, value))
    lines.append("---")
    lines.append("")
    for heading in packet["required_sections"]:
        lines.append("## {}".format(heading))
        lines.append("")
        lines.append(sections[heading])
        lines.append("")
    return "\n".join(lines) + "\n"


class GeneratedValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo_root = Path(self.tmp.name)
        self.citable_files = ["src/a.py", "src/b.py", "src/c.py"]
        for f in self.citable_files:
            _write(self.repo_root / f, "line1\nline2\nline3\n")
        self.packet = {
            "packet_id": "how-l2--core--context",
            "layer": "how_l2",
            "kind": "context_md",
            "module_id": "core/",
            "tier": 2,
            "output_path": "org/core/CONTEXT.md",
            "template": ss.TEMPLATE_PATH_BY_KIND["context_md"],
            "content_mode_requested": "grounded",
            "content_mode": "grounded",
            "mode_reason": None,
            "required_sections": list(ss.REQUIRED_SECTIONS_BY_KIND["context_md"]),
            "probe_checklist_ref": ss.PROBE_CHECKLIST_REF_BY_KIND["context_md"],
            "must_cite": ["src/a.py"],
            "evidence_hints": dict(ss._EMPTY_EVIDENCE_HINTS),
            "domain_pack": None,
            "validation_floor": dict(ss.VALIDATION_FLOORS[("context_md", 2)]),
            "read_budget": ss.READ_BUDGET_BY_TIER[2],
            "head_commit": None,
        }
        self.baseline_sections = _full_sections(
            self.packet["required_sections"], self.citable_files
        )

    def _write_doc(self, text, path=None):
        path = path or self.packet["output_path"]
        _write(self.repo_root / path, text)
        return path

    # -- baseline: a genuinely correct doc must validate clean ------------ #

    def test_valid_grounded_document_passes(self):
        path = self._write_doc(_make_doc(self.packet, self.baseline_sections))
        result = ss.validate(self.repo_root, path, self.packet)
        self.assertEqual(result["failures"], [])
        self.assertTrue(result["valid"])

    # -- existence / output_path ------------------------------------------ #

    def test_missing_file_fails(self):
        result = ss.validate(self.repo_root, self.packet["output_path"], self.packet)
        self.assertFalse(result["valid"])
        self.assertTrue(any("exist" in f.lower() for f in result["failures"]))

    def test_wrong_output_path_fails(self):
        self._write_doc(_make_doc(self.packet, self.baseline_sections))
        result = ss.validate(self.repo_root, "org/core/WRONG.md", self.packet)
        self.assertFalse(result["valid"])
        self.assertTrue(any("output_path" in f for f in result["failures"]))

    # -- frontmatter -------------------------------------------------------- #

    def test_missing_content_mode_frontmatter_fails(self):
        doc = _make_doc(self.packet, self.baseline_sections,
                         frontmatter_overrides={"content_mode": None})
        path = self._write_doc(doc)
        result = ss.validate(self.repo_root, path, self.packet)
        self.assertFalse(result["valid"])
        self.assertTrue(any("content_mode" in f for f in result["failures"]))

    def test_missing_skill_version_frontmatter_fails(self):
        doc = _make_doc(self.packet, self.baseline_sections,
                         frontmatter_overrides={"skill_version": None})
        path = self._write_doc(doc)
        result = ss.validate(self.repo_root, path, self.packet)
        self.assertFalse(result["valid"])
        self.assertTrue(any("skill_version" in f for f in result["failures"]))

    def test_status_not_draft_fails(self):
        doc = _make_doc(self.packet, self.baseline_sections,
                         frontmatter_overrides={"status": "final"})
        path = self._write_doc(doc)
        result = ss.validate(self.repo_root, path, self.packet)
        self.assertFalse(result["valid"])
        self.assertTrue(any("status" in f for f in result["failures"]))

    def test_content_mode_mismatch_with_packet_content_mode_fails(self):
        doc = _make_doc(self.packet, self.baseline_sections,
                         frontmatter_overrides={"content_mode": "skeleton"})
        path = self._write_doc(doc)
        result = ss.validate(self.repo_root, path, self.packet)
        self.assertFalse(result["valid"])
        self.assertTrue(any("content_mode" in f for f in result["failures"]))

    # -- sections ------------------------------------------------------------ #

    def test_missing_required_section_fails(self):
        doc = _make_doc(self.packet, self.baseline_sections)
        doc = doc.replace("## Gotchas\n", "## Renamed\n")
        path = self._write_doc(doc)
        result = ss.validate(self.repo_root, path, self.packet)
        self.assertFalse(result["valid"])
        self.assertTrue(any("Gotchas" in f for f in result["failures"]))

    def test_placeholder_section_body_fails(self):
        sections = dict(self.baseline_sections)
        sections["Gotchas"] = "TBD -- fill in later."
        path = self._write_doc(_make_doc(self.packet, sections))
        result = ss.validate(self.repo_root, path, self.packet)
        self.assertFalse(result["valid"])
        self.assertTrue(any("Gotchas" in f for f in result["failures"]))

    def test_empty_section_body_fails(self):
        sections = dict(self.baseline_sections)
        sections["Gotchas"] = ""
        path = self._write_doc(_make_doc(self.packet, sections))
        result = ss.validate(self.repo_root, path, self.packet)
        self.assertFalse(result["valid"])
        self.assertTrue(any("Gotchas" in f for f in result["failures"]))

    # -- must-cite ------------------------------------------------------------ #

    def test_missing_must_cite_path_fails(self):
        # Every heading cites only b.py/c.py -- packet["must_cite"] names
        # a.py, which never appears in a [src:] citation anywhere.
        sections = _full_sections(self.packet["required_sections"],
                                   ["src/b.py", "src/c.py"])
        path = self._write_doc(_make_doc(self.packet, sections))
        result = ss.validate(self.repo_root, path, self.packet)
        self.assertFalse(result["valid"])
        self.assertTrue(any("must_cite" in f or "src/a.py" in f for f in result["failures"]))

    def test_cmake_enable_testing_literal_marker_can_be_cited_and_pass(self):
        # _probe_cmake_test_registration's test_config signal for a CMake
        # project is the literal string "CMakeLists.txt:enable_testing"
        # (Sec 4.3's own worked-example illustration), not a real
        # filesystem path -- it feeds must_cite for testing_guidelines
        # packets verbatim (build_work_packets: sorted(set(signals
        # ["test_config"]))). Sec 6's "Must-cite" row requires this exact
        # string appear in a [src:] citation; its "Citation resolution"
        # row then requires every [src:] path to exist on disk. Taken
        # together as written, no CMake-based repo could ever satisfy
        # both rows for this one marker -- a real CMake-based repo's CMakeLists.txt
        # reproduces this for real. The fix scopes citation-resolution's
        # existence/line-range check to real paths only, leaving the
        # literal marker's presence requirement (must_cite) unchanged.
        _write(self.repo_root / "CMakeLists.txt", "project(x)\nenable_testing()\n")
        packet = dict(self.packet)
        packet.update({
            "kind": "testing_guidelines",
            "module_id": None,
            "tier": None,
            "output_path": "org/TESTING-GUIDELINES.md",
            "template": ss.TEMPLATE_PATH_BY_KIND["testing_guidelines"],
            "required_sections": list(ss.REQUIRED_SECTIONS_BY_KIND["testing_guidelines"]),
            "probe_checklist_ref": ss.PROBE_CHECKLIST_REF_BY_KIND["testing_guidelines"],
            "must_cite": ["CMakeLists.txt:enable_testing"],
            "validation_floor": dict(ss.VALIDATION_FLOORS[("testing_guidelines", None)]),
            "read_budget": ss.READ_BUDGET_REPO_DOC,
        })
        sections = _full_sections(packet["required_sections"], self.citable_files)
        # Exactly one heading carries the literal marker citation; the
        # rest keep citing real files so the floor is met honestly.
        first_heading = packet["required_sections"][0]
        sections[first_heading] = (
            "CTest is registered via enable_testing() in the top-level "
            "build file [src: CMakeLists.txt:enable_testing#L2-L2] "
            "[src: CMakeLists.txt#L2-L2]."
        )
        path = self._write_doc(_make_doc(packet, sections), path=packet["output_path"])
        result = ss.validate(self.repo_root, path, packet)
        self.assertEqual(result["failures"], [])
        self.assertTrue(result["valid"])

    # -- citation resolution --------------------------------------------------- #

    def test_citation_to_nonexistent_file_fails(self):
        sections = dict(self.baseline_sections)
        sections["Purpose"] = "See the ghost module. [src: src/ghost.py#L1]"
        path = self._write_doc(_make_doc(self.packet, sections))
        result = ss.validate(self.repo_root, path, self.packet)
        self.assertFalse(result["valid"])
        self.assertTrue(any("ghost.py" in f for f in result["failures"]))

    def test_citation_line_range_out_of_bounds_fails(self):
        sections = dict(self.baseline_sections)
        sections["Purpose"] = "Out of range on purpose. [src: src/a.py#L1-L99]"
        path = self._write_doc(_make_doc(self.packet, sections))
        result = ss.validate(self.repo_root, path, self.packet)
        self.assertFalse(result["valid"])
        self.assertTrue(any("a.py" in f and "99" in f for f in result["failures"]))

    # -- gap honesty (false absence claims) ------------------------------------ #

    def test_false_absence_claim_fails(self):
        # src/a.py genuinely exists -- claiming it's absent must fail.
        sections = dict(self.baseline_sections)
        sections["Purpose"] = "Not evidenced. Searched: src/a.py (absent)."
        path = self._write_doc(_make_doc(self.packet, sections))
        result = ss.validate(self.repo_root, path, self.packet)
        self.assertFalse(result["valid"])
        self.assertTrue(any("a.py" in f for f in result["failures"]))

    def test_genuine_absence_claim_passes_gap_honesty(self):
        sections = dict(self.baseline_sections)
        sections["Purpose"] = "Not evidenced. Searched: src/does-not-exist.py (absent)."
        path = self._write_doc(_make_doc(self.packet, sections))
        result = ss.validate(self.repo_root, path, self.packet)
        self.assertFalse(any("does-not-exist.py" in f for f in result["failures"]))

    # -- floors ---------------------------------------------------------------- #

    def test_body_below_min_body_bytes_floor_fails(self):
        packet = dict(self.packet)
        packet["validation_floor"] = {"min_distinct_cited_files": 1, "min_body_bytes": 100000}
        path = self._write_doc(_make_doc(packet, self.baseline_sections))
        result = ss.validate(self.repo_root, path, packet)
        self.assertFalse(result["valid"])
        self.assertTrue(any("body" in f.lower() and "byte" in f.lower() for f in result["failures"]))

    def test_below_min_distinct_cited_files_floor_fails(self):
        packet = dict(self.packet)
        packet["validation_floor"] = {"min_distinct_cited_files": 10, "min_body_bytes": 1}
        path = self._write_doc(_make_doc(packet, self.baseline_sections))
        result = ss.validate(self.repo_root, path, packet)
        self.assertFalse(result["valid"])
        self.assertTrue(any("cited file" in f.lower() for f in result["failures"]))

    # -- conflicts (coding_standards only) -------------------------------------- #

    def _coding_standards_packet(self):
        # Four distinct signal classes, all synthetic/generic (never modeled
        # on a specific real repo's actual layout): formatter_config
        # (.clang-format), linter_config (CPPLINT.cfg), wrapper_scripts
        # (format.sh), ci (cpp.yml). Only clang-format is mentioned from two
        # distinct sources (format.sh + cpp.yml) -- cpplint's config exists
        # but its name appears nowhere else, so it must NOT itself trigger a
        # conflict requirement (see the precision test below).
        # Every file here needs >= 2 lines: _prose() below always cites
        # "#L1-L2", so a 1-line file would itself fail citation-range
        # validation independently of anything this fixture is testing.
        tool_files = [
            ".clang-format", "CPPLINT.cfg", "format.sh", ".github/workflows/cpp.yml",
        ]
        _write(self.repo_root / ".clang-format", "BasedOnStyle: Google\nColumnLimit: 100\n")
        _write(self.repo_root / "CPPLINT.cfg", "linelength=100\nfilter=-whitespace\n")
        _write(self.repo_root / "format.sh", "#!/bin/sh\nclang-format --version\n")
        _write(self.repo_root / ".github" / "workflows" / "cpp.yml",
               "jobs:\n  fmt:\n    run: clang-format --version\n")
        packet = dict(self.packet)
        packet.update({
            "kind": "coding_standards", "module_id": None, "tier": None,
            "output_path": "org/CODING-STANDARDS.md",
            "template": ss.TEMPLATE_PATH_BY_KIND["coding_standards"],
            "required_sections": list(ss.REQUIRED_SECTIONS_BY_KIND["coding_standards"]),
            "probe_checklist_ref": ss.PROBE_CHECKLIST_REF_BY_KIND["coding_standards"],
            "must_cite": [".clang-format", "CPPLINT.cfg"],
            "validation_floor": dict(ss.VALIDATION_FLOORS[("coding_standards", None)]),
            "read_budget": ss.READ_BUDGET_REPO_DOC,
        })
        return packet, tool_files

    def test_coding_standards_tool_version_disagreement_requires_conflict_line(self):
        packet, tool_files = self._coding_standards_packet()
        sections = _full_sections(packet["required_sections"], tool_files)
        path = self._write_doc(_make_doc(packet, sections), path=packet["output_path"])
        result = ss.validate(self.repo_root, path, packet)
        self.assertFalse(result["valid"])
        self.assertTrue(any("conflict" in f.lower() for f in result["failures"]))

    def test_coding_standards_conflict_line_present_satisfies_check(self):
        packet, tool_files = self._coding_standards_packet()
        sections = _full_sections(packet["required_sections"], tool_files)
        sections["Formatting"] += (
            "\nConflicting evidence: format.sh and cpp.yml both pin "
            "clang-format independently [src: format.sh#L2] "
            "[src: .github/workflows/cpp.yml#L3]."
        )
        path = self._write_doc(_make_doc(packet, sections), path=packet["output_path"])
        result = ss.validate(self.repo_root, path, packet)
        self.assertFalse(any("conflict" in f.lower() for f in result["failures"]))

    def test_coding_standards_single_source_tool_does_not_require_its_own_conflict_line(self):
        # cpplint's config is present and cited (must_cite), but "cpplint"
        # is never mentioned in any wrapper_scripts/ci/contributing file --
        # only clang-format has two-source citation. Adding the clang-format
        # conflict line must satisfy the check for BOTH tools; cpplint must
        # never have generated a failure of its own in the first place, and
        # this document must otherwise validate completely cleanly.
        packet, tool_files = self._coding_standards_packet()
        sections = _full_sections(packet["required_sections"], tool_files)
        sections["Formatting"] += (
            "\nConflicting evidence: format.sh and cpp.yml both pin "
            "clang-format independently [src: format.sh#L2] "
            "[src: .github/workflows/cpp.yml#L3]."
        )
        path = self._write_doc(_make_doc(packet, sections), path=packet["output_path"])
        result = ss.validate(self.repo_root, path, packet)
        self.assertEqual(result["failures"], [])
        self.assertTrue(result["valid"])

    # -- thin boilerplate doc must fail end to end -------------------------------- #

    def test_thin_boilerplate_standards_doc_fails(self):
        # Real incident class (Sec 1.1): a repo doc marked generated with a
        # single boilerplate sentence and zero citations -- exactly what
        # Sec 6 exists to catch before it reaches `mark-*`.
        packet, _tool_files = self._coding_standards_packet()
        thin_doc = (
            "---\n"
            "generated_by: ult-autoscaffold-content\n"
            "generated_at: 2026-01-01\n"
            "status: draft\n"
            "content_mode: grounded\n"
            "doc_kind: coding_standards\n"
            "skill_version: 2.0.0-dev\n"
            "---\n\n"
            "This module follows standard coding conventions.\n"
        )
        path = self._write_doc(thin_doc)
        result = ss.validate(self.repo_root, path, packet)
        self.assertFalse(result["valid"])
        self.assertGreaterEqual(len(result["failures"]), 3)


# --------------------------------------------------------------------------- #
# TASK-0107: mark_generated / mark_repo_doc_generated / mark_interface_generated #
# wired to ss.validate() -- blocks invalid output outright, persists a       #
# "passed" validation record + content hash on a clean pass, accepts a      #
# failure only with a non-empty --accept-validation-failure reason (as      #
# "bypassed"), and the bypass surfaces in render_index as                   #
# "VALIDATION-BYPASSED: <reason>". The orchestrator's mark-* CLI wiring     #
# already exists (TASK-0106); these tests are the dedicated coverage of    #
# that wiring's own behavior, not just of validate() in isolation.         #
# --------------------------------------------------------------------------- #

class MarkGeneratedValidationWiringTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo_root = Path(self.tmp.name)
        self.citable_files = ["src/a.py", "src/b.py", "src/c.py"]
        for f in self.citable_files:
            _write(self.repo_root / f, "line1\nline2\nline3\n")
        self.module_packet = {
            "packet_id": "how-l2--core--context",
            "layer": "how_l2",
            "kind": "context_md",
            "module_id": "core/",
            "tier": 2,
            "output_path": "org/core/CONTEXT.md",
            "template": ss.TEMPLATE_PATH_BY_KIND["context_md"],
            "content_mode_requested": "grounded",
            "content_mode": "grounded",
            "mode_reason": None,
            "required_sections": list(ss.REQUIRED_SECTIONS_BY_KIND["context_md"]),
            "probe_checklist_ref": ss.PROBE_CHECKLIST_REF_BY_KIND["context_md"],
            "must_cite": ["src/a.py"],
            "evidence_hints": dict(ss._EMPTY_EVIDENCE_HINTS),
            "domain_pack": None,
            "validation_floor": dict(ss.VALIDATION_FLOORS[("context_md", 2)]),
            "read_budget": ss.READ_BUDGET_BY_TIER[2],
            "head_commit": None,
        }
        self.good_sections = _full_sections(
            self.module_packet["required_sections"], self.citable_files
        )

    def _module_state(self):
        return {"modules": [_module("core/", 2)], "repo_docs": _repo_docs(), "interfaces": []}

    def _write_at(self, path, text):
        _write(self.repo_root / path, text)
        return path

    # -- mark_generated (module) ------------------------------------------ #

    def test_mark_generated_blocks_invalid_output_without_bypass(self):
        state = self._module_state()
        self._write_at(self.module_packet["output_path"], "not a valid doc at all\n")
        with self.assertRaises(ValueError):
            ss.mark_generated(
                state, "core/", self.module_packet["output_path"],
                packet=self.module_packet, repo_root=self.repo_root,
            )
        # The blocked attempt must not have moved the module out of pending.
        self.assertEqual(ss._find_module(state, "core/")["status"], "pending")

    def test_mark_generated_rejects_empty_string_bypass_reason(self):
        state = self._module_state()
        self._write_at(self.module_packet["output_path"], "not a valid doc at all\n")
        with self.assertRaises(ValueError):
            ss.mark_generated(
                state, "core/", self.module_packet["output_path"],
                packet=self.module_packet, repo_root=self.repo_root,
                accept_validation_failure="",
            )
        self.assertEqual(ss._find_module(state, "core/")["status"], "pending")

    def test_mark_generated_persists_passed_validation_and_hash_on_success(self):
        state = self._module_state()
        doc = _make_doc(self.module_packet, self.good_sections)
        self._write_at(self.module_packet["output_path"], doc)
        module = ss.mark_generated(
            state, "core/", self.module_packet["output_path"],
            packet=self.module_packet, repo_root=self.repo_root,
        )
        self.assertEqual(module["status"], "generated")
        self.assertEqual(module["validation"], {"status": "passed", "reasons": []})
        self.assertEqual(module["packet_id"], self.module_packet["packet_id"])
        self.assertIsNotNone(module["output_sha256"])
        self.assertIsNone(module["previous_sha256"])

    def test_mark_generated_accepts_bypass_with_nonempty_reason_and_records_it(self):
        state = self._module_state()
        self._write_at(self.module_packet["output_path"], "not a valid doc at all\n")
        module = ss.mark_generated(
            state, "core/", self.module_packet["output_path"],
            packet=self.module_packet, repo_root=self.repo_root,
            accept_validation_failure="legacy-module Tier-3 exception, PM approved",
        )
        self.assertEqual(module["status"], "generated")
        self.assertEqual(module["validation"]["status"], "bypassed")
        self.assertEqual(
            module["validation"]["bypass_reason"], "legacy-module Tier-3 exception, PM approved"
        )
        self.assertTrue(module["validation"]["reasons"])

    def test_rendered_index_flags_bypassed_module(self):
        state = self._module_state()
        self._write_at(self.module_packet["output_path"], "not a valid doc at all\n")
        ss.mark_generated(
            state, "core/", self.module_packet["output_path"],
            packet=self.module_packet, repo_root=self.repo_root,
            accept_validation_failure="approved exception",
        )
        text = ss.render_index(state, "demo-repo")
        self.assertIn("VALIDATION-BYPASSED: approved exception", text)

    def test_rendered_index_has_no_bypass_note_on_clean_pass(self):
        state = self._module_state()
        doc = _make_doc(self.module_packet, self.good_sections)
        self._write_at(self.module_packet["output_path"], doc)
        ss.mark_generated(
            state, "core/", self.module_packet["output_path"],
            packet=self.module_packet, repo_root=self.repo_root,
        )
        text = ss.render_index(state, "demo-repo")
        self.assertNotIn("VALIDATION-BYPASSED", text)

    # -- mark_repo_doc_generated -------------------------------------------- #

    def _repo_doc_packet(self):
        packet = dict(self.module_packet)
        packet.update({
            "packet_id": "repo--coding-standards",
            "kind": "coding_standards",
            "module_id": None,
            "tier": None,
            "output_path": "org/CODING-STANDARDS.md",
            "template": ss.TEMPLATE_PATH_BY_KIND["coding_standards"],
            "required_sections": list(ss.REQUIRED_SECTIONS_BY_KIND["coding_standards"]),
            "probe_checklist_ref": ss.PROBE_CHECKLIST_REF_BY_KIND["coding_standards"],
            "must_cite": [],
            "validation_floor": dict(ss.VALIDATION_FLOORS[("coding_standards", None)]),
            "read_budget": ss.READ_BUDGET_REPO_DOC,
        })
        return packet

    def test_mark_repo_doc_generated_blocks_invalid_output_without_bypass(self):
        state = {"modules": [], "repo_docs": _repo_docs(), "interfaces": []}
        packet = self._repo_doc_packet()
        self._write_at(packet["output_path"], "not a valid doc at all\n")
        with self.assertRaises(ValueError):
            ss.mark_repo_doc_generated(
                state, "coding_standards", packet["output_path"],
                packet=packet, repo_root=self.repo_root,
            )
        self.assertEqual(ss._find_repo_doc(state, "coding_standards")["status"], "pending")

    def test_mark_repo_doc_generated_persists_passed_validation_on_success(self):
        state = {"modules": [], "repo_docs": _repo_docs(), "interfaces": []}
        packet = self._repo_doc_packet()
        sections = _full_sections(packet["required_sections"], self.citable_files)
        self._write_at(packet["output_path"], _make_doc(packet, sections))
        doc = ss.mark_repo_doc_generated(
            state, "coding_standards", packet["output_path"],
            packet=packet, repo_root=self.repo_root,
        )
        self.assertEqual(doc["status"], "generated")
        self.assertEqual(doc["validation"], {"status": "passed", "reasons": []})
        self.assertIsNotNone(doc["output_sha256"])

    def test_mark_repo_doc_generated_bypass_flagged_in_index(self):
        state = {"modules": [], "repo_docs": _repo_docs(), "interfaces": []}
        packet = self._repo_doc_packet()
        self._write_at(packet["output_path"], "not a valid doc at all\n")
        ss.mark_repo_doc_generated(
            state, "coding_standards", packet["output_path"],
            packet=packet, repo_root=self.repo_root,
            accept_validation_failure="approved exception",
        )
        text = ss.render_index(state, "demo-repo")
        self.assertIn("VALIDATION-BYPASSED: approved exception", text)

    # -- mark_interface_generated -------------------------------------------- #

    def _interface_packet(self):
        packet = dict(self.module_packet)
        packet.update({
            "packet_id": "interface--core--utils",
            "kind": "interface_boundary",
            "module_id": None,
            "tier": None,
            "output_path": "org/interfaces/core-to-utils.md",
            "template": ss.TEMPLATE_PATH_BY_KIND["interface_boundary"],
            "required_sections": list(ss.REQUIRED_SECTIONS_BY_KIND["interface_boundary"]),
            "probe_checklist_ref": ss.PROBE_CHECKLIST_REF_BY_KIND["interface_boundary"],
            "must_cite": [],
            "validation_floor": dict(ss.VALIDATION_FLOORS[("interface_boundary", None)]),
            "read_budget": ss.READ_BUDGET_INTERFACE,
        })
        return packet

    def test_mark_interface_generated_blocks_invalid_output_without_bypass(self):
        interface_id = ss._interface_id("core/", "utils/")
        state = {
            "modules": [], "repo_docs": _repo_docs(),
            "interfaces": [_interface("core/", "utils/")],
        }
        packet = self._interface_packet()
        self._write_at(packet["output_path"], "not a valid doc at all\n")
        with self.assertRaises(ValueError):
            ss.mark_interface_generated(
                state, interface_id, packet["output_path"],
                packet=packet, repo_root=self.repo_root,
            )
        self.assertEqual(ss._find_interface(state, interface_id)["status"], "pending")

    def test_mark_interface_generated_persists_passed_validation_on_success(self):
        interface_id = ss._interface_id("core/", "utils/")
        state = {
            "modules": [], "repo_docs": _repo_docs(),
            "interfaces": [_interface("core/", "utils/")],
        }
        packet = self._interface_packet()
        sections = _full_sections(packet["required_sections"], self.citable_files)
        self._write_at(packet["output_path"], _make_doc(packet, sections))
        interface = ss.mark_interface_generated(
            state, interface_id, packet["output_path"],
            packet=packet, repo_root=self.repo_root,
        )
        self.assertEqual(interface["status"], "generated")
        self.assertEqual(interface["validation"], {"status": "passed", "reasons": []})
        self.assertIsNotNone(interface["output_sha256"])

    def test_mark_interface_generated_bypass_flagged_in_index(self):
        interface_id = ss._interface_id("core/", "utils/")
        state = {
            "modules": [], "repo_docs": _repo_docs(),
            "interfaces": [_interface("core/", "utils/")],
        }
        packet = self._interface_packet()
        self._write_at(packet["output_path"], "not a valid doc at all\n")
        ss.mark_interface_generated(
            state, interface_id, packet["output_path"],
            packet=packet, repo_root=self.repo_root,
            accept_validation_failure="approved exception",
        )
        text = ss.render_index(state, "demo-repo")
        self.assertIn("VALIDATION-BYPASSED: approved exception", text)


# --------------------------------------------------------------------------- #
# TASK-0108: `final=True` -- the second, terminal half of Sec 5.4's retry     #
# contract. The default (final=False, exercised above by                     #
# MarkGeneratedValidationWiringTests) is the *first* attempt: validation     #
# failure with no bypass raises and persists nothing, leaving the record     #
# pending for a retry. `final=True` is what the orchestrator passes on the   #
# retry itself: a second failure with no bypass must NOT raise -- it must    #
# be persisted as `status: "failed"` (never silently promoted to            #
# "generated"), while a bypass reason still wins over `final` either way.   #
# --------------------------------------------------------------------------- #

class FinalFailureStatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo_root = Path(self.tmp.name)
        self.citable_files = ["src/a.py", "src/b.py", "src/c.py"]
        for f in self.citable_files:
            _write(self.repo_root / f, "line1\nline2\nline3\n")
        self.module_packet = {
            "packet_id": "how-l2--core--context",
            "layer": "how_l2",
            "kind": "context_md",
            "module_id": "core/",
            "tier": 2,
            "output_path": "org/core/CONTEXT.md",
            "template": ss.TEMPLATE_PATH_BY_KIND["context_md"],
            "content_mode_requested": "grounded",
            "content_mode": "grounded",
            "mode_reason": None,
            "required_sections": list(ss.REQUIRED_SECTIONS_BY_KIND["context_md"]),
            "probe_checklist_ref": ss.PROBE_CHECKLIST_REF_BY_KIND["context_md"],
            "must_cite": ["src/a.py"],
            "evidence_hints": dict(ss._EMPTY_EVIDENCE_HINTS),
            "domain_pack": None,
            "validation_floor": dict(ss.VALIDATION_FLOORS[("context_md", 2)]),
            "read_budget": ss.READ_BUDGET_BY_TIER[2],
            "head_commit": None,
        }

    def _module_state(self):
        return {"modules": [_module("core/", 2)], "repo_docs": _repo_docs(), "interfaces": []}

    def _write_at(self, path, text):
        _write(self.repo_root / path, text)
        return path

    def test_mark_generated_final_true_persists_failed_status_without_raising(self):
        state = self._module_state()
        self._write_at(self.module_packet["output_path"], "not a valid doc at all\n")
        module = ss.mark_generated(
            state, "core/", self.module_packet["output_path"],
            packet=self.module_packet, repo_root=self.repo_root, final=True,
        )
        self.assertEqual(module["status"], "failed")
        self.assertEqual(module["validation"]["status"], "failed")
        self.assertTrue(module["validation"]["reasons"])
        self.assertEqual(module["packet_id"], self.module_packet["packet_id"])

    def test_mark_generated_final_true_leaves_content_hash_fields_untouched(self):
        state = self._module_state()
        self._write_at(self.module_packet["output_path"], "not a valid doc at all\n")
        module = ss.mark_generated(
            state, "core/", self.module_packet["output_path"],
            packet=self.module_packet, repo_root=self.repo_root, final=True,
        )
        # Rejected content was never accepted -- no hash of it is recorded.
        self.assertIsNone(module.get("output_sha256"))
        self.assertIsNone(module.get("previous_sha256"))

    def test_mark_generated_final_true_blocks_further_attempts(self):
        state = self._module_state()
        self._write_at(self.module_packet["output_path"], "not a valid doc at all\n")
        ss.mark_generated(
            state, "core/", self.module_packet["output_path"],
            packet=self.module_packet, repo_root=self.repo_root, final=True,
        )
        with self.assertRaises(ValueError):
            ss.mark_generated(
                state, "core/", self.module_packet["output_path"],
                packet=self.module_packet, repo_root=self.repo_root,
            )

    def test_mark_generated_bypass_reason_wins_over_final(self):
        state = self._module_state()
        self._write_at(self.module_packet["output_path"], "not a valid doc at all\n")
        module = ss.mark_generated(
            state, "core/", self.module_packet["output_path"],
            packet=self.module_packet, repo_root=self.repo_root, final=True,
            accept_validation_failure="approved despite retry exhaustion",
        )
        self.assertEqual(module["status"], "generated")
        self.assertEqual(module["validation"]["status"], "bypassed")

    def test_mark_generated_final_false_still_raises_and_persists_nothing(self):
        # The default (non-final) path is unchanged by adding `final` --
        # a first failed attempt still blocks outright, leaving the module
        # eligible for a retry rather than being marked "failed" outright.
        state = self._module_state()
        self._write_at(self.module_packet["output_path"], "not a valid doc at all\n")
        with self.assertRaises(ValueError):
            ss.mark_generated(
                state, "core/", self.module_packet["output_path"],
                packet=self.module_packet, repo_root=self.repo_root,
            )
        self.assertEqual(ss._find_module(state, "core/")["status"], "pending")

    def test_rendered_index_flags_failed_module(self):
        state = self._module_state()
        self._write_at(self.module_packet["output_path"], "not a valid doc at all\n")
        ss.mark_generated(
            state, "core/", self.module_packet["output_path"],
            packet=self.module_packet, repo_root=self.repo_root, final=True,
        )
        text = ss.render_index(state, "demo-repo")
        self.assertIn("VALIDATION-FAILED", text)

    def _repo_doc_packet(self):
        packet = dict(self.module_packet)
        packet.update({
            "packet_id": "repo--coding-standards",
            "kind": "coding_standards",
            "module_id": None,
            "tier": None,
            "output_path": "org/CODING-STANDARDS.md",
            "template": ss.TEMPLATE_PATH_BY_KIND["coding_standards"],
            "required_sections": list(ss.REQUIRED_SECTIONS_BY_KIND["coding_standards"]),
            "probe_checklist_ref": ss.PROBE_CHECKLIST_REF_BY_KIND["coding_standards"],
            "must_cite": [],
            "validation_floor": dict(ss.VALIDATION_FLOORS[("coding_standards", None)]),
            "read_budget": ss.READ_BUDGET_REPO_DOC,
        })
        return packet

    def test_mark_repo_doc_generated_final_true_persists_failed_status(self):
        state = {"modules": [], "repo_docs": _repo_docs(), "interfaces": []}
        packet = self._repo_doc_packet()
        self._write_at(packet["output_path"], "not a valid doc at all\n")
        doc = ss.mark_repo_doc_generated(
            state, "coding_standards", packet["output_path"],
            packet=packet, repo_root=self.repo_root, final=True,
        )
        self.assertEqual(doc["status"], "failed")
        self.assertEqual(doc["validation"]["status"], "failed")

    def _interface_packet(self):
        packet = dict(self.module_packet)
        packet.update({
            "packet_id": "interface--core--utils",
            "kind": "interface_boundary",
            "module_id": None,
            "tier": None,
            "output_path": "org/interfaces/core-to-utils.md",
            "template": ss.TEMPLATE_PATH_BY_KIND["interface_boundary"],
            "required_sections": list(ss.REQUIRED_SECTIONS_BY_KIND["interface_boundary"]),
            "probe_checklist_ref": ss.PROBE_CHECKLIST_REF_BY_KIND["interface_boundary"],
            "must_cite": [],
            "validation_floor": dict(ss.VALIDATION_FLOORS[("interface_boundary", None)]),
            "read_budget": ss.READ_BUDGET_INTERFACE,
        })
        return packet

    def test_mark_interface_generated_final_true_persists_failed_status(self):
        interface_id = ss._interface_id("core/", "utils/")
        state = {
            "modules": [], "repo_docs": _repo_docs(),
            "interfaces": [_interface("core/", "utils/")],
        }
        packet = self._interface_packet()
        self._write_at(packet["output_path"], "not a valid doc at all\n")
        interface = ss.mark_interface_generated(
            state, interface_id, packet["output_path"],
            packet=packet, repo_root=self.repo_root, final=True,
        )
        self.assertEqual(interface["status"], "failed")
        self.assertEqual(interface["validation"]["status"], "failed")


# --------------------------------------------------------------------------- #
# TASK-0108: _normalized_body_hash -- Sec 9.3/9.4's normalized               #
# LF/trailing-whitespace/body-only hashing, exercised directly rather than   #
# only incidentally through mark_generated's success-path tests above.      #
# --------------------------------------------------------------------------- #

class NormalizedBodyHashTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo_root = Path(self.tmp.name)

    def _doc(self, body, generated_at="2026-01-01"):
        return (
            "---\n"
            "generated_by: ult-autoscaffold-content\n"
            "generated_at: {}\n"
            "status: draft\n"
            "content_mode: grounded\n"
            "doc_kind: context_md\n"
            "skill_version: 2.0.0-dev\n"
            "---\n"
            "{}"
        ).format(generated_at, body)

    def test_hash_ignores_frontmatter_differences(self):
        a = self.repo_root / "a.md"
        b = self.repo_root / "b.md"
        _write(a, self._doc("## Purpose\n\nSame body.\n", generated_at="2026-01-01"))
        _write(b, self._doc("## Purpose\n\nSame body.\n", generated_at="2099-12-31"))
        self.assertEqual(ss._normalized_body_hash(a), ss._normalized_body_hash(b))

    def test_hash_normalizes_crlf_to_lf(self):
        # write_bytes, not _write/write_text: on Windows, text-mode write
        # would itself translate "\n" -> "\r\n" and corrupt the CRLF fixture
        # (double-translating the "\n" inside the "\r\n" we just inserted).
        # Writing exact bytes is the only way to get a genuine CRLF file on
        # disk regardless of platform.
        a = self.repo_root / "a.md"
        b = self.repo_root / "b.md"
        body_lf = "## Purpose\n\nSame body.\n"
        body_crlf = body_lf.replace("\n", "\r\n")
        a.write_bytes(self._doc(body_lf).encode("utf-8"))
        b.write_bytes(self._doc(body_crlf).encode("utf-8"))
        self.assertEqual(ss._normalized_body_hash(a), ss._normalized_body_hash(b))

    def test_hash_strips_trailing_whitespace_per_line(self):
        a = self.repo_root / "a.md"
        b = self.repo_root / "b.md"
        _write(a, self._doc("## Purpose\n\nSame body.\n"))
        _write(b, self._doc("## Purpose   \n\nSame body.\t\n"))
        self.assertEqual(ss._normalized_body_hash(a), ss._normalized_body_hash(b))

    def test_hash_differs_for_different_body_content(self):
        a = self.repo_root / "a.md"
        b = self.repo_root / "b.md"
        _write(a, self._doc("## Purpose\n\nOne body.\n"))
        _write(b, self._doc("## Purpose\n\nA different body entirely.\n"))
        self.assertNotEqual(ss._normalized_body_hash(a), ss._normalized_body_hash(b))


# --------------------------------------------------------------------------- #
# TASK-0108: stale packet HEAD -- proposal risk table line 490: "Each packet #
# records the HEAD commit. `mark-*` warns if HEAD has changed since the     #
# packet was created." Advisory only: validate()'s "valid"/"failures" must  #
# be unaffected either way -- only a new "warnings" key carries this.       #
# --------------------------------------------------------------------------- #

class StalePacketHeadWarningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo_root = Path(self.tmp.name)
        self.citable_files = ["src/a.py", "src/b.py", "src/c.py"]
        for f in self.citable_files:
            _write(self.repo_root / f, "line1\nline2\nline3\n")
        subprocess.run(["git", "init", "-q"], cwd=self.repo_root, check=True)
        subprocess.run(
            ["git", "add", "-A"], cwd=self.repo_root, check=True,
        )
        subprocess.run(
            ["git", "-c", "user.email=t@example.com", "-c", "user.name=t",
             "commit", "-q", "-m", "init"],
            cwd=self.repo_root, check=True,
        )
        self.current_head = subprocess.run(
            ["git", "-C", str(self.repo_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        self.packet = {
            "packet_id": "how-l2--core--context",
            "layer": "how_l2",
            "kind": "context_md",
            "module_id": "core/",
            "tier": 2,
            "output_path": "org/core/CONTEXT.md",
            "template": ss.TEMPLATE_PATH_BY_KIND["context_md"],
            "content_mode_requested": "grounded",
            "content_mode": "grounded",
            "mode_reason": None,
            "required_sections": list(ss.REQUIRED_SECTIONS_BY_KIND["context_md"]),
            "probe_checklist_ref": ss.PROBE_CHECKLIST_REF_BY_KIND["context_md"],
            "must_cite": ["src/a.py"],
            "evidence_hints": dict(ss._EMPTY_EVIDENCE_HINTS),
            "domain_pack": None,
            "validation_floor": dict(ss.VALIDATION_FLOORS[("context_md", 2)]),
            "read_budget": ss.READ_BUDGET_BY_TIER[2],
            "head_commit": self.current_head,
        }
        sections = _full_sections(self.packet["required_sections"], self.citable_files)
        _write(self.repo_root / self.packet["output_path"], _make_doc(self.packet, sections))

    def test_no_warning_when_head_commit_matches_current_head(self):
        result = ss.validate(self.repo_root, self.packet["output_path"], self.packet)
        self.assertTrue(result["valid"])
        self.assertEqual(result.get("warnings", []), [])

    def test_warns_when_packet_head_commit_differs_from_current_head(self):
        packet = dict(self.packet)
        packet["head_commit"] = "0" * 40
        result = ss.validate(self.repo_root, packet["output_path"], packet)
        self.assertTrue(any("HEAD" in w for w in result["warnings"]))

    def test_warning_does_not_affect_validity_or_failures(self):
        packet = dict(self.packet)
        packet["head_commit"] = "0" * 40
        result = ss.validate(self.repo_root, packet["output_path"], packet)
        self.assertTrue(result["valid"])
        self.assertEqual(result["failures"], [])

    def test_no_warning_when_packet_head_commit_is_none(self):
        packet = dict(self.packet)
        packet["head_commit"] = None
        result = ss.validate(self.repo_root, packet["output_path"], packet)
        self.assertEqual(result.get("warnings", []), [])


# --------------------------------------------------------------------------- #
# TASK-0108/0109: state_lock() -- Sec 9.3's file lock, proposal line 252:    #
# "A file lock (`TRIAGE-STATE.json.lock`, created with `O_EXCL` and cleaned  #
# up if stale) protects the whole-file rewrite in case an orchestrator ever #
# violates the single-writer rule." Defense in depth, not a substitute for  #
# the orchestrator-is-sole-writer discipline documented elsewhere.          #
# --------------------------------------------------------------------------- #

class StateLockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state_path = Path(self.tmp.name) / "TRIAGE-STATE.json"

    def test_lock_path_naming_convention(self):
        self.assertEqual(
            ss._lock_path_for(self.state_path),
            Path(str(self.state_path) + ".lock"),
        )

    def test_acquire_release_cycle_leaves_no_lock_file_behind(self):
        with ss.state_lock(self.state_path):
            self.assertTrue(ss._lock_path_for(self.state_path).exists())
        self.assertFalse(ss._lock_path_for(self.state_path).exists())

    def test_concurrent_acquire_raises_state_lock_error(self):
        with ss.state_lock(self.state_path):
            with self.assertRaises(ss.StateLockError):
                with ss.state_lock(self.state_path):
                    pass
        self.assertFalse(ss._lock_path_for(self.state_path).exists())

    def test_fresh_lock_is_not_treated_as_stale(self):
        with self.assertRaises(ss.StateLockError):
            with ss.state_lock(self.state_path, stale_after_seconds=3600):
                with ss.state_lock(self.state_path, stale_after_seconds=3600):
                    pass

    def test_stale_lock_is_cleaned_up_and_fresh_acquire_succeeds(self):
        lock_path = ss._lock_path_for(self.state_path)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text("", encoding="utf-8")
        stale_time = time.time() - 3600
        os.utime(lock_path, (stale_time, stale_time))
        with ss.state_lock(self.state_path, stale_after_seconds=120):
            pass  # must not raise -- the stale lock is cleaned up first.
        self.assertFalse(lock_path.exists())

    def test_lock_released_even_if_body_raises(self):
        with self.assertRaises(RuntimeError):
            with ss.state_lock(self.state_path):
                raise RuntimeError("boom")
        self.assertFalse(ss._lock_path_for(self.state_path).exists())


# --------------------------------------------------------------------------- #
# TASK-0108: backward-compatible schema-1 backfill -- a state file written   #
# before v2's per-record fields existed must still load and render cleanly. #
# --------------------------------------------------------------------------- #

class SchemaBackfillTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state_path = Path(self.tmp.name) / "TRIAGE-STATE.json"

    def _write_legacy_state(self):
        legacy = {
            "schema_version": 1,
            "repo_scan": {"graph_source": None, "graph_path": None, "scanned_at": None},
            "modules": [
                {
                    "id": "core/",
                    "tier": 2,
                    "in_degree": None,
                    "file_count": 3,
                    "basis": "heuristic",
                    "status": "generated",
                    "generated_at": "2026-01-01T00:00:00+00:00",
                    "output_path": "org/core/CONTEXT.md",
                    "skip_reason": None,
                    # No packet_id / output_sha256 / validation / previous_sha256 --
                    # this is exactly what a pre-v2 record on disk looks like.
                }
            ],
            "interfaces": [],
            "repo_docs": {
                "coding_standards": {"status": "pending", "output_path": None,
                                      "generated_at": None, "skip_reason": None},
                "testing_guidelines": {"status": "pending", "output_path": None,
                                        "generated_at": None, "skip_reason": None},
            },
            "index": {"output_path": None, "rendered_at": None},
        }
        _write(self.state_path, json.dumps(legacy, indent=2))
        return legacy

    def test_load_state_does_not_raise_on_legacy_record_missing_v2_fields(self):
        self._write_legacy_state()
        state = ss.load_state(self.state_path)
        module = ss._find_module(state, "core/")
        self.assertEqual(module["status"], "generated")
        self.assertNotIn("packet_id", module)

    def test_render_index_tolerates_legacy_record_missing_validation(self):
        self._write_legacy_state()
        state = ss.load_state(self.state_path)
        text = ss.render_index(state, "demo-repo")
        self.assertIn("core/", text)
        self.assertNotIn("VALIDATION-BYPASSED", text)
        self.assertNotIn("VALIDATION-FAILED", text)

    def test_load_state_still_backfills_top_level_schema_keys(self):
        _write(self.state_path, json.dumps({"modules": []}, indent=2))
        state = ss.load_state(self.state_path)
        self.assertEqual(state["schema_version"], ss.SCHEMA_VERSION)
        self.assertIn("repo_docs", state)
        self.assertIn("index", state)
        self.assertIn("interfaces", state)


# --------------------------------------------------------------------------- #
# TASK-0110/0111: render-index --out must match the *resolved*               #
# ult-repo-layout slot for `autoscaffold_content_index`, so CEP-INDEX.md     #
# never drifts to a second location ult-repo-layout and other skills don't  #
# know to look at. `_resolve_content_index_slot_path` is a deliberately      #
# minimal, scoped duplicate of validate_layout.py's own resolution order:   #
# marker (`.layout-slots.yaml`) if present, else the workspace_root-relative#
# default, else the hardcoded pre-D21 default.                              #
# --------------------------------------------------------------------------- #

class ResolveContentIndexSlotPathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo_root = Path(self.tmp.name)

    def test_no_marker_no_config_resolves_to_pre_d21_default(self):
        resolved = ss._resolve_content_index_slot_path(self.repo_root)
        self.assertEqual(
            resolved.as_posix(), "starter_kit/autoscaffold-content/CEP-INDEX.md"
        )

    def test_no_marker_with_workspace_root_resolves_relative_to_it(self):
        _write(
            self.repo_root / "context-config.yaml",
            "layout:\n  workspace_root: myrepo\n",
        )
        resolved = ss._resolve_content_index_slot_path(self.repo_root)
        self.assertEqual(
            resolved.as_posix(), "myrepo/cache/autoscaffold-content/CEP-INDEX.md"
        )

    def test_workspace_root_of_dot_is_malformed_falls_back_to_pre_d21_default(self):
        _write(self.repo_root / "context-config.yaml", "layout:\n  workspace_root: .\n")
        resolved = ss._resolve_content_index_slot_path(self.repo_root)
        self.assertEqual(
            resolved.as_posix(), "starter_kit/autoscaffold-content/CEP-INDEX.md"
        )

    def test_marker_overrides_default(self):
        _write(
            self.repo_root / "docs" / "index" / ".layout-slots.yaml",
            "slots:\n  - slot: autoscaffold_content_index\n"
            "    kind: file\n    file: ROUTER.md\n",
        )
        resolved = ss._resolve_content_index_slot_path(self.repo_root)
        self.assertEqual(resolved.as_posix(), "docs/index/ROUTER.md")

    def test_marker_wins_even_when_workspace_root_is_also_set(self):
        _write(
            self.repo_root / "context-config.yaml",
            "layout:\n  workspace_root: myrepo\n",
        )
        _write(
            self.repo_root / "docs" / "index" / ".layout-slots.yaml",
            "slots:\n  - slot: autoscaffold_content_index\n"
            "    kind: file\n    file: ROUTER.md\n",
        )
        resolved = ss._resolve_content_index_slot_path(self.repo_root)
        self.assertEqual(resolved.as_posix(), "docs/index/ROUTER.md")

    def test_marker_for_a_different_slot_is_ignored(self):
        _write(
            self.repo_root / "docs" / ".layout-slots.yaml",
            "slots:\n  - slot: some_other_slot\n    kind: file\n    file: OTHER.md\n",
        )
        resolved = ss._resolve_content_index_slot_path(self.repo_root)
        self.assertEqual(
            resolved.as_posix(), "starter_kit/autoscaffold-content/CEP-INDEX.md"
        )

    def test_multiple_markers_for_the_slot_raise_content_index_slot_error(self):
        _write(
            self.repo_root / "a" / ".layout-slots.yaml",
            "slots:\n  - slot: autoscaffold_content_index\n"
            "    kind: file\n    file: ROUTER.md\n",
        )
        _write(
            self.repo_root / "b" / ".layout-slots.yaml",
            "slots:\n  - slot: autoscaffold_content_index\n"
            "    kind: file\n    file: ROUTER.md\n",
        )
        with self.assertRaises(ss.ContentIndexSlotError):
            ss._resolve_content_index_slot_path(self.repo_root)

    def test_marker_under_git_dir_is_ignored(self):
        _write(
            self.repo_root / ".git" / "weird" / ".layout-slots.yaml",
            "slots:\n  - slot: autoscaffold_content_index\n"
            "    kind: file\n    file: ROUTER.md\n",
        )
        resolved = ss._resolve_content_index_slot_path(self.repo_root)
        self.assertEqual(
            resolved.as_posix(), "starter_kit/autoscaffold-content/CEP-INDEX.md"
        )


class RenderIndexOutSlotEnforcementTests(unittest.TestCase):
    """`_cmd_render_index`'s --out must be refused unless it resolves to the
    same path as `_resolve_content_index_slot_path` -- otherwise CEP-INDEX.md
    could silently be written somewhere ult-repo-layout never resolves to."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo_root = Path(self.tmp.name)
        self.state_path = self.repo_root / "TRIAGE-STATE.json"
        _write(self.state_path, json.dumps({"modules": []}, indent=2))

    def _run(self, out_rel, repo_root=None):
        args = argparse.Namespace(
            state=self.state_path,
            repo_name="demo-repo",
            out=str(out_rel),
            repo_root=str(repo_root if repo_root is not None else self.repo_root),
        )
        return ss._cmd_render_index(args)

    def test_out_matching_resolved_default_succeeds(self):
        rc = self._run(self.repo_root / "starter_kit/autoscaffold-content/CEP-INDEX.md")
        self.assertEqual(rc, 0)
        self.assertTrue(
            (self.repo_root / "starter_kit/autoscaffold-content/CEP-INDEX.md").exists()
        )

    def test_out_not_matching_resolved_default_is_refused(self):
        rc = self._run(self.repo_root / "somewhere/else/CEP-INDEX.md")
        self.assertEqual(rc, 1)
        self.assertFalse((self.repo_root / "somewhere/else/CEP-INDEX.md").exists())

    def test_out_missing_repo_root_is_refused(self):
        args = argparse.Namespace(
            state=self.state_path,
            repo_name="demo-repo",
            out=str(self.repo_root / "starter_kit/autoscaffold-content/CEP-INDEX.md"),
            repo_root=None,
        )
        rc = ss._cmd_render_index(args)
        self.assertEqual(rc, 1)

    def test_out_matching_marker_resolved_path_succeeds(self):
        _write(
            self.repo_root / "docs" / "index" / ".layout-slots.yaml",
            "slots:\n  - slot: autoscaffold_content_index\n"
            "    kind: file\n    file: ROUTER.md\n",
        )
        rc = self._run(self.repo_root / "docs/index/ROUTER.md")
        self.assertEqual(rc, 0)
        self.assertTrue((self.repo_root / "docs/index/ROUTER.md").exists())

    def test_stdout_only_call_without_out_does_not_require_repo_root(self):
        # Preserves the pre-existing no --out / stdout-only behavior for
        # every caller that never passes --repo-root (e.g. existing SKILL.md
        # invocations that only print to stdout).
        args = argparse.Namespace(
            state=self.state_path, repo_name="demo-repo", out=None, repo_root=None,
        )
        rc = ss._cmd_render_index(args)
        self.assertEqual(rc, 0)

    def test_ambiguous_markers_refuse_rather_than_pick_one(self):
        _write(
            self.repo_root / "a" / ".layout-slots.yaml",
            "slots:\n  - slot: autoscaffold_content_index\n"
            "    kind: file\n    file: ROUTER.md\n",
        )
        _write(
            self.repo_root / "b" / ".layout-slots.yaml",
            "slots:\n  - slot: autoscaffold_content_index\n"
            "    kind: file\n    file: ROUTER.md\n",
        )
        rc = self._run(self.repo_root / "a/ROUTER.md")
        self.assertEqual(rc, 1)


class ListInterfacesWithSitesCLITests(unittest.TestCase):
    """`list-interfaces --with-sites` -- the CLI surface over
    _interface_call_sites() (TASK-0205). Exercises _cmd_list_interfaces()
    and the main() argparse wiring directly, matching this suite's existing
    argparse.Namespace() convention for CLI-entry-point tests."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo_root = Path(self.tmp.name)
        self.state_path = self.repo_root / "TRIAGE-STATE.json"
        self.graph_path = self.repo_root / "graph.json"
        _write(self.graph_path, json.dumps(_fixture_graph()))
        _write(
            self.repo_root / "core" / "main.py",
            "def run():\n    utils_helpers_add(1, 2)\n",
        )
        state = {
            "modules": [], "repo_docs": {},
            "interfaces": [{
                "id": "core--utils", "module_a": "core", "module_b": "utils",
                "relations": ["calls", "imports", "imports_from"], "weight": 4,
                "status": "pending", "output_path": None,
                "generated_at": None, "defer_reason": None,
            }],
        }
        _write(self.state_path, json.dumps(state))

    def _run(self, **extra):
        args = argparse.Namespace(
            state=str(self.state_path), eligible_only=False,
            with_sites=False, repo_root=None, graph_path=None,
        )
        for k, v in extra.items():
            setattr(args, k, v)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = ss._cmd_list_interfaces(args)
        return rc, buf.getvalue()

    def test_with_sites_adds_call_sites_key_from_the_loaded_graph(self):
        rc, out = self._run(
            with_sites=True, repo_root=str(self.repo_root), graph_path=str(self.graph_path),
        )
        self.assertEqual(rc, 0)
        entries = json.loads(out)
        self.assertEqual(len(entries), 1)
        self.assertIn("core/main.py:L2", entries[0]["call_sites"])

    def test_without_with_sites_no_call_sites_key_at_all(self):
        rc, out = self._run()
        self.assertEqual(rc, 0)
        entries = json.loads(out)
        self.assertNotIn("call_sites", entries[0])

    def test_with_sites_without_repo_root_refuses(self):
        rc, out = self._run(with_sites=True, graph_path=str(self.graph_path))
        self.assertEqual(rc, 1)

    def test_with_sites_without_graph_path_refuses(self):
        rc, out = self._run(with_sites=True, repo_root=str(self.repo_root))
        self.assertEqual(rc, 1)

    def test_with_sites_missing_graph_file_reports_error_not_crash(self):
        rc, out = self._run(
            with_sites=True, repo_root=str(self.repo_root),
            graph_path=str(self.repo_root / "missing-graph.json"),
        )
        self.assertEqual(rc, 1)


class ContentModePrecedenceTests(unittest.TestCase):
    """TASK-0301 (AutoScaffold_Mode_Plan.md Phase 3 / P1). REQ-001's
    precedence chain for `content_mode_requested`, resolved by
    `resolve_content_mode(kind, layer, prompt_override=, config_overrides=,
    global_mode=)`, highest wins:

      1. prompt_override      -- explicit instruction this run
      2. config_overrides[kind] -- per-(layer, kind) config override
      3. global_mode          -- the config's global content_mode value
      4. the per-layer default -- no flat constant: TASK-0303 states this
         explicitly as "default What-L2 overview to skeleton", which only
         makes sense as a *per-layer* default, not a single global one --
         how_l2 (today's only implemented packet layer) defaults to
         "grounded", matching current pre-P1 behaviour, while what_l2
         (no packet-generation path in this release) defaults to
         "skeleton" until a mode is explicitly requested for it (still
         capped at "grounded" per Sec 4.4/F4 if someone does ask for
         more). See DefaultModeByLayerTests for the level-4 cases
         specifically.

    Most tests here pin the requested-mode winner using coding_standards
    under how_l2, the one (layer, kind) pair whose cap is "augmented"
    (Sec 4.4/F15), so the cap never masks the precedence result. Cap and
    evidence-gate clamping are covered separately by
    ContentModeCapMatrixTests and ContentModeEvidenceGateTests.
    """

    def test_no_inputs_defaults_to_grounded_for_how_l2(self):
        result = ss.resolve_content_mode("coding_standards", ss.PACKET_LAYER)
        self.assertEqual(result["content_mode_requested"], "grounded")
        self.assertEqual(result["content_mode"], "grounded")
        self.assertIsNone(result["mode_reason"])

    def test_global_mode_beats_default(self):
        result = ss.resolve_content_mode(
            "coding_standards", ss.PACKET_LAYER, global_mode="skeleton",
        )
        self.assertEqual(result["content_mode_requested"], "skeleton")

    def test_config_override_beats_global_mode(self):
        result = ss.resolve_content_mode(
            "coding_standards", ss.PACKET_LAYER,
            config_overrides={"coding_standards": "augmented"},
            global_mode="skeleton",
        )
        self.assertEqual(result["content_mode_requested"], "augmented")

    def test_config_override_only_applies_to_its_own_kind(self):
        # A testing_guidelines override must not leak into a
        # coding_standards resolution -- overrides are per-(layer, kind).
        result = ss.resolve_content_mode(
            "coding_standards", ss.PACKET_LAYER,
            config_overrides={"testing_guidelines": "augmented"},
            global_mode="skeleton",
        )
        self.assertEqual(result["content_mode_requested"], "skeleton")

    def test_prompt_override_beats_everything(self):
        result = ss.resolve_content_mode(
            "coding_standards", ss.PACKET_LAYER,
            prompt_override="skeleton",
            config_overrides={"coding_standards": "augmented"},
            global_mode="augmented",
        )
        self.assertEqual(result["content_mode_requested"], "skeleton")

    def test_invalid_prompt_override_raises_before_resolving(self):
        with self.assertRaises(ValueError):
            ss.resolve_content_mode(
                "coding_standards", ss.PACKET_LAYER, prompt_override="thorough",
            )

    def test_invalid_config_override_raises(self):
        with self.assertRaises(ValueError):
            ss.resolve_content_mode(
                "coding_standards", ss.PACKET_LAYER,
                config_overrides={"coding_standards": "verbose"},
            )

    def test_invalid_global_mode_raises(self):
        with self.assertRaises(ValueError):
            ss.resolve_content_mode(
                "coding_standards", ss.PACKET_LAYER, global_mode="full",
            )

    def test_config_override_for_a_different_kind_does_not_raise(self):
        # An invalid value under a kind that isn't being resolved right now
        # must not block this resolution -- only the entry actually in play
        # is validated.
        result = ss.resolve_content_mode(
            "coding_standards", ss.PACKET_LAYER,
            config_overrides={"testing_guidelines": "not-a-mode"},
        )
        self.assertEqual(result["content_mode_requested"], "grounded")


class DefaultModeByLayerTests(unittest.TestCase):
    """TASK-0303's own wording -- "Default What-L2 overview to skeleton;
    allow grounded on explicit request" -- only makes sense if
    precedence level 4 (REQ-001) is a *per-layer* default, not the single
    flat "grounded" a plain reading of proposal Sec 9.1 ("Absent means
    grounded") would suggest for every layer alike. how_l2 is today's
    only implemented packet layer, so its default of "grounded" simply
    continues current pre-P1 behaviour (every how_l2 packet already ships
    grounded content unconditionally); what_l2 has no packet-generation
    path in this release at all, so its default is the conservative
    "skeleton" -- it still honours an explicit request up to its own cap
    ("grounded", Sec 4.4/F4), it just never volunteers grounded content
    for a layer that isn't implemented yet.
    """

    def test_how_l2_kind_with_no_inputs_defaults_to_grounded(self):
        for kind in ("context_md", "coding_standards", "testing_guidelines", "interface_boundary"):
            result = ss.resolve_content_mode(kind, "how_l2")
            self.assertEqual(result["content_mode_requested"], "grounded", kind)

    def test_what_l2_kind_with_no_inputs_defaults_to_skeleton(self):
        for kind in ("context_md", "requirements_overview"):
            result = ss.resolve_content_mode(kind, "what_l2")
            self.assertEqual(result["content_mode_requested"], "skeleton", kind)
            self.assertEqual(result["content_mode"], "skeleton", kind)

    def test_what_l2_kind_honours_explicit_grounded_request(self):
        # "allow grounded on explicit request" -- the low per-layer
        # default is not a ceiling; an explicit ask still resolves to
        # grounded (what_l2's own cap), same as any other layer.
        result = ss.resolve_content_mode(
            "requirements_overview", "what_l2", prompt_override="grounded",
        )
        self.assertEqual(result["content_mode_requested"], "grounded")
        self.assertEqual(result["content_mode"], "grounded")
        self.assertIsNone(result["mode_reason"])

    def test_what_l2_kind_explicit_augmented_request_still_capped_at_grounded(self):
        # The low default doesn't change the cap: F4 still caps every
        # what_l2 kind at grounded even when the request is explicit.
        result = ss.resolve_content_mode(
            "requirements_overview", "what_l2", prompt_override="augmented",
        )
        self.assertEqual(result["content_mode"], "grounded")
        self.assertIsNotNone(result["mode_reason"])

    def test_global_mode_still_overrides_the_what_l2_default(self):
        result = ss.resolve_content_mode(
            "requirements_overview", "what_l2", global_mode="grounded",
        )
        self.assertEqual(result["content_mode_requested"], "grounded")

    def test_unlisted_layer_defaults_to_the_safest_mode(self):
        # Any future layer not yet in the default table must fail safe
        # (skeleton -- no claims) rather than silently inherit how_l2's
        # grounded default.
        result = ss.resolve_content_mode("some_future_kind", "some_future_layer")
        self.assertEqual(result["content_mode_requested"], "skeleton")


class ContentModeCapMatrixTests(unittest.TestCase):
    """The (layer, kind) ceiling matrix (proposal Sec 4.4), corrected by
    adversarial-review F4 (keyed on (layer, kind), not kind alone --
    context_md is written under both what_l2 and how_l2 with different
    ceilings) and F15 (v1 simplification: the "augmented, restricted"
    distinction for CONTEXT.md/architecture overview can't be
    linted/enforced, so v1 caps everything except how_l2's
    coding_standards/testing_guidelines at grounded). content_mode =
    min(requested, cap) -- these tests always request "augmented" (the
    highest mode) so the cap is what's under test, not precedence.
    """

    def test_how_l2_coding_standards_reaches_augmented(self):
        result = ss.resolve_content_mode(
            "coding_standards", "how_l2", prompt_override="augmented",
        )
        self.assertEqual(result["content_mode"], "augmented")
        self.assertIsNone(result["mode_reason"])

    def test_how_l2_testing_guidelines_reaches_augmented(self):
        result = ss.resolve_content_mode(
            "testing_guidelines", "how_l2", prompt_override="augmented",
        )
        self.assertEqual(result["content_mode"], "augmented")
        self.assertIsNone(result["mode_reason"])

    def test_how_l2_context_md_caps_at_grounded(self):
        # F15: the "restricted" carve-out for CONTEXT.md can't be
        # enforced automatically, so v1 caps it at grounded even though
        # the original proposal draft allowed "augmented, restricted".
        result = ss.resolve_content_mode(
            "context_md", "how_l2", prompt_override="augmented",
        )
        self.assertEqual(result["content_mode"], "grounded")
        self.assertIsNotNone(result["mode_reason"])

    def test_how_l2_architecture_overview_caps_at_grounded(self):
        result = ss.resolve_content_mode(
            "architecture_overview", "how_l2", prompt_override="augmented",
        )
        self.assertEqual(result["content_mode"], "grounded")

    def test_how_l2_interface_boundary_caps_at_grounded(self):
        result = ss.resolve_content_mode(
            "interface_boundary", "how_l2", prompt_override="augmented",
        )
        self.assertEqual(result["content_mode"], "grounded")

    def test_what_l2_context_md_caps_at_grounded_regardless_of_kind(self):
        # F4: What-L2 is always capped at grounded, whatever kind name is
        # used -- context_md is the exact kind name that collides with
        # the how_l2 row above, so this pins the layer (not just the
        # kind string) as the discriminator.
        result = ss.resolve_content_mode(
            "context_md", "what_l2", prompt_override="augmented",
        )
        self.assertEqual(result["content_mode"], "grounded")

    def test_what_l2_requirements_overview_caps_at_grounded(self):
        result = ss.resolve_content_mode(
            "requirements_overview", "what_l2", prompt_override="augmented",
        )
        self.assertEqual(result["content_mode"], "grounded")

    def test_cap_never_upgrades_a_lower_request(self):
        # A cap is a ceiling, never a floor -- requesting skeleton under a
        # kind capped at augmented must still yield skeleton.
        result = ss.resolve_content_mode(
            "coding_standards", "how_l2", prompt_override="skeleton",
        )
        self.assertEqual(result["content_mode"], "skeleton")
        self.assertIsNone(result["mode_reason"])

    def test_grounded_request_under_augmented_cap_is_unaffected(self):
        result = ss.resolve_content_mode(
            "coding_standards", "how_l2", prompt_override="grounded",
        )
        self.assertEqual(result["content_mode"], "grounded")
        self.assertIsNone(result["mode_reason"])

    def test_unknown_layer_kind_pair_defaults_to_grounded_cap(self):
        # Anything not explicitly listed in the cap matrix caps at
        # grounded -- v1 has no uncapped (layer, kind) pair.
        result = ss.resolve_content_mode(
            "some_future_kind", "how_l2", prompt_override="augmented",
        )
        self.assertEqual(result["content_mode"], "grounded")


class ContentModeEvidenceGateTests(unittest.TestCase):
    """The evidence gate (proposal Sec 6.2): a requested/capped mode above
    skeleton collapses to skeleton when its kind lacks grounded-mode
    evidence. `evidence` is the dict probe_size() already returns
    (`greenfield`, `grounded_viable` keyed by GROUNDED_VIABLE_KINDS) --
    resolve_content_mode() takes it as-is, no adapter needed.
    """

    def _evidence(self, greenfield=False, **grounded_viable):
        return {"greenfield": greenfield, "grounded_viable": grounded_viable}

    def test_no_evidence_argument_never_downgrades(self):
        # Callers that haven't run probe-evidence yet (or don't need to,
        # e.g. tests above) get pre-P1 behaviour: no evidence gate applied.
        result = ss.resolve_content_mode(
            "coding_standards", "how_l2", prompt_override="augmented",
        )
        self.assertEqual(result["content_mode"], "augmented")

    def test_viable_kind_is_not_downgraded(self):
        evidence = self._evidence(coding_standards=True)
        result = ss.resolve_content_mode(
            "coding_standards", "how_l2", prompt_override="grounded",
            evidence=evidence,
        )
        self.assertEqual(result["content_mode"], "grounded")
        self.assertIsNone(result["mode_reason"])

    def test_non_viable_kind_collapses_to_skeleton(self):
        evidence = self._evidence(coding_standards=False)
        result = ss.resolve_content_mode(
            "coding_standards", "how_l2", prompt_override="grounded",
            evidence=evidence,
        )
        self.assertEqual(result["content_mode"], "skeleton")
        self.assertIsNotNone(result["mode_reason"])

    def test_non_viable_kind_does_not_affect_a_different_kind(self):
        # testing_guidelines lacking evidence must not collapse a
        # coding_standards resolution in the same run.
        evidence = self._evidence(coding_standards=True, testing_guidelines=False)
        result = ss.resolve_content_mode(
            "coding_standards", "how_l2", prompt_override="grounded",
            evidence=evidence,
        )
        self.assertEqual(result["content_mode"], "grounded")

    def test_greenfield_collapses_every_kind_to_skeleton(self):
        # TASK-0303 (plan doc): "Greenfield downgrades every kind to
        # skeleton" -- unconditional, even for coding_standards/
        # testing_guidelines whose grounded_viable happens to read True
        # (greenfield always wins; Sec 6.2).
        evidence = self._evidence(
            greenfield=True, coding_standards=True, testing_guidelines=True,
        )
        for kind in ("coding_standards", "testing_guidelines", "context_md"):
            result = ss.resolve_content_mode(
                kind, "how_l2", prompt_override="augmented", evidence=evidence,
            )
            self.assertEqual(result["content_mode"], "skeleton", kind)
            self.assertIsNotNone(result["mode_reason"])

    def test_kind_outside_grounded_viable_kinds_is_viable_unless_greenfield(self):
        # context_md/interface_boundary/architecture_overview have no
        # entry in GROUNDED_VIABLE_KINDS -- they're evidenced by the
        # module/interface's own existence, so they're viable whenever the
        # repo isn't greenfield, with no signal dict entry needed for them.
        evidence = self._evidence()
        result = ss.resolve_content_mode(
            "context_md", "how_l2", prompt_override="grounded", evidence=evidence,
        )
        self.assertEqual(result["content_mode"], "grounded")

    def test_requesting_skeleton_is_never_gated(self):
        # skeleton mode makes no claims to evidence -- the gate only ever
        # applies to grounded/augmented.
        evidence = self._evidence(greenfield=True)
        result = ss.resolve_content_mode(
            "coding_standards", "how_l2", prompt_override="skeleton",
            evidence=evidence,
        )
        self.assertEqual(result["content_mode"], "skeleton")
        self.assertIsNone(result["mode_reason"])


if __name__ == "__main__":
    unittest.main()
