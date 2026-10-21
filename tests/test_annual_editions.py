"""Successor-profile fixtures preserve exact inputs and isolate the 2025 engine."""
from pathlib import Path
import copy
import json
import socket
import unittest
from unittest.mock import patch

import mwparserfromhell as mw

from seed import annual_archive as annual, annual_editions as editions, extract

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/annual_2024'


class AnnualEditionTests(unittest.TestCase):
    def setUp(self):
        self.records = json.loads((ROOT / editions.NOTICES).read_bytes())
        self.roles = json.loads((ROOT / 'reference/overrides/2024-extraction.json').read_bytes())

    def document(self, day, records=None):
        raw = (FIXTURES / (day + '.wiki')).read_bytes()
        meta = json.loads((FIXTURES / (day + '.json')).read_bytes())
        with patch.object(socket.socket, 'connect', side_effect=AssertionError('network forbidden')):
            doc = editions.make_profile(self.records if records is None else records,
                day, meta, raw, {}, [r for r in self.roles if r['date'] == day])
        self.assertEqual(meta['source_sha256'], annual.digest(raw))
        return doc, raw, meta

    def test_commented_heading_has_own_category_and_identical_evidence(self):
        day = '2024-02-26'
        doc, raw, meta = self.document(day)
        original = editions.ORIGINAL_MAKE(day, meta, raw, {})
        category = next(c for c in doc['categories'] if c['name'] == 'Law and crime')
        self.assertEqual(14, category['line'])
        self.assertIn('<!--Do not add information', category['raw'])
        self.assertEqual(1, len(category['entries']))
        event = category['entries'][0]
        self.assertEqual((15, [1], None, 1), (event['line'], event['source_path'], event['parent_path'], event['depth']))
        prior = next(e for c in original['categories'] for e in c['entries'] if e['line'] == 15)
        for key in ('raw', 'text', 'links', 'citations'):
            self.assertEqual(prior[key], event[key])
        comparison = editions.compare_profile(original, doc)
        self.assertEqual(0, comparison['event_leaf_delta'])
        self.assertEqual(['explicit_category_followed_by_comment'], comparison['entry_deltas'][0]['reasons'])
        self.assertTrue(all(w['resolution'] for w in doc['warnings']))
        self.assertEqual(doc, self.document(day)[0])

    def test_orphan_labels_remain_childless_and_following_depth_is_real(self):
        for day, line, depth in [('2024-01-27', 9, 2), ('2024-05-05', 6, 3)]:
            doc, _, _ = self.document(day)
            entries = [(c, e) for c in doc['categories'] for e in c['entries']]
            category, orphan = next((c, e) for c, e in entries if e['line'] == line)
            self.assertEqual(('topic', depth), (orphan['role'], orphan['depth']))
            self.assertFalse(any(e['parent_path'] == orphan['source_path'] for e in category['entries']))
            following = next(e for _, e in entries if e['line'] == line + 1)
            self.assertEqual(depth, following['depth'])
            self.assertNotEqual(orphan['source_path'], following['parent_path'])
            notices = [w for w in doc['warnings'] if w['code'] == 'ORPHAN_TOPIC']
            self.assertEqual(1, len(notices))
            self.assertEqual('approved_orphan_topic_preserved', notices[0]['resolution'])
            self.assertTrue(all(w['resolution'] for w in doc['warnings']))

    def test_notice_drift_fails_and_unhandled_notice_stays_unresolved(self):
        rules = copy.deepcopy(self.records)
        next(r for r in rules if r['date'] == '2024-05-05')['raw_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'locator drift'):
            self.document('2024-05-05', rules)
        rules = [r for r in self.records if not (r['date'] == '2024-05-05' and r['code'] == 'ORPHAN_TOPIC')]
        doc, _, _ = self.document('2024-05-05', rules)
        self.assertTrue(any(w['code'] == 'ORPHAN_TOPIC' and w['resolution'] is None for w in doc['warnings']))

    def test_literal_projection_and_frozen_engine_restoration(self):
        cases = {'{{conv|50|F-change}}': '50 °F change', '{{conv|10|–|20|km|mi}}': '10–20 km',
                 '{{US$|300}}': 'US$300', '{{convert|195|mi2|km2}}': '195 mi2',
                 '{{chem|O|2}}': 'O2', '{{m|ww|link=y}}': 'Mww',
                 '{{conv|37.6|e6ha|e6acre}}': '37.6 million ha'}
        for source, expected in cases.items():
            self.assertEqual(expected, editions.projection(mw.parse(source).filter_templates()[0]))
        self.assertIsNone(editions.projection(mw.parse('{{conv|{{unknown}}|F}}').filter_templates()[0]))
        original, projection = annual.make_extraction, extract.project_template
        with self.assertRaisesRegex(RuntimeError, 'test failure'):
            with editions.profile_context(self.records):
                self.assertIsNot(original, annual.make_extraction)
                raise RuntimeError('test failure')
        self.assertIs(original, annual.make_extraction)
        self.assertIs(projection, extract.project_template)
