"""Regression suite for content_hash.py (D19 v2, C1/C2).

Stdlib unittest only -- no pytest dependency, so this stays vendorable along
with content_hash.py itself. Run with:

    python -m unittest discover -s scripts/tests -v
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import content_hash as ch  # noqa: E402


SAMPLE_WITHOUT_HASH = (
    "context_package:\n"
    "  id: example_user-story_20260613\n"
    "  generated_at: \"2026-06-13T00:00:00Z\"\n"
    "  human_approved: true\n"
)

SAMPLE_WITH_HASH = (
    "context_package:\n"
    "  id: example_user-story_20260613\n"
    "  generated_at: \"2026-06-13T00:00:00Z\"\n"
    "  human_approved: true\n"
    "  content_hash: deadbeef\n"
)


def write_tmp(content, suffix=".yaml"):
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False, encoding="utf-8", newline=""
    )
    f.write(content)
    f.close()
    return Path(f.name)


class TestContentHash8(unittest.TestCase):
    def test_deterministic(self):
        path = write_tmp(SAMPLE_WITHOUT_HASH)
        try:
            h1 = ch.content_hash8(path)
            h2 = ch.content_hash8(path)
            self.assertEqual(h1, h2)
            self.assertEqual(len(h1), 8)
            int(h1, 16)  # raises if not hex
        finally:
            path.unlink()

    def test_content_hash_field_is_self_excluded(self):
        """A file with its own content_hash line hashes the same as the
        same file without that line (the field is a fixed point)."""
        without = write_tmp(SAMPLE_WITHOUT_HASH)
        with_hash = write_tmp(SAMPLE_WITH_HASH)
        try:
            self.assertEqual(
                ch.content_hash8(without), ch.content_hash8(with_hash)
            )
        finally:
            without.unlink()
            with_hash.unlink()

    def test_crlf_and_lf_hash_identically(self):
        lf = write_tmp(SAMPLE_WITHOUT_HASH)
        crlf = write_tmp(SAMPLE_WITHOUT_HASH.replace("\n", "\r\n"))
        try:
            self.assertEqual(ch.content_hash8(lf), ch.content_hash8(crlf))
        finally:
            lf.unlink()
            crlf.unlink()

    def test_content_change_changes_hash(self):
        path_a = write_tmp(SAMPLE_WITHOUT_HASH)
        path_b = write_tmp(SAMPLE_WITHOUT_HASH + "  domain_additions_count: 1\n")
        try:
            self.assertNotEqual(ch.content_hash8(path_a), ch.content_hash8(path_b))
        finally:
            path_a.unlink()
            path_b.unlink()


class TestMain(unittest.TestCase):
    def test_main_prints_hash(self):
        import contextlib
        import io

        path = write_tmp(SAMPLE_WITHOUT_HASH)
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = ch.main([str(path)])
            self.assertEqual(rc, 0)
            self.assertEqual(buf.getvalue().strip(), ch.content_hash8(path))
        finally:
            path.unlink()

    def test_main_requires_one_arg(self):
        self.assertEqual(ch.main([]), 2)
        self.assertEqual(ch.main(["a", "b"]), 2)


if __name__ == "__main__":
    unittest.main()
