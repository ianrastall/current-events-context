"""Book records: validate JSON research records against the archive, build the book database, render dossiers.

Offline and read-only toward the archive. The JSON files under book/<year>/
are the authoritative records; book/<year>.sqlite is rebuilt from them.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from seed import annual_archive as annual  # noqa: E402

VERSION = 'book-1.0'
BOOK = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def archive_conn(path):
    conn = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def story_path(conn, row):
    out, parent = [], row['parent_path_json']
    while parent is not None:
        p = conn.execute('SELECT text, parent_path_json FROM extraction_entries WHERE date=? AND category_ord=? AND source_path_json=?',
                         (row['date'], row['category_ord'], parent)).fetchone()
        out.append(p['text'])
        parent = p['parent_path_json']
    return out[::-1]


def candidates(conn, pattern):
    """Archive events whose text or story headings match, with guarded locators."""
    rx = re.compile(pattern, re.I)
    for row in conn.execute("SELECT * FROM event_overview WHERE role='event' ORDER BY date, category_ord, ord"):
        path = story_path(conn, row)
        if rx.search(row['text']) or rx.search(' | '.join(path)):
            yield {'locator': annual.review_locator(row), 'event_sha256': annual.structured_hash(dict(row)),
                   'category': row['category'], 'story': path, 'text': row['text']}


def check_date(value, field):
    if value is not None and str(dt.date.fromisoformat(value)) != value:
        raise ValueError(f'{field}: ISO date required, got {value!r}')


def validate(year_dir):
    book = load(year_dir / 'book.json')
    archive = ROOT / book['archive']
    if sha(archive) != book['archive_sha256']:
        raise ValueError('Archive edition differs from the one this book was built on')
    check_date(book['source_cutoff'], 'source_cutoff')
    chapters = {c['id']: c for c in book['chapters']}
    records = {}
    conn = archive_conn(archive)
    try:
        for cid in sorted(chapters):
            folder = year_dir / cid
            if not folder.exists():
                continue
            inv = load(folder / 'inventory.json') if (folder / 'inventory.json').exists() else {'sections': [], 'events': []}
            dos = load(folder / 'dossier.json') if (folder / 'dossier.json').exists() else {'questions': [], 'sources': [], 'findings': []}
            sections = {s['ord'] for s in inv['sections']}
            seen = set()
            for e in inv['events']:
                row = annual.locate_review_event(conn, e['locator'])
                if annual.structured_hash(row) != e['event_sha256']:
                    raise ValueError(f'{cid}: archive entry drift at {e["locator"]["date"]}')
                key = (row['date'], row['category_ord'], row['source_path_json'])
                if key in seen:
                    raise ValueError(f'{cid}: duplicate inventory entry {key}')
                seen.add(key)
                if e['role'] not in ('core', 'context', 'excluded'):
                    raise ValueError(f'{cid}: bad role {e["role"]}')
                if e['role'] != 'excluded' and e['section'] not in sections:
                    raise ValueError(f'{cid}: unknown section {e["section"]}')
                if not e['note'].strip():
                    raise ValueError(f'{cid}: every inventory decision needs a note')
                e['_row'] = row
            src_ids = {s['id'] for s in dos['sources']}
            q_ids = {q['id'] for q in dos['questions']}
            for s in dos['sources']:
                check_date(s.get('published'), f'{s["id"]}.published')
                check_date(s['accessed'], f'{s["id"]}.accessed')
                if s.get('published') and s['published'] > book['source_cutoff']:
                    raise ValueError(f'{s["id"]}: published after the source cutoff')
                if not 1 <= s['tier'] <= 4 or not s['url'].startswith(('http://', 'https://')):
                    raise ValueError(f'{s["id"]}: tier and an http(s) URL are required')
                if 'wikipedia.org' in s['url']:
                    raise ValueError(f'{s["id"]}: Wikipedia is a finding aid, not a source')
            for f in dos['findings']:
                if f['source_id'] not in src_ids or f['question_id'] not in q_ids:
                    raise ValueError(f'{f["id"]}: unknown source or question')
                src = next(s for s in dos['sources'] if s['id'] == f['source_id'])
                if src['access'] != 'opened':
                    raise ValueError(f'{f["id"]}: findings require an opened source')
            for q in dos['questions']:
                if q['section'] not in sections:
                    raise ValueError(f'{q["id"]}: unknown section')
            records[cid] = (inv, dos)
    finally:
        conn.close()
    return book, records


def build(year_dir):
    book, records = validate(year_dir)
    output = year_dir.parent / f'{year_dir.name}.sqlite'
    fd, temporary = tempfile.mkstemp(prefix=f'.{output.stem}-', suffix='.sqlite', dir=output.parent)
    os.close(fd)
    Path(temporary).unlink()
    try:
        conn = sqlite3.connect(temporary)
        conn.executescript((BOOK / 'schema.sql').read_text(encoding='utf-8'))
        meta = {'contract': VERSION, 'year': str(book['year']), 'archive': book['archive'],
                'archive_sha256': book['archive_sha256'], 'source_cutoff': book['source_cutoff'],
                'trim': book['trim'], 'schema_sha256': sha(BOOK / 'schema.sql')}
        conn.executemany('INSERT INTO book_meta VALUES (?, ?)', sorted(meta.items()))
        for c in book['chapters']:
            conn.execute('INSERT INTO chapters VALUES (?,?,?,?,?,?,?)',
                         (c['id'], c['ord'], c['part'], c['title'], c['question'], c['word_budget'], c['status']))
        for cid, (inv, dos) in records.items():
            for s in inv['sections']:
                conn.execute('INSERT INTO sections VALUES (?,?,?,?)', (cid, s['ord'], s['title'], s['span']))
            for e in inv['events']:
                r = e['_row']
                conn.execute('INSERT INTO chapter_events VALUES (?,?,?,?,?,?,?,?,?,?)',
                             (cid, r['date'], r['category_ord'], r['source_path_json'],
                              json.dumps(e['locator'], sort_keys=True), e['event_sha256'], r['text'],
                              e.get('section'), e['role'], e['note']))
            for s in dos['sources']:
                conn.execute('INSERT INTO sources VALUES (?,?,?,?,?,?,?,?,?,?)',
                             (s['id'], s['tier'], s['kind'], s['publisher'], s['title'], s['url'],
                              s.get('published'), s['accessed'], s['access'], s['note']))
            for q in dos['questions']:
                conn.execute('INSERT INTO questions VALUES (?,?,?,?,?,?)',
                             (q['id'], cid, q['section'], q['question'], q['status'], q['answer']))
            for f in dos['findings']:
                conn.execute('INSERT INTO findings VALUES (?,?,?,?,?,?,?)',
                             (f['id'], cid, f['question_id'], f['source_id'], f['locator'], f['finding'], f.get('quotation')))
            claims_path, ver_path = year_dir / cid / 'claims.json', year_dir / cid / 'verification.json'
            if claims_path.exists():
                verified = ver_path.exists()
                for n, c in enumerate(load(claims_path)):
                    claim_id = f'{cid}-C{n:03d}'
                    # Rough type from the wording; the claim plan's finer types are assigned by hand later.
                    kind = 'quotation' if '"' in c['claim'] else 'quantity' if re.search(r'\d', c['claim']) else 'action'
                    conn.execute('INSERT INTO claims VALUES (?,?,?,?,?,?,?,?)',
                                 (claim_id, cid, c['section'], kind, c['claim'], None,
                                  'reviewed' if verified else 'draft', 'supported' if verified else None))
                    for k, item in enumerate(p.strip() for p in c['sources'].split('|')):
                        sid, _, loc = item.partition(' ')
                        conn.execute('INSERT INTO claim_evidence VALUES (?,?,?,?,?,?)',
                                     (claim_id, k, sid, 'supports', loc.strip(), None))
        conn.commit()
        problems = conn.execute('PRAGMA foreign_key_check').fetchall()
        conn.close()
        if problems:
            raise ValueError(f'Foreign key problems: {problems[:5]}')
        os.replace(temporary, output)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return output


def dossier(year_dir, cid):
    """Readable research dossier for one chapter, written beside its records."""
    book, records = validate(year_dir)
    chapter = next(c for c in book['chapters'] if c['id'] == cid)
    inv, dos = records[cid]
    sources = {s['id']: s for s in dos['sources']}
    by_q = defaultdict(list)
    for f in dos['findings']:
        by_q[f['question_id']].append(f)
    events = defaultdict(list)
    for e in inv['events']:
        events[e.get('section')].append(e)
    lines = [f'# Research dossier: {chapter["title"]}', '',
             f'Chapter {chapter["ord"]} of *{book["working_title"]}*. Status: {chapter["status"]}. '
             f'Source cutoff {book["source_cutoff"]}. Generated by `book/tool.py` from `book/{book["year"]}/{cid}/`; edit the JSON, not this file.', '',
             f'**Question.** {chapter["question"]}', '']
    roles = defaultdict(int)
    for e in inv['events']:
        roles[e['role']] += 1
    tiers = defaultdict(int)
    for s in dos['sources']:
        tiers[s['tier']] += 1
    status = defaultdict(int)
    for q in dos['questions']:
        status[q['status']] += 1
    lines += ['| Archive entries | Core | Context | Excluded | Sources (T1/T2/T3/T4) | Questions answered / partial / open |',
              '| --- | --- | --- | --- | --- | --- |',
              f'| {len(inv["events"])} | {roles["core"]} | {roles["context"]} | {roles["excluded"]} | '
              f'{len(dos["sources"])} ({tiers[1]}/{tiers[2]}/{tiers[3]}/{tiers[4]}) | '
              f'{status["answered"]} / {status["partial"]} / {status["open"]} |', '']
    for s in inv['sections']:
        lines += [f'## {s["ord"]}. {s["title"]}', '', f'*Archive span: {s["span"]}.*', '']
        for q in (q for q in dos['questions'] if q['section'] == s['ord']):
            lines += [f'### {q["id"]}: {q["question"]}', '', f'**Status: {q["status"]}.** {q["answer"]}', '']
            for f in by_q[q['id']]:
                src = sources[f['source_id']]
                quote = f' "{f["quotation"]}"' if f.get('quotation') else ''
                lines.append(f'- {f["finding"]}{quote} — [{src["publisher"]}, {src["title"]}]({src["url"]}), {f["locator"]}. *[{src["id"]}, tier {src["tier"]}]*')
            lines.append('')
        evs = [e for e in events[s['ord']] if e['role'] != 'excluded']
        if evs:
            lines += ['**Archive entries**', '']
            for e in evs:
                lines.append(f'- {e["_row"]["date"]} ({e["role"]}): {e["_row"]["text"]}' + (f' *Note: {e["note"]}*' if e['note'] != 'in scope' else ''))
            lines.append('')
    excluded = events.get(None, []) + [e for e in inv['events'] if e['role'] == 'excluded' and e.get('section') is not None]
    if excluded:
        lines += ['## Excluded keyword matches', '']
        lines += [f'- {e["_row"]["date"]}: {e["_row"]["text"][:140]}… *{e["note"]}*' for e in excluded]
        lines.append('')
    lines += ['## Sources', '', '| ID | Tier | Publisher | Title | Published | Accessed | Access |', '| --- | --- | --- | --- | --- | --- | --- |']
    for s in sorted(dos['sources'], key=lambda s: (s['tier'], s['id'])):
        lines.append(f'| {s["id"]} | {s["tier"]} | {s["publisher"]} | [{s["title"]}]({s["url"]}) | {s.get("published") or ""} | {s["accessed"]} | {s["access"]} |')
    out = year_dir / cid / 'DOSSIER.md'
    out.write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    c = sub.add_parser('candidates', help='List archive events matching a regular expression, with locators')
    c.add_argument('archive', type=Path)
    c.add_argument('pattern')
    b = sub.add_parser('build', help='Validate records and rebuild book/<year>.sqlite')
    b.add_argument('year_dir', type=Path)
    d = sub.add_parser('dossier', help='Render a chapter research dossier')
    d.add_argument('year_dir', type=Path)
    d.add_argument('chapter')
    args = p.parse_args()
    if args.command == 'candidates':
        conn = archive_conn(args.archive)
        for item in candidates(conn, args.pattern):
            print(json.dumps(item, ensure_ascii=False))
    elif args.command == 'build':
        print(build(args.year_dir.resolve()))
    else:
        print(dossier(args.year_dir.resolve(), args.chapter))


if __name__ == '__main__':
    main()
