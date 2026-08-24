"""Regression suite for decision_ledger.py (trip-wire).

Stdlib unittest only -- no pytest dependency, so this stays vendorable along
with decision_ledger.py itself. Run with:

    python -m unittest discover -s scripts/tests -v
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import decision_ledger as dl  # noqa: E402


class LoadSaveRoundtripTests(unittest.TestCase):
    def test_missing_file_returns_empty_skeleton(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = dl.load_ledger(Path(d) / "DECISION-LEDGER.json")
        self.assertEqual(ledger["entries"], [])
        self.assertEqual(ledger["run_state"]["cursors"], [])
        self.assertEqual(ledger["run_state"]["rejected_sources"], [])
        self.assertEqual(ledger["hit_dispositions"], [])
        self.assertEqual(ledger["schema_version"], dl.SCHEMA_VERSION)

    def test_save_then_load_roundtrips(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "nested" / "DECISION-LEDGER.json"
            ledger = dl.empty_ledger()
            dl.add_entry(
                ledger, "Use Kafka", "RabbitMQ failed under load", ["kafka", "message-queue"],
                "pr", "https://example/pr/1", "EXTRACTED", "run-1", "cursor-0",
            )
            dl.save_ledger(path, ledger)
            self.assertTrue(path.exists(), "save_ledger must create parent dirs")
            reloaded = dl.load_ledger(path)
            self.assertEqual(len(reloaded["entries"]), 1)
            self.assertEqual(reloaded["entries"][0]["decision"], "Use Kafka")

    def test_empty_file_treated_as_empty_skeleton(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "DECISION-LEDGER.json"
            path.write_text("", encoding="utf-8")
            ledger = dl.load_ledger(path)
            self.assertEqual(ledger["entries"], [])


class AddEntryTests(unittest.TestCase):
    def test_add_entry_basic_fields(self):
        ledger = dl.empty_ledger()
        entry = dl.add_entry(
            ledger, "Use Kafka", "RabbitMQ failed under our load profile", ["kafka", "queue"],
            "postmortem", "docs/postmortems/2026-01.md", "EXTRACTED", "run-1", "cursor-1",
            rejected_alternatives=["RabbitMQ"], source_excerpt="we lost 40% of events",
        )
        self.assertTrue(entry["id"].startswith("dl_"))
        self.assertEqual(entry["rejected_alternatives"], ["RabbitMQ"])
        self.assertEqual(entry["aliases"], [])
        self.assertIsNone(entry["supersedes"])
        self.assertEqual(len(ledger["entries"]), 1)

    def test_add_entry_rejects_bad_confidence(self):
        ledger = dl.empty_ledger()
        with self.assertRaises(ValueError):
            dl.add_entry(
                ledger, "d", "r", ["t"], "pr", "ref", "MAYBE", "run-1", "cursor-1",
            )

    def test_add_entry_rejects_bad_source_type(self):
        ledger = dl.empty_ledger()
        with self.assertRaises(ValueError):
            dl.add_entry(
                ledger, "d", "r", ["t"], "slack-thread", "ref", "EXTRACTED", "run-1", "cursor-1",
            )

    def test_supersedes_sets_symmetric_back_link(self):
        ledger = dl.empty_ledger()
        old = dl.add_entry(ledger, "Use RabbitMQ", "r1", ["queue"], "pr", "ref1", "EXTRACTED", "run-1", "c1")
        new = dl.add_entry(
            ledger, "Use Kafka", "r2", ["queue", "kafka"], "pr", "ref2", "EXTRACTED", "run-2", "c2",
            supersedes=old["id"],
        )
        self.assertEqual(new["supersedes"], old["id"])
        self.assertEqual(old["superseded_by"], new["id"])
        # both entries remain independently addressable -- supersession
        # never deletes or hides the earlier entry.
        self.assertEqual(len(ledger["entries"]), 2)

    def test_supersedes_rejects_nonexistent_target(self):
        ledger = dl.empty_ledger()
        with self.assertRaises(ValueError):
            dl.add_entry(
                ledger, "d", "r", ["t"], "pr", "ref", "EXTRACTED", "run-1", "c1",
                supersedes="dl_does_not_exist",
            )

    def test_never_merges_only_adds(self):
        """Constraint 4: a second add-entry call never mutates the first --
        two distinct entries always coexist unless explicitly aliased."""
        ledger = dl.empty_ledger()
        dl.add_entry(ledger, "Use Kafka", "r1", ["kafka"], "pr", "ref1", "EXTRACTED", "run-1", "c1")
        dl.add_entry(ledger, "Use Kafka again", "r2", ["kafka"], "pr", "ref2", "EXTRACTED", "run-2", "c2")
        self.assertEqual(len(ledger["entries"]), 2)


class AliasTests(unittest.TestCase):
    def test_alias_requires_both_entries_to_exist(self):
        ledger = dl.empty_ledger()
        e1 = dl.add_entry(ledger, "d1", "r1", ["t"], "pr", "ref1", "EXTRACTED", "run-1", "c1")
        with self.assertRaises(ValueError):
            dl.add_alias(ledger, e1["id"], "dl_does_not_exist", "INFERRED", "run-2")
        with self.assertRaises(ValueError):
            dl.add_alias(ledger, "dl_does_not_exist", e1["id"], "INFERRED", "run-2")

    def test_alias_never_deletes_the_source_entry(self):
        """'a superseded object remains addressable' (graph-engineering-paper
        invariant this design explicitly cites)."""
        ledger = dl.empty_ledger()
        e1 = dl.add_entry(ledger, "d1", "r1", ["t"], "pr", "ref1", "EXTRACTED", "run-1", "c1")
        e2 = dl.add_entry(ledger, "d2", "r2", ["t"], "pr", "ref2", "EXTRACTED", "run-2", "c2")
        dl.add_alias(ledger, e1["id"], e2["id"], "INFERRED", "run-3")
        self.assertEqual(len(ledger["entries"]), 2, "alias must not delete the merged-from entry")
        self.assertEqual(len(e1["aliases"]), 1)
        self.assertEqual(e1["aliases"][0]["entry_id"], e2["id"])
        self.assertEqual(e1["aliases"][0]["merge_confidence"], "INFERRED")

    def test_alias_rejects_bad_merge_confidence(self):
        ledger = dl.empty_ledger()
        e1 = dl.add_entry(ledger, "d1", "r1", ["t"], "pr", "ref1", "EXTRACTED", "run-1", "c1")
        e2 = dl.add_entry(ledger, "d2", "r2", ["t"], "pr", "ref2", "EXTRACTED", "run-2", "c2")
        with self.assertRaises(ValueError):
            dl.add_alias(ledger, e1["id"], e2["id"], "CERTAIN", "run-3")


class CursorAndTombstoneTests(unittest.TestCase):
    def test_advance_cursor_creates_then_updates(self):
        ledger = dl.empty_ledger()
        dl.advance_cursor(ledger, "github-prs", "sha-1")
        self.assertEqual(len(ledger["run_state"]["cursors"]), 1)
        dl.advance_cursor(ledger, "github-prs", "sha-2")
        self.assertEqual(len(ledger["run_state"]["cursors"]), 1, "same stream_id updates in place")
        self.assertEqual(ledger["run_state"]["cursors"][0]["last_processed_id"], "sha-2")

    def test_advance_cursor_separate_streams_coexist(self):
        ledger = dl.empty_ledger()
        dl.advance_cursor(ledger, "github-prs", "sha-1")
        dl.advance_cursor(ledger, "postmortems-drive", "doc-9")
        self.assertEqual(len(ledger["run_state"]["cursors"]), 2)

    def test_reject_source_tombstones(self):
        ledger = dl.empty_ledger()
        dl.reject_source(ledger, "github-prs", "pr-42", "run-1", "no real decision in it")
        self.assertTrue(dl.is_tombstoned(ledger, "github-prs", "pr-42"))
        self.assertFalse(dl.is_tombstoned(ledger, "github-prs", "pr-43"))

    def test_reject_source_is_terminal_without_override(self):
        ledger = dl.empty_ledger()
        dl.reject_source(ledger, "github-prs", "pr-42", "run-1", "first look: nothing here")
        with self.assertRaises(ValueError):
            dl.reject_source(ledger, "github-prs", "pr-42", "run-2", "second look: actually something")

    def test_reject_source_override_replaces_tombstone(self):
        ledger = dl.empty_ledger()
        dl.reject_source(ledger, "github-prs", "pr-42", "run-1", "first look")
        dl.reject_source(ledger, "github-prs", "pr-42", "run-2", "reconsidered", override_tombstone=True)
        self.assertEqual(len(ledger["run_state"]["rejected_sources"]), 1)
        self.assertEqual(ledger["run_state"]["rejected_sources"][0]["reason"], "reconsidered")


class QueryTests(unittest.TestCase):
    def _seeded_ledger(self):
        ledger = dl.empty_ledger()
        dl.add_entry(
            ledger, "Use Kafka not RabbitMQ", "RabbitMQ failed under our load profile",
            ["kafka", "message-queue", "load-testing"], "postmortem", "docs/pm-1.md", "EXTRACTED",
            "run-1", "cursor-1",
        )
        dl.add_entry(
            ledger, "Deny legal sign-off on vendor X", "compliance blocked it",
            ["legal", "vendor-review"], "design-doc", "docs/dd-1.md", "EXTRACTED", "run-1", "cursor-1",
        )
        dl.advance_cursor(ledger, "github-prs", "sha-99")
        return ledger

    def test_query_matches_by_topic_overlap(self):
        ledger = self._seeded_ledger()
        aspects = [{"aspect_id": "asp_1", "topics": ["kafka", "throughput"]}]
        result = dl.query_ledger(ledger, aspects)
        self.assertFalse(result["stopped_early"])
        self.assertEqual(len(result["results"]), 1)
        r = result["results"][0]
        self.assertEqual(r["total_entries"], 2)
        self.assertEqual(len(r["candidates"]), 1)
        self.assertEqual(r["candidates"][0]["matched_topics"], ["kafka"])

    def test_query_never_writes_dispositions(self):
        """Reading the query candidates must never itself resolve a hit --
        turning a candidate into a disposed hit is a separate, human-gated
        call to record_disposition."""
        ledger = self._seeded_ledger()
        aspects = [{"aspect_id": "asp_1", "topics": ["kafka"]}]
        dl.query_ledger(ledger, aspects)
        self.assertEqual(ledger["hit_dispositions"], [])

    def test_query_zero_hits_still_reports_coverage(self):
        """The false-absence fix: zero hits on an aspect always carries its
        own coverage caveat, never reads as blanket clearance."""
        ledger = self._seeded_ledger()
        aspects = [{"aspect_id": "asp_2", "topics": ["frontend-css"]}]
        result = dl.query_ledger(ledger, aspects)
        r = result["results"][0]
        self.assertEqual(r["candidates"], [])
        self.assertEqual(r["total_entries"], 2)
        self.assertIn("covers_through", r)
        self.assertIsNotNone(r["covers_through"])

    def test_min_evidence_required_drops_weak_candidates(self):
        ledger = self._seeded_ledger()
        aspects = [{"aspect_id": "asp_1", "topics": ["kafka"]}]
        budget = dict(dl._DEFAULT_BUDGET, min_evidence_required=2)
        result = dl.query_ledger(ledger, aspects, budget=budget)
        # only 1 topic token overlaps ("kafka") -- below min_evidence_required=2
        self.assertEqual(result["results"][0]["candidates"], [])
        # but the entry is still counted as in-scope (it did overlap on 1 token)
        self.assertEqual(result["results"][0]["entries_in_scope_for_this_aspect"], 1)

    def test_wall_clock_budget_exhaustion_marks_remaining_aspects_unscanned(self):
        ledger = self._seeded_ledger()
        aspects = [
            {"aspect_id": "asp_1", "topics": ["kafka"]},
            {"aspect_id": "asp_2", "topics": ["legal"]},
        ]
        budget = dict(dl._DEFAULT_BUDGET, max_wall_clock_ms=-1)  # already expired
        result = dl.query_ledger(ledger, aspects, budget=budget)
        self.assertTrue(result["stopped_early"])
        self.assertEqual(result["stop_reason"], "max_wall_clock_ms")
        # asp_1 trips the budget mid-scan -- it must still carry an honest
        # partial-scan note, never read as "fully scanned, zero matches".
        asp_1, asp_2 = result["results"]
        self.assertEqual(asp_1["entries_in_scope_for_this_aspect"], 0)
        self.assertIn("partial scan", asp_1["note"])
        # asp_2 never started at all.
        self.assertIsNone(asp_2["entries_in_scope_for_this_aspect"])
        self.assertIn("not scanned", asp_2["note"])


class DispositionTests(unittest.TestCase):
    def _ledger_with_one_entry(self):
        ledger = dl.empty_ledger()
        entry = dl.add_entry(
            ledger, "Use Kafka", "r", ["kafka"], "pr", "ref", "EXTRACTED", "run-1", "c1",
        )
        return ledger, entry["id"]

    def test_proceed_tier_only_accepts_accepted(self):
        ledger, entry_id = self._ledger_with_one_entry()
        dl.record_disposition(
            ledger, "ihm_1", "pkg_1", "asp_1", entry_id, "proceed", "accepted", "human:alice",
        )
        with self.assertRaises(ValueError):
            dl.record_disposition(
                ledger, "ihm_2", "pkg_1", "asp_1", entry_id, "proceed", "dismissed", "human:alice",
            )

    def test_escalate_tier_cannot_be_dismissed(self):
        ledger, entry_id = self._ledger_with_one_entry()
        with self.assertRaises(ValueError):
            dl.record_disposition(
                ledger, "ihm_1", "pkg_1", "asp_1", entry_id, "escalate", "dismissed", "human:alice",
                reason="not sure",
            )

    def test_revise_tier_allows_all_three(self):
        ledger, entry_id = self._ledger_with_one_entry()
        for i, disposition in enumerate(("dismissed", "accepted", "escalated")):
            dl.record_disposition(
                ledger, "ihm_{}".format(i), "pkg_1", "asp_1", entry_id, "revise", disposition,
                "human:alice", reason="because",
            )
        self.assertEqual(len(ledger["hit_dispositions"]), 3)

    def test_revise_tier_requires_reason(self):
        ledger, entry_id = self._ledger_with_one_entry()
        with self.assertRaises(ValueError):
            dl.record_disposition(
                ledger, "ihm_1", "pkg_1", "asp_1", entry_id, "revise", "dismissed", "human:alice",
            )

    def test_proceed_tier_reason_optional(self):
        ledger, entry_id = self._ledger_with_one_entry()
        record = dl.record_disposition(
            ledger, "ihm_1", "pkg_1", "asp_1", entry_id, "proceed", "accepted", "human:alice",
        )
        self.assertEqual(record["reason"], "")

    def test_disposition_requires_matching_ledger_entry(self):
        ledger, _ = self._ledger_with_one_entry()
        with self.assertRaises(ValueError):
            dl.record_disposition(
                ledger, "ihm_1", "pkg_1", "asp_1", "dl_does_not_exist", "proceed", "accepted",
                "human:alice",
            )

    def test_unresolved_hit_is_absence_not_a_disposition_value(self):
        """A hit nobody has acted on yet must never appear in
        hit_dispositions[] at all -- 'unresolved' is a property the
        *consuming* package computes from absence, not a disposition value
        decision_ledger.py itself ever writes."""
        ledger, entry_id = self._ledger_with_one_entry()
        aspects = [{"aspect_id": "asp_1", "topics": ["kafka"]}]
        dl.query_ledger(ledger, aspects)  # a hit exists, but nobody dispositioned it
        self.assertEqual(ledger["hit_dispositions"], [])
        for legal in dl._LEGAL_DISPOSITIONS.values():
            self.assertNotIn("unresolved", legal)


class ValidateLedgerTests(unittest.TestCase):
    def test_valid_ledger_has_no_problems(self):
        ledger = dl.empty_ledger()
        dl.add_entry(ledger, "d", "r", ["t"], "pr", "ref", "EXTRACTED", "run-1", "c1")
        self.assertEqual(dl.validate_ledger(ledger), [])

    def test_missing_required_field_is_flagged(self):
        ledger = dl.empty_ledger()
        ledger["entries"].append({"id": "dl_x", "decision": "d"})  # missing reasoning/confidence/etc.
        problems = dl.validate_ledger(ledger)
        self.assertTrue(any("reasoning" in p for p in problems))

    def test_duplicate_id_is_flagged(self):
        ledger = dl.empty_ledger()
        dl.add_entry(ledger, "d1", "r1", ["t"], "pr", "ref1", "EXTRACTED", "run-1", "c1", entry_id="dl_dup")
        dl.add_entry(ledger, "d2", "r2", ["t"], "pr", "ref2", "EXTRACTED", "run-1", "c1", entry_id="dl_dup")
        problems = dl.validate_ledger(ledger)
        self.assertTrue(any("duplicate id" in p for p in problems))

    def test_illegal_disposition_written_directly_is_flagged(self):
        """validate_ledger is the last line of defense if a ledger file is
        ever hand-edited outside decision_ledger.py's own writers."""
        ledger = dl.empty_ledger()
        entry = dl.add_entry(ledger, "d", "r", ["t"], "pr", "ref", "EXTRACTED", "run-1", "c1")
        ledger["hit_dispositions"].append({
            "hit_id": "ihm_1", "package_id": "pkg_1", "aspect_id": "asp_1",
            "matched_decision": entry["id"], "tier": "proceed", "disposition": "dismissed",
            "reason": "", "by": "human:alice", "at": "2026-08-05T00:00:00Z",
        })
        problems = dl.validate_ledger(ledger)
        self.assertTrue(any("not legal for tier" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
