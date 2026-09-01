#!/usr/bin/env python3
"""Regression suite for wizard_retrofit_state.py (Journey 3, Phase B).

Stdlib unittest only, direct function calls - route-wiring for the state-
touching /api/retrofit/* routes is covered separately in test_wizard_server.py.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wizard_retrofit_state as wrs  # noqa: E402


class RetrofitStateTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


class TestLoadState(RetrofitStateTestCase):
    def test_missing_file_returns_a_fresh_skeleton(self):
        state = wrs.load_state(str(self.root))
        self.assertEqual(state, {"schema_version": wrs.SCHEMA_VERSION, "units": {}})

    def test_corrupt_file_returns_a_fresh_skeleton_not_an_error(self):
        path = wrs.state_path(self.root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not valid json", encoding="utf-8")
        state = wrs.load_state(str(self.root))
        self.assertEqual(state, {"schema_version": wrs.SCHEMA_VERSION, "units": {}})

    def test_file_with_wrong_shape_returns_a_fresh_skeleton(self):
        path = wrs.state_path(self.root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"units": "not-a-dict"}', encoding="utf-8")
        state = wrs.load_state(str(self.root))
        self.assertEqual(state, {"schema_version": wrs.SCHEMA_VERSION, "units": {}})


class TestSaveAndRoundTrip(RetrofitStateTestCase):
    def test_save_then_load_round_trips(self):
        state = wrs.load_state(str(self.root))
        wrs.upsert_selection(
            state, "widget-reviewer",
            primary_file="widget-reviewer/SKILL.md",
            unit_dir_rel_path="widget-reviewer",
            include=True,
            contracts=["CONSUMING-CONTEXT-PACKAGE.md"],
            reference_mode="same-repo",
            reference_args={"CONSUMING-CONTEXT-PACKAGE.md": "../CONSUMING-CONTEXT-PACKAGE.md"},
        )
        wrs.save_state(str(self.root), state)

        reloaded = wrs.load_state(str(self.root))
        self.assertIn("widget-reviewer", reloaded["units"])
        entry = reloaded["units"]["widget-reviewer"]
        self.assertEqual(entry["primary_file"], "widget-reviewer/SKILL.md")
        self.assertTrue(entry["include"])
        self.assertEqual(entry["contracts"], ["CONSUMING-CONTEXT-PACKAGE.md"])

    def test_save_registers_state_dir_in_gitignore(self):
        state = wrs.load_state(str(self.root))
        wrs.save_state(str(self.root), state)
        gitignore = (self.root / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("cache/cep-retrofit/", gitignore)

    def test_save_is_idempotent_about_gitignore(self):
        state = wrs.load_state(str(self.root))
        wrs.save_state(str(self.root), state)
        wrs.save_state(str(self.root), state)
        gitignore = (self.root / ".gitignore").read_text(encoding="utf-8")
        self.assertEqual(gitignore.count("cache/cep-retrofit/"), 1)

    def test_save_preserves_existing_gitignore_content(self):
        (self.root / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
        state = wrs.load_state(str(self.root))
        wrs.save_state(str(self.root), state)
        gitignore = (self.root / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("node_modules/", gitignore)
        self.assertIn("cache/cep-retrofit/", gitignore)


class TestFindUnit(unittest.TestCase):
    def test_missing_unit_is_a_retrofit_state_error(self):
        state = {"schema_version": 1, "units": {}}
        with self.assertRaises(wrs.RetrofitStateError) as ctx:
            wrs.find_unit(state, "widget-reviewer")
        self.assertIn("widget-reviewer", str(ctx.exception))
        self.assertIn("select it first", str(ctx.exception))


class TestUpsertSelection(unittest.TestCase):
    def test_replacing_a_selection_does_not_clear_a_prior_draft(self):
        state = {"schema_version": 1, "units": {}}
        wrs.upsert_selection(
            state, "widget-reviewer",
            primary_file="widget-reviewer/SKILL.md", unit_dir_rel_path="widget-reviewer",
            include=True, contracts=["CONSUMING-CONTEXT-PACKAGE.md"],
            reference_mode="same-repo", reference_args={},
        )
        wrs.set_draft(
            state, "widget-reviewer",
            draft_text="See `../CONSUMING-CONTEXT-PACKAGE.md`.",
            insertion_point={"method": "prepend", "line": 0, "heading": None},
            contracts_included=["CONSUMING-CONTEXT-PACKAGE.md"],
            contracts_skipped_idempotent=[], target_file_hash="deadbeef",
            context_before="", context_after="body text",
        )
        # Re-stage the same selection (e.g. the human re-ticks the same box) -
        # the draft fields should still be there until draft() explicitly runs
        # again, per set_draft's own docstring contract.
        wrs.upsert_selection(
            state, "widget-reviewer",
            primary_file="widget-reviewer/SKILL.md", unit_dir_rel_path="widget-reviewer",
            include=True, contracts=["CONSUMING-CONTEXT-PACKAGE.md"],
            reference_mode="same-repo", reference_args={},
        )
        entry = wrs.find_unit(state, "widget-reviewer")
        self.assertEqual(entry["draft_text"], "See `../CONSUMING-CONTEXT-PACKAGE.md`.")
        self.assertEqual(entry["target_file_hash"], "deadbeef")

    def test_context_availability_defaults_to_ask_and_is_persisted(self):
        """ISSUES.md Round 2 finding 6 (2026-08-31)."""
        state = {"schema_version": 1, "units": {}}
        wrs.upsert_selection(
            state, "widget-reviewer",
            primary_file="widget-reviewer/SKILL.md", unit_dir_rel_path="widget-reviewer",
            include=True, contracts=["CONSUMING-CONTEXT-PACKAGE.md"],
            reference_mode="same-repo", reference_args={},
        )
        entry = wrs.find_unit(state, "widget-reviewer")
        self.assertEqual(entry["context_availability"], "ask")

    def test_explicit_context_availability_is_persisted(self):
        state = {"schema_version": 1, "units": {}}
        wrs.upsert_selection(
            state, "widget-reviewer",
            primary_file="widget-reviewer/SKILL.md", unit_dir_rel_path="widget-reviewer",
            include=True, contracts=["CONSUMING-CONTEXT-PACKAGE.md"],
            reference_mode="same-repo", reference_args={},
            context_availability="required",
        )
        entry = wrs.find_unit(state, "widget-reviewer")
        self.assertEqual(entry["context_availability"], "required")

    def test_target_root_defaults_to_none_and_is_persisted(self):
        """ISSUES.md Round 2 finding 7 (2026-08-31) - None means "this unit's
        primary_file is relative to ctx.repo_root", the unchanged in-repo
        case every existing entry shape and caller keeps working with."""
        state = {"schema_version": 1, "units": {}}
        wrs.upsert_selection(
            state, "widget-reviewer",
            primary_file="widget-reviewer/SKILL.md", unit_dir_rel_path="widget-reviewer",
            include=True, contracts=["CONSUMING-CONTEXT-PACKAGE.md"],
            reference_mode="same-repo", reference_args={},
        )
        entry = wrs.find_unit(state, "widget-reviewer")
        self.assertIn("target_root", entry)
        self.assertIsNone(entry["target_root"])

    def test_explicit_target_root_is_persisted_per_unit(self):
        state = {"schema_version": 1, "units": {}}
        wrs.upsert_selection(
            state, "external-widget",
            primary_file="widget-reviewer/SKILL.md", unit_dir_rel_path="widget-reviewer",
            include=True, contracts=["CONSUMING-CODE-GRAPH.md"],
            reference_mode="plugin",
            reference_args={"CONSUMING-CODE-GRAPH.md": "/context-engineering-oss:ult-cep-wizard"},
            target_root="C:/clones/mattpocock-skills",
        )
        # A second, ordinary in-repo unit selected in the same session must
        # keep its own independent (None) target_root - proves this is a
        # per-unit field, not a session-global toggle.
        wrs.upsert_selection(
            state, "in-repo-widget",
            primary_file="second-widget.md", unit_dir_rel_path=".",
            include=True, contracts=["CONSUMING-CONTEXT-PACKAGE.md"],
            reference_mode="same-repo",
            reference_args={"CONSUMING-CONTEXT-PACKAGE.md": "context-engineering/CONSUMING-CONTEXT-PACKAGE.md"},
        )
        self.assertEqual(
            wrs.find_unit(state, "external-widget")["target_root"],
            "C:/clones/mattpocock-skills",
        )
        self.assertIsNone(wrs.find_unit(state, "in-repo-widget")["target_root"])


class TestSetDraft(unittest.TestCase):
    def setUp(self):
        self.state = {"schema_version": 1, "units": {}}
        wrs.upsert_selection(
            self.state, "widget-reviewer",
            primary_file="widget-reviewer/SKILL.md", unit_dir_rel_path="widget-reviewer",
            include=True, contracts=["CONSUMING-CONTEXT-PACKAGE.md"],
            reference_mode="same-repo", reference_args={},
        )

    def test_set_draft_on_an_unselected_unit_is_a_retrofit_state_error(self):
        with self.assertRaises(wrs.RetrofitStateError):
            wrs.set_draft(
                self.state, "never-selected",
                draft_text="x", insertion_point=None, contracts_included=[],
                contracts_skipped_idempotent=[], target_file_hash=None,
            )

    def test_set_draft_persists_context_before_and_after(self):
        entry = wrs.set_draft(
            self.state, "widget-reviewer",
            draft_text="See `../CONSUMING-CONTEXT-PACKAGE.md`.",
            insertion_point={"method": "see-also", "line": 5, "heading": "See Also"},
            contracts_included=["CONSUMING-CONTEXT-PACKAGE.md"],
            contracts_skipped_idempotent=[], target_file_hash="deadbeef",
            context_before="above line", context_after="below line",
        )
        self.assertEqual(entry["context_before"], "above line")
        self.assertEqual(entry["context_after"], "below line")
        self.assertFalse(entry["draft_overridden"])

    def test_set_draft_defaults_context_fields_to_empty_string(self):
        entry = wrs.set_draft(
            self.state, "widget-reviewer",
            draft_text="x", insertion_point=None, contracts_included=[],
            contracts_skipped_idempotent=[], target_file_hash=None,
        )
        self.assertEqual(entry["context_before"], "")
        self.assertEqual(entry["context_after"], "")

    def test_set_draft_resets_a_prior_override_flag(self):
        wrs.set_draft(
            self.state, "widget-reviewer",
            draft_text="first draft", insertion_point=None, contracts_included=[],
            contracts_skipped_idempotent=[], target_file_hash="hash1",
        )
        wrs.set_draft_override(self.state, "widget-reviewer", "human-edited text")
        entry = wrs.find_unit(self.state, "widget-reviewer")
        self.assertTrue(entry["draft_overridden"])

        wrs.set_draft(
            self.state, "widget-reviewer",
            draft_text="re-drafted text", insertion_point=None, contracts_included=[],
            contracts_skipped_idempotent=[], target_file_hash="hash2",
        )
        entry = wrs.find_unit(self.state, "widget-reviewer")
        self.assertFalse(entry["draft_overridden"])
        self.assertEqual(entry["draft_text"], "re-drafted text")


class TestSetDraftOverride(unittest.TestCase):
    def setUp(self):
        self.state = {"schema_version": 1, "units": {}}
        wrs.upsert_selection(
            self.state, "widget-reviewer",
            primary_file="widget-reviewer/SKILL.md", unit_dir_rel_path="widget-reviewer",
            include=True, contracts=["CONSUMING-CONTEXT-PACKAGE.md"],
            reference_mode="same-repo", reference_args={},
        )

    def test_override_without_a_prior_draft_is_a_retrofit_state_error(self):
        with self.assertRaises(wrs.RetrofitStateError) as ctx:
            wrs.set_draft_override(self.state, "widget-reviewer", "human text")
        self.assertIn("no computed draft yet", str(ctx.exception))

    def test_override_after_a_draft_replaces_the_text_and_sets_the_flag(self):
        wrs.set_draft(
            self.state, "widget-reviewer",
            draft_text="template text", insertion_point=None, contracts_included=[],
            contracts_skipped_idempotent=[], target_file_hash="hash1",
        )
        entry = wrs.set_draft_override(self.state, "widget-reviewer", "human-edited text")
        self.assertEqual(entry["draft_text"], "human-edited text")
        self.assertTrue(entry["draft_overridden"])


class TestToJsonDict(unittest.TestCase):
    def test_returns_the_state_dict_itself(self):
        state = {"schema_version": 1, "units": {}}
        self.assertIs(wrs.to_json_dict(state), state)


if __name__ == "__main__":
    unittest.main()
