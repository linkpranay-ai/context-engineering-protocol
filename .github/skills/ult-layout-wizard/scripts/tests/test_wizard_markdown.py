"""Regression suite for wizard_markdown.py (UI design pass). Stdlib unittest
only. Run with:

    python -m unittest discover -s scripts/tests -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wizard_markdown as wm  # noqa: E402


class TestHeaders(unittest.TestCase):
    def test_h1_through_h3(self):
        self.assertEqual(wm.render("# One"), "<h1>One</h1>")
        self.assertEqual(wm.render("## Two"), "<h2>Two</h2>")
        self.assertEqual(wm.render("### Three"), "<h3>Three</h3>")

    def test_header_strips_trailing_hashes(self):
        self.assertEqual(wm.render("## Title ##"), "<h2>Title</h2>")


class TestParagraphsAndInline(unittest.TestCase):
    def test_simple_paragraph(self):
        self.assertEqual(wm.render("hello world"), "<p>hello world</p>")

    def test_consecutive_lines_join_one_paragraph(self):
        self.assertEqual(wm.render("line one\nline two"), "<p>line one line two</p>")

    def test_blank_line_separates_paragraphs(self):
        self.assertEqual(
            wm.render("first\n\nsecond"), "<p>first</p>\n<p>second</p>"
        )

    def test_bold_and_italic(self):
        self.assertEqual(wm.render("**bold** and *italic*"), "<p><strong>bold</strong> and <em>italic</em></p>")

    def test_inline_code_not_further_processed(self):
        self.assertEqual(wm.render("`**not bold**`"), "<p><code>**not bold**</code></p>")

    def test_link(self):
        self.assertEqual(
            wm.render("[CEP](https://example.com)"),
            '<p><a href="https://example.com">CEP</a></p>',
        )

    def test_raw_angle_brackets_escaped(self):
        self.assertEqual(wm.render("a <placeholder> here"), "<p>a &lt;placeholder&gt; here</p>")

    def test_ampersand_escaped(self):
        self.assertEqual(wm.render("What & How"), "<p>What &amp; How</p>")


class TestCodeFences(unittest.TestCase):
    def test_fenced_code_block_no_language(self):
        self.assertEqual(
            wm.render("```\nplain(text)\n```"),
            "<pre><code>plain(text)</code></pre>",
        )

    def test_fenced_code_block_with_language(self):
        self.assertEqual(
            wm.render("```yaml\ncase: foo\n```"),
            '<pre><code class="language-yaml">case: foo</code></pre>',
        )

    def test_fenced_code_block_content_not_interpreted_as_markdown(self):
        result = wm.render("```\n# not a header\n**not bold**\n```")
        self.assertIn("# not a header", result)
        self.assertIn("**not bold**", result)
        self.assertNotIn("<h1>", result)
        self.assertNotIn("<strong>", result)


class TestLists(unittest.TestCase):
    def test_unordered_list(self):
        self.assertEqual(
            wm.render("- one\n- two"), "<ul><li>one</li><li>two</li></ul>"
        )

    def test_ordered_list(self):
        self.assertEqual(
            wm.render("1. one\n2. two"), "<ol><li>one</li><li>two</li></ol>"
        )


class TestBlockquote(unittest.TestCase):
    def test_blockquote(self):
        self.assertEqual(
            wm.render("> quoted text"), "<blockquote><p>quoted text</p></blockquote>"
        )


class TestHorizontalRule(unittest.TestCase):
    def test_hr(self):
        self.assertEqual(wm.render("---"), "<hr>")


class TestTables(unittest.TestCase):
    def test_simple_table(self):
        result = wm.render("| A | B |\n|---|---|\n| 1 | 2 |")
        self.assertIn("<table>", result)
        self.assertIn("<th>A</th>", result)
        self.assertIn("<th>B</th>", result)
        self.assertIn("<td>1</td>", result)
        self.assertIn("<td>2</td>", result)

    def test_table_cell_supports_inline_bold(self):
        result = wm.render("| A |\n|---|\n| **bold** |")
        self.assertIn("<td><strong>bold</strong></td>", result)


class TestImages(unittest.TestCase):
    def test_image_syntax(self):
        self.assertEqual(
            wm.render("![CEP logo](./assets/hero.svg)"),
            '<p><img src="./assets/hero.svg" alt="CEP logo"></p>',
        )

    def test_image_does_not_leave_stray_bang_or_become_a_link(self):
        result = wm.render("![CI](https://example.com/ci.svg)")
        self.assertNotIn("!<img", result)
        self.assertNotIn("<a href", result)

    def test_image_adjacent_to_link_both_render(self):
        result = wm.render(
            "![badge](https://example.com/badge.svg) "
            "[docs](https://example.com/docs)"
        )
        self.assertIn('<img src="https://example.com/badge.svg" alt="badge">', result)
        self.assertIn('<a href="https://example.com/docs">docs</a>', result)


class TestRawHtmlBlocks(unittest.TestCase):
    def test_html_block_passthrough_unescaped(self):
        text = '<p align="center">\n  <img src="./hero.svg" alt="hero">\n</p>'
        result = wm.render(text)
        self.assertEqual(result, text)

    def test_html_block_terminates_on_blank_line(self):
        text = '<p align="center">raw</p>\n\nafter, a **real** paragraph'
        result = wm.render(text)
        self.assertIn('<p align="center">raw</p>', result)
        self.assertIn("<p>after, a <strong>real</strong> paragraph</p>", result)

    def test_ordinary_paragraph_with_angle_bracket_still_escaped(self):
        # Guards against the HTML-block rule over-firing: a stray `<` that
        # isn't a real tag opener (no matching structure) must still take
        # the ordinary escaped-paragraph path, not raw passthrough.
        self.assertEqual(wm.render("a <placeholder> here"), "<p>a &lt;placeholder&gt; here</p>")


class TestRealDocFixture(unittest.TestCase):
    def test_representative_case_study_snippet_renders_without_crashing(self):
        text = (
            "# Case Study: Example\n\n"
            "```yaml\n"
            "case: example\n"
            "codebase: some/repo\n"
            "```\n\n"
            "## Summary\n\n"
            "This uses **CEP** and `graphify` together.\n\n"
            "| Layer | Status |\n"
            "|---|---|\n"
            "| What-L2 | Implemented |\n"
        )
        result = wm.render(text)
        # render() has no knowledge of the "Case Study:" title-prefix
        # convention - that stripping happens one layer up, in
        # wizard_docs._case_study_title(). The renderer just renders the H1
        # as written.
        self.assertIn("<h1>Case Study: Example</h1>", result)
        self.assertIn("<h2>Summary</h2>", result)
        self.assertIn("<table>", result)
        self.assertIn("<code>graphify</code>", result)


if __name__ == "__main__":
    unittest.main()
