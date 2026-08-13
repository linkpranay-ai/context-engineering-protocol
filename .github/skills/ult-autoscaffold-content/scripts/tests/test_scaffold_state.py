"""Regression suite for scaffold_state.py (D24 Phase B, ult-autoscaffold-content).

Stdlib unittest only -- no pytest dependency, so this stays vendorable along
with scaffold_state.py itself. Run with:

    python -m unittest discover -s scripts/tests -v
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scaffold_state as ss  # noqa: E402


def _write(path, content=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# A synthetic graph.json fixture in the real, empirically-verified graphify
# 0.9.11 schema (see D24 Phase B session notes -- top-level keys
# input_tokens/output_tokens/nodes/links; node id/label/file_type/
# source_file/source_location/_origin; link source/target/relation/
# context/confidence/source_file/source_location/weight). Mirrors a
# 3-module repo: core/ depends heavily on utils/ (many distinct call/import
# edges from several core symbols), legacy/ has exactly one caller (core/),
# and orphan/ has none.
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

    def test_top_level_candidate_dirs_missing_root_returns_empty(self):
        self.assertEqual(ss._top_level_candidate_dirs("/does/not/exist/anywhere"), [])

    def test_iter_files_prunes_nested_ignored_dirs(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _write(root / "core" / "main.py", "x")
            _write(root / "core" / "__pycache__" / "main.cpython.pyc", "x")
            found = sorted(p.name for p in ss._iter_files(root / "core"))
            self.assertEqual(found, ["main.py"])


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


class TierAssignmentTests(unittest.TestCase):
    def test_tier_for_graph_thresholds(self):
        self.assertEqual(ss._tier_for_graph(10, False), (1, "graph:in-degree"))
        self.assertEqual(ss._tier_for_graph(9, False), (2, "graph:in-degree"))
        self.assertEqual(ss._tier_for_graph(1, False), (2, "graph:in-degree"))
        self.assertEqual(ss._tier_for_graph(0, False), (3, "graph:in-degree"))
        self.assertEqual(ss._tier_for_graph(62, True), (0, "generated"))

    def test_tier_for_heuristic_thresholds(self):
        self.assertEqual(ss._tier_for_heuristic(50, False), (1, "heuristic:file-count"))
        self.assertEqual(ss._tier_for_heuristic(49, False), (2, "heuristic:file-count"))
        self.assertEqual(ss._tier_for_heuristic(1, False), (2, "heuristic:file-count"))
        self.assertEqual(ss._tier_for_heuristic(0, False), (3, "heuristic:file-count"))
        self.assertEqual(ss._tier_for_heuristic(5, True), (0, "generated"))


class ScanTests(unittest.TestCase):
    def _make_repo(self, root):
        _write(root / "core" / "main.py", "x")
        _write(root / "core" / "service.py", "x")
        _write(root / "utils" / "helpers.py", "x")
        _write(root / "legacy" / "old.py", "x")
        _write(root / "orphan" / "thing.py", "x")
        _write(root / "generated" / "stub.py", "x")

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
        self.assertIn("1 generated, 1 pending, 1 skipped (3 modules total)", text)

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


if __name__ == "__main__":
    unittest.main()
