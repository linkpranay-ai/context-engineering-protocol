"""Regression suite for wizard_apply.py (D24 §18.3/§18.9, locked). Stdlib
unittest only. Run with:

    python -m unittest discover -s scripts/tests -v

confirm_layers.py and layout_decision_grammar.py are copied fresh from the
real ult-repo-layout/scripts/ at test time (not hand-transcribed stubs), same
convention as test_wizard_decision_staging.py and test_wizard_layout_source.py
- so apply_confirmed is exercised against the real run_confirm/parse_artifact/
Field.resolve, not a paraphrase that could silently drift from them.

Two of these tests are the ones the plan itself calls out as needing
*behavioral*, not merely structural, proof (round-3 M10):

- test_idempotent_reapply_after_commit_is_success_not_error - the legitimate
  "every field already confirmed" no-op.
- test_unexpected_no_op_raises_when_nothing_is_written - the round-3 C2
  silent-no-op failure mode, triggered for real (a staged SKIP decision on a
  fresh repo with no context-config.yaml at all: run_confirm's own
  `if config_lines:` guard never fires because config_lines starts and stays
  empty, so it returns (0, ["Confirmed 1 field(s), wrote 0 config key(s)."])
  - exit 0, hash unchanged, no "Nothing to confirm" - exactly the shape
  apply_confirmed must not report as success), not via mocking run_confirm.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wizard_content_hash as wch  # noqa: E402
import wizard_decision_staging as wds  # noqa: E402
import wizard_apply as wa  # noqa: E402


def _find_real_repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        marker = (
            candidate
            / ".github"
            / "skills"
            / "ult-repo-layout"
            / "scripts"
            / "validate_layout.py"
        )
        if marker.exists():
            return candidate
    raise RuntimeError(
        "could not locate the context-engineering-oss repo root from this test "
        "file's location"
    )


REAL_REPO_ROOT = _find_real_repo_root()
REAL_SKILLS_DIR = REAL_REPO_ROOT / ".github" / "skills" / "ult-repo-layout"
REAL_VALIDATE_LAYOUT = REAL_SKILLS_DIR / "scripts" / "validate_layout.py"
REAL_DISCOVER_LAYERS = REAL_SKILLS_DIR / "scripts" / "discover_layers.py"
REAL_LAYOUT_DECISION_GRAMMAR = REAL_SKILLS_DIR / "scripts" / "layout_decision_grammar.py"
REAL_CONFIRM_LAYERS = REAL_SKILLS_DIR / "scripts" / "confirm_layers.py"


def _install_ult_repo_layout(repo_root: Path) -> None:
    scripts_dir = repo_root / ".github" / "skills" / "ult-repo-layout" / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    for name, src in (
        ("validate_layout.py", REAL_VALIDATE_LAYOUT),
        ("discover_layers.py", REAL_DISCOVER_LAYERS),
        ("layout_decision_grammar.py", REAL_LAYOUT_DECISION_GRAMMAR),
        ("confirm_layers.py", REAL_CONFIRM_LAYERS),
    ):
        shutil.copy(src, scripts_dir / name)


WHAT_L2_TITLE = "What-L2 - project's own requirements/spec docs"
HOW_L2_TITLE = "How-L2 - this project's own compiled conventions"
WHAT_L1_TITLE = "What-L1 - external reference material (standards/specs this project didn't author)"
COLLISION_TITLE = "Cross-layer path collisions (S30)"

# Mirrors test_wizard_decision_staging.py's SINGLE_CANDIDATE_ARTIFACT - kept
# as its own copy (not imported from that test module) so this file stays
# independently runnable, same convention the production modules themselves
# follow.
FULL_ARTIFACT = f"""# Context Layout Discovery - test-repo

## {WHAT_L2_TITLE}
**Status:** enabled by default.

    decision: PENDING   # CONFIRM: docs/reqs/ | CUSTOM: <path> | SKIP

## {HOW_L2_TITLE}
**Status:** enabled by default.

    decision: PENDING   # CONFIRM: org/ | CUSTOM: <path> | SKIP

## {WHAT_L1_TITLE}
**Status:** disabled by default (what_l1.enabled: false).

    decision: PENDING   # CUSTOM: <path> | ACKNOWLEDGE

## {COLLISION_TITLE}
**Status:** checked pairwise for equality or nesting.

    collision_decision: PENDING   # ACKNOWLEDGE | CUSTOM: <layer> -> <new path>
"""

# Only one decision line, offering SKIP - used for the genuine
# UnexpectedNoOpError trigger (a fresh repo with no context-config.yaml at
# all, where a staged SKIP writes nothing).
SKIP_ONLY_ARTIFACT = f"""# Context Layout Discovery - test-repo

## {HOW_L2_TITLE}
**Status:** enabled by default.

    decision: PENDING   # CONFIRM: org/ | CUSTOM: <path> | SKIP
"""

# Two decision lines in the same section, both already staged CONFIRM by
# hand - stage_decision itself refuses to create this shape (its own
# stage-time primary-choice check), so this simulates a hand-edited artifact
# to reach confirm_layers._check_single_primary_choice's refusal through
# apply_confirmed instead.
DOUBLE_PRIMARY_ARTIFACT = f"""# Context Layout Discovery - test-repo

## {WHAT_L2_TITLE}
**Status:** enabled by default.

    decision: CONFIRM: docs/a/   # CONFIRM: docs/a/ | SKIP

    decision: CONFIRM: docs/b/   # CONFIRM: docs/b/ | SKIP
"""


def _write_artifact(root: Path, content: str) -> Path:
    path = root / "context-layout-discovery.md"
    path.write_text(content, encoding="utf-8")
    return path


class TestApplyConfirmedRefusals(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _install_ult_repo_layout(self.root)
        self.artifact_path = _write_artifact(self.root, FULL_ARTIFACT)

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_artifact_raises_validation_error(self):
        missing = self.root / "context-layout-discovery.md"
        missing.unlink()
        with self.assertRaises(wa.ValidationError):
            wa.apply_confirmed(self.root, missing, None)

    def test_still_pending_field_raises_validation_error(self):
        loaded_hash = wch.hash_artifact(self.artifact_path)
        with self.assertRaises(wa.ValidationError):
            wa.apply_confirmed(self.root, self.artifact_path, loaded_hash)
        self.assertFalse((self.root / "context-config.yaml").exists())

    def test_stale_artifact_hash_raises_stale_artifact_error(self):
        loaded_hash = wch.hash_artifact(self.artifact_path)
        # Simulate a concurrent edit landing between the caller's load and
        # its Apply call - e.g. another discover re-run's drift tracking, or
        # another browser tab staging something.
        self.artifact_path.write_text(
            self.artifact_path.read_text(encoding="utf-8") + "\n<!-- edited concurrently -->\n",
            encoding="utf-8",
        )
        with self.assertRaises(wa.StaleArtifactError):
            wa.apply_confirmed(self.root, self.artifact_path, loaded_hash)
        self.assertFalse((self.root / "context-config.yaml").exists())

    def test_double_primary_choice_raises_validation_error(self):
        double_path = _write_artifact(self.root, DOUBLE_PRIMARY_ARTIFACT)
        loaded_hash = wch.hash_artifact(double_path)
        with self.assertRaises(wa.ValidationError) as ctx:
            wa.apply_confirmed(self.root, double_path, loaded_hash)
        self.assertIn("primary path", str(ctx.exception))
        self.assertFalse((self.root / "context-config.yaml").exists())


class TestApplyConfirmedSuccess(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _install_ult_repo_layout(self.root)
        self.artifact_path = _write_artifact(self.root, FULL_ARTIFACT)

        wds.stage_decision(self.root, self.artifact_path, WHAT_L2_TITLE, "decision", "CONFIRM")
        wds.stage_decision(self.root, self.artifact_path, HOW_L2_TITLE, "decision", "SKIP")
        wds.stage_decision(self.root, self.artifact_path, WHAT_L1_TITLE, "decision", "ACKNOWLEDGE")
        wds.stage_decision(
            self.root, self.artifact_path, COLLISION_TITLE, "collision_decision", "ACKNOWLEDGE"
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_successful_apply_writes_config_and_stamps_artifact(self):
        loaded_hash = wch.hash_artifact(self.artifact_path)
        result = wa.apply_confirmed(self.root, self.artifact_path, loaded_hash)

        self.assertTrue(result.config_changed)
        self.assertFalse(result.idempotent)

        config_text = (self.root / "context-config.yaml").read_text(encoding="utf-8")
        self.assertIn("docs/reqs/", config_text)

        artifact_after = self.artifact_path.read_text(encoding="utf-8")
        self.assertNotIn("PENDING", artifact_after)
        self.assertIn("CONFIRMED", artifact_after)

        self.assertEqual(result.config_hash_after, wch.hash_config(self.root))
        self.assertEqual(result.artifact_hash_after, wch.hash_artifact(self.artifact_path))

    def test_idempotent_reapply_after_commit_is_success_not_error(self):
        first_hash = wch.hash_artifact(self.artifact_path)
        first = wa.apply_confirmed(self.root, self.artifact_path, first_hash)
        self.assertTrue(first.config_changed)

        second = wa.apply_confirmed(self.root, self.artifact_path, first.artifact_hash_after)
        self.assertFalse(second.config_changed)
        self.assertTrue(second.idempotent)
        self.assertTrue(any(m.startswith("Nothing to confirm") for m in second.messages))
        # No further write happened - config content is byte-identical.
        self.assertEqual(second.config_hash_after, first.config_hash_after)


class TestApplyConfirmedUnexpectedNoOp(unittest.TestCase):
    """The round-3 C2 silent-no-op failure mode, triggered for real rather
    than mocked: a fresh repo with no context-config.yaml at all, and a
    single decision staged SKIP. confirm_layers.apply_field returns False
    for SKIP (nothing to write), and run_confirm's own
    `if config_lines: config_path.write_text(...)` guard never fires because
    config_lines started and stayed an empty list - so the file is never
    created, the config hash stays None -> None (unchanged), and the
    returned message ("Confirmed 1 field(s), wrote 0 config key(s).") does
    not start with "Nothing to confirm". This is exactly the shape
    apply_confirmed must refuse to report as success."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _install_ult_repo_layout(self.root)
        self.artifact_path = _write_artifact(self.root, SKIP_ONLY_ARTIFACT)
        wds.stage_decision(self.root, self.artifact_path, HOW_L2_TITLE, "decision", "SKIP")

    def tearDown(self):
        self._tmp.cleanup()

    def test_unexpected_no_op_raises_when_nothing_is_written(self):
        self.assertFalse((self.root / "context-config.yaml").exists())
        loaded_hash = wch.hash_artifact(self.artifact_path)
        with self.assertRaises(wa.UnexpectedNoOpError):
            wa.apply_confirmed(self.root, self.artifact_path, loaded_hash)
        # Still no config file, and run_confirm's own artifact rewrite (the
        # CONFIRMED stamp) did happen - that part is not gated on anything
        # being written to config_lines, so it is not itself proof of a
        # commit; apply_confirmed's refusal is keyed on the config hash only.
        self.assertFalse((self.root / "context-config.yaml").exists())


if __name__ == "__main__":
    unittest.main()
