from datetime import date
from pathlib import Path
from types import SimpleNamespace
import socket
import tempfile
import unittest
from unittest.mock import patch

import yaml
from seed import annual_archive as annual, annual_access as archive_access, archive_release, cli, merge, replay, source


class PreservationReleaseTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.database = self.root / '2025/2025.sqlite'
        self.database.parent.mkdir()
        self.day = '2025-01-01'
        self.raw = b';News\n*A reported event. [https://example.test (Publisher)]\n'
        source.store(self.raw, title='Portal:Current events/2025 January 1', revision_id=123,
                     timestamp=None, cache=self.root / 'reference/sources/wikipedia')
        self.seed = self.root / '2025/01/2025-01-01.yaml'
        self.seed.parent.mkdir(parents=True)
        self.seed.write_bytes(yaml.safe_dump({'date': self.day,
            'source_page': {'portal': 'Portal:Current events/2025 January 1', 'language': 'en', 'wikipedia_revision_id': 123},
            'wikipedia': {'categories': {'News': ['A reported event.']}}}).encode())
        self.legacy = self.seed.read_bytes()
        conn = annual.initialize(self.database, 2025)
        annual.ingest_day(conn, self.day, self.root)
        conn.close()
        # These small fixtures test publication/access/retirement, not the
        # already separately tested complete-calendar annual verifier.
        self.transfer = {'verified': True, 'calendar_complete': True, 'unresolved_warnings': {},
                         'unknown_heading_roles': 0, 'prior_candidate_differences_or_missing': [],
                         'legacy_replay_differences': [], 'year': 2025, 'events': 1,
                         'replacement_blockers': ['factual_coverage_review_not_recorded']}
        for p in (patch.object(annual, 'verify', return_value=self.transfer),
                  patch.object(socket.socket, 'connect', side_effect=AssertionError('network forbidden')),
                  patch.object(archive_release.subprocess, 'run', return_value=SimpleNamespace(stdout='checkpoint\n'))):
            p.start()
            self.addCleanup(p.stop)

    def test_lossless_cutover_access_and_pre_network_write_protection(self):
        report = archive_release.prepare(self.database, self.root)
        self.assertFalse(report['independent_review_required'])
        archive_release.retire(self.database, self.root)
        self.assertFalse(self.seed.exists())
        self.assertEqual(self.legacy, archive_access.legacy_bytes(self.day, self.root))
        self.assertEqual(self.raw, archive_access.wikipedia(self.day, self.root)[1])
        self.assertEqual(self.raw, archive_access.revision(123, self.root)[1])
        with patch.object(merge, 'REPO_ROOT', self.root):
            self.assertTrue(merge.already_saved(date(2025, 1, 1)))
            self.assertEqual([], cli.discover_work(start=date(2025, 1, 1), end=date(2025, 1, 1), target='all', max_bytes=500))
            with self.assertRaisesRegex(ValueError, 'published annual'):
                merge.save(date(2025, 1, 1), {})
            with patch.object(cli, 'fetch_day', side_effect=AssertionError('must fail before acquisition')):
                with self.assertRaisesRegex(ValueError, 'published annual'):
                    cli.fetch_and_save_day(date(2025, 1, 1), no_gdelt=True, monthly_cache={})
        with patch.object(replay, 'REPO_ROOT', self.root):
            self.assertTrue(replay.seed_exists(self.day))
            self.assertEqual(123, replay.seed_doc(self.day)['source_page']['wikipedia_revision_id'])
            self.assertEqual('A reported event.', replay.candidate(self.day)['categories'][0]['entries'][0]['text'])
        with patch.object(source, 'ROOT', self.root), patch.object(source, 'CACHE', self.root / 'reference/sources/wikipedia'):
            self.assertEqual(self.raw, source.revision(123, cache=source.CACHE)[1])
        self.assertEqual(0, archive_release.retire(self.database, self.root)['removed_files'])

    def test_retirement_preflights_every_file_and_preserves_modified_original(self):
        archive_release.prepare(self.database, self.root)
        self.seed.write_bytes(self.legacy + b'changed')
        with self.assertRaisesRegex(ValueError, 'changed since preservation'):
            archive_release.retire(self.database, self.root)
        self.assertTrue((self.root / 'reference/sources/wikipedia/wikitext/123.wiki').exists())
        self.assertTrue(self.seed.exists())

    def test_year_folder_discovery_and_legacy_layout_fallback(self):
        archive_release.prepare(self.database, self.root)
        old = self.root / 'archive/2025.sqlite'
        old.parent.mkdir()
        old.write_bytes(self.database.read_bytes())
        self.assertEqual([self.database], archive_access.annual_paths(self.root))
        self.assertEqual(self.database, archive_access.published_path(self.day, self.root))
        self.database.unlink()
        self.assertEqual([old], archive_access.annual_paths(self.root))
        self.assertEqual(old, archive_access.published_path(self.day, self.root))
        self.assertEqual(self.raw, archive_access.revision(123, self.root)[1])
        self.assertEqual(self.legacy, archive_access.legacy_bytes(self.day, self.root))

    def test_shared_cache_stays_and_publication_does_not_claim_factual_verification(self):
        another = self.root / '2024/12/2024-12-31.yaml'
        another.parent.mkdir(parents=True)
        another.write_text(yaml.safe_dump({'source_page': {'wikipedia_revision_id': 123}}))
        archive_release.prepare(self.database, self.root)
        archive_release.retire(self.database, self.root)
        self.assertTrue((self.root / 'reference/sources/wikipedia/wikitext/123.wiki').exists())
        conn = annual.connect(self.database, readonly=True)
        try:
            report = archive_release.verify(conn)
            self.assertFalse(report['independent_review_complete'])
            self.assertFalse(report['finished_historical_yearbook'])
            first = archive_release.render(conn, 'f' * 64)
            self.assertEqual(first, archive_release.render(conn, 'f' * 64))
            self.assertIn(b'Source-preservation edition', first)
            self.assertNotIn(b'old daily files remain', first)
            self.assertIn(b'Archived source account', first)
        finally:
            conn.close()


if __name__ == '__main__':
    unittest.main()
