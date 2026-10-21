"""Book research records stay consistent with the archive edition they cite."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'book'))
import tool  # noqa: E402


class BookRecordsTest(unittest.TestCase):
    def test_2025_records_validate(self):
        book, records = tool.validate(ROOT / 'book' / '2025')
        self.assertEqual(book['archive'], '2025/2025.sqlite')
        inv, dos = records['ch02']
        self.assertTrue(inv['events'])
        self.assertTrue(all(s['access'] == 'opened' for s in dos['sources'] if any(f['source_id'] == s['id'] for f in dos['findings'])))

    def test_wikipedia_source_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            year = Path(folder) / '2025'
            (year / 'ch02').mkdir(parents=True)
            book = json.loads((ROOT / 'book' / '2025' / 'book.json').read_text(encoding='utf-8'))
            book['archive'] = str((ROOT / book['archive']).relative_to(ROOT))
            (year / 'book.json').write_text(json.dumps(book), encoding='utf-8')
            inv = {'sections': [{'ord': 1, 'title': 't', 'span': 's'}], 'events': []}
            dos = {'questions': [], 'findings': [], 'sources': [{
                'id': 'S1', 'tier': 3, 'kind': 'article', 'publisher': 'Wikipedia', 'title': 't',
                'url': 'https://en.wikipedia.org/wiki/Tariff', 'published': None,
                'accessed': '2026-10-21', 'access': 'opened', 'note': ''}]}
            (year / 'ch02' / 'inventory.json').write_text(json.dumps(inv), encoding='utf-8')
            (year / 'ch02' / 'dossier.json').write_text(json.dumps(dos), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'finding aid'):
                tool.validate(year)


if __name__ == '__main__':
    unittest.main()
