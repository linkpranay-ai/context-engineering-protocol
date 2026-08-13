"""Regression suite for wizard_content_hash.py (D24 §18.3/§18.9, locked).
Stdlib unittest only. Run with:

    python -m unittest discover -s scripts/tests -v
"""

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wizard_content_hash as wch  # noqa: E402


class TestHashFile(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_file_returns_none(self):
        self.assertIsNone(wch.hash_file(self.root / "does-not-exist.yaml"))

    def test_matches_plain_sha256_of_bytes(self):
        p = self.root / "f.txt"
        p.write_bytes(b"hello world")
        expected = hashlib.sha256(b"hello world").hexdigest()
        self.assertEqual(wch.hash_file(p), expected)

    def test_same_content_same_hash(self):
        p1 = self.root / "a.txt"
        p2 = self.root / "b.txt"
        p1.write_text("identical content\n", encoding="utf-8")
        p2.write_text("identical content\n", encoding="utf-8")
        self.assertEqual(wch.hash_file(p1), wch.hash_file(p2))

    def test_different_content_different_hash(self):
        p = self.root / "f.txt"
        p.write_text("version one\n", encoding="utf-8")
        first = wch.hash_file(p)
        p.write_text("version two\n", encoding="utf-8")
        second = wch.hash_file(p)
        self.assertNotEqual(first, second)

    def test_same_size_different_content_different_hash(self):
        """A size check alone would miss this - same byte count, different
        bytes - which is exactly the case a content hash exists to catch."""
        p = self.root / "f.txt"
        p.write_text("aaaa", encoding="utf-8")
        first = wch.hash_file(p)
        p.write_text("bbbb", encoding="utf-8")
        second = wch.hash_file(p)
        self.assertNotEqual(first, second)


class TestHashConfig(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_config_returns_none(self):
        self.assertIsNone(wch.hash_config(self.root))

    def test_reads_context_config_yaml_at_repo_root(self):
        # write_bytes (not write_text) so the on-disk bytes are exactly what
        # this test hashes below - write_text's universal-newline
        # translation would turn "\n" into "\r\n" on Windows and make the
        # hand-computed expected hash wrong for the wrong reason.
        (self.root / "context-config.yaml").write_bytes(b"layers: {}\n")
        expected = hashlib.sha256(b"layers: {}\n").hexdigest()
        self.assertEqual(wch.hash_config(self.root), expected)

    def test_ignores_a_same_named_file_under_workspace_root(self):
        """hash_config always reads {repo_root}/context-config.yaml, never a
        workspace_root-relative one - mirrors confirm_layers.run_confirm's
        own config_path, which is not subject to the artifact's
        workspace_root placement dance."""
        (self.root / "context-config.yaml").write_text("layers: {}\n", encoding="utf-8")
        nested = self.root / "sub" / "context-config.yaml"
        nested.parent.mkdir(parents=True)
        nested.write_text("layers: {different: true}\n", encoding="utf-8")
        self.assertEqual(wch.hash_config(self.root), wch.hash_config(self.root))
        self.assertNotEqual(wch.hash_config(self.root), wch.hash_file(nested))


class TestHashArtifact(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_artifact_returns_none(self):
        self.assertIsNone(wch.hash_artifact(self.root / "context-layout-discovery.md"))

    def test_hashes_whatever_path_it_is_given(self):
        p = self.root / "sub" / "context-layout-discovery.md"
        p.parent.mkdir(parents=True)
        # write_bytes, not write_text - see the comment in
        # TestHashConfig.test_reads_context_config_yaml_at_repo_root.
        p.write_bytes(b"# discovery\n")
        expected = hashlib.sha256(b"# discovery\n").hexdigest()
        self.assertEqual(wch.hash_artifact(p), expected)

    def test_detects_a_change_underneath_a_staged_session(self):
        """The core round-3 H6 scenario: hash at load time, then re-hash
        right before Apply - a change in between must be detectable."""
        p = self.root / "context-layout-discovery.md"
        p.write_text("original\n", encoding="utf-8")
        loaded_hash = wch.hash_artifact(p)

        p.write_text("changed underneath the session\n", encoding="utf-8")
        current_hash = wch.hash_artifact(p)

        self.assertNotEqual(loaded_hash, current_hash)


if __name__ == "__main__":
    unittest.main()
