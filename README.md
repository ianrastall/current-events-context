# current-events-context

Long-term preservation of day-by-day current-events sources, with readable
chronicles and LLM context. Source extraction and researched interpretation
have separate provenance. The collection does not claim exhaustive or
guaranteed impartial news coverage.

| Path | Purpose |
|---|---|
| `archive/<YYYY>.sqlite` and `archive/<YYYY>.md` | Annual preservation database and readable chronicle |
| `dist/` (ignored) | Reproducible preservation bundles and optional print derivatives |
| `<YYYY>/<MM>/<YYYY-MM-DD>.yaml` | Unmigrated daily seeds; some files retain the legacy shape |
| `expanded/<YYYY>/<MM>/<YYYY-MM-DD>.yaml` | Schema-2.2 researched synthesis |
| `reference/deep-research/` | Source research reports |
| `reference/expansion/inputs.json` | Explicit report/snapshot identities |
| `reference/schema/` | Synthesis contract, authoring guide and validator |
| `reference/sources/wikipedia/` | Exact immutable source payloads and provenance |
| `provisional/extraction-v1/` | Separate, locally regenerated extraction candidates |
| `seed/` | Collection CLI and archival migration tools |

The repository is transitioning from published mixed daily paths to separate
layers. See `reference/reconciliation/README.md` before publication. Imported
review states preserve prior work; draft research still needs factual review.

## Annual preservation editions

Each published year has a self-contained database and readable companion:

| Year | SQLite | Markdown | Dates | Event assertions |
|---|---|---|---:|---:|
| 2024 | [2024.sqlite](archive/2024.sqlite) | [2024.md](archive/2024.md) | 366 | 5,305 |
| 2025 | [2025.sqlite](archive/2025.sqlite) | [2025.md](archive/2025.md) | 365 | 5,453 |

These editions replace their old daily YAML files and dedicated cached-source copies.
The originals, metadata and prior local extraction candidates remain embedded
as exact bytes inside the database, with hashes, a retirement manifest and
a Git checkpoint. Other years retain their existing formats until migrated.

The 2025 edition preserves 365 dates, 5,453 event assertions and 10,096 structural
entries. Exact pinned Wikipedia inputs, category/topic hierarchy, original
text, links, citations, source errors and existing GDELT content are retained.
No collection refetch was performed for cutover. An empty marker and five
unclassified fragments from one malformed May 6 passage remain explicit evidence.

Publication verifies lossless transfer, source identity, reproducible extraction,
attribution and disclosed uncertainties. Independent checking of every event
is optional further research, not a publication prerequisite. Source statements
are not certified complete, impartial or correct. The active
[preservation publication contract](reference/schema/PRESERVATION_RELEASE.md)
supersedes the exhaustive-check gates in historical embedded draft contracts.

The Markdown contains the whole year's events, month/day navigation, topic
context, original citations and pinned revisions. Eight cited editorial accounts
supply separate evidence for the seven originally uncited entries and correct
documented discrepancies. Seventeen earlier scoped findings and access limits
are disclosed too. Five full-event reviews are complete and three remain partial;
the rest are not represented as checked. Source text remains unchanged.
This is an archival reference edition, with further historical interpretation
and further researched yearbook interpretation possible as later work.

The 2024 edition preserves 9,868 structural entries. Six separately cited
editorial accounts cover its originally uncited entries: four full-event
reviews are complete and two remain partial. Original reporting limits remain
visible. The two approved orphan topic labels are retained with warnings in
both formats. Four source-depth gaps and malformed markup retain the exact
source form; an explicit category heading followed by a comment is recognized.
See [successor annual profiles](reference/schema/ANNUAL_EDITIONS.md) for the
pinned 2024 interpretation and year-appropriate renderer. The frozen 2025
implementation and annual file bytes remain unchanged.

```powershell
python -m seed.annual_editions verify archive/2024.sqlite
python -m seed.annual_editions render archive/2024.sqlite
```

```powershell
python -m seed.archive_release verify archive/2025.sqlite
python -m seed.archive_release render archive/2025.sqlite
python -m seed.yearbook queue archive/2025.sqlite --month 2025-01 --limit 10
```

Verification reparses embedded inputs offline, checks structural coverage and
hashes, validates editorial guards and checks the retirement manifest. Rendering
is deterministic UTF-8 Markdown and records the exact database SHA-256. Close
database writers before rendering. The older annual builder is for unmigrated
candidates; it refuses to overwrite research. Editorial changes require an
explicit successor edition. No permanent daily export or review files are needed.

Read the Markdown without SQLite software, or download it for a text editor.
In an SQLite reader, start with `event_overview`, `event_citations`, `event_links`,
`source_text`, `unclassified_source` and `factual_review_queue`. The publication
manifest is in `source_text`, role `preservation_publication`. Always use
`ORDER BY` for ordered SQL output. For example:

```sql
SELECT date, category, text FROM archive_events_fts
WHERE archive_events_fts MATCH 'earthquake' ORDER BY date;
```

Offline replay and synthesis obtain published-year inputs from their annual databases.
Planning treats those dates as present; acquisition and writers refuse to
recreate daily files. Shared cache entries still used elsewhere remain on disk.
Preservation exports are generated as release assets rather than multiplying
canonical files. The offline builder produces one uncompressed annual TAR
containing the original SQLite/Markdown pair, a SQL dump, reversible typed TSV,
schema, recovery instructions, checksums and restore-verification results.
Both SQL and TSV are restored and compared before installation. No network
access or modification of the source database is required.

```powershell
python tools/build_tiers.py build archive/2025.sqlite
```

Read [the plain-text primer](PRIMER.txt) and [preservation build instructions](tools/PRESERVATION.md).
An optional [print builder](reference/yearbook/README.md) produces a complete
reference chronicle with charts, citations and a subject index. Generated PDFs,
page images and recovery parity belong in release assets under ignored `dist/`.
Physical inscription remains a separate digest and equipment-specific production
task; it must not be mistaken for a complete copy of the archive.

## Setup and verification

Requires Python 3.10 or later and Git for optional Git workflows.

```
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python reference/schema/validate.py --archive-root expanded expanded/2026/01/2026-01-15.yaml
```

## Collection

```
python -m seed plan 2026-01-01 2026-01-31
python -m seed date 2026-10-04 --no-overwrite
python -m seed range 2026-01-01 2026-01-31 --no-gdelt
```

`date` overwrites by default; `range` skips existing dates by default. These
commands acquire network data and are not parser-replay commands. GDELT is
optional live enrichment. Never use a full refetch to repair historical
extraction or add `--commit`/`--push` to provisional runs.

## Offline source replay

```
python -m seed cache 2026-01-01 2026-01-31
python -m seed reparse 2026-01-01 2026-01-31 --output-root provisional/extraction-v1
```

`cache` acquires the oldids already recorded in seeds. For legacy daily files
without an oldid, `cache --capture-unpinned` explicitly records current revisions
as new inputs without changing their daily files; it cannot recover their
original capture. `--skip-unpinned` instead leaves them out. These policies are
mutually exclusive. `reparse` never acquires network data and fails on missing
inputs by default. `--cached-only` explicitly
permits a partial run with every skipped date recorded in `report.json`.
Candidates retain hierarchy, raw fragments, links, citations and warnings.
See `reference/schema/EXTRACTION_MIGRATION.md` for the public replacement gate.
New network captures also save their raw input and a structured artifact under
`provisional/captures/`; optional Git workflows include the capture's inputs.

## Research and synthesis

Start a research run with `llm_prompt.txt` and the exact daily date. Save the
report under `reference/deep-research/<YYYY>/<MM>/`, then register it:

```
python reference/expansion/inputs.py 2026-01-16 --report reference/deep-research/2026/01/2026-01-16a.md
python generate_prompts.py 2026-01-16
```

Follow `reference/schema/AUTHORING_GUIDE.md`. Write synthesis under
`expanded/`; never replace a seed with model prose. Corrections belong in
durable guarded overlays, followed by regeneration and validation. Check
original publishers for dates, facts, quotations and source disagreements.
Size does not determine whether a file is complete or reviewed.

Unchanged January 2-3 and 5-7 preserve published reviewed status. January 1,
4, 8-9 and 10-15 are draft after import or guarded corrections.
January 16-31 await research. A monthly summary should be generated only
from completed daily inputs, with related developments deduplicated.

The archive is offered under the repository's license; cached Wikipedia
source material retains its CC BY-SA attribution obligations.
