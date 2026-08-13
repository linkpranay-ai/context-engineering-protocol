"""Regression suite for wizard_decision_staging.py (D24 §18.3, locked). Stdlib
unittest only. Run with:

    python -m unittest discover -s scripts/tests -v

confirm_layers.py and layout_decision_grammar.py are copied fresh from the
real ult-repo-layout/scripts/ at test time (not hand-transcribed stubs), same
convention as test_wizard_layout_source.py - so stage_decision is exercised
against the real parse_artifact/CONFIRMED_STAMP_RE/parse_comment_clauses, not
a paraphrase that could silently drift from them.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wizard_containment as wc  # noqa: E402
import wizard_decision_staging as wds  # noqa: E402


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
    # stage_decision only ever needs confirm_layers.py (which itself imports
    # layout_decision_grammar.py and validate_layout.py) - discover_layers.py
    # is not on the import path this module exercises, but is copied too so
    # this fixture is a faithful "ult-repo-layout is installed" shape, same
    # as every other fixture in this test package.
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

SINGLE_CANDIDATE_ARTIFACT = f"""# Context Layout Discovery - test-repo

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

MULTI_CANDIDATE_ARTIFACT = f"""# Context Layout Discovery - test-repo

## {WHAT_L2_TITLE}
**Status:** enabled by default.

    decision: PENDING   # CONFIRM: docs/a/ | SKIP

    decision: PENDING   # CONFIRM: docs/b/ | SKIP

    include_roots_decision: PENDING   # ADD: vendor/spec-a/ | SKIP

    include_roots_decision: PENDING   # ADD: vendor/spec-b/ | SKIP
"""


def _write_artifact(root: Path, content: str) -> Path:
    path = root / "context-layout-discovery.md"
    path.write_text(content, encoding="utf-8")
    return path


class TestValidateCustomArg(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "docs" / "specs").mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def test_accepts_a_plain_repo_relative_path(self):
        self.assertEqual(wds.validate_custom_arg(self.root, "docs/specs/"), "docs/specs/")

    def test_rejects_empty(self):
        with self.assertRaises(wds.DecisionStagingError):
            wds.validate_custom_arg(self.root, "   ")

    def test_rejects_hash(self):
        with self.assertRaises(wds.DecisionStagingError):
            wds.validate_custom_arg(self.root, "docs/spec#s/")

    def test_rejects_backslash(self):
        with self.assertRaises(wds.DecisionStagingError):
            wds.validate_custom_arg(self.root, "docs\\specs\\")

    def test_rejects_absolute_path(self):
        with self.assertRaises(wds.DecisionStagingError):
            wds.validate_custom_arg(self.root, "/etc/passwd")

    def test_rejects_drive_letter(self):
        with self.assertRaises(wds.DecisionStagingError):
            wds.validate_custom_arg(self.root, "C:/Windows")

    def test_rejects_parent_traversal(self):
        with self.assertRaises(wds.DecisionStagingError):
            wds.validate_custom_arg(self.root, "../outside/")

    def test_rejects_double_slash(self):
        with self.assertRaises(wds.DecisionStagingError):
            wds.validate_custom_arg(self.root, "docs//specs/")

    def test_rejects_path_outside_root_via_containment(self):
        sibling = self.root.parent / "sibling_dir"
        sibling.mkdir(exist_ok=True)
        try:
            with self.assertRaises(wds.DecisionStagingError):
                wds.validate_custom_arg(self.root, f"../{sibling.name}/")
        finally:
            shutil.rmtree(sibling, ignore_errors=True)


class TestFormatDecisionLine(unittest.TestCase):
    def test_renders_verb_only(self):
        line = wds.format_decision_line("    ", "decision", "SKIP", None, "CONFIRM: docs/ | SKIP")
        self.assertEqual(line, "    decision: SKIP   # CONFIRM: docs/ | SKIP")

    def test_renders_verb_with_arg(self):
        line = wds.format_decision_line("    ", "decision", "CUSTOM", "docs/specs/", "CUSTOM: <path> | SKIP")
        self.assertEqual(line, "    decision: CUSTOM: docs/specs/   # CUSTOM: <path> | SKIP")


class TestStageDecisionSingleCandidate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _install_ult_repo_layout(self.root)
        (self.root / "docs" / "specs").mkdir(parents=True)
        self.artifact_path = _write_artifact(self.root, SINGLE_CANDIDATE_ARTIFACT)

    def tearDown(self):
        self._tmp.cleanup()

    def _reread(self):
        return self.artifact_path.read_text(encoding="utf-8")

    def test_stage_confirm_with_default_arg(self):
        wds.stage_decision(self.root, self.artifact_path, WHAT_L2_TITLE, "decision", "CONFIRM")
        text = self._reread()
        self.assertIn("decision: CONFIRM: docs/reqs/   # CONFIRM: docs/reqs/ | CUSTOM: <path> | SKIP", text)

    def test_stage_custom_with_valid_path(self):
        wds.stage_decision(
            self.root, self.artifact_path, WHAT_L2_TITLE, "decision", "CUSTOM", arg="docs/specs/"
        )
        text = self._reread()
        self.assertIn("decision: CUSTOM: docs/specs/   # CONFIRM: docs/reqs/ | CUSTOM: <path> | SKIP", text)

    def test_stage_custom_with_invalid_path_refuses_and_does_not_write(self):
        before = self._reread()
        with self.assertRaises(wds.DecisionStagingError):
            wds.stage_decision(
                self.root, self.artifact_path, WHAT_L2_TITLE, "decision", "CUSTOM", arg="../escape/"
            )
        self.assertEqual(self._reread(), before)

    def test_stage_skip(self):
        wds.stage_decision(self.root, self.artifact_path, HOW_L2_TITLE, "decision", "SKIP")
        text = self._reread()
        self.assertIn("decision: SKIP   # CONFIRM: org/ | CUSTOM: <path> | SKIP", text)

    def test_verb_not_offered_refuses(self):
        with self.assertRaises(wds.DecisionStagingError):
            wds.stage_decision(self.root, self.artifact_path, HOW_L2_TITLE, "decision", "DISABLE")

    def test_re_staging_an_already_staged_line_refuses(self):
        wds.stage_decision(self.root, self.artifact_path, HOW_L2_TITLE, "decision", "SKIP")
        with self.assertRaises(wds.DecisionStagingError):
            wds.stage_decision(self.root, self.artifact_path, HOW_L2_TITLE, "decision", "CONFIRM")

    def test_missing_field_key_in_section_refuses(self):
        with self.assertRaises(wds.DecisionStagingError):
            wds.stage_decision(self.root, self.artifact_path, HOW_L2_TITLE, "enable", "true")

    def test_collision_custom_splits_and_validates_new_path_only(self):
        wds.stage_decision(
            self.root, self.artifact_path, COLLISION_TITLE, "collision_decision", "CUSTOM",
            arg="layers.what_l2.include_roots[0] -> vendor/moved-spec/",
        )
        text = self._reread()
        self.assertIn(
            "collision_decision: CUSTOM: layers.what_l2.include_roots[0] -> vendor/moved-spec/"
            "   # ACKNOWLEDGE | CUSTOM: <layer> -> <new path>",
            text,
        )

    def test_collision_custom_rejects_bad_new_path(self):
        with self.assertRaises(wds.DecisionStagingError):
            wds.stage_decision(
                self.root, self.artifact_path, COLLISION_TITLE, "collision_decision", "CUSTOM",
                arg="layers.what_l2.include_roots[0] -> ../escape/",
            )

    def test_collision_custom_without_arrow_refuses(self):
        with self.assertRaises(wds.DecisionStagingError):
            wds.stage_decision(
                self.root, self.artifact_path, COLLISION_TITLE, "collision_decision", "CUSTOM",
                arg="vendor/moved-spec/",
            )

    def test_write_is_atomic_no_partial_file_on_failure(self):
        # A verb that is offered but whose CUSTOM arg is invalid must leave
        # the artifact byte-for-byte untouched - write_text_atomic is only
        # ever reached after every validation has already passed.
        before = self.artifact_path.stat().st_mtime_ns
        with self.assertRaises(wds.DecisionStagingError):
            wds.stage_decision(
                self.root, self.artifact_path, WHAT_L1_TITLE, "decision", "CUSTOM", arg="C:/nope"
            )
        self.assertEqual(self.artifact_path.stat().st_mtime_ns, before)


class TestStageDecisionMultiCandidate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _install_ult_repo_layout(self.root)
        self.artifact_path = _write_artifact(self.root, MULTI_CANDIDATE_ARTIFACT)

    def tearDown(self):
        self._tmp.cleanup()

    def _reread(self):
        return self.artifact_path.read_text(encoding="utf-8")

    def _confirm_layers(self):
        """Same module wizard_decision_staging.py itself imports (added to
        sys.path once here, then cached by Python's own import machinery) -
        used only so these tests can locate a field's exact line_no the same
        way a real caller (e.g. a future /api/decisions handler) would."""
        scripts_dir = str(self.root / ".github" / "skills" / "ult-repo-layout" / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import importlib
        return importlib.import_module("confirm_layers")

    def test_ambiguous_without_line_no_refuses(self):
        with self.assertRaises(wds.DecisionStagingError) as ctx:
            wds.stage_decision(self.root, self.artifact_path, WHAT_L2_TITLE, "decision", "CONFIRM")
        self.assertIn("line_no", str(ctx.exception))

    def test_line_no_disambiguates(self):
        # Locate the second "decision:" line's 0-based index the same way a
        # caller would: parse the artifact once first.
        cl = self._confirm_layers()
        _lines, fields = cl.parse_artifact(self._reread())
        decision_fields = [f for f in fields if f.section_title == WHAT_L2_TITLE and f.key == "decision"]
        self.assertEqual(len(decision_fields), 2)
        second = decision_fields[1]

        wds.stage_decision(
            self.root, self.artifact_path, WHAT_L2_TITLE, "decision", "CONFIRM",
            line_no=second.line_no,
        )
        text = self._reread()
        self.assertIn("decision: CONFIRM: docs/b/   # CONFIRM: docs/b/ | SKIP", text)
        # The other candidate line must be untouched.
        self.assertIn("decision: PENDING   # CONFIRM: docs/a/ | SKIP", text)

    def test_staging_a_second_primary_choice_in_same_section_refuses(self):
        cl = self._confirm_layers()
        _lines, fields = cl.parse_artifact(self._reread())
        decision_fields = [f for f in fields if f.section_title == WHAT_L2_TITLE and f.key == "decision"]
        first, second = decision_fields[0], decision_fields[1]

        wds.stage_decision(
            self.root, self.artifact_path, WHAT_L2_TITLE, "decision", "CONFIRM", line_no=first.line_no
        )
        with self.assertRaises(wds.DecisionStagingError):
            wds.stage_decision(
                self.root, self.artifact_path, WHAT_L2_TITLE, "decision", "CONFIRM", line_no=second.line_no
            )

    def test_skipping_the_other_candidate_after_a_primary_choice_is_allowed(self):
        cl = self._confirm_layers()
        _lines, fields = cl.parse_artifact(self._reread())
        decision_fields = [f for f in fields if f.section_title == WHAT_L2_TITLE and f.key == "decision"]
        first, second = decision_fields[0], decision_fields[1]

        wds.stage_decision(
            self.root, self.artifact_path, WHAT_L2_TITLE, "decision", "CONFIRM", line_no=first.line_no
        )
        # Must not raise - SKIP is never a primary choice.
        wds.stage_decision(
            self.root, self.artifact_path, WHAT_L2_TITLE, "decision", "SKIP", line_no=second.line_no
        )

    def test_include_roots_decision_line_no_disambiguates_independently(self):
        cl = self._confirm_layers()
        _lines, fields = cl.parse_artifact(self._reread())
        add_fields = [
            f for f in fields
            if f.section_title == WHAT_L2_TITLE and f.key == "include_roots_decision"
        ]
        self.assertEqual(len(add_fields), 2)

        wds.stage_decision(
            self.root, self.artifact_path, WHAT_L2_TITLE, "include_roots_decision", "ADD",
            line_no=add_fields[0].line_no,
        )
        text = self._reread()
        self.assertIn("include_roots_decision: ADD: vendor/spec-a/   # ADD: vendor/spec-a/ | SKIP", text)
        self.assertIn("include_roots_decision: PENDING   # ADD: vendor/spec-b/ | SKIP", text)


if __name__ == "__main__":
    unittest.main()
