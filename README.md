# current-events-context

Daily current-events context for LLMs. Source extraction and researched
synthesis have separate provenance and are stored separately.

| Path | Purpose |
|---|---|
| `<YYYY>/<MM>/<YYYY-MM-DD>.yaml` | Wikipedia seed archive; some later files still use the legacy shape |
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

## Annual SQLite reference archive

The destination for the next migration is one self-contained database per
year: `archive/<YYYY>.sqlite`. The first candidate is 2025. Its contract and
data dictionary are in `reference/schema/ANNUAL_ARCHIVE.md`.

```
python -m seed.annual_archive build 2025
python -m seed.annual_archive verify archive/2025.sqlite
python -m seed.annual_archive ingest-day archive/2025.sqlite 2025-01-01
```

These commands are offline. Each date is ingested transactionally; the annual
build replaces its destination only after verification succeeds. The database
embeds exact legacy seed bytes, raw pinned Wikipedia inputs and metadata,
schema/code evidence, structured extraction and a migration report. It can be
verified from embedded source inputs without reopening the daily source tree.
No permanent daily exports are produced. Changed inputs require an explicit
migration; existing research is protected against a source-only rebuild.

Open `day_coverage`, `event_overview`, `event_citations`, `event_links`,
`source_text` and `review_queue` in an SQLite reader. Always specify `ORDER BY`
for ordered output. Search source events with, for example:

```sql
SELECT date, category, text FROM archive_events_fts
WHERE archive_events_fts MATCH 'earthquake' ORDER BY date;
```

The 2025 material currently has no complete researched synthesis. Successful migration
verification does not make it fact-checked or ready for a finished yearbook. The
database retains warnings and reports deletion blockers in `archive_checks`.
Existing daily files and shared source caches remain intact until the
documented replacement gate passes. Yearbook sections and researched claims
have separate tables. A [readable Markdown preview](archive/2025.md) accompanies
the [SQLite candidate](archive/2025.sqlite); illustrated PDF production is deferred.
The chosen yearly pair is `<YYYY>.sqlite` plus `<YYYY>.md`.

The current 2025 container is `annual-archive-1.1`. Its original extraction
queue has been reconciled through tested source rules and seven guarded
interpretations; no unresolved extraction warnings or unknown heading roles
remain. Resolved notices are retained. The May 6 pasted football passage
remains in `unclassified_source`, with separate publisher research evidence.
Existing synthesis callers keep their historical interpretation profile.

`factual_reviews`, `review_evidence` and `factual_review_queue` contain an
initial 17 scoped review records across all twelve months, including three
contradicted claims. They do not approve whole events, days or the year.
`archive_checks` also contains a complete-calendar coverage census and the
comparison against the previous annual container. Seven nonempty source event
entries have no attached citation. A literal empty bullet is retained as a
known source marker with the existing `unknown` structural role, excluded from
the 5,453 event/search entries. Five unclassified fragments belong to the one May 6 passage;
they do not represent five omitted events. The annual file remains a candidate
and is not ready for a finished yearbook or deletion of the old corpus.

The Markdown preview contains all 5,453 original source assertions, with
month/day navigation, topic context, pinned Wikipedia revisions and citations.
Eight separately researched editorial accounts supply evidence for all seven
originally uncited entries and corrections for the three documented factual
discrepancies. The original source still has seven uncited entries: editorial
evidence never overwrites extraction. Five full-event reviews are complete;
three remain partial, and 5,445 entries have no full-event review. Every event
requires independent checking before cutover. These counts are separate from
the 17 earlier scoped findings, which cannot approve whole events.

The remaining partial findings concern the worldwide scope of Titanic
commemorations, the full extent of Kathmandu's curfew, and the original
French prime minister's "sworn in" wording. Supported narrower accounts are
shown alongside the original wording. A corrected editorial account is not
proof that all remaining source assertions have been established.

Review work is incremental and stays inside the annual database; no permanent
per-day review files are added. See the [Markdown/review contract](reference/schema/YEARBOOK.md).

```powershell
python -m seed.yearbook queue archive/2025.sqlite --month 2025-01 --limit 10
python -m seed.yearbook verify archive/2025.sqlite
python -m seed.yearbook render archive/2025.sqlite
```

Rendering is offline and deterministic, records the exact database SHA-256,
and labels every unreviewed or partial event. Close database writers before
rendering. Source and embedded pipeline bytes are preserved through Git;
`.gitattributes` prevents platform newline conversion from breaking replay.

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
