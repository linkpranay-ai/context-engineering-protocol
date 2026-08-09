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

    def test_empty_install_lists_nothing(self):
        self.assertEqual(wd.list_docs(self.root), [])

    def test_protocol_and_readme_found_when_present(self):
        (self.root / "PROTOCOL.md").write_text("# Protocol", encoding="utf-8")
        (self.root / "README.md").write_text("# Readme", encoding="utf-8")
        docs = wd.list_docs(self.root)
        ids = [d.doc_id for d in docs]
        self.assertEqual(ids, ["protocol", "readme"])
        self.assertEqual(docs[0].kind, "doc")

    def test_readme_omitted_when_missing_not_errored(self):
        (self.root / "PROTOCOL.md").write_text("# Protocol", encoding="utf-8")
        docs = wd.list_docs(self.root)
        self.assertEqual([d.doc_id for d in docs], ["protocol"])

    def test_case_studies_discovered_and_sorted(self):
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
        cs_dir = self.root / "case-studies" / "ripgrep-user-stories"
        cs_dir.mkdir(parents=True)
        (cs_dir / "CASE-STUDY.md").write_text(
            "```yaml\ncase: ripgrep-trim-user-stories\n```\n", encoding="utf-8"
        )
        docs = wd.list_docs(self.root)
        case_study = [d for d in docs if d.kind == "case-study"][0]
        self.assertEqual(case_study.title, "ripgrep-user-stories")

    def test_directory_without_case_study_file_is_skipped(self):
        empty_dir = self.root / "case-studies" / "not-a-case-study"
        empty_dir.mkdir(parents=True)
        self.assertEqual(wd.list_docs(self.root), [])

    def test_find_doc_returns_none_for_unknown_id(self):
        self.assertIsNone(wd.find_doc("nonexistent", self.root))

    def test_find_doc_returns_matching_entry(self):
        (self.root / "README.md").write_text("hi", encoding="utf-8")
        entry = wd.find_doc("readme", self.root)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.doc_id, "readme")

    def test_to_json_dict_shape(self):
        (self.root / "README.md").write_text("hi", encoding="utf-8")
        payload = wd.to_json_dict(wd.list_docs(self.root))
        self.assertEqual(
            payload, {"docs": [{"id": "readme", "title": "README", "kind": "doc"}]}
        )


class TestInstallRoot(unittest.TestCase):
    def test_install_root_is_repo_root(self):
        # scripts -> ult-layout-wizard -> skills -> .github -> repo root
        root = wd.install_root()
        self.assertTrue((root / ".github").is_dir())


if __name__ == "__main__":
    unittest.main()
