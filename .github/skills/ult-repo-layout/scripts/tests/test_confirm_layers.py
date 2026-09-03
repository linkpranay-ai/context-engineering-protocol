"""Regression suite for confirm_layers.py (§17.5-17.6).

Stdlib unittest only, same posture as test_discover_layers.py. Run with:

    python -m unittest discover -s scripts/tests -v
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import confirm_layers as cl  # noqa: E402
import discover_layers as dl  # noqa: E402


def write(path, content=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TempRepoTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo_root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def artifact(self, text):
        write(self.repo_root / "context-layout-discovery.md", text)

    def config_text(self):
        path = self.repo_root / "context-config.yaml"
        return path.read_text(encoding="utf-8") if path.exists() else None

    def artifact_text(self):
        return (self.repo_root / "context-layout-discovery.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Field.resolve() - the comment-as-grammar parser
# ---------------------------------------------------------------------------

class TestFieldResolve(unittest.TestCase):
    def _field(self, raw_value, comment):
        return cl.Field(0, "Some Section", "decision", raw_value, comment)

    def test_bare_verb_pulls_default_arg_from_comment(self):
        f = self._field("CONFIRM", "CONFIRM: my-specs/ | CUSTOM: <path> | SKIP")
        f.resolve()
        self.assertEqual(f.verb, "CONFIRM")
        self.assertEqual(f.arg, "my-specs/")

    def test_explicit_arg_overrides_comment_default(self):
        f = self._field("CONFIRM: other-specs/", "CONFIRM: my-specs/ | CUSTOM: <path> | SKIP")
        f.resolve()
        self.assertEqual(f.verb, "CONFIRM")
        self.assertEqual(f.arg, "other-specs/")

    def test_custom_with_explicit_arg_is_accepted(self):
        f = self._field("CUSTOM: docs/reqs/", "CONFIRM: my-specs/ | CUSTOM: <path> | SKIP")
        f.resolve()
        self.assertEqual(f.verb, "CUSTOM")
        self.assertEqual(f.arg, "docs/reqs/")

    def test_bare_custom_with_no_argument_is_a_placeholder_error(self):
        f = self._field("CUSTOM", "CONFIRM: my-specs/ | CUSTOM: <path> | SKIP")
        with self.assertRaises(cl.FieldError):
            f.resolve()

    def test_custom_with_leftover_placeholder_text_is_an_error(self):
        f = self._field("CUSTOM: <path>", "CONFIRM: my-specs/ | CUSTOM: <path> | SKIP")
        with self.assertRaises(cl.FieldError):
            f.resolve()

    def test_verb_not_offered_on_this_line_is_rejected(self):
        f = self._field("ACKNOWLEDGE", "CONFIRM: my-specs/ | CUSTOM: <path> | SKIP")
        with self.assertRaises(cl.FieldError):
            f.resolve()

    def test_acknowledge_offered_alongside_candidates_is_accepted(self):
        # the 2026-08-31 Round-2 evaluation's finding on What-L2 decision-line verb
        # coverage: once a line's own comment lists ACKNOWLEDGE (as
        # discover_layers.py's with-candidates template now does), it resolves
        # like any other listed verb - same generic comment-as-grammar parsing
        # as the negative case above, just with the verb actually offered.
        f = self._field("ACKNOWLEDGE", "CONFIRM: my-specs/ | CUSTOM: <path> | SKIP | ACKNOWLEDGE")
        f.resolve()
        self.assertEqual(f.verb, "ACKNOWLEDGE")
        self.assertIsNone(f.arg)

    def test_still_pending_is_an_error(self):
        f = self._field("PENDING", "CONFIRM: my-specs/ | CUSTOM: <path> | SKIP")
        with self.assertRaises(cl.FieldError):
            f.resolve()

    def test_missing_comment_is_an_error(self):
        f = self._field("SKIP", None)
        with self.assertRaises(cl.FieldError):
            f.resolve()

    def test_bare_verb_with_trailing_prose_and_no_colon(self):
        f = self._field("false", "true | false - discovery never flips this on by itself")
        f.resolve()
        self.assertEqual(f.verb, "false")
        self.assertIsNone(f.arg)

    def test_bare_verb_with_parenthetical_note_h2_case(self):
        comment = "CONFIRM: docs/api/ | SKIP  (H-2: no Requirements match exists - pick one)"
        f = self._field("SKIP", comment)
        f.resolve()
        self.assertEqual(f.verb, "SKIP")
        self.assertIsNone(f.arg)

    def test_already_confirmed_stamp_short_circuits_validation(self):
        # .comment is already `#`-stripped by parse_artifact() by the time a
        # real Field sees it - no leading "#" here, matching that contract.
        f = self._field("SKIP", "CONFIRMED 2026-07-24T00:00:00+00:00")
        f.resolve()
        self.assertTrue(f.already_confirmed)
        # verb/arg are still parsed from the stamped value even though
        # validation is short-circuited - §17.6 drift tracking needs to know
        # what was decided, not just that something was.
        self.assertEqual(f.verb, "SKIP")
        self.assertIsNone(f.arg)


# ---------------------------------------------------------------------------
# YAML-preserving writer primitives
# ---------------------------------------------------------------------------

class TestSetScalar(unittest.TestCase):
    def test_creates_full_path_on_empty_file(self):
        lines = []
        cl.set_scalar(lines, ["layers", "what_l2", "path"], "my-specs/")
        text = "\n".join(lines)
        self.assertIn("layers:", text)
        self.assertIn("  what_l2:", text)
        self.assertIn("    path: my-specs/", text)

    def test_overwrites_existing_value_preserving_trailing_comment(self):
        lines = [
            "layers:",
            "  what_l2:",
            "    path: <requirements docs root, e.g. docs/requirements/>",
        ]
        cl.set_scalar(lines, ["layers", "what_l2", "path"], "my-specs/")
        self.assertEqual(lines[2], "    path: my-specs/")

    def test_preserves_unrelated_sibling_keys(self):
        lines = [
            "layers:",
            "  what_l2:",
            "    path: old/",
            "    exclude: []",
            "  what_l1:",
            "    enabled: false",
        ]
        cl.set_scalar(lines, ["layers", "what_l2", "path"], "new/")
        self.assertEqual(lines[2], "    path: new/")
        self.assertEqual(lines[3], "    exclude: []")
        self.assertEqual(lines[4], "  what_l1:")
        self.assertEqual(lines[5], "    enabled: false")

    def test_creates_missing_leaf_under_existing_parent(self):
        lines = ["layers:", "  what_l2:", "    exclude: []"]
        cl.set_scalar(lines, ["layers", "what_l2", "path"], "my-specs/")
        self.assertIn("    path: my-specs/", lines)


class TestAppendListItem(unittest.TestCase):
    def test_converts_inline_empty_list_to_block_form(self):
        lines = ["layers:", "  what_l2:", "    exclude: []"]
        cl.append_list_item(lines, ["layers", "what_l2", "exclude"], "vendor/")
        text = "\n".join(lines)
        self.assertNotIn("exclude: []", text)
        self.assertIn("    exclude:", text)
        self.assertIn("      - vendor/", text)

    def test_appends_after_existing_block_entries(self):
        lines = [
            "layers:",
            "  what_l2:",
            "    include_roots:",
            "      - a/",
            "      - b/",
        ]
        cl.append_list_item(lines, ["layers", "what_l2", "include_roots"], "c/")
        self.assertEqual(lines[-1], "      - c/")
        self.assertEqual(len(lines), 6)

    def test_creates_key_and_list_when_absent(self):
        lines = ["layers:", "  what_l2:", "    path: my-specs/"]
        cl.append_list_item(lines, ["layers", "what_l2", "exclude"], "cache/")
        text = "\n".join(lines)
        self.assertIn("    exclude:", text)
        self.assertIn("      - cache/", text)

    def test_preserves_inline_list_trailing_comment_on_conversion(self):
        lines = ["layers:", "  what_l2:", "    exclude: []           # D21 note"]
        cl.append_list_item(lines, ["layers", "what_l2", "exclude"], "vendor/")
        self.assertEqual(lines[2], "    exclude:  # D21 note")
        self.assertEqual(lines[3], "      - vendor/")


class TestSetListItem(unittest.TestCase):
    def test_overwrites_item_at_index(self):
        lines = [
            "layers:",
            "  what_l2:",
            "    include_roots:",
            "      - a/",
            "      - b/",
        ]
        cl.set_list_item(lines, ["layers", "what_l2", "include_roots"], 1, "b-new/")
        self.assertEqual(lines[4], "      - b-new/")
        self.assertEqual(lines[3], "      - a/")

    def test_missing_list_raises(self):
        lines = ["layers:", "  what_l2:", "    path: x/"]
        with self.assertRaises(ValueError):
            cl.set_list_item(lines, ["layers", "what_l2", "include_roots"], 0, "x/")

    def test_out_of_range_index_raises(self):
        lines = ["layers:", "  what_l2:", "    include_roots:", "      - a/"]
        with self.assertRaises(ValueError):
            cl.set_list_item(lines, ["layers", "what_l2", "include_roots"], 5, "x/")


class TestParseDottedPath(unittest.TestCase):
    def test_plain_scalar_path(self):
        parts, index = cl.parse_dotted_path("how_dimension.how_l1.path")
        self.assertEqual(parts, ["how_dimension", "how_l1", "path"])
        self.assertIsNone(index)

    def test_indexed_list_path(self):
        parts, index = cl.parse_dotted_path("layers.what_l2.include_roots[0]")
        self.assertEqual(parts, ["layers", "what_l2", "include_roots"])
        self.assertEqual(index, 0)


# ---------------------------------------------------------------------------
# End-to-end run_confirm() - §17.9 stress scenarios assigned to confirm-layers
# ---------------------------------------------------------------------------

class TestRunConfirmEndToEnd(TempRepoTestCase):
    def test_missing_artifact_refuses(self):
        code, messages = cl.run_confirm(self.repo_root)
        self.assertEqual(code, 1)
        self.assertIn("run `discover` first", messages[0])

    def test_pending_field_refuses_no_partial_write(self):
        self.artifact(
            f"## {dl.WHAT_L2_TITLE}\n\n"
            "    decision: PENDING   # CONFIRM: my-specs/ | CUSTOM: <path> | SKIP\n"
        )
        original = self.artifact_text()
        code, messages = cl.run_confirm(self.repo_root)
        self.assertEqual(code, 1)
        self.assertIn("PENDING", messages[0])
        self.assertIsNone(self.config_text())
        self.assertEqual(self.artifact_text(), original)

    def test_confirm_writes_config_and_stamps_artifact(self):
        self.artifact(
            f"## {dl.WHAT_L2_TITLE}\n\n"
            "    decision: CONFIRM   # CONFIRM: my-specs/ | CUSTOM: <path> | SKIP\n"
        )
        code, messages = cl.run_confirm(self.repo_root)
        self.assertEqual(code, 0)
        self.assertIn("layers:", self.config_text())
        self.assertIn("my-specs/", self.config_text())
        self.assertIn("CONFIRMED", self.artifact_text())
        self.assertNotIn("CONFIRM: my-specs/ | CUSTOM", self.artifact_text())

    def test_skip_stamps_but_writes_no_config(self):
        self.artifact(
            f"## {dl.WHAT_L2_TITLE}\n\n"
            "    decision: SKIP   # CONFIRM: my-specs/ | CUSTOM: <path> | SKIP\n"
        )
        code, messages = cl.run_confirm(self.repo_root)
        self.assertEqual(code, 0)
        self.assertIsNone(self.config_text())
        self.assertIn("CONFIRMED", self.artifact_text())

    def test_idempotent_rerun_does_nothing_the_second_time(self):
        self.artifact(
            f"## {dl.WHAT_L2_TITLE}\n\n"
            "    decision: CONFIRM   # CONFIRM: my-specs/ | CUSTOM: <path> | SKIP\n"
        )
        cl.run_confirm(self.repo_root)
        stamped = self.artifact_text()
        config_after_first = self.config_text()
        code, messages = cl.run_confirm(self.repo_root)
        self.assertEqual(code, 0)
        self.assertIn("Nothing to confirm", messages[0])
        self.assertEqual(self.artifact_text(), stamped)
        self.assertEqual(self.config_text(), config_after_first)

    def test_include_roots_add_appends_to_config(self):
        self.artifact(
            f"## {dl.WHAT_L2_TITLE}\n\n"
            "    decision: CONFIRM   # CONFIRM: my-specs/ | CUSTOM: <path> | SKIP\n\n"
            "    include_roots_decision: ADD   # ADD: extra-docs/ | SKIP\n"
        )
        code, _ = cl.run_confirm(self.repo_root)
        self.assertEqual(code, 0)
        self.assertIn("extra-docs/", self.config_text())
        self.assertIn("include_roots", self.config_text())

    def test_collision_custom_writes_arbitrary_dotted_path(self):
        self.artifact(
            f"## {dl.COLLISION_TITLE}\n\n"
            "    collision_decision: CUSTOM: how_dimension.how_l2.path -> team-notes/   "
            "# ACKNOWLEDGE | CUSTOM: <layer> -> <new path>\n"
        )
        code, _ = cl.run_confirm(self.repo_root)
        self.assertEqual(code, 0)
        self.assertIn("team-notes/", self.config_text())
        self.assertIn("how_l2", self.config_text())

    def test_collision_custom_on_indexed_include_root(self):
        write(
            self.repo_root / "context-config.yaml",
            "layers:\n  what_l2:\n    include_roots:\n      - old/\n",
        )
        self.artifact(
            f"## {dl.COLLISION_TITLE}\n\n"
            "    collision_decision: CUSTOM: layers.what_l2.include_roots[0] -> moved/   "
            "# ACKNOWLEDGE | CUSTOM: <layer> -> <new path>\n"
        )
        code, _ = cl.run_confirm(self.repo_root)
        self.assertEqual(code, 0)
        self.assertIn("moved/", self.config_text())
        self.assertNotIn("old/", self.config_text())

    def test_two_candidates_both_confirmed_in_same_section_refuses(self):
        self.artifact(
            f"## {dl.WHAT_L2_TITLE}\n\n"
            "    decision: CONFIRM   # CONFIRM: docs/api/ | SKIP  (H-2: pick one)\n\n"
            "    decision: CONFIRM   # CONFIRM: docs/spec/ | SKIP  (H-2: pick one)\n"
        )
        code, messages = cl.run_confirm(self.repo_root)
        self.assertEqual(code, 1)
        self.assertTrue(any("pick exactly one" in m for m in messages))
        self.assertIsNone(self.config_text())

    def test_one_confirmed_one_skipped_in_same_section_succeeds(self):
        self.artifact(
            f"## {dl.WHAT_L2_TITLE}\n\n"
            "    decision: CONFIRM   # CONFIRM: docs/api/ | SKIP  (H-2: pick one)\n\n"
            "    decision: SKIP   # CONFIRM: docs/spec/ | SKIP  (H-2: pick one)\n"
        )
        code, _ = cl.run_confirm(self.repo_root)
        self.assertEqual(code, 0)
        self.assertIn("docs/api/", self.config_text())
        self.assertNotIn("docs/spec/", self.config_text())

    def test_disable_verb_writes_enabled_false(self):
        self.artifact(
            f"## {dl.WHAT_L1_TITLE}\n\n"
            "    decision: DISABLE   # CUSTOM: <path> | DISABLE\n"
        )
        code, _ = cl.run_confirm(self.repo_root)
        self.assertEqual(code, 0)
        self.assertIn("enabled: false", self.config_text())

    def test_enable_and_decision_resolved_together(self):
        self.artifact(
            f"## {dl.WHAT_L1_TITLE}\n\n"
            "    decision: CONFIRM   # CONFIRM: specs/external/ | CUSTOM: <path> | SKIP\n\n"
            "    enable: true   # true | false - discovery never flips this on by itself\n"
        )
        code, _ = cl.run_confirm(self.repo_root)
        self.assertEqual(code, 0)
        self.assertIn("enabled: true", self.config_text())
        self.assertIn("specs/external/", self.config_text())

    def test_workspace_root_placement_used_for_artifact_lookup(self):
        write(
            self.repo_root / "context-config.yaml",
            "layout:\n  workspace_root: contexts/\n",
        )
        self.artifact_in_workspace = self.repo_root / "contexts" / "context-layout-discovery.md"
        write(
            self.artifact_in_workspace,
            f"## {dl.WHAT_L2_TITLE}\n\n"
            "    decision: SKIP   # CONFIRM: my-specs/ | CUSTOM: <path> | SKIP\n",
        )
        code, _ = cl.run_confirm(self.repo_root)
        self.assertEqual(code, 0)
        self.assertIn("CONFIRMED", self.artifact_in_workspace.read_text(encoding="utf-8"))
