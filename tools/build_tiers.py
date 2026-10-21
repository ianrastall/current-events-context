"""Build and restore offline annual preservation exports without source writes."""
import argparse
from contextlib import closing
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import tarfile
import tempfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'preservation-bundle-1.0'
FORMAT = '''Preservation bundle 1.0
Encoding: UTF-8, no BOM, LF line endings. SQL is SQLite SQL, not ASCII.
TSV: first row contains column names escaped as below (no type prefix).
Each following cell begins with its SQLite storage-class tag:
n = NULL (no suffix); i = decimal integer; f = Python float repr (finite);
t = text; b = hexadecimal BLOB. Empty text is t; empty BLOB is b.
Text escapes: backslash=\\\\, tab=\\t, LF=\\n, CR=\\r, NUL=\\0.
All other Unicode characters are literal. Split rows/tabs BEFORE decoding.
schema.json describes table order, columns, logical row counts/hashes and
database header pragmas. Virtual-table TSV starts with its explicit rowid.
views/ contains reading projections; restore only tables/.
schema.sql creates tables, indexes, views and triggers, in that order.
Restore creates tables first, loads rows, then creates other objects.
Only ordinary tables and internal-content FTS5 tables are supported.
FTS shadow tables are derived and excluded; indexes are rebuilt on restore.
SHA-256 logical hashes cover the exact header and typed TSV row bytes.
SQL and TSV restores are both checked before a bundle is installed.
Database file layout and FTS shadow-table bytes may differ after restore.
MANIFEST.sha256 and CHECKSUMS.tsv cover every other member, not themselves.
The outer TAR hash is reported separately, avoiding a circular checksum.
'''


def ident(name):
    return '"' + name.replace('"', '""') + '"'


def escape(value):
    return value.replace('\\', '\\\\').replace('\t', '\\t').replace('\n', '\\n').replace('\r', '\\r').replace('\0', '\\0')


def unescape(value):
    out, i = [], 0
    codes = {'\\': '\\', 't': '\t', 'n': '\n', 'r': '\r', '0': '\0'}
    while i < len(value):
        if value[i] == '\\':
            i += 1
            if i == len(value) or value[i] not in codes:
                raise ValueError('Invalid TSV escape')
            out.append(codes[value[i]])
        else:
            out.append(value[i])
        i += 1
    return ''.join(out)


def cell(value):
    if value is None:
        return 'n'
    if isinstance(value, int):
        return 'i' + str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError('Non-finite floats are unsupported')
        return 'f' + repr(value)
    if isinstance(value, bytes):
        return 'b' + value.hex()
    if isinstance(value, str):
        return 't' + escape(value)
    raise TypeError(type(value))


def decode(value):
    tag, data = value[:1], value[1:]
    if tag == 'n' and not data:
        return None
    if tag == 'i':
        return int(data)
    if tag == 'f':
        result = float(data)
        if not math.isfinite(result):
            raise ValueError('Non-finite float')
        return result
    if tag == 'b':
        return bytes.fromhex(data)
    if tag == 't':
        return unescape(data)
    raise ValueError('Invalid typed TSV cell')


def sql_value(value):
    if value is None:
        return 'NULL'
    if isinstance(value, bytes):
        return "X'" + value.hex() + "'"
    if isinstance(value, str):
        if '\0' in value:
            return "CAST(X'" + value.encode('utf-8').hex() + "' AS TEXT)"
        return "'" + value.replace("'", "''") + "'"
    cell(value)  # Reject unsupported numeric values.
    return repr(value)


def checksum(path):
    h, crc, size = hashlib.sha256(), 0, 0
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
            crc = zlib.crc32(block, crc)
            size += len(block)
    return {'sha256': h.hexdigest(), 'crc32': f'{crc:08x}', 'bytes': size}


def read_only(path):
    conn = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    conn.execute('PRAGMA query_only=ON')
    conn.execute('BEGIN')
    return conn


def inventory(conn):
    if sqlite3.sqlite_version_info < (3, 37):
        raise RuntimeError('SQLite 3.37+ is required')
    kinds = {r[1]: r[2] for r in conn.execute('PRAGMA main.table_list')}
    objects = []
    for kind, name, sql in conn.execute("SELECT type,name,sql FROM sqlite_schema WHERE sql IS NOT NULL ORDER BY CASE type WHEN 'table' THEN 0 WHEN 'index' THEN 1 WHEN 'view' THEN 2 ELSE 3 END,name"):
        if name.startswith('sqlite_') or kinds.get(name) == 'shadow':
            continue
        if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', name):
            raise ValueError(f'Unsupported export filename: {name}')
        virtual = kinds.get(name) == 'virtual'
        if virtual:
            if not re.search(r'\bUSING\s+fts5\s*\(', sql, re.I) or re.search(r'\bcontent\s*=', sql, re.I):
                raise ValueError(f'Unsupported virtual table: {name}')
            config = list(conn.execute(f'SELECT * FROM {ident(name + "_config")}'))
            if config != [('version', 4)]:
                raise ValueError(f'Non-default FTS configuration: {name}')
        columns = []
        pk = []
        if kind in ('table', 'view'):
            for r in conn.execute(f'PRAGMA table_xinfo({ident(name)})'):
                if r[6] in (2, 3):
                    raise ValueError('Generated columns require a successor export contract')
                if not r[6]:
                    columns.append(r[1])
                    if r[5]:
                        pk.append((r[5], r[1]))
            if virtual:
                columns.insert(0, 'rowid')
        objects.append({'type': kind, 'name': name, 'sql': sql,
                        'virtual': virtual, 'columns': columns,
                        'order': ['rowid'] if virtual else [v for _, v in sorted(pk)] or columns})
    return objects


def rows(conn, obj):
    columns = ','.join(map(ident, obj['columns']))
    order = ','.join(map(ident, obj['order']))
    return conn.execute(f'SELECT {columns} FROM {ident(obj["name"])} ORDER BY {order}')


def lines(conn, obj):
    yield ('\t'.join(map(escape, obj['columns'])) + '\n').encode('utf-8')
    for row in rows(conn, obj):
        yield ('\t'.join(map(cell, row)) + '\n').encode('utf-8')


def logical(conn, obj):
    h, count = hashlib.sha256(), -1
    for data in lines(conn, obj):
        h.update(data)
        count += 1
    return {'rows': count, 'sha256': h.hexdigest()}


def validate(conn, metadata):
    if conn.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
        raise ValueError('SQLite integrity check failed')
    if list(conn.execute('PRAGMA foreign_key_check')):
        raise ValueError('Foreign-key check failed')
    for obj in metadata['objects']:
        if obj['type'] in ('table', 'view'):
            if logical(conn, obj) != obj['logical']:
                raise ValueError(f'Logical restore mismatch: {obj["name"]}')
        if obj['virtual']:
            conn.execute(f'INSERT INTO {ident(obj["name"])}({ident(obj["name"])}) VALUES (\'integrity-check\')')
    actual = {(o['type'], o['name'], o['sql']) for o in inventory(conn)}
    expected = {(o['type'], o['name'], o['sql']) for o in metadata['objects']}
    if actual != expected:
        raise ValueError('Restored schema differs')
    for key, value in metadata['pragmas'].items():
        if conn.execute(f'PRAGMA {key}').fetchone()[0] != value:
            raise ValueError(f'Restored pragma differs: {key}')


def restore_tsv(folder, output):
    metadata = json.loads((folder / 'schema.json').read_text(encoding='utf-8'))
    if metadata['format'] != VERSION:
        raise ValueError('Unknown bundle version')
    if output.exists():
        raise FileExistsError(output)
    with closing(sqlite3.connect(output)) as conn:
        conn.execute('PRAGMA foreign_keys=OFF')
        for obj in metadata['objects']:
            if obj['type'] == 'table':
                conn.execute(obj['sql'])
        for obj in metadata['objects']:
            if obj['type'] != 'table':
                continue
            # Metadata comes from a bundle: reject paths and unsafe identifiers.
            if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', obj['name']):
                raise ValueError('Unsafe table filename')
            sql = f'INSERT INTO {ident(obj["name"])} ({",".join(map(ident, obj["columns"]))}) VALUES ({",".join("?" for _ in obj["columns"])})'
            with (folder / 'tables' / (obj['name'] + '.tsv')).open(encoding='utf-8', newline='') as stream:
                if next(stream) != '\t'.join(map(escape, obj['columns'])) + '\n':
                    raise ValueError('TSV header mismatch')
                conn.executemany(sql, (tuple(map(decode, line.removesuffix('\n').split('\t'))) for line in stream))
        for obj in metadata['objects']:
            if obj['type'] != 'table':
                conn.execute(obj['sql'])
        for key, value in metadata['pragmas'].items():
            if key not in ('application_id', 'user_version') or not isinstance(value, int):
                raise ValueError('Unsupported pragma')
            conn.execute(f'PRAGMA {key}={value}')
        validate(conn, metadata)
        conn.commit()
    return metadata


def write_exports(conn, folder):
    objects = inventory(conn)
    metadata = {'format': VERSION, 'objects': objects, 'pragmas': {
        key: conn.execute(f'PRAGMA {key}').fetchone()[0] for key in ('application_id', 'user_version')}}
    (folder / 'tables').mkdir()
    (folder / 'views').mkdir()
    schema = '\n'.join(o['sql'] + ';' for o in objects) + '\n'
    (folder / 'schema.sql').write_text(schema, encoding='utf-8', newline='\n')
    with (folder / 'archive.sql').open('w', encoding='utf-8', newline='\n') as sql:
        sql.write('PRAGMA foreign_keys=OFF;\nBEGIN TRANSACTION;\n')
        for obj in objects:
            if obj['type'] == 'table':
                sql.write(obj['sql'] + ';\n')
        for obj in objects:
            if obj['type'] not in ('table', 'view'):
                continue
            target = folder / ('tables' if obj['type'] == 'table' else 'views') / (obj['name'] + '.tsv')
            with target.open('wb') as stream:
                for line in lines(conn, obj):
                    stream.write(line)
            obj['logical'] = logical(conn, obj)
            if obj['type'] == 'table':
                prefix = f'INSERT INTO {ident(obj["name"])} ({",".join(map(ident, obj["columns"]))}) VALUES('
                for row in rows(conn, obj):
                    sql.write(prefix + ','.join(map(sql_value, row)) + ');\n')
        for obj in objects:
            if obj['type'] != 'table':
                sql.write(obj['sql'] + ';\n')
        for key, value in metadata['pragmas'].items():
            sql.write(f'PRAGMA {key}={value};\n')
        sql.write('COMMIT;\n')
    (folder / 'schema.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    (folder / 'FORMAT.txt').write_text(FORMAT, encoding='ascii', newline='\n')
    return metadata


def build(database, output, pdf=None):
    database = database.resolve()
    markdown = database.with_suffix('.md')
    if not markdown.is_file():
        raise FileNotFoundError(markdown)
    for source in (database, markdown, pdf):
        if source and output.resolve() == source.resolve():
            raise ValueError('Output must not replace an input')
    before = checksum(database)
    input_hashes = {p: checksum(p) for p in (database, markdown, pdf) if p}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='cec-bundle-') as temporary:
        folder = Path(temporary) / database.stem
        folder.mkdir()
        # Explicit allowlist; never recursively inventory the repository.
        for source, name in [(database, database.name), (markdown, markdown.name),
                             (ROOT / 'PRIMER.txt', 'PRIMER.txt'),
                             (Path(__file__), 'build_tiers.py')]:
            (folder / name).write_bytes(source.read_bytes())
        if pdf:
            (folder / (database.stem + '.pdf')).write_bytes(pdf.read_bytes())
        with closing(read_only(database)) as conn:
            if conn.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                raise ValueError('Source integrity check failed')
            metadata = write_exports(conn, folder)
        restore_tsv(folder, Path(temporary) / 'tsv-restore.sqlite')
        with closing(sqlite3.connect(Path(temporary) / 'sql-restore.sqlite')) as restored:
            restored.executescript((folder / 'archive.sql').read_text(encoding='utf-8'))
            validate(restored, metadata)
        report = {'format': VERSION, 'database': before,
                  'markdown': checksum(markdown), 'sql_restore_verified': True,
                  'tsv_restore_verified': True,
                  'tables': sum(o['type'] == 'table' for o in metadata['objects']),
                  'views': sum(o['type'] == 'view' for o in metadata['objects'])}
        if pdf:
            report['pdf'] = checksum(pdf)
        (folder / 'VERIFICATION.json').write_text(json.dumps(report, indent=2) + '\n', encoding='ascii', newline='\n')
        files = sorted(p for p in folder.rglob('*') if p.is_file())
        sha_lines, crc_lines = [], ['path\tbytes\tcrc32\tsha256\n']
        for path in files:
            name = path.relative_to(folder).as_posix()
            info = checksum(path)
            sha_lines.append(f'{info["sha256"]}  {name}\n')
            crc_lines.append(f'{name}\t{info["bytes"]}\t{info["crc32"]}\t{info["sha256"]}\n')
        (folder / 'MANIFEST.sha256').write_text(''.join(sha_lines), encoding='ascii', newline='\n')
        (folder / 'CHECKSUMS.tsv').write_text(''.join(crc_lines), encoding='ascii', newline='\n')
        fd, stage = tempfile.mkstemp(prefix='.preservation-', suffix='.tar', dir=output.parent)
        os.close(fd)
        try:
            with tarfile.open(stage, 'w', format=tarfile.USTAR_FORMAT) as archive:
                for path in sorted(p for p in folder.rglob('*') if p.is_file()):
                    info = tarfile.TarInfo(database.stem + '/' + path.relative_to(folder).as_posix())
                    info.size, info.mode, info.mtime = path.stat().st_size, 0o644, 0
                    with path.open('rb') as stream:
                        archive.addfile(info, stream)
            verify_bundle(Path(stage))
            if any(checksum(p) != expected for p, expected in input_hashes.items()):
                raise ValueError('Input changed during export')
            os.replace(stage, output)
        finally:
            Path(stage).unlink(missing_ok=True)
    return {**report, 'bundle': checksum(output), 'output': str(output)}


def verify_bundle(path):
    """Verify all allowlisted TAR members without extracting or executing SQL."""
    with tarfile.open(path, 'r:') as archive:
        members = archive.getmembers()
        names = [m.name for m in members]
        if len(names) != len(set(names)) or not names:
            raise ValueError('Empty bundle or duplicate member names')
        root = names[0].split('/')[0] + '/'
        if any(not m.isfile() or not m.name.startswith(root) or
               '..' in m.name.split('/') or '\\' in m.name or m.name.startswith('/')
               for m in members):
            raise ValueError('Unexpected TAR member')
        manifest = archive.extractfile(root + 'MANIFEST.sha256').read().decode('ascii')
        expected = {}
        for line in manifest.splitlines():
            sha, name = line.split('  ', 1)
            if name in expected or not re.fullmatch('[0-9a-f]{64}', sha):
                raise ValueError('Invalid checksum manifest')
            expected[name] = sha
        actual_names = {m.name[len(root):] for m in members} - {'MANIFEST.sha256', 'CHECKSUMS.tsv'}
        if set(expected) != actual_names:
            raise ValueError('Manifest coverage mismatch')
        checksums = archive.extractfile(root + 'CHECKSUMS.tsv').read().decode('ascii').splitlines()
        if checksums[0] != 'path\tbytes\tcrc32\tsha256':
            raise ValueError('Invalid CRC manifest header')
        crc_records = {}
        for line in checksums[1:]:
            name, size, crc, sha = line.split('\t')
            if name in crc_records:
                raise ValueError('Duplicate CRC manifest entry')
            crc_records[name] = {'bytes': int(size), 'crc32': crc, 'sha256': sha}
        if set(crc_records) != actual_names:
            raise ValueError('CRC manifest coverage mismatch')
        for name, sha in expected.items():
            h, crc, size = hashlib.sha256(), 0, 0
            with archive.extractfile(root + name) as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    h.update(block)
                    crc = zlib.crc32(block, crc)
                    size += len(block)
            info = {'bytes': size, 'crc32': f'{crc:08x}', 'sha256': h.hexdigest()}
            if info['sha256'] != sha or info != crc_records[name]:
                raise ValueError(f'Checksum mismatch: {name}')
    return {'members_verified': len(expected), 'bundle': checksum(path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('build')
    p.add_argument('database', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--pdf', type=Path)
    p = sub.add_parser('verify')
    p.add_argument('bundle', type=Path)
    p = sub.add_parser('restore-tsv', help='Run only on a trusted, extracted bundle')
    p.add_argument('folder', type=Path)
    p.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.command == 'build':
        result = build(args.database, args.output or args.database.parent / (args.database.stem + '-preservation.tar'), args.pdf)
        print(json.dumps(result, indent=2))
    elif args.command == 'restore-tsv':
        metadata = restore_tsv(args.folder, args.output)
        print(json.dumps({'restored': str(args.output), 'format': metadata['format']}))
    else:
        print(json.dumps(verify_bundle(args.bundle), indent=2))


if __name__ == '__main__':
    main()
