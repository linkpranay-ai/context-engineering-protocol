"""Regression suite for wizard_layout_source.py (D24 §18.2b/§18.3, locked). Stdlib
unittest only. Run with:

    python -m unittest discover -s scripts/tests -v

validate_layout.py and discover_layers.py are both copied fresh from the real
ult-repo-layout/scripts/ at test time (not hand-transcribed stubs), same convention
as test_wizard_preflight.py - so these tests exercise the real resolver functions
(resolve_default, resolved_path_for_marker, resolve_what_l2_path, etc.) and cannot
silently drift from them.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
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
REAL_SKILLS_DIR = REAL_REPO_ROOT / ".github" / "skills" / "ult-repo-layout"
REAL_SKILL_MD = REAL_SKILLS_DIR / "SKILL.md"
REAL_VALIDATE_LAYOUT = REAL_SKILLS_DIR / "scripts" / "validate_layout.py"
REAL_DISCOVER_LAYERS = REAL_SKILLS_DIR / "scripts" / "discover_layers.py"
REAL_LAYOUT_DECISION_GRAMMAR = REAL_SKILLS_DIR / "scripts" / "layout_decision_grammar.py"
REAL_CONFIRM_LAYERS = REAL_SKILLS_DIR / "scripts" / "confirm_layers.py"


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _install_ult_repo_layout(repo_root: Path) -> None:
    skill_dir = repo_root / ".github" / "skills" / "ult-repo-layout"
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(REAL_SKILL_MD, skill_dir / "SKILL.md")
    shutil.copy(REAL_VALIDATE_LAYOUT, scripts_dir / "validate_layout.py")
    shutil.copy(REAL_DISCOVER_LAYERS, scripts_dir / "discover_layers.py")
    # D24 Phase 1: LayoutSource._import_repo_layout_modules now also imports
    # layout_decision_grammar and confirm_layers unconditionally (needed for
    # the write path), so every fixture that constructs a LayoutSource needs
    # both present alongside discover_layers.py/validate_layout.py.
    shutil.copy(
        REAL_LAYOUT_DECISION_GRAMMAR, scripts_dir / "layout_decision_grammar.py"
    )
    shutil.copy(REAL_CONFIRM_LAYERS, scripts_dir / "confirm_layers.py")


def _make_valid_target_repo(root: Path) -> None:
    """A repo that passes validate_layout.py's own --validate (same shape
    test_wizard_preflight.py's positive fixture uses) - installed, initialized, and
    validating clean, with one marker for the context_packages slot."""
    _install_ult_repo_layout(root)
    (root / ".github" / "skills" / "ult-context-generate").mkdir(parents=True)
    _write(
        root / "contexts" / ".layout-slots.yaml",
        "slots:\n  - slot: context_packages\n    kind: directory\n"
        "    schema_version: 1\n",
    )


class TestConstructionGate(unittest.TestCase):
    def test_missing_ult_repo_layout_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(wls.LayoutSourceError) as ctx:
                wls.LayoutSource(tmp)
            self.assertIn("ult-repo-layout", str(ctx.exception))

    def test_broken_layout_raises_with_failures_listed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _install_ult_repo_layout(root)
            # Two markers for the same slot ("has markers at multiple locations") is
            # a real validate_layout.py FAIL condition, not an artificial one.
            (root / ".github" / "skills" / "ult-context-generate").mkdir(parents=True)
            marker = (
                "slots:\n  - slot: context_packages\n    kind: directory\n"
                "    schema_version: 1\n"
            )
            _write(root / "contexts" / ".layout-slots.yaml", marker)
            _write(root / "contexts2" / ".layout-slots.yaml", marker)
            with self.assertRaises(wls.LayoutSourceError) as ctx:
                wls.LayoutSource(root)
            self.assertIn("FAIL", str(ctx.exception))

    def test_valid_repo_constructs_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_valid_target_repo(root)
            wls.LayoutSource(root)  # must not raise


class TestReadSlots(unittest.TestCase):
    def test_marker_backed_slot_is_initialized_with_resolved_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_valid_target_repo(root)
            source = wls.LayoutSource(root)
            slots = source.read_slots()
            self.assertIn("context_packages", slots)
            state = slots["context_packages"]
            self.assertTrue(state.initialized)
            self.assertEqual(state.resolved_paths, ["contexts"])
            self.assertEqual(state.owning_skill, "ult-context-generate")

    def test_slot_with_no_marker_is_not_initialized_but_has_a_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_valid_target_repo(root)
            # writing-plans owns plans_output, but no marker for it exists and its
            # owning skill isn't installed either - resolve_default still returns
            # the pre-D21 documented default, matching validate_layout.py's own
            # INFO-not-FAIL behavior for an unmarked, uninstalled-owner slot.
            source = wls.LayoutSource(root)
            slots = source.read_slots()
            # Only installed-owning-skill slots are surfaced at all (mirrors
            # validate_layout.py's own _owning_skill_installed filter) - plans_output's
            # owning skill (writing-plans) isn't installed in this fixture, so it must
            # not appear.
            self.assertNotIn("plans_output", slots)

    def test_slot_read_is_fresh_not_cached(self):
        """Moving the marker to a different directory between two read_slots() calls
        must show up on the second call - proves no caching happened at construction
        time. (Two *simultaneous* markers for the same slot is itself a
        validate_layout.py FAIL condition - see TestConstructionGate - so this test
        moves the marker rather than adding a second one, to stay in a state
        validate() would still accept.)"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_valid_target_repo(root)
            source = wls.LayoutSource(root)

            first = source.read_slots()
            self.assertEqual(first["context_packages"].resolved_paths, ["contexts"])

            (root / "contexts" / ".layout-slots.yaml").unlink()
            _write(
                root / "contexts_renamed" / ".layout-slots.yaml",
                "slots:\n  - slot: context_packages\n    kind: directory\n"
                "    schema_version: 1\n",
            )
            second = source.read_slots()
            self.assertEqual(
                second["context_packages"].resolved_paths, ["contexts_renamed"]
            )


class TestReadLayers(unittest.TestCase):
    def test_all_four_layer_keys_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_valid_target_repo(root)
            source = wls.LayoutSource(root)
            layers = source.read_layers()
            self.assertEqual(
                set(layers.keys()),
                {"layers.what_l2", "how_dimension.how_l2", "layers.what_l1", "how_dimension.how_l1"},
            )

    def test_always_on_layers_default_to_enabled_with_a_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_valid_target_repo(root)
            source = wls.LayoutSource(root)
            layers = source.read_layers()
            what_l2 = layers["layers.what_l2"]
            how_l2 = layers["how_dimension.how_l2"]
            self.assertTrue(what_l2.enabled)
            self.assertTrue(how_l2.enabled)
            self.assertEqual(what_l2.path, "docs/requirements/")  # pre-D21 default
            self.assertEqual(how_l2.path, "org/")  # pre-D21 default
            self.assertEqual(what_l2.resolved_paths, ["docs/requirements/"])

    def test_opt_in_layer_defaults_to_disabled_with_no_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_valid_target_repo(root)
            source = wls.LayoutSource(root)
            layers = source.read_layers()
            what_l1 = layers["layers.what_l1"]
            how_l1 = layers["how_dimension.how_l1"]
            self.assertFalse(what_l1.enabled)
            self.assertIsNone(what_l1.path)
            self.assertEqual(what_l1.resolved_paths, [])
            self.assertFalse(how_l1.enabled)

    def test_explicitly_enabled_opt_in_layer_with_path_resolves(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_valid_target_repo(root)
            _write(
                root / "context-config.yaml",
                "layers:\n  what_l1:\n    enabled: true\n    path: external/specs/\n",
            )
            source = wls.LayoutSource(root)
            layers = source.read_layers()
            what_l1 = layers["layers.what_l1"]
            self.assertTrue(what_l1.enabled)
            self.assertEqual(what_l1.path, "external/specs/")
            self.assertEqual(what_l1.resolved_paths, ["external/specs/"])

    def test_enabled_but_no_path_still_resolves_to_empty(self):
        """An opt-in layer enabled: true with no path set has nothing to resolve -
        matches validate_layout.py's own S28 condition, not a wizard-invented rule."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_valid_target_repo(root)
            _write(root / "context-config.yaml", "layers:\n  what_l1:\n    enabled: true\n")
            source = wls.LayoutSource(root)
            layers = source.read_layers()
            self.assertEqual(layers["layers.what_l1"].resolved_paths, [])

    def test_what_l2_include_roots_are_multi_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_valid_target_repo(root)
            _write(
                root / "context-config.yaml",
                "layers:\n  what_l2:\n    path: docs/requirements/\n"
                "    include_roots:\n      - vendor/spec-a/\n      - vendor/spec-b/\n",
            )
            source = wls.LayoutSource(root)
            layers = source.read_layers()
            what_l2 = layers["layers.what_l2"]
            self.assertEqual(
                what_l2.resolved_paths,
                ["docs/requirements/", "vendor/spec-a/", "vendor/spec-b/"],
            )

    def test_layer_read_is_fresh_not_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_valid_target_repo(root)
            source = wls.LayoutSource(root)

            first = source.read_layers()
            self.assertFalse(first["layers.what_l1"].enabled)

            _write(root / "context-config.yaml", "layers:\n  what_l1:\n    enabled: true\n"
                   "    path: external/specs/\n")
            second = source.read_layers()
            self.assertTrue(second["layers.what_l1"].enabled)
            self.assertEqual(second["layers.what_l1"].path, "external/specs/")

    def test_titles_come_from_discover_layers_title_to_base_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_valid_target_repo(root)
            source = wls.LayoutSource(root)
            layers = source.read_layers()
            self.assertIn("What-L2", layers["layers.what_l2"].title)
            self.assertIn("How-L2", layers["how_dimension.how_l2"].title)


if __name__ == "__main__":
    unittest.main()
