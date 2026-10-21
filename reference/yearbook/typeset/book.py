"""Typeset annual yearbook. Offline: reads SQLite, writes JSON, compiles Typst.

The design lives in book.typ; this module only selects and arranges data.
No network access, model calls or database writes occur.
"""
from __future__ import annotations

import argparse
import calendar
from collections import Counter, defaultdict
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import unicodedata
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
VERSION = 'typeset-yearbook-1.0'

# Presentation grouping only. Category labels are still printed as archived.
CATEGORY_KEYS = {
    'armed conflicts and attacks': 'conflict', 'attacks and armed conflicts': 'conflict',
    'law and crime': 'law',
    'disasters and accidents': 'disaster', 'disaster and accidents': 'disaster',
    'disasters and incidents': 'disaster',
    'politics and elections': 'politics',
    'international relations': 'relations',
    'business and economy': 'business',
    'sports': 'sports',
    'arts and culture': 'arts',
    'science and technology': 'science',
    'health and environment': 'health',
}
CATEGORY_NAMES = {
    'conflict': 'Armed conflicts and attacks', 'law': 'Law and crime',
    'disaster': 'Disasters and accidents', 'politics': 'Politics and elections',
    'relations': 'International relations', 'business': 'Business and economy',
    'sports': 'Sports', 'arts': 'Arts and culture', 'science': 'Science and technology',
    'health': 'Health and environment', 'other': 'Other',
}
INVISIBLE = dict.fromkeys(map(ord, '\u200e\u200f\u200b\ufeff'))


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def category_key(name):
    return CATEGORY_KEYS.get((name or '').strip().casefold(), 'other')


def typographic(text):
    """Curly quotes and invisible-mark removal for print. Source bytes stay in SQLite."""
    text = ' '.join(str(text).translate(INVISIBLE).split())
    text = re.sub(r'(^|[\s(\[{\u2014\u2013/-])"', '\\1\u201c', text)
    text = text.replace('"', '\u201d')
    text = re.sub(r"(^|[\s(\[{\u2014\u2013/-])'", '\\1\u2018', text)
    return text.replace("'", '\u2019')


def subject(target):
    """MediaWiki-equivalent display of a link target: spaces, capital first letter."""
    target = ' '.join(target.replace('_', ' ').translate(INVISIBLE).split())
    page, _, section = target.partition('#')
    page = page[:1].upper() + page[1:]
    return f'{page} \u00a7 {section}' if section else page


def sort_key(term):
    value = unicodedata.normalize('NFKD', term).casefold()
    value = ''.join(ch for ch in value if unicodedata.category(ch) != 'Mn')
    value = re.sub(r'^(the|a|an) ', '', value)
    return re.sub(r'[^\w ]', '', value).strip() or value


class Archive:
    def __init__(self, path):
        self.path = path
        self.digest = sha(path.read_bytes())
        conn = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
        conn.row_factory = sqlite3.Row
        try:
            self.load(conn)
        finally:
            conn.close()

    def load(self, conn):
        q = lambda sql, *a: [dict(r) for r in conn.execute(sql, a)]
        self.meta = {r['key']: r['value'] for r in q('SELECT key, value FROM archive_metadata ORDER BY key')}
        self.year = int(self.meta['year'])
        self.entries = q('SELECT e.*, c.name AS category FROM extraction_entries e '
                         'JOIN extraction_categories c ON c.date=e.date AND c.ord=e.category_ord '
                         'ORDER BY e.date, e.category_ord, e.ord')
        self.structural = {(e['date'], e['category_ord'], e['source_path_json']): e for e in self.entries}
        self.days = q('SELECT * FROM sources_wikipedia ORDER BY date')
        self.citations = defaultdict(list)
        for r in q('SELECT * FROM event_citations ORDER BY date, category_ord, entry_ord, citation_ord'):
            self.citations[(r['date'], r['category_ord'], r['entry_ord'])].append(r)
        self.links = defaultdict(list)
        for r in q('SELECT * FROM event_links ORDER BY date, category_ord, entry_ord, link_ord'):
            if r['target']:
                self.links[(r['date'], r['category_ord'], r['entry_ord'])].append(r['target'])
        self.reviews = [json.loads(r['payload']) for r in q(
            "SELECT b.payload FROM archive_inputs i JOIN archive_blobs b USING(sha256) "
            "WHERE i.role='yearbook_event_review' ORDER BY i.path")]
        self.findings = q('SELECT * FROM factual_reviews ORDER BY date, id')
        for f in self.findings:
            f['evidence'] = q('SELECT * FROM review_evidence WHERE review_id=? ORDER BY ord', f['id'])
        self.fragments = q('SELECT * FROM unclassified_source ORDER BY date, ord')
        self.notices = Counter(json.loads(r['warning_json'])['code'] for r in q('SELECT warning_json FROM extraction_warnings'))
        self.publication = json.loads(q("SELECT b.payload FROM archive_inputs i JOIN archive_blobs b USING(sha256) "
                                        "WHERE i.role='preservation_publication'")[0]['payload'])

    def ancestors(self, entry):
        out, parent = [], entry['parent_path_json']
        while parent is not None:
            p = self.structural[(entry['date'], entry['category_ord'], parent)]
            out.append(p)
            parent = p['parent_path_json']
        return out[::-1]

    def locate(self, locator):
        found = [e for e in self.entries if e['role'] == 'event' and e['date'] == locator['date']
                 and e['category_ord'] == locator['category_ord']
                 and json.loads(e['source_path_json']) == locator['source_path']]
        if len(found) != 1:
            raise ValueError(f'Editorial locator drift: {locator}')
        return found[0]


def note_records(archive):
    """Editorial reviews and scoped checks, keyed by event."""
    notes = defaultdict(list)
    for r in archive.reviews:
        e = archive.locate(r['locator'])
        notes[(e['date'], e['category_ord'], e['ord'])].append({
            'kind': 'review', 'label': 'Editorial note',
            'state': r['state'], 'date': r['display_date'],
            'statement': typographic(r['statement']), 'note': typographic(r['note']),
            'evidence': [{'name': ev['publisher'], 'url': ev['url']} for ev in r['evidence']],
        })
    for f in archive.findings:
        e = archive.locate(json.loads(f['locator_json']))
        notes[(e['date'], e['category_ord'], e['ord'])].append({
            'kind': 'check', 'label': 'Scoped check',
            'state': f['assessment'].replace('_', ' '), 'date': f['date'],
            'statement': typographic(f['scope']), 'note': typographic(f['note']),
            'evidence': [{'name': ev['publisher'], 'url': ev['url'], 'access': ev['access_status']}
                         for ev in f['evidence']],
        })
    return notes


def build_data(archive, edition_date, sample=None):
    notes = note_records(archive)
    events = [e for e in archive.entries if e['role'] == 'event']
    eid = {(e['date'], e['category_ord'], e['ord']): n for n, e in enumerate(events, 1)}

    # Running stories: top-level topic headers, counted by distinct days.
    story_days = defaultdict(set)
    story_months = defaultdict(Counter)
    subjects = defaultdict(set)
    forms = defaultdict(Counter)
    for e in events:
        k = (e['date'], e['category_ord'], e['ord'])
        chain = archive.ancestors(e)
        if chain:
            name = typographic(chain[0]['text'])
            story_days[name].add(e['date'])
            story_months[name][int(e['date'][5:7])] += 1
        for node in [*chain, e]:
            for target in archive.links[(node['date'], node['category_ord'], node['ord'])]:
                term = subject(target)
                folded = term[:1].upper() + term[1:]
                subjects[folded].add(eid[k])
                forms[folded][term] += 1

    def stories(day_filter=None, limit=12):
        counted = []
        for name, days in story_days.items():
            ds = {d for d in days if day_filter is None or d.startswith(day_filter)}
            if ds:
                counted.append((len(ds), name))
        counted.sort(key=lambda x: (-x[0], sort_key(x[1])))
        return [{'name': n, 'days': c, 'months': [story_months[n][m] for m in range(1, 13)]}
                for c, n in counted[:limit]]

    months = []
    shown = [e for e in events if sample is None or e['date'] in sample]
    by_month = defaultdict(list)
    for e in shown:
        by_month[int(e['date'][5:7])].append(e)
    all_by_day = Counter(e['date'] for e in events)
    publisher_counts = Counter()
    for e in events:
        for c in archive.citations[(e['date'], e['category_ord'], e['ord'])]:
            publisher_counts[(c['publisher'] or c['display'] or '').strip().strip('()').strip()] += 1

    for m in sorted(by_month):
        prefix = f'{archive.year}-{m:02d}'
        month_events = [e for e in events if e['date'].startswith(prefix)]
        cats = Counter(category_key(e['category']) for e in month_events)
        days = []
        for date in sorted({e['date'] for e in by_month[m]}):
            when = dt.date.fromisoformat(date)
            sections = []
            for e in (x for x in by_month[m] if x['date'] == date):
                k = (e['date'], e['category_ord'], e['ord'])
                if not sections or sections[-1]['ord'] != e['category_ord']:
                    sections.append({'ord': e['category_ord'], 'name': ' '.join((e['category'] or 'Uncategorized').split()),
                                     'key': category_key(e['category']), 'groups': []})
                path = [typographic(a['text']) for a in archive.ancestors(e)]
                groups = sections[-1]['groups']
                if not groups or groups[-1]['path'] != path:
                    groups.append({'path': path, 'events': []})
                groups[-1]['events'].append({
                    'id': eid[k],
                    'text': typographic(e['text']),
                    'cites': [{'name': typographic((c['publisher'] or c['display'] or 'Source').strip().strip('()').strip()),
                               'url': c['url']} for c in archive.citations[k]],
                    'notes': notes.get(k, []),
                })
            for s in sections:
                del s['ord']
            days.append({'date': date, 'day': when.day, 'weekday': when.strftime('%A'),
                         'count': all_by_day[date], 'sections': sections})
        months.append({
            'num': m, 'name': calendar.month_name[m], 'abbr': calendar.month_abbr[m],
            'first_weekday': calendar.monthrange(archive.year, m)[0],
            'length': calendar.monthrange(archive.year, m)[1],
            'entries': len(month_events),
            'citations': sum(len(archive.citations[(e['date'], e['category_ord'], e['ord'])]) for e in month_events),
            'counts': [all_by_day[f'{prefix}-{d:02d}'] for d in range(1, calendar.monthrange(archive.year, m)[1] + 1)],
            'categories': [{'key': k, 'name': CATEGORY_NAMES[k], 'count': n} for k, n in cats.most_common()],
            'stories': stories(prefix, 8),
            'days': days,
        })

    year_cats = Counter(category_key(e['category']) for e in events)
    month_cats = [[sum(1 for e in events if e['date'][5:7] == f'{m:02d}' and category_key(e['category']) == k)
                   for k in CATEGORY_NAMES] for m in range(1, 13)]
    shown_ids = {eid[(e['date'], e['category_ord'], e['ord'])] for e in shown}
    index = []
    for term, ids in subjects.items():
        ids = sorted(ids & shown_ids)
        if ids:
            index.append({'term': term, 'sort': sort_key(term), 'ids': ids})
    index.sort(key=lambda x: (x['sort'], x['term']))
    for item in index:
        first = item['sort'][:1].upper()
        item['letter'] = first if first.isalpha() and first.isascii() else '#'
        del item['sort']

    all_notes = []
    for k, items in sorted(notes.items()):
        for n in items:
            if eid[k] in shown_ids:
                all_notes.append({'id': eid[k], 'date': k[0], **{x: n[x] for x in ('label', 'state', 'statement')}})

    register = [{'date': d['date'], 'revision': d['revision_id'], 'timestamp': d['revision_timestamp'] or '',
                 'sha': d['source_sha256'],
                 'url': f"https://en.wikipedia.org/w/index.php?title={quote(d['page'], safe='')}&oldid={d['revision_id']}"}
                for d in archive.days]
    publishers = sorted(({'name': typographic(n), 'count': c} for n, c in publisher_counts.items() if n),
                        key=lambda x: (sort_key(x['name']), x['name']))

    return {
        'meta': {
            'year': archive.year, 'edition_date': edition_date, 'version': VERSION,
            'database_sha256': archive.digest,
            'generator_sha256': sha(Path(__file__).read_bytes()),
            'template_sha256': sha((HERE / 'book.typ').read_bytes()),
            'contract': archive.publication.get('contract', ''),
            'sample': sample is not None,
            'days': len(archive.days), 'entries': len(events),
            'structural': len(archive.entries),
            'citations': sum(len(v) for v in archive.citations.values()),
            'publishers': len(publishers), 'subjects': len(index),
            'stories': len(story_days), 'uncited': sum(1 for e in events if not archive.citations[(e['date'], e['category_ord'], e['ord'])]),
        },
        'categories': [{'key': k, 'name': CATEGORY_NAMES[k], 'count': year_cats[k]} for k in CATEGORY_NAMES if year_cats[k]],
        'category_order': list(CATEGORY_NAMES),
        'month_categories': month_cats,
        'year_counts': [all_by_day[d['date']] for d in archive.days],
        'first_weekday': calendar.monthrange(archive.year, 1)[0],
        'stories': stories(None, 24),
        'publishers': publishers,
        'top_publishers': [{'name': typographic(n), 'count': c} for n, c in publisher_counts.most_common(15)],
        'months': months,
        'notes': all_notes,
        'register': register,
        'index': index,
        'notices': [{'code': k, 'count': v} for k, v in sorted(archive.notices.items())],
        'fragments': [{'date': f['date'], 'line': f['line'], 'raw': f['raw']} for f in archive.fragments],
    }


def build(database, output, edition_date, font_dirs, sample=None, keep_json=None):
    import typst

    if str(dt.date.fromisoformat(edition_date)) != edition_date:
        raise ValueError('An ISO edition date is required')
    archive = Archive(database)
    data = build_data(archive, edition_date, sample)
    data['meta']['typst'] = getattr(typst, '__version__', 'unknown')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='cec-typeset-') as folder:
        root = Path(folder)
        shutil.copy(HERE / 'book.typ', root / 'book.typ')
        (root / 'book.json').write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        if keep_json:
            shutil.copy(root / 'book.json', keep_json)
        stamp = dt.datetime.fromisoformat(edition_date).replace(tzinfo=dt.timezone.utc).timestamp()
        pdf, warnings = typst.compile_with_warnings(str(root / 'book.typ'), root=str(root),
                                                    font_paths=[str(p) for p in font_dirs],
                                                    timestamp=int(stamp))
        for w in warnings:
            print('typst warning:', w)
        fd, temporary = tempfile.mkstemp(prefix=f'.{output.stem}-', suffix='.pdf', dir=output.parent)
        os.close(fd)
        try:
            # Object streams roughly halve the tagged-PDF structure overhead.
            import pymupdf
            doc = pymupdf.open(stream=pdf, filetype='pdf')
            doc.save(temporary, garbage=1, deflate=True, use_objstms=1, no_new_id=True)
            doc.close()
            os.replace(temporary, output)
        finally:
            Path(temporary).unlink(missing_ok=True)
    if sha(database.read_bytes()) != archive.digest:
        raise ValueError('Database changed while rendering')
    return {'output': str(output), 'bytes': output.stat().st_size, 'pdf_sha256': sha(output.read_bytes()),
            'database_sha256': archive.digest, 'entries': data['meta']['entries'], 'sample': sample is not None}


SAMPLE_DATES = {'2025-01-01', '2025-01-02', '2025-01-09', '2025-01-25', '2025-04-02', '2025-04-06',
                '2025-05-06', '2025-09-08', '2025-09-10'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('database', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--edition-date', required=True)
    p.add_argument('--font-dir', type=Path, action='append', required=True,
                   help='Folder containing Source Serif 4 and Source Sans 3 OTF files (repeatable).')
    p.add_argument('--sample', action='store_true', help='Typeset a short labeled proof of selected dates.')
    p.add_argument('--keep-json', type=Path, help='Also write the intermediate book data here.')
    args = p.parse_args()
    output = args.output or Path('dist') / f'{args.database.stem}-yearbook.pdf'
    result = build(args.database, output, args.edition_date, args.font_dir,
                   SAMPLE_DATES if args.sample else None, args.keep_json)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
