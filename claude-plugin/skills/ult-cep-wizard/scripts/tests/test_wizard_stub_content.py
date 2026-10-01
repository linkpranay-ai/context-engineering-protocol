"""Regression suite for wizard_stub_content.py (D24 §18.6/§18.10, locked). Stdlib
unittest only. Run with:

    python -m unittest discover -s scripts/tests -v
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wizard_stub_content as wsc  # noqa: E402

_DRAFT_FRONTMATTER = """---
generated_by: ult-autoscaffold-content
generated_at: 2026-09-01T00:00:00Z
status: draft
content_mode_requested: skeleton
content_mode: skeleton
mode_reason: default
doc_kind: requirements_overview
skill_version: 1
---

# Requirements Overview

TBD.
"""

_FINAL_FRONTMATTER = _DRAFT_FRONTMATTER.replace("status: draft", "status: final")


class TestWhatHowCard(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_no_resolved_paths_returns_none(self):
        self.assertIsNone(wsc.what_how_card("What", self.root, []))

    def test_pending_decision_suppresses_card_even_when_path_is_empty(self):
        # Regression test: a still-pending decision means Apply may move
        # this box's resolved path out from under the very instruction the
        # card would hand the user - the empty-path case alone must not be
        # enough to build a card while that's true.
        card = wsc.what_how_card(
            "What", self.root, ["docs/requirements/"], layer_decisions_pending=True,
        )
        self.assertIsNone(card)

    def test_default_keeps_prior_no_decisions_involved_behavior(self):
        # Every pre-existing caller/test omits layer_decisions_pending
        # entirely - the default must keep producing a card for an empty
        # path, unchanged from before this parameter existed.
        card = wsc.what_how_card("What", self.root, ["docs/requirements/"])
        self.assertIsNotNone(card)

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


class TestWhatHowCardContentModes(unittest.TestCase):
    """W1 mode selector (Proposal Sec 10/12, TASK-0401): `content_modes` /
    `default_mode` on every What/How `StubCard`, gated by the `evidence`
    param a caller optionally passes (wizard_server.py's lazy probe result,
    TASK-0403) - never computed by this module itself."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_default_evidence_is_unknown_and_every_pre_existing_caller_still_works(self):
        # No existing caller/test passes `evidence` - the default must keep
        # every pre-existing assertion in TestWhatHowCard passing unchanged
        # while still populating content_modes/default_mode on the card.
        card = wsc.what_how_card("What", self.root, ["docs/requirements/"])
        self.assertIsNotNone(card.content_modes)
        self.assertEqual(card.default_mode, "skeleton")

    def test_skeleton_always_available(self):
        card = wsc.what_how_card("What", self.root, ["docs/requirements/"])
        skeleton = next(m for m in card.content_modes if m["id"] == "skeleton")
        self.assertTrue(skeleton["available"])
        self.assertIsNone(skeleton["reason"])

    def test_what_box_never_offers_augmented(self):
        card = wsc.what_how_card("What", self.root, ["docs/requirements/"])
        ids = [m["id"] for m in card.content_modes]
        self.assertNotIn("augmented", ids)

    def test_how_box_offers_augmented(self):
        card = wsc.what_how_card("How", self.root, ["org/"])
        ids = [m["id"] for m in card.content_modes]
        self.assertIn("augmented", ids)

    def test_unknown_evidence_marks_grounded_unavailable_with_reason(self):
        card = wsc.what_how_card(
            "How", self.root, ["org/"], evidence="unknown",
        )
        grounded = next(m for m in card.content_modes if m["id"] == "grounded")
        self.assertFalse(grounded["available"])
        self.assertIn("unknown", grounded["reason"])
        self.assertEqual(card.default_mode, "skeleton")

    def test_greenfield_evidence_marks_grounded_unavailable_with_reason(self):
        card = wsc.what_how_card(
            "How", self.root, ["org/"],
            evidence={"greenfield": True, "grounded_viable": {}},
        )
        grounded = next(m for m in card.content_modes if m["id"] == "grounded")
        self.assertFalse(grounded["available"])
        self.assertIn("greenfield", grounded["reason"])
        self.assertEqual(card.default_mode, "skeleton")

    def test_real_grounded_evidence_makes_how_default_to_grounded(self):
        card = wsc.what_how_card(
            "How", self.root, ["org/"],
            evidence={
                "greenfield": False,
                "grounded_viable": {"coding_standards": True, "testing_guidelines": False},
            },
        )
        grounded = next(m for m in card.content_modes if m["id"] == "grounded")
        augmented = next(m for m in card.content_modes if m["id"] == "augmented")
        self.assertTrue(grounded["available"])
        self.assertTrue(augmented["available"])
        self.assertEqual(card.default_mode, "grounded")

    def test_no_viable_signal_keeps_what_default_at_skeleton(self):
        card = wsc.what_how_card(
            "What", self.root, ["docs/requirements/"],
            evidence={"greenfield": False, "grounded_viable": {"requirements_overview": False}},
        )
        grounded = next(m for m in card.content_modes if m["id"] == "grounded")
        self.assertFalse(grounded["available"])
        self.assertEqual(card.default_mode, "skeleton")

    def test_scaffold_card_kind_is_the_default(self):
        card = wsc.what_how_card("What", self.root, ["docs/requirements/"])
        self.assertEqual(card.card_kind, "scaffold")
        self.assertEqual(card.draft_files, [])


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

    def test_layer_decisions_pending_suppresses_the_card(self):
        # Closes the What/How-vs-Guidelines/Trip-wire card-gating asymmetry:
        # an uninitialized, otherwise card-worthy state is still suppressed
        # while a What/How layer decision is unresolved.
        card = wsc.guidelines_card(
            self.root, initialized=False,
            default_path="starter_kit/project_guidelines/COMPILED-GUIDELINES.md",
            layer_decisions_pending=True,
        )
        self.assertIsNone(card)


class TestTripwireCard(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_unavailable_yields_no_card(self):
        # Owning skill not installed - the frontend's own "not available"
        # messaging already covers this; a stub card here would just repeat it.
        card = wsc.tripwire_card(
            self.root, available=False, initialized=False, entries=0, ledger_path=None,
        )
        self.assertIsNone(card)

    def test_never_initialized_yields_a_card_naming_the_skill(self):
        card = wsc.tripwire_card(
            self.root, available=True, initialized=False, entries=0,
            ledger_path="cache/decision-ledger/DECISION-LEDGER.json",
        )
        self.assertIsNotNone(card)
        self.assertEqual(card.box_title, "Trip-wire")
        self.assertIn("ult-institutional-memory-distill", card.prompt_text)
        self.assertEqual(
            card.expected_path, "cache/decision-ledger/DECISION-LEDGER.json"
        )

    def test_initialized_but_empty_ledger_still_yields_a_card(self):
        # Regression test for the report finding this fixes: an
        # initialized-but-0-entries ledger is exactly as much of an onboarding
        # dead end as a missing one - entries==0 must gate independently of
        # initialized, not be masked by it.
        card = wsc.tripwire_card(
            self.root, available=True, initialized=True, entries=0,
            ledger_path="cache/decision-ledger/DECISION-LEDGER.json",
        )
        self.assertIsNotNone(card)

    def test_initialized_with_real_entries_yields_no_card(self):
        card = wsc.tripwire_card(
            self.root, available=True, initialized=True, entries=3,
            ledger_path="cache/decision-ledger/DECISION-LEDGER.json",
        )
        self.assertIsNone(card)

    def test_missing_ledger_path_yields_no_card_defensively(self):
        # Shouldn't happen per wizard_tripwire.read_summary()'s own contract, but
        # this module never assumes it - same defensive posture as what_how_card's
        # empty-resolved_paths branch.
        card = wsc.tripwire_card(
            self.root, available=True, initialized=False, entries=0, ledger_path=None,
        )
        self.assertIsNone(card)

    def test_prompt_states_no_synthesis_without_evidence(self):
        card = wsc.tripwire_card(
            self.root, available=True, initialized=False, entries=0,
            ledger_path="cache/decision-ledger/DECISION-LEDGER.json",
        )
        self.assertIn("evidence", card.prompt_text)
        self.assertIn("source streams", card.prompt_text)

    def test_layer_decisions_pending_suppresses_the_card(self):
        # Same card-gating asymmetry fix as guidelines_card's own test above.
        card = wsc.tripwire_card(
            self.root, available=True, initialized=False, entries=0,
            ledger_path="cache/decision-ledger/DECISION-LEDGER.json",
            layer_decisions_pending=True,
        )
        self.assertIsNone(card)


class TestUpgradeCard(unittest.TestCase):
    """P1 'Upgrade drafts' card (Proposal Sec 9.4/10, TASK-0401): appears only
    when every file under the resolved What/How path is an untouched
    autoscaffold-content draft, so the wizard can offer a one-click
    regenerate-at-higher-mode handoff without ever risking a human edit."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.layer_dir = self.root / "docs" / "requirements"
        self.layer_dir.mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, name, text):
        (self.layer_dir / name).write_text(text, encoding="utf-8")

    def test_no_resolved_paths_returns_none(self):
        self.assertIsNone(wsc.upgrade_card("What", self.root, []))

    def test_empty_directory_returns_none(self):
        self.assertIsNone(
            wsc.upgrade_card("What", self.root, ["docs/requirements/"])
        )

    def test_all_drafts_yields_a_card_listing_them(self):
        self._write("REQUIREMENTS-OVERVIEW.md", _DRAFT_FRONTMATTER)
        card = wsc.upgrade_card("What", self.root, ["docs/requirements/"])
        self.assertIsNotNone(card)
        self.assertEqual(card.box_title, "What")
        self.assertEqual(card.card_kind, "upgrade")
        self.assertEqual(
            card.draft_files,
            ["docs/requirements/REQUIREMENTS-OVERVIEW.md"],
        )

    def test_a_finalized_file_suppresses_the_card(self):
        self._write("REQUIREMENTS-OVERVIEW.md", _DRAFT_FRONTMATTER)
        self._write("NOTES.md", _FINAL_FRONTMATTER)
        self.assertIsNone(
            wsc.upgrade_card("What", self.root, ["docs/requirements/"])
        )

    def test_a_file_with_no_frontmatter_suppresses_the_card(self):
        self._write("REQUIREMENTS-OVERVIEW.md", _DRAFT_FRONTMATTER)
        self._write("README.md", "# Hand-written notes\n")
        self.assertIsNone(
            wsc.upgrade_card("What", self.root, ["docs/requirements/"])
        )

    def test_a_file_not_generated_by_this_skill_suppresses_the_card(self):
        self._write("REQUIREMENTS-OVERVIEW.md", _DRAFT_FRONTMATTER)
        other_tool_draft = _DRAFT_FRONTMATTER.replace(
            "generated_by: ult-autoscaffold-content",
            "generated_by: some-other-skill",
        )
        self._write("OTHER.md", other_tool_draft)
        self.assertIsNone(
            wsc.upgrade_card("What", self.root, ["docs/requirements/"])
        )

    def test_layer_decisions_pending_suppresses_the_card(self):
        self._write("REQUIREMENTS-OVERVIEW.md", _DRAFT_FRONTMATTER)
        self.assertIsNone(
            wsc.upgrade_card(
                "What", self.root, ["docs/requirements/"],
                layer_decisions_pending=True,
            )
        )

    def test_truncated_listing_suppresses_the_card_conservatively(self):
        self._write("REQUIREMENTS-OVERVIEW.md", _DRAFT_FRONTMATTER)
        truncated = wsc.wbf.FileListing(
            files=["REQUIREMENTS-OVERVIEW.md"], total_count=9999, truncated=True,
        )
        with patch.object(wsc.wbf, "list_files", return_value=truncated):
            self.assertIsNone(
                wsc.upgrade_card("What", self.root, ["docs/requirements/"])
            )

    def test_card_carries_content_modes_like_what_how_card(self):
        self._write("REQUIREMENTS-OVERVIEW.md", _DRAFT_FRONTMATTER)
        card = wsc.upgrade_card("What", self.root, ["docs/requirements/"])
        ids = [m["id"] for m in card.content_modes]
        self.assertIn("skeleton", ids)
        self.assertNotIn("augmented", ids)
        self.assertEqual(card.default_mode, "skeleton")


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
        drafts = self.root / "drafts"
        drafts.mkdir()
        (drafts / "REQUIREMENTS-OVERVIEW.md").write_text(
            _DRAFT_FRONTMATTER, encoding="utf-8"
        )

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
        wsc.tripwire_card(  # never initialized -> card
            self.root, available=True, initialized=False, entries=0,
            ledger_path="cache/decision-ledger/DECISION-LEDGER.json",
        )
        wsc.tripwire_card(  # real entries -> no card
            self.root, available=True, initialized=True, entries=3,
            ledger_path="cache/decision-ledger/DECISION-LEDGER.json",
        )
        wsc.upgrade_card("What", self.root, ["drafts/"])  # all drafts -> card
        wsc.upgrade_card("How", self.root, ["org/"])  # not a draft -> no card
        wsc.upgrade_card("What", self.root, ["docs/requirements/"])  # empty -> no card

        after = self._snapshot()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
