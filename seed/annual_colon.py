"""Pinned annual dispatcher with exact, disclosed legacy-projection reconciliation."""
from contextlib import contextmanager
from contextlib import closing
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

from seed import annual_archive as annual, annual_legacy, extract, sqlite_archive, yearbook

_spec = importlib.util.spec_from_file_location('seed._annual_colon_legacy', Path(annual_legacy.__file__))
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)
VERSION = 'annual-series-1.2'
_base.VERSION = VERSION
_engine = _base._engine
_engine.VERSION = VERSION
_engine.INPUTS = (*_engine.INPUTS, 'seed/annual_colon.py', 'reference/schema/ANNUAL_COLON.md')
_context = _engine.profile_context
_profile_verify = _engine.verify
_profile_render = _engine.render
_profile_prepare = _engine.prepare
_profile_retire = _engine.retire


def validate_baseline(rule, meta, payload, legacy_payload, doc):
    """Prove one guarded baseline is the exact projection of preserved structure."""
    if rule['interpretation'] != 'structured_legacy_projection' or not rule['reason'].strip():
        raise ValueError('Unsupported legacy baseline interpretation')
    if (meta['source_sha256'] != rule['source_sha256']
            or annual.digest(payload) != rule['source_sha256']
            or annual.digest(legacy_payload) != rule['legacy_sha256']
            or annual.structured_hash(doc) != rule['extraction_sha256']
            or doc['date'] != rule['date']):
        raise ValueError('Legacy baseline guard drift')
    legacy = annual.yaml.load(legacy_payload, Loader=annual.LOADER)
    if legacy['date'] != rule['date'] or extract.legacy_view(doc) != legacy['wikipedia']['categories']:
        raise ValueError('Legacy baseline is not the exact structured projection')
    return {'date': rule['date'], 'interpretation': rule['interpretation'],
            'source_sha256': rule['source_sha256'], 'legacy_sha256': rule['legacy_sha256'],
            'extraction_sha256': rule['extraction_sha256'], 'reason': rule['reason']}


def reconcile_baselines(config, conn, report):
    report = dict(report)
    remaining = list(report['legacy_replay_differences'])
    disclosed = []
    seen = set()
    for rule in config.get('legacy_baselines', []):
        day = rule['date']
        if day[:4] != str(config['year']) or day in seen:
            raise ValueError('Duplicate or out-of-year legacy baseline rule')
        seen.add(day)
        row = conn.execute('SELECT * FROM day_ingestions WHERE date=?', (day,)).fetchone()
        if row is None:
            continue  # A partial ingest must not invent a date that has not been ingested.
        if day not in remaining:
            raise ValueError('Legacy baseline rule no longer identifies a replay difference')
        disclosed.append(validate_baseline(rule, json.loads(row['source_metadata_json']),
            annual.input_bytes(conn, row['source_path']), annual.input_bytes(conn, row['legacy_path']),
            sqlite_archive.export_extraction_doc(conn, day)))
        remaining.remove(day)
    report['legacy_replay_differences'] = remaining
    report['disclosed_legacy_projection_reconciliations'] = disclosed
    if not remaining:
        report['replacement_blockers'] = [b for b in report['replacement_blockers'] if b != 'baseline_reconciliation_required']
    # Per-day original reconciliation facts remain unchanged in SQLite.
    return report


@contextmanager
def profile_context(config):
    with _context(config):
        previous = annual.verify
        def transfer(conn, *, complete=True):
            return reconcile_baselines(config, conn, previous(conn, complete=complete))
        with patch.object(annual, 'verify', transfer):
            yield


_engine.profile_context = profile_context
build = _engine.build
make_profile = _engine.make_profile
read_config = _engine.read_config


def verify(conn, *, complete=True):
    if annual_legacy.annual_series.selected_profile(conn) == VERSION:
        return _profile_verify(conn, complete=complete)
    return annual_legacy.verify(conn, complete=complete)


def prepare(database, root=annual.ROOT):
    with closing(annual.connect(database, readonly=True)) as conn:
        selected = annual_legacy.annual_series.selected_profile(conn)
    if selected == VERSION:
        return _profile_prepare(database, root)
    return annual_legacy.prepare(database, root)


def retire(database, root=annual.ROOT):
    with closing(annual.connect(database, readonly=True)) as conn:
        selected = annual_legacy.annual_series.selected_profile(conn)
    if selected == VERSION:
        return _profile_retire(database, root)
    return annual_legacy.retire(database, root)


def render(conn, digest):
    if annual_legacy.annual_series.selected_profile(conn) == VERSION:
        payload = _profile_render(conn, digest)
        citations = list(conn.execute('''SELECT e.date,e.category,e.line,e.text,c.url,c.publisher,c.display
            FROM event_citations c JOIN event_overview e
            ON c.date=e.date AND c.category_ord=e.category_ord AND c.entry_ord=e.ord
            WHERE e.role <> 'event' ORDER BY e.date,e.category_ord,e.ord,c.citation_ord'''))
        if citations:
            notes = ['## Citations attached to source topic headers', '',
                     'These citations belong to the preserved topic headers, rather than individual child assertions.', '']
            for row in citations:
                notes += [f"- {row['date']}, source line {row['line']}: "
                          + yearbook.safe_text(row['text']) + ' '
                          + yearbook.source_link(row['publisher'] or row['display'] or 'Source', row['url']), '']
            payload += ('\n' + '\n'.join(notes).rstrip() + '\n').encode('utf-8')
        rules = read_config(conn).get('legacy_baselines', [])
        if rules:
            notes = ['## Historical baseline replay', '']
            for rule in rules:
                notes += [f"- {rule['date']}: " + rule['reason'], '']
            marker = b'## Contents'
            if payload.count(marker) != 1:
                raise ValueError('Historical baseline notes need one contents boundary')
            payload = payload.replace(marker, ('\n'.join(notes) + '\n').encode('utf-8') + marker, 1)
        return payload
    return annual_legacy.render(conn, digest)


_engine.verify = verify
_engine.render = render
_engine.prepare = prepare
_engine.retire = retire

if __name__ == '__main__':
    _engine.main()
