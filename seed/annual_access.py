"""Read-only annual access for the year-folder layout.

archive_access remains frozen for published implementation verification.
Legacy archive/ paths are supported for older checkouts and temporary fixtures.
"""
from pathlib import Path
import datetime as dt
import sqlite3
import json
import hashlib

ROOT = Path(__file__).resolve().parents[1]


def publication(conn):
    """Read either published preservation contract without changing frozen access."""
    rows = conn.execute("SELECT b.payload,b.sha256 FROM archive_inputs i JOIN archive_blobs b USING(sha256) WHERE i.role='preservation_publication'").fetchall()
    if not rows:
        return None
    if len(rows) != 1 or hashlib.sha256(rows[0][0]).hexdigest() != rows[0][1]:
        raise ValueError('Invalid annual publication identity')
    record = json.loads(rows[0][0])
    if record['contract'] not in ('preservation-release-1.0', 'preservation-release-1.1') or record['edition'] != 'source-preservation':
        raise ValueError('Unsupported annual publication contract')
    if record['contract'] == 'preservation-release-1.1' and (
            record.get('uncited_claim_policy') != 'unverified-source-claim-1.0'
            or record.get('publication_toolchain') != 'annual-series-1.3'):
        raise ValueError('Unsupported unverified claim policy')
    return record


def annual_paths(root=None):
    """Discover annual editions, preferring year folders over legacy locations."""
    root = Path(root or ROOT)
    paths = {p.stem: p for p in sorted((root / "archive").glob("[0-9][0-9][0-9][0-9].sqlite"))}
    for folder in sorted(root.glob("[0-9][0-9][0-9][0-9]")):
        path = folder / (folder.name + ".sqlite")
        if path.is_file():
            paths[folder.name] = path
    return [paths[year] for year in sorted(paths)]


def published_path(day, root=None):
    day = str(dt.date.fromisoformat(str(day)))
    base = Path(root or ROOT)
    path = base / day[:4] / f'{day[:4]}.sqlite'
    if not path.exists():
        path = base / 'archive' / f'{day[:4]}.sqlite'
    if not path.exists():
        return None
    conn = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        record = publication(conn)
        if record is None:
            return None
        if record['year'] != int(day[:4]) or not conn.execute('SELECT 1 FROM day_ingestions WHERE date=?', (day,)).fetchone():
            raise ValueError("Incomplete published annual calendar")
        return path
    finally:
        conn.close()


def wikipedia(day, root=None):
    path = published_path(day, root)
    if path is None:
        raise FileNotFoundError(f'No published annual source for {day}')
    from seed import annual_archive as annual
    conn = annual.connect(path, readonly=True)
    try:
        row = conn.execute('SELECT source_metadata_json,source_path FROM day_ingestions WHERE date=?', (str(day),)).fetchone()
        meta, payload = json.loads(row[0]), annual.input_bytes(conn, row[1])
        if annual.digest(payload) != meta['source_sha256']:
            raise ValueError('Annual source payload hash mismatch')
        return meta, payload
    finally:
        conn.close()


def legacy_bytes(day, root=None):
    path = published_path(day, root)
    if path is None:
        raise FileNotFoundError(f'No published annual seed for {day}')
    from seed import annual_archive as annual
    conn = annual.connect(path, readonly=True)
    try:
        row = conn.execute('SELECT legacy_path FROM day_ingestions WHERE date=?', (str(day),)).fetchone()
        return annual.input_bytes(conn, row[0])
    finally:
        conn.close()


def extraction(day, root=None):
    path = published_path(day, root)
    if path is None:
        raise FileNotFoundError(f'No published annual extraction for {day}')
    from seed import annual_archive as annual, sqlite_archive
    conn = annual.connect(path, readonly=True)
    try:
        return sqlite_archive.export_extraction_doc(conn, str(day))
    finally:
        conn.close()


def revision(revision_id, root=None):
    for path in annual_paths(root):
        conn = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
        try:
            if publication(conn) is None:
                continue
            row = conn.execute('SELECT date FROM sources_wikipedia WHERE revision_id=?', (revision_id,)).fetchone()
            if row is not None:
                return wikipedia(row[0], root)
        finally:
            conn.close()
    raise FileNotFoundError(f'Revision {revision_id} is not in a published annual archive')
