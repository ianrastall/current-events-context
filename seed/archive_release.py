"""Publish a lossless annual source-preservation edition and retire exact duplicates."""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile

from seed import annual_archive as annual, archive_access, yearbook

VERSION = 'preservation-release-1.0'
INPUTS = ('seed/archive_release.py', 'seed/archive_access.py', 'reference/schema/PRESERVATION_RELEASE.md')


def verify(conn, *, complete=True):
    transfer = annual.verify(conn, complete=complete)
    reviews = yearbook.review_report(conn)
    record = archive_access.publication(conn)
    if record is None:
        raise ValueError('No preservation publication manifest')
    if (not transfer['verified'] or not transfer['calendar_complete'] or transfer['unresolved_warnings']
            or transfer['unknown_heading_roles'] or transfer['prior_candidate_differences_or_missing']
            or transfer['legacy_replay_differences'] or reviews['uncited_events_without_editorial_evidence']):
        raise ValueError('Preservation publication verification failed')
    for name in INPUTS:
        if annual.input_bytes(conn, f'publication/implementation/{VERSION}/{name}') != (annual.ROOT / name).read_bytes():
            raise ValueError(f'Publication implementation drift: {name}')
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
            'known_uncertainties_disclosed': True}


def prepare(database, root=annual.ROOT):
    """Create an atomic edition; immutable source and prior review bytes are unchanged."""
    database, root = Path(database), Path(root)
    conn = annual.connect(database, readonly=True)
    try:
        if archive_access.publication(conn):
            return verify(conn)
        report = annual.verify(conn)
        if report['replacement_blockers'] != ['factual_coverage_review_not_recorded']:
            raise ValueError('Non-factual migration blockers remain')
        year = report['year']
        checkpoint = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
        # References from other daily seeds, expansion caches and capture
        # pointers keep their shared cache pair on disk, even though annual
        # revision access can also supply it.
        revisions = set()
        for path in root.glob('20*/*/*.yaml'):
            if path.parts[-3] == str(year):
                continue
            import yaml
            doc = yaml.load(path.read_bytes(), Loader=annual.LOADER)
            rev = (doc.get('source_page') or {}).get('wikipedia_revision_id')
            if rev is not None:
                revisions.add(str(rev))
        for folder in ('reference/expansion/wikitext', 'reference/sources/wikipedia/captures'):
            for path in (root / folder).glob('*.json'):
                data = json.loads(path.read_bytes())
                revisions.add(str(data.get('revid', data.get('revision_id'))))
        candidates = [dict(r) for r in conn.execute("SELECT path,role,sha256 FROM archive_inputs WHERE role IN ('legacy_seed','wikipedia_wikitext','source_metadata') ORDER BY path")]
    finally:
        conn.close()
    fd, name = tempfile.mkstemp(prefix='.publication-', suffix='.sqlite', dir=database.parent)
    os.close(fd)
    staged = Path(name)
    try:
        with closing(sqlite3.connect(database)) as src, closing(sqlite3.connect(staged)) as dst:
            src.backup(dst)
        conn = annual.connect(staged)
        try:
            with conn:
                for path in sorted((root / 'provisional/extraction-v1' / str(year)).glob('*/*')):
                    if not path.is_file():
                        continue
                    relative = path.relative_to(root).as_posix()
                    payload = path.read_bytes()
                    key = annual.put_input(conn, relative, payload, 'retired_extraction_candidate', path.stem[:10], 'text/plain')
                    candidates.append({'path': relative, 'role': 'retired_extraction_candidate', 'sha256': key})
                preserved, retire, shared = [], [], []
                for item in candidates:
                    path = (root / item['path']).resolve()
                    if not path.is_relative_to(root.resolve()) or not path.is_file():
                        raise ValueError('Deletion candidate is missing or escapes repository')
                    payload = path.read_bytes()
                    if annual.digest(payload) != item['sha256'] or payload != annual.input_bytes(conn, item['path']):
                        raise ValueError(f"Original preservation mismatch: {item['path']}")
                    item = {**item, 'bytes': len(payload)}
                    preserved.append(item)
                    revision = path.name.split('.')[0]
                    if item['role'] in ('wikipedia_wikitext', 'source_metadata') and revision in revisions:
                        shared.append(item['path'])
                    else:
                        retire.append(item)
                record = {'contract': VERSION, 'edition': 'source-preservation', 'year': year,
                          'published_on': '2026-10-21', 'checkpoint_commit': checkpoint,
                          'independent_review_required': False,
                          'policy': 'Publish verified archival sources and disclosed editorial findings; independent checking of every event is optional further research, not a cutover prerequisite.',
                          'preserved_inputs': preserved, 'retire_files': retire, 'retained_shared_inputs': shared,
                          'limits': ['Wikipedia selection is not exhaustive or guaranteed impartial.',
                                     'Source statements retain source errors; reviewed editorial accounts are separate.',
                                     'Independent review is incomplete; an archival edition is not a finished historical interpretation.']}
                for source in INPUTS:
                    annual.put_input(conn, f'publication/implementation/{VERSION}/{source}',
                                     (annual.ROOT / source).read_bytes(), 'publication_implementation')
                annual.put_input(conn, f'publication/{year}.json', annual.encoded(record), 'preservation_publication', media_type='application/json')
                result = verify(conn)
                conn.execute("INSERT OR REPLACE INTO archive_checks VALUES('preservation_publication',?)", (annual.encoded(result).decode(),))
            conn.execute('VACUUM')
        finally:
            conn.close()
        os.replace(staged, database)
        return result
    finally:
        staged.unlink(missing_ok=True)


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


def render(conn, digest):
    report = verify(conn)
    reviews = yearbook.review_report(conn)
    record = archive_access.publication(conn)
    old = yearbook.render(conn, digest).decode('utf-8')
    body = old[old.index('## Contents'):]
    body = body.replace('**Source account; full-event review pending.**', '**Archived source account.**')
    year = record['year']
    header = [f'# {year}: current events archive', '', '**Source-preservation edition.**', '',
              f'This chronological reference preserves {report["events"]:,} Wikipedia event assertions across the full calendar year, with pinned source revisions, topic context and original citations. It is intended for long-term reference, reading and LLM context.', '',
              'The sources reflect Wikipedia’s selection and wording. They are not guaranteed exhaustive, impartial or factually correct. Independent checks are recorded where performed; publication does not imply that every event has been independently verified. Source errors remain visible, alongside separately labeled cited editorial accounts.', '',
              f'Database: [{year}.sqlite]({year}.sqlite). Edition SHA-256: `{digest}`. Publication contract: `{VERSION}`. Date: {record["published_on"]}.', '',
              f"The {reviews['source_events_without_attached_citations']} entries originally lacking attached citations have separate publisher evidence in the editorial layer. There are {reviews['editorial_resolutions']} editorial accounts, including documented corrections; {reviews['full_event_reviews_complete']} full-event reviews are complete and {reviews['full_event_reviews_partial']} remain partial. Outstanding questions are disclosed rather than used to postpone source preservation.", '',
              'Editorial dates are explicit where they differ from portal dates. Historical casualty totals apply at the reporting time. Five unclassified fragments from one malformed May 6 football passage and an empty July 5 marker are preserved in the database; they are not invented event assertions. Original daily files, cached source bytes, metadata and prior extraction candidates are embedded losslessly, with a deletion manifest and Git checkpoint identity.', '',
              'Wikipedia text is attributed through the pinned revision links and remains subject to its CC BY-SA terms. Publisher links identify evidence; publisher full text and images are not reproduced. This is an archival chronicle, with further synthesis and a PDF yearbook possible as later interpretations.', '']
    findings = ['## Recorded research findings', '',
                'These are scoped observations, not endorsements of entire days or the year. Access limitations and unresolved claims remain explicit.', '']
    for row in conn.execute('SELECT * FROM factual_reviews ORDER BY date,id'):
        links = [yearbook.source_link(e['publisher'], e['url']) + f" ({e['access_status']})"
                 for e in conn.execute('SELECT * FROM review_evidence WHERE review_id=? ORDER BY ord', (row['id'],))]
        findings += [f"- **{row['date']}: {row['assessment'].replace('_', ' ')}.** "
                     + yearbook.safe_text(row['scope']) + ' ' + yearbook.safe_text(row['note'])
                     + ' Evidence: ' + '; '.join(links) + '.', '']
    return ('\n'.join(header + findings) + '\n' + body).encode('utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'verify', 'retire', 'render'))
    parser.add_argument('database', type=Path)
    args = parser.parse_args(argv)
    if args.command == 'prepare':
        result = prepare(args.database)
    elif args.command == 'retire':
        result = retire(args.database)
    else:
        conn = annual.connect(args.database, readonly=True)
        try:
            result = verify(conn)
            if args.command == 'render':
                if any(Path(str(args.database) + s).exists() for s in ('-wal', '-journal')):
                    raise ValueError('Close database writers before rendering')
                payload = render(conn, annual.digest(args.database.read_bytes()))
                target = args.database.with_suffix('.md')
                fd, temporary = tempfile.mkstemp(prefix='.publication-', dir=target.parent)
                try:
                    with os.fdopen(fd, 'wb') as stream:
                        stream.write(payload)
                    os.replace(temporary, target)
                finally:
                    Path(temporary).unlink(missing_ok=True)
                result['markdown_sha256'] = annual.digest(payload)
        finally:
            conn.close()
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
