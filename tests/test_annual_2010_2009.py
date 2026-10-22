import json
from pathlib import Path
import re
import socket
import unittest
from unittest.mock import patch

from seed import annual_archive as annual, annual_continuations as engine

ROOT = Path(__file__).resolve().parents[1]


class EarlierAnnualFixtures(unittest.TestCase):
    def setUp(self):
        self.folder = ROOT / 'tests/fixtures/annual_2010_2009'
        self.network = patch.object(socket.socket, 'connect', side_effect=AssertionError('offline fixtures'))
        self.network.start()
        self.addCleanup(self.network.stop)

    def fixture(self, day):
        meta = json.loads((self.folder / (day + '.json')).read_bytes())
        raw = (self.folder / (day + '.wiki')).read_bytes()
        cfg = json.loads((ROOT / f'reference/overrides/{day[:4]}-series.json').read_bytes())
        return raw, engine.make_profile(cfg, day, meta, raw, {}), cfg, meta

    def test_all_eleven_golden_documents_warnings_and_idempotence_offline(self):
        files = list(self.folder.glob('*.wiki'))
        self.assertEqual(11, len(files))
        for path in files:
            with self.subTest(day=path.stem):
                raw, doc, cfg, meta = self.fixture(path.stem)
                self.assertEqual(json.loads(path.with_suffix('.expected.json').read_bytes()), doc)
                self.assertEqual(doc, engine.make_profile(cfg, path.stem, meta, raw, {}))
                self.assertTrue(all(w.get('resolution') for w in doc['warnings']))
                report = annual.reconcile(raw.decode(), doc, {})
                self.assertEqual(report['source_bullets'], report['represented_bullets'])

    def test_complete_statements_keep_their_children_and_event_roles(self):
        for day, line in [('2010-04-18', 4), ('2010-10-10', 41), ('2009-11-08', 15)]:
            with self.subTest(day=day):
                _, doc, _, _ = self.fixture(day)
                category, entry = next((c, e) for c in doc['categories'] for e in c['entries'] if e['line'] == line)
                self.assertEqual('event', entry['role'])
                self.assertTrue(any(e['parent_path'] == entry['source_path'] for e in category['entries']))

    def test_orphan_labels_keep_actual_depth_and_parentless_following_events(self):
        for day, line in [('2010-05-08', 3), ('2010-12-18', 4)]:
            _, doc, _, _ = self.fixture(day)
            category, entry = next((c, e) for c in doc['categories'] for e in c['entries'] if e['line'] == line)
            self.assertEqual('topic', entry['role'])
            self.assertTrue(any(w['code'] == 'ORPHAN_TOPIC' and w['line'] == line for w in doc['warnings']))
            if day == '2010-12-18':
                self.assertEqual(2, entry['depth'])
                following = next(e for e in category['entries'] if e['line'] == 5)
                self.assertIsNone(following['parent_path'])
                self.assertTrue(any(w['code'] == 'DEPTH_JUMP' and w['line'] == 4 for w in doc['warnings']))

    def test_malformed_parameter_preserves_the_entire_tail_and_all_omitted_bullets(self):
        raw, doc, _, _ = self.fixture('2010-10-17')
        warning = next(w for w in doc['warnings'] if w['code'] == 'UNASSIGNED_TEMPLATE_PARAMETER')
        self.assertEqual('unclassified_source_requires_factual_research', warning['interpretation'])
        self.assertIn('5+1 group in November', warning['raw'])
        self.assertIn(';Law and crime', warning['raw'])
        self.assertIn(';Sport', warning['raw'])
        self.assertIn('[[Andy Murray]]', warning['raw'])
        text = raw.decode()
        start = text.index(warning['raw'])
        first = text[:start].count('\n') + 1
        last = first + warning['raw'].count('\n')
        represented = {e['line'] for c in doc['categories'] for e in c['entries']}
        represented.update(c['line'] for c in doc['categories'] if re.match(r'^\s*[*:]+', c.get('raw', '')))
        missing = {i for i, line in enumerate(text.splitlines(), 1) if re.match(r'^\s*[*:]+', line)} - represented
        self.assertTrue(missing)
        self.assertTrue(all(first <= line <= last for line in missing))
        self.assertFalse(any('[[Andy Murray]]' in e['raw'] for c in doc['categories'] for e in c['entries']))

    def test_source_metadata_empty_marker_and_unbulleted_statement_stay_explicit(self):
        _, doc, _, _ = self.fixture('2010-08-30')
        self.assertEqual(2, sum(w['code'] == 'UNSUPPORTED_CONTENT' for w in doc['warnings']))
        self.assertTrue(all(w['interpretation'] != 'unclassified_source_requires_factual_research'
                            for w in doc['warnings'] if w['code'] == 'UNSUPPORTED_CONTENT'))
        _, doc, _, _ = self.fixture('2009-01-22')
        entry = next(e for c in doc['categories'] for e in c['entries'] if e['line'] == 2)
        self.assertEqual(('unknown', ''), (entry['role'], entry['text']))
        self.assertTrue(any(w['code'] == 'SOURCE_EMPTY_MARKER' for w in doc['warnings']))
        _, doc, _, _ = self.fixture('2009-11-24')
        warning = next(w for w in doc['warnings'] if w['code'] == 'UNSUPPORTED_CONTENT')
        self.assertIn('Bad Romance', warning['raw'])
        self.assertEqual('unclassified_source_requires_factual_research', warning['interpretation'])
