# SQLite-First Archive and Synthesis Storage Contract (`sqlite-archive-1.0`)

## Purpose and Governance

This document specifies the side-by-side SQLite storage architecture (`schema_version: sqlite-archive-1.0`) for `current-events-context`, together with deterministic, lossless import/export bridges for:

1. **Canonical YAML contracts**:
   - Candidate hierarchy-preserving extraction (`extraction-1.0`, validated against `reference/schema/extraction.schema.json`)
   - Legacy daily seed files (`<YYYY>/<MM>/<YYYY-MM-DD>.yaml`, preserving `gdelt` enrichment blocks)
   - Deep-researched daily synthesis files (`2.2`, validated against `reference/schema/daily-events.schema.json`)
2. **Human and LLM context views exported on demand**:
   - **reStructuredText (`.rst`)** daily and monthly rollups with explicit directive blocks (`.. topic::`, `.. list-table::`, `.. note::`), cross-event `:ref:` targets, and footnote citations (`[1]_` -> `.. [1]`)
   - **Markdown (`.md`)** daily and monthly briefings

Per `AGENTS.md` schema governance, this SQLite store operates **side by side** with the existing file-based outputs until full corpus reconciliation and workflow cutover are approved. Existing canonical files in `<YYYY>/<MM>/`, `provisional/extraction-v1/`, and `expanded/` are never silently overwritten or reinterpreted in place.

---

## Pipeline Layer Separation & Per-Day SQLite Layout (`<YYYY>/<MM>/<YYYY-MM-DD>.sqlite`)

Starting at `2000-01-01`, each day is stored as a self-contained, compact SQLite database at `<YYYY>/<MM>/<YYYY-MM-DD>.sqlite` built with `PRAGMA page_size = 1024; PRAGMA journal_mode = DELETE; VACUUM;` (typically 35–55 KB per day). Multiple daily `.sqlite` files can be rolled up on demand into a monthly (`2000/01/2000-01.sqlite`) or master (`provisional/archive.sqlite`) database with full `FTS5` indexing via `python -m seed.sqlite_archive rollup`.

The database schema enforces strict separation across the pipeline layers required by `AGENTS.md`:

| Layer | SQLite Tables | Reproducibility & Provenance Guarantees |
|---|---|---|
| **1. Source Acquisition** | `sources_wikipedia`, `raw_sources` | `sources_wikipedia` stores the primary Wikipedia portal/retrospective revision identity (`page`, `revision_id`, `revision_timestamp`, `source_mode`, `source_sha256`). `raw_sources` records all multi-source inputs (`wikipedia_retrospective_wikitext`, `wikidata_sparql_day_precision`, `usgs_comcat_geojson`, `gdelt_v1_cameo_archive`, `reliefweb_api`) with exact `sha256` and `cache_path`. |
| **2. Deterministic Extraction & Multi-Source Feeds** | `extraction_days`, `extraction_categories`, `extraction_entries`, `extraction_warnings`, `structured_feed_items` | Deterministic transform of `sources_wikipedia` (`extraction-1.0`) plus `structured_feed_items` holding machine-extracted items from Wikipedia retrospective pages, Wikidata (`P585` day-precision QIDs), USGS ComCat (`M4.5+` earthquakes), and GDELT 1.0 (`CAMEO` event clusters). |
| **3. GDELT Enrichment** | `gdelt_enrichment` | Keyed by `date`. Stores `gdelt_json` (`queried_at`, `article_count`, `articles`). Preserved independently of Wikipedia re-extraction. |
| **4. Synthesis (Schema 2.2 + 3-Tier Daily Scope)** | `synthesis_days`, `synthesis_events`, `synthesis_actors_entities`, `synthesis_key_data`, `synthesis_sources`, `synthesis_works_cited`, `synthesis_related_events` | Stores `2.2` researched day snapshots (`draft` or `reviewed`), including event `tier` (`1` = Global/Systemic `8–10`, `2` = National/Sectoral `5–7`, `3` = Archival/Digest `1–4`), a flat GUI-browsable `synthesis_actors_entities` table (`person`, `organization`, `place`, `commodity`), verbatim `quoted_material`, `citation_refs`, and `works_cited`. |

Full-text search is provided by an SQLite `FTS5` virtual table (`synthesis_events_fts`) indexing `date`, `event_id`, `category`, `subcategory`, `headline`, `summary`, `topics_text`, `actors_text`, and `places_text`.

---

## Ordering, Null Semantics, and Legacy Provenance

1. **Ordering**:
   - Every sequence table includes an explicit `ord INTEGER NOT NULL` column (0-indexed) and a composite primary key or unique constraint including `ord`.
   - Exporting back to YAML or `.rst` always orders by `ord ASC`, guaranteeing deterministic sequence ordering.
2. **Null Semantics**:
   - Nullable integers (`casualty_report.killed`, `injured`, `displaced`, `missing`, `arrest_count`, `wikipedia_revision_id`) are stored as SQL `NULL` and round-trip to YAML `null` (never coerced to `0` or `""`).
   - Empty strings (`""`) vs `NULL` (`null` in YAML) are preserved distinctly (`sources.wikipedia_portal.text_fragment` is `NULL` when `included = 0`; `notes` is `""` when empty).
3. **Legacy Monthly Fallback Provenance**:
   - Legacy rendered monthly HTML inputs use `source_mode = 'rendered_html'` and `revision_id IS NULL`. The SQLite store records `page`, `source_mode`, `source_sha256`, and the `RENDERED_SOURCE` warning without conflating HTML fallback inputs with revision-pinned raw wikitext.
4. **Lossless Round-Trip Verification**:
   - For both `extraction-1.0` and `synthesis-2.2`, `export_synthesis_doc(conn, date)` and `export_extraction_doc(conn, date)` reconstruct the exact dictionary structure and pass `reference/schema/validate.py`, `seed.replay.extraction_validator()`, `seed.replay.dump()`, and `build.dump()` byte-identically.
