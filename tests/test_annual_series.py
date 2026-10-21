from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
import copy
import json
import socket
import tempfile
import unittest
from unittest.mock import patch

import mwparserfromhell as mw
import yaml
from seed import annual_archive as annual, annual_editions, annual_series as series, archive_access, source

ROOT = Path(__file__).resolve().parents[1]


class AnnualSeriesTests(unittest.TestCase):
    def test_comment_boundaries_do_not_hide_live_bullets(self):
        raw = ';News\n*Live assertion. <!-- note -->\n<!-- hidden\n**Hidden assertion.\n*\n-->\n*Live again.\n<nowiki><!--\n*Literal marker.\n--></nowiki>\n'
        self.assertEqual({4, 5}, series.commented_lines(raw))

    def test_approved_nested_assertions_and_commented_source_roles(self):
        folder = ROOT / 'tests/fixtures/annual_series'
        day = '2022-01-14'
        raw = (folder / (day + '.wiki')).read_bytes()
        meta = json.loads((folder / (day + '.json')).read_bytes())
        prior = series.ORIGINAL_MAKE(day, meta, raw, {})
        warning = next(w for w in prior['warnings'] if w['code'] == 'AMBIGUOUS_ROLE')
        role = {k: warning[k] for k in ('date', 'source_sha256', 'category', 'source_path', 'line')}
        role.update(raw_sha256=series.extract.fingerprint(warning['raw']), role='event',
                    interpretation='approved_source_statement', reason='Preserve both complete source assertions at their original depth.')
        config = dict(version=series.VERSION, year=2022, edition_date='2026-10-21', roles=[role], notices=[])
        doc = series.make_profile(config, day, meta, raw, {})
        entries = next(c['entries'] for c in doc['categories'] if c['name'] == warning['category'])
        parent = next(e for e in entries if e['line'] == 11)
        child = next(e for e in entries if e['line'] == 12)
        self.assertEqual(('event', 'event', parent['source_path']), (parent['role'], child['role'], child['parent_path']))
        self.assertEqual(1, series.compare_profile(config, prior, doc)['event_assertion_delta'])
        day = '2021-08-17'
        raw = (folder / (day + '.wiki')).read_bytes()
        meta = json.loads((folder / (day + '.json')).read_bytes())
        config.update(year=2021, roles=[])
        doc = series.make_profile(config, day, meta, raw, {})
        commented = [w for w in doc['warnings'] if w['code'] == 'SOURCE_COMMENTED_ENTRY']
        self.assertEqual(1, len(commented))
        self.assertIn('booster', commented[0]['raw'])
        entry = next(e for c in doc['categories'] for e in c['entries'] if e['line'] == commented[0]['line'])
        self.assertEqual('unknown', entry['role'])
        prior = series.ORIGINAL_MAKE(day, meta, raw, {})
        report = series.compare_profile(config, prior, doc)
        self.assertEqual(-1, report['event_assertion_delta'])
        self.assertEqual('commented_source_non_event', report['source_role_changes'][0]['reason'])

    def test_category_comment_repair_preserves_all_original_entry_fields(self):
        folder = ROOT / 'tests/fixtures/annual_2024'
        raw = (folder / '2024-02-26.wiki').read_bytes()
        meta = json.loads((folder / '2024-02-26.json').read_bytes())
        notices = json.loads((ROOT / 'reference/overrides/2024-preservation.json').read_bytes())
        roles = json.loads((ROOT / 'reference/overrides/2024-extraction.json').read_bytes())
        config = {'version': series.VERSION, 'year': 2024, 'edition_date': '2026-10-21',
                  'roles': roles, 'notices': [{**r, 'action': 'category_comment' if r.get('action') == 'category_comment' else 'preserve_notice'} for r in notices]}
        doc = series.make_profile(config, '2024-02-26', meta, raw, {})
        frozen = annual_editions.make_profile(notices, '2024-02-26', meta, raw, {})
        self.assertEqual(frozen['categories'], doc['categories'])
        prior = series.ORIGINAL_MAKE('2024-02-26', meta, raw, {})
        report = series.compare_profile(config, prior, doc)
        self.assertEqual(0, report['event_leaf_delta'])
        self.assertEqual('Law and crime', report['category_repairs'][0]['to'])
        damaged = copy.deepcopy(doc)
        next(c for c in damaged['categories'] if c['name'] == 'Law and crime')['entries'][0]['citations'] = []
        with self.assertRaises(ValueError):
            series.compare_profile(config, prior, damaged)

    def test_unbulleted_claim_and_orphan_are_preserved_without_event_invention(self):
        folder = ROOT / 'tests/fixtures/annual_series'
        raw = (folder / '2023-12-30.wiki').read_bytes()
        meta = json.loads((folder / '2023-12-30.json').read_bytes())
        config = json.loads((ROOT / series.config_path(2023)).read_bytes())
        with patch.object(socket.socket, 'connect', side_effect=AssertionError('network')):
            doc = series.make_profile(config, '2023-12-30', meta, raw, {})
            repeated = series.make_profile(config, '2023-12-30', meta, raw, {})
        self.assertEqual(doc, repeated)
        self.assertTrue(all(w['resolution'] for w in doc['warnings']))
        unclassified = [w for w in doc['warnings'] if w['interpretation'] == 'unclassified_source_requires_factual_research']
        self.assertEqual(1, len(unclassified))
        self.assertIn('Khan Yunis', unclassified[0]['raw'])
        self.assertFalse(any(e['line'] == unclassified[0]['line'] for c in doc['categories'] for e in c['entries']))
        self.assertEqual(1, sum(w['code'] == 'ORPHAN_TOPIC' for w in doc['warnings']))
        changed = copy.deepcopy(config)
        changed['notices'][-1]['raw_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'locator drift'):
            series.make_profile(changed, '2023-12-30', meta, raw, {})

    def test_literal_currencies_spacing_and_reliability_retention(self):
        cases = {'{{JPY|3.5 billion|link=yes}}': 'JPY 3.5 billion',
                 '{{Indian Rupee|24.68}}': 'INR 24.68', '{{Euro|170 million}}': 'EUR 170 million',
                 '{{nbsp}}': ' ', '{{conv|1.43|C-change}}': '1.43 °C change',
                 '{{convert|1.91|e6km2|sqmi}}': '1.91 million km2'}
        for raw, expected in cases.items():
            self.assertEqual(expected, series.projection(mw.parse(raw).filter_templates()[0]))
        self.assertIsNone(series.projection(mw.parse('{{Citation needed|date=September 2025}}').filter_templates()[0]))
        original = annual.make_extraction
        config = json.loads((ROOT / series.config_path(2023)).read_bytes())
        with self.assertRaises(RuntimeError):
            with series.profile_context(config):
                raise RuntimeError('rollback')
        self.assertIs(original, annual.make_extraction)

    def test_preparation_date_atomicity_and_exact_retirement(self):
        # The complete calendar/replay checks run separately on real years.
        # This fixture exercises real staged publication and retirement safely.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / 'archive/2023.sqlite'
            database.parent.mkdir()
            raw = b';News\n*A reported event. [https://example.test (Publisher)]\n'
            source.store(raw, title='Portal:Current events/2023 January 1', revision_id=123,
                         timestamp=None, cache=root / 'reference/sources/wikipedia')
            seed = root / '2023/01/2023-01-01.yaml'
            seed.parent.mkdir(parents=True)
            seed.write_bytes(yaml.safe_dump({'date': '2023-01-01', 'source_page': {
                'portal': 'Portal:Current events/2023 January 1', 'wikipedia_revision_id': 123},
                'wikipedia': {'categories': {'News': ['A reported event.']}}}).encode())
            original = seed.read_bytes()
            with closing(annual.initialize(database, 2023)) as conn:
                annual.ingest_day(conn, '2023-01-01', root)
                with conn:
                    conn.execute('INSERT INTO archive_metadata VALUES(?,?)', ('extraction_profile', series.VERSION))
            config = {'version': series.VERSION, 'year': 2023, 'edition_date': '2026-10-22', 'roles': [], 'notices': []}
            transfer = {'verified': True, 'calendar_complete': True, 'unresolved_warnings': {},
                'unknown_heading_roles': 0, 'prior_candidate_differences_or_missing': [],
                'legacy_replay_differences': [], 'year': 2023, 'events': 1,
                'replacement_blockers': ['factual_coverage_review_not_recorded']}
            with patch.object(series, 'read_config', return_value=config), patch.object(series, 'ORIGINAL_VERIFY', return_value=transfer), patch.object(series.subprocess, 'run', return_value=SimpleNamespace(stdout='checkpoint\n')):
                before = database.read_bytes()
                seed.write_bytes(original + b'changed')
                with self.assertRaisesRegex(ValueError, 'differs from preserved'):
                    series.prepare(database, root)
                self.assertEqual(before, database.read_bytes())
                seed.write_bytes(original)
                series.prepare(database, root)
                with closing(annual.connect(database, readonly=True)) as conn:
                    self.assertEqual('2026-10-22', archive_access.publication(conn)['published_on'])
                self.assertEqual(3, series.retire(database, root)['removed_files'])
                self.assertEqual(original, archive_access.legacy_bytes('2023-01-01', root))
                self.assertEqual(0, series.retire(database, root)['removed_files'])

