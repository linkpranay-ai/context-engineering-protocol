"""Self-verifying check for the golden fixtures under
evals/fixtures/autoscaffold-content/ (see that directory's README.md).

This does not re-run scan/plan/probe-size (their captured output already
lives in each fixture's expected/ directory as documentation, produced by
actually running the CLI -- see the README for the exact commands). What
this guards against is silent bit-rot of the hand-authored good/bad
CODING-STANDARDS.md docs: if a future scaffold_state.py change makes
validate() stricter or looser, this is what will fail and say so, instead
of the fixture quietly drifting out of sync with the code it's meant to
pin down.

Both fixtures are fully synthetic two-module repos (see the README) --
this file makes no assumption about any particular real-world codebase.

Run with:

    python -m unittest tests.test_golden_fixtures -v
"""

import json
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scaffold_state as ss  # noqa: E402

FIXTURES_ROOT = (
    Path(__file__).resolve().parent.parent.parent.parent.parent.parent
    / "evals" / "fixtures" / "autoscaffold-content"
)


def _load_packet(fixture_dir, packet_filename):
    path = fixture_dir / "expected" / "packets" / packet_filename
    return json.loads(path.read_text(encoding="utf-8"))


class GoldenFixtureCodingStandardsTests(unittest.TestCase):
    """Runs ss.validate() against each <lang>-repo's good/bad
    CODING-STANDARDS.md, using the real packet plan() produced for it."""

    FIXTURES = ("cpp-repo", "python-repo")

    def setUp(self):
        if not FIXTURES_ROOT.is_dir():
            self.skipTest("fixtures root not found: {}".format(FIXTURES_ROOT))

    def _validate_variant(self, lang_repo, variant):
        fixture_dir = FIXTURES_ROOT / lang_repo
        repo_root = fixture_dir / "repo"
        packet = _load_packet(fixture_dir, "how-l2--coding-standards.json")
        src = fixture_dir / variant / "CODING-STANDARDS.md"
        dst = repo_root / packet["output_path"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        try:
            return ss.validate(str(repo_root), packet["output_path"], packet)
        finally:
            dst.unlink()
            # Clean up the docs/how/repo/... tree this test created, but
            # only the empty directories it made -- never touch anything
            # that predates this test run.
            for parent in dst.parents:
                if parent == repo_root:
                    break
                try:
                    parent.rmdir()
                except OSError:
                    break

    def test_good_coding_standards_validates_for_every_fixture(self):
        for lang_repo in self.FIXTURES:
            with self.subTest(lang_repo=lang_repo):
                result = self._validate_variant(lang_repo, "good")
                self.assertTrue(
                    result["valid"],
                    "{}/good/CODING-STANDARDS.md unexpectedly failed "
                    "validation: {}".format(lang_repo, result["failures"]),
                )

    def test_bad_coding_standards_fails_for_every_fixture(self):
        for lang_repo in self.FIXTURES:
            with self.subTest(lang_repo=lang_repo):
                result = self._validate_variant(lang_repo, "bad")
                self.assertFalse(
                    result["valid"],
                    "{}/bad/CODING-STANDARDS.md unexpectedly passed "
                    "validation -- the fixture no longer demonstrates a "
                    "failure case".format(lang_repo),
                )
                # Precision check mirroring test_scaffold_state.py's
                # single-source-tool test: the bad doc must fail for the
                # reasons this fixture exists to demonstrate (missing
                # citations/sections/floor), not for some unrelated
                # accident of the fixture's construction.
                joined = " ".join(result["failures"])
                self.assertIn("must_cite path not cited", joined)
                self.assertIn("no evidenced content or gap line", joined)

    def test_bad_coding_standards_flags_the_known_tool_version_conflict(self):
        # Each fixture's tool-config set was built so exactly one tool has
        # two distinct citing sources (clang-format for cpp-repo, ruff for
        # python-repo) and one has exactly one (cpplint / yapf respectively,
        # which must NOT itself demand a conflict line). The bad doc cites
        # neither, so validate() should surface the conflict-line failure
        # for the two-source tool specifically.
        expected_conflict_tool = {"cpp-repo": "clang-format", "python-repo": "ruff"}
        for lang_repo, tool in expected_conflict_tool.items():
            with self.subTest(lang_repo=lang_repo):
                result = self._validate_variant(lang_repo, "bad")
                joined = " ".join(result["failures"])
                self.assertIn(tool, joined)
                self.assertIn("Conflicting evidence", joined)


if __name__ == "__main__":
    unittest.main()
