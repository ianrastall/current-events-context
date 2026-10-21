"""Recovery tests for preservation exports, including lossy-export hazards."""
from contextlib import closing
import importlib.util
from pathlib import Path
import socket
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('build_tiers', Path(__file__).resolve().parents[1] / 'tools/build_tiers.py')
tiers = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tiers)


class BundleTests(unittest.TestCase):
    def test_typed_cells_distinguish_source_values(self):
        values = [None, '', b'', b'\x00\xff', 'n', '\\N', 'tab\tLF\nCR\rNUL\0',
                  "quote's λ 中", 0, -9223372036854775808, 1.125]
        self.assertEqual(values, [tiers.decode(tiers.cell(v)) for v in values])
        self.assertEqual(len(values), len({tiers.cell(v) for v in values}))
        with self.assertRaises(ValueError):
            tiers.decode('t\\q')

    def test_offline_roundtrips_determinism_and_damage_detection(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(socket, 'socket', side_effect=AssertionError('network')):
            root = Path(temp)
            db = root / '2025.sqlite'
            with closing(sqlite3.connect(db)) as conn:
                conn.executescript('CREATE TABLE records(id INTEGER PRIMARY KEY, value, payload BLOB);'
                                   'CREATE VIRTUAL TABLE search USING fts5(text);'
                                   'CREATE VIEW reading AS SELECT id,value FROM records;'
                                   'PRAGMA user_version=17;')
                conn.executemany('INSERT INTO records VALUES(?,?,?)', [(1, None, b''), (2, '', b'\xff\0'), (3, 'a\tb\nc\rd\0中', b'hello')])
                conn.execute("INSERT INTO search(rowid,text) VALUES(7,'durable earthquake')")
                conn.commit()
            db.with_suffix('.md').write_text('A readable chronicle\n', encoding='utf-8')
            original = db.read_bytes()
            first, second = root / 'first.tar', root / 'second.tar'
            report = tiers.build(db, first)
            tiers.build(db, second)
            self.assertTrue(report['sql_restore_verified'])
            self.assertTrue(report['tsv_restore_verified'])
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(db.read_bytes(), original)
            self.assertGreater(tiers.verify_bundle(first)['members_verified'], 10)
            data = bytearray(first.read_bytes())
            marker = data.index(b'A readable chronicle')
            data[marker] ^= 1
            first.write_bytes(data)
            with self.assertRaisesRegex(ValueError, 'Checksum mismatch'):
                tiers.verify_bundle(first)

    def test_unsupported_virtual_content_fails(self):
        with closing(sqlite3.connect(':memory:')) as conn:
            conn.executescript("CREATE TABLE content(text); CREATE VIRTUAL TABLE search USING fts5(text,content='content');")
            with self.assertRaisesRegex(ValueError, 'Unsupported virtual'):
                tiers.inventory(conn)
