"""Annual dispatcher allowing explicitly disclosed unverified source claims."""
from contextlib import closing
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
from seed import annual_archive as annual, annual_colon, annual_access as archive_access, yearbook
from seed import preservation_unverified as archive_release

_spec = importlib.util.spec_from_file_location('seed._annual_unverified_colon', Path(annual_colon.__file__))
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)
VERSION = 'annual-series-1.3'
_base.VERSION = VERSION
_base._base.VERSION = VERSION
_engine = _base._engine
_engine.VERSION = VERSION
_engine.INPUTS = (*_engine.INPUTS, 'seed/annual_unverified.py',
                  'seed/preservation_unverified.py', 'reference/schema/PRESERVATION_UNVERIFIED.md')
_engine.archive_release = archive_release
_engine.archive_access = archive_access
build = _engine.build
make_profile = _engine.make_profile
read_config = _engine.read_config
profile_context = _engine.profile_context
_profile_verify = _engine.verify
_profile_render = _engine.render


def selected(conn):
    return _engine.selected_profile(conn) == VERSION


def verify(conn, *, complete=True):
    if selected(conn):
        return _profile_verify(conn, complete=complete)
    return annual_colon.verify(conn, complete=complete)


def prepare(database, root=annual.ROOT):
    database, root = Path(database), Path(root)
    with closing(annual.connect(database, readonly=True)) as conn:
        if not selected(conn):
            return annual_colon.prepare(database, root)
    with closing(annual.connect(database, readonly=True)) as conn:
        if archive_access.publication(conn):
            return verify(conn)
        config = read_config(conn)
        report = verify(conn)
        if report['replacement_blockers'] != ['factual_coverage_review_not_recorded']:
            raise ValueError('Non-factual migration blockers remain')
        archive_release.research_coverage(conn)
        year = config['year']
        checkpoint = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
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
    fd, name = tempfile.mkstemp(prefix='.series-', suffix='.sqlite', dir=database.parent)
    os.close(fd)
    staged = Path(name)
    try:
        with closing(annual.connect(database, readonly=True)) as src, closing(sqlite3.connect(staged)) as dst:
            src.backup(dst)
        with closing(annual.connect(staged)) as conn:
            with conn:
                for path in sorted((root / 'provisional/extraction-v1' / str(year)).glob('*/*')):
                    if path.is_file():
                        relative = path.relative_to(root).as_posix()
                        key = annual.put_input(conn, relative, path.read_bytes(), 'retired_extraction_candidate', path.stem[:10])
                        candidates.append({'path': relative, 'role': 'retired_extraction_candidate', 'sha256': key})
                preserved, retire, shared = [], [], []
                for item in candidates:
                    path = (root / item['path']).resolve()
                    if not path.is_relative_to(root.resolve()) or not path.is_file():
                        raise ValueError('Preservation candidate missing or outside repository')
                    payload = path.read_bytes()
                    if payload != annual.input_bytes(conn, item['path']) or annual.digest(payload) != item['sha256']:
                        raise ValueError('Original input differs from preserved bytes')
                    item = {**item, 'bytes': len(payload)}
                    preserved.append(item)
                    if item['role'] in ('wikipedia_wikitext', 'source_metadata') and path.name.split('.')[0] in revisions:
                        shared.append(item['path'])
                    else:
                        retire.append(item)
                record = {'contract': archive_release.VERSION, 'edition': 'source-preservation', 'year': year,
                    'published_on': config['edition_date'], 'checkpoint_commit': checkpoint,
                    'independent_review_required': False, 'publication_toolchain': VERSION,
                    'uncited_claim_policy': archive_release.CLAIM_VERSION,
                    'policy': 'Verified source preservation with disclosed uncertainty; exhaustive independent review is optional research.',
                    'preserved_inputs': preserved, 'retire_files': retire, 'retained_shared_inputs': shared,
                    'limits': ['Source selection is not guaranteed exhaustive or impartial.',
                               'Original source errors remain visible; editorial accounts are separate.',
                               'Independent review is incomplete; uncited unverified claims are explicitly disclosed.']}
                for source in archive_release.INPUTS:
                    annual.put_input(conn, f'publication/implementation/{archive_release.VERSION}/{source}',
                                     (annual.ROOT / source).read_bytes(), 'publication_implementation')
                annual.put_input(conn, f'publication/{year}.json', annual.encoded(record), 'preservation_publication', media_type='application/json')
                result = verify(conn)
                conn.execute("INSERT OR REPLACE INTO archive_checks VALUES('preservation_publication',?)", (annual.encoded(result).decode(),))
            conn.execute('VACUUM')
        os.replace(staged, database)
        return result
    finally:
        staged.unlink(missing_ok=True)


def retire(database, root=annual.ROOT):
    with closing(annual.connect(database, readonly=True)) as conn:
        if not selected(conn):
            return annual_colon.retire(database, root)
        config = read_config(conn)
        verify(conn)
    with profile_context(config):
        return archive_release.retire(database, root)


def render(conn, digest):
    if not selected(conn):
        return annual_colon.render(conn, digest)
    coverage = archive_release.research_coverage(conn)
    payload = _profile_render(conn, digest)
    old = b'These have separate editorial evidence.'
    if payload.count(old) != 1:
        raise ValueError('Unverified disclosure renderer boundary drift')
    payload = payload.replace(old, (f"Separate editorial evidence: {coverage['uncited_claims_with_editorial_evidence']}; "
        f"explicitly unverified: {coverage['uncited_unverified_claims']}. "
        'Unverified means no full-event verification is established; research may be incomplete or not attempted. '
        'An unsuccessful search does not establish that a claim is false.').encode())
    payload = payload.replace(b'No attached source citation; independent evidence still required.',
        b'No attached source citation. This assertion is unverified; see its disclosure and research status above.')
    notes = ['## Unverified source claims', '',
             'The following uncited assertions are preserved unchanged. These disclosures are not factual reviews or independent corroboration.', '']
    for key, record in sorted(archive_release.load_claims(conn).items()):
        row = annual.locate_review_event(conn, record['locator'])
        notes += [f"- **{row['date']}, source line {row['line']}: unverified.** "
                  + yearbook.safe_text(row['text']) + ' Research status: '
                  + record['search_status'].replace('_', ' ') + '. '
                  + yearbook.safe_text(record['note']), '']
        if record['queries']:
            notes += ['  Recorded searches: ' + '; '.join(yearbook.safe_text(q) for q in record['queries']) + '.', '']
    findings = list(conn.execute('SELECT * FROM factual_reviews ORDER BY date,id'))
    if findings:
        notes += ['## Scoped research findings', '',
                  'These observations cover the specified passages only. They do not establish full-event verification.', '']
        for row in findings:
            evidence = list(conn.execute('SELECT * FROM review_evidence WHERE review_id=? ORDER BY ord', (row['id'],)))
            notes += [f"- **{row['date']}.** " + yearbook.safe_text(row['scope']) + ' '
                      + yearbook.safe_text(row['note']) + ' Evidence: '
                      + '; '.join(yearbook.source_link(e['publisher'], e['url']) + ' ('
                                  + yearbook.safe_text(e['access_status']) + ')' for e in evidence) + '.', '']
    marker = b'## Contents'
    if payload.count(marker) != 1:
        raise ValueError('Unverified notes need one contents boundary')
    return payload.replace(marker, ('\n'.join(notes) + '\n').encode() + marker, 1)


_engine.verify = verify
_engine.render = render
_engine.prepare = prepare
_engine.retire = retire

if __name__ == '__main__':
    _engine.main()
