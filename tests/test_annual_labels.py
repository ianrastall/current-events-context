import copy
import json
from pathlib import Path
import socket
import unittest
from unittest.mock import patch

from seed import annual_archive as annual, annual_labels as labels, annual_unverified, extract

ROOT = Path(__file__).resolve().parents[1]


class AnnualLabelTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / 'reference/overrides/2011-series.json').read_bytes())
        self.folder = ROOT / 'tests/fixtures/annual_labels'
        self.network = patch.object(socket.socket, 'connect', side_effect=AssertionError('offline'))
        self.network.start()
        self.addCleanup(self.network.stop)

    def fixture(self, day):
        raw = (self.folder / (day + '.wiki')).read_bytes()
        meta = json.loads((self.folder / (day + '.json')).read_bytes())
        return meta, raw, labels.make_profile(self.config, day, meta, raw, {})

    def test_golden_sources_and_warnings_are_identical_offline(self):
        for path in self.folder.glob('*.wiki'):
            with self.subTest(day=path.stem):
                meta, raw, doc = self.fixture(path.stem)
                self.assertEqual(json.loads(path.with_suffix('.expected.json').read_bytes()), doc)
                self.assertEqual(doc, labels.make_profile(self.config, path.stem, meta, raw, {}))
                report = annual.reconcile(raw.decode(), doc, {})
                self.assertEqual(report['source_bullets'], report['represented_bullets'])
                self.assertTrue(all(w.get('resolution') for w in doc['warnings']))

    def test_tornado_label_is_topic_without_promoting_unbulleted_sentence(self):
        meta, raw, doc = self.fixture('2011-04-22')
        entry = next(e for c in doc['categories'] for e in c['entries'] if e['line'] == 26)
        self.assertEqual('topic', entry['role'])
        self.assertIn('Circular reference', entry['raw'])
        self.assertTrue(any('2011 St. Louis tornado' in link['target'] for link in entry['links']))
        self.assertTrue(any(w['code'] == 'ORPHAN_TOPIC' and w['line'] == 26 for w in doc['warnings']))
        warning = next(w for w in doc['warnings'] if w['line'] == 27)
        self.assertEqual('unclassified_source_requires_factual_research', warning['interpretation'])
        self.assertFalse(any(e['line'] == 27 for c in doc['categories'] for e in c['entries']))
        prior = labels._engine.ORIGINAL_MAKE('2011-04-22', meta, raw, {})
        result = labels.compare_profile(self.config, prior, doc)
        self.assertEqual(-1, result['event_assertion_delta'])
        self.assertEqual('event', result['source_role_changes'][0]['before'])
        self.assertEqual('topic', result['source_role_changes'][0]['after'])

    def test_source_label_guards_reject_drift_and_loss(self):
        meta, raw, doc = self.fixture('2011-04-22')
        prior = labels._engine.ORIGINAL_MAKE('2011-04-22', meta, raw, {})
        for key, value in [('source_sha256','0'*64), ('raw_sha256','0'*64),
                           ('prior_entry_sha256','0'*64), ('line',999), ('source_path',[999])]:
            cfg = copy.deepcopy(self.config)
            rule = next(r for r in cfg['roles'] if r.get('interpretation') == 'explicit_source_label')
            rule[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                labels.compare_profile(cfg, prior, doc)
        damaged = copy.deepcopy(doc)
        next(e for c in damaged['categories'] for e in c['entries'] if e['line'] == 26)['links'].clear()
        with self.assertRaisesRegex(ValueError, 'link or citation'):
            labels.compare_profile(self.config, prior, damaged)
        cfg = copy.deepcopy(self.config)
        cfg['roles'].append(next(r for r in cfg['roles'] if r.get('interpretation') == 'explicit_source_label'))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            labels.validate_config(cfg)

    def test_bare_film_titles_remain_orphans_and_assertion_parent_stays_event(self):
        _, _, doc = self.fixture('2011-06-24')
        movies = next(c for c in doc['categories'] if c['name'] == 'Movies')
        self.assertEqual(4, len(movies['entries']))
        self.assertTrue(all(e['role'] == 'topic' for e in movies['entries']))
        self.assertEqual(4, sum(w['code'] == 'ORPHAN_TOPIC' and w['category'] == 'Movies' for w in doc['warnings']))
        _, _, doc = self.fixture('2011-05-28')
        parent = next(e for c in doc['categories'] for e in c['entries'] if e['line'] == 23)
        self.assertEqual('event', parent['role'])
        self.assertTrue(any(e['parent_path'] == parent['source_path'] for c in doc['categories'] for e in c['entries']))

    def test_comment_entry_excluded_and_previous_profiles_unchanged(self):
        _, _, doc = self.fixture('2011-12-31')
        entry = next(e for c in doc['categories'] for e in c['entries'] if e['line'] == 21)
        self.assertEqual('unknown', entry['role'])
        self.assertTrue(any(w['code'] == 'SOURCE_COMMENTED_ENTRY' and w['line'] == 21 for w in doc['warnings']))
        self.assertEqual('annual-series-1.3', annual_unverified.VERSION)
        self.assertEqual('annual-series-1.3', annual_unverified._engine.VERSION)
        self.assertNotIn('seed/annual_labels.py', annual_unverified._engine.INPUTS)
        with patch.object(labels._base, 'selected', return_value=False), patch.object(annual_unverified, 'render', return_value=b'frozen'):
            self.assertEqual(b'frozen', labels.render(None, 'hash'))
