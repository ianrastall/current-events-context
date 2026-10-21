from pathlib import Path
import copy
import json
import socket
import unittest
from unittest.mock import patch
import yaml
from seed import annual_archive as annual, annual_legacy as legacy, annual_series

ROOT = Path(__file__).resolve().parents[1]


class UnheadedCategoryTests(unittest.TestCase):
    def test_exact_empty_prelude_preserves_absent_category_location(self):
        folder = ROOT / 'tests/fixtures/annual_series'
        day = '2017-03-23'
        raw = (folder / (day + '.wiki')).read_bytes()
        meta = json.loads((folder / (day + '.json')).read_bytes())
        prior = yaml.safe_load((folder / (day + '.prior.yaml')).read_bytes())
        config = json.loads((ROOT / annual_series.config_path(2017)).read_bytes())
        original = copy.deepcopy(prior)
        with patch.object(socket.socket, 'connect', side_effect=AssertionError('offline')):
            doc = legacy.make_profile(config, day, meta, raw, {})
            self.assertEqual(doc, legacy.make_profile(config, day, meta, raw, {}))
            report = legacy.compare_profile(config, prior, doc)
            annual.reconcile(raw.decode(), doc, {})
        self.assertIsNone(doc['categories'][0]['name'])
        self.assertNotIn('line', doc['categories'][0])
        marker = doc['categories'][0]['entries'][0]
        self.assertEqual(('unknown', 4, None), (marker['role'], marker['line'], marker['parent_path']))
        self.assertEqual([0], report['unheaded_categories_preserved'])
        self.assertEqual(-1, report['event_assertion_delta'])
        self.assertEqual(original, prior)
        changed = copy.deepcopy(doc)
        changed['categories'][0]['line'] = 1
        with self.assertRaisesRegex(ValueError, 'source-location'):
            legacy.compare_profile(config, prior, changed)
        changed = copy.deepcopy(doc)
        changed['categories'][0]['entries'].pop()
        with self.assertRaises(ValueError):
            legacy.compare_profile(config, prior, changed)

    def test_successor_namespace_does_not_mutate_published_profile(self):
        self.assertEqual('annual-series-1.0', annual_series.VERSION)
        self.assertNotIn('seed/annual_legacy.py', annual_series.INPUTS)
        original = annual.make_extraction
        config = json.loads((ROOT / annual_series.config_path(2017)).read_bytes())
        with legacy.profile_context(config):
            self.assertIsNot(original, annual.make_extraction)
        self.assertIs(original, annual.make_extraction)
