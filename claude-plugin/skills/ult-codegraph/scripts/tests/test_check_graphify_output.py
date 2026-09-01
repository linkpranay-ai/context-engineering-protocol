"""Tests for check_graphify_output.py (the 2026-08-31 Round-2 evaluation's finding on the codegraph sanity-check invocation not being runnable as documented). Stdlib unittest only. Run with:

python -m unittest discover -s scripts/tests -v
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import check_graphify_output as cgo  # noqa: E402


def _init_git_repo(root):
    """Same minimal git-fixture shape test_validate_layout.py's own
    `_git_repo` helper uses elsewhere in this project - a real commit is
    the only way to get a real HEAD timestamp to compare `graph.json`'s
    mtime against."""
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    (root / "a.txt").write_text("a", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True)


class TestCheckGraphifyOutput(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_never_ran_when_graphify_out_missing(self):
        result = cgo.check_graphify_output(self.root)
        self.assertEqual(result.status, cgo.NEVER_RAN)
        self.assertFalse(result.ok)
        self.assertIn("No `graphify-out/` found", result.message)
        self.assertEqual(result.troubleshooting, [])

    def test_partial_failure_when_cache_exists_but_no_graph_json(self):
        # The exact repro: graphify-out/cache/ exists, graph.json doesn't.
        (self.root / "graphify-out" / "cache").mkdir(parents=True)
        result = cgo.check_graphify_output(self.root)
        self.assertEqual(result.status, cgo.PARTIAL_FAILURE)
        self.assertFalse(result.ok)
        self.assertIn("graph.json` was never written", result.message)
        self.assertIn(
            cgo.WINDOWS_ACCESS_DENIED_SIGNATURE, result.troubleshooting[0]
        )

    def test_empty_or_corrupt_when_graph_json_is_zero_length(self):
        out_dir = self.root / "graphify-out"
        out_dir.mkdir()
        (out_dir / "graph.json").write_text("", encoding="utf-8")
        result = cgo.check_graphify_output(self.root)
        self.assertEqual(result.status, cgo.EMPTY_OR_CORRUPT)
        self.assertFalse(result.ok)
        self.assertIn("is empty", result.message)
        self.assertTrue(result.troubleshooting)

    def test_empty_or_corrupt_when_graph_json_is_invalid_json(self):
        out_dir = self.root / "graphify-out"
        out_dir.mkdir()
        (out_dir / "graph.json").write_text("{not valid json", encoding="utf-8")
        result = cgo.check_graphify_output(self.root)
        self.assertEqual(result.status, cgo.EMPTY_OR_CORRUPT)
        self.assertIn("not valid JSON", result.message)

    def test_empty_or_corrupt_when_graph_json_has_only_empty_containers(self):
        out_dir = self.root / "graphify-out"
        out_dir.mkdir()
        (out_dir / "graph.json").write_text(
            json.dumps({"nodes": [], "edges": []}), encoding="utf-8"
        )
        result = cgo.check_graphify_output(self.root)
        self.assertEqual(result.status, cgo.EMPTY_OR_CORRUPT)
        self.assertIn("no graph content", result.message)
        # This state isn't the Windows-repro state, so no Windows-specific
        # troubleshooting is attached here.
        self.assertEqual(result.troubleshooting, [])

    def test_empty_or_corrupt_when_graph_json_is_bare_empty_dict(self):
        out_dir = self.root / "graphify-out"
        out_dir.mkdir()
        (out_dir / "graph.json").write_text("{}", encoding="utf-8")
        result = cgo.check_graphify_output(self.root)
        self.assertEqual(result.status, cgo.EMPTY_OR_CORRUPT)

    def test_ok_when_graph_json_has_content(self):
        out_dir = self.root / "graphify-out"
        out_dir.mkdir()
        (out_dir / "graph.json").write_text(
            json.dumps(
                {
                    "nodes": [{"id": "a::foo", "label": "foo"}],
                    "edges": [],
                }
            ),
            encoding="utf-8",
        )
        result = cgo.check_graphify_output(self.root)
        self.assertEqual(result.status, cgo.OK)
        self.assertTrue(result.ok)
        self.assertIn("looks populated", result.message)
        self.assertEqual(result.troubleshooting, [])

    def test_main_returns_zero_on_ok_and_nonzero_on_failure(self):
        # never_ran -> nonzero
        self.assertEqual(cgo.main([str(self.root)]), 1)

        # ok -> zero
        out_dir = self.root / "graphify-out"
        out_dir.mkdir()
        (out_dir / "graph.json").write_text(
            json.dumps({"nodes": [{"id": "x"}], "edges": []}), encoding="utf-8"
        )
        self.assertEqual(cgo.main([str(self.root)]), 0)

    def test_main_defaults_to_current_directory(self):
        # No target_dir argument -> "." -> resolves against cwd, not an
        # error. Just confirm it doesn't raise and returns an int.
        result = cgo.main([])
        self.assertIsInstance(result, int)


class TestStaleGraph(unittest.TestCase):
    # The 2026-09-01 evaluation's finding on this check having no state
    # between "well-formed" and "fresh": a graph that predates the repo's
    # current HEAD commit used to still come back `ok`.
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_graph(self):
        out_dir = self.root / "graphify-out"
        out_dir.mkdir()
        graph_json = out_dir / "graph.json"
        graph_json.write_text(
            json.dumps({"nodes": [{"id": "a::foo"}], "edges": []}), encoding="utf-8"
        )
        return graph_json

    def test_graph_older_than_head_commit_is_stale(self):
        _init_git_repo(self.root)
        graph_json = self._write_graph()
        head_ts = int(
            subprocess.run(
                ["git", "log", "-1", "--format=%ct", "HEAD"],
                cwd=self.root, capture_output=True, text=True, check=True,
            ).stdout.strip()
        )
        # Force the graph to predate HEAD's commit, regardless of how fast
        # this test itself runs relative to the commit above.
        os.utime(graph_json, (head_ts - 3600, head_ts - 3600))
        result = cgo.check_graphify_output(self.root)
        self.assertEqual(result.status, cgo.STALE)
        self.assertFalse(result.ok)
        self.assertIn("predates", result.message)

    def test_graph_newer_than_head_commit_is_still_ok(self):
        _init_git_repo(self.root)
        self._write_graph()
        # Written after the commit above, so its mtime is already newer -
        # no os.utime needed.
        result = cgo.check_graphify_output(self.root)
        self.assertEqual(result.status, cgo.OK)
        self.assertTrue(result.ok)

    def test_non_git_target_falls_back_to_ok_unchanged(self):
        # No .git/ at all here - self.root is a bare tempdir, exactly the
        # fixture every pre-existing test in TestCheckGraphifyOutput uses.
        # Confirms adding staleness detection didn't change behavior for a
        # target where staleness can't be determined at all.
        self._write_graph()
        result = cgo.check_graphify_output(self.root)
        self.assertEqual(result.status, cgo.OK)


if __name__ == "__main__":
    unittest.main()
