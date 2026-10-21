import copy
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from seed import annual_archive as annual, extract, sqlite_archive, yearbook


class YearbookTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.conn = annual.initialize(Path(temporary.name) / "annual.sqlite", 2025)
        self.addCleanup(self.conn.close)
        self.network = patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden"))
        self.network.start()
        self.addCleanup(self.network.stop)
        raw = ";News\n*[[Topic]]\n**A source error.\n*An unchecked event.\n"
        meta = {"page": "Portal:Current events/2025 January 1", "revision_id": 123,
                "revision_timestamp": None, "source_mode": "wikitext", "source_sha256": annual.digest(raw.encode())}
        doc = extract.extract(raw, date="2025-01-01", source=meta, source_templates=True)
        sqlite_archive.import_extraction_doc(self.conn, doc)
        self.row = dict(self.conn.execute("SELECT * FROM event_overview WHERE role='event' ORDER BY ord").fetchone())
        self.record = {"contract": yearbook.VERSION, "id": "fixture-review", "locator": annual.review_locator(self.row),
                       "event_sha256": annual.structured_hash(self.row), "checked_on": "2026-10-21",
                       "display_date": "2025-01-02", "state": "complete", "statement": "A corrected account.",
                       "note": "Original date and wording differ.", "model": None,
                       "workflow": "fixture", "perspective": "retrospective",
                       "dispositions": [{"start": 0, "end": len(self.row["text"]), "assessment": "contradicted",
                                         "note": "Publisher confirms the different date and event wording.", "evidence": [0]}],
                       "evidence": [{"url": "https://example.test/report", "publisher": "Fixture publisher",
                                     "publication_date": "2025-01-02", "access_status": "opened",
                                     "locator": "Paragraph 1", "note": "Fixture evidence only."}]}

    def test_partial_coverage_and_unsubstantiated_assertions_cannot_complete_review(self):
        for change in ("gap", "missing_end", "unsubstantiated", "bad_evidence", "not_opened"):
            record = copy.deepcopy(self.record)
            if change == "gap":
                record["dispositions"][0]["start"] = 1
            elif change == "missing_end":
                record["dispositions"][0]["end"] -= 1
            elif change == "unsubstantiated":
                record["dispositions"][0]["assessment"] = "unsubstantiated"
            elif change == "bad_evidence":
                record["dispositions"][0]["evidence"] = [9]
            else:
                record["evidence"][0]["access_status"] = "blocked"
            with self.subTest(change=change), self.assertRaises(ValueError):
                yearbook.record_review(self.conn, record)
        self.assertEqual(0, self.conn.execute("SELECT count(*) FROM archive_inputs WHERE role=?", (yearbook.ROLE,)).fetchone()[0])

    def test_originals_immutable_queue_and_independent_gate_counts(self):
        yearbook.record_review(self.conn, self.record)
        yearbook.record_review(self.conn, self.record)
        report = yearbook.review_report(self.conn)
        self.assertEqual(1, report["editorial_resolutions"])
        self.assertEqual(1, report["full_event_reviews_complete"])
        self.assertEqual(1, report["events_remaining_before_factual_gate"])
        self.assertEqual(2, report["source_events_without_attached_citations"])
        self.assertEqual(1, len(report["uncited_events_without_editorial_evidence"]))
        self.assertFalse(report["every_event_independently_checked"])
        self.assertFalse(report["replacement_ready"])
        self.assertEqual("An unchecked event.", next(yearbook.queue(self.conn))["text"])
        self.assertEqual(self.row["text"], annual.locate_review_event(self.conn, self.record["locator"])["text"])
        changed = copy.deepcopy(self.record)
        changed["statement"] = "Replacement without migration."
        with self.assertRaisesRegex(ValueError, "immutable"):
            yearbook.record_review(self.conn, changed)

    def test_replay_guards_detect_source_and_implementation_drift(self):
        record = copy.deepcopy(self.record)
        record["locator"]["source_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "locator drift"):
            yearbook.record_review(self.conn, record)
        yearbook.record_review(self.conn, self.record)
        with patch.object(Path, "read_bytes", return_value=b"changed implementation"):
            with self.assertRaisesRegex(ValueError, "implementation drift"):
                yearbook.load_reviews(self.conn)
        with self.conn:
            self.conn.execute("UPDATE extraction_entries SET text='changed source'")
        with self.assertRaisesRegex(ValueError, "extraction drift"):
            yearbook.load_reviews(self.conn)

    def test_markdown_is_deterministic_complete_and_does_not_hide_source_error(self):
        yearbook.record_review(self.conn, self.record)
        before = self.conn.total_changes
        payload = yearbook.render(self.conn, "f" * 64)
        self.assertEqual(payload, yearbook.render(self.conn, "f" * 64))
        self.assertEqual(before, self.conn.total_changes)
        self.assertNotIn(b"\r", payload)
        self.assertTrue(payload.endswith(b"\n"))
        self.assertFalse(payload.endswith(b"\n\n"))
        text = payload.decode()
        self.assertEqual(2, text.count('<a id="event-'))
        self.assertIn("Original source account: A source error.", text)
        self.assertIn("Editorial date: 2025-01-02", text)
        self.assertIn("full-event review pending", text)
        self.assertIn("Context: Topic", text)
        self.assertIn("Fixture publisher", text)
        self.assertNotIn("<script>", yearbook.safe_text("<script>[x](javascript:bad)</script>"))


if __name__ == "__main__":
    unittest.main()
