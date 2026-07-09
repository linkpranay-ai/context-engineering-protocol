"""Regression suite for usage_report.py (ROADMAP item 7 - aggregation report).

Stdlib unittest only -- no pytest dependency, so this stays vendorable along
with usage_report.py itself. Run with:

    python -m unittest discover -s scripts/tests -v
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import usage_report as ur  # noqa: E402


PACKAGE_ALL_CITED = """context_package:
  id: alpha_design_20260701
  generated_at: "2026-07-01T00:00:00Z"
  human_approved: true
  context_items:
    - id: ctx_001
      layer: what-l3
      source: src/foo.py:10-20
      type: implementation
      confidence: EXTRACTED
      summary: >
        Something extracted from code.
    - id: ctx_002
      layer: what-l2
      source: docs/requirements/foo.md
      type: requirement
      confidence: EXTRACTED
      summary: >
        Something extracted from requirements.
  conflicts_detected: []
"""

ADDENDA_ALL_CITED = """addenda:
  - id: add_001
    kind: reference
    added_by: demo-consume-context
    added_at: "2026-07-01T01:00:00Z"
    artifact: "plan.md"
    cites: { ctx_ids: [ctx_001, ctx_002], aspect_ids: [] }
    tokens_used: 4200
"""

PACKAGE_SOME_NEVER_CITED = """context_package:
  id: beta_bugfix_20260702
  generated_at: "2026-07-02T00:00:00Z"
  human_approved: true
  context_items:
    - id: ctx_001
      layer: what-l3
      source: src/bar.py:5-9
      type: implementation
      confidence: EXTRACTED
      summary: >
        Cited item.
    - id: ctx_002
      layer: what-l1
      source: "specs/external/spec.md (5.2)"
      type: domain-spec
      confidence: EXTRACTED
      what_l1_fallback: true
      summary: >
        Never-cited What-L1 fallback item.
    - id: ctx_003
      layer: how-l1
      source: "org/process-standards/qms.md (4.1)"
      type: process-standard
      confidence: EXTRACTED
      how_l1_fallback: true
      summary: >
        Never-cited How-L1 fallback item.
  conflicts_detected: []
"""

ADDENDA_SOME_NEVER_CITED = """addenda:
  - id: add_001
    kind: reference
    added_by: demo-consume-context
    added_at: "2026-07-02T01:00:00Z"
    artifact: "chat response"
    cites: { ctx_ids: [ctx_001], aspect_ids: [] }
"""


def write(dir_path, name, content):
    (dir_path / name).write_text(content, encoding="utf-8")


class TestParsePackage(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_parses_id_and_items(self):
        path = self.tmp / "alpha_design_20260701.yaml"
        write(self.tmp, path.name, PACKAGE_ALL_CITED)
        pkg = ur.parse_package(path)
        self.assertEqual(pkg["id"], "alpha_design_20260701")
        self.assertEqual(pkg["generated_at"], '"2026-07-01T00:00:00Z"')
        self.assertEqual([i["id"] for i in pkg["items"]], ["ctx_001", "ctx_002"])
        self.assertEqual(pkg["items"][0]["layer"], "what-l3")
        self.assertEqual(pkg["items"][1]["layer"], "what-l2")

    def test_parses_fallback_flags(self):
        path = self.tmp / "beta_bugfix_20260702.yaml"
        write(self.tmp, path.name, PACKAGE_SOME_NEVER_CITED)
        pkg = ur.parse_package(path)
        by_id = {i["id"]: i for i in pkg["items"]}
        self.assertEqual(by_id["ctx_002"]["what_l1_fallback"], "true")
        self.assertEqual(by_id["ctx_003"]["how_l1_fallback"], "true")


class TestParseAddenda(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_parses_cites_and_tokens_used(self):
        path = self.tmp / "alpha_design_20260701_20260701.addenda.yaml"
        write(self.tmp, path.name, ADDENDA_ALL_CITED)
        entries = ur.parse_addenda(path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["ctx_ids"], ["ctx_001", "ctx_002"])
        self.assertEqual(entries[0]["tokens_used"], 4200)

    def test_missing_tokens_used_is_none(self):
        path = self.tmp / "beta_bugfix_20260702_20260702.addenda.yaml"
        write(self.tmp, path.name, ADDENDA_SOME_NEVER_CITED)
        entries = ur.parse_addenda(path)
        self.assertEqual(entries[0]["ctx_ids"], ["ctx_001"])
        self.assertIsNone(entries[0]["tokens_used"])


class TestAggregateAndRender(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_dir_reports_zero_packages(self):
        report = ur.aggregate(self.tmp)
        self.assertEqual(report["packages"], [])
        markdown = ur.render_markdown(report)
        self.assertIn("No context packages found.", markdown)

    def test_missing_dir_is_graceful(self):
        report = ur.aggregate(self.tmp / "does-not-exist")
        self.assertEqual(report["packages"], [])

    def test_two_packages_cited_and_never_cited(self):
        write(self.tmp, "alpha_design_20260701.yaml", PACKAGE_ALL_CITED)
        write(
            self.tmp,
            "alpha_design_20260701_20260701.addenda.yaml",
            ADDENDA_ALL_CITED,
        )
        write(self.tmp, "beta_bugfix_20260702.yaml", PACKAGE_SOME_NEVER_CITED)
        write(
            self.tmp,
            "beta_bugfix_20260702_20260702.addenda.yaml",
            ADDENDA_SOME_NEVER_CITED,
        )

        report = ur.aggregate(self.tmp)
        self.assertEqual(len(report["packages"]), 2)

        by_id = {pkg["id"]: pkg for pkg in report["packages"]}
        alpha_items = {i["id"]: i["cited"] for i in by_id["alpha_design_20260701"]["items"]}
        self.assertTrue(all(alpha_items.values()))

        beta_items = {i["id"]: i["cited"] for i in by_id["beta_bugfix_20260702"]["items"]}
        self.assertTrue(beta_items["ctx_001"])
        self.assertFalse(beta_items["ctx_002"])  # never-cited what-l1 fallback
        self.assertFalse(beta_items["ctx_003"])  # never-cited how-l1 fallback

        self.assertEqual(report["tokens_used_samples"], [4200])

        markdown = ur.render_markdown(report)
        self.assertIn("Total context items: 5", markdown)
        self.assertIn("Never cited: 2", markdown)
        self.assertIn("based on 1 measured run", markdown.lower())
        self.assertIn("alpha_design_20260701", markdown)
        self.assertIn("beta_bugfix_20260702", markdown)

    def test_no_measured_tokens_prints_placeholder(self):
        write(self.tmp, "beta_bugfix_20260702.yaml", PACKAGE_SOME_NEVER_CITED)
        write(
            self.tmp,
            "beta_bugfix_20260702_20260702.addenda.yaml",
            ADDENDA_SOME_NEVER_CITED,
        )
        report = ur.aggregate(self.tmp)
        markdown = ur.render_markdown(report)
        self.assertIn("No measured runs yet", markdown)


class TestMain(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_main_writes_report_file(self):
        write(self.tmp, "alpha_design_20260701.yaml", PACKAGE_ALL_CITED)
        write(
            self.tmp,
            "alpha_design_20260701_20260701.addenda.yaml",
            ADDENDA_ALL_CITED,
        )
        rc = ur.main(["--dir", str(self.tmp)])
        self.assertEqual(rc, 0)
        report_path = self.tmp / "USAGE_REPORT.md"
        self.assertTrue(report_path.exists())
        self.assertIn("Total context items: 2", report_path.read_text(encoding="utf-8"))

    def test_main_on_empty_dir_still_writes_report(self):
        rc = ur.main(["--dir", str(self.tmp)])
        self.assertEqual(rc, 0)
        report_path = self.tmp / "USAGE_REPORT.md"
        self.assertTrue(report_path.exists())
        self.assertIn("No context packages found.", report_path.read_text(encoding="utf-8"))

    def test_main_bad_flag_returns_2(self):
        self.assertEqual(ur.main(["--bogus"]), 2)


if __name__ == "__main__":
    unittest.main()
