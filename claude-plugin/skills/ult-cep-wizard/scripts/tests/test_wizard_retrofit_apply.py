#!/usr/bin/env python3
"""Regression suite for wizard_retrofit_apply.py (Journey 3, Phase C).

Stdlib unittest only. Calls apply_unit()/apply_batch() directly rather than
driving a real socket - route-wiring for POST /api/retrofit/apply is covered
separately in test_wizard_server.py, following test_wizard_retrofit_draft.py's
own precedent on why only test_wizard_server.py needs the real-bound-socket
treatment.

Most fixtures here are produced by actually calling
wizard_retrofit_draft.build_draft() first, exactly as the real select -> draft
-> apply flow would, rather than hand-constructing draft_text/insertion_point -
this exercises apply_unit() against the same shapes the real write path
produces. A few tests (the last-instant idempotency guard, the partial-overlap
guard) hand-construct an ApplyUnitInput directly, since those branches require
file state that isn't reachable via the normal flow (see
wizard_retrofit_apply.py's own module docstring for why) - they're still
worth covering in isolation as defense-in-depth.

Real-fixture-copy convention (matches test_wizard_retrofit_draft.py /
test_wizard_retrofit_inventory.py): the real cep_retrofit.py is copied into a
temp dir shaped like .github/skills/ult-cep-retrofit/scripts/ so apply_unit()'s
dynamic import exercises the actual script, not a stand-in. Fixture skill/
target names are always fabricated placeholders ("widget-reviewer",
"second-widget"), never a real skill name.
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wizard_content_hash as wch  # noqa: E402
import wizard_retrofit_apply as wra  # noqa: E402
import wizard_retrofit_draft as wrd  # noqa: E402


def _find_real_repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        marker = (
            candidate
            / ".github"
            / "skills"
            / "ult-cep-retrofit"
            / "scripts"
            / "cep_retrofit.py"
        )
        if marker.exists():
            return candidate
    raise RuntimeError(
        "could not locate context-engineering-oss repo root from this test "
        "file's location"
    )


REAL_REPO_ROOT = _find_real_repo_root()
REAL_CEP_RETROFIT_SCRIPT = (
    REAL_REPO_ROOT / ".github" / "skills" / "ult-cep-retrofit" / "scripts" / "cep_retrofit.py"
)


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _install_ult_cep_retrofit(repo_root: Path) -> None:
    scripts_dir = repo_root / ".github" / "skills" / "ult-cep-retrofit" / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(REAL_CEP_RETROFIT_SCRIPT, scripts_dir / "cep_retrofit.py")


REFERENCE_ARGS = {
    "CONSUMING-CONTEXT-PACKAGE.md": "context-engineering/CONSUMING-CONTEXT-PACKAGE.md",
    "CONSUMING-CODE-GRAPH.md": "context-engineering/CONSUMING-CODE-GRAPH.md",
}


class RetrofitApplyTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _install_ult_cep_retrofit(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _draft(self, primary_file_rel_path, unit_dir_rel_path, contracts, unit_id="unit-1"):
        result = wrd.build_draft(
            str(self.root), primary_file_rel_path, unit_dir_rel_path, contracts,
            "same-repo", REFERENCE_ARGS,
        )
        return wra.ApplyUnitInput(
            unit_id=unit_id,
            primary_file=primary_file_rel_path,
            insertion_point=result.insertion_point,
            draft_text=result.draft_text,
            contracts_included=result.contracts_included,
            target_file_hash=result.target_file_hash,
        )


class TestApplyUnitSuccess(RetrofitApplyTestCase):
    def test_splices_the_drafted_block_and_writes_atomically(self):
        target = self.root / "widget-reviewer" / "SKILL.md"
        _write(target, "# Widget Reviewer\n\n## See Also\n\nSome other doc.\n")
        unit_input = self._draft("widget-reviewer/SKILL.md", "widget-reviewer", ["CONSUMING-CONTEXT-PACKAGE.md"])

        result = wra.apply_unit(str(self.root), unit_input)

        self.assertEqual(result.status, "applied")
        self.assertEqual(result.reason, "")
        self.assertEqual(result.contracts_applied, ["CONSUMING-CONTEXT-PACKAGE.md"])
        self.assertIsNotNone(result.target_file_hash_after)

        new_text = target.read_text(encoding="utf-8")
        self.assertIn("CONSUMING-CONTEXT-PACKAGE.md", new_text)
        self.assertIn("Some other doc.", new_text)  # original content preserved
        self.assertEqual(wch.hash_file(target), result.target_file_hash_after)

    def test_preserves_trailing_newline_when_original_has_one(self):
        target = self.root / "widget-reviewer" / "SKILL.md"
        _write(target, "just a paragraph, no headings\n")
        unit_input = self._draft("widget-reviewer/SKILL.md", "widget-reviewer", ["CONSUMING-CONTEXT-PACKAGE.md"])

        wra.apply_unit(str(self.root), unit_input)

        self.assertTrue(target.read_text(encoding="utf-8").endswith("\n"))

    def test_does_not_add_a_trailing_newline_when_original_has_none(self):
        target = self.root / "widget-reviewer" / "SKILL.md"
        _write(target, "just a paragraph, no headings")  # no trailing \n
        unit_input = self._draft("widget-reviewer/SKILL.md", "widget-reviewer", ["CONSUMING-CONTEXT-PACKAGE.md"])

        wra.apply_unit(str(self.root), unit_input)

        self.assertFalse(target.read_text(encoding="utf-8").endswith("\n"))

    def test_multiple_contracts_combine_into_one_insertion(self):
        target = self.root / "widget-reviewer" / "SKILL.md"
        _write(target, "# Widget Reviewer\n\n## See Also\n\nSome other doc.\n")
        unit_input = self._draft(
            "widget-reviewer/SKILL.md", "widget-reviewer",
            ["CONSUMING-CONTEXT-PACKAGE.md", "CONSUMING-CODE-GRAPH.md"],
        )

        result = wra.apply_unit(str(self.root), unit_input)

        self.assertEqual(result.status, "applied")
        self.assertCountEqual(
            result.contracts_applied,
            ["CONSUMING-CONTEXT-PACKAGE.md", "CONSUMING-CODE-GRAPH.md"],
        )
        new_text = target.read_text(encoding="utf-8")
        self.assertIn("CONSUMING-CONTEXT-PACKAGE.md", new_text)
        self.assertIn("CONSUMING-CODE-GRAPH.md", new_text)


class TestApplyUnitNothingStaged(RetrofitApplyTestCase):
    def test_empty_draft_text_is_skipped_idempotent_without_touching_disk(self):
        target = self.root / "widget-reviewer" / "SKILL.md"
        _write(target, "# Widget Reviewer\n")
        before = target.read_text(encoding="utf-8")

        unit_input = wra.ApplyUnitInput(
            unit_id="unit-1", primary_file="widget-reviewer/SKILL.md",
            insertion_point=None, draft_text="", contracts_included=[],
            target_file_hash=None,
        )
        result = wra.apply_unit(str(self.root), unit_input)

        self.assertEqual(result.status, "skipped_idempotent")
        self.assertEqual(target.read_text(encoding="utf-8"), before)


class TestApplyUnitStaleFile(RetrofitApplyTestCase):
    def test_file_changed_since_draft_fails_that_unit_with_a_clear_reason(self):
        target = self.root / "widget-reviewer" / "SKILL.md"
        _write(target, "# Widget Reviewer\n\n## See Also\n\nSome other doc.\n")
        unit_input = self._draft("widget-reviewer/SKILL.md", "widget-reviewer", ["CONSUMING-CONTEXT-PACKAGE.md"])

        # Someone/something else edits the file after the draft was computed.
        _write(target, "# Widget Reviewer (edited)\n\n## See Also\n\nSome other doc.\n")

        result = wra.apply_unit(str(self.root), unit_input)

        self.assertEqual(result.status, "failed")
        self.assertIn("changed since", result.reason)
        # nothing was written on top of the concurrent edit
        self.assertIn("(edited)", target.read_text(encoding="utf-8"))


class TestApplyUnitLastInstantGuard(RetrofitApplyTestCase):
    def test_all_contracts_already_present_skips_without_duplicate_insertion(self):
        target = self.root / "widget-reviewer" / "SKILL.md"
        _write(
            target,
            "# Widget Reviewer\n\nSee `CONSUMING-CONTEXT-PACKAGE.md` for details.\n",
        )
        before_hash = wch.hash_file(target)
        before_text = target.read_text(encoding="utf-8")

        # Hand-constructed: as if a draft had been computed for this exact
        # (now-already-satisfied) content - only reachable in the real flow
        # as a resubmit after a prior successful apply; constructed directly
        # here to unit test the guard itself. See module docstring.
        unit_input = wra.ApplyUnitInput(
            unit_id="unit-1", primary_file="widget-reviewer/SKILL.md",
            insertion_point={"method": "prepend", "line": 0},
            draft_text="If compiled project guidelines exist, see `...`.",
            contracts_included=["CONSUMING-CONTEXT-PACKAGE.md"],
            target_file_hash=before_hash,
        )
        result = wra.apply_unit(str(self.root), unit_input)

        self.assertEqual(result.status, "skipped_idempotent")
        self.assertEqual(result.contracts_skipped_idempotent, ["CONSUMING-CONTEXT-PACKAGE.md"])
        self.assertEqual(target.read_text(encoding="utf-8"), before_text)  # untouched

    def test_partial_overlap_fails_closed_rather_than_re_slice(self):
        target = self.root / "widget-reviewer" / "SKILL.md"
        _write(
            target,
            "# Widget Reviewer\n\nSee `CONSUMING-CONTEXT-PACKAGE.md` for details.\n",
        )
        before_hash = wch.hash_file(target)
        before_text = target.read_text(encoding="utf-8")

        unit_input = wra.ApplyUnitInput(
            unit_id="unit-1", primary_file="widget-reviewer/SKILL.md",
            insertion_point={"method": "prepend", "line": 0},
            draft_text="combined block covering both contracts",
            contracts_included=["CONSUMING-CONTEXT-PACKAGE.md", "CONSUMING-CODE-GRAPH.md"],
            target_file_hash=before_hash,
        )
        result = wra.apply_unit(str(self.root), unit_input)

        self.assertEqual(result.status, "failed")
        self.assertIn("some but not all", result.reason)
        self.assertEqual(target.read_text(encoding="utf-8"), before_text)  # untouched


class TestApplyUnitValidation(RetrofitApplyTestCase):
    def test_missing_primary_file_is_failed(self):
        unit_input = wra.ApplyUnitInput(
            unit_id="unit-1", primary_file=None, insertion_point={"method": "prepend", "line": 0},
            draft_text="something", contracts_included=["CONSUMING-CONTEXT-PACKAGE.md"],
            target_file_hash=None,
        )
        result = wra.apply_unit(str(self.root), unit_input)
        self.assertEqual(result.status, "failed")
        self.assertIn("primary_file", result.reason)

    def test_missing_insertion_point_is_failed(self):
        unit_input = wra.ApplyUnitInput(
            unit_id="unit-1", primary_file="widget-reviewer/SKILL.md", insertion_point=None,
            draft_text="something", contracts_included=["CONSUMING-CONTEXT-PACKAGE.md"],
            target_file_hash=None,
        )
        result = wra.apply_unit(str(self.root), unit_input)
        self.assertEqual(result.status, "failed")
        self.assertIn("insertion point", result.reason)

    def test_containment_violation_is_failed(self):
        unit_input = wra.ApplyUnitInput(
            unit_id="unit-1", primary_file="../outside/SKILL.md",
            insertion_point={"method": "prepend", "line": 0}, draft_text="something",
            contracts_included=["CONSUMING-CONTEXT-PACKAGE.md"], target_file_hash=None,
        )
        result = wra.apply_unit(str(self.root), unit_input)
        self.assertEqual(result.status, "failed")

    def test_non_file_target_is_failed(self):
        (self.root / "widget-reviewer").mkdir(parents=True)
        unit_input = wra.ApplyUnitInput(
            unit_id="unit-1", primary_file="widget-reviewer",
            insertion_point={"method": "prepend", "line": 0}, draft_text="something",
            contracts_included=["CONSUMING-CONTEXT-PACKAGE.md"], target_file_hash=None,
        )
        result = wra.apply_unit(str(self.root), unit_input)
        self.assertEqual(result.status, "failed")
        self.assertIn("is not a file", result.reason)


class TestApplyBatch(RetrofitApplyTestCase):
    def test_zero_overlap_two_units_different_files_both_succeed_independently(self):
        target_a = self.root / "widget-reviewer" / "SKILL.md"
        target_b = self.root / "second-widget" / "SKILL.md"
        _write(target_a, "# Widget Reviewer\n\n## See Also\n\nSome doc.\n")
        _write(target_b, "# Second Widget\n\n## See Also\n\nAnother doc.\n")

        input_a = self._draft("widget-reviewer/SKILL.md", "widget-reviewer", ["CONSUMING-CONTEXT-PACKAGE.md"], "unit-a")
        input_b = self._draft("second-widget/SKILL.md", "second-widget", ["CONSUMING-CODE-GRAPH.md"], "unit-b")

        results = wra.apply_batch(str(self.root), [input_a, input_b])

        by_id = {r.unit_id: r for r in results}
        self.assertEqual(by_id["unit-a"].status, "applied")
        self.assertEqual(by_id["unit-b"].status, "applied")
        self.assertIn("CONSUMING-CONTEXT-PACKAGE.md", target_a.read_text(encoding="utf-8"))
        self.assertNotIn("CONSUMING-CODE-GRAPH.md", target_a.read_text(encoding="utf-8"))
        self.assertIn("CONSUMING-CODE-GRAPH.md", target_b.read_text(encoding="utf-8"))
        self.assertNotIn("CONSUMING-CONTEXT-PACKAGE.md", target_b.read_text(encoding="utf-8"))

    def test_partial_batch_failure_one_write_failing_does_not_abort_siblings(self):
        target_a = self.root / "widget-reviewer" / "SKILL.md"
        target_b = self.root / "second-widget" / "SKILL.md"
        _write(target_a, "# Widget Reviewer\n\n## See Also\n\nSome doc.\n")
        _write(target_b, "# Second Widget\n\n## See Also\n\nAnother doc.\n")

        input_a = self._draft("widget-reviewer/SKILL.md", "widget-reviewer", ["CONSUMING-CONTEXT-PACKAGE.md"], "unit-a")
        input_b = self._draft("second-widget/SKILL.md", "second-widget", ["CONSUMING-CODE-GRAPH.md"], "unit-b")

        real_write = wra.waw.write_text_atomic

        def flaky_write(target_path, content, encoding="utf-8"):
            if "widget-reviewer" in str(target_path):
                raise wra.waw.AtomicWriteError("simulated disk failure")
            return real_write(target_path, content, encoding=encoding)

        with patch.object(wra.waw, "write_text_atomic", side_effect=flaky_write):
            results = wra.apply_batch(str(self.root), [input_a, input_b])

        by_id = {r.unit_id: r for r in results}
        self.assertEqual(by_id["unit-a"].status, "failed")
        self.assertIn("simulated disk failure", by_id["unit-a"].reason)
        self.assertEqual(by_id["unit-b"].status, "applied")
        self.assertIn("CONSUMING-CODE-GRAPH.md", target_b.read_text(encoding="utf-8"))
        # the failed unit's file is untouched
        self.assertNotIn("CONSUMING-CONTEXT-PACKAGE.md", target_a.read_text(encoding="utf-8"))

    def test_idempotent_reapply_after_state_reset_does_not_duplicate(self):
        target = self.root / "widget-reviewer" / "SKILL.md"
        _write(target, "# Widget Reviewer\n\n## See Also\n\nSome doc.\n")
        unit_input = self._draft("widget-reviewer/SKILL.md", "widget-reviewer", ["CONSUMING-CONTEXT-PACKAGE.md"])

        first = wra.apply_unit(str(self.root), unit_input)
        self.assertEqual(first.status, "applied")
        once_text = target.read_text(encoding="utf-8")

        # Mirrors what the wizard_server.py route handler does after a
        # successful apply: reset draft_text/insertion_point/contracts to
        # the "nothing left to insert" shape before persisting state.
        reapply_input = wra.ApplyUnitInput(
            unit_id=unit_input.unit_id, primary_file=unit_input.primary_file,
            insertion_point=None, draft_text="", contracts_included=[],
            target_file_hash=first.target_file_hash_after,
        )
        second = wra.apply_unit(str(self.root), reapply_input)

        self.assertEqual(second.status, "skipped_idempotent")
        self.assertEqual(target.read_text(encoding="utf-8"), once_text)  # unchanged, no duplicate

    def test_unexpected_exception_in_one_unit_is_isolated(self):
        target = self.root / "widget-reviewer" / "SKILL.md"
        _write(target, "# Widget Reviewer\n\n## See Also\n\nSome doc.\n")
        input_a = self._draft("widget-reviewer/SKILL.md", "widget-reviewer", ["CONSUMING-CONTEXT-PACKAGE.md"], "unit-a")

        target_b = self.root / "second-widget" / "SKILL.md"
        _write(target_b, "# Second Widget\n\n## See Also\n\nAnother doc.\n")
        input_b = self._draft("second-widget/SKILL.md", "second-widget", ["CONSUMING-CODE-GRAPH.md"], "unit-b")

        real_apply_unit = wra.apply_unit

        def flaky_apply_unit(repo_root, unit_input):
            if unit_input.unit_id == "unit-a":
                raise RuntimeError("boom")
            return real_apply_unit(repo_root, unit_input)

        with patch.object(wra, "apply_unit", side_effect=flaky_apply_unit):
            results = wra.apply_batch(str(self.root), [input_a, input_b])

        by_id = {r.unit_id: r for r in results}
        self.assertEqual(by_id["unit-a"].status, "failed")
        self.assertIn("unexpected error", by_id["unit-a"].reason)
        self.assertEqual(by_id["unit-b"].status, "applied")


if __name__ == "__main__":
    unittest.main()
