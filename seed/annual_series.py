"""Declarative, pinned preservation profiles for successive annual editions."""
import argparse
from collections import Counter
from contextlib import closing, contextmanager
import copy
import datetime as dt
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile
from unittest.mock import patch

import mwparserfromhell as mw

from seed import annual_archive as annual, annual_editions, archive_access, archive_release, extract, yearbook

VERSION = 'annual-series-1.0'
INPUTS = ('seed/annual_series.py', 'reference/schema/ANNUAL_SERIES.md',
          'seed/annual_editions.py', 'reference/schema/ANNUAL_EDITIONS.md',
          'seed/yearbook.py', 'reference/schema/YEARBOOK.md')
ORIGINAL_MAKE = annual.make_extraction
ORIGINAL_COMPARE = annual.compare_candidate
ORIGINAL_INITIALIZE = annual.initialize
ORIGINAL_VERIFY = annual.verify


def config_path(year):
    return f'reference/overrides/{year}-series.json'


def snapshot_path(name):
    return f'publication/implementation/{VERSION}/{name}'


def projection(template):
    value = annual_editions.projection(template)
    if value is not None:
        return value
    name = str(template.name).strip().lower()
    def arg(key):
        return str(template.get(key).value).strip() if template.has(key) else ''
    if not template.params and name in ('nbsp', 'snd', 'ndash', 'mdash'):
        return {'nbsp': ' ', 'snd': ' – ', 'ndash': '–', 'mdash': '—'}[name]
    number = r'[+−-]?\d[\d,.]*(?:\s*(?:thousand|million|billion|trillion))?'
    currencies = {'¥': 'JPY', 'jpy': 'JPY', 'yen': 'JPY', 'usd': 'US$',
                  'hkd': 'HKD', 'philippine peso': 'PHP', 'indian rupee': 'INR',
                  'euro': 'EUR', 'gbp': 'GBP', 'bdt': 'BDT', 'aud': 'AUD',
                  'cad': 'CAD', 'cny': 'CNY', 'rmb': 'CNY', 'krw': 'KRW',
                  'inr': 'INR', 'php': 'PHP', 'zar': 'ZAR', 'sgd': 'SGD',
                  'rub': 'RUB', 'chf': 'CHF', 'nzd': 'NZD', 'pkr': 'PKR'}
    if name in currencies and re.fullmatch(number, arg(1)):
        return currencies[name] + ' ' + arg(1)
    units = {'sqmi': 'sqmi', 'mile': 'mile', 'miles': 'miles',
             'C-change': '°C change', 'e6km2': 'million km2', 'e6m3': 'million m3',
             'm3': 'm3', 'ft3': 'ft3', 'sqft': 'sqft', 'km/h': 'km/h',
             'kph': 'kph', 'kn': 'kn', 't': 't', 'tonne': 'tonne',
             'tonnes': 'tonnes', 'liter': 'liter', 'litre': 'litre'}
    if name in ('conv', 'convert', 'cvt') and re.fullmatch(number, arg(1)) and arg(2) in units:
        return arg(1) + ' ' + units[arg(2)]
    return None


def validate_config(config):
    if config['version'] != VERSION or type(config['year']) is not int:
        raise ValueError('Unsupported annual series configuration')
    if str(dt.date.fromisoformat(config['edition_date'])) != config['edition_date']:
        raise ValueError('Explicit ISO edition date required')
    for rule in config['roles'] + config['notices']:
        if dt.date.fromisoformat(rule['date']).year != config['year'] or not rule['reason'].strip():
            raise ValueError('Out-of-year or undocumented source rule')
        for key in ('source_sha256', 'raw_sha256'):
            if not re.fullmatch('[0-9a-f]{64}', rule[key]):
                raise ValueError('Source rules require exact hashes')
    for rule in config['roles']:
        if rule['role'] not in ('topic', 'event'):
            raise ValueError('Source role overrides must identify a topic or an explicitly approved assertion')
        if rule['role'] == 'event' and (rule.get('interpretation') != 'approved_source_statement' or type(rule.get('line')) is not int):
            raise ValueError('A source assertion needs an explicit guarded interpretation')


def commented_lines(raw):
    """Find real parsed HTML comment spans, including comments in template args."""
    spans, cursor = [], 0
    for node in mw.parse(raw).filter_comments(recursive=True):
        fragment = str(node)
        start = raw.find(fragment, cursor)
        if start < 0:
            raise ValueError('Comment location cannot be matched to exact source')
        end = start + len(fragment)
        spans.append((start, end))
        cursor = end
    result, offset = set(), 0
    for number, line in enumerate(raw.splitlines(keepends=True), 1):
        marker = re.match(r'^\s*([*:]+)', line)
        if marker and any(start <= offset + marker.start(1) < end for start, end in spans):
            result.add(number)
        offset += len(line)
    return result


def repath(entries):
    stack, counters = [], {}
    for entry in entries:
        while stack and stack[-1]['depth'] >= entry['depth']:
            stack.pop()
        parent = stack[-1]['source_path'] if stack else None
        key = tuple(parent or [])
        counters[key] = counters.get(key, 0) + 1
        entry['parent_path'] = parent
        entry['source_path'] = list(parent or []) + [counters[key]]
        stack.append(entry)


def make_profile(config, day, meta, payload, legacy, overrides=None):
    if overrides:
        raise ValueError('Declare all series role interpretations in its pinned configuration')
    roles = [r for r in config['roles'] if r['date'] == day]
    with patch.object(extract, 'project_template', projection):
        doc = ORIGINAL_MAKE(day, meta, payload, legacy, roles)
    comments = commented_lines(payload.decode('utf-8'))
    for category in doc['categories']:
        for entry in category['entries']:
            if entry['line'] not in comments:
                continue
            entry['role'] = 'unknown'
            for warning in doc['warnings']:
                if warning['line'] == entry['line'] and warning['source_path'] == entry['source_path']:
                    warning['interpretation'] = 'commented_source_non_event'
                    if warning['code'] in ('AMBIGUOUS_ROLE', 'ORPHAN_TOPIC'):
                        warning['resolution'] = 'source_comment_non_event'
            doc['warnings'].append({'code': 'SOURCE_COMMENTED_ENTRY', 'date': day,
                'source_page': meta['page'], 'revision_id': meta['revision_id'],
                'source_sha256': meta['source_sha256'], 'category': category['name'],
                'source_path': entry['source_path'], 'line': entry['line'], 'raw': entry['raw'],
                'interpretation': 'unclassified_source_requires_factual_research',
                'resolution': 'source_comment_non_event',
                'message': 'Commented-out source material preserved as a non-event; not live portal news and excluded from event totals.'})
    for rule in (r for r in config['notices'] if r['date'] == day):
        if rule['source_sha256'] != meta['source_sha256']:
            raise ValueError('Series notice source drift')
        found = [w for w in doc['warnings'] if w['code'] == rule['code']
                 and w['line'] == rule['line'] and w['category'] == rule['category']
                 and w['source_path'] == rule['source_path']
                 and extract.fingerprint(w['raw']) == rule['raw_sha256']]
        expected_occurrences = rule.get('occurrences', 1)
        if type(expected_occurrences) is not int or expected_occurrences < 1 or len(found) != expected_occurrences:
            raise ValueError(f'Series notice locator drift: {day}/{rule["code"]}')
        warning = found[0]
        action = rule['action']
        if action == 'category_comment':
            if expected_occurrences != 1:
                raise ValueError('A category repair must identify one exact heading')
            match = re.fullmatch(r"'''(.+?)'''(?:<!--.*?-->)+", warning['raw'].strip())
            if not match or match.group(1) != rule['name']:
                raise ValueError('Category rule does not match the explicit source heading')
            index = next(i for i, c in enumerate(doc['categories']) if c['name'] == rule['category'] and c['line'] < rule['line'])
            previous = doc['categories'][index]
            moved = [e for e in previous['entries'] if e['line'] > rule['line']]
            if not moved:
                raise ValueError('Category repair has no matching source entries')
            previous['entries'] = [e for e in previous['entries'] if e['line'] < rule['line']]
            repath(moved)
            doc['categories'].insert(index + 1, {'name': rule['name'], 'links': [], 'citations': [],
                'entries': moved, 'line': rule['line'], 'raw': warning['raw']})
            warning['interpretation'] = 'explicit_source_category_with_comment'
        elif action == 'unclassified':
            for warning in found:
                warning['interpretation'] = 'unclassified_source_requires_factual_research'
        elif action not in ('preserve_notice', 'retain_template'):
            raise ValueError('Unsupported series notice action')
        for warning in found:
            warning['resolution'] = 'guarded_series_' + action
            warning['message'] += ' Resolution: ' + rule['reason']
    return doc


def compare_profile(config, prior, doc):
    rules = [r for r in config['notices'] if r['date'] == doc['date'] and r['action'] == 'category_comment']
    normalized = copy.deepcopy(doc)
    before_entries = {(c['line'], e['line']): e for c in prior['categories'] for e in c['entries']}
    role_changes = []
    assertion_delta = sum(e['role'] == 'event' for c in doc['categories'] for e in c['entries']) - sum(e['role'] == 'event' for c in prior['categories'] for e in c['entries'])
    comment_lines = {w['line'] for w in doc['warnings'] if w['code'] == 'SOURCE_COMMENTED_ENTRY' and w['resolution'] == 'source_comment_non_event'}
    statements = {r['line'] for r in config['roles'] if r['date'] == doc['date'] and r['role'] == 'event' and r.get('interpretation') == 'approved_source_statement'}
    for category in normalized['categories']:
        for entry in category['entries']:
            old = before_entries.get((category['line'], entry['line']))
            if old is None or old['role'] == entry['role']:
                continue
            if (entry['role'] == 'unknown' and entry['line'] in comment_lines) or (old['role'] == 'unknown' and entry['role'] == 'event' and entry['line'] in statements):
                role_changes.append({'line': entry['line'], 'before': old['role'], 'after': entry['role'],
                    'reason': 'commented_source_non_event' if entry['line'] in comment_lines else 'approved_source_statement'})
                entry['role'] = old['role']
    if not rules:
        result = ORIGINAL_COMPARE(prior, normalized)
        result['source_role_changes'] = role_changes
        result['event_leaf_delta'] = assertion_delta  # Historical field counts assertions, including containers.
        result['event_assertion_delta'] = assertion_delta
        return result
    added_lines = {r['line'] for r in rules}
    old_categories = {c['line']: c for c in prior['categories']}
    current = {c['line']: c for c in normalized['categories'] if c['line'] not in added_lines}
    if current.keys() != old_categories.keys():
        raise ValueError('Unexpected category coverage change')
    before = [(c['line'], e) for c in prior['categories'] for e in c['entries']]
    after = {e['line']: (c, e) for c in normalized['categories'] for e in c['entries']}
    if len(after) != sum(len(c['entries']) for c in normalized['categories']) or len(after) != len(before):
        raise ValueError('Category repair changed entry coverage')
    audit = []
    for category_line, old in before:
        category, entry = after[old['line']]
        if category['line'] in added_lines:
            rule = next(r for r in rules if r['line'] == category['line'])
            if old_categories[category_line]['name'] != rule['category'] or category['name'] != rule['name']:
                raise ValueError('Unexpected category reassignment')
            audit.append({'line': entry['line'], 'from': rule['category'], 'to': rule['name'],
                          'source_path_before': old['source_path'], 'source_path_after': entry['source_path']})
            entry['source_path'], entry['parent_path'] = old['source_path'], old['parent_path']
        elif category['line'] != category_line:
            raise ValueError('Unexpected category reassignment')
    for line, category in current.items():
        category['entries'] = [after[e['line']][1] for e in old_categories[line]['entries']]
    normalized['categories'] = [current[c['line']] for c in prior['categories']]
    result = ORIGINAL_COMPARE(prior, normalized)
    result['category_repairs'] = audit
    result['source_role_changes'] = role_changes
    result['event_leaf_delta'] = assertion_delta
    result['event_assertion_delta'] = assertion_delta
    return result


@contextmanager
def profile_context(config):
    validate_config(config)
    def make(*args, **kwargs):
        return make_profile(config, *args, **kwargs)
    def compare(prior, doc):
        return compare_profile(config, prior, doc)
    def transfer(conn, *, complete=True):
        result = ORIGINAL_VERIFY(conn, complete=complete)
        count = conn.execute("SELECT count(*) FROM extraction_entries e WHERE e.role='unknown' AND EXISTS(SELECT 1 FROM extraction_warnings w WHERE w.date=e.date AND json_extract(w.warning_json,'$.code')='SOURCE_COMMENTED_ENTRY' AND json_extract(w.warning_json,'$.resolution')='source_comment_non_event' AND json_extract(w.warning_json,'$.line')=e.line AND json_extract(w.warning_json,'$.category')=(SELECT name FROM extraction_categories c WHERE c.date=e.date AND c.ord=e.category_ord) AND json(json_extract(w.warning_json,'$.source_path'))=json(e.source_path_json)) AND NOT EXISTS(SELECT 1 FROM extraction_warnings w WHERE w.date=e.date AND json_extract(w.warning_json,'$.code')='SOURCE_EMPTY_MARKER' AND json_extract(w.warning_json,'$.line')=e.line)").fetchone()[0]
        result['known_commented_source_entries'] = count
        result['unknown_heading_roles'] -= count
        if result['unknown_heading_roles'] < 0:
            raise ValueError('Commented-source accounting exceeds unknown entries')
        if not result['unknown_heading_roles'] and not result['unresolved_warnings']:
            result['replacement_blockers'] = [b for b in result['replacement_blockers'] if b != 'unresolved_extraction_warnings']
        return result
    with patch.object(annual, 'make_extraction', make), patch.object(annual, 'compare_candidate', compare), patch.object(annual, 'verify', transfer):
        yield


def selected_profile(conn):
    row = conn.execute("SELECT value FROM archive_metadata WHERE key='extraction_profile'").fetchone()
    return row[0] if row else None


def read_config(conn):
    if selected_profile(conn) != VERSION:
        raise ValueError('Unknown annual series profile')
    year = int(conn.execute("SELECT value FROM archive_metadata WHERE key='year'").fetchone()[0])
    for name in (*INPUTS, config_path(year)):
        if annual.input_bytes(conn, snapshot_path(name)) != (annual.ROOT / name).read_bytes():
            raise ValueError(f'Annual series implementation drift: {name}')
    config = json.loads(annual.input_bytes(conn, snapshot_path(config_path(year))))
    validate_config(config)
    if config['year'] != year:
        raise ValueError('Series configuration year mismatch')
    return config


def build(year, output, root=annual.ROOT):
    root = Path(root)
    config = json.loads((root / config_path(year)).read_bytes())
    validate_config(config)
    if config['year'] != year:
        raise ValueError('Configuration year mismatch')
    def initialize(path, selected_year, selected_root=annual.ROOT):
        conn = ORIGINAL_INITIALIZE(path, selected_year, selected_root)
        with conn:
            conn.execute('INSERT INTO archive_metadata VALUES(?,?)', ('extraction_profile', VERSION))
            for name in (*INPUTS, config_path(year)):
                annual.put_input(conn, snapshot_path(name), (root / name).read_bytes(), 'edition_implementation')
        return conn
    with profile_context(config), patch.object(annual, 'initialize', initialize):
        return annual.build_year(year, output, root)


def verify(conn, *, complete=True):
    if selected_profile(conn) != VERSION:
        return annual_editions.verify(conn, complete=complete)
    config = read_config(conn)
    with profile_context(config):
        result = archive_release.verify(conn, complete=complete) if archive_access.publication(conn) else annual.verify(conn, complete=complete)
    return {**result, 'extraction_profile': VERSION}


def prepare(database, root=annual.ROOT):
    database, root = Path(database), Path(root)
    with closing(annual.connect(database, readonly=True)) as conn:
        if archive_access.publication(conn):
            return verify(conn)
        config = read_config(conn)
        report = verify(conn)
        if report['replacement_blockers'] != ['factual_coverage_review_not_recorded']:
            raise ValueError('Non-factual migration blockers remain')
        if yearbook.review_report(conn)['uncited_events_without_editorial_evidence']:
            raise ValueError('Uncited original events lack separate editorial evidence')
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
                    'policy': 'Verified source preservation with disclosed uncertainty; exhaustive independent review is optional research.',
                    'preserved_inputs': preserved, 'retire_files': retire, 'retained_shared_inputs': shared,
                    'limits': ['Source selection is not guaranteed exhaustive or impartial.',
                               'Original source errors remain visible; editorial accounts are separate.',
                               'Independent review is incomplete.']}
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
        config = read_config(conn)
        verify(conn)
    with profile_context(config):
        return archive_release.retire(database, root)


def render(conn, digest):
    if selected_profile(conn) != VERSION:
        return annual_editions.render(conn, digest)
    report = verify(conn)
    config = read_config(conn)
    reviews = yearbook.review_report(conn)
    year = config['year']
    days = conn.execute('SELECT count(*) FROM extraction_days').fetchone()[0]
    draft = yearbook.render(conn, digest).decode('utf-8')
    body = draft[draft.index('## Contents'):].replace('**Source account; full-event review pending.**', '**Archived source account.**')
    lines = [f'# {year}: current events archive', '', '**Source-preservation edition.**', '',
        f'This chronological reference preserves {report["events"]:,} Wikipedia event assertions across {days} dates, including topic hierarchy, original citations and pinned revisions. SQLite is authoritative; this UTF-8 Markdown is its readable companion.', '',
        'Source selection and wording are Wikipedia’s, and are not certified exhaustive, impartial or factually correct. Publication does not imply independent checking of every assertion. Original wording, errors and dated reporting figures remain visible. Editorial accounts are separately labeled and cited.', '',
        f'Database: [{year}.sqlite]({year}.sqlite). Edition SHA-256: `{digest}`. Publication: `{archive_release.VERSION}`. Extraction/Markdown profile: `{VERSION}`. Date: {config["edition_date"]}.', '',
        f'Original entries without attached citations: {reviews["source_events_without_attached_citations"]}. These have separate editorial evidence. Full-event reviews complete: {reviews["full_event_reviews_complete"]}; partial: {reviews["full_event_reviews_partial"]}; without a full-event review: {reviews["events_without_full_event_review"]:,}. Partial reviews leave unsupported details explicit.', '',
        'Exact original daily files, Wikipedia payloads/metadata and prior extraction candidates are embedded losslessly, with hashes, an exact retirement manifest and Git checkpoint. Wikipedia attribution and CC BY-SA obligations remain applicable. Publisher URLs identify evidence; full publisher articles and images are not reproduced.', '',
        'Template display uses explicit original arguments without calculated conversions, live expansion or inferred links. Unsupported template markup and source reliability tags remain visible. Orphan topics and malformed/unbulleted material are preserved with the handling notes below; no missing child or event is invented.', '',
        'Commented-out source assertions remain labeled non-event material in the database and handling notes; they are excluded from ordinary event totals.', '',
        '## Source handling notes', '']
    for row in conn.execute('SELECT warning_json FROM extraction_warnings ORDER BY date,ord'):
        w = json.loads(row[0])
        if w['code'] not in ('SOURCE_TEMPLATE', 'SOURCE_METADATA', 'CITATION_CONTINUATION', 'AMBIGUOUS_ROLE'):
            lines += [f'- **{w["date"]}, {w["code"]}, source line {w["line"]}.** '
                      + yearbook.safe_text(w['message']) + ' Source fragment: ' + yearbook.safe_text(w['raw']), '']
    return ('\n'.join(lines) + '\n' + body.rstrip() + '\n').encode('utf-8')


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
                fd, name = tempfile.mkstemp(prefix='.series-', dir=target.parent)
                try:
                    with os.fdopen(fd, 'wb') as stream:
                        stream.write(payload)
                    os.replace(name, target)
                finally:
                    Path(name).unlink(missing_ok=True)
                result = {'sha256': annual.digest(payload), 'bytes': len(payload)}
            else:
                result = verify(conn)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
