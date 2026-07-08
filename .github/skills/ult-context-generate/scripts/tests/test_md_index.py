"""Regression suite for md_index.py (R2).

Stdlib unittest only -- no pytest dependency, so this stays vendorable along
with md_index.py itself. Run with:

    python -m unittest discover -s scripts/tests -v

Each fixture in fixtures/*.md targets one of the edge cases the original
agent-simulated D13/D14 mechanism never had a regression test for (see
ADVERSARIAL-REVIEW-OSS-AND-MD-MINING.md, finding H2 / recommendation R2).

The two real validation files (TS 33.401, session-management.md) are too
large/external to vendor as fixtures; `golden_session_management.md` is a
verbatim copy of the small NIST excerpt and is checked against a full
parse_file() snapshot, which is fully deterministic (content-hash based, no
machine-dependent fields) and therefore safe to commit.
"""

import contextlib
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import md_index as mi  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def parse(fixture_name, profile_name):
    profile = mi.load_profile(profile_name)
    return mi.parse_file(FIXTURES / fixture_name, FIXTURES, profile)


def heading_by_clause(entry, clause_id):
    for h in entry["headings"]:
        if h["clause_id"] == clause_id:
            return h
    raise AssertionError("no heading with clause_id={!r}".format(clause_id))


def xrefs_by_target(heading, target_clause):
    return [c for c in heading["cross_refs"] if c["target_clause"] == target_clause]


class TestMixedAtxSetext(unittest.TestCase):
    """TS 33.401 shape: ATX subclauses nested under Setext top-level clauses,
    plus a Setext 'Contents' heading that must be TOC-suppressed."""

    def setUp(self):
        self.entry = parse("mixed_atx_setext.md", "generic")

    def test_heading_count_and_styles(self):
        h = self.entry["headings"]
        self.assertEqual(len(h), 6)
        self.assertEqual([x["style"] for x in h],
                         ["setext", "setext", "atx", "setext", "atx", "atx"])

    def test_contents_heading_is_toc_suppressed(self):
        toc = self.entry["headings"][0]
        self.assertEqual(toc["title"], "Contents")
        self.assertIsNone(toc["clause_id"])
        self.assertTrue(toc["is_toc"])

    def test_atx_subclause_under_setext_clause(self):
        scope = heading_by_clause(self.entry, "1")
        sub = heading_by_clause(self.entry, "1.1")
        self.assertEqual(sub["style"], "atx")
        self.assertEqual(sub["level"], 4)
        # Parent's section_bounds spans the child's heading line and body
        # (same-or-higher-level walk: the ATX H4 does not close the Setext H1).
        self.assertLessEqual(scope["section_bounds"][0], sub["line"])
        self.assertGreaterEqual(scope["section_bounds"][1], sub["section_bounds"][1])

    def test_cross_ref_resolves_across_style_switch(self):
        overview = heading_by_clause(self.entry, "2.1")
        refs = xrefs_by_target(overview, "2.2")
        self.assertEqual(len(refs), 1)
        self.assertTrue(refs[0]["resolved"])
        self.assertEqual(refs[0]["resolved_heading_id"],
                         heading_by_clause(self.entry, "2.2")["id"])


class TestFrontMatterAndCodeFences(unittest.TestCase):
    """YAML front matter + a fenced code block containing '# not a heading',
    '---' and '|---|---|' -- none of which may be detected as structure."""

    def setUp(self):
        self.entry = parse("front_matter_and_code_fences.md", "generic")

    def test_front_matter_detected_and_masked(self):
        self.assertEqual(self.entry["front_matter_lines"], [1, 4])

    def test_only_real_headings_detected(self):
        titles = [h["title"] for h in self.entry["headings"]]
        self.assertEqual(titles, ["1 Introduction", "1.1 Details"])
        clauses = [h["clause_id"] for h in self.entry["headings"]]
        self.assertEqual(clauses, ["1", "1.1"])

    def test_fence_contents_excluded_from_section_text(self):
        # The fenced '# not a heading' / '---' / '|---|---|' lines must not
        # have produced extra headings (covered by test_only_real_headings_detected)
        # and must not appear as a clause_id or cross_ref anywhere.
        for h in self.entry["headings"]:
            self.assertEqual(h["cross_refs"], [])


class TestNon3gppNumbering(unittest.TestCase):
    """A trailing-period RFC-numbered heading ('5.2.2.  Title') must parse
    its clause id ONLY under the rfc profile -- generic/3gpp/ieee must not
    hallucinate a clause id from it. A plain dotted-numeric IEEE-style
    heading ('9.3.2 Title') must parse identically under all profiles."""

    def test_rfc_only_parses_trailing_period_heading(self):
        for profile in ("generic", "3gpp", "ieee"):
            entry = parse("non_3gpp_numbering.md", profile)
            self.assertIsNone(entry["headings"][0]["clause_id"],
                               "profile={} should not parse '5.2.2.  ...'".format(profile))

        rfc_entry = parse("non_3gpp_numbering.md", "rfc")
        self.assertEqual(rfc_entry["headings"][0]["clause_id"], "5.2.2")

    def test_ieee_plain_numbering_parses_everywhere(self):
        for profile in ("generic", "3gpp", "rfc", "ieee"):
            entry = parse("non_3gpp_numbering.md", profile)
            self.assertEqual(heading_by_clause(entry, "9.3.2")["title"], "9.3.2 Frame Format")
            self.assertEqual(heading_by_clause(entry, "9.3.3")["title"], "9.3.3 Field Definitions")

    def test_ieee_section_sign_cross_ref_resolves(self):
        entry = parse("non_3gpp_numbering.md", "ieee")
        intro = entry["headings"][0]
        refs = xrefs_by_target(intro, "9.3.2")
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["kind"], "section")
        self.assertEqual(refs[0]["raw"], "§9.3.2")  # section sign U+00A7
        self.assertTrue(refs[0]["resolved"])

    def test_rfc_section_cross_ref_resolves_to_self(self):
        entry = parse("non_3gpp_numbering.md", "rfc")
        intro = entry["headings"][0]
        refs = xrefs_by_target(intro, "5.2.2")
        self.assertEqual(len(refs), 1)
        self.assertTrue(refs[0]["resolved"])
        self.assertEqual(refs[0]["resolved_heading_id"], intro["id"])


class TestAlignmentColonTables(unittest.TestCase):
    """Pipe tables with alignment colons, and a table-separator row
    immediately followed by a bare '---' thematic break, must never be
    mistaken for headings or Setext underlines."""

    def setUp(self):
        self.entry = parse("alignment_colon_tables.md", "generic")

    def test_only_real_headings_detected(self):
        titles = [h["title"] for h in self.entry["headings"]]
        self.assertEqual(titles, ["1 Overview", "1.1 Notes"])

    def test_table_and_thematic_break_absorbed_into_section_body(self):
        overview = heading_by_clause(self.entry, "1")
        notes = heading_by_clause(self.entry, "1.1")
        # '1 Overview' (L1) section body starts right after its heading and
        # spans through the tables, the '|---|---|'/'---' edge case, and the
        # nested '1.1 Notes' (L2) subsection -- same-or-higher-level walk
        # means an L2 heading does not close an L1 section (parent spans
        # children, as in TestDeepNesting).
        self.assertEqual(overview["section_bounds"][0], 2)
        self.assertEqual(notes["line"], 12)
        self.assertGreaterEqual(overview["section_bounds"][1], notes["section_bounds"][1])


class TestCrossRefs(unittest.TestCase):
    """In-file clause/Annex/(see) references, including one DANGLING
    reference to a clause id that does not exist in the document. Dangling
    refs must be kept with resolved:false, never silently dropped."""

    def setUp(self):
        self.entry = parse("cross_refs.md", "3gpp")

    def test_annex_heading_has_no_clause_id_but_subclause_does(self):
        annex = next(h for h in self.entry["headings"] if h["title"].startswith("Annex B"))
        self.assertIsNone(annex["clause_id"])
        self.assertEqual(heading_by_clause(self.entry, "B.1")["title"], "B.1 Example flows")

    def test_resolved_refs(self):
        km = heading_by_clause(self.entry, "4.1")
        clause_ref = xrefs_by_target(km, "5.2")[0]
        self.assertEqual(clause_ref["kind"], "clause")
        self.assertTrue(clause_ref["resolved"])
        self.assertEqual(clause_ref["resolution_status"], "resolved")
        self.assertEqual(clause_ref["resolved_heading_id"], heading_by_clause(self.entry, "5.2")["id"])

        annex_ref = xrefs_by_target(km, "B.1")[0]
        self.assertEqual(annex_ref["kind"], "annex")
        self.assertTrue(annex_ref["resolved"])
        self.assertEqual(annex_ref["resolution_status"], "resolved")
        self.assertEqual(annex_ref["resolved_heading_id"], heading_by_clause(self.entry, "B.1")["id"])

        see_ref = xrefs_by_target(km, "4.2")[0]
        self.assertEqual(see_ref["kind"], "see")
        self.assertTrue(see_ref["resolved"])
        self.assertEqual(see_ref["resolution_status"], "resolved")

    def test_dangling_ref_kept_not_dropped(self):
        km = heading_by_clause(self.entry, "4.1")
        dangling = xrefs_by_target(km, "9.9")
        self.assertEqual(len(dangling), 1)
        self.assertEqual(dangling[0]["kind"], "clause")
        self.assertFalse(dangling[0]["resolved"])
        self.assertEqual(dangling[0]["resolution_status"], "unresolved-not-found")
        self.assertIsNone(dangling[0]["resolved_heading_id"])


class TestAmbiguousClauseId(unittest.TestCase):
    """A clause id (6.1) appears on two headings in the same file (main body
    and an annex). A cross-ref targeting it must never guess which one is
    meant -- it stays unresolved with resolution_status=unresolved-ambiguous,
    even though resolved-vs-dangling alone couldn't tell this case apart from
    a clean resolution."""

    def setUp(self):
        self.entry = parse("cross_refs_ambiguous.md", "3gpp")

    def test_ambiguous_clause_id_not_silently_resolved(self):
        pointer = heading_by_clause(self.entry, "8.1")
        ambiguous = xrefs_by_target(pointer, "6.1")
        self.assertEqual(len(ambiguous), 1)
        self.assertEqual(ambiguous[0]["kind"], "clause")
        self.assertFalse(ambiguous[0]["resolved"])
        self.assertEqual(ambiguous[0]["resolution_status"], "unresolved-ambiguous")
        self.assertIsNone(ambiguous[0]["resolved_heading_id"])


class TestCrossFileResolution(unittest.TestCase):
    """Phase B: a citation like 'IEEE 802.11-2020 section-sign 9.3.2' in one
    file resolves to a heading in a DIFFERENT file, joined via that file's
    doc_id front matter -- never guessed (R9). Synthetic 2-3 file corpora,
    written inline per-test via tempfile.TemporaryDirectory(), following the
    established pattern in TestWhatL2ExcludeAndIncludeRoots."""

    SECTION_SIGN = "§"

    def _write(self, root, rel_path, text):
        p = root / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def test_cross_file_ref_resolves_via_doc_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "spec_a.md",
                        "---\ndoc_id: IEEE 802.11-2020\n---\n"
                        "# 9.3.2 Frame Format\n\nDetails of frame format.\n")
            self._write(root, "spec_b.md",
                        "# 5.1 Overview\n\n"
                        "See IEEE 802.11-2020 {}9.3.2 for details.\n".format(self.SECTION_SIGN))

            index = mi.build_index(root, "ieee")
            by_path = {f["path"]: f for f in index["files"]}
            a_heading = by_path["spec_a.md"]["headings"][0]
            b_ref = xrefs_by_target(by_path["spec_b.md"]["headings"][0], "9.3.2")[0]

            self.assertEqual(b_ref["target_doc"], "IEEE 802.11-2020")
            self.assertTrue(b_ref["resolved"])
            self.assertEqual(b_ref["resolution_status"], "resolved")
            self.assertEqual(b_ref["resolved_file"], "spec_a.md")
            self.assertEqual(b_ref["resolved_heading_id"], a_heading["id"])

    def test_cross_file_ref_no_designator_still_resolves_same_file(self):
        # Backward compatibility: a bare section-sign ref (no doc designator)
        # must keep resolving same-file, single-hop, exactly as before Phase B.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "spec.md",
                        "# 9.3.2 Frame Format\n\nDetails.\n\n"
                        "# 5.1 Overview\n\nSee {}9.3.2 for details.\n".format(self.SECTION_SIGN))
            index = mi.build_index(root, "ieee")
            entry = index["files"][0]
            ref = xrefs_by_target(entry["headings"][1], "9.3.2")[0]
            self.assertIsNone(ref["target_doc"])
            self.assertTrue(ref["resolved"])
            self.assertEqual(len(entry["headings"][1]["cross_refs"]), 1)

    def test_cross_file_ref_doc_not_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "spec_a.md",
                        "---\ndoc_id: IEEE 802.11-2020\n---\n# 9.3.2 Frame Format\n\nDetails.\n")
            self._write(root, "spec_b.md",
                        "# 5.1 Overview\n\nSee IEEE 999.99-2099 {}1.1 for details.\n".format(self.SECTION_SIGN))
            index = mi.build_index(root, "ieee")
            by_path = {f["path"]: f for f in index["files"]}
            ref = xrefs_by_target(by_path["spec_b.md"]["headings"][0], "1.1")[0]
            self.assertEqual(ref["resolution_status"], "unresolved-doc-not-found")
            self.assertFalse(ref["resolved"])
            self.assertIsNone(ref["resolved_file"])

    def test_cross_file_ref_doc_id_ambiguous(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "spec_a.md",
                        "---\ndoc_id: IEEE 802.11-2020\n---\n# 9.3.2 Frame Format\n\nDetails.\n")
            self._write(root, "spec_a_dup.md",
                        "---\ndoc_id: IEEE 802.11-2020\n---\n# 9.3.2 Frame Format (dup)\n\nDetails.\n")
            self._write(root, "spec_b.md",
                        "# 5.1 Overview\n\nSee IEEE 802.11-2020 {}9.3.2 for details.\n".format(self.SECTION_SIGN))
            index = mi.build_index(root, "ieee")
            by_path = {f["path"]: f for f in index["files"]}
            ref = xrefs_by_target(by_path["spec_b.md"]["headings"][0], "9.3.2")[0]
            self.assertEqual(ref["resolution_status"], "unresolved-doc-ambiguous")
            self.assertFalse(ref["resolved"])

    def test_cross_file_ref_clause_not_found_in_matched_doc(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "spec_a.md",
                        "---\ndoc_id: IEEE 802.11-2020\n---\n# 9.3.2 Frame Format\n\nDetails.\n")
            self._write(root, "spec_b.md",
                        "# 5.1 Overview\n\nSee IEEE 802.11-2020 {}9.9.9 for details.\n".format(self.SECTION_SIGN))
            index = mi.build_index(root, "ieee")
            by_path = {f["path"]: f for f in index["files"]}
            ref = xrefs_by_target(by_path["spec_b.md"]["headings"][0], "9.9.9")[0]
            self.assertEqual(ref["resolution_status"], "unresolved-not-found")
            self.assertFalse(ref["resolved"])

    def test_cross_file_ref_clause_ambiguous_in_matched_doc(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "spec_a.md",
                        "---\ndoc_id: IEEE 802.11-2020\n---\n"
                        "# 9.3.2 Frame Format\n\nDetails.\n\n"
                        "# Annex C (informative): Duplicate\n\n"
                        "## 9.3.2 Frame Format\n\nAccidental duplicate.\n")
            self._write(root, "spec_b.md",
                        "# 5.1 Overview\n\nSee IEEE 802.11-2020 {}9.3.2 for details.\n".format(self.SECTION_SIGN))
            index = mi.build_index(root, "ieee")
            by_path = {f["path"]: f for f in index["files"]}
            ref = xrefs_by_target(by_path["spec_b.md"]["headings"][0], "9.3.2")[0]
            self.assertEqual(ref["resolution_status"], "unresolved-ambiguous")
            self.assertFalse(ref["resolved"])

    def test_cross_file_ref_designator_line_wrap_still_resolves(self):
        # A hard line-wrap between "IEEE" and "802.11-2020" in the source
        # prose must not leave an embedded newline in target_doc - that would
        # never exact-match a clean single-line doc_id.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "spec_a.md",
                        "---\ndoc_id: IEEE 802.11-2020\n---\n# 9.3.2 Frame Format\n\nDetails.\n")
            self._write(root, "spec_b.md",
                        "# 5.1 Overview\n\nSee IEEE\n802.11-2020 {}9.3.2 for details.\n".format(self.SECTION_SIGN))
            index = mi.build_index(root, "ieee")
            by_path = {f["path"]: f for f in index["files"]}
            ref = xrefs_by_target(by_path["spec_b.md"]["headings"][0], "9.3.2")[0]
            self.assertEqual(ref["target_doc"], "IEEE 802.11-2020")
            self.assertTrue(ref["resolved"])
            self.assertEqual(ref["resolved_file"], "spec_a.md")


class TestDeepNesting(unittest.TestCase):
    """Clause ids nested 6 levels deep (7.2.9.2.1.3) must parse, and the
    deepest section's bounds must not collapse to an empty range."""

    def setUp(self):
        self.entry = parse("deep_nesting.md", "3gpp")

    def test_all_depths_parsed(self):
        clauses = [h["clause_id"] for h in self.entry["headings"]]
        self.assertEqual(clauses,
                         ["7", "7.2", "7.2.9", "7.2.9.2", "7.2.9.2.1", "7.2.9.2.1.3", "7.2.9.3"])

    def test_deepest_section_bounds_not_collapsed(self):
        deepest = heading_by_clause(self.entry, "7.2.9.2.1.3")
        start, end = deepest["section_bounds"]
        self.assertGreater(end, start - 1)  # non-empty
        self.assertEqual([start, end], [12, 14])

    def test_parent_bounds_span_children(self):
        parent = heading_by_clause(self.entry, "7.2.9.2")
        child = heading_by_clause(self.entry, "7.2.9.2.1")
        self.assertLessEqual(parent["section_bounds"][0], child["line"])
        self.assertGreaterEqual(parent["section_bounds"][1], child["section_bounds"][1])


class TestGoldenSessionManagement(unittest.TestCase):
    """Full parse_file() snapshot of the real (53-line) NIST excerpt used to
    validate D13/D14. parse_file() output has no machine-dependent fields
    (sha256 is content-derived, path is relative), so a full dict comparison
    is a stable golden regression test."""

    def test_matches_snapshot(self):
        entry = parse("golden_session_management.md", "generic")
        with open(FIXTURES / "golden_session_management.expected.json", encoding="utf-8") as fh:
            expected = json.load(fh)
        self.assertEqual(entry, expected)


class TestQueryAndStaleness(unittest.TestCase):
    """End-to-end: build_index -> query_index, and the --stale-check contract."""

    def test_query_ranks_and_skips_toc(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "index.json"
            index = mi.build_index(FIXTURES / "mixed_atx_setext.md", "generic")
            with out.open("w", encoding="utf-8") as fh:
                json.dump(index, fh)

            results = mi.query_index(out, ["security", "network"], top=10)
            files = {r["heading_id"] for r in results}
            # 'Contents' (h_0000, is_toc=true) must never appear in results.
            self.assertNotIn("h_0000", files)
            self.assertTrue(any(r["clause_id"] == "2.2" for r in results))

    def test_query_warns_on_missing_source_and_still_returns_other_results(self):
        """R15: an index entry whose source file can't be resolved (moved /
        deleted / index copied without its sources) must not crash `query` --
        it prints a stderr warning naming the path and candidates tried, then
        skips that file while still returning results for files that DO
        resolve."""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "index.json"
            index = mi.build_index(FIXTURES, "generic")
            index["files"].append({
                "path": "does_not_exist.md",
                "sha256": "0" * 64,
                "front_matter_lines": None,
                "headings": [{
                    "id": "h_0000",
                    "style": "atx",
                    "level": 1,
                    "title": "Phantom",
                    "clause_id": None,
                    "is_toc": False,
                    "line": 1,
                    "section_bounds": [2, 2],
                    "cross_refs": [],
                }],
            })
            with out.open("w", encoding="utf-8") as fh:
                json.dump(index, fh)

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                results = mi.query_index(out, ["security"], top=10)

            warning = stderr.getvalue()
            self.assertIn("does_not_exist.md", warning)
            self.assertIn("Warning: source file not found", warning)
            # mixed_atx_setext.md (a real, resolvable fixture) is still
            # searched and still produces its known "security" match.
            self.assertTrue(any(r["clause_id"] == "2.2" for r in results))

    def test_stale_check_profile_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "index.json"
            target = FIXTURES / "deep_nesting.md"

            self.assertTrue(mi.is_stale(out, [target], "3gpp"))

            index = mi.build_index(target, "3gpp")
            with out.open("w", encoding="utf-8") as fh:
                json.dump(index, fh)

            self.assertFalse(mi.is_stale(out, [target], "3gpp"))
            # Same output file, different profile -> stale.
            self.assertTrue(mi.is_stale(out, [target], "generic"))


class TestWhatL2ExcludeAndIncludeRoots(unittest.TestCase):
    """D21 §16.5/§16.7 (Phase 3c): gather_md_files() gains `exclude` (subtree
    prefix-filter, relative to `target`) and `include_roots` (additional
    out-of-tree directories walked wholesale). Both default to `[]`."""

    def _make_tree(self, tmp):
        root = Path(tmp)
        write = lambda p, text="# Heading\n": (p.parent.mkdir(parents=True, exist_ok=True), p.write_text(text, encoding="utf-8"))
        target = root / "docs"
        write(target / "outputs" / "a.md")
        write(target / "contexts" / "b.md")
        write(target / "cache-extra" / "d.md")  # near-miss of 'cache/' - must NOT be excluded
        write(target / "c.md")
        external = root / "output_docs_structure" / "Requirements"
        write(external / "z.md")
        return target, external

    def test_no_exclude_no_include_roots_matches_plain_rglob(self):
        """Critical regression case: absent/empty exclude and include_roots
        must collect exactly what plain `target.rglob("*.md")` would - byte-
        identical to before this parameter existed."""
        with tempfile.TemporaryDirectory() as tmp:
            target, _external = self._make_tree(tmp)
            baseline = sorted(target.rglob("*.md"))

            files_no_kwargs, root_no_kwargs = mi.gather_md_files(target)
            files_empty, root_empty = mi.gather_md_files(target, exclude=[], include_roots=[])

            self.assertEqual(files_no_kwargs, baseline)
            self.assertEqual(files_empty, baseline)
            self.assertEqual(root_no_kwargs, target)
            self.assertEqual(root_empty, target)

    def test_exclude_removes_a_subtree(self):
        with tempfile.TemporaryDirectory() as tmp:
            target, _external = self._make_tree(tmp)
            files, _root = mi.gather_md_files(target, exclude=["contexts/"])
            rels = {f.relative_to(target).as_posix() for f in files}
            self.assertNotIn("contexts/b.md", rels)
            self.assertIn("outputs/a.md", rels)
            self.assertIn("c.md", rels)

    def test_exclude_near_miss_does_not_match(self):
        # 'cache/' must not exclude 'cache-extra/' (S21's flip side: a
        # correctly-spelled exclude entry only prefix-matches whole path
        # components, never a partial directory-name match).
        with tempfile.TemporaryDirectory() as tmp:
            target, _external = self._make_tree(tmp)
            files, _root = mi.gather_md_files(target, exclude=["cache/"])
            rels = {f.relative_to(target).as_posix() for f in files}
            self.assertIn("cache-extra/d.md", rels)

    def test_include_roots_adds_out_of_tree_subtree(self):
        with tempfile.TemporaryDirectory() as tmp:
            target, external = self._make_tree(tmp)
            files, root = mi.gather_md_files(target, include_roots=[str(external)])
            self.assertEqual(root, target)

            in_tree = {f.relative_to(target).as_posix() for f in files if _is_relative_to(f, target)}
            self.assertIn("outputs/a.md", in_tree)

            out_of_tree = [f for f in files if not _is_relative_to(f, target)]
            self.assertEqual(len(out_of_tree), 1)
            self.assertTrue(out_of_tree[0].is_absolute())
            self.assertEqual(out_of_tree[0].resolve(), (external / "z.md").resolve())

    def test_build_index_indexes_include_roots_file_via_fallback_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            target, external = self._make_tree(tmp)
            index = mi.build_index(target, "generic", exclude=["contexts/"],
                                    include_roots=[str(external)])
            paths = {f["path"] for f in index["files"]}

            # In-tree, non-excluded files are relative to `target`.
            self.assertIn("outputs/a.md", paths)
            self.assertIn("c.md", paths)
            # Excluded subtree is absent.
            self.assertFalse(any(p.startswith("contexts/") for p in paths))
            # include_roots file falls back to an absolute, '/'-normalised path.
            ext_path = next(p for p in paths if p.endswith("Requirements/z.md"))
            self.assertTrue(Path(ext_path).is_absolute())
            self.assertNotIn("\\", ext_path)


def _is_relative_to(path, other):
    try:
        path.relative_to(other)
        return True
    except ValueError:
        return False


class TestQueryBatch(unittest.TestCase):
    """R18: cmd_query_batch runs query_index once per key in a JSON file and
    returns a dict of per-key results, matching plain `query` per key."""

    def test_query_batch_matches_per_key_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "index.json"
            index = mi.build_index(FIXTURES / "mixed_atx_setext.md", "generic")
            with out.open("w", encoding="utf-8") as fh:
                json.dump(index, fh)

            queries_file = Path(tmp) / "queries.json"
            with queries_file.open("w", encoding="utf-8") as fh:
                json.dump({"1": ["security"], "2": ["network"]}, fh)

            args = types.SimpleNamespace(
                index=str(out), queries_file=str(queries_file), top=10)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                rc = mi.cmd_query_batch(args)
            self.assertEqual(rc, 0)

            batched = json.loads(stdout.getvalue())
            self.assertEqual(set(batched), {"1", "2"})
            self.assertEqual(batched["1"], mi.query_index(out, ["security"], 10))
            self.assertEqual(batched["2"], mi.query_index(out, ["network"], 10))


if __name__ == "__main__":
    unittest.main()
