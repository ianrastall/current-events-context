from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

import yaml

from seed import annual_archive as annual, source, sqlite_archive


class AnnualArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "annual.sqlite"
        self.conn = annual.initialize(self.path, 2025)
        self.addCleanup(self.conn.close)
        self.network = patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def make_day(self, day="2025-01-01", revision=123):
        raw = (';News\n*[[Topic]]\n**[[Country|The country]] has a mispelt event. '
               '[https://example.test/a (Publisher)]\n*[[Ambiguous]]\n')
        title = f"Portal:Current events/{day}"
        source.store(raw.encode(), title=title, revision_id=revision, timestamp=None,
                     cache=self.root / "reference/sources/wikipedia")
        doc = {"date": day, "source_page": {"portal": title, "language": "en", "wikipedia_revision_id": revision},
               "wikipedia": {"categories": {"News": ["Original flat baseline"]}},
               "gdelt": {"queried_at": "original", "article_count": 1, "articles": [{"title": "preserved"}]}}
        path = self.root / day[:4] / day[5:7] / f"{day}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = yaml.safe_dump(doc, sort_keys=False).replace("\n", "\r\n").encode()
        path.write_bytes(payload)
        return path, payload

    def test_self_contained_round_trip_citations_warnings_and_idempotence(self):
        path, payload = self.make_day()
        annual.ingest_day(self.conn, "2025-01-01", self.root)
        report = annual.verify(self.conn, complete=False)
        self.assertFalse(report["replacement_ready"])
        self.assertGreater(report["unknown_roles"], 0)
        self.assertEqual(1, self.conn.execute("SELECT count(*) FROM event_citations WHERE url='https://example.test/a'").fetchone()[0])
        self.assertEqual(payload, annual.input_bytes(self.conn, "2025/01/2025-01-01.yaml"))
        exported = sqlite_archive.export_extraction_doc(self.conn, "2025-01-01")
        self.assertEqual("original", exported["gdelt"]["queried_at"])
        self.assertIn("mispelt", exported["categories"][0]["entries"][1]["text"])
        counts = tuple(self.conn.execute("SELECT (SELECT count(*) FROM archive_inputs),(SELECT count(*) FROM extraction_entries),(SELECT count(*) FROM archive_events_fts)").fetchone())
        annual.ingest_day(self.conn, "2025-01-01", self.root)
        self.assertEqual(counts, tuple(self.conn.execute("SELECT (SELECT count(*) FROM archive_inputs),(SELECT count(*) FROM extraction_entries),(SELECT count(*) FROM archive_events_fts)").fetchone()))
        path.unlink()
        # Verification does not reopen original daily/cache files.
        self.assertEqual(report, annual.verify(self.conn, complete=False))

    def test_day_failure_rolls_back_bridge_import_and_inputs(self):
        self.make_day()
        original = sqlite_archive.import_extraction_doc

        def failing(conn, doc):
            original(conn, doc)
            raise RuntimeError("failure after nested bridge transaction")

        with patch.object(sqlite_archive, "import_extraction_doc", side_effect=failing):
            with self.assertRaisesRegex(RuntimeError, "nested bridge"):
                annual.ingest_day(self.conn, "2025-01-01", self.root)
        for table in ("sources_wikipedia", "extraction_entries", "day_ingestions", "archive_events_fts"):
            self.assertEqual(0, self.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
        self.assertEqual(0, self.conn.execute("SELECT count(*) FROM archive_inputs WHERE date IS NOT NULL").fetchone()[0])

    def test_drift_corruption_wrong_year_and_incomplete_calendar_rejected(self):
        path, payload = self.make_day()
        annual.ingest_day(self.conn, "2025-01-01", self.root)
        with self.assertRaisesRegex(ValueError, "calendar"):
            annual.verify(self.conn)
        with self.assertRaisesRegex(ValueError, "outside"):
            annual.ingest_day(self.conn, "2024-12-31", self.root)
        path.write_bytes(payload + b"\n")
        with self.assertRaisesRegex(ValueError, "input drift"):
            annual.ingest_day(self.conn, "2025-01-01", self.root)
        with self.conn:
            self.conn.execute("UPDATE extraction_entries SET text='corrupted' WHERE role='event'")
        with self.assertRaisesRegex(ValueError, "round-trip"):
            annual.verify(self.conn, complete=False)

    def test_atomic_build_preserves_existing_archive_on_failure(self):
        self.conn.close()
        previous = self.path.read_bytes()
        with patch.object(annual, "ingest_day", side_effect=RuntimeError("simulated failure")):
            with self.assertRaisesRegex(RuntimeError, "simulated failure"):
                annual.build_year(2025, self.path)
        self.assertEqual(previous, self.path.read_bytes())
        self.assertEqual([], list(self.root.glob(".annual-*.sqlite")))

    def test_embedded_payload_and_search_corruption_are_detected(self):
        self.make_day()
        annual.ingest_day(self.conn, "2025-01-01", self.root)
        with self.conn:
            self.conn.execute("UPDATE archive_events_fts SET text='wrong'")
        with self.assertRaisesRegex(ValueError, "search index"):
            annual.verify(self.conn, complete=False)
        with self.conn:
            self.conn.execute("UPDATE archive_blobs SET payload=? WHERE sha256=(SELECT sha256 FROM archive_inputs WHERE role='legacy_seed')", (b"bad",))
        with self.assertRaisesRegex(ValueError, "input hash"):
            annual.verify(self.conn, complete=False)

    def test_source_rebuild_refuses_to_discard_research(self):
        with self.conn:
            self.conn.execute("INSERT INTO generation_runs VALUES(?,?,?,?,?,?,?,?,?)",
                              ("research-1", "2025-01-01", None, "test", "1", "retrospective", None, "[]", "0" * 64))
        previous = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "research or external feeds"):
            annual.build_year(2025, self.path)
        self.assertEqual(previous, self.path.read_bytes())

    def test_scoped_factual_review_is_guarded_and_never_approves_the_year(self):
        self.make_day()
        annual.ingest_day(self.conn, "2025-01-01", self.root)
        row = dict(self.conn.execute("SELECT * FROM event_overview WHERE role='event'").fetchone())
        record = {'id': 'fixture-review', 'locator': annual.review_locator(row),
                  'event_sha256': annual.structured_hash(row), 'scope': 'One precisely identified claim',
                  'assessment': 'supported', 'checked_on': '2026-10-21', 'note': 'Source supports only this scope.',
                  'evidence': [{'url': 'https://example.test/a', 'publisher': 'Fixture',
                                'publication_date': None, 'access_status': 'opened', 'note': 'Body checked.'}]}
        annual.record_review(self.conn, record)
        annual.record_review(self.conn, record)
        report = annual.verify(self.conn, complete=False)
        self.assertEqual(1, report['scoped_factual_reviews'])
        self.assertFalse(report['yearbook_ready'])
        self.assertFalse(annual.coverage_report(self.conn)['factual_review_complete'])
        changed = dict(record, id='stale', event_sha256='0' * 64)
        with self.assertRaisesRegex(ValueError, 'extraction drift'):
            annual.record_review(self.conn, changed)
        with self.conn:
            self.conn.execute("UPDATE review_evidence SET note='corrupt'")
        with self.assertRaisesRegex(ValueError, 'evidence corruption'):
            annual.verify(self.conn, complete=False)

    def test_candidate_reconciliation_rejects_event_loss(self):
        self.make_day()
        annual.ingest_day(self.conn, '2025-01-01', self.root)
        doc = sqlite_archive.export_extraction_doc(self.conn, '2025-01-01')
        import copy
        other = copy.deepcopy(doc)
        other['categories'][0]['entries'].pop()
        with self.assertRaisesRegex(ValueError, 'entry/category coverage'):
            annual.compare_candidate(doc, other)


if __name__ == "__main__":
    unittest.main()
