#!/usr/bin/env python3
"""Regression suite for wizard_retrofit_draft.py (Journey 3, Phase B).

Stdlib unittest only. Calls resolve_reference()/draft_insertion_text()/
detect_contract_locations()/build_draft() directly rather than driving a real
socket - route-wiring for the five new /api/retrofit/* routes is covered
separately in test_wizard_server.py, following test_wizard_retrofit_inventory.py's
own precedent on why only test_wizard_server.py needs the real-bound-socket
treatment.

Real-fixture-copy convention (matches test_wizard_retrofit_inventory.py /
test_wizard_decision_staging.py): the real cep_retrofit.py is copied into a temp
dir shaped like .github/skills/ult-cep-retrofit/scripts/ so build_draft()'s
dynamic import exercises the actual script, not a stand-in. Fixture skill/target
names are always fabricated placeholders ("widget-reviewer", "second-widget"),
never a real skill name.
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
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


class RetrofitDraftTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


class TestResolveReferenceSameRepo(RetrofitDraftTestCase):
    def test_resolves_a_relative_path_between_unit_dir_and_contract(self):
        ref = wrd.resolve_reference(
            str(self.root),
            "libs/widget-reviewer",
            "CONSUMING-CONTEXT-PACKAGE.md",
            "same-repo",
            same_repo_contract_rel_path="context-engineering/CONSUMING-CONTEXT-PACKAGE.md",
        )
        self.assertEqual(ref, "../../context-engineering/CONSUMING-CONTEXT-PACKAGE.md")

    def test_unit_dir_at_repo_root_resolves_without_traversal(self):
        ref = wrd.resolve_reference(
            str(self.root),
            ".",
            "CONSUMING-CONTEXT-PACKAGE.md",
            "same-repo",
            same_repo_contract_rel_path="context-engineering/CONSUMING-CONTEXT-PACKAGE.md",
        )
        self.assertEqual(ref, "context-engineering/CONSUMING-CONTEXT-PACKAGE.md")

    def test_missing_rel_path_is_a_retrofit_draft_error(self):
        with self.assertRaises(wrd.RetrofitDraftError) as ctx:
            wrd.resolve_reference(
                str(self.root), "libs/widget-reviewer", "CONSUMING-CONTEXT-PACKAGE.md",
                "same-repo",
            )
        self.assertIn("same_repo_contract_rel_path", str(ctx.exception))

    def test_containment_violation_on_contract_path_is_a_retrofit_draft_error(self):
        with self.assertRaises(wrd.RetrofitDraftError):
            wrd.resolve_reference(
                str(self.root), "libs/widget-reviewer", "CONSUMING-CONTEXT-PACKAGE.md",
                "same-repo", same_repo_contract_rel_path="../escaped/CONSUMING-CONTEXT-PACKAGE.md",
            )

    def test_containment_violation_on_unit_dir_is_a_retrofit_draft_error(self):
        with self.assertRaises(wrd.RetrofitDraftError):
            wrd.resolve_reference(
                str(self.root), "../escaped", "CONSUMING-CONTEXT-PACKAGE.md",
                "same-repo", same_repo_contract_rel_path="context-engineering/CONSUMING-CONTEXT-PACKAGE.md",
            )


class TestResolveReferencePlugin(RetrofitDraftTestCase):
    def test_valid_plugin_qualifier_passes_through(self):
        ref = wrd.resolve_reference(
            str(self.root), "libs/widget-reviewer", "CONSUMING-CODE-GRAPH.md",
            "plugin", plugin_qualifier="/context-engineering-oss:ult-cep-wizard",
        )
        self.assertEqual(ref, "/context-engineering-oss:ult-cep-wizard's CONSUMING-CODE-GRAPH.md")

    def test_missing_qualifier_is_a_retrofit_draft_error(self):
        with self.assertRaises(wrd.RetrofitDraftError) as ctx:
            wrd.resolve_reference(
                str(self.root), "libs/widget-reviewer", "CONSUMING-CODE-GRAPH.md", "plugin",
            )
        self.assertIn("plugin_qualifier", str(ctx.exception))

    def test_malformed_qualifier_is_a_retrofit_draft_error(self):
        with self.assertRaises(wrd.RetrofitDraftError) as ctx:
            wrd.resolve_reference(
                str(self.root), "libs/widget-reviewer", "CONSUMING-CODE-GRAPH.md", "plugin",
                plugin_qualifier="not-plugin-qualified",
            )
        self.assertIn("does not look like a plugin-qualified reference", str(ctx.exception))


class TestResolveReferenceMode(RetrofitDraftTestCase):
    def test_unknown_mode_is_a_retrofit_draft_error(self):
        with self.assertRaises(wrd.RetrofitDraftError) as ctx:
            wrd.resolve_reference(
                str(self.root), "libs/widget-reviewer", "CONSUMING-CODE-GRAPH.md", "bogus-mode",
            )
        self.assertIn("unknown reference mode", str(ctx.exception))

    def test_unknown_contract_is_a_retrofit_draft_error(self):
        with self.assertRaises(wrd.RetrofitDraftError):
            wrd.resolve_reference(
                str(self.root), ".", "NOT-A-REAL-CONTRACT.md", "same-repo",
                same_repo_contract_rel_path="whatever.md",
            )


class TestDraftInsertionText(unittest.TestCase):
    def test_sentences_are_emitted_in_fixed_contract_order_regardless_of_input_order(self):
        text = wrd.draft_insertion_text(
            ["CONSUMING-CODE-GRAPH.md", "CONSUMING-CONTEXT-PACKAGE.md"],
            {
                "CONSUMING-CODE-GRAPH.md": "../CONSUMING-CODE-GRAPH.md",
                "CONSUMING-CONTEXT-PACKAGE.md": "../CONSUMING-CONTEXT-PACKAGE.md",
            },
        )
        package_idx = text.index("CONSUMING-CONTEXT-PACKAGE.md")
        graph_idx = text.index("CONSUMING-CODE-GRAPH.md")
        self.assertLess(package_idx, graph_idx)

    def test_single_contract_renders_its_template_with_the_resolved_ref(self):
        text = wrd.draft_insertion_text(
            ["CONSUMING-COMPILED-GUIDELINES.md"],
            {"CONSUMING-COMPILED-GUIDELINES.md": "../CONSUMING-COMPILED-GUIDELINES.md"},
        )
        self.assertIn("../CONSUMING-COMPILED-GUIDELINES.md", text)
        self.assertIn("compiled project guidelines", text)

    def test_unknown_contract_is_a_retrofit_draft_error(self):
        with self.assertRaises(wrd.RetrofitDraftError):
            wrd.draft_insertion_text(["NOT-A-REAL-CONTRACT.md"], {"NOT-A-REAL-CONTRACT.md": "x"})

    def test_missing_reference_is_a_retrofit_draft_error(self):
        with self.assertRaises(wrd.RetrofitDraftError) as ctx:
            wrd.draft_insertion_text(["CONSUMING-CONTEXT-PACKAGE.md"], {})
        self.assertIn("no resolved reference for", str(ctx.exception))


class TestDetectContractLocations(RetrofitDraftTestCase):
    def test_finds_each_contract_once_and_reports_missing_as_none(self):
        _write(
            self.root / "context-engineering" / "CONSUMING-CONTEXT-PACKAGE.md",
            "content\n",
        )
        found = wrd.detect_contract_locations(str(self.root))
        self.assertEqual(
            found["CONSUMING-CONTEXT-PACKAGE.md"],
            "context-engineering/CONSUMING-CONTEXT-PACKAGE.md",
        )
        self.assertIsNone(found["CONSUMING-COMPILED-GUIDELINES.md"])
        self.assertIsNone(found["CONSUMING-CODE-GRAPH.md"])

    def test_stops_early_once_all_three_are_found(self):
        for name in wrd.CONTRACT_ORDER:
            _write(self.root / "docs" / name, "content\n")
        found = wrd.detect_contract_locations(str(self.root))
        for name in wrd.CONTRACT_ORDER:
            self.assertEqual(found[name], f"docs/{name}")


class TestBuildDraftMissingInstall(RetrofitDraftTestCase):
    def test_missing_ult_cep_retrofit_is_a_clear_error(self):
        _write(self.root / "widget-reviewer" / "SKILL.md", "# Widget Reviewer\n")
        with self.assertRaises(wrd.RetrofitDraftError) as ctx:
            wrd.build_draft(
                str(self.root), "widget-reviewer/SKILL.md", "widget-reviewer",
                ["CONSUMING-CONTEXT-PACKAGE.md"], "same-repo",
                {"CONSUMING-CONTEXT-PACKAGE.md": "context-engineering/CONSUMING-CONTEXT-PACKAGE.md"},
            )
        self.assertIn("ult-cep-retrofit", str(ctx.exception))


class TestBuildDraftIdempotency(RetrofitDraftTestCase):
    def setUp(self):
        super().setUp()
        _install_ult_cep_retrofit(self.root)

    def test_all_contracts_already_present_short_circuits_without_insertion_point(self):
        _write(
            self.root / "widget-reviewer" / "SKILL.md",
            "# Widget Reviewer\n\nSee `CONSUMING-CONTEXT-PACKAGE.md` for details. "
            "**Context-availability policy: `ask`** — if no approved matching "
            "package is found, follow `CONSUMING-CONTEXT-PACKAGE.md`'s "
            "\"Context-availability policy\" callout for the `ask` branch before "
            "proceeding with the work.\n",
        )
        result = wrd.build_draft(
            str(self.root), "widget-reviewer/SKILL.md", "widget-reviewer",
            ["CONSUMING-CONTEXT-PACKAGE.md"], "same-repo",
            {"CONSUMING-CONTEXT-PACKAGE.md": "context-engineering/CONSUMING-CONTEXT-PACKAGE.md"},
        )
        self.assertTrue(result.all_satisfied)
        self.assertEqual(result.contracts_included, [])
        self.assertEqual(result.contracts_skipped_idempotent, ["CONSUMING-CONTEXT-PACKAGE.md"])
        self.assertIsNone(result.insertion_point)
        self.assertEqual(result.draft_text, "")
        self.assertEqual(result.context_before, "")
        self.assertEqual(result.context_after, "")
        self.assertIsNotNone(result.target_file_hash)
        # The embedded policy line matches the requested (default "ask") policy,
        # so this is genuinely satisfied, not drifted - the 2026-08-31 Round-2
        # evaluation's finding on policy drift going undetected.
        self.assertFalse(result.policy_drifted)

    def test_partial_overlap_drafts_only_the_remaining_contracts(self):
        _write(
            self.root / "widget-reviewer" / "SKILL.md",
            "# Widget Reviewer\n\nSee `CONSUMING-CONTEXT-PACKAGE.md` for details.\n\n"
            "## See Also\n\nSome other doc.\n",
        )
        result = wrd.build_draft(
            str(self.root), "widget-reviewer/SKILL.md", "widget-reviewer",
            ["CONSUMING-CONTEXT-PACKAGE.md", "CONSUMING-CODE-GRAPH.md"], "same-repo",
            {
                "CONSUMING-CONTEXT-PACKAGE.md": "context-engineering/CONSUMING-CONTEXT-PACKAGE.md",
                "CONSUMING-CODE-GRAPH.md": "context-engineering/CONSUMING-CODE-GRAPH.md",
            },
        )
        self.assertFalse(result.all_satisfied)
        self.assertEqual(result.contracts_included, ["CONSUMING-CODE-GRAPH.md"])
        self.assertEqual(result.contracts_skipped_idempotent, ["CONSUMING-CONTEXT-PACKAGE.md"])
        self.assertEqual(result.insertion_point["method"], "see-also")
        self.assertIn("CONSUMING-CODE-GRAPH.md", result.draft_text)
        self.assertNotIn("CONSUMING-CONTEXT-PACKAGE.md", result.draft_text)


class TestBuildDraftContextAvailability(RetrofitDraftTestCase):
    """the 2026-08-31 Round-2 evaluation's finding on context-availability policy handling during retrofit drafting."""

    def setUp(self):
        super().setUp()
        _install_ult_cep_retrofit(self.root)
        _write(
            self.root / "widget-reviewer" / "SKILL.md",
            "# Widget Reviewer\n\nSome intro.\n",
        )

    def _build(self, **overrides):
        kwargs = dict(
            repo_root=str(self.root),
            primary_file_rel_path="widget-reviewer/SKILL.md",
            unit_dir_rel_path="widget-reviewer",
            contracts=["CONSUMING-CONTEXT-PACKAGE.md"],
            reference_mode="same-repo",
            reference_args={
                "CONSUMING-CONTEXT-PACKAGE.md": "context-engineering/CONSUMING-CONTEXT-PACKAGE.md"
            },
        )
        kwargs.update(overrides)
        return wrd.build_draft(**kwargs)

    def test_default_policy_is_ask_and_echoed_on_the_result(self):
        result = self._build()
        self.assertEqual(result.context_availability, "ask")
        self.assertIn("Context-availability policy: `ask`", result.draft_text)

    def test_explicit_policy_is_threaded_through_to_draft_text_and_result(self):
        result = self._build(context_availability="required")
        self.assertEqual(result.context_availability, "required")
        self.assertIn("Context-availability policy: `required`", result.draft_text)

    def test_unknown_policy_is_a_retrofit_draft_error(self):
        with self.assertRaises(wrd.RetrofitDraftError):
            self._build(context_availability="sometimes")

    def test_policy_is_echoed_even_when_all_contracts_already_satisfied(self):
        _write(
            self.root / "widget-reviewer" / "SKILL.md",
            "# Widget Reviewer\n\nSee `CONSUMING-CONTEXT-PACKAGE.md` for details.\n",
        )
        result = self._build(context_availability="optional")
        self.assertTrue(result.all_satisfied)
        self.assertEqual(result.context_availability, "optional")

    def test_drifted_policy_on_already_present_contract_still_produces_a_draft(self):
        # The 2026-08-31 Round-2 evaluation's finding on policy drift going
        # undetected on already-retrofitted units: this unit was retrofitted
        # under the "ask" policy (embedded in its own text); the project has
        # since reconfigured to "required". cr.check_pointer only sees the
        # contract filename is present and would otherwise report
        # all_satisfied=True with nothing further to review.
        _write(
            self.root / "widget-reviewer" / "SKILL.md",
            "# Widget Reviewer\n\nSee `CONSUMING-CONTEXT-PACKAGE.md` for details. "
            "**Context-availability policy: `ask`** — if no approved matching "
            "package is found, follow `CONSUMING-CONTEXT-PACKAGE.md`'s "
            "\"Context-availability policy\" callout for the `ask` branch before "
            "proceeding with the work.\n",
        )
        result = self._build(context_availability="required")
        self.assertFalse(result.all_satisfied)
        self.assertTrue(result.policy_drifted)
        self.assertEqual(result.contracts_included, [])
        self.assertEqual(result.contracts_skipped_idempotent, ["CONSUMING-CONTEXT-PACKAGE.md"])
        self.assertIsNone(result.insertion_point)
        # Policy-line replacement only - not a full contract re-insertion, and
        # the old policy value must not survive anywhere in the draft.
        self.assertIn("Context-availability policy: `required`", result.draft_text)
        self.assertIn("the `required` branch", result.draft_text)
        self.assertNotIn("`ask`", result.draft_text)

    def test_matching_policy_on_already_present_contract_is_not_drifted(self):
        _write(
            self.root / "widget-reviewer" / "SKILL.md",
            "# Widget Reviewer\n\nSee `CONSUMING-CONTEXT-PACKAGE.md` for details. "
            "**Context-availability policy: `required`** — if no approved matching "
            "package is found, follow `CONSUMING-CONTEXT-PACKAGE.md`'s "
            "\"Context-availability policy\" callout for the `required` branch "
            "before proceeding with the work.\n",
        )
        result = self._build(context_availability="required")
        self.assertTrue(result.all_satisfied)
        self.assertFalse(result.policy_drifted)
        self.assertEqual(result.draft_text, "")


class TestDraftInsertionTextContextAvailability(unittest.TestCase):
    """the 2026-08-31 Round-2 evaluation's finding on context-availability policy handling during retrofit drafting."""

    def test_default_policy_is_ask_when_not_specified(self):
        text = wrd.draft_insertion_text(
            ["CONSUMING-CONTEXT-PACKAGE.md"],
            {"CONSUMING-CONTEXT-PACKAGE.md": "../CONSUMING-CONTEXT-PACKAGE.md"},
        )
        self.assertIn("Context-availability policy: `ask`", text)

    def test_explicit_policy_is_rendered_into_the_sentence(self):
        text = wrd.draft_insertion_text(
            ["CONSUMING-CONTEXT-PACKAGE.md"],
            {"CONSUMING-CONTEXT-PACKAGE.md": "../CONSUMING-CONTEXT-PACKAGE.md"},
            context_availability="required",
        )
        self.assertIn("Context-availability policy: `required`", text)

    def test_policy_placeholder_is_silently_ignored_by_contracts_that_dont_use_it(self):
        text = wrd.draft_insertion_text(
            ["CONSUMING-CODE-GRAPH.md"],
            {"CONSUMING-CODE-GRAPH.md": "../CONSUMING-CODE-GRAPH.md"},
            context_availability="optional",
        )
        self.assertNotIn("Context-availability policy", text)

    def test_unknown_policy_is_a_retrofit_draft_error(self):
        with self.assertRaises(wrd.RetrofitDraftError) as ctx:
            wrd.draft_insertion_text(
                ["CONSUMING-CONTEXT-PACKAGE.md"],
                {"CONSUMING-CONTEXT-PACKAGE.md": "../CONSUMING-CONTEXT-PACKAGE.md"},
                context_availability="sometimes",
            )
        self.assertIn("unknown context_availability", str(ctx.exception))


class TestBuildDraftContext(RetrofitDraftTestCase):
    def setUp(self):
        super().setUp()
        _install_ult_cep_retrofit(self.root)

    def test_context_before_and_after_bracket_the_insertion_line(self):
        _write(
            self.root / "widget-reviewer" / "SKILL.md",
            "# Widget Reviewer\n\nline one\nline two\nline three\n\n"
            "## See Also\n\nfollow one\nfollow two\nfollow three\n",
        )
        result = wrd.build_draft(
            str(self.root), "widget-reviewer/SKILL.md", "widget-reviewer",
            ["CONSUMING-CONTEXT-PACKAGE.md"], "same-repo",
            {"CONSUMING-CONTEXT-PACKAGE.md": "context-engineering/CONSUMING-CONTEXT-PACKAGE.md"},
        )
        self.assertEqual(result.insertion_point["method"], "see-also")
        # insertion_point["line"] splices right after the "## See Also" heading
        # line itself (cep_retrofit's i + 1), so the heading is the last line of
        # context_before, not the content above it.
        self.assertIn("line three", result.context_before)
        self.assertIn("## See Also", result.context_before)
        self.assertIn("follow one", result.context_after)

    def test_prepend_insertion_point_has_empty_context_before(self):
        _write(self.root / "widget-reviewer" / "SKILL.md", "just a paragraph, no headings\n")
        result = wrd.build_draft(
            str(self.root), "widget-reviewer/SKILL.md", "widget-reviewer",
            ["CONSUMING-CONTEXT-PACKAGE.md"], "same-repo",
            {"CONSUMING-CONTEXT-PACKAGE.md": "context-engineering/CONSUMING-CONTEXT-PACKAGE.md"},
        )
        self.assertEqual(result.insertion_point["method"], "prepend")
        self.assertEqual(result.context_before, "")
        self.assertIn("just a paragraph", result.context_after)


class TestBuildDraftValidation(RetrofitDraftTestCase):
    def setUp(self):
        super().setUp()
        _install_ult_cep_retrofit(self.root)

    def test_containment_violation_on_primary_file_is_a_retrofit_draft_error(self):
        with self.assertRaises(wrd.RetrofitDraftError):
            wrd.build_draft(
                str(self.root), "../escaped/SKILL.md", ".", ["CONSUMING-CONTEXT-PACKAGE.md"],
                "same-repo", {"CONSUMING-CONTEXT-PACKAGE.md": "x.md"},
            )

    def test_non_file_primary_target_is_a_retrofit_draft_error(self):
        (self.root / "widget-reviewer").mkdir(parents=True)
        with self.assertRaises(wrd.RetrofitDraftError) as ctx:
            wrd.build_draft(
                str(self.root), "widget-reviewer", "widget-reviewer",
                ["CONSUMING-CONTEXT-PACKAGE.md"], "same-repo",
                {"CONSUMING-CONTEXT-PACKAGE.md": "x.md"},
            )
        self.assertIn("is not a file", str(ctx.exception))

    def test_unknown_reference_mode_is_a_retrofit_draft_error(self):
        _write(self.root / "widget-reviewer" / "SKILL.md", "# Widget Reviewer\n")
        with self.assertRaises(wrd.RetrofitDraftError):
            wrd.build_draft(
                str(self.root), "widget-reviewer/SKILL.md", "widget-reviewer",
                ["CONSUMING-CONTEXT-PACKAGE.md"], "bogus-mode",
                {"CONSUMING-CONTEXT-PACKAGE.md": "x.md"},
            )


class TestResolveReferenceContainmentRoot(RetrofitDraftTestCase):
    """the 2026-08-31 Round-2 evaluation's finding on external (out-of-repo) retrofit-target containment - `containment_root` is the
    root `unit_dir_rel_path` is actually relative to when it differs from
    repo_root (an external retrofit target). same-repo mode must be refused
    outright whenever containment_root is genuinely external - a relative
    path between a contract doc under repo_root and a unit dir under an
    unrelated root is either meaningless or an unsafe cross-boundary escape."""

    def setUp(self):
        super().setUp()
        self._ext_tmp = tempfile.TemporaryDirectory()
        self.external_root = Path(self._ext_tmp.name)

    def tearDown(self):
        self._ext_tmp.cleanup()
        super().tearDown()

    def test_same_repo_mode_is_refused_for_an_external_containment_root(self):
        with self.assertRaises(wrd.RetrofitDraftError) as ctx:
            wrd.resolve_reference(
                str(self.root), "libs/widget-reviewer", "CONSUMING-CONTEXT-PACKAGE.md",
                "same-repo",
                same_repo_contract_rel_path="context-engineering/CONSUMING-CONTEXT-PACKAGE.md",
                containment_root=str(self.external_root),
            )
        self.assertIn("external", str(ctx.exception))

    def test_plugin_mode_is_unaffected_by_an_external_containment_root(self):
        ref = wrd.resolve_reference(
            str(self.root), "libs/widget-reviewer", "CONSUMING-CODE-GRAPH.md",
            "plugin", plugin_qualifier="/context-engineering-oss:ult-cep-wizard",
            containment_root=str(self.external_root),
        )
        self.assertEqual(ref, "/context-engineering-oss:ult-cep-wizard's CONSUMING-CODE-GRAPH.md")

    def test_same_repo_mode_still_works_when_containment_root_equals_repo_root(self):
        # containment_root == repo_root is the "in-repo unit, field just
        # happens to be populated" case - must behave identically to
        # containment_root=None (the default), not be treated as external.
        ref = wrd.resolve_reference(
            str(self.root), "libs/widget-reviewer", "CONSUMING-CONTEXT-PACKAGE.md",
            "same-repo",
            same_repo_contract_rel_path="context-engineering/CONSUMING-CONTEXT-PACKAGE.md",
            containment_root=str(self.root),
        )
        self.assertEqual(ref, "../../context-engineering/CONSUMING-CONTEXT-PACKAGE.md")

    def test_containment_root_none_is_the_unchanged_in_repo_default(self):
        ref = wrd.resolve_reference(
            str(self.root), "libs/widget-reviewer", "CONSUMING-CONTEXT-PACKAGE.md",
            "same-repo",
            same_repo_contract_rel_path="context-engineering/CONSUMING-CONTEXT-PACKAGE.md",
            containment_root=None,
        )
        self.assertEqual(ref, "../../context-engineering/CONSUMING-CONTEXT-PACKAGE.md")


class TestBuildDraftContainmentRoot(RetrofitDraftTestCase):
    def setUp(self):
        super().setUp()
        self._ext_tmp = tempfile.TemporaryDirectory()
        self.external_root = Path(self._ext_tmp.name)
        _install_ult_cep_retrofit(self.root)

    def tearDown(self):
        self._ext_tmp.cleanup()
        super().tearDown()

    def test_build_draft_checks_containment_against_containment_root(self):
        _write(self.external_root / "widget-reviewer" / "SKILL.md", "# Widget Reviewer\n")
        # Not present under self.root (repo_root) at all - if build_draft
        # still checked containment against repo_root, this would fail
        # closed instead of succeeding.
        result = wrd.build_draft(
            str(self.root), "widget-reviewer/SKILL.md", "widget-reviewer",
            ["CONSUMING-CODE-GRAPH.md"], "plugin",
            {"CONSUMING-CODE-GRAPH.md": "/context-engineering-oss:ult-cep-wizard"},
            containment_root=str(self.external_root),
        )
        self.assertFalse(result.all_satisfied)

    def test_build_draft_refuses_same_repo_mode_for_an_external_containment_root(self):
        _write(self.external_root / "widget-reviewer" / "SKILL.md", "# Widget Reviewer\n")
        with self.assertRaises(wrd.RetrofitDraftError):
            wrd.build_draft(
                str(self.root), "widget-reviewer/SKILL.md", "widget-reviewer",
                ["CONSUMING-CONTEXT-PACKAGE.md"], "same-repo",
                {"CONSUMING-CONTEXT-PACKAGE.md": "context-engineering/CONSUMING-CONTEXT-PACKAGE.md"},
                containment_root=str(self.external_root),
            )

    def test_cep_retrofit_engine_is_still_imported_from_repo_root_not_containment_root(self):
        # No ult-cep-retrofit installed under external_root at all - if
        # build_draft tried to import the engine from containment_root
        # instead of repo_root, this would raise a "not installed"
        # RetrofitDraftError instead of succeeding.
        _write(self.external_root / "widget-reviewer" / "SKILL.md", "# Widget Reviewer\n")
        result = wrd.build_draft(
            str(self.root), "widget-reviewer/SKILL.md", "widget-reviewer",
            ["CONSUMING-CODE-GRAPH.md"], "plugin",
            {"CONSUMING-CODE-GRAPH.md": "/context-engineering-oss:ult-cep-wizard"},
            containment_root=str(self.external_root),
        )
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
