import copy
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from seed import annual_archive as annual, annual_colon, annual_unverified, extract
from seed import annual_access, archive_access
from seed import preservation_unverified as policy, sqlite_archive, yearbook


class UnverifiedPreservationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.conn = annual.initialize(Path(temporary.name) / 'annual.sqlite', 2012)
        self.addCleanup(self.conn.close)
        self.network = patch.object(socket.socket, 'connect', side_effect=AssertionError('offline'))
        self.network.start()
        self.addCleanup(self.network.stop)
        raw = ';News\n*An unsupported source assertion.\n'
        meta = {'page': 'Portal:Current events/2012 January 1', 'revision_id': 123,
                'revision_timestamp': None, 'source_mode': 'wikitext', 'source_sha256': annual.digest(raw.encode())}
        doc = extract.extract(raw, date='2012-01-01', source=meta, source_templates=True)
        sqlite_archive.import_extraction_doc(self.conn, doc)
        self.row = dict(self.conn.execute("SELECT * FROM event_overview WHERE role='event'").fetchone())
        self.record = {'contract': policy.CLAIM_VERSION, 'locator': annual.review_locator(self.row),
                       'event_sha256': annual.structured_hash(self.row), 'state': 'unverified',
                       'recorded_on': '2026-10-22', 'workflow': 'fixture', 'model': None,
                       'search_status': 'not_researched', 'queries': [],
                       'note': 'No independent research has been completed.'}

    def test_explicit_disclosure_allows_preservation_without_claiming_review(self):
        with self.assertRaisesRegex(ValueError, 'lack review or unverified disclosure'):
            policy.research_coverage(self.conn)
        before = yearbook.review_report(self.conn)
        policy.record_claim(self.conn, self.record)
        policy.record_claim(self.conn, self.record)
        result = policy.research_coverage(self.conn)
        self.assertEqual(1, result['uncited_unverified_claims'])
        self.assertEqual(0, result['uncited_claims_with_editorial_evidence'])
        self.assertFalse(result['independent_review_complete'])
        self.assertEqual(before, yearbook.review_report(self.conn))
        self.assertEqual(self.row, dict(self.conn.execute("SELECT * FROM event_overview WHERE role='event'").fetchone()))

    def test_failed_search_requires_actual_queries_and_keeps_unverified_state(self):
        record = {**self.record, 'search_status': 'no_separate_evidence_found'}
        with self.assertRaisesRegex(ValueError, 'requires recorded queries'):
            policy.record_claim(self.conn, record)
        record['queries'] = ['unsupported source assertion independent evidence']
        policy.record_claim(self.conn, record)
        self.assertEqual('unverified', next(iter(policy.load_claims(self.conn).values()))['state'])
        for state in ('complete', 'supported'):
            with self.assertRaisesRegex(ValueError, 'contract/state'):
                policy.validate_claim(self.conn, {**record, 'state': state})

    def test_source_and_event_drift_fail_and_records_are_immutable(self):
        record = copy.deepcopy(self.record)
        record['locator']['source_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'locator drift'):
            policy.record_claim(self.conn, record)
        with self.assertRaisesRegex(ValueError, 'extraction drift'):
            policy.record_claim(self.conn, {**self.record, 'event_sha256': '0' * 64})
        policy.record_claim(self.conn, self.record)
        with self.assertRaisesRegex(ValueError, 'immutable'):
            policy.record_claim(self.conn, {**self.record, 'note': 'Changed interpretation.'})
        with self.conn:
            self.conn.execute("UPDATE extraction_entries SET text='Changed source.'")
        with self.assertRaisesRegex(ValueError, 'extraction drift'):
            policy.load_claims(self.conn)

    def test_duplicate_identity_and_stale_disclosures_fail(self):
        policy.record_claim(self.conn, self.record)
        with self.conn:
            annual.put_input(self.conn, 'research/unverified/duplicate.json', annual.encoded(self.record),
                             policy.ROLE, self.row['date'], 'application/json')
        with self.assertRaisesRegex(ValueError, 'identity drift'):
            policy.load_claims(self.conn)
        with self.conn:
            self.conn.execute("DELETE FROM archive_inputs WHERE path='research/unverified/duplicate.json'")
        with patch.object(yearbook, 'review_report', return_value={'uncited_events_without_editorial_evidence': []}):
            with self.assertRaisesRegex(ValueError, 'Stale or unnecessary'):
                policy.research_coverage(self.conn)

    def test_published_records_cannot_be_changed(self):
        with patch.object(policy.archive_access, 'publication', return_value={'year': 2012}):
            with self.assertRaisesRegex(ValueError, 'successor edition'):
                policy.record_claim(self.conn, self.record)

    def test_prior_profile_versions_and_dispatch_stay_frozen(self):
        self.assertEqual('annual-series-1.2', annual_colon.VERSION)
        self.assertEqual('preservation-release-1.0', annual_colon._engine.archive_release.VERSION)
        self.assertNotIn('seed/annual_unverified.py', annual_colon._engine.INPUTS)
        sentinel = object()
        with patch.object(annual_unverified, 'selected', return_value=False):
            with patch.object(annual_colon, 'verify', return_value=sentinel) as check:
                self.assertIs(sentinel, annual_unverified.verify(self.conn))
                check.assert_called_once_with(self.conn, complete=True)
            with patch.object(annual_colon, 'render', return_value=b'frozen bytes'):
                self.assertEqual(b'frozen bytes', annual_unverified.render(self.conn, 'hash'))

    def test_readable_projection_discloses_assertion_and_search_limit(self):
        policy.record_claim(self.conn, self.record)
        with patch.object(annual_unverified, 'selected', return_value=True), patch.object(
                annual_unverified, '_profile_render', return_value=b'These have separate editorial evidence.\n## Contents\n'):
            payload = annual_unverified.render(self.conn, 'hash')
            self.assertEqual(payload, annual_unverified.render(self.conn, 'hash'))
        self.assertIn(b'explicitly unverified: 1', payload)
        self.assertIn(b'2012-01-01, source line 2: unverified.', payload)
        self.assertIn(b'An unsupported source assertion.', payload)
        self.assertIn(b'Research status: not researched.', payload)
        self.assertNotIn(b'These have separate editorial evidence.', payload)

    def test_unverified_policy_does_not_waive_structural_or_manifest_checks(self):
        policy.record_claim(self.conn, self.record)
        report = {'verified': True, 'calendar_complete': False, 'unresolved_warnings': 0,
                  'unknown_heading_roles': 0, 'prior_candidate_differences_or_missing': [],
                  'legacy_replay_differences': [], 'year': 2012, 'events': 1}
        manifest = {'year': 2012, 'independent_review_required': False,
                    'uncited_claim_policy': policy.CLAIM_VERSION,
                    'preserved_inputs': [], 'retire_files': [], 'edition': 'source-preservation'}
        original_input = annual.input_bytes
        def stored_input(conn, path):
            prefix = f'publication/implementation/{policy.VERSION}/'
            return (annual.ROOT / path[len(prefix):]).read_bytes() if path.startswith(prefix) else original_input(conn, path)
        with patch.object(annual, 'verify', return_value=report), patch.object(
                policy.archive_access, 'publication', return_value=manifest), patch.object(
                annual, 'input_bytes', side_effect=stored_input):
            with self.assertRaisesRegex(ValueError, 'verification failed'):
                policy.verify(self.conn)
            report['calendar_complete'] = True
            self.assertEqual(1, policy.verify(self.conn)['uncited_unverified_claims'])
            manifest['uncited_claim_policy'] = 'unapproved-policy'
            with self.assertRaisesRegex(ValueError, 'policy drift'):
                policy.verify(self.conn)

    def test_current_access_accepts_both_contracts_and_frozen_access_stays_frozen(self):
        record = {'contract': 'preservation-release-1.1', 'edition': 'source-preservation',
                  'year': 2012, 'publication_toolchain': annual_unverified.VERSION,
                  'uncited_claim_policy': policy.CLAIM_VERSION}
        with self.conn:
            annual.put_input(self.conn, 'publication/2012.json', annual.encoded(record), 'preservation_publication')
        self.assertEqual(record, annual_access.publication(self.conn))
        with self.assertRaisesRegex(ValueError, 'Unsupported annual publication contract'):
            archive_access.publication(self.conn)
        for contract, claim_policy, succeeds in [('preservation-release-1.0', None, True),
                ('preservation-release-1.1', 'unknown', False), ('unknown', None, False)]:
            changed = {**record, 'contract': contract, 'uncited_claim_policy': claim_policy}
            with self.conn:
                self.conn.execute("DELETE FROM archive_inputs WHERE role='preservation_publication'")
                annual.put_input(self.conn, 'publication/2012.json', annual.encoded(changed), 'preservation_publication')
            if succeeds:
                self.assertEqual(changed, annual_access.publication(self.conn))
                self.assertEqual(changed, archive_access.publication(self.conn))
            else:
                with self.assertRaisesRegex(ValueError, 'Unsupported'):
                    annual_access.publication(self.conn)
