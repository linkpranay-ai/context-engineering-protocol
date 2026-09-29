"""Regression suite for draft_coverage.py (the ult-context-generate consumer
row's fail-closed handling of generated_by: ult-autoscaffold-content drafts
in Step 5, Step 5.5, and Step 6).

Stdlib unittest only -- no pytest dependency, so this stays vendorable along
with draft_coverage.py itself. Run with:

    python -m unittest discover -s scripts/tests -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import draft_coverage as dc  # noqa: E402


def _fm(**overrides):
    """A minimal but complete generated_by: ult-autoscaffold-content
    frontmatter dict, with per-field overrides."""
    base = {
        "generated_by": "ult-autoscaffold-content",
        "generated_at": "2026-09-28T00:00:00Z",
        "status": "draft",
        "content_mode": "grounded",
        "doc_kind": "module_context",
        "skill_version": "0.3.0",
    }
    base.update(overrides)
    return base


NOT_GENERATED = "author: a-human\n"

GROUNDED_SECTION_WITH_REPO_CITATION = (
    "Formatting is enforced by clang-format 17 [src: .clang-format#L3-L9].\n"
)

GROUNDED_SECTION_NO_CITATION = (
    "Formatting is enforced by clang-format 17, per project convention.\n"
)

GROUNDED_SECTION_CITES_ONLY_GENERATED_FILE = (
    "See the generated overview [src: cache/autoscaffold-content/overview.md#L1-L4].\n"
)

GROUNDED_SECTION_CITES_BOTH = (
    "Real: [src: .clang-format#L3]. Also see draft "
    "[src: cache/autoscaffold-content/overview.md#L1-L4].\n"
)


def _generated_path(path):
    """Fake is_generated_path: only cache/autoscaffold-content/... paths are
    themselves autoscaffold-generated; everything else is real repo content."""
    return path.startswith("cache/autoscaffold-content/")


class IsAutoscaffoldGeneratedTests(unittest.TestCase):
    def test_true_for_matching_generated_by(self):
        self.assertTrue(dc.is_autoscaffold_generated(_fm()))

    def test_false_for_other_generated_by(self):
        self.assertFalse(dc.is_autoscaffold_generated(_fm(generated_by="some-other-skill")))

    def test_false_when_absent(self):
        self.assertFalse(dc.is_autoscaffold_generated({}))


class CitationsInTests(unittest.TestCase):
    def test_single_line_citation(self):
        self.assertEqual(
            dc.citations_in("see [src: foo.md#L4]"),
            [("foo.md", 4, 4)],
        )

    def test_range_citation(self):
        self.assertEqual(
            dc.citations_in("see [src: foo.md#L4-L9]"),
            [("foo.md", 4, 9)],
        )

    def test_multiple_citations(self):
        self.assertEqual(
            dc.citations_in("[src: a.md#L1] and [src: b.md#L2-L3]"),
            [("a.md", 1, 1), ("b.md", 2, 3)],
        )

    def test_no_citations(self):
        self.assertEqual(dc.citations_in("nothing here"), [])


class HasNonGeneratedCitationTests(unittest.TestCase):
    def test_true_when_citation_is_real_repo_file(self):
        self.assertTrue(
            dc.has_non_generated_citation(GROUNDED_SECTION_WITH_REPO_CITATION, _generated_path)
        )

    def test_false_when_no_citation_at_all(self):
        self.assertFalse(
            dc.has_non_generated_citation(GROUNDED_SECTION_NO_CITATION, _generated_path)
        )

    def test_false_when_only_citation_is_itself_generated(self):
        self.assertFalse(
            dc.has_non_generated_citation(GROUNDED_SECTION_CITES_ONLY_GENERATED_FILE, _generated_path)
        )

    def test_true_when_at_least_one_of_several_citations_is_real(self):
        self.assertTrue(
            dc.has_non_generated_citation(GROUNDED_SECTION_CITES_BOTH, _generated_path)
        )


class ClassifyL2MatchTests(unittest.TestCase):
    """Proposal Sec 8, rules (a) and (b)."""

    def test_non_autoscaffold_document_falls_through(self):
        result = dc.classify_l2_match({}, GROUNDED_SECTION_WITH_REPO_CITATION, _generated_path)
        self.assertEqual(result, {"coverage": False, "reason": "not-autoscaffold"})

    def test_skeleton_mode_is_never_coverage_even_with_a_citation(self):
        fm = _fm(content_mode="skeleton")
        result = dc.classify_l2_match(fm, GROUNDED_SECTION_WITH_REPO_CITATION, _generated_path)
        self.assertEqual(result, {"coverage": False, "reason": "skeleton"})

    def test_grounded_with_no_citation_is_no_coverage(self):
        fm = _fm(content_mode="grounded")
        result = dc.classify_l2_match(fm, GROUNDED_SECTION_NO_CITATION, _generated_path)
        self.assertEqual(result, {"coverage": False, "reason": "no-non-generated-citation"})

    def test_grounded_citing_only_a_generated_file_is_no_coverage(self):
        fm = _fm(content_mode="grounded")
        result = dc.classify_l2_match(fm, GROUNDED_SECTION_CITES_ONLY_GENERATED_FILE, _generated_path)
        self.assertEqual(result, {"coverage": False, "reason": "no-non-generated-citation"})

    def test_grounded_with_a_real_citation_is_draft_coverage_inferred(self):
        fm = _fm(content_mode="grounded")
        result = dc.classify_l2_match(fm, GROUNDED_SECTION_WITH_REPO_CITATION, _generated_path)
        self.assertEqual(
            result,
            {
                "coverage": True,
                "layer": "draft_coverage",
                "confidence": "INFERRED",
                "clears_gap": False,
            },
        )

    def test_draft_coverage_never_clears_the_gap(self):
        fm = _fm(content_mode="grounded")
        result = dc.classify_l2_match(fm, GROUNDED_SECTION_WITH_REPO_CITATION, _generated_path)
        self.assertFalse(result["clears_gap"])


class CanCorroborateWhatL3Tests(unittest.TestCase):
    """Step 6 (D7) anti-circularity -- also applies on the Step 5.5
    constraints path per the same proposal row."""

    def test_autoscaffold_generated_cannot_corroborate(self):
        self.assertFalse(dc.can_corroborate_what_l3(_fm()))

    def test_non_generated_document_can_corroborate(self):
        self.assertTrue(dc.can_corroborate_what_l3({}))

    def test_still_cannot_corroborate_even_when_reviewed(self):
        # Review lifts the INFERRED cap on cited draft content (rule e), but
        # never turns a generated document into an independent source for
        # anti-circularity purposes -- it is still the same graph.
        fm = _fm(status="reviewed", reviewed_by="human:alice")
        self.assertFalse(dc.can_corroborate_what_l3(fm))


CEP_EXT_TEXT = (
    "#### Suggested practice -- external, not from this repo\n"
    '<!-- cep:ext id=EXT-1 source=model confidence=SUGGESTED -->\n'
    "*Run the formatter as a pre-commit hook.* [^EXT-1]\n"
    "<!-- /cep:ext -->\n"
)

CEP_EXT_TEXT_TWO_BLOCKS = CEP_EXT_TEXT + (
    '<!-- cep:ext id=EXT-2 source=domain_pack confidence=SUGGESTED -->\n'
    "*Second suggestion.*\n"
    "<!-- /cep:ext -->\n"
)

NO_CEP_EXT_TEXT = "Just ordinary content with [src: a.md#L1] citations.\n"


class FindCepExtBlocksTests(unittest.TestCase):
    def test_no_blocks_found(self):
        self.assertEqual(dc.find_cep_ext_blocks(NO_CEP_EXT_TEXT), [])

    def test_single_block_parsed(self):
        blocks = dc.find_cep_ext_blocks(CEP_EXT_TEXT)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["id"], "EXT-1")
        self.assertEqual(blocks[0]["source"], "model")
        self.assertEqual(blocks[0]["confidence"], "SUGGESTED")
        self.assertIn("pre-commit hook", blocks[0]["body"])

    def test_two_blocks_parsed_in_order(self):
        blocks = dc.find_cep_ext_blocks(CEP_EXT_TEXT_TWO_BLOCKS)
        self.assertEqual([b["id"] for b in blocks], ["EXT-1", "EXT-2"])


class ClassifyCepExtBlocksTests(unittest.TestCase):
    """Proposal Sec 8, rule (c)."""

    def test_excluded_by_default(self):
        result = dc.classify_cep_ext_blocks(CEP_EXT_TEXT, include_external_suggestions=False)
        self.assertEqual(len(result), 1)
        self.assertFalse(result[0]["included"])
        self.assertIsNone(result[0]["layer"])
        self.assertIsNone(result[0]["confidence"])

    def test_included_when_opted_in_gets_llm_generated_suggested(self):
        result = dc.classify_cep_ext_blocks(CEP_EXT_TEXT, include_external_suggestions=True)
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["included"])
        self.assertEqual(result[0]["layer"], "llm-generated")
        self.assertEqual(result[0]["confidence"], "SUGGESTED")

    def test_opted_in_confidence_is_always_suggested_regardless_of_marker_attribute(self):
        # The marker's own confidence= attribute is provenance metadata, not
        # a trust upgrade -- classify_cep_ext_blocks must not just echo it.
        text = CEP_EXT_TEXT.replace("confidence=SUGGESTED", "confidence=EXTRACTED")
        result = dc.classify_cep_ext_blocks(text, include_external_suggestions=True)
        self.assertEqual(result[0]["confidence"], "SUGGESTED")

    def test_no_blocks_returns_empty_list(self):
        self.assertEqual(
            dc.classify_cep_ext_blocks(NO_CEP_EXT_TEXT, include_external_suggestions=True), []
        )


class StripCepExtBlocksTests(unittest.TestCase):
    def test_block_removed_entirely(self):
        stripped = dc.strip_cep_ext_blocks(CEP_EXT_TEXT)
        self.assertNotIn("cep:ext", stripped)
        self.assertNotIn("pre-commit hook", stripped)

    def test_non_block_content_untouched(self):
        self.assertEqual(dc.strip_cep_ext_blocks(NO_CEP_EXT_TEXT), NO_CEP_EXT_TEXT)


class LiftsInferredCapTests(unittest.TestCase):
    """Proposal Sec 7 / Q8, rule (e)."""

    def test_true_with_status_reviewed_and_reviewed_by(self):
        fm = _fm(status="reviewed", reviewed_by="human:alice")
        self.assertTrue(dc.lifts_inferred_cap(fm))

    def test_false_with_status_reviewed_but_no_reviewed_by(self):
        fm = _fm(status="reviewed")
        self.assertFalse(dc.lifts_inferred_cap(fm))

    def test_false_with_reviewed_by_but_status_still_draft(self):
        fm = _fm(status="draft", reviewed_by="human:alice")
        self.assertFalse(dc.lifts_inferred_cap(fm))

    def test_false_by_default(self):
        self.assertFalse(dc.lifts_inferred_cap(_fm()))


class ClassifyL2MatchWithReviewTests(unittest.TestCase):
    """Proposal Sec 7 / Q8, rule (e): review lifts the cap for repo-cited
    content only."""

    def test_reviewed_draft_with_real_citation_is_promoted_to_extracted(self):
        fm = _fm(content_mode="grounded", status="reviewed", reviewed_by="human:alice")
        result = dc.classify_l2_match_with_review(fm, GROUNDED_SECTION_WITH_REPO_CITATION, _generated_path)
        self.assertTrue(result["coverage"])
        self.assertEqual(result["confidence"], "EXTRACTED")
        self.assertTrue(result["clears_gap"])
        self.assertTrue(result["reviewed"])

    def test_reviewed_skeleton_is_still_no_coverage(self):
        # Review cannot resurrect a skeleton match -- there is no cited
        # content to lift in the first place.
        fm = _fm(content_mode="skeleton", status="reviewed", reviewed_by="human:alice")
        result = dc.classify_l2_match_with_review(fm, GROUNDED_SECTION_WITH_REPO_CITATION, _generated_path)
        self.assertEqual(result, {"coverage": False, "reason": "skeleton"})

    def test_reviewed_but_uncited_match_is_still_no_coverage(self):
        fm = _fm(content_mode="grounded", status="reviewed", reviewed_by="human:alice")
        result = dc.classify_l2_match_with_review(fm, GROUNDED_SECTION_NO_CITATION, _generated_path)
        self.assertEqual(result, {"coverage": False, "reason": "no-non-generated-citation"})

    def test_unreviewed_draft_is_unaffected(self):
        fm = _fm(content_mode="grounded")
        result = dc.classify_l2_match_with_review(fm, GROUNDED_SECTION_WITH_REPO_CITATION, _generated_path)
        self.assertEqual(
            result,
            {
                "coverage": True,
                "layer": "draft_coverage",
                "confidence": "INFERRED",
                "clears_gap": False,
            },
        )


if __name__ == "__main__":
    unittest.main()
