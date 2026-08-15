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
        # Every heading now carries a GitHub-style anchor id (see _slugify) -
        # so in-app links to `#some-heading` (case-studies/README.md's links
        # into PROTOCOL.md/README.md) have a real element to scroll to.
        self.assertEqual(wm.render("# One"), '<h1 id="one">One</h1>')
        self.assertEqual(wm.render("## Two"), '<h2 id="two">Two</h2>')
        self.assertEqual(wm.render("### Three"), '<h3 id="three">Three</h3>')

    def test_header_strips_trailing_hashes(self):
        self.assertEqual(wm.render("## Title ##"), '<h2 id="title">Title</h2>')

    def test_heading_anchor_slug_matches_real_repo_links(self):
        # Grep-confirmed against this exact repo: case-studies/README.md
        # links to `../PROTOCOL.md#7-trip-wire--institutional-memory-decision-
        # ledger-piloting` for this exact heading text, and
        # `../README.md#measured-impact` for "### Measured impact". The em
        # dash sits between two spaces, and only the dash character is
        # stripped (not either space) - that's what produces the double
        # hyphen in "wire--institutional".
        result = wm.render(
            "## 7. Trip-wire — institutional memory, decision ledger (piloting)"
        )
        self.assertIn(
            'id="7-trip-wire--institutional-memory-decision-ledger-piloting"',
            result,
        )
        self.assertIn('id="measured-impact"', wm.render("### Measured impact"))


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
        # target="_blank" is deliberate: an absolute link left to navigate in
        # the same tab would take a single-use /exchange URL with it - see
        # _render_link's docstring, case 2.
        self.assertEqual(
            wm.render("[CEP](https://example.com)"),
            '<p><a href="https://example.com" target="_blank" rel="noopener">CEP</a></p>',
        )

    def test_bare_anchor_link_untouched(self):
        self.assertEqual(
            wm.render("[jump](#section)"),
            '<p><a href="#section">jump</a></p>',
        )

    def test_relative_link_resolves_via_link_resolver(self):
        resolver = {"case-studies/textual/CASE-STUDY.md": "case-study-textual"}.get
        result = wm.render(
            "[Textual](textual/CASE-STUDY.md)",
            doc_dir="case-studies",
            link_resolver=resolver,
        )
        self.assertEqual(
            result,
            '<p><a href="#" data-doc-id="case-study-textual">Textual</a></p>',
        )

    def test_relative_link_with_fragment_carries_data_doc_fragment(self):
        resolver = {"README.md": "readme"}.get
        result = wm.render(
            "[Impact](../README.md#measured-impact)",
            doc_dir="case-studies",
            link_resolver=resolver,
        )
        self.assertEqual(
            result,
            '<p><a href="#" data-doc-id="readme" data-doc-fragment="measured-impact">Impact</a></p>',
        )

    def test_relative_link_unresolved_falls_back_to_github(self):
        # link_resolver returning None (path is a real repo file, just
        # outside the wizard's doc corpus) still gets a real, working link -
        # never a dead same-page href.
        result = wm.render(
            "[Guide](../references/reproducibility-guide.md)",
            doc_dir="case-studies",
            link_resolver=lambda _resolved: None,
        )
        self.assertEqual(
            result,
            '<p><a href="https://github.com/linkpranay-ai/context-engineering-protocol/'
            'blob/main/references/reproducibility-guide.md" target="_blank" '
            'rel="noopener">Guide</a></p>',
        )

    def test_relative_link_with_no_resolver_falls_back_to_github(self):
        # link_resolver=None (the default, matching every pre-existing caller
        # and test) behaves the same as a resolver that never matches.
        result = wm.render("[Guide](references/reproducibility-guide.md)")
        self.assertIn(
            'href="https://github.com/linkpranay-ai/context-engineering-protocol/'
            'blob/main/references/reproducibility-guide.md"',
            result,
        )
        self.assertIn('target="_blank"', result)

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

    def test_ordered_list_item_with_indented_continuation_line(self):
        # Regression for PROTOCOL.md's "1. The problem this protocol
        # addresses" section: a 3-item list where each item wraps onto an
        # indented continuation line (real convention used throughout
        # PROTOCOL.md/README.md/every CASE-STUDY.md) used to break the list
        # after item 1 - the continuation line didn't match _OL_ITEM, so
        # _render_list returned early and the caller started a *new* <ol>
        # for item 2, then another for item 3, each restarting the browser's
        # auto-numbering at "1." (found via screenshot review of the
        # rendered docs viewer: "1. / 1. / 1." instead of "1. / 2. / 3.").
        result = wm.render(
            "1. one\n   still one\n2. two\n   still two\n3. three"
        )
        self.assertEqual(
            result,
            "<ol><li>one still one</li><li>two still two</li><li>three</li></ol>",
        )

    def test_unordered_list_item_with_indented_continuation_line(self):
        result = wm.render("- one\n  still one\n- two")
        self.assertEqual(
            result, "<ul><li>one still one</li><li>two</li></ul>"
        )

    def test_ordered_list_continuation_line_supports_inline_markup(self):
        result = wm.render("1. **bold** start\n   plain *italic* end")
        self.assertEqual(
            result,
            "<ol><li><strong>bold</strong> start plain <em>italic</em> end</li></ol>",
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

    def test_table_cell_with_escaped_pipe_does_not_split_column(self):
        # Regression for PROTOCOL.md's Constraints row: a code span containing
        # `\|`-escaped literal pipes (`constraint_class: compliance \| convention
        # \| scheduling`) must render as ONE cell with real `|` characters, not
        # get split into extra cells that shift every later column over.
        result = wm.render(
            "| A | B |\n"
            "|---|---|\n"
            "| `x \\| y \\| z` | second |"
        )
        self.assertIn("<td><code>x | y | z</code></td>", result)
        self.assertIn("<td>second</td>", result)
        # Exactly one header row (thead) + one body row (tbody) - if the
        # escaped pipes were still splitting cells, the body row would carry
        # extra <td>s instead of a second <tr>, so this also guards the bug.
        self.assertEqual(result.count("<tr>"), 2)
        self.assertEqual(result.count("<td>"), 2)


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
        self.assertIn(
            '<a href="https://example.com/docs" target="_blank" rel="noopener">docs</a>',
            result,
        )


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
        self.assertIn('<h1 id="case-study-example">Case Study: Example</h1>', result)
        self.assertIn('<h2 id="summary">Summary</h2>', result)
        self.assertIn("<table>", result)
        self.assertIn("<code>graphify</code>", result)


if __name__ == "__main__":
    unittest.main()
