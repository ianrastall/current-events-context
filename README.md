# current-events-context

Long-term preservation of day-by-day current-events sources, with readable
chronicles and LLM context. Source extraction and researched interpretation
have separate provenance. The collection does not claim exhaustive or
guaranteed impartial news coverage.

| Path | Purpose |
|---|---|
| `<YYYY>/<YYYY>.sqlite` and `<YYYY>/<YYYY>.md` | Annual preservation database and readable chronicle |
| `<YYYY>/<YYYY>-preservation.tar` (ignored) | Optional preservation bundle, built beside the annual pair |
| `dist/` (ignored) | Working build outputs and optional print derivatives |
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

Annual assets live directly in their year folder, for example
`2025/2025.sqlite` and `2025/2025.md`. Release checksums and notes live beside
them. Existing local TAR bundles and audit/uncited JSON reports are also kept
with their year; generated bundles and working reports remain ignored by Git.
Older embedded contracts and historical handoffs refer to `archive/`; that
was the previous location. This relocation preserves edition bytes and all
embedded source paths and implementation snapshots.

| Year | SQLite | Markdown | Dates | Event assertions |
|---|---|---|---:|---:|
| 2016 | [2016.sqlite](2016/2016.sqlite) | [2016.md](2016/2016.md) | 366 | 5,233 |
| 2017 | [2017.sqlite](2017/2017.sqlite) | [2017.md](2017/2017.md) | 365 | 3,791 |
| 2018 | [2018.sqlite](2018/2018.sqlite) | [2018.md](2018/2018.md) | 365 | 4,653 |
| 2019 | [2019.sqlite](2019/2019.sqlite) | [2019.md](2019/2019.md) | 365 | 3,841 |
| 2020 | [2020.sqlite](2020/2020.sqlite) | [2020.md](2020/2020.md) | 366 | 7,393 |
| 2021 | [2021.sqlite](2021/2021.sqlite) | [2021.md](2021/2021.md) | 365 | 8,350 |
| 2022 | [2022.sqlite](2022/2022.sqlite) | [2022.md](2022/2022.md) | 365 | 5,324 |
| 2023 | [2023.sqlite](2023/2023.sqlite) | [2023.md](2023/2023.md) | 365 | 4,686 |
| 2024 | [2024.sqlite](2024/2024.sqlite) | [2024.md](2024/2024.md) | 366 | 5,305 |
| 2025 | [2025.sqlite](2025/2025.sqlite) | [2025.md](2025/2025.md) | 365 | 5,453 |

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

The 2016 edition preserves all 366 dates, 5,233 assertions and 2,862 topic labels.
Its 26 originally uncited assertions have separate evidence accounts: 11 complete
and 15 partial. Formation dates, award descriptions, debt amounts, appointment
details and local/UTC date conventions are qualified in the editorial layer;
the original source wording and placement remain unchanged. The existing
partial Afghanistan withdrawal review is retained without replacement.

The 2017 edition preserves 3,791 assertions and an empty marker before the first
category heading. Missing source category locations remain absent; no heading
is invented. Seventeen uncited assertions have separate evidence accounts:
ten complete and seven partial. Use the [current annual dispatcher](reference/schema/ANNUAL_LEGACY.md)
for all published editions, including the frozen earlier profiles.

The 2018 edition preserves 4,653 assertions and two unbulleted source fragments
as unclassified research material. Three uncited assertions have separate
evidence accounts: two complete and one partial. Original templates, depth gaps
and bare topic labels remain visible with source handling notes.

The 2019 edition preserves 3,841 assertions and a source editorial comment
without treating it as an event. Six uncited assertions have separate evidence
accounts: two complete and four partial. The early COVID-19 first-case claim
remains explicitly unverified; the Aigle Azur date and corporate-merger wording
are qualified separately from the unchanged source accounts.

The 2020 edition preserves 7,393 assertions across the leap year. The two
approved prose bullets remain assertions at their original depth, with visible
notes explaining their misleading nesting. Eight separate editorial accounts
cover uncited assertions: four complete and four partial. The broad 3DS support
claim is qualified; unsupported details remain explicit.

The 2021 edition preserves 8,350 live assertions and four explicitly labeled
commented-out entries, excluded from the event tally. Original indentation and
comment text remain available. Its one uncited live assertion has a separate
complete FIA-based editorial account. Unsupported source templates and orphan
labels remain visible with guarded handling notes.

The 2022 edition preserves 5,324 assertions, including two explicitly nested
earthquake assertions, an empty marker and two unbulleted research fragments.
Six separate editorial accounts cover uncited assertions: four complete and
two partial. The earthquake-depth discrepancy and Hans Island agreement date
are disclosed without rewriting the original source.

The 2023 edition preserves 4,686 assertions and the December 30 unbulleted
military claim as unclassified source material. Seven uncited assertions have
separate evidence accounts: two complete reviews and five partial reviews.
Use the [annual series dispatcher](reference/schema/ANNUAL_SERIES.md) for
current and earlier editions; the 2024/2025 implementations remain frozen.

Tagged [2024](https://github.com/ianrastall/current-events-context/releases/tag/archive-2024-v1)
and [2025](https://github.com/ianrastall/current-events-context/releases/tag/archive-2025-v1)
releases distribute the committed pairs with SHA-256 checksums.

```powershell
python -m seed.annual_series verify 2023/2023.sqlite
python -m seed.annual_series render 2023/2023.sqlite
```

```powershell
python -m seed.annual_editions verify 2024/2024.sqlite
python -m seed.annual_editions render 2024/2024.sqlite
```

```powershell
python -m seed.archive_release verify 2025/2025.sqlite
python -m seed.archive_release render 2025/2025.sqlite
python -m seed.yearbook queue 2025/2025.sqlite --month 2025-01 --limit 10
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

Offline replay and synthesis use `seed.annual_access` to obtain published-year
inputs from their annual databases. The frozen `seed.archive_access` remains
for historical implementation verification; the current accessor also supports
the old `archive/` layout for existing checkouts.
Planning treats those dates as present; acquisition and writers refuse to
recreate daily files. Shared cache entries still used elsewhere remain on disk.
Preservation exports are generated beside the annual pair as ignored release
assets. The offline builder produces one uncompressed annual TAR
containing the original SQLite/Markdown pair, a SQL dump, reversible typed TSV,
schema, recovery instructions, checksums and restore-verification results.
Both SQL and TSV are restored and compared before installation. No network
access or modification of the source database is required.

```powershell
python tools/build_tiers.py build 2025/2025.sqlite
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
