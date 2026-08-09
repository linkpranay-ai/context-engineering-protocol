"""Regression suite for wizard_boxes.py (D24 §18.1/§18.7, locked). Stdlib unittest
only. Run with:

    python -m unittest discover -s scripts/tests -v

Fixture-building helpers are duplicated from test_wizard_layout_source.py/
test_wizard_tripwire.py rather than imported (see those files' own module
docstrings for why) - validate_layout.py, discover_layers.py, and decision_ledger.py
are all copied fresh from the real skills at test time, so these tests exercise real
resolver/ledger logic end to end through build_boxes, not a hand-duplicated stub.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wizard_boxes as wb  # noqa: E402
import wizard_layout_source as wls  # noqa: E402


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


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _install_skill(root: Path, skill_name: str, script_names) -> None:
    real_skill_dir = REAL_REPO_ROOT / ".github" / "skills" / skill_name
    skill_dir = root / ".github" / "skills" / skill_name
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(real_skill_dir / "SKILL.md", skill_dir / "SKILL.md")
    for script_name in script_names:
        shutil.copy(real_skill_dir / "scripts" / script_name, scripts_dir / script_name)


def _make_valid_target_repo(root: Path) -> None:
    """A repo that passes validate_layout.py's own --validate, with a marker for
    context_packages only - What/How/Guidelines/Trip-wire all start uninitialized
    (default-path-only), which is the realistic "just ran ult-repo-layout init" state
    every real onboarding session starts from."""
    _install_skill(
        root,
        "ult-repo-layout",
        [
            "validate_layout.py",
            "discover_layers.py",
            # D24 Phase 1: LayoutSource now also imports these two
            # unconditionally (write-path support) alongside discover_layers.py.
            "layout_decision_grammar.py",
            "confirm_layers.py",
        ],
    )
    (root / ".github" / "skills" / "ult-context-generate").mkdir(parents=True)
    _write(
        root / "contexts" / ".layout-slots.yaml",
        "slots:\n  - slot: context_packages\n    kind: directory\n"
        "    schema_version: 1\n",
    )


class TestBuildBoxesMinimalRepo(unittest.TestCase):
    """Neither compiling-project-guidelines nor ult-institutional-memory-distill is
    installed - Guidelines and Trip-wire must both report unavailable, not raise or
    silently show empty-but-available."""

    def test_what_and_how_reflect_pre_d21_defaults_uninitialized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_valid_target_repo(root)
            source = wls.LayoutSource(root)
            view = wb.build_boxes(source)

            self.assertEqual(view.what.title, "What")
            self.assertTrue(view.what.l2_enabled)
            self.assertFalse(view.what.l1_enabled)
            self.assertEqual([p.path for p in view.what.paths], ["docs/requirements/"])
            self.assertEqual([p.source for p in view.what.paths], ["L2"])

            self.assertEqual(view.how.title, "How")
            self.assertTrue(view.how.l2_enabled)
            self.assertFalse(view.how.l1_enabled)
            self.assertEqual([p.path for p in view.how.paths], ["org/"])

    def test_guidelines_box_unavailable_when_owning_skill_not_installed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_valid_target_repo(root)
            source = wls.LayoutSource(root)
            view = wb.build_boxes(source)
            self.assertFalse(view.guidelines.available)
            self.assertIn("compiling-project-guidelines", view.guidelines.unavailable_reason)

    def test_tripwire_box_unavailable_when_owning_skill_not_installed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_valid_target_repo(root)
            source = wls.LayoutSource(root)
            view = wb.build_boxes(source)
            self.assertFalse(view.tripwire.available)


class TestBuildBoxesWithL1AndGuidelines(unittest.TestCase):
    def test_l1_enabled_layers_union_into_what_how_alongside_l2(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_valid_target_repo(root)
            _write(
                root / "context-config.yaml",
                "layers:\n  what_l1:\n    enabled: true\n    path: external/specs/\n"
                "how_dimension:\n  how_l1:\n    enabled: true\n    path: external/conventions/\n",
            )
            source = wls.LayoutSource(root)
            view = wb.build_boxes(source)

            self.assertTrue(view.what.l1_enabled)
            self.assertEqual(
                sorted((p.path, p.source) for p in view.what.paths),
                sorted(
                    [("docs/requirements/", "L2"), ("external/specs/", "L1")]
                ),
            )
            self.assertTrue(view.how.l1_enabled)
            self.assertEqual(
                sorted((p.path, p.source) for p in view.how.paths),
                sorted([("org/", "L2"), ("external/conventions/", "L1")]),
            )

    def test_guidelines_box_available_but_uninitialized_shows_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_valid_target_repo(root)
            _install_skill(root, "compiling-project-guidelines", [])
            source = wls.LayoutSource(root)
            view = wb.build_boxes(source)
            self.assertTrue(view.guidelines.available)
            self.assertFalse(view.guidelines.initialized)
            self.assertEqual(
                view.guidelines.default_path,
                "starter_kit/project_guidelines/COMPILED-GUIDELINES.md",
            )
            self.assertEqual(view.guidelines.resolved_paths, [])


class TestToJsonDict(unittest.TestCase):
    def test_view_serializes_to_json_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_valid_target_repo(root)
            source = wls.LayoutSource(root)
            view = wb.build_boxes(source)
            payload = json.dumps(wb.to_json_dict(view))
            decoded = json.loads(payload)
            self.assertEqual(set(decoded.keys()), {"what", "how", "guidelines", "tripwire"})
            self.assertIn("paths", decoded["what"])
            self.assertIn("available", decoded["guidelines"])
            self.assertIn("available", decoded["tripwire"])


if __name__ == "__main__":
    unittest.main()
