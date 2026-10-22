import copy
import json
from pathlib import Path
import socket
import unittest
from unittest.mock import MagicMock, patch

from seed import annual_archive as annual, annual_continuations as successor, annual_labels, annual_unverified

ROOT = Path(__file__).resolve().parents[1]


class ConsecutiveCitationTests(unittest.TestCase):
    def setUp(self):
        self.network = patch.object(socket.socket, 'connect', side_effect=AssertionError('offline'))
        self.network.start()
        self.addCleanup(self.network.stop)

    def fixture(self, day):
        folder = ROOT / 'tests/fixtures/annual_2010_2009'
        prior = annual.yaml.load((folder / (day + '.prior.yaml')).read_bytes(), Loader=annual.LOADER)
        doc = json.loads((folder / (day + '.expected.json')).read_bytes())
        config = json.loads((ROOT / f'reference/overrides/{day[:4]}-series.json').read_bytes())
        return config, prior, doc

    def test_two_exact_lines_reconcile_without_changing_either_document(self):
        for day in ('2010-12-28', '2009-07-09'):
            with self.subTest(day=day):
                config, prior, doc = self.fixture(day)
                before, after = copy.deepcopy(prior), copy.deepcopy(doc)
                with self.assertRaisesRegex(ValueError, 'source fragment change'):
                    annual_labels.compare_profile(config, prior, doc)
                report = successor.compare_profile(config, prior, doc)
                group = report['consecutive_citation_reconciliations'][0]
                self.assertEqual(2, len(group['continuation_lines']))
                self.assertEqual([group['line'] + 1, group['line'] + 2], [r['line'] for r in group['continuation_lines']])
                self.assertTrue(report['source_identity_preserved'])
                self.assertEqual((before, after), (prior, doc))

    def test_exact_hash_location_and_warning_guards_reject_drift(self):
        config, prior, doc = self.fixture('2010-12-28')
        for field in ('source_sha256', 'prior_entry_sha256', 'extraction_entry_sha256'):
            bad = copy.deepcopy(config)
            bad['citation_continuations'][0][field] = '0' * 64
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'guard drift'):
                successor.compare_profile(bad, prior, doc)
        for value in (prior, doc):
            damaged = copy.deepcopy(value)
            damaged['warnings'] = [w for w in damaged['warnings'] if w['line'] != 24]
            args = (damaged, doc) if value is prior else (prior, damaged)
            with self.assertRaisesRegex(ValueError, 'warning coverage drift'):
                successor.compare_profile(config, *args)
        bad = copy.deepcopy(config)
        bad['citation_continuations'][0]['line'] = 999
        with self.assertRaisesRegex(ValueError, 'locator drift'):
            successor.compare_profile(bad, prior, doc)

    def test_rule_is_required_and_duplicate_or_out_of_year_rules_fail(self):
        config, prior, doc = self.fixture('2009-07-09')
        with self.assertRaisesRegex(ValueError, 'source fragment change'):
            successor.compare_profile({**config, 'citation_continuations': []}, prior, doc)
        duplicate = copy.deepcopy(config)
        duplicate['citation_continuations'] *= 2
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            successor.validate_config(duplicate)
        for day in ('2008-07-09', '2009-99-99'):
            bad = copy.deepcopy(config)
            bad['citation_continuations'][0]['date'] = day
            with self.assertRaises(ValueError):
                successor.validate_config(bad)

    def test_suffix_reconciliation_keeps_lossless_structural_and_citation_gates(self):
        config, prior, doc = self.fixture('2009-07-09')
        for field in ('citations', 'depth'):
            bad_config, damaged = copy.deepcopy(config), copy.deepcopy(doc)
            entry = next(e for c in damaged['categories'] for e in c['entries'] if e['line'] == 6)
            if field == 'citations':
                entry['citations'].pop(0)  # Remove the citation already present in the old bullet.
            else:
                entry['depth'] += 1
            bad_config['citation_continuations'][0]['extraction_entry_sha256'] = annual.structured_hash(entry)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'link or citation|source hierarchy'):
                successor.compare_profile(bad_config, prior, damaged)

    def test_earlier_profile_versions_and_dispatch_remain_frozen(self):
        self.assertEqual('annual-series-1.4', annual_labels.VERSION)
        self.assertEqual('annual-series-1.4', annual_labels._engine.VERSION)
        self.assertEqual('annual-series-1.3', annual_unverified._engine.VERSION)
        self.assertNotIn('seed/annual_continuations.py', annual_labels._engine.INPUTS)
        with patch.object(successor._engine, 'selected_profile', return_value='annual-series-1.4'):
            with patch.object(annual_labels, 'verify', return_value='frozen') as delegated:
                self.assertEqual('frozen', successor.verify(None))
                delegated.assert_called_once_with(None, complete=True)
            with patch.object(annual_labels, 'render', return_value=b'frozen'):
                self.assertEqual(b'frozen', successor.render(None, 'hash'))
            for command in ('prepare', 'retire'):
                conn = MagicMock()
                with patch.object(annual, 'connect', return_value=conn), patch.object(annual_labels, command, return_value='frozen') as delegated:
                    self.assertEqual('frozen', getattr(successor, command)('old.sqlite', ROOT))
                    delegated.assert_called_once_with('old.sqlite', ROOT)
