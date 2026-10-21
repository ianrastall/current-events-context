"""Check a typeset yearbook against its book data: entries, citation links, index terms."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

import pymupdf

# Running heads sit above this line (points from the top edge) and are excluded,
# so entries continuing across a page break still read as one string.
BODY_TOP = 62


def squash(text):
    # Hyphenation and line breaks are layout, not content.
    return re.sub(r'[\s\-­‐‑]', '', text)


def verify(book_json, pdf):
    data = json.loads(Path(book_json).read_text(encoding='utf-8'))
    doc = pymupdf.open(pdf)
    width, height = doc[0].rect.width, doc[0].rect.height
    body = squash(''.join(page.get_text(clip=pymupdf.Rect(0, BODY_TOP, width, height)) for page in doc))
    links = {l['uri'] for page in doc for l in page.get_links() if l.get('uri')}
    events = [e for m in data['months'] for d in m['days'] for s in d['sections']
              for g in s['groups'] for e in g['events']]
    urls = {c['url'] for e in events for c in e['cites']}
    result = {
        'pages': doc.page_count,
        'bookmarks': len(doc.get_toc()),
        'entries': len(events),
        'entries_missing': [e['id'] for e in events if squash(e['text']) not in body],
        'cited_urls': len(urls),
        'urls_unlinked': sorted(urls - links),
        'index_terms': len(data['index']),
        'index_missing': [t['term'] for t in data['index'] if squash(t['term']) not in body],
        'database_sha256_in_pdf': data['meta']['database_sha256'] in (doc.metadata.get('subject') or ''),
    }
    result['ok'] = not (result['entries_missing'] or result['urls_unlinked'] or result['index_missing']) \
        and result['database_sha256_in_pdf']
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('book_json', type=Path, help='Data written by book.py --keep-json')
    p.add_argument('pdf', type=Path)
    result = verify(p.parse_args().book_json, p.parse_args().pdf)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(0 if result['ok'] else 1)


if __name__ == '__main__':
    main()
