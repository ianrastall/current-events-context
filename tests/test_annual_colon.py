import copy
import json
from pathlib import Path
import socket
import sqlite3
import unittest
from unittest.mock import patch, MagicMock

from seed import annual_archive as annual, annual_colon, annual_legacy, annual_series, wikipedia

ROOT = Path(__file__).resolve().parents[1]


class LegacyProjectionTests(unittest.TestCase):
    def setUp(self):
        folder = ROOT / 'tests/fixtures/annual_colon'
        self.day = '2014-11-18'
        self.raw = (folder / (self.day + '.wiki')).read_bytes()
        self.meta = json.loads((folder / (self.day + '.json')).read_bytes())
        self.legacy = (folder / (self.day + '.legacy.yaml')).read_bytes()
        self.expected = json.loads((folder / (self.day + '.expected.json')).read_bytes())
        self.config = json.loads((ROOT / 'reference/overrides/2014-series.json').read_bytes())
        self.rule = self.config['legacy_baselines'][0]

    def test_exact_colon_source_preserves_all_assertions_and_discloses_flat_failure(self):
        with patch.object(socket.socket, 'connect', side_effect=AssertionError('offline')):
            doc = annual_colon.make_profile(self.config, self.day, self.meta, self.raw, {})
            self.assertEqual(self.expected, doc)
            self.assertEqual(doc, annual_colon.make_profile(self.config, self.day, self.meta, self.raw, {}))
            check = annual.reconcile(self.raw.decode(), doc, annual.yaml.load(self.legacy, Loader=annual.LOADER))
            self.assertFalse(check['baseline_matches_legacy_replay'])
            self.assertEqual((20, 20, 15), (check['source_bullets'], check['represented_bullets'], check['event_leaves']))
            self.assertEqual({}, wikipedia.parse_events_legacy(self.raw.decode(), self.meta['page']))
            report = annual_colon.validate_baseline(self.rule, self.meta, self.raw, self.legacy, doc)
        self.assertEqual(self.day, report['date'])
        self.assertTrue(all(e['list_marker'].startswith(':') for c in doc['categories'] for e in c['entries']))

    def test_guard_drift_and_changed_projection_are_rejected(self):
        for raw, legacy, doc in [(self.raw+b'changed', self.legacy, self.expected),
                                 (self.raw, self.legacy+b'\n', self.expected),
                                 (self.raw, self.legacy, {**self.expected, 'date': '2014-11-19'})]:
            with self.assertRaisesRegex(ValueError, 'guard drift'):
                annual_colon.validate_baseline(self.rule, self.meta, raw, legacy, doc)
        dropped = copy.deepcopy(self.expected)
        dropped['categories'][0]['entries'].pop()
        rule = {**self.rule, 'extraction_sha256': annual.structured_hash(dropped)}
        with self.assertRaisesRegex(ValueError, 'exact structured projection'):
            annual_colon.validate_baseline(rule, self.meta, self.raw, self.legacy, dropped)

    def test_report_keeps_unmatched_differences_and_rejects_unnecessary_rule(self):
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        conn.row_factory = sqlite3.Row
        conn.execute('CREATE TABLE day_ingestions(date TEXT, source_metadata_json TEXT, source_path TEXT, legacy_path TEXT)')
        conn.execute('INSERT INTO day_ingestions VALUES(?,?,?,?)', (self.day, json.dumps(self.meta), 'raw', 'legacy'))
        report = {'legacy_replay_differences': [self.day, '2014-01-01'], 'replacement_blockers': ['baseline_reconciliation_required']}
        with patch.object(annual, 'input_bytes', side_effect=lambda c,p: {'raw':self.raw,'legacy':self.legacy}[p]), patch.object(annual_colon.sqlite_archive, 'export_extraction_doc', return_value=self.expected):
            result = annual_colon.reconcile_baselines(self.config, conn, report)
            self.assertEqual(['2014-01-01'], result['legacy_replay_differences'])
            self.assertEqual(['baseline_reconciliation_required'], result['replacement_blockers'])
            self.assertEqual([self.day,'2014-01-01'], report['legacy_replay_differences'])
            result = annual_colon.reconcile_baselines(self.config, conn, {**report,'legacy_replay_differences':[self.day]})
            self.assertEqual([], result['replacement_blockers'])
            with self.assertRaisesRegex(ValueError, 'no longer identifies'):
                annual_colon.reconcile_baselines(self.config, conn, {**report,'legacy_replay_differences':[]})
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                annual_colon.reconcile_baselines({**self.config,'legacy_baselines':[self.rule,self.rule]}, conn, report)

    def test_successor_does_not_mutate_prior_profiles_or_dispatch(self):
        self.assertEqual('annual-series-1.1', annual_legacy.VERSION)
        self.assertEqual('annual-series-1.0', annual_series.VERSION)
        self.assertNotIn('seed/annual_colon.py', annual_legacy._engine.INPUTS)
        sentinel = object()
        with patch.object(annual_colon.annual_legacy.annual_series, 'selected_profile', return_value=annual_legacy.VERSION), patch.object(annual_legacy, 'verify', return_value=sentinel) as check:
            self.assertIs(sentinel, annual_colon.verify(None))
            check.assert_called_once_with(None, complete=True)
        original = annual.make_extraction
        with annual_colon.profile_context(self.config):
            self.assertIsNot(original, annual.make_extraction)
        self.assertIs(original, annual.make_extraction)

    def test_prepare_and_retire_delegate_existing_researched_profile(self):
        for command in ('prepare', 'retire'):
            conn = MagicMock()
            with patch.object(annual, 'connect', return_value=conn), patch.object(annual_colon.annual_legacy.annual_series, 'selected_profile', return_value=annual_legacy.VERSION), patch.object(annual_legacy, command, return_value={'delegated': True}) as delegated:
                self.assertEqual({'delegated': True}, getattr(annual_colon, command)('old.sqlite', ROOT))
                delegated.assert_called_once_with('old.sqlite', ROOT)
                conn.close.assert_called_once()

    def test_topic_citations_are_rendered_with_source_location(self):
        conn = MagicMock()
        conn.execute.return_value = [{'date': '2015-03-09', 'category': 'Disasters',
            'line': 12, 'text': 'Source topic', 'url': 'https://example.org/a?x=1&y=2',
            'publisher': 'Publisher', 'display': '(Publisher)'}]
        with patch.object(annual_colon.annual_legacy.annual_series, 'selected_profile', return_value=annual_colon.VERSION), patch.object(annual_colon, '_profile_render', return_value=b'## Contents\n'), patch.object(annual_colon, 'read_config', return_value={}):
            payload = annual_colon.render(conn, 'hash')
        self.assertIn(b'2015-03-09, source line 12: Source topic', payload)
        self.assertIn(b'[Publisher](<https://example.org/a?x=1&amp;y=2>)', payload)
