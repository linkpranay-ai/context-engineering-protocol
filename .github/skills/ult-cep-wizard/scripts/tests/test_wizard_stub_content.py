"""Regression suite for wizard_stub_content.py (D24 §18.6/§18.10, locked). Stdlib
unittest only. Run with:

    python -m unittest discover -s scripts/tests -v
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wizard_stub_content as wsc  # noqa: E402


class TestWhatHowCard(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_no_resolved_paths_returns_none(self):
        self.assertIsNone(wsc.what_how_card("What", self.root, []))

    def test_nonexistent_directory_yields_a_card(self):
        card = wsc.what_how_card("What", self.root, ["docs/requirements/"])
        self.assertIsNotNone(card)
        self.assertEqual(card.box_title, "What")
        self.assertEqual(card.expected_path, "docs/requirements/")
        self.assertEqual(card.mode, "agent-writes-in-place")
        self.assertIn("docs/requirements/", card.prompt_text)

    def test_existing_but_empty_directory_yields_a_card(self):
        (self.root / "docs" / "requirements").mkdir(parents=True)
        card = wsc.what_how_card("What", self.root, ["docs/requirements/"])
        self.assertIsNotNone(card)

    def test_directory_with_only_ignored_files_still_counts_as_empty(self):
        target = self.root / "docs" / "requirements"
        target.mkdir(parents=True)
        (target / ".gitkeep").write_text("", encoding="utf-8")
        card = wsc.what_how_card("What", self.root, ["docs/requirements/"])
        self.assertIsNotNone(card)

    def test_directory_with_real_content_yields_no_card(self):
        target = self.root / "docs" / "requirements"
        target.mkdir(parents=True)
        (target / "overview.md").write_text("# Requirements\n", encoding="utf-8")
        card = wsc.what_how_card("What", self.root, ["docs/requirements/"])
        self.assertIsNone(card)

    def test_content_in_a_nested_subdirectory_still_counts(self):
        target = self.root / "docs" / "requirements" / "sub"
        target.mkdir(parents=True)
        (target / "detail.md").write_text("content\n", encoding="utf-8")
        card = wsc.what_how_card("What", self.root, ["docs/requirements/"])
        self.assertIsNone(card)

    def test_multi_root_all_empty_yields_a_card(self):
        card = wsc.what_how_card(
            "What", self.root, ["docs/requirements/", "external/specs/"]
        )
        self.assertIsNotNone(card)
        self.assertEqual(card.expected_path, "docs/requirements/")

    def test_multi_root_any_populated_suppresses_the_card(self):
        populated = self.root / "external" / "specs"
        populated.mkdir(parents=True)
        (populated / "spec.md").write_text("content\n", encoding="utf-8")
        card = wsc.what_how_card(
            "What", self.root, ["docs/requirements/", "external/specs/"]
        )
        self.assertIsNone(card)

    def test_how_box_prompt_text_differs_from_what(self):
        what_card = wsc.what_how_card("What", self.root, ["docs/requirements/"])
        how_card = wsc.what_how_card("How", self.root, ["org/"])
        self.assertNotEqual(what_card.prompt_text, how_card.prompt_text)
        self.assertEqual(how_card.box_title, "How")

    def test_what_and_how_cards_name_the_autoscaffold_skill(self):
        what_card = wsc.what_how_card("What", self.root, ["docs/requirements/"])
        how_card = wsc.what_how_card("How", self.root, ["org/"])
        self.assertIn("ult-autoscaffold-content", what_card.prompt_text)
        self.assertIn("ult-autoscaffold-content", how_card.prompt_text)

    def test_prompt_names_autoscaffold_content_artifact_kinds(self):
        card = wsc.what_how_card("What", self.root, ["docs/requirements/"])
        self.assertIn("coding-standards", card.prompt_text)
        self.assertIn("testing-guidelines", card.prompt_text)


class TestGuidelinesCard(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_uninitialized_yields_a_card_naming_the_skill(self):
        card = wsc.guidelines_card(
            self.root, initialized=False,
            default_path="starter_kit/project_guidelines/COMPILED-GUIDELINES.md",
        )
        self.assertIsNotNone(card)
        self.assertEqual(card.box_title, "Guidelines")
        self.assertIn("compiling-project-guidelines", card.prompt_text)
        self.assertEqual(
            card.expected_path, "starter_kit/project_guidelines/COMPILED-GUIDELINES.md"
        )

    def test_initialized_yields_no_card(self):
        card = wsc.guidelines_card(
            self.root, initialized=True,
            default_path="starter_kit/project_guidelines/COMPILED-GUIDELINES.md",
        )
        self.assertIsNone(card)


class TestZeroOnDiskMutation(unittest.TestCase):
    """Direct assertion that this module never writes anything - not just an
    absence of write calls in the source, but a checked before/after snapshot of the
    fixture directory across a full run of both public functions, covering every
    branch (card produced and card suppressed) in one pass."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "docs" / "requirements").mkdir(parents=True)
        populated = self.root / "org"
        populated.mkdir()
        (populated / "conventions.md").write_text("content\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _snapshot(self):
        return sorted(
            (p.relative_to(self.root).as_posix(), p.read_bytes() if p.is_file() else None)
            for p in self.root.rglob("*")
        )

    def test_no_files_added_changed_or_removed(self):
        before = self._snapshot()

        wsc.what_how_card("What", self.root, ["docs/requirements/"])  # empty -> card
        wsc.what_how_card("How", self.root, ["org/"])  # populated -> no card
        wsc.guidelines_card(self.root, initialized=False, default_path="guidelines.md")
        wsc.guidelines_card(self.root, initialized=True, default_path="guidelines.md")

        after = self._snapshot()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
