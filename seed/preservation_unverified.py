"""Successor preservation policy with explicit, guarded unverified claims."""
from contextlib import closing
import datetime as dt
import json
from pathlib import Path
from seed import annual_archive as annual, annual_access as archive_access, yearbook

VERSION = 'preservation-release-1.1'
CLAIM_VERSION = 'unverified-source-claim-1.0'
ROLE = 'unverified_source_claim'
INPUTS = ('seed/preservation_unverified.py', 'seed/annual_access.py',
          'reference/schema/PRESERVATION_UNVERIFIED.md')


def validate_claim(conn, record):
    if record['contract'] != CLAIM_VERSION or record['state'] != 'unverified':
        raise ValueError('Invalid unverified claim contract/state')
    row = annual.locate_review_event(conn, record['locator'])
    if row['role'] != 'event' or annual.structured_hash(row) != record['event_sha256']:
        raise ValueError('Unverified claim extraction drift')
    dt.date.fromisoformat(record['recorded_on'])
    if not record['note'].strip() or not record['workflow'].strip() or 'model' not in record:
        raise ValueError('Unverified claim requires disclosure and provenance')
    if record['search_status'] not in ('not_researched', 'research_incomplete', 'no_separate_evidence_found'):
        raise ValueError('Invalid unverified search status')
    if not isinstance(record['queries'], list) or any(not isinstance(q, str) or not q.strip() for q in record['queries']):
        raise ValueError('Invalid research queries')
    if record['search_status'] == 'no_separate_evidence_found' and not record['queries']:
        raise ValueError('Unsuccessful search requires recorded queries')
    return row


def claim_path(row):
    return f"research/unverified/{row['date']}-{row['category_ord']}-{row['ord']}.json"


def load_claims(conn):
    claims = {}
    for item in conn.execute('SELECT path,date FROM archive_inputs WHERE role=? ORDER BY path', (ROLE,)):
        record = json.loads(annual.input_bytes(conn, item['path']))
        row = validate_claim(conn, record)
        key = yearbook.event_key(row)
        if key in claims or item['path'] != claim_path(row) or item['date'] != row['date']:
            raise ValueError('Unverified claim identity drift')
        claims[key] = record
    return claims


def record_claim(conn, record):
    if archive_access.publication(conn):
        raise ValueError('Published research requires a successor edition')
    row = validate_claim(conn, record)
    key = yearbook.event_key(row)
    existing = load_claims(conn).get(key)
    if existing is not None and existing != record:
        raise ValueError('Unverified claim is immutable; migrate explicitly')
    if key not in map(tuple, yearbook.review_report(conn)['uncited_events_without_editorial_evidence']):
        raise ValueError('Unverified disclosure must identify an uncited, unreviewed assertion')
    with conn:
        annual.put_input(conn, claim_path(row), annual.encoded(record), ROLE, row['date'], 'application/json')


def research_coverage(conn):
    reviews = yearbook.review_report(conn)
    claims = load_claims(conn)
    missing = set(map(tuple, reviews['uncited_events_without_editorial_evidence']))
    if set(claims) - missing:
        raise ValueError('Stale or unnecessary unverified disclosure')
    uncovered = sorted(missing - set(claims))
    if uncovered:
        raise ValueError(f'Uncited assertions lack review or unverified disclosure: {uncovered}')
    return {'uncited_unverified_claims': len(claims),
            'uncited_claims_with_editorial_evidence': reviews['source_events_without_attached_citations'] - len(missing),
            'independent_review_complete': reviews['every_event_independently_checked']}


def verify(conn, *, complete=True):
    transfer = annual.verify(conn, complete=complete)
    reviews = yearbook.review_report(conn)
    coverage = research_coverage(conn)
    record = archive_access.publication(conn)
    if record is None:
        raise ValueError('No preservation publication manifest')
    if (not transfer['verified'] or not transfer['calendar_complete'] or transfer['unresolved_warnings']
            or transfer['unknown_heading_roles'] or transfer['prior_candidate_differences_or_missing']
            or transfer['legacy_replay_differences']):
        raise ValueError('Preservation publication verification failed')
    for name in INPUTS:
        if annual.input_bytes(conn, f'publication/implementation/{VERSION}/{name}') != (annual.ROOT / name).read_bytes():
            raise ValueError(f'Publication implementation drift: {name}')
    if record.get('uncited_claim_policy') != CLAIM_VERSION:
        raise ValueError('Unverified publication policy drift')
    if record['independent_review_required'] is not False or record['year'] != transfer['year']:
        raise ValueError('Publication policy drift')
    for item in record['preserved_inputs']:
        payload = annual.input_bytes(conn, item['path'])
        if annual.digest(payload) != item['sha256'] or len(payload) != item['bytes']:
            raise ValueError(f"Publication preservation drift: {item['path']}")
    for item in record['retire_files']:
        if item not in record['preserved_inputs']:
            raise ValueError('Deletion is not covered by exact preserved bytes')
    return {'contract': VERSION, 'year': record['year'], 'edition': record['edition'],
            'preservation_verified': True, 'preserved_files': len(record['preserved_inputs']),
            'retire_files': len(record['retire_files']), 'independent_review_required': False,
            'independent_review_complete': reviews['every_event_independently_checked'],
            'finished_historical_yearbook': False, 'events': transfer['events'],
            'known_uncertainties_disclosed': True, **coverage}


def retire(database, root=annual.ROOT):
    root = Path(root).resolve()
    conn = annual.connect(database, readonly=True)
    try:
        verify(conn)
        record = archive_access.publication(conn)
        # Validate the entire remaining set before deleting any file. Only
        # listed files are unlinked; no computed directory is recursively removed.
        remaining = []
        for item in record['retire_files']:
            path = (root / item['path']).resolve()
            if not path.is_relative_to(root) or not (item['path'].startswith(f"{record['year']}/") or item['path'].startswith('reference/sources/wikipedia/') or item['path'].startswith(f"provisional/extraction-v1/{record['year']}/")):
                raise ValueError('Retirement path outside approved scope')
            if path.exists():
                if path.read_bytes() != annual.input_bytes(conn, item['path']):
                    raise ValueError('Retirement input changed since preservation')
                remaining.append(path)
        for path in remaining:
            path.unlink()
        return {'removed_files': len(remaining), 'remaining_manifest_files': 0}
    finally:
        conn.close()
