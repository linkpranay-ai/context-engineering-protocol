"""Tests for check_graphify_output.py (the 2026-08-31 Round-2 evaluation's finding on the codegraph sanity-check invocation not being runnable as documented). Stdlib unittest only. Run with:

python -m unittest discover -s scripts/tests -v
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import check_graphify_output as cgo  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
