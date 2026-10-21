"""Typeset a book chapter: chapter.txt + dossier.json -> footnoted 6 x 9 in. PDF via Typst.

Chapter source format: header lines (key: value), then paragraphs separated by
blank lines; '## ' starts a section; '{{figure:id}}' and '{{portrait:id}}' stand
on their own lines; notes are written [[S001 locator | S002 locator]] and become
footnotes, in full on a source's first citation and short thereafter. All source
text is inserted as Typst strings, never as markup.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile

BOOK = Path(__file__).resolve().parent
NOTE = re.compile(r'\[\[(.+?)\]\]')
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
          'September', 'October', 'November', 'December']


def typographic(text):
    text = re.sub(r'(^|[\s(\[\u2014\u2013/-])"', '\\1\u201c', text)
    text = text.replace('"', '\u201d')
    text = re.sub(r"(^|[\s(\[\u2014\u2013/-])'", '\\1\u2018', text)
    return text.replace("'", '\u2019').replace(' -- ', ' \u2013 ')


def s(text):
    """A Typst string literal."""
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'


def pretty(iso):
    if not iso:
        return 'undated'
    d = dt.date.fromisoformat(iso)
    return f'{d.day} {MONTHS[d.month - 1]} {d.year}'


def short_title(title):
    head = title.split(':')[0]
    return head if len(head) <= 60 else ' '.join(head.split()[:7]) + '\u2026'


class Notes:
    def __init__(self, sources):
        self.sources = sources
        self.seen = set()
        self.cited = []

    def text(self, body):
        parts = []
        for item in [p.strip() for p in body.split('|')]:
            sid, _, loc = item.partition(' ')
            if sid not in self.sources:
                raise ValueError(f'Unknown source {sid}')
            src = self.sources[sid]
            if src['access'] != 'opened':
                raise ValueError(f'{sid} was not opened')
            loc = loc.strip()
            if loc.lower().startswith('derived'):
                loc = 'figure calculated from the documents cited'
            if sid not in self.seen:
                self.seen.add(sid)
                self.cited.append(sid)
                # Full form on first citation; URLs are listed in the Sources section.
                who = '' if src['publisher'].startswith('Office of the Federal Register') else src['publisher'] + ', '
                parts.append((f'{who}\u201c{src["title"]},\u201d {pretty(src.get("published"))}, {loc}', None))
            else:
                parts.append((f'{short_title(src["title"])}, {loc}', None))
        return parts


def note_markup(parts):
    out = []
    for i, (text, url) in enumerate(parts):
        sep = '; ' if i < len(parts) - 1 else '.'
        out.append(f'#{s(typographic(text))}' + (f'#{s(", ")}#link({s(url)})' if url else '') + f'#{s(sep)}')
    return '#footnote[#h(0.3em)' + ''.join(out) + ']'


def inline(text, notes, claims, section):
    out, last = [], 0
    sentence_start = 0
    for m in NOTE.finditer(text):
        chunk = text[last:m.start()]
        out.append(f'#{s(typographic(chunk))}')
        parts = notes.text(m.group(1))
        out.append(note_markup(parts))
        sentence = text[sentence_start:m.start()].strip()
        sentence = NOTE.sub('', sentence)
        claims.append({'section': section, 'claim': sentence, 'sources': m.group(1)})
        last = m.end()
        sentence_start = m.end()
    out.append(f'#{s(typographic(text[last:]))}')
    return ''.join(out)


def build_body(chapter_txt, sources, portraits):
    raw = Path(chapter_txt).read_text(encoding='utf-8')
    head, _, body = raw.partition('\n\n')
    meta = dict(line.split(': ', 1) for line in head.splitlines())
    notes, claims = Notes(sources), []
    blocks, section = [], 0
    epi = NOTE.search(meta['epigraph_source'])
    epi_src = NOTE.sub('', meta['epigraph_source']).strip()
    blocks.append(f'#epigraph({s(typographic(meta["epigraph"]))}, [#{s(epi_src)}{note_markup(notes.text(epi.group(1)))}])')
    for para in [p.strip() for p in body.split('\n\n') if p.strip()]:
        if para.startswith('## '):
            section += 1
            blocks.append(f'#section({s(typographic(para[3:]))})')
        elif m := re.fullmatch(r'\{\{figure:([\w-]+)\}\}', para):
            blocks.append(f'#figure-block({s(m.group(1))})')
        elif m := re.fullmatch(r'\{\{portrait:([\w-]+)\}\}', para):
            p = portraits[m.group(1)]
            blocks.append(f'#portrait({s(m.group(1))}, {s(p["name"])})')
        else:
            blocks.append('#par[' + inline(para, notes, claims, section) + ']')
    return meta, '\n\n'.join(blocks), notes.cited, claims


def figure_data(year_dir, sources_dir):
    rows = json.loads((Path(sources_dir) / 'mts4.json').read_text())['data']
    customs = [{'month': r['record_date'][:7], 'billions': round(float(r['current_month_net_rcpt_amt']) / 1e9, 2)}
               for r in sorted(rows, key=lambda r: r['record_date'])
               if r['classification_desc'].strip() == 'Customs Duties' and r['record_date'][:4] in ('2024', '2025')]
    jobs = []
    bls = Path(sources_dir) / 'bls-federal.json'
    if bls.exists():
        series = json.loads(bls.read_text())['Results']['series'][0]['data']
        jobs = [{'month': f"{x['year']}-{x['period'][1:]}", 'thousands': int(x['value'])}
                for x in sorted(series, key=lambda x: (x['year'], x['period']))]
    return {
        'federal_jobs': jobs,
        'customs': customs,
        # Additional US duty on most Chinese goods (fentanyl + reciprocal), by effective date.
        'us_on_china': [['2025-01-01', 0], ['2025-02-04', 10], ['2025-03-03', 20], ['2025-04-09', 104],
                        ['2025-04-10', 145], ['2025-05-14', 30], ['2025-11-10', 20], ['2025-12-31', 20]],
        # China's across-the-board additional duty on US goods.
        'china_on_us': [['2025-01-01', 0], ['2025-04-10', 84], ['2025-04-12', 125], ['2025-05-14', 10],
                        ['2025-12-31', 10]],
        'deficit_change': [{'partner': p, 'change': v, 'label': f'{v:+.1f}'.replace('-', '−')}
                           for p, v in [('Taiwan', 73.0), ('Vietnam', 54.7), ('All partners (goods)', 25.5), ('China', -93.4)]],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('chapter_dir', type=Path)
    p.add_argument('--font-dir', type=Path, action='append', required=True)
    p.add_argument('--sources-dir', type=Path, required=True, help='Folder holding mts4.json (Treasury API extract)')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    import typst
    import pymupdf

    cdir = a.chapter_dir.resolve()
    year_dir = cdir.parent
    book = json.loads((year_dir / 'book.json').read_text(encoding='utf-8'))
    dossier = json.loads((cdir / 'dossier.json').read_text(encoding='utf-8'))
    sources = {x['id']: x for x in dossier['sources']}
    portraits = {x['id']: x for x in json.loads((cdir / 'portraits.json').read_text(encoding='utf-8'))}
    meta, body, cited, claims = build_body(cdir / 'chapter.txt', sources, portraits)
    (cdir / 'claims.json').write_text(json.dumps(claims, indent=1, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    bib = [sources[c] for c in sorted(cited, key=lambda c: (sources[c]['tier'], sources[c]['publisher'], sources[c]['title']))]
    data = {
        'meta': {**meta, 'book': book['working_title'], 'cutoff': pretty(book['source_cutoff']), 'trim': book['trim'],
                 'notes': len(claims), 'sources': len(cited), 'words': len(NOTE.sub('', (cdir / 'chapter.txt').read_text(encoding='utf-8')).split()),
                 'chapter_sha256': hashlib.sha256((cdir / 'chapter.txt').read_bytes()).hexdigest(),
                 'dossier_sha256': hashlib.sha256((cdir / 'dossier.json').read_bytes()).hexdigest(),
                 'date': dt.date.today().isoformat(),
                 **({'verified_on': pretty((v := json.loads((cdir / 'verification.json').read_text(encoding='utf-8')))['checked_on']),
                     'verification': v['result']} if (cdir / 'verification.json').exists() else {})},
        'bibliography': [{'tier': b['tier'], 'text': typographic(f'{b["publisher"]}. \u201c{b["title"]}.\u201d {pretty(b.get("published"))}.'), 'url': b['url']} for b in bib],
        'portraits': [{**v, 'credit': typographic(v['credit'])} for v in portraits.values()],
        'used_portraits': re.findall(r'\{\{portrait:([\w-]+)\}\}', (cdir / 'chapter.txt').read_text(encoding='utf-8')),
        'figures': figure_data(year_dir, a.sources_dir),
    }
    with tempfile.TemporaryDirectory(prefix='cec-chapter-') as folder:
        root = Path(folder)
        shutil.copy(BOOK / 'history.typ', root / 'history.typ')
        (root / 'body.typ').write_text(body, encoding='utf-8')
        (root / 'data.json').write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        shutil.copytree(cdir / 'figures', root / 'figures')
        try:
            pdf = typst.compile(str(root / 'history.typ'), root=str(root), font_paths=[str(f) for f in a.font_dir])
        except typst.TypstError as e:
            print(getattr(e, 'diagnostic', e))
            raise SystemExit(1)
        a.output.parent.mkdir(parents=True, exist_ok=True)
        doc = pymupdf.open(stream=pdf, filetype='pdf')
        doc.save(str(a.output), garbage=1, deflate=True, use_objstms=1, no_new_id=True)
    print(json.dumps({'output': str(a.output), 'notes': len(claims), 'sources': len(cited)}, indent=1))


if __name__ == '__main__':
    main()
