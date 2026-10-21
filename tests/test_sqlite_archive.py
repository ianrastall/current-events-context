import copy
import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference/expansion"))
import build
from seed import extract, replay, sqlite_archive

spec = importlib.util.spec_from_file_location("validator", ROOT / "reference/schema/validate.py")
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class SqliteArchiveTests(unittest.TestCase):
    def test_extraction_round_trip_with_gdelt_and_byte_idempotence(self):
        conn = sqlite_archive.connect(":memory:")
        raw_text = (ROOT / "provisional/extraction-v1/2026/01/2026-01-16.yaml").read_text(encoding="utf-8")
        doc = yaml.safe_load(raw_text)
        doc_with_gdelt = copy.deepcopy(doc)
        doc_with_gdelt["gdelt"] = {
            "queried_at": "2026-01-17T00:00:00Z",
            "article_count": 1,
            "articles": [{"title": "Test Article", "url": "https://example.test/article"}],
        }

        sqlite_archive.import_extraction_doc(conn, doc_with_gdelt)
        exported = sqlite_archive.export_extraction_doc(conn, "2026-01-16")

        replay.extraction_validator().validate(exported)
        self.assertEqual(doc_with_gdelt, exported)
        self.assertEqual(replay.dump(doc_with_gdelt), replay.dump(exported))

        # Re-importing without GDELT should cleanly remove GDELT and match original bytes
        sqlite_archive.import_extraction_doc(conn, doc)
        exported_no_gdelt = sqlite_archive.export_extraction_doc(conn, "2026-01-16")
        self.assertEqual(doc, exported_no_gdelt)
        self.assertEqual(raw_text, replay.dump(exported_no_gdelt))

    def test_rendered_html_fallback_round_trip(self):
        conn = sqlite_archive.connect(":memory:")
        html = (
            '<div class="current-events-main" aria-label="January 1">'
            '<ul><li>Topic<ul><li><a href="/wiki/Test">Test</a> event '
            '<a href="https://example.test/cite">(Example)</a></li></ul></li></ul></div>'
        )
        source_meta = {
            "page": "Portal:Current events/January 2002",
            "revision_id": None,
            "revision_timestamp": None,
            "source_mode": "rendered_html",
            "source_sha256": extract.fingerprint(html),
        }
        doc = extract.extract(html, date="2002-01-01", source=source_meta)
        sqlite_archive.import_extraction_doc(conn, doc)
        exported = sqlite_archive.export_extraction_doc(conn, "2002-01-01")

        replay.extraction_validator().validate(exported)
        self.assertIsNone(exported["source_page"]["revision_id"])
        self.assertEqual("rendered_html", exported["source_page"]["source_mode"])
        self.assertEqual(doc, exported)
        self.assertEqual(replay.dump(doc), replay.dump(exported))

    def test_synthesis_2_2_round_trip_and_byte_idempotence(self):
        conn = sqlite_archive.connect(":memory:")
        for day in ("2026-01-01", "2026-01-15", "2026-01-16"):
            path = ROOT / "expanded" / day[:4] / day[5:7] / f"{day}.yaml"
            raw_text = path.read_text(encoding="utf-8")
            doc = yaml.safe_load(raw_text)
            sqlite_archive.import_synthesis_doc(conn, doc)
            exported = sqlite_archive.export_synthesis_doc(conn, day)

            self.assertEqual([], validator.schema_errors(exported))
            self.assertEqual([], validator.cross_ref_errors(exported))
            self.assertEqual([], validator.related_errors(exported, ROOT / "expanded"))
            self.assertEqual(doc, exported)
            self.assertEqual(raw_text, build.dump(exported))

    def test_fts5_search_and_rst_daily_and_monthly_views(self):
        conn = sqlite_archive.connect(":memory:")
        for day in ("2026-01-15", "2026-01-16"):
            path = ROOT / "expanded/2026/01" / f"{day}.yaml"
            sqlite_archive.import_synthesis_doc(conn, yaml.safe_load(path.read_text(encoding="utf-8")))

        hits = sqlite_archive.search_synthesis_events(conn, "Yoon")
        self.assertEqual(1, len(hits))
        self.assertEqual("evt-2026-01-16-008", hits[0]["event_id"])

        doc_16 = sqlite_archive.export_synthesis_doc(conn, "2026-01-16")
        daily_rst = sqlite_archive.render_synthesis_rst(doc_16)
        self.assertIn(".. _day-2026-01-16:", daily_rst)
        self.assertIn(".. _evt-2026-01-16-001:", daily_rst)
        self.assertIn(".. list-table:: Key Data", daily_rst)
        self.assertIn(":ref:`evt-2026-01-15-013`", daily_rst)
        self.assertIn(".. [1]", daily_rst)

        monthly_rst = sqlite_archive.render_monthly_rst(conn, "2026-01")
        self.assertIn(".. _month-2026-01:", monthly_rst)
        self.assertIn(":Days Covered: 2 (2026-01-15 to 2026-01-16)", monthly_rst)
        self.assertIn(".. _day-summary-2026-01-16:", monthly_rst)

    def test_per_day_compact_sqlite_multisource_and_rollup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            day1_db = sqlite_archive.build_day_sqlite(
                "2000-01-01",
                db_path=tmp / "2000-01-01.sqlite",
            )
            day2_db = sqlite_archive.build_day_sqlite(
                "2000-01-02",
                db_path=tmp / "2000-01-02.sqlite",
            )
            self.assertTrue(day1_db.exists())
            self.assertTrue(day2_db.exists())

            conn1 = sqlite3.connect(str(day1_db))
            conn1.row_factory = sqlite3.Row
            try:
                page_size = conn1.execute("PRAGMA page_size").fetchone()[0]
                self.assertEqual(1024, page_size)
                raw_cnt = conn1.execute("SELECT COUNT(*) FROM raw_sources WHERE date = '2000-01-01'").fetchone()[0]
                feed_cnt = conn1.execute("SELECT COUNT(*) FROM structured_feed_items WHERE date = '2000-01-01'").fetchone()[0]
                ent_cnt = conn1.execute("SELECT COUNT(*) FROM synthesis_actors_entities WHERE event_id LIKE 'evt-2000-01-01-%'").fetchone()[0]
                tier1_cnt = conn1.execute("SELECT COUNT(*) FROM synthesis_events WHERE date = '2000-01-01' AND tier = 1").fetchone()[0]
                self.assertGreaterEqual(raw_cnt, 7)
                self.assertGreaterEqual(feed_cnt, 30)
                self.assertGreater(ent_cnt, 10)
                self.assertGreaterEqual(tier1_cnt, 2)

                exported_1 = sqlite_archive.export_synthesis_doc(conn1, "2000-01-01")
                self.assertEqual([], validator.schema_errors(exported_1))
                self.assertEqual([], validator.cross_ref_errors(exported_1))
            finally:
                conn1.close()

            rollup_db = sqlite_archive.rollup_sqlite([day1_db, day2_db], tmp / "2000-01.sqlite")
            rconn = sqlite_archive.connect(rollup_db)
            try:
                hits = sqlite_archive.search_synthesis_events(rconn, "Kipawa")
                self.assertEqual(1, len(hits))
                self.assertEqual("evt-2000-01-01-010", hits[0]["event_id"])
                monthly_rst = sqlite_archive.render_monthly_rst(rconn, "2000-01")
                self.assertIn(":Days Covered: 2 (2000-01-01 to 2000-01-02)", monthly_rst)
            finally:
                rconn.close()


if __name__ == "__main__":
    unittest.main()
