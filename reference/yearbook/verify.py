"""Check a complete print edition against its named SQLite source (offline)."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from pypdf import PdfReader


def compact(value):
    value = str(value).translate(str.maketrans({c: '-' for c in '\u2010\u2011\u2012\u2013\u2014\u2015\u2212'}))
    return re.sub(r'\s+', '', value)


def verify(database, pdf):
    digest = hashlib.sha256(database.read_bytes()).hexdigest()
    conn = sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    reader = PdfReader(pdf)
    if reader.is_encrypted:
        raise ValueError('The preservation print copy must not be encrypted')
    texts, full_texts, used_fonts = [], [], {}
    for n, page in enumerate(reader.pages, 1):
        if tuple(round(float(v), 2) for v in page.mediabox) != (0, 0, 612, 792):
            raise ValueError(f'Unexpected page dimensions: {n}')

        def font_check(text, cm, tm, font, size):
            if text.strip() and font:
                used_fonts[str(font.get('/BaseFont'))] = font

        text = page.extract_text(visitor_text=font_check)
        full_texts.append(text)
        if '\ufffd' in text or '\x00' in text:
            raise ValueError(f'Undecodable glyph on page {n}')
        # The builder draws these four furniture strings before body text.
        # Remove only that checked prefix. Visitor coordinates can describe the
        # end of a multi-line fragment and must not be used to discard prose.
        page_lines = text.splitlines(keepends=True)
        if n > 1:
            if (len(page_lines) < 4 or
                    not page_lines[0].strip().endswith(' / CURRENT EVENTS ARCHIVE') or
                    page_lines[2].strip() != 'Source-preservation edition / Chronology and reference' or
                    page_lines[3].strip() != str(n)):
                raise ValueError(f'Unexpected page furniture: {n}')
            page_lines = page_lines[4:]
        texts.append(''.join(page_lines))
    for name, font in used_fonts.items():
        descriptor = font.get('/FontDescriptor')
        if descriptor is None and font.get('/DescendantFonts'):
            descriptor = font['/DescendantFonts'][0].get_object().get('/FontDescriptor')
        if descriptor is None or not any(k in descriptor.get_object() for k in ('/FontFile', '/FontFile2', '/FontFile3')):
            raise ValueError(f'Unembedded used typeface: {name}')
    joined = '\n'.join(texts)
    flat = compact(joined)
    if digest not in str(reader.metadata.subject) or digest not in flat:
        raise ValueError('PDF does not identify this exact database edition')
    if 'DESIGN PROOF' in joined:
        raise ValueError('A design proof is not the complete print edition')
    scope_text = compact(''.join(full_texts))
    if 'SOURCE-PRESERVATIONEDITION' not in scope_text or 'Independentresearchisincomplete' not in scope_text:
        raise ValueError('Archival scope or research limits are missing')
    events = list(conn.execute("SELECT date,category_ord,ord,text FROM event_overview WHERE role='event' ORDER BY date,category_ord,ord"))
    missing_ids, missing_prose = [], []
    for i, event in enumerate(events, 1):
        eid = f'E{i:05d}'
        if eid + '/SOURCEACCOUNT' not in flat:
            missing_ids.append(eid)
        if compact(event['text']) not in flat:
            missing_prose.append(eid)
    if missing_ids or missing_prose:
        raise ValueError(f'Incomplete event preservation: labels={missing_ids[:12]}, prose={missing_prose[:12]}')
    urls = {r[0] for r in conn.execute('SELECT DISTINCT url FROM event_citations')}
    urls.update(r[0] for r in conn.execute('SELECT url FROM review_evidence'))
    for r in conn.execute("SELECT b.payload FROM archive_inputs i JOIN archive_blobs b USING(sha256) WHERE i.role='yearbook_event_review'"):
        urls.update(e['url'] for e in json.loads(r[0])['evidence'])
    outline = [r for r in reader.outline if not isinstance(r, list)]
    sections = {str(d.title).casefold(): reader.get_destination_page_number(d) for d in outline}
    publisher_text = compact(''.join(texts[sections['publisher register']:sections['subject index']]))
    index_text = compact(''.join(texts[sections['subject index']:sections['colophon']]))
    wikipedia_text = compact(''.join(texts[sections['wikipedia register']:sections['publisher register']]))
    missing_urls = [url for url in urls if compact(url) not in publisher_text]
    if missing_urls:
        raise ValueError(f'Missing printed publisher URLs: {missing_urls[:5]}')
    for day in conn.execute('SELECT date,revision_id,source_sha256 FROM sources_wikipedia ORDER BY date'):
        wid = 'W' + day['date'][5:7] + day['date'][8:10]
        if wid not in wikipedia_text or str(day['revision_id']) not in wikipedia_text or day['source_sha256'] not in wikipedia_text:
            raise ValueError(f'Missing pinned source record: {day["date"]}')
    entries = [dict(r) for r in conn.execute('SELECT * FROM event_overview')]
    by_path = {(r['date'], r['category_ord'], r['source_path_json']): r for r in entries}
    referenced = set()
    for row in entries:
        if row['role'] != 'event':
            continue
        referenced.add((row['date'], row['category_ord'], row['ord']))
        parent = row['parent_path_json']
        while parent is not None:
            ancestor = by_path[(row['date'], row['category_ord'], parent)]
            referenced.add((ancestor['date'], ancestor['category_ord'], ancestor['ord']))
            parent = ancestor['parent_path_json']
    subjects = {r['target'] for r in conn.execute('SELECT * FROM event_links')
                if (r['date'], r['category_ord'], r['entry_ord']) in referenced}
    for target in subjects:
        if compact(target) not in index_text:
            raise ValueError(f'Missing index subject: {target}')
    for destination in outline:
        index = reader.get_destination_page_number(destination)
        if index is None or not 0 <= index < len(reader.pages):
            raise ValueError('Invalid PDF bookmark')
    if len(outline) != 21:
        raise ValueError(f'Unexpected chapter/bookmark coverage: {len(outline)}')
    lengths = [len(t.strip()) for t in texts]
    report = {'pages': len(reader.pages), 'source_events_preserved': len(events),
              'printed_publisher_urls': len(urls), 'pinned_days': 365,
              'bookmarks': len(outline), 'embedded_used_typefaces': sorted(used_fonts),
              'index_subjects_preserved': len(subjects),
              'section_pages': {k: v + 1 for k, v in sections.items()},
              'minimum_page_text_characters': min(lengths),
              'database_sha256': digest, 'pdf_sha256': hashlib.sha256(pdf.read_bytes()).hexdigest(),
              'letter_pages': True, 'unencrypted': True, 'missing_event_ids': missing_ids,
              'missing_event_prose': missing_prose, 'missing_publisher_urls': missing_urls,
              'visual_review_required': True}
    conn.close()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database', type=Path)
    parser.add_argument('pdf', type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.database, args.pdf), indent=2))
