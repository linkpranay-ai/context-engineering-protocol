"""Regression suite for wizard_containment.py (D24 §18.2b, locked). Stdlib unittest
only. Run with:

    python -m unittest discover -s scripts/tests -v

Platform note: the symlink/junction tests that need a *real* reparse point on disk are
skipped when the current process can't create one (e.g. Windows without Developer Mode
or admin rights) rather than failing - CI's windows-latest leg (build-order step 3 /
risk R1) is expected to actually exercise them; a local run without that privilege
still exercises every platform-independent path (containment math, case-fold/UNC-
prefix normalization). The OneDrive-cloud-placeholder distinction is tested via a
mocked reparse tag rather than live sync state - R3: not fully CI-automatable as a real
filesystem condition; full end-to-end validation needs one manual run on a real
OneDrive-synced machine, documented in wizard-security-model.md.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wizard_containment as wc  # noqa: E402


def _try_make_symlink(link_path: Path, target: Path) -> bool:
    """Best-effort real symlink creation. Returns False (caller should skip) rather
    than raising when the process lacks the privilege to create one."""
    try:
        link_path.symlink_to(target, target_is_directory=target.is_dir())
        return True
    except OSError:
        return False


class TestContainmentBasics(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "sub").mkdir()
        (self.root / "sub" / "file.txt").write_text("x", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_direct_child_is_contained(self):
        result = wc.check_containment(self.root, "sub")
        self.assertTrue(str(result).endswith("sub"))

    def test_nested_file_is_contained(self):
        wc.check_containment(self.root, "sub/file.txt")  # must not raise

    def test_root_itself_is_contained(self):
        wc.check_containment(self.root, ".")

    def test_dotdot_escape_is_rejected(self):
        with self.assertRaises(wc.ContainmentError):
            wc.check_containment(self.root, "../escaped")

    def test_sibling_absolute_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as other:
            with self.assertRaises(wc.ContainmentError):
                wc.check_containment(self.root, Path(other) / "x")

    def test_is_contained_is_a_non_raising_wrapper(self):
        self.assertTrue(wc.is_contained(self.root, "sub"))
        self.assertFalse(wc.is_contained(self.root, "../escaped"))


class TestSymlinkContainment(unittest.TestCase):
    """Exercises a *real* symlink on disk - skipped where the process can't create
    one (see module docstring)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.outside = Path(tempfile.mkdtemp())
        (self.outside / "secret.txt").write_text("outside", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()
        shutil.rmtree(self.outside, ignore_errors=True)

    def test_symlinked_component_pointing_outside_root_is_rejected(self):
        link = self.root / "escape_link"
        if not _try_make_symlink(link, self.outside):
            self.skipTest("process cannot create symlinks (no Developer Mode/admin)")
        with self.assertRaises(wc.ContainmentError):
            wc.check_containment(self.root, "escape_link/secret.txt")

    def test_symlinked_component_pointing_inside_root_is_still_rejected(self):
        """A symlink is a containment violation even when it happens to resolve to
        somewhere still under root - link-based indirection is rejected on its own
        terms, not just as an outside-root-escape proxy (see module docstring)."""
        real_dir = self.root / "real"
        real_dir.mkdir()
        (real_dir / "f.txt").write_text("x", encoding="utf-8")
        link = self.root / "link_to_real"
        if not _try_make_symlink(link, real_dir):
            self.skipTest("process cannot create symlinks (no Developer Mode/admin)")
        with self.assertRaises(wc.ContainmentError):
            wc.check_containment(self.root, "link_to_real/f.txt")


class TestReparseTagLogic(unittest.TestCase):
    """Platform-independent: the cloud-placeholder-tag mask math itself, tested
    directly against the real winnt.h constant values - no live filesystem reparse
    point involved."""

    def test_base_cloud_tag_is_recognized(self):
        self.assertTrue(wc._is_cloud_placeholder_tag(0x9000001A))

    def test_cloud_provider_family_variants_are_recognized(self):
        # IO_REPARSE_TAG_CLOUD_1 .. _F: same base tag, family nibble 0x1000-0xF000.
        for nibble in range(1, 0x10):
            tag = 0x9000001A | (nibble << 12)
            with self.subTest(tag=hex(tag)):
                self.assertTrue(wc._is_cloud_placeholder_tag(tag))

    def test_symlink_tag_is_not_a_cloud_placeholder(self):
        self.assertFalse(wc._is_cloud_placeholder_tag(wc.IO_REPARSE_TAG_SYMLINK))

    def test_mount_point_tag_is_not_a_cloud_placeholder(self):
        self.assertFalse(wc._is_cloud_placeholder_tag(wc.IO_REPARSE_TAG_MOUNT_POINT))

    def test_unrecognized_tag_is_not_a_cloud_placeholder(self):
        """Fail-closed: an arbitrary/unknown reparse tag is not treated as safe just
        because it isn't specifically SYMLINK or MOUNT_POINT."""
        self.assertFalse(wc._is_cloud_placeholder_tag(0xDEADBEEF))


class TestComponentIsContainmentViolationMocked(unittest.TestCase):
    """Mocks os.stat + sys.platform to deterministically exercise the Windows
    reparse-tag branch on any CI OS (R3 - see module docstring)."""

    def _fake_stat(self, attrs, reparse_tag=None):
        result = mock.Mock()
        result.st_file_attributes = attrs
        if reparse_tag is not None:
            result.st_reparse_tag = reparse_tag
        return result

    def test_ordinary_file_no_reparse_attribute_is_not_a_violation(self):
        with mock.patch.object(wc.sys, "platform", "win32"), mock.patch.object(
            wc.os, "stat", return_value=self._fake_stat(0)
        ):
            self.assertFalse(wc.component_is_containment_violation(Path("C:/x")))

    def test_symlink_reparse_point_is_a_violation(self):
        fake = self._fake_stat(wc.FILE_ATTRIBUTE_REPARSE_POINT, wc.IO_REPARSE_TAG_SYMLINK)
        with mock.patch.object(wc.sys, "platform", "win32"), mock.patch.object(
            wc.os, "stat", return_value=fake
        ):
            self.assertTrue(wc.component_is_containment_violation(Path("C:/x")))

    def test_mount_point_reparse_point_is_a_violation(self):
        fake = self._fake_stat(
            wc.FILE_ATTRIBUTE_REPARSE_POINT, wc.IO_REPARSE_TAG_MOUNT_POINT
        )
        with mock.patch.object(wc.sys, "platform", "win32"), mock.patch.object(
            wc.os, "stat", return_value=fake
        ):
            self.assertTrue(wc.component_is_containment_violation(Path("C:/x")))

    def test_cloud_placeholder_reparse_point_is_not_a_violation(self):
        """The critical OneDrive Files-On-Demand case: a cloud placeholder must NOT be
        rejected."""
        fake = self._fake_stat(wc.FILE_ATTRIBUTE_REPARSE_POINT, 0x9000001A)
        with mock.patch.object(wc.sys, "platform", "win32"), mock.patch.object(
            wc.os, "stat", return_value=fake
        ):
            self.assertFalse(wc.component_is_containment_violation(Path("C:/x")))

    def test_unrecognized_reparse_point_is_conservatively_a_violation(self):
        fake = self._fake_stat(wc.FILE_ATTRIBUTE_REPARSE_POINT, 0x12345678)
        with mock.patch.object(wc.sys, "platform", "win32"), mock.patch.object(
            wc.os, "stat", return_value=fake
        ):
            self.assertTrue(wc.component_is_containment_violation(Path("C:/x")))

    def test_stat_oserror_is_not_a_violation(self):
        """A nonexistent path component (e.g. checking ahead of a future write) can't
        be a symlink - not an error, not a violation."""
        with mock.patch.object(wc.sys, "platform", "win32"), mock.patch.object(
            wc.os, "stat", side_effect=OSError("nope")
        ):
            self.assertFalse(wc.component_is_containment_violation(Path("C:/x")))


class TestResolveExternalTarget(unittest.TestCase):
    """ISSUES.md Round 2 finding 7 (2026-08-31) - "Retrofit wizard cannot
    operate on sibling or standalone skill library". resolve_external_target
    is the validation gate for a user-supplied external retrofit-target root;
    every requirement in its docstring gets its own failure-mode test here."""

    def setUp(self):
        self._repo_tmp = tempfile.TemporaryDirectory()
        self.repo_root = Path(self._repo_tmp.name)
        (self.repo_root / "sub").mkdir()

        self._ext_tmp = tempfile.TemporaryDirectory()
        self.external_root = Path(self._ext_tmp.name)
        (self.external_root / "skills").mkdir()

    def tearDown(self):
        self._repo_tmp.cleanup()
        self._ext_tmp.cleanup()

    def test_valid_external_root_resolves(self):
        resolved = wc.resolve_external_target(self.repo_root, self.external_root)
        self.assertEqual(resolved, self.external_root.resolve())

    def test_blank_candidate_is_rejected(self):
        with self.assertRaises(wc.ContainmentError):
            wc.resolve_external_target(self.repo_root, "")

    def test_none_candidate_is_rejected(self):
        with self.assertRaises(wc.ContainmentError):
            wc.resolve_external_target(self.repo_root, None)

    def test_relative_candidate_is_rejected(self):
        with self.assertRaises(wc.ContainmentError):
            wc.resolve_external_target(self.repo_root, "some/relative/path")

    def test_candidate_already_inside_repo_root_is_rejected(self):
        """This is just an ordinary in-repo target - callers should route it
        through the existing picker, not the external-target flow."""
        with self.assertRaises(wc.ContainmentError):
            wc.resolve_external_target(self.repo_root, self.repo_root / "sub")

    def test_nonexistent_candidate_is_rejected(self):
        with self.assertRaises(wc.ContainmentError):
            wc.resolve_external_target(self.repo_root, self.external_root / "does-not-exist")

    def test_candidate_that_is_a_file_not_a_directory_is_rejected(self):
        a_file = self.external_root / "not-a-dir.txt"
        a_file.write_text("x", encoding="utf-8")
        with self.assertRaises(wc.ContainmentError):
            wc.resolve_external_target(self.repo_root, a_file)

    def test_symlinked_external_root_is_rejected(self):
        link = self.external_root.parent / "link_to_external_root"
        if not _try_make_symlink(link, self.external_root):
            self.skipTest("process cannot create symlinks (no Developer Mode/admin)")
        try:
            with self.assertRaises(wc.ContainmentError):
                wc.resolve_external_target(self.repo_root, link)
        finally:
            link.unlink(missing_ok=True)


class TestNormalizedForComparison(unittest.TestCase):
    def test_case_fold(self):
        self.assertEqual(
            wc._normalized_for_comparison(Path("C:/Foo/BAR")),
            wc._normalized_for_comparison(Path("c:/foo/bar")),
        )

    def test_trailing_slash_ignored(self):
        self.assertEqual(
            wc._normalized_for_comparison(Path("C:/foo/")),
            wc._normalized_for_comparison(Path("C:/foo")),
        )

    def test_extended_length_prefix_stripped(self):
        self.assertEqual(wc._strip_extended_prefix("\\\\?\\C:\\foo\\bar"), "C:\\foo\\bar")

    def test_extended_length_unc_prefix_stripped(self):
        self.assertEqual(
            wc._strip_extended_prefix("\\\\?\\UNC\\server\\share\\foo"),
            "\\\\server\\share\\foo",
        )

    def test_no_prefix_passthrough(self):
        self.assertEqual(wc._strip_extended_prefix("C:\\foo"), "C:\\foo")


if __name__ == "__main__":
    unittest.main()
