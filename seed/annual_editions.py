"""Versioned annual extraction profiles and year-appropriate preservation Markdown.

The original annual/release modules remain immutable for the 2025 edition.
Scoped compatibility contexts apply the pinned successor profile only while a
single-threaded annual operation runs; they never change a cached source.
"""
import argparse
from contextlib import closing, contextmanager
import copy
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from unittest.mock import patch

from seed import annual_archive as annual, archive_access, archive_release, extract, yearbook
from seed.inline import project as original_projection

PROFILE = 'preservation-extraction-2024-1.0'
INPUTS = ('seed/annual_editions.py', 'reference/schema/ANNUAL_EDITIONS.md',
          'seed/yearbook.py', 'reference/schema/YEARBOOK.md',
          'reference/overrides/2024-preservation.json',
          'reference/overrides/2024-extraction.json')
NOTICES = 'reference/overrides/2024-preservation.json'
ORIGINAL_MAKE = annual.make_extraction
ORIGINAL_COMPARE = annual.compare_candidate
ORIGINAL_INITIALIZE = annual.initialize


def projection(template):
    """Only display explicit source arguments; never compute a conversion."""
    result = original_projection(template)
    if result is not None:
        return result
    name = str(template.name).strip().lower()

    def arg(key):
        return str(template.get(key).value).strip() if template.has(key) else ''

    number = r'[+−-]?\d[\d,.]*'
    units = {'mi2': 'mi2', 'km2': 'km2', 'sqkm': 'sqkm', 'mph': 'mph',
             'F': '°F', 'F-change': '°F change', 'lb': 'lb', 'acre': 'acre',
             'hectare': 'hectare', 'e6ha': 'million ha'}
    if name in ('conv', 'convert', 'cvt') and re.fullmatch(number, arg(1)):
        if arg(2) in units:
            return arg(1) + ' ' + units[arg(2)]
        if arg(2) in ('–', '-', 'to') and re.fullmatch(number, arg(3)) and arg(4) in ('km',):
            return f'{arg(1)}{arg(2)}{arg(3)} {arg(4)}'
    if name == 'us$' and re.fullmatch(number, arg(1)):
        return 'US$' + arg(1)
    if name in ('hms', 'hdms') and arg(1) and not re.search(r'[{}<>]', arg(1)):
        # The surrounding source can already supply HMS; do not double it.
        return arg(1)
    if name == 'chem' and arg(1) == 'O' and arg(2) == '2':
        return 'O2'
    if name == 'rws' and arg(1) and not re.search(r'[{}<>]', arg(1)):
        return arg(1)
    if name == 'm' and arg(1) == 'ww' and not arg(2):
        return 'Mww'
    return None


def make_profile(records, day, meta, payload, legacy, overrides=None):
    with patch.object(extract, 'project_template', projection):
        doc = ORIGINAL_MAKE(day, meta, payload, legacy, overrides)
    for rule in (r for r in records if r['date'] == day):
        if rule['source_sha256'] != meta['source_sha256']:
            raise ValueError('Preservation notice source drift')
        found = [w for w in doc['warnings'] if w['code'] == rule['code']
                 and w['line'] == rule['line'] and w['category'] == rule['category']
                 and w['source_path'] == rule['source_path']
                 and extract.fingerprint(w['raw']) == rule['raw_sha256']]
        if len(found) != 1:
            raise ValueError(f'Preservation notice locator drift: {day}/{rule["code"]}')
        warning = found[0]
        if rule.get('action') == 'category_comment':
            # One exact source heading failed the frozen parser's full-line
            # match because of its trailing HTML comment. Preserve that line.
            raw_line = warning['raw']
            if not re.fullmatch(r"'''Law and crime'''<!--.*?-->", raw_line):
                raise ValueError('Unexpected category source fragment')
            index = next(i for i, c in enumerate(doc['categories'])
                         if c['name'] == rule['category'] and c['line'] < rule['line'])
            old = doc['categories'][index]
            moved = [e for e in old['entries'] if e['line'] > rule['line']]
            if len(moved) != 1 or moved[0]['depth'] != 1 or moved[0]['parent_path'] is not None:
                raise ValueError('Category repair no longer matches its exact source structure')
            old['entries'] = [e for e in old['entries'] if e not in moved]
            moved[0]['source_path'] = [1]
            doc['categories'].insert(index + 1, {'name': rule['name'], 'links': [],
                'citations': [], 'entries': moved, 'line': rule['line'], 'raw': raw_line})
            warning['interpretation'] = 'explicit_source_category_with_comment'
        warning['resolution'] = rule['resolution']
        warning['message'] += ' Resolution: ' + rule['reason']
    return doc


def compare_profile(prior, doc):
    if doc['date'] != '2024-02-26':
        return ORIGINAL_COMPARE(prior, doc)
    if prior['source_page'] != doc['source_page'] or prior['date'] != doc['date']:
        raise ValueError('Category repair changed pinned source identity')
    before = {e['line']: (c['name'], e) for c in prior['categories'] for e in c['entries']}
    after = {e['line']: (c['name'], e) for c in doc['categories'] for e in c['entries']}
    if before.keys() != after.keys() or len(doc['categories']) != len(prior['categories']) + 1:
        raise ValueError('Category repair changed source entry coverage')
    changes = []
    for line, (category, old) in before.items():
        new_category, new = after[line]
        expected = copy.deepcopy(old)
        if line == 15 and category == 'International relations':
            expected['source_path'] = [1]
            if new_category != 'Law and crime':
                raise ValueError('Explicit category repair missing')
            changes.append({'line': line, 'reasons': ['explicit_category_followed_by_comment'],
                            'before_sha256': annual.structured_hash(old),
                            'after_sha256': annual.structured_hash(new)})
        elif new_category != category:
            raise ValueError('Unexpected category reassignment')
        if expected != new:
            raise ValueError('Category repair changed an event or its evidence')
    return {'source_identity_preserved': True, 'entries_preserved': len(before),
            'event_leaf_delta': 0, 'entry_deltas': changes}


@contextmanager
def profile_context(records):
    def make(*args, **kwargs):
        return make_profile(records, *args, **kwargs)
    with patch.object(annual, 'make_extraction', make), patch.object(annual, 'compare_candidate', compare_profile):
        yield


def profile_name(conn):
    row = conn.execute("SELECT value FROM archive_metadata WHERE key='extraction_profile'").fetchone()
    return row[0] if row else None


def snapshot_path(name):
    return f'publication/implementation/{PROFILE}/{name}'


def records_from_archive(conn):
    if profile_name(conn) != PROFILE:
        raise ValueError('Unsupported annual extraction profile')
    for name in INPUTS:
        if annual.input_bytes(conn, snapshot_path(name)) != (annual.ROOT / name).read_bytes():
            raise ValueError(f'Annual edition implementation drift: {name}')
    return json.loads(annual.input_bytes(conn, snapshot_path(NOTICES)))


def build(year, output, root=annual.ROOT):
    if year != 2024:
        raise ValueError('This successor profile is approved for 2024 only')
    root = Path(root)
    records = json.loads((root / NOTICES).read_bytes())

    def initialize(path, selected_year, selected_root=annual.ROOT):
        conn = ORIGINAL_INITIALIZE(path, selected_year, selected_root)
        with conn:
            conn.execute('INSERT INTO archive_metadata VALUES(?,?)', ('extraction_profile', PROFILE))
            for name in INPUTS:
                annual.put_input(conn, snapshot_path(name), (annual.ROOT / name).read_bytes(), 'edition_implementation')
        return conn

    with profile_context(records), patch.object(annual, 'initialize', initialize):
        return annual.build_year(year, output, root)


def verify(conn, *, complete=True):
    if profile_name(conn) is None:
        return archive_release.verify(conn, complete=complete) if archive_access.publication(conn) else annual.verify(conn, complete=complete)
    records = records_from_archive(conn)
    with profile_context(records):
        result = archive_release.verify(conn, complete=complete) if archive_access.publication(conn) else annual.verify(conn, complete=complete)
    return {**result, 'extraction_profile': PROFILE}


def prepare(database, root=annual.ROOT):
    with closing(annual.connect(database, readonly=True)) as conn:
        records = records_from_archive(conn)
    with profile_context(records):
        return archive_release.prepare(database, root)


def retire(database, root=annual.ROOT):
    with closing(annual.connect(database, readonly=True)) as conn:
        records = records_from_archive(conn)
        verify(conn)
    with profile_context(records):
        return archive_release.retire(database, root)


def render(conn, digest):
    if profile_name(conn) is None:
        return archive_release.render(conn, digest)
    report = verify(conn)
    record = archive_access.publication(conn)
    reviews = yearbook.review_report(conn)
    year = record['year']
    days = conn.execute('SELECT count(*) FROM extraction_days').fetchone()[0]
    old = yearbook.render(conn, digest).decode('utf-8')
    body = old[old.index('## Contents'):].replace('**Source account; full-event review pending.**', '**Archived source account.**')
    header = [f'# {year}: current events archive', '', '**Source-preservation edition.**', '',
        f'This chronological reference preserves {report["events"]:,} Wikipedia event assertions across {days} dates, with pinned source revisions, actual topic hierarchy and original citations. The SQLite database is authoritative; this UTF-8 Markdown is its readable companion.', '',
        'The sources reflect Wikipedia’s selection and wording. They are not guaranteed exhaustive, impartial or factually correct. Publication does not mean every event has been independently checked. Original errors and dated reporting figures remain visible; separately labeled editorial accounts record the limited checks actually performed.', '',
        f'Database: [{year}.sqlite]({year}.sqlite). Edition SHA-256: `{digest}`. Publication contract: `{archive_release.VERSION}`. Extraction/Markdown profile: `{PROFILE}`. Date: {record["published_on"]}.', '',
        f'The {reviews["source_events_without_attached_citations"]} entries originally lacking attached citations have separately cited editorial evidence. Full-event reviews complete: {reviews["full_event_reviews_complete"]}; partial: {reviews["full_event_reviews_partial"]}; events without a full-event review: {reviews["events_without_full_event_review"]:,}. Partial reviews do not establish every detail of the original statement.', '',
        'Exact original daily files, cached Wikipedia payloads/metadata and previous extraction candidates are embedded losslessly, with a guarded retirement manifest and Git checkpoint. Wikipedia text is attributed through pinned revision links and remains subject to CC BY-SA terms. Publisher URLs identify evidence; full publisher articles and images are not reproduced.', '',
        'Template displays use explicit original arguments, without live expansion, currency exchange or computed unit conversion. Complete original markup remains in SQLite. Source-depth gaps and malformed brackets are preserved rather than silently repaired.', '', '## Source handling notes', '']
    for row in conn.execute('SELECT warning_json FROM extraction_warnings ORDER BY date,ord'):
        w = json.loads(row[0])
        if w['code'] in ('ORPHAN_TOPIC', 'DEPTH_JUMP', 'MALFORMED_MARKUP') or w['resolution'] == 'source_category_comment_recognized':
            header += [f'- **{w["date"]}, {w["code"]}, source line {w["line"]}.** '
                       + yearbook.safe_text(w['message']) + ' Source fragment: ' + yearbook.safe_text(w['raw']), '']
    return ('\n'.join(header) + '\n' + body.rstrip() + '\n').encode('utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('build'); p.add_argument('year', type=int); p.add_argument('--output', required=True, type=Path)
    for command in ('prepare', 'verify', 'render', 'retire'):
        p = sub.add_parser(command); p.add_argument('database', type=Path)
    args = parser.parse_args()
    if args.command == 'build':
        result = build(args.year, args.output)
    elif args.command in ('prepare', 'retire'):
        result = globals()[args.command](args.database)
    else:
        with closing(annual.connect(args.database, readonly=True)) as conn:
            if args.command == 'render':
                if any(Path(str(args.database) + s).exists() for s in ('-wal', '-journal')):
                    raise ValueError('Close database writers before rendering')
                payload = render(conn, annual.digest(args.database.read_bytes()))
                target = args.database.with_suffix('.md')
                fd, name = tempfile.mkstemp(prefix='.edition-', dir=target.parent)
                try:
                    with os.fdopen(fd, 'wb') as stream:
                        stream.write(payload)
                    os.replace(name, target)
                finally:
                    Path(name).unlink(missing_ok=True)
                result = {'markdown_sha256': annual.digest(payload), 'bytes': len(payload)}
            else:
                result = verify(conn)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
