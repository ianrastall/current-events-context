"""Print-first annual source chronicle. No network, model calls or source edits."""
from __future__ import annotations

import argparse
import calendar
from collections import Counter, defaultdict
import datetime as dt
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import unicodedata
from urllib.parse import quote, urlsplit

from reportlab import Version as REPORTLAB_VERSION
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (ActionFlowable, BaseDocTemplate, Flowable, Frame,
                               KeepTogether, NextPageTemplate, PageBreak,
                               PageTemplate, Paragraph, Spacer, Table, TableStyle)

ROOT = Path(__file__).resolve().parents[2]
VERSION = 'print-chronicle-1.0'
PAGE = (612, 792)
LEFT, RIGHT, TOP, BOTTOM = 58, 43, 58, 49
WIDTH, HEIGHT = PAGE[0] - LEFT - RIGHT, PAGE[1] - TOP - BOTTOM
GAP = 20
COL = (WIDTH - GAP) / 2
INK = colors.HexColor('#172D3A')
TEAL = colors.HexColor('#1C635F')
RUST = colors.HexColor('#9A482C')
GREY = colors.HexColor('#4A5358')
PALE = colors.HexColor('#ECF0EE')
RULE = colors.HexColor('#BFC8CA')
PAPER = colors.HexColor('#FAF8F2')
FONT_FILES = {}
FALLBACKS = []


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def display(text):
    # Presentation-only punctuation normalization. Original code points and
    # exact source bytes remain in the named database edition.
    return str(text).translate(str.maketrans({c: '-' for c in '\u2010\u2011\u2012\u2013\u2014\u2015\u2212'}))


def register_fonts(folder, fallback_files):
    for name, filename in [('Book', 'DejaVuSerif.ttf'), ('BookBold', 'DejaVuSerif-Bold.ttf'),
                           ('Sans', 'DejaVuSans.ttf'), ('SansBold', 'DejaVuSans-Bold.ttf')]:
        path = folder / filename
        pdfmetrics.registerFont(TTFont(name, str(path)))
        FONT_FILES[name] = path
    pdfmetrics.registerFontFamily('Book', normal='Book', bold='BookBold', italic='Book', boldItalic='BookBold')
    pdfmetrics.registerFontFamily('Sans', normal='Sans', bold='SansBold', italic='Sans', boldItalic='SansBold')
    for n, path in enumerate(fallback_files):
        name = f'Fallback{n}'
        pdfmetrics.registerFont(TTFont(name, str(path), subfontIndex=0))
        FONT_FILES[name] = path
        FALLBACKS.append(name)


def markup(text, font='Book'):
    """Escape source markup; fail instead of silently emitting missing glyphs."""
    result, current, chunk = [], None, []
    for ch in display(text):
        if ch in '\r\n\t':
            ch = ' '
        if ord(ch) < 32:
            raise ValueError(f'Unsupported source control character {ord(ch)}')
        face = next((n for n in [font, 'Sans', *FALLBACKS]
                     if ord(ch) in pdfmetrics.getFont(n).face.charToGlyph), None)
        if face is None:
            raise ValueError(f'Missing font coverage: U+{ord(ch):04X} {ch!r}')
        if current is not None and face != current:
            segment = html.escape(''.join(chunk))
            result.append(segment if current == font else f'<font name="{current}">{segment}</font>')
            chunk = []
        current = face
        chunk.append(ch)
    if chunk:
        segment = html.escape(''.join(chunk))
        result.append(segment if current == font else f'<font name="{current}">{segment}</font>')
    return ''.join(result)


def styles():
    def style(name, font, size, leading, **kw):
        return ParagraphStyle(name, fontName=font, fontSize=size, leading=leading,
                              textColor=kw.pop('textColor', INK), spaceAfter=kw.pop('spaceAfter', 5), **kw)
    return {
        'body': style('body', 'Book', 10, 13.2, allowWidows=0, allowOrphans=0),
        'intro': style('intro', 'Book', 11, 16, spaceAfter=11),
        'h1': style('h1', 'SansBold', 25, 30, spaceAfter=16, keepWithNext=True),
        'h2': style('h2', 'SansBold', 14, 18, spaceBefore=12, spaceAfter=8, keepWithNext=True),
        'day': style('day', 'SansBold', 14, 18, spaceBefore=12, spaceAfter=7, keepWithNext=True),
        'category': style('category', 'SansBold', 8.8, 12, textTransform='uppercase',
                          textColor=TEAL, spaceBefore=7, keepWithNext=True),
        'label': style('label', 'SansBold', 7.5, 10, textColor=GREY, keepWithNext=True, spaceBefore=3, spaceAfter=2),
        'context': style('context', 'Sans', 8.2, 11, textColor=GREY, keepWithNext=True, spaceAfter=3),
        'refs': style('refs', 'Sans', 7.6, 10, textColor=GREY, spaceAfter=10),
        'small': style('small', 'Sans', 8.4, 11.4, spaceAfter=7),
        'tiny': style('tiny', 'Sans', 7.3, 9.4),
        'url': style('url', 'Sans', 8.2, 10.8, wordWrap='CJK', spaceAfter=7),
        'editorial': style('editorial', 'Sans', 8.7, 12, borderColor=TEAL, borderWidth=0.5,
                           borderPadding=7, backColor=PALE, spaceBefore=4, spaceAfter=10),
        'index': style('index', 'Sans', 7.7, 10.2, spaceAfter=3),
        'colophon': style('colophon', 'Book', 9.6, 13.2, spaceAfter=9),
    }


class Data:
    def __init__(self, path, sample=False):
        self.path = path
        self.digest = sha(path.read_bytes())
        conn = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
        conn.row_factory = sqlite3.Row
        try:
            self.year = int(conn.execute("SELECT value FROM archive_metadata WHERE key='year'").fetchone()[0])
            self.rows = [dict(r) for r in conn.execute("SELECT * FROM event_overview WHERE role='event' ORDER BY date,category_ord,ord")]
            self.all_rows = self.rows[:]
            self.structural = {(r['date'], r['category_ord'], r['source_path_json']): dict(r)
                               for r in conn.execute('SELECT * FROM event_overview')}
            self.days = [dict(r) for r in conn.execute('SELECT * FROM sources_wikipedia ORDER BY date')]
            self.citations = defaultdict(list)
            self.subjects = defaultdict(set)
            entry_links = defaultdict(list)
            self.eids = {key(r): f'E{n:05d}' for n, r in enumerate(self.rows, 1)}
            for r in conn.execute('SELECT * FROM event_citations ORDER BY date,category_ord,entry_ord,citation_ord'):
                self.citations[(r['date'], r['category_ord'], r['entry_ord'])].append(dict(r))
            for r in conn.execute('SELECT * FROM event_links ORDER BY date,category_ord,entry_ord,link_ord'):
                k = (r['date'], r['category_ord'], r['entry_ord'])
                entry_links[k].append(r['target'])
            for row in self.rows:
                eid = self.eids[key(row)]
                for target in entry_links[key(row)]:
                    self.subjects[target].add(eid)
                parent = row['parent_path_json']
                while parent is not None:
                    ancestor = self.structural[(row['date'], row['category_ord'], parent)]
                    for target in entry_links[key(ancestor)]:
                        self.subjects[target].add(eid)
                    parent = ancestor['parent_path_json']
            self.reviews = {}
            for row in conn.execute("SELECT b.payload FROM archive_inputs i JOIN archive_blobs b USING(sha256) WHERE i.role='yearbook_event_review' ORDER BY i.path"):
                record = json.loads(row[0])
                loc = record['locator']
                found = [r for r in self.rows if r['date'] == loc['date'] and r['category_ord'] == loc['category_ord']
                         and json.loads(r['source_path_json']) == loc['source_path']]
                if len(found) != 1:
                    raise ValueError('Editorial source locator drift')
                self.reviews[key(found[0])] = record
            self.findings = [dict(r) for r in conn.execute('SELECT * FROM factual_reviews ORDER BY date,id')]
            self.finding_evidence = {r['id']: [dict(e) for e in conn.execute('SELECT * FROM review_evidence WHERE review_id=? ORDER BY ord', (r['id'],))]
                                     for r in self.findings}
            self.fragments = [dict(r) for r in conn.execute('SELECT * FROM unclassified_source ORDER BY date,ord')]
            self.notices = Counter(json.loads(r[0])['code'] for r in conn.execute('SELECT warning_json FROM extraction_warnings'))
            self.structural_count = conn.execute('SELECT count(*) FROM extraction_entries').fetchone()[0]
            self.citation_count = conn.execute('SELECT count(*) FROM event_citations').fetchone()[0]
            self.publication = json.loads(conn.execute("SELECT b.payload FROM archive_inputs i JOIN archive_blobs b USING(sha256) WHERE i.role='preservation_publication'").fetchone()[0])
        finally:
            conn.close()
        if sample:
            chosen = {'2025-01-01', '2025-01-09', '2025-01-25', '2025-04-02', '2025-04-06',
                      '2025-04-15', '2025-05-06', '2025-05-11', '2025-09-08', '2025-09-10'}
            self.rows = [r for r in self.rows if r['date'] in chosen]
        self.sample = sample
        self.sid_by_url, self.sources = {}, []
        for r in self.rows:
            for cite in self.citations[key(r)]:
                self.add_source(cite['url'], cite['publisher'] or cite['display'] or urlsplit(cite['url']).netloc,
                                'Portal citation; access or support is not implied.', cite.get('via'), cite.get('language'))
        for record in self.reviews.values():
            for e in record['evidence']:
                self.add_source(e['url'], e['publisher'], f"Editorial evidence: {e['access_status']}; checked {record['checked_on']}.")
        for evidence in self.finding_evidence.values():
            for e in evidence:
                self.add_source(e['url'], e['publisher'], f"Scoped research evidence: {e['access_status']}.")
        selected = {self.eids[key(r)] for r in self.rows}
        self.subjects = {k: v & selected for k, v in self.subjects.items() if v & selected}
        self.month_counts = Counter(r['date'][:7] for r in self.all_rows)

    def add_source(self, url, label, scope, via=None, language=None):
        if url not in self.sid_by_url:
            sid = f'S{len(self.sources) + 1:05d}'
            self.sid_by_url[url] = sid
            self.sources.append({'id': sid, 'url': url, 'labels': [], 'notes': []})
        item = self.sources[int(self.sid_by_url[url][1:]) - 1]
        label = ' '.join((label or '').strip().strip('()').split())
        if label and label not in item['labels']:
            item['labels'].append(label)
        note = scope + (f' Via: {via}.' if via else '') + (f' Language: {language}.' if language else '')
        if note not in item['notes']:
            item['notes'].append(note)

    def context(self, row):
        ancestors, parent = [], row['parent_path_json']
        while parent is not None:
            p = self.structural[(row['date'], row['category_ord'], parent)]
            ancestors.append(p['text'])
            parent = p['parent_path_json']
        return ' / '.join(reversed(ancestors))


def key(row):
    return (row['date'], row['category_ord'], row['ord'])


def ranges(values):
    values = sorted(set(values))
    runs = []
    for value in values:
        if runs and value == runs[-1][-1] + 1:
            runs[-1].append(value)
        else:
            runs.append([value])
    return ', '.join(str(r[0]) if len(r) == 1 else ', '.join(map(str, r)) if len(r) == 2 else f'{r[0]}-{r[-1]}' for r in runs)


def index_order(target):
    value = unicodedata.normalize('NFKD', display(target).strip()).casefold()
    return ''.join(ch for ch in value if unicodedata.category(ch) != 'Mn')


class Section(ActionFlowable):
    def __init__(self, title):
        self.title = title

    def apply(self, doc):
        doc.section = self.title


class Graphic(Flowable):
    def __init__(self, kind, data, month=None):
        super().__init__()
        self.kind, self.data, self.month = kind, data, month
        self.width, self.height = WIDTH, HEIGHT - 4
        self.section_key = 'cover' if kind == 'cover' else 'overview' if kind == 'overview' else month

    def text(self, x, y, text, font='Sans', size=10, color=INK):
        self.canv.setFillColor(color)
        self.canv.setFont(font, size)
        self.canv.drawString(x, y, display(text))

    def draw(self):
        c, d, w, h = self.canv, self.data, self.width, self.height
        if self.kind == 'cover':
            self.text(0, h - 20, 'CURRENT EVENTS CONTEXT', 'SansBold', 10, TEAL)
            self.text(-5, h - 145, str(d.year), 'SansBold', 108)
            self.text(0, h - 193, 'The year in record', 'Book', 31)
            self.text(0, h - 226, 'A chronicle for long-term reference', 'Sans', 14, GREY)
            c.setStrokeColor(TEAL)
            c.setLineWidth(2)
            c.line(0, h - 253, w, h - 253)
            # A data-derived calendar ribbon, not decorative world imagery.
            maximum = max(d.month_counts.values())
            for m in range(1, 13):
                n = d.month_counts[f'{d.year}-{m:02d}']
                x = (m - 1) * w / 12
                c.setFillColor(TEAL if m % 2 else INK)
                c.rect(x, 126, w / 12 - 7, 80 * n / maximum, fill=1, stroke=0)
                self.text(x, 110, calendar.month_abbr[m].upper(), 'Sans', 7, GREY)
            self.text(0, 82, 'Recorded assertions by month | heights describe this archive', 'Sans', 8, GREY)
            self.text(0, 43, f'{len(d.all_rows):,} source assertions  /  {len(d.days)} days  /  indexed sources', 'SansBold', 11)
            self.text(0, 20, 'SOURCE-PRESERVATION EDITION' + ('  |  DESIGN PROOF' if d.sample else ''), 'Sans', 9, TEAL)
        elif self.kind == 'overview':
            self.text(0, h - 18, 'THE ARCHIVE AT A GLANCE', 'SansBold', 9, TEAL)
            self.text(0, h - 59, 'The shape of the record', 'Book', 28)
            self.text(0, h - 84, 'Coverage counts describe source selection, not the scale or importance of events.', 'Sans', 8.5, GREY)
            for x, number, label in [(0, len(d.all_rows), 'event assertions'), (176, len(d.days), 'daily records'), (353, d.citation_count, 'citation occurrences')]:
                self.text(x, h - 140, f'{number:,}', 'SansBold', 31)
                self.text(x, h - 161, label, 'Sans', 9, GREY)
            y, maximum = h - 205, max(d.month_counts.values())
            for m in range(1, 13):
                n = d.month_counts[f'{d.year}-{m:02d}']
                self.text(0, y, calendar.month_name[m], 'Sans', 9)
                c.setFillColor(PALE)
                c.rect(93, y - 2, w - 140, 11, fill=1, stroke=0)
                c.setFillColor(TEAL)
                c.rect(93, y - 2, (w - 140) * n / maximum, 11, fill=1, stroke=0)
                self.text(w - 32, y, str(n), 'SansBold', 9)
                y -= 22
            c.setStrokeColor(RULE)
            c.line(0, y + 3, w, y + 3)
            self.text(0, y - 24, 'READ THE MEASURE CORRECTLY', 'SansBold', 9, TEAL)
            p = Paragraph('One assertion may describe several developments; several assertions may concern the same incident. '
                          'A tall bar is a feature of the archived portal, not a measure of deaths, intensity, geographical reach or historical significance.', styles()['intro'])
            p.wrap(w, 150)
            p.drawOn(c, 0, y - 109)
        else:
            m = int(self.month[-2:])
            month_rows = [r for r in d.all_rows if r['date'].startswith(self.month)]
            counts = Counter(r['date'] for r in month_rows)
            self.text(0, h - 18, f'CHRONOLOGY / {m:02d}', 'SansBold', 9, TEAL)
            self.text(0, h - 71, calendar.month_name[m], 'Book', 43)
            self.text(0, h - 101, f'{len(month_rows):,} source assertions in {calendar.monthrange(d.year, m)[1]} daily records', 'Sans', 12, GREY)
            self.text(0, h - 130, 'Selected dates only in this design proof.' if d.sample else 'The following pages preserve the complete daily sequence.', 'Sans', 9, GREY)
            cellw, cellh, y0 = w / 7, 37, h - 185
            for j, name in enumerate(calendar.day_abbr):
                self.text(j * cellw + 5, y0 + 21, name.upper(), 'SansBold', 8, GREY)
            weeks = calendar.monthcalendar(d.year, m)
            for i, week in enumerate(weeks):
                for j, day in enumerate(week):
                    x, y = j * cellw, y0 - i * cellh
                    if day:
                        c.setFillColor(PALE)
                        c.rect(x + 1, y - cellh + 3, cellw - 3, cellh - 3, fill=1, stroke=0)
                        self.text(x + 6, y - 11, str(day), 'SansBold', 10)
                        self.text(x + 28, y - 26, str(counts[f'{self.month}-{day:02d}']), 'Sans', 8, GREY)
            y = y0 - len(weeks) * cellh - 24
            self.text(0, y, 'SUBJECT MIX / ARCHIVED CATEGORY LABELS', 'SansBold', 8, TEAL)
            cats = Counter(r['category'] for r in month_rows)
            for name, n in cats.most_common(5):
                y -= 26
                self.text(0, y, name, 'Sans', 8.5)
                c.setFillColor(TEAL)
                c.rect(270, y - 2, (w - 310) * n / max(cats.values()), 8, fill=1, stroke=0)
                self.text(w - 27, y, str(n), 'SansBold', 8.5)
            self.text(0, 26, 'Numbers in the calendar are source-assertion counts, not incident totals.', 'Sans', 8, GREY)
            self.text(0, 9, 'Category spelling and case remain as archived; labels have not been silently merged.', 'Sans', 8, GREY)


class MirrorTemplate(PageTemplate):
    def __init__(self, name, columns, on_page):
        self.columns = columns
        super().__init__(id=name, frames=[], onPage=on_page, pagesize=PAGE)

    def beforeDrawPage(self, canvas, doc):
        x = LEFT if doc.page % 2 else RIGHT
        width = (WIDTH - GAP * (self.columns - 1)) / self.columns
        self.frames = [Frame(x + i * (width + GAP), BOTTOM, width, HEIGHT,
                             leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
                             id=f'{self.id}-{i}') for i in range(self.columns)]


class BookDoc(BaseDocTemplate):
    def __init__(self, path, data):
        super().__init__(str(path), pagesize=PAGE, title=f'{data.year}: The year in record',
                         author='current-events-context', subject=f'{VERSION}; database SHA-256 {data.digest}',
                         pageCompression=1, allowSplitting=1)
        self.data, self.section, self.event_pages, self.section_pages = data, '', {}, {}
        self.addPageTemplates([MirrorTemplate('Full', 1, self.furniture),
                               MirrorTemplate('Body', 2, self.furniture),
                               MirrorTemplate('Index', 3, self.furniture)])

    def furniture(self, c, doc):
        c.setFillColor(colors.white)
        c.rect(0, 0, *PAGE, fill=1, stroke=0)
        if self.page == 1:
            return
        x = LEFT if self.page % 2 else RIGHT
        c.setStrokeColor(RULE)
        c.setLineWidth(0.45)
        c.line(x, PAGE[1] - 39, x + WIDTH, PAGE[1] - 39)
        c.setFont('Sans', 7.8)
        c.setFillColor(GREY)
        c.drawString(x, PAGE[1] - 30, f'{self.data.year} / CURRENT EVENTS ARCHIVE')
        c.drawRightString(x + WIDTH, PAGE[1] - 30, self.section.upper())
        c.line(x, 35, x + WIDTH, 35)
        c.setFont('Sans', 7.2)
        c.drawString(x, 23, 'Source-preservation edition / ' + ('Design proof' if self.data.sample else 'Chronology and reference'))
        c.setFont('SansBold', 9)
        c.drawRightString(x + WIDTH, 22, str(self.page))

    def afterFlowable(self, f):
        eid = getattr(f, 'event_id', None)
        if eid:
            self.event_pages[eid] = self.page
            self.canv.bookmarkPage(eid)
        section = getattr(f, 'section_key', None)
        if section:
            self.section_pages[section] = self.page
            self.canv.bookmarkPage('part-' + section)
            title = calendar.month_name[int(section[-2:])] if re.fullmatch(r'\d{4}-\d\d', section) else section.replace('-', ' ').title()
            self.canv.addOutlineEntry(title, 'part-' + section, level=0, closed=False)


def section(story, title, columns='Full'):
    story += [Section(title), NextPageTemplate(columns), PageBreak()]


def linked_sources(data, urls):
    return ', '.join(f'<link href="#src-{data.sid_by_url[u]}" color="#1C635F">{data.sid_by_url[u]}</link>' for u in dict.fromkeys(urls))


def story(data, edition_date, previous_events=None, previous_sections=None):
    s = styles()
    out = [Graphic('cover', data)]
    section(out, 'Reading this edition')
    out.append(Paragraph('A record that can stand on paper', s['h1']))
    paras = [
        'This volume preserves the daily record selected by Wikipedia\'s Current Events portal for 2025. '
        'It is an archival reference, not a claim to exhaustive, impartial or independently verified news coverage. '
        'A printed copy contains the event prose, context, source register, research limits and index; no software is needed to read it.',
        'The database is the exact-source preservation layer. Plain-text Markdown accommodates simpler digital tools. '
        'This book is a readable physical layer: its contents and navigation survive without a device. '
        'It does not reproduce full publisher articles or every byte of the source wikitext. URLs and revision identities preserve the trail to that evidence.',
        'The chronology retains original source wording and original portal dates. '
        'A source account may be wrong or may reflect a changing report. '
        'Separate shaded editorial notes identify supported corrections or narrower accounts; the original assertion remains visible. '
        'Independent research is incomplete and publication does not turn the rest of the entries into checked facts.',
        'The calendar and bars measure assertions in this archive. They are not a ranking of historical importance or a count of unique incidents. '
        'A single continuing event can appear on several days. Topic context follows the source hierarchy; a parentless entry is not assigned an invented topic.',
    ]
    for p in paras:
        out.append(Paragraph(markup(p), s['intro']))
    out.append(Paragraph('Reference system', s['h2']))
    for p in [
        'E00001 identifies one source event assertion. Numbering follows source date, category and order; it remains stable in this edition. '
        'A printed editorial date may differ from the portal date.',
        'S00001 identifies a publisher URL in the source register. Every cited URL is printed there in full. '
        'A copied citation does not establish that the publisher page was opened or that it supports every part of an assertion.',
        'W0101 identifies the January 1 portal source. The Wikipedia register prints every pinned revision ID, exact payload hash and revision URL. '
        'The subject index covers event wikilink targets as written, without redirect resolution or invented entity classifications.',
    ]:
        out.append(Paragraph(markup(p), s['small']))
    out += [Paragraph('Printing and preservation', s['h2']), Paragraph(markup(
        'US Letter pages have mirrored binding margins. Print at actual size, double-sided, flipping on the long edge. '
        'Color supports navigation; text labels and bar lengths retain their meaning in monochrome. '
        'Pages are numbered continuously and can be bound in manageable sections without changing the references. '
        'The cover is page 1; the first visible folio is page 2.'), s['small'])]
    section(out, 'Contents')
    heading = Paragraph('Contents', s['h1'])
    heading.section_key = 'contents'
    out.append(heading)
    items = [('overview', 'The shape of the record'), ('anchors', 'Selected editorial anchors')]
    items += [(m, calendar.month_name[int(m[-2:])] + ' / daily chronology') for m in sorted({r['date'][:7] for r in data.rows})]
    items += [('source-notes', 'Source handling and research notes'), ('wikipedia-register', 'Pinned Wikipedia register'),
              ('publisher-register', 'Publisher source register'), ('subject-index', 'Subject index'), ('colophon', 'Edition and production record')]
    for identifier, label in items:
        page = (previous_sections or {}).get(identifier, 0)
        row = [Paragraph(f'<link href="#part-{identifier}">{markup(label, "Sans")}</link>', s['small']),
               Paragraph(str(page) if page else '-', ParagraphStyle('toc-page', parent=s['small'], alignment=TA_RIGHT))]
        t = Table([row], colWidths=[WIDTH - 46, 46], hAlign='LEFT')
        t.setStyle(TableStyle([('LINEBELOW', (0, 0), (-1, -1), 0.35, RULE),
                               ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                               ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
        out.append(t)
    out += [Spacer(1, 18), Paragraph(markup('Digital copies also include bookmarks and internal links. '
            'Printed page numbers, event identifiers and source identifiers provide equivalent navigation on paper.'), s['small'])]
    section(out, 'Archive overview')
    out.append(Graphic('overview', data))
    section(out, 'Selected editorial anchors', 'Body')
    h = Paragraph('Selected editorial anchors', s['h1'])
    h.section_key = 'anchors'
    out += [h, Paragraph(markup('A small researched selection, not a ranking or a summary of the entire year. '
             'These accounts include corrections and deliberately narrow statements where the original scope remains uncertain.'), s['small'])]
    for k, r in sorted(data.reviews.items(), key=lambda item: (item[1]['display_date'], item[0])):
        eid = data.eids[k]
        out.append(Paragraph(f"{r['display_date']} / {eid}", s['h2']))
        out.append(Paragraph(markup(r['statement']), s['body']))
        out.append(Paragraph(markup(f"Source review: {r['state']}. {r['note']}", 'Sans'), s['small']))
        out.append(Paragraph('Evidence: ' + linked_sources(data, [e['url'] for e in r['evidence']]), s['refs']))
    bymonth = defaultdict(list)
    for r in data.rows:
        bymonth[r['date'][:7]].append(r)
    for month, rows in sorted(bymonth.items()):
        section(out, calendar.month_name[int(month[-2:])])
        out.append(Graphic('month', data, month))
        section(out, calendar.month_name[int(month[-2:])], 'Body')
        day, cat = None, None
        for row in rows:
            headings = []
            if row['date'] != day:
                day, cat = row['date'], None
                when = dt.date.fromisoformat(day)
                headings.append(Paragraph(f'{when.day} {when.strftime("%B")} <font size="8" name="Sans">{when.strftime("%A")} / W{when:%m%d}</font>', s['day']))
            if row['category_ord'] != cat:
                cat = row['category_ord']
                headings.append(Paragraph(markup(row['category'], 'SansBold'), s['category']))
            eid = data.eids[key(row)]
            label = Paragraph(eid + ' / SOURCE ACCOUNT', s['label'])
            label.event_id = eid
            block = headings + [label]
            context = data.context(row)
            if context:
                block.append(Paragraph(markup(context, 'Sans'), s['context']))
            block.append(Paragraph(markup(row['text']), s['body']))
            citations = data.citations[key(row)]
            block.append(Paragraph('Sources: ' + linked_sources(data, [c['url'] for c in citations]) if citations else
                                 'No citation attached to this original entry; see the separate editorial evidence below.', s['refs']))
            out.append(KeepTogether(block))
            review = data.reviews.get(key(row))
            if review:
                out.append(Paragraph(f'<b>{eid} / EDITORIAL CLARIFICATION</b><br/>'
                    + markup(review['statement'], 'Sans') + '<br/>'
                    + markup(f"Editorial date: {review['display_date']}. Source review: {review['state']}. {review['note']}", 'Sans')
                    + '<br/>Evidence: ' + linked_sources(data, [e['url'] for e in review['evidence']]), s['editorial']))
    section(out, 'Source handling and research notes', 'Body')
    h = Paragraph('Source handling and research notes', s['h1'])
    h.section_key = 'source-notes'
    out += [h, Paragraph(markup('Extraction is a deterministic reading of exact cached Wikipedia payloads. '
            'It preserves list hierarchy, ordering, source text, links, citations and provenance. '
            'Source notices are retained even when their extraction handling has been resolved. '
            'A resolved parser notice is not a factual endorsement.'), s['body'])]
    out.append(Paragraph('Retained source notices', s['h2']))
    for name, n in sorted(data.notices.items()):
        out.append(Paragraph(markup(f'{name}: {n}', 'Sans'), s['small']))
    out.append(Paragraph('Unclassified May 6 passage', s['h2']))
    out.append(Paragraph(markup('One pasted football passage contains malformed structure and unescaped parameter separators. '
            'Its five retained fragments are shown below as source evidence. They are not counted as five events or assigned an invented category.'), s['small']))
    for f in data.fragments:
        out.append(Paragraph(markup(f"{f['date']}, source line {f['line']}", 'SansBold'), s['label']))
        out.append(Paragraph(markup(f['raw'], 'Sans'), s['url']))
    out.append(Paragraph('Empty source marker', s['h2']))
    out.append(Paragraph(markup('A literal empty bullet on July 5 is preserved in the database as an unknown-role empty marker. '
            'It is not an asserted event and is omitted from the narrative and index.'), s['small']))
    out.append(Paragraph('Scoped factual findings', s['h2']))
    out.append(Paragraph(markup('The following checks concern only their stated scopes. '
            'Access failures do not establish that a claim is false. Totals reported during disasters or conflict may change with time.'), s['small']))
    for f in data.findings:
        out.append(Paragraph(markup(f"{f['date']} / {f['assessment'].replace('_', ' ')}", 'SansBold'), s['h2']))
        out.append(Paragraph(markup(f['scope'], 'SansBold'), s['small']))
        out.append(Paragraph(markup(f['note']), s['body']))
        evidence = data.finding_evidence[f['id']]
        for e in evidence:
            out.append(Paragraph(linked_sources(data, [e['url']]) + ' / '
                + markup(f"{e['publisher']}; {e['publication_date'] or 'publication date unknown'}; access: {e['access_status']}. {e['note']}", 'Sans'), s['small']))
    section(out, 'Pinned Wikipedia register', 'Body')
    h = Paragraph('Pinned Wikipedia register', s['h1'])
    h.section_key = 'wikipedia-register'
    out += [h, Paragraph(markup('The portal date is not necessarily the capture date. '
            'A later revision may include retrospective edits. The exact cached payload hash distinguishes the archived input. '
            'Wikipedia text retains its CC BY-SA obligations; see the license and page history at the revision URL.'), s['small']),
            Paragraph('License: https://creativecommons.org/licenses/by-sa/4.0/', s['url'])]
    for d in data.days:
        url = f'https://en.wikipedia.org/w/index.php?title={quote(d["page"], safe="")}&oldid={d["revision_id"]}'
        block = [Paragraph(f"<b>W{d['date'][5:7]}{d['date'][8:10]} / {d['date']}</b><br/>"
            + markup(d['page'], 'Sans') + '<br/>'
            + markup(f"Revision {d['revision_id']}; timestamp {d['revision_timestamp'] or 'unknown'}; {d['source_mode']}", 'Sans'), s['small']),
            Paragraph('SHA-256: ' + markup(d['source_sha256'], 'Sans'), s['url']),
            Paragraph(markup(url, 'Sans'), s['url'])]
        out.append(KeepTogether(block))
    section(out, 'Publisher source register', 'Body')
    h = Paragraph('Publisher source register', s['h1'])
    h.section_key = 'publisher-register'
    out += [h, Paragraph(markup('Source identifiers point to URLs exactly as archived, without redirect resolution or inferred article titles. '
            'Labels and language/syndication information come from the source. Research notes identify separately opened evidence. '
            'Full publisher articles are not reproduced in this volume.'), s['small'])]
    for source in data.sources:
        block = [Paragraph(f'<a name="src-{source["id"]}"/>' + source['id'] + ' / '
                           + markup('; '.join(source['labels']), 'SansBold'), s['label']),
                 Paragraph(markup(source['url'], 'Sans'), s['url'])]
        notes = [n for n in source['notes'] if n != 'Portal citation; access or support is not implied.']
        if notes:
            block.append(Paragraph(markup(' '.join(notes), 'Sans'), s['tiny']))
        out.append(KeepTogether(block))
    section(out, 'Subject index', 'Index')
    h = Paragraph('Subject index', s['h2'])
    h.section_key = 'subject-index'
    out += [h, Paragraph(markup('Wikilink targets as written, followed by page numbers. '
             'Names are printed as written; alphabetization folds accents. Targets are not resolved or assigned entity types. Topic-ancestor links are included. Page references point to source assertions.'), s['tiny'])]
    initial = None
    for target, eids in sorted(data.subjects.items(), key=lambda item: (index_order(item[0]), item[0])):
        block = []
        letter = index_order(target)[:1].upper()
        if letter != initial:
            initial = letter
            block.append(Paragraph(markup(letter, 'SansBold'), s['h2']))
        pages = [(previous_events or {}).get(eid, 0) for eid in eids]
        refs = ranges(p for p in pages if p) or '-'
        block.append(Paragraph(markup(target, 'Sans') + ' <font name="SansBold">' + refs + '</font>', s['index']))
        out.append(KeepTogether(block))
    section(out, 'Edition and production record')
    h = Paragraph('Edition and production record', s['h1'])
    h.section_key = 'colophon'
    out.append(h)
    for p in [f'Source: archive/{data.year}.sqlite. Database SHA-256: {data.digest}',
              f'Publication contract: {data.publication["contract"]}. Print interpretation: {VERSION}. Edition date: {edition_date}.',
              f'Complete archive: {len(data.all_rows):,} assertions, {len(data.days)} dates, {data.structural_count:,} structural entries. '
              f'This PDF includes {len(data.rows):,} assertions, {len(data.sources):,} publisher URL records and {len(data.subjects):,} index subjects.',
              'Scope: source-preservation chronicle. Independent review remains incomplete. '
              'The book includes source errors and changing reports, with separately attributed editorial findings. '
              'No new publisher articles, pictures or model-generated illustrations were acquired for this production.',
              'Typography normalizes dash/minus variants to ASCII hyphens for print. '
              'Other source text is retained. Embedded fonts provide Unicode coverage, including fallback glyphs. '
              'The SQLite edition preserves original characters, raw markup and input bytes.',
              'All charts use database counts. Their bars, calendar figures and axis labels are generated from the same edition. '
              'The subject index uses source wikilinks only; it is not an inferred geographical or biographical classification.',
              'This PDF is designed for duplex printing at 100% scale on US Letter paper. '
              'It has selectable text, bookmarks, embedded font subsets and internal references. '
              'It is not claimed to be PDF/A, digitally signed, or a substitute for retaining the database and plain text.',
              f'Generator: reference/yearbook/build.py. SHA-256: {sha(Path(__file__).read_bytes())}. ReportLab: {REPORTLAB_VERSION}.',
              'Wikipedia attribution: English Wikipedia Current Events contributors, linked pinned revisions and page histories. '
              'Wikipedia source material retains applicable CC BY-SA terms. '
              'Publisher names and URLs are citations, not a grant of rights to their articles or pictures.']:
        out.append(Paragraph(markup(p), s['colophon']))
    out.append(Paragraph('Typeface inputs / file identities', s['h2']))
    for name, path in FONT_FILES.items():
        out.append(Paragraph(markup(f'{name}: {path.name}. SHA-256: {sha(path.read_bytes())}', 'Sans'), s['url']))
    return out


def fixed_canvas(*args, **kwargs):
    kwargs['invariant'] = 1
    return Canvas(*args, **kwargs)


def build(database, output, font_dir, fallback_files, edition_date, sample=False):
    if str(dt.date.fromisoformat(edition_date)) != edition_date:
        raise ValueError('An ISO edition date is required')
    register_fonts(font_dir, fallback_files)
    data = Data(database, sample)
    # Validate every printable text before a lengthy build; missing glyphs must
    # fail rather than become invisible squares in a physical reference.
    for r in data.rows:
        markup(r['text'])
        markup(data.context(r), 'Sans')
    for target in data.subjects:
        markup(target, 'Sans')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='cec-print-pass-') as folder:
        first = BookDoc(Path(folder) / 'pagination.pdf', data)
        first.build(story(data, edition_date), canvasmaker=fixed_canvas)
        print(f'Pagination pass: {first.page} pages', flush=True)
        fd, temporary = tempfile.mkstemp(prefix=f'.{output.stem}-', suffix='.pdf', dir=output.parent)
        os.close(fd)
        try:
            final = BookDoc(Path(temporary), data)
            final.build(story(data, edition_date, first.event_pages, first.section_pages),
                        canvasmaker=fixed_canvas)
            if final.event_pages != first.event_pages:
                raise ValueError('Chronology pagination drifted between passes')
            # Colophon follows the variable-length index and can shift. Rebuild
            # its single table-of-contents reference if needed; chronology/index
            # starts and all other references must already be stable.
            if final.section_pages != first.section_pages:
                previous = final
                final = BookDoc(Path(temporary), data)
                final.build(story(data, edition_date, previous.event_pages, previous.section_pages),
                            canvasmaker=fixed_canvas)
                if final.section_pages != previous.section_pages or final.event_pages != previous.event_pages:
                    raise ValueError('Book navigation did not converge')
            os.replace(temporary, output)
        finally:
            Path(temporary).unlink(missing_ok=True)
    if sha(database.read_bytes()) != data.digest:
        raise ValueError('Database changed while rendering')
    return {'output': str(output), 'pages': final.page, 'events': len(final.event_pages),
            'sources': len(data.sources), 'index_subjects': len(data.subjects),
            'database_sha256': data.digest, 'pdf_sha256': sha(output.read_bytes()),
            'sections': final.section_pages, 'sample': sample}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('database', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--font-dir', type=Path, default=Path('C:/Windows/Fonts') if os.name == 'nt' else Path('/usr/share/fonts/truetype/dejavu'))
    p.add_argument('--fallback-font', action='append', type=Path)
    p.add_argument('--edition-date', required=True)
    p.add_argument('--sample', action='store_true')
    args = p.parse_args()
    fallbacks = args.fallback_font
    if fallbacks is None:
        fallbacks = [p for p in [Path('C:/Windows/Fonts/arial.ttf'), Path('C:/Windows/Fonts/simsun.ttc')] if p.exists()]
    result = build(args.database, args.output or Path('dist') / (args.database.stem + '.pdf'), args.font_dir,
                   fallbacks, args.edition_date, args.sample)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
