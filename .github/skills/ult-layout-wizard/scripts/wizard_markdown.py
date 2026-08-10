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
from typing import Callable, List, Optional, Tuple

# The project's own canonical public GitHub URL - already used verbatim in
# this repo's own README.md badges (CI badge, version badge), not a value
# invented for this module. Used only as the *fallback* destination for a
# relative doc link that render() can't resolve to an in-app doc (see
# _rewrite_link) - e.g. a case-studies/README.md link to
# references/reproducibility-guide.md, which is intentionally outside the
# wizard's doc corpus (see wizard_docs.py).
_GITHUB_BLOB_BASE = "https://github.com/linkpranay-ai/context-engineering-protocol/blob/main/"

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

# Strips everything but lowercase letters/digits/space/hyphen - the rest of
# _slugify's job (mapping spaces to hyphens) happens separately because it
# must NOT collapse runs of spaces first (see _slugify's docstring).
_SLUG_STRIP = re.compile(r"[^a-z0-9 -]")


def _slugify(text: str) -> str:
    """Approximates GitHub's own heading-anchor algorithm well enough for
    this module's real links to resolve: case-studies/README.md links to
    `../PROTOCOL.md#7-trip-wire--institutional-memory-decision-ledger-piloting`
    (heading "## 7. Trip-wire — institutional memory, decision ledger
    (piloting)") and `../README.md#measured-impact` (heading "### Measured
    impact") - both grep-confirmed against this exact algorithm: lowercase,
    strip everything that isn't a-z/0-9/space/hyphen, then map each
    individual space to a hyphen WITHOUT collapsing runs first - the em dash
    in "Trip-wire — institutional" sits between two spaces, and removing
    just the dash (not the spaces either side of it) is what produces the
    target's "wire--institutional" double hyphen. Duplicate headings within
    one doc are not de-duplicated (GitHub appends -1/-2; no doc this module
    renders today has same-level duplicate headings, so that case doesn't
    arise)."""
    return _SLUG_STRIP.sub("", text.lower()).replace(" ", "-")


def _render_link(
    text: str,
    href: str,
    doc_dir: Optional[str],
    link_resolver: Optional[Callable[[str], Optional[str]]],
) -> str:
    """Builds one `<a>` tag for a `[text](href)` match. `text` is already
    HTML-escaped (it comes from `_process_inline`'s already-`html.escape`d
    working string); `href` is the raw, un-escaped Markdown link target.

    Three cases, in order:
    1. Bare in-page anchor (`#foo`, no path) - left as an ordinary same-page
       anchor link; nothing to resolve.
    2. Already-absolute target (own scheme, or root-relative - the same
       `_ABSOLUTE_SRC` rule `_rewrite_src` uses for images) - a real,
       correct destination already, so it's left alone except for
       `target="_blank"` - without that, clicking it would navigate the
       single-page docs overlay away entirely (the wizard's exchange-token
       URLs are single-use, so there's no coming back - see render()'s
       module docstring on why this viewer is client-side-only).
    3. Relative path - resolved against `doc_dir` (the *rendering* doc's own
       install-root-relative directory, supplied by wizard_server.py, same
       role `asset_prefix` plays for images but expressed as a plain path
       instead of a URL prefix - see wizard_docs.py for how doc paths are
       tracked). If `link_resolver` (built by wizard_server.py from
       wizard_docs.list_docs(), a closed-set dict lookup - no filesystem
       access from this resolved path, matching wizard_docs.py's
       no-path-traversal-surface posture) maps the resolved path to a known
       doc_id, the link becomes an in-app navigation trigger instead of a
       real href (`href="#"` plus `data-doc-id`/`data-doc-fragment`,
       consumed by wizard.js's delegated click handler) - real hrefs can't
       work here for the same single-use-URL reason as case 2. Otherwise
       (resolver returns None - the path is a real repo file but outside
       the wizard's doc corpus, e.g. `references/reproducibility-guide.md`)
       it falls back to a real link at the project's own public GitHub URL,
       also opened in a new tab.
    """
    path, _, fragment = href.partition("#")

    if not path:
        return f'<a href="{html.escape(href, quote=True)}">{text}</a>'

    if _ABSOLUTE_SRC.match(path):
        return (
            f'<a href="{html.escape(href, quote=True)}" '
            f'target="_blank" rel="noopener">{text}</a>'
        )

    resolved = posixpath.normpath(posixpath.join(doc_dir or ".", path))
    doc_id = link_resolver(resolved) if link_resolver else None
    if doc_id:
        frag_attr = f' data-doc-fragment="{html.escape(fragment, quote=True)}"' if fragment else ""
        return (
            f'<a href="#" data-doc-id="{html.escape(doc_id, quote=True)}"'
            f'{frag_attr}>{text}</a>'
        )

    fallback_href = _GITHUB_BLOB_BASE + resolved + (f"#{fragment}" if fragment else "")
    return (
        f'<a href="{html.escape(fallback_href, quote=True)}" '
        f'target="_blank" rel="noopener">{text}</a>'
    )


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


def _process_inline(
    text: str,
    asset_prefix: Optional[str] = None,
    doc_dir: Optional[str] = None,
    link_resolver: Optional[Callable[[str], Optional[str]]] = None,
) -> str:
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
        lambda m: _render_link(m.group(1), m.group(2), doc_dir, link_resolver),
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
    lines: List[str],
    start: int,
    asset_prefix: Optional[str] = None,
    doc_dir: Optional[str] = None,
    link_resolver: Optional[Callable[[str], Optional[str]]] = None,
) -> Tuple[str, int]:
    header_cells = [c.strip() for c in lines[start].strip().strip("|").split("|")]
    i = start + 2  # skip header + separator row
    rows: List[List[str]] = []
    while i < len(lines) and "|" in lines[i] and lines[i].strip():
        rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
        i += 1

    out = ['<table>', "<thead><tr>"]
    for cell in header_cells:
        out.append(f"<th>{_process_inline(cell, asset_prefix, doc_dir, link_resolver)}</th>")
    out.append("</tr></thead><tbody>")
    for row in rows:
        out.append("<tr>")
        for cell in row:
            out.append(f"<td>{_process_inline(cell, asset_prefix, doc_dir, link_resolver)}</td>")
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out), i


def _render_list(
    lines: List[str],
    start: int,
    ordered: bool,
    asset_prefix: Optional[str] = None,
    doc_dir: Optional[str] = None,
    link_resolver: Optional[Callable[[str], Optional[str]]] = None,
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

        out.append(f"<li>{_process_inline(text, asset_prefix, doc_dir, link_resolver)}</li>")
        i += 1

    while len(stack) > 1:
        stack.pop()
        out.append(f"</{tag}>")
    out.append(f"</{tag}>")
    return "".join(out), i


def render(
    markdown_text: str,
    *,
    asset_prefix: Optional[str] = None,
    doc_dir: Optional[str] = None,
    link_resolver: Optional[Callable[[str], Optional[str]]] = None,
) -> str:
    """Converts one Markdown document to an HTML fragment (no <html>/<body>
    wrapper - callers embed this into the docs-overlay panel, matching how
    wizard_boxes.py hands back plain view-model data for wizard_server.py to
    wrap, not a full page itself).

    `asset_prefix`, when given, is prepended to every relative image src
    (Markdown `![](...)`) syntax and raw HTML `<img src="...">` alike) so it
    resolves against the *source doc's own directory* instead of the
    wizard's page URL - see _rewrite_src. None (the default) renders every
    doc exactly as it always has (every existing caller/test).

    `doc_dir` and `link_resolver` do the equivalent job for `[text](href)`
    links (see _render_link): `doc_dir` is the rendering doc's own
    install-root-relative directory (`"."` for a doc at the repo root,
    defaulted to when doc_dir is None too), used to resolve a relative link
    target the same way `asset_prefix` resolves a relative image src;
    `link_resolver` maps that resolved path to a doc_id when it's one of the
    wizard's own docs, so the link can navigate in-app instead of using a
    real href that single-use exchange-token URLs can't support. When
    `link_resolver` is None (or returns no match for a given path), the
    relative link still gets *something* real rather than a guaranteed-dead
    same-page href: a link to the resolved path at the project's own public
    GitHub URL - see `_GITHUB_BLOB_BASE`. Absolute links (own scheme, or
    root-relative) are untouched except for `target="_blank"` regardless of
    either parameter - see _render_link."""
    lines = markdown_text.replace("\r\n", "\n").split("\n")
    out: List[str] = []
    i = 0
    n = len(lines)
    paragraph_buf: List[str] = []

    def _flush_paragraph() -> None:
        if paragraph_buf:
            joined = " ".join(paragraph_buf).strip()
            if joined:
                out.append(f"<p>{_process_inline(joined, asset_prefix, doc_dir, link_resolver)}</p>")
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
            heading_text = header_match.group(2)
            slug = _slugify(heading_text)
            out.append(
                f'<h{level} id="{html.escape(slug, quote=True)}">'
                f"{_process_inline(heading_text, asset_prefix, doc_dir, link_resolver)}</h{level}>"
            )
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
            table_html, i = _render_table(lines, i, asset_prefix, doc_dir, link_resolver)
            out.append(table_html)
            continue

        if _OL_ITEM.match(line):
            _flush_paragraph()
            list_html, i = _render_list(
                lines, i, ordered=True, asset_prefix=asset_prefix,
                doc_dir=doc_dir, link_resolver=link_resolver,
            )
            out.append(list_html)
            continue

        if _UL_ITEM.match(line):
            _flush_paragraph()
            list_html, i = _render_list(
                lines, i, ordered=False, asset_prefix=asset_prefix,
                doc_dir=doc_dir, link_resolver=link_resolver,
            )
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
            inner = _process_inline(" ".join(bq_lines).strip(), asset_prefix, doc_dir, link_resolver)
            out.append(f"<blockquote><p>{inner}</p></blockquote>")
            continue

        paragraph_buf.append(line.strip())
        i += 1

    _flush_paragraph()
    return "\n".join(out)
