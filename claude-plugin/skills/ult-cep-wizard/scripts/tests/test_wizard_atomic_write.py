"""Regression suite for wizard_atomic_write.py (D24 §18.2b, locked). Stdlib
unittest only. Run with:

    python -m unittest discover -s scripts/tests -v
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wizard_atomic_write as waw  # noqa: E402


class TestWriteTextAtomic(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_writes_new_file(self):
        target = self.root / "new.md"
        waw.write_text_atomic(target, "hello\n")
        self.assertEqual(target.read_text(encoding="utf-8"), "hello\n")

    def test_overwrites_existing_file_completely(self):
        target = self.root / "existing.md"
        target.write_text("old content that is longer than the new one\n", encoding="utf-8")
        waw.write_text_atomic(target, "new\n")
        self.assertEqual(target.read_text(encoding="utf-8"), "new\n")

    def test_no_leftover_temp_file_after_success(self):
        target = self.root / "clean.md"
        waw.write_text_atomic(target, "content\n")
        leftovers = [p for p in self.root.iterdir() if p != target]
        self.assertEqual(leftovers, [])

    def test_missing_parent_directory_raises_and_writes_nothing(self):
        target = self.root / "does-not-exist" / "file.md"
        with self.assertRaises(waw.AtomicWriteError):
            waw.write_text_atomic(target, "content\n")
        self.assertFalse(target.exists())

    def test_failure_during_replace_leaves_target_untouched_and_cleans_up_temp(self):
        target = self.root / "protected.md"
        target.write_text("original\n", encoding="utf-8")

        with mock.patch("os.replace", side_effect=OSError("simulated failure")):
            with self.assertRaises(waw.AtomicWriteError):
                waw.write_text_atomic(target, "attempted overwrite\n")

        self.assertEqual(target.read_text(encoding="utf-8"), "original\n")
        leftovers = [p for p in self.root.iterdir() if p != target]
        self.assertEqual(leftovers, [])

    def test_unicode_content_round_trips(self):
        target = self.root / "unicode.md"
        content = "café — 日本語\n"
        waw.write_text_atomic(target, content)
        self.assertEqual(target.read_text(encoding="utf-8"), content)

    def test_transient_windows_permission_error_on_replace_is_retried(self):
        # Real-world failure this reproduces: a fresh Windows-only
        # atomic-write failure observed during a product-focused rerun -
        # repeatedly replacing the same context-layout-discovery.md target
        # in quick succession (wizard_decision_staging.stage_decision,
        # called once per staged decision) occasionally hit
        # PermissionError (WinError 5) on os.replace, almost certainly
        # AV/indexer holding a momentary handle on the file just written.
        # A single transient PermissionError must not fail the whole write.
        target = self.root / "flaky.md"
        real_replace = os.replace
        calls = {"n": 0}

        def flaky_replace(src, dst):
            calls["n"] += 1
            if calls["n"] == 1:
                raise PermissionError(5, "Access is denied")
            return real_replace(src, dst)

        with mock.patch("os.replace", side_effect=flaky_replace):
            waw.write_text_atomic(target, "content\n")

        self.assertEqual(target.read_text(encoding="utf-8"), "content\n")
        self.assertEqual(calls["n"], 2)
        leftovers = [p for p in self.root.iterdir() if p != target]
        self.assertEqual(leftovers, [])

    def test_persistent_permission_error_on_replace_still_fails_closed(self):
        # The retry above must not mask a *real* lock: if PermissionError
        # never clears, write_text_atomic must still raise AtomicWriteError,
        # leave the target's original content untouched, and clean up the
        # temp file - same contract as any other replace failure.
        target = self.root / "locked.md"
        target.write_text("original\n", encoding="utf-8")

        with mock.patch(
            "os.replace", side_effect=PermissionError(5, "Access is denied")
        ), mock.patch("time.sleep"):
            with self.assertRaises(waw.AtomicWriteError):
                waw.write_text_atomic(target, "attempted overwrite\n")

        self.assertEqual(target.read_text(encoding="utf-8"), "original\n")
        leftovers = [p for p in self.root.iterdir() if p != target]
        self.assertEqual(leftovers, [])

    def test_replace_with_retry_misconfigured_to_zero_attempts_raises_assertion_not_typeerror(self):
        # Defensive guard: if _REPLACE_RETRY_ATTEMPTS were ever misconfigured
        # to 0, the retry loop body never runs, so last_exc stays None --
        # `raise None` would be a confusing TypeError masking the real
        # misconfiguration. Must fail loudly and specifically instead.
        target = self.root / "misconfigured.md"
        with mock.patch.object(waw, "_REPLACE_RETRY_ATTEMPTS", 0):
            with self.assertRaises(AssertionError):
                waw._replace_with_retry(self.root / "src.tmp", target)


if __name__ == "__main__":
    unittest.main()
