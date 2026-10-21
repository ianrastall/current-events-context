# Preservation exports

The authoritative annual files stay at `YYYY/YYYY.sqlite` and
`YYYY/YYYY.md`. Preservation TARs are built offline beside that pair as
ignored release assets for distribution or independent backups. Optional print
work stays in `dist/`. The exact database is copied;
it is never vacuumed, re-journaled or rewritten by the exporter. Existing
daily archives, including January 2000, are not migrated by this tool.

The four preservation layers are structured digital data, accessible text,
printable reference, and a future selected physical digest. They serve different
purposes. SQL and TSV retain logical records; the original SQLite member retains
the precise file bytes. Markdown and PDF are reading projections. An engraved
digest would preserve only a selection, with explicit scope and provenance.

## Build and verify

Use Python 3.11+ with SQLite 3.37+, FTS5 and JSON support. No extra dependencies
or network service is required for the bundle tool.

```powershell
python tools/build_tiers.py build 2025/2025.sqlite
python tools/build_tiers.py verify 2025/2025-preservation.tar
```

The single uncompressed USTAR contains the original annual pair, `PRIMER.txt`,
the exporter, `archive.sql`, `schema.sql`, `schema.json`, `FORMAT.txt`, typed TSV
for every logical table and reading view, two checksum manifests, and
`VERIFICATION.json`. It deliberately excludes FTS shadow tables. Only internal
content FTS5 virtual tables with default runtime configuration are supported;
unsupported structures fail explicitly. Indexes are rebuilt from logical rows.
SQLite schema declarations, explicit FTS rowids, application ID and user version
are preserved. Ordinary implicit rowids and physical index layout are not an
independent archival contract.

Both SQL and TSV are restored into temporary databases before installation.
All logical tables and reading views are compared by typed row hashes and
counts. Schema, header pragmas, database integrity, foreign keys and FTS
integrity are checked. Original input hashes must remain unchanged. The TAR is
then checked against both manifests. Temporary expanded files are removed;
one annual bundle remains, with no daily output proliferation.

Building uses temporary disk space for expanded exports and two restored
databases. Hexadecimal BLOBs make SQL/TSV larger than SQLite. Generated bundles
belong in release assets or external backups, not Git. A successful build prints
the outer TAR hash separately. Hashes detect damage; they do not repair it.

Determinism is defined for identical input files and exporter/runtime versions:
UTF-8, LF, stable object/row order, fixed TAR permissions, zero timestamps and
numeric owners. SQL reconstruction requires SQLite rather than arbitrary SQL
engines. Text remains Unicode; a SQL dump is not necessarily ASCII.

## Recovery

Verify the TAR before extracting it into a fresh directory. On systems with
standard tar and SHA-256 utilities:

```sh
tar -xf 2025-preservation.tar
cd 2025
sha256sum -c MANIFEST.sha256
sqlite3 restored.sqlite < archive.sql
```

Alternatively restore the typed TSV with the included Python program:

```sh
python build_tiers.py restore-tsv . restored.sqlite
```

The output must not already exist. The TSV restore performs logical verification.
SQL/scripts in a bundle are executable instructions: restore only trusted
bundles. Checksums provide change detection, not authentication. `FORMAT.txt`
specifies the simple reversible cell encoding for alternative implementations;
empty text, NULL, BLOBs, numbers and embedded control characters remain distinct.

## Print and physical derivatives

The optional [PDF builder](../reference/yearbook/README.md) creates a complete
printable chronicle. Verify it before including it in a bundle:

```powershell
python reference/yearbook/verify.py 2025/2025.sqlite dist/2025.pdf
python tools/build_tiers.py build 2025/2025.sqlite --pdf dist/2025.pdf
```

PDFs and any future TIFF/PBM pages are release assets. TIFF Group 4 is compressed;
it must not be described as an uncompressed baseline export. Raster pages can
be useful additional derivatives but create substantial volume and do not
replace structured data. This pass does not generate them, recovery barcodes,
PAR2 parity, a C bootstrap reader, engraving layouts or machine G-code.

Those are separate optional build stages. Physical inscription needs a selected
digest and typography tested at the intended scale. Machine control requires
known equipment, units, origin, tooling and material; a generic G-code file is
not universally safe or usable. Do not claim archival lifetimes for media or
guaranteed recovery from untested printed encodings.

Technical references: [SQLite table/shadow classifications](https://www.sqlite.org/pragma.html#pragma_table_list),
[SQLite virtual tables](https://www.sqlite.org/vtab.html),
[Library of Congress uncompressed TIFF description](https://www.loc.gov/preservation/digital/formats/fdd/fdd000023.shtml),
and [bit preservation versus long-term usability](https://www.loc.gov/programs/digital-collections-management/digital-formats/bit-level-preservation-and-long-term-usability/).
