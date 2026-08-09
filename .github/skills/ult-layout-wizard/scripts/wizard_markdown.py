#!/usr/bin/env python3
"""wizard_markdown.py - hand-rolled, stdlib-only Markdown -> HTML renderer for
ult-layout-wizard's in-app docs viewer (D24 UI design pass).

Stdlib-only is a deliberate choice, not an oversight: the project has no
`requirements.txt`/`pyproject.toml` anywhere and `wizard_server.py`'s own
import block is stdlib-plus-sibling-modules only (see that file's module
docstring). Adding a `markdown` package dependency just for this one feature
would break that stance for the whole project, so this module implements the
specific subset of Markdown that `PROTOCOL.md`, `README.md`, and the
`case-studies/*/CASE-STUDY.md` files actually use (grep-confirmed, not
guessed): ATX headers, fenced code blocks (incl. language-tagged ```yaml```
fences), ordered/unordered lists (one level of indent-based nesting),
blockquotes, pipe tables, horizontal rules, inline bold/italic/code/links/
images, and raw HTML blocks (README.md's centered hero image + CI/License/
Version badge row - confirmed via screenshot review that these need to render,
not show up as literal markup text). It is not a general CommonMark
implementation and does not try to be.

All source documents are repo-controlled files, not request-time user input
(see wizard_docs.py's module docstring on the closed-set doc-ID model) - the
same trust level `wizard_server.py`'s STATIC_ASSETS already assumes for
wizard.css/wizard.js. Raw text is still HTML-escaped before any tag is
emitted (see _process_inline), so a literal `<`/`>`/`&` in prose (e.g. a
`<path>` placeholder) renders as text rather than being parsed as markup -
that is a correctness measure for stray angle brackets, not a defense against
adversarial input.
"""

from __future__ import annotations

import html
import posixpath
import re
from typing import List, Optional, Tuple

_ATX_HEADER = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE_START = re.compile(r"^```\s*([\w+-]*)\s*$")
_FENCE_END = re.compile(r"^```\s*$")
_HR = re.compile(r"^(?:-{3,}|\*{3,}|_{3,})\s*$")
_UL_ITEM = re.compile(r"^(\s*)[-*]\s+(.*)$")
_OL_ITEM = re.compile(r"^(\s*)\d+\.\s+(.*)$")
_BLOCKQUOTE = re.compile(r"^\s*>\s?(.*)$")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$")

_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")
_ITALIC = re.compile(r"(\*|_)(?=\S)(.+?)(?<=\S)\1")
_LINK = re.compile(r'\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)')
_IMAGE = re.compile(r'!\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)')

# A line-starts-a-raw-HTML-block rule (render()'s doc-level loop), narrowly
# scoped to what README.md's own preamble actually needs: a centered hero
# <img> and a CI/License/Version badge row, both wrapped in bare <p> tags -
# the same trust model as everything else in this module (repo-controlled
# files only, see module docstring), so passthrough is fine rather than
# needing a real HTML block-type grammar (CommonMark's is much larger).
_HTML_BLOCK_START = re.compile(r"^\s*(?:</?[a-zA-Z][\w-]*(?:\s[^>]*)?/?>|<!--)")

# Anything with its own scheme (http:, https:, data:, ...), a root-relative
# path, or an in-page anchor is left exactly as written - only a bare
# relative path like `./assets/hero.svg` needs resolving against the doc's
# own directory before it means anything to a browser (see _rewrite_src).
_ABSOLUTE_SRC = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|/|#)")


# Matches a quoted `src="..."` attribute inside a raw HTML block line (e.g.
# README.md's hero `<img src="./assets/readme/hero.svg" ...>`) - raw blocks
# are passed through byte-for-byte otherwise (see the _HTML_BLOCK_START
# branch in render()), so this is the one place they still need touching:
# same relative-path problem as Markdown image syntax, different syntax.
_HTML_SRC_ATTR = re.compile(r'(\bsrc=")([^"]*)(")')


def _rewrite_html_line_srcs(line: str, asset_prefix: Optional[str]) -> str:
    if not asset_prefix:
        return line
    return _HTML_SRC_ATTR.sub(
        lambda m: m.group(1)
        + html.escape(_rewrite_src(m.group(2), asset_prefix), quote=True)
        + m.group(3),
        line,
    )


def _rewrite_src(src: str, asset_prefix: Optional[str]) -> str:
    """Resolves a Markdown image's relative `src` against the rendering doc's
    own directory, so `README.md`'s `./assets/readme/hero.svg` (written
    relative to the doc's location in the repo) still points at the right
    file once served from the wizard's own page URL instead of the repo
    directly - without this, every relative image is a guaranteed broken-image
    icon (confirmed via screenshot review). `asset_prefix` is supplied by
    `wizard_server.py` per doc (see its module docstring); None (the default)
    leaves every src untouched, which is what the unit tests exercise since
    they call render() without a serving context."""
    if not asset_prefix or _ABSOLUTE_SRC.match(src):
        return src
    return posixpath.normpath(posixpath.join(asset_prefix, src))


def _process_inline(text: str, asset_prefix: Optional[str] = None) -> str:
    """Escapes raw text then re-introduces the small inline-markup subset this
    module supports. Order matters: code spans are pulled out first (and
    protected behind placeholders) so `**`/`_`/`[` characters inside them are
    never mistaken for bold/italic/link syntax, matching how every real
    Markdown renderer treats code spans as opaque."""
    code_spans: List[str] = []

    def _stash_code(match: "re.Match[str]") -> str:
        code_spans.append(html.escape(match.group(1), quote=False))
        return f"\x00CODE{len(code_spans) - 1}\x00"

    protected = _INLINE_CODE.sub(_stash_code, text)
    escaped = html.escape(protected, quote=False)

    # Images before links: image syntax is `![...](...)`) - a link match
    # alone would consume the `[...](...)`) tail and leave a stray `!`
    # sitting next to the resulting <a>, so images must claim their `!...`
    # span first.
    escaped = _IMAGE.sub(
        lambda m: (
            f'<img src="{html.escape(_rewrite_src(m.group(2), asset_prefix), quote=True)}" '
            f'alt="{html.escape(m.group(1), quote=True)}">'
        ),
        escaped,
    )
    escaped = _LINK.sub(
        lambda m: (
            f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>'
        ),
        escaped,
    )
    escaped = _BOLD.sub(lambda m: f"<strong>{m.group(2)}</strong>", escaped)
    escaped = _ITALIC.sub(lambda m: f"<em>{m.group(2)}</em>", escaped)

    def _restore_code(match: "re.Match[str]") -> str:
        return f"<code>{code_spans[int(match.group(1))]}</code>"

    return re.sub(r"\x00CODE(\d+)\x00", _restore_code, escaped)


def _indent_level(leading_spaces: str) -> int:
    # Two spaces per nesting level, matching the modest nesting depth actually
    # used in these docs - not a full tab-aware CommonMark indent parser.
    return len(leading_spaces) // 2


def _render_table(
    lines: List[str], start: int, asset_prefix: Optional[str] = None
) -> Tuple[str, int]:
    header_cells = [c.strip() for c in lines[start].strip().strip("|").split("|")]
    i = start + 2  # skip header + separator row
    rows: List[List[str]] = []
    while i < len(lines) and "|" in lines[i] and lines[i].strip():
        rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
        i += 1

    out = ['<table>', "<thead><tr>"]
    for cell in header_cells:
        out.append(f"<th>{_process_inline(cell, asset_prefix)}</th>")
    out.append("</tr></thead><tbody>")
    for row in rows:
        out.append("<tr>")
        for cell in row:
            out.append(f"<td>{_process_inline(cell, asset_prefix)}</td>")
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out), i


def _render_list(
    lines: List[str], start: int, ordered: bool, asset_prefix: Optional[str] = None
) -> Tuple[str, int]:
    item_re = _OL_ITEM if ordered else _UL_ITEM
    tag = "ol" if ordered else "ul"
    stack: List[Tuple[int, str]] = [(0, tag)]  # (indent_level, tag) currently open
    out = [f"<{tag}>"]
    i = start
    while i < len(lines):
        real_match = item_re.match(lines[i])
        if not real_match:
            break
        level = _indent_level(real_match.group(1))
        text = real_match.group(2)

        while level > stack[-1][0]:
            out.append(f"<{tag}>")
            stack.append((level, tag))
        while level < stack[-1][0]:
            stack.pop()
            out.append(f"</{tag}>")

        out.append(f"<li>{_process_inline(text, asset_prefix)}</li>")
        i += 1

    while len(stack) > 1:
        stack.pop()
        out.append(f"</{tag}>")
    out.append(f"</{tag}>")
    return "".join(out), i


def render(markdown_text: str, *, asset_prefix: Optional[str] = None) -> str:
    """Converts one Markdown document to an HTML fragment (no <html>/<body>
    wrapper - callers embed this into the docs-overlay panel, matching how
    wizard_boxes.py hands back plain view-model data for wizard_server.py to
    wrap, not a full page itself).

    `asset_prefix`, when given, is prepended to every relative image src
    (Markdown `![](...)`) syntax and raw HTML `<img src="...">` alike) so it
    resolves against the *source doc's own directory* instead of the
    wizard's page URL - see _rewrite_src. None (the default) renders every
    doc exactly as it always has (every existing caller/test)."""
    lines = markdown_text.replace("\r\n", "\n").split("\n")
    out: List[str] = []
    i = 0
    n = len(lines)
    paragraph_buf: List[str] = []

    def _flush_paragraph() -> None:
        if paragraph_buf:
            joined = " ".join(paragraph_buf).strip()
            if joined:
                out.append(f"<p>{_process_inline(joined, asset_prefix)}</p>")
            paragraph_buf.clear()

    while i < n:
        line = lines[i]

        if not line.strip():
            _flush_paragraph()
            i += 1
            continue

        if _HTML_BLOCK_START.match(line):
            # Raw passthrough, no escaping/inline processing - this is the
            # module's one deliberate "trust the source" exception (see
            # module docstring), needed for README.md's centered hero image
            # and CI/License/Version badge row, both bare-<p>-wrapped HTML
            # rather than Markdown. Bounded to "until the next blank line",
            # matching CommonMark's own Type 7 HTML block termination rule -
            # good enough for the handful of real blocks this renderer
            # actually needs to support.
            _flush_paragraph()
            html_lines: List[str] = [_rewrite_html_line_srcs(line, asset_prefix)]
            i += 1
            while i < n and lines[i].strip():
                html_lines.append(_rewrite_html_line_srcs(lines[i], asset_prefix))
                i += 1
            out.append("\n".join(html_lines))
            continue

        fence_match = _FENCE_START.match(line)
        if fence_match:
            _flush_paragraph()
            lang = fence_match.group(1)
            code_lines: List[str] = []
            i += 1
            while i < n and not _FENCE_END.match(lines[i]):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing fence
            css_class = f' class="language-{html.escape(lang)}"' if lang else ""
            body = html.escape("\n".join(code_lines), quote=False)
            out.append(f"<pre><code{css_class}>{body}</code></pre>")
            continue

        header_match = _ATX_HEADER.match(line)
        if header_match:
            _flush_paragraph()
            level = len(header_match.group(1))
            out.append(f"<h{level}>{_process_inline(header_match.group(2), asset_prefix)}</h{level}>")
            i += 1
            continue

        if _HR.match(line):
            _flush_paragraph()
            out.append("<hr>")
            i += 1
            continue

        if (
            "|" in line
            and i + 1 < n
            and _TABLE_SEPARATOR.match(lines[i + 1])
            and "|" in lines[i + 1]
        ):
            _flush_paragraph()
            table_html, i = _render_table(lines, i, asset_prefix)
            out.append(table_html)
            continue

        if _OL_ITEM.match(line):
            _flush_paragraph()
            list_html, i = _render_list(lines, i, ordered=True, asset_prefix=asset_prefix)
            out.append(list_html)
            continue

        if _UL_ITEM.match(line):
            _flush_paragraph()
            list_html, i = _render_list(lines, i, ordered=False, asset_prefix=asset_prefix)
            out.append(list_html)
            continue

        bq_match = _BLOCKQUOTE.match(line)
        if bq_match:
            _flush_paragraph()
            bq_lines = [bq_match.group(1)]
            i += 1
            while i < n:
                m = _BLOCKQUOTE.match(lines[i])
                if not m:
                    break
                bq_lines.append(m.group(1))
                i += 1
            inner = _process_inline(" ".join(bq_lines).strip(), asset_prefix)
            out.append(f"<blockquote><p>{inner}</p></blockquote>")
            continue

        paragraph_buf.append(line.strip())
        i += 1

    _flush_paragraph()
    return "\n".join(out)
