"""Regression suite for layout_decision_grammar.py's resolve_section_layer().

Stdlib unittest only, same posture as test_discover_layers.py. Run with:

    python -m unittest discover -s scripts/tests -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import layout_decision_grammar as gr  # noqa: E402


class TestResolveSectionLayerCanonicalTitles(unittest.TestCase):
    def test_what_l2_title_resolves_to_what(self):
        self.assertEqual(gr.resolve_section_layer(gr.WHAT_L2_TITLE), frozenset({"what"}))

    def test_what_l1_title_resolves_to_what(self):
        self.assertEqual(gr.resolve_section_layer(gr.WHAT_L1_TITLE), frozenset({"what"}))

    def test_how_l2_title_resolves_to_how(self):
        self.assertEqual(gr.resolve_section_layer(gr.HOW_L2_TITLE), frozenset({"how"}))

    def test_how_l1_title_resolves_to_how(self):
        self.assertEqual(gr.resolve_section_layer(gr.HOW_L1_TITLE), frozenset({"how"}))

    def test_collision_title_resolves_to_both(self):
        # The exact false-negative the old `startswith("What"/"How")` check
        # missed: COLLISION_TITLE ("Cross-layer path collisions (S30)")
        # starts with neither word, so it was invisible to both branches.
        self.assertEqual(
            gr.resolve_section_layer(gr.COLLISION_TITLE), frozenset({"what", "how"})
        )

    def test_unrecognized_title_resolves_to_empty(self):
        self.assertEqual(gr.resolve_section_layer("Something Else Entirely"), frozenset())


class TestResolveSectionLayerRediscoveryTitles(unittest.TestCase):
    """discover_layers._apply_drift_tracking renders re-discovery sections as
    f"Re-discovery - {section.title} - {today}" and
    f"Re-discovery - {section.title} - candidates - {today}" - the other
    false negative the old startswith check missed, since every re-issued
    title starts with "Re-discovery", not "What"/"How"."""

    def test_rediscovery_of_what_l2_resolves_to_what(self):
        title = f"Re-discovery - {gr.WHAT_L2_TITLE} - 2026-01-01"
        self.assertEqual(gr.resolve_section_layer(title), frozenset({"what"}))

    def test_rediscovery_candidates_of_how_l2_resolves_to_how(self):
        title = f"Re-discovery - {gr.HOW_L2_TITLE} - candidates - 2026-01-01"
        self.assertEqual(gr.resolve_section_layer(title), frozenset({"how"}))

    def test_rediscovery_of_collision_title_resolves_to_both(self):
        title = f"Re-discovery - {gr.COLLISION_TITLE} - 2026-01-01"
        self.assertEqual(gr.resolve_section_layer(title), frozenset({"what", "how"}))

    def test_rediscovery_of_unrecognized_title_resolves_to_empty(self):
        title = "Re-discovery - Something Else Entirely - 2026-01-01"
        self.assertEqual(gr.resolve_section_layer(title), frozenset())

    def test_rediscovery_prefix_alone_does_not_falsely_match_a_short_title(self):
        # A canonical title that happens to be a prefix of another (none are,
        # today) must not falsely match via startswith - guards the
        # `remainder == canonical_title or remainder.startswith(canonical_title
        # + " - ")` check specifically, not just a looser `startswith`.
        title = f"Re-discovery - {gr.WHAT_L2_TITLE}extra-suffix - 2026-01-01"
        self.assertEqual(gr.resolve_section_layer(title), frozenset())


if __name__ == "__main__":
    unittest.main()
