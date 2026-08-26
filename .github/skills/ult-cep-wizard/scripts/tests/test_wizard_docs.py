"""Regression suite for wizard_docs.py (UI design pass). Stdlib unittest only.
Run with:

    python -m unittest discover -s scripts/tests -v
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wizard_docs as wd  # noqa: E402


class TestListDocs(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _verify_bundle(self):
        # Satisfies _bundle_verified() so list_docs() actually scans root -
        # every test below that isn't itself exercising the gate calls this
        # first, now that CONCEPT.md+PROTOCOL.md together gate everything
        # else found under root (see wizard_docs.py's module docstring and
        # TestBundleVerification below for the gate's own regression tests).
        (self.root / "CONCEPT.md").write_text("# Concept", encoding="utf-8")
        (self.root / "PROTOCOL.md").write_text("# Protocol", encoding="utf-8")

    def test_empty_install_lists_nothing(self):
        self.assertEqual(wd.list_docs(self.root), [])

    def test_concept_found_when_present(self):
        # Concept must be first in list order - the wizard's nav order
        # mirrors this, and Concept is meant to be read before Protocol.
        self._verify_bundle()
        (self.root / "README.md").write_text("# Readme", encoding="utf-8")
        docs = wd.list_docs(self.root)
        ids = [d.doc_id for d in docs]
        self.assertEqual(ids, ["concept", "protocol", "readme"])
        self.assertEqual(docs[0].kind, "doc")

    def test_faq_found_when_present_and_ordered_last(self):
        # FAQ must be last in list order - the wizard's nav order mirrors
        # this, and FAQ is meant to be a reference readers reach for after
        # (or independently of) the other docs, not a prerequisite to them.
        self._verify_bundle()
        (self.root / "README.md").write_text("# Readme", encoding="utf-8")
        (self.root / "FAQ.md").write_text("# FAQ", encoding="utf-8")
        docs = wd.list_docs(self.root)
        ids = [d.doc_id for d in docs]
        self.assertEqual(ids, ["concept", "protocol", "readme", "faq"])
        self.assertEqual(docs[-1].kind, "doc")
        self.assertEqual(docs[-1].title, "FAQ")

    def test_faq_omitted_when_missing_not_errored(self):
        self._verify_bundle()
        (self.root / "README.md").write_text("# Readme", encoding="utf-8")
        docs = wd.list_docs(self.root)
        self.assertEqual([d.doc_id for d in docs], ["concept", "protocol", "readme"])

    def test_concept_missing_fails_bundle_verification(self):
        # Regression test for the leak this gate closes: PROTOCOL.md alone
        # (without CONCEPT.md alongside it) must not be enough to trust
        # `root` as CEP's own repo - the whole bundle stays unverified and
        # nothing is listed, not just Concept itself omitted. See
        # TestBundleVerification for the full set of these cases.
        (self.root / "PROTOCOL.md").write_text("# Protocol", encoding="utf-8")
        (self.root / "README.md").write_text("# Readme", encoding="utf-8")
        self.assertEqual(wd.list_docs(self.root), [])

    def test_readme_omitted_when_missing_not_errored(self):
        # README.md is not part of the bundle-verification signal itself
        # (see module docstring - it's the one doc nearly every repo has),
        # so a verified bundle without it still lists Concept/Protocol.
        self._verify_bundle()
        docs = wd.list_docs(self.root)
        self.assertEqual([d.doc_id for d in docs], ["concept", "protocol"])

    def test_case_studies_readme_synthesis_template_discovered_with_titles(self):
        # These three are the Case Studies section's landing doc and its two
        # supporting docs - reachable only via links inside the README, not
        # their own top-nav buttons (see wizard_docs.list_docs's docstring).
        self._verify_bundle()
        cs_dir = self.root / "case-studies"
        cs_dir.mkdir(parents=True)
        (cs_dir / "README.md").write_text("# Case Studies\n\nbody", encoding="utf-8")
        (cs_dir / "SYNTHESIS.md").write_text(
            "# Cross-case synthesis\n\nbody", encoding="utf-8"
        )
        (cs_dir / "TEMPLATE.md").write_text(
            "# Case Study Template\n\nbody", encoding="utf-8"
        )
        docs = wd.list_docs(self.root)
        by_id = {d.doc_id: d for d in docs}
        self.assertEqual(by_id["case-studies-readme"].title, "Case Studies")
        self.assertEqual(by_id["case-studies-readme"].kind, "doc")
        self.assertEqual(by_id["case-studies-synthesis"].title, "Cross-case synthesis")
        self.assertEqual(by_id["case-studies-template"].title, "Case Study Template")
        # Ordering: readme/synthesis/template come before any individual
        # case-study-* entry (and after concept/protocol - the bundle files
        # written by _verify_bundle above).
        ids = [d.doc_id for d in docs]
        self.assertEqual(
            ids,
            [
                "concept",
                "protocol",
                "case-studies-readme",
                "case-studies-synthesis",
                "case-studies-template",
            ],
        )

    def test_case_studies_readme_falls_back_to_default_title_without_h1(self):
        self._verify_bundle()
        cs_dir = self.root / "case-studies"
        cs_dir.mkdir(parents=True)
        (cs_dir / "README.md").write_text("no heading here", encoding="utf-8")
        docs = wd.list_docs(self.root)
        cs_docs = [d for d in docs if d.doc_id == "case-studies-readme"]
        self.assertEqual(cs_docs[0].title, "Case Studies")

    def test_case_studies_readme_synthesis_template_omitted_when_missing(self):
        # A case-studies/ dir with only individual case studies (no README/
        # SYNTHESIS/TEMPLATE) must not error or synthesize fake entries.
        self._verify_bundle()
        cs_dir = self.root / "case-studies" / "aaa-first"
        cs_dir.mkdir(parents=True)
        (cs_dir / "CASE-STUDY.md").write_text(
            "# Case Study: Aaa First\n\nbody", encoding="utf-8"
        )
        docs = wd.list_docs(self.root)
        ids = [d.doc_id for d in docs]
        self.assertNotIn("case-studies-readme", ids)
        self.assertNotIn("case-studies-synthesis", ids)
        self.assertNotIn("case-studies-template", ids)
        self.assertEqual(ids, ["concept", "protocol", "case-study-aaa-first"])

    def test_case_studies_discovered_and_sorted(self):
        self._verify_bundle()
        cs_dir = self.root / "case-studies"
        for slug, title in [("zzz-last", "Zzz Last"), ("aaa-first", "Aaa First")]:
            d = cs_dir / slug
            d.mkdir(parents=True)
            (d / "CASE-STUDY.md").write_text(
                f"# Case Study: {title}\n\nbody", encoding="utf-8"
            )
        docs = wd.list_docs(self.root)
        case_studies = [d for d in docs if d.kind == "case-study"]
        self.assertEqual([d.title for d in case_studies], ["Aaa First", "Zzz Last"])
        self.assertEqual(case_studies[0].doc_id, "case-study-aaa-first")

    def test_case_study_without_h1_falls_back_to_slug(self):
        self._verify_bundle()
        cs_dir = self.root / "case-studies" / "ripgrep-user-stories"
        cs_dir.mkdir(parents=True)
        (cs_dir / "CASE-STUDY.md").write_text(
            "```yaml\ncase: ripgrep-trim-user-stories\n```\n", encoding="utf-8"
        )
        docs = wd.list_docs(self.root)
        case_study = [d for d in docs if d.kind == "case-study"][0]
        self.assertEqual(case_study.title, "ripgrep-user-stories")

    def test_directory_without_case_study_file_is_skipped(self):
        self._verify_bundle()
        empty_dir = self.root / "case-studies" / "not-a-case-study"
        empty_dir.mkdir(parents=True)
        docs = wd.list_docs(self.root)
        self.assertEqual([d.doc_id for d in docs], ["concept", "protocol"])

    def test_directory_with_obsolete_marker_is_skipped(self):
        # Mirrors case-studies/cep-retrofit-mattpocock-skills-copilot/ in this
        # repo: a real CASE-STUDY.md sitting next to an OBSOLETE.md sentinel
        # must not appear in the docs list, regardless of content quality.
        self._verify_bundle()
        obsolete_dir = self.root / "case-studies" / "cep-retrofit-something-copilot"
        obsolete_dir.mkdir(parents=True)
        (obsolete_dir / "CASE-STUDY.md").write_text(
            "# Case Study: Something\n\nbody", encoding="utf-8"
        )
        (obsolete_dir / "OBSOLETE.md").write_text(
            "# OBSOLETE - not part of this repo, do not publish\n", encoding="utf-8"
        )
        published_dir = self.root / "case-studies" / "aaa-still-published"
        published_dir.mkdir(parents=True)
        (published_dir / "CASE-STUDY.md").write_text(
            "# Case Study: Still Published\n\nbody", encoding="utf-8"
        )
        docs = wd.list_docs(self.root)
        case_studies = [d for d in docs if d.kind == "case-study"]
        self.assertEqual([d.title for d in case_studies], ["Still Published"])

    def test_find_doc_returns_none_for_unknown_id(self):
        self._verify_bundle()
        self.assertIsNone(wd.find_doc("nonexistent", self.root))

    def test_find_doc_returns_matching_entry(self):
        self._verify_bundle()
        (self.root / "README.md").write_text("hi", encoding="utf-8")
        entry = wd.find_doc("readme", self.root)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.doc_id, "readme")

    def test_to_json_dict_shape(self):
        self._verify_bundle()
        payload = wd.to_json_dict(wd.list_docs(self.root))
        self.assertEqual(
            payload,
            {
                "docs": [
                    {"id": "concept", "title": "Concept", "kind": "doc"},
                    {"id": "protocol", "title": "Protocol", "kind": "doc"},
                ]
            },
        )


class TestBundleVerification(unittest.TestCase):
    """Regression tests for the consumer-repo docs leak `_bundle_verified()`
    closes: `install_root()` silently resolves to whatever repo this skill's
    directory happens to sit under, so once installed into a consumer repo,
    `list_docs()` used to serve that repo's own README.md under CEP branding.
    See wizard_docs.py's module docstring."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_consumer_repo_with_only_readme_lists_nothing(self):
        # The exact leak this gate closes: an unrelated consumer repo with
        # its own README.md and nothing CEP-specific must not have that
        # README served back under CEP's docs-viewer branding.
        (self.root / "README.md").write_text(
            "# Some Unrelated Project\n", encoding="utf-8"
        )
        self.assertEqual(wd.list_docs(self.root), [])

    def test_protocol_without_concept_lists_nothing(self):
        (self.root / "PROTOCOL.md").write_text("# Protocol", encoding="utf-8")
        (self.root / "README.md").write_text("# Readme", encoding="utf-8")
        self.assertEqual(wd.list_docs(self.root), [])

    def test_concept_without_protocol_lists_nothing(self):
        (self.root / "CONCEPT.md").write_text("# Concept", encoding="utf-8")
        (self.root / "README.md").write_text("# Readme", encoding="utf-8")
        self.assertEqual(wd.list_docs(self.root), [])

    def test_concept_and_protocol_together_verify_the_bundle(self):
        (self.root / "CONCEPT.md").write_text("# Concept", encoding="utf-8")
        (self.root / "PROTOCOL.md").write_text("# Protocol", encoding="utf-8")
        docs = wd.list_docs(self.root)
        self.assertEqual([d.doc_id for d in docs], ["concept", "protocol"])

    def test_find_doc_returns_none_when_bundle_unverified(self):
        (self.root / "README.md").write_text("# Readme", encoding="utf-8")
        self.assertIsNone(wd.find_doc("readme", self.root))

    def test_case_studies_not_served_from_unverified_bundle(self):
        # Even real case-study content must not surface until the bundle
        # itself is verified - a whole-bundle gate, not a per-doc one (see
        # wizard_docs.list_docs's own docstring on this distinction).
        cs_dir = self.root / "case-studies" / "aaa-first"
        cs_dir.mkdir(parents=True)
        (cs_dir / "CASE-STUDY.md").write_text(
            "# Case Study: Aaa First\n\nbody", encoding="utf-8"
        )
        self.assertEqual(wd.list_docs(self.root), [])


class TestDocsRoot(unittest.TestCase):
    """Regression tests for docs_root()'s two-location resolution (see
    wizard_docs.py's module docstring): a bundled docs/ sibling of this
    script's own installed directory, preferred outright when present, else
    a guarded fallback to the CEP-repo-root guess `install_root()` used to
    always make unconditionally."""

    def test_docs_root_falls_back_to_repo_root_when_no_bundled_docs_dir(self):
        # This repo's own source tree has no .github/skills/ult-cep-wizard/
        # docs/ sibling - that's materialized only at install time by
        # install.ps1/install.sh into a *target* repo (see module
        # docstring) - so self-testing here must fall back to the
        # repo-root heuristic exactly as install_root() used to always do.
        root = wd.docs_root()
        self.assertIsNotNone(root)
        self.assertTrue((root / ".github").is_dir())
        self.assertTrue((root / "CONCEPT.md").is_file())

    def test_docs_root_prefers_bundled_docs_dir_when_present(self):
        # Simulates a real consumer install: install.ps1/install.sh bundled
        # docs/ as a sibling of this skill's own scripts/ directory. A
        # bundled docs/ existing at all is trusted outright - no
        # CONCEPT.md/PROTOCOL.md check needed there, unlike the fallback.
        with tempfile.TemporaryDirectory() as tmp:
            bundled = Path(tmp) / "docs"
            bundled.mkdir()
            original = wd._docs_dir
            wd._docs_dir = lambda: bundled
            try:
                self.assertEqual(wd.docs_root(), bundled)
            finally:
                wd._docs_dir = original

    def test_docs_root_none_when_neither_location_verifies(self):
        original_docs_dir = wd._docs_dir
        original_self_test = wd._self_test_root
        with tempfile.TemporaryDirectory() as tmp:
            missing_bundle = Path(tmp) / "docs"  # never created
            unrelated = Path(tmp) / "unrelated"
            unrelated.mkdir()
            (unrelated / "README.md").write_text("# Some repo", encoding="utf-8")
            wd._docs_dir = lambda: missing_bundle
            wd._self_test_root = lambda: unrelated
            try:
                self.assertIsNone(wd.docs_root())
                self.assertEqual(wd.list_docs(), [])
            finally:
                wd._docs_dir = original_docs_dir
                wd._self_test_root = original_self_test


if __name__ == "__main__":
    unittest.main()
