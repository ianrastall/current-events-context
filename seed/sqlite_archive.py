"""SQLite-first storage and lossless multi-format export (`sqlite-archive-1.0`).

Stores all four pipeline layers with explicit provenance and ordering:
1. Source acquisition metadata (`sources_wikipedia`)
2. Hierarchy-preserving Wikipedia extraction (`extraction_*`, schema `extraction-1.0`)
3. GDELT news enrichment (`gdelt_enrichment`)
4. Deep-research synthesis (`synthesis_*`, schema `2.2`, plus `synthesis_events_fts` FTS5 index)

Provides lossless bi-directional import/export to canonical YAML and on-demand
export to reStructuredText (`.rst`) and Markdown (`.md`) daily and monthly views.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

import yaml

SCHEMA_VERSION = "sqlite-archive-1.0"

DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS archive_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources_wikipedia (
    date TEXT PRIMARY KEY,
    page TEXT NOT NULL,
    revision_id INTEGER,
    revision_timestamp TEXT,
    source_mode TEXT NOT NULL,
    source_sha256 TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS extraction_days (
    date TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    FOREIGN KEY (date) REFERENCES sources_wikipedia(date) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS extraction_categories (
    date TEXT NOT NULL,
    ord INTEGER NOT NULL,
    name TEXT,
    links_json TEXT NOT NULL,
    citations_json TEXT NOT NULL,
    line INTEGER,
    raw TEXT,
    PRIMARY KEY (date, ord),
    FOREIGN KEY (date) REFERENCES extraction_days(date) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS extraction_entries (
    date TEXT NOT NULL,
    category_ord INTEGER NOT NULL,
    ord INTEGER NOT NULL,
    role TEXT NOT NULL,
    depth INTEGER NOT NULL,
    list_marker TEXT,
    source_path_json TEXT NOT NULL,
    parent_path_json TEXT,
    line INTEGER NOT NULL,
    raw TEXT NOT NULL,
    text TEXT NOT NULL,
    links_json TEXT NOT NULL,
    citations_json TEXT NOT NULL,
    PRIMARY KEY (date, category_ord, ord),
    FOREIGN KEY (date, category_ord) REFERENCES extraction_categories(date, ord) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS extraction_warnings (
    date TEXT NOT NULL,
    ord INTEGER NOT NULL,
    warning_json TEXT NOT NULL,
    PRIMARY KEY (date, ord),
    FOREIGN KEY (date) REFERENCES extraction_days(date) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS gdelt_enrichment (
    date TEXT PRIMARY KEY,
    gdelt_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_sources (
    date TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    title_or_query TEXT NOT NULL,
    uri TEXT NOT NULL,
    revision_id INTEGER,
    source_timestamp TEXT,
    fetched_at TEXT,
    sha256 TEXT NOT NULL,
    cache_path TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    PRIMARY KEY (date, source_id)
);

CREATE TABLE IF NOT EXISTS structured_feed_items (
    date TEXT NOT NULL,
    item_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    feed_type TEXT NOT NULL,
    ord INTEGER NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    actors_text TEXT NOT NULL,
    location_text TEXT NOT NULL,
    metric_value TEXT NOT NULL,
    url TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    PRIMARY KEY (date, item_id),
    FOREIGN KEY (date, source_id) REFERENCES raw_sources(date, source_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS synthesis_days (
    date TEXT PRIMARY KEY,
    portal TEXT NOT NULL,
    language TEXT NOT NULL,
    wikipedia_revision_id INTEGER,
    schema_version TEXT NOT NULL,
    compiler_mode TEXT NOT NULL,
    compiler_status TEXT NOT NULL,
    compiler_reviewed INTEGER NOT NULL,
    seed_source TEXT NOT NULL,
    enrichment_sources_expected INTEGER NOT NULL,
    editorial_policy_json TEXT NOT NULL,
    analytical_overview TEXT NOT NULL,
    strategic_conclusion TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS synthesis_events (
    date TEXT NOT NULL,
    ord INTEGER NOT NULL,
    event_id TEXT PRIMARY KEY,
    tier INTEGER NOT NULL DEFAULT 2,
    category TEXT NOT NULL,
    subcategory TEXT NOT NULL,
    topics_json TEXT NOT NULL,
    importance INTEGER NOT NULL,
    headline TEXT NOT NULL,
    summary TEXT NOT NULL,
    what_happened_json TEXT NOT NULL,
    why_it_matters_json TEXT NOT NULL,
    uncertainty_notes_json TEXT NOT NULL,
    actors_json TEXT NOT NULL,
    entities_json TEXT NOT NULL,
    geography_json TEXT NOT NULL,
    time_json TEXT NOT NULL,
    casualty_report_json TEXT NOT NULL,
    classification_json TEXT NOT NULL,
    portal_source_json TEXT NOT NULL,
    provenance_json TEXT NOT NULL,
    confidence_json TEXT NOT NULL,
    notes TEXT NOT NULL,
    FOREIGN KEY (date) REFERENCES synthesis_days(date) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS synthesis_actors_entities (
    event_id TEXT NOT NULL,
    ord INTEGER NOT NULL,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    country TEXT NOT NULL,
    PRIMARY KEY (event_id, ord),
    FOREIGN KEY (event_id) REFERENCES synthesis_events(event_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS synthesis_key_data (
    event_id TEXT NOT NULL,
    ord INTEGER NOT NULL,
    label TEXT NOT NULL,
    value TEXT NOT NULL,
    citation_refs_json TEXT NOT NULL,
    PRIMARY KEY (event_id, ord),
    FOREIGN KEY (event_id) REFERENCES synthesis_events(event_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS synthesis_sources (
    event_id TEXT NOT NULL,
    ord INTEGER NOT NULL,
    source_id TEXT NOT NULL,
    outlet TEXT NOT NULL,
    url TEXT NOT NULL,
    publication_date TEXT NOT NULL,
    source_type TEXT NOT NULL,
    reliability_tier TEXT NOT NULL,
    supports_json TEXT NOT NULL,
    contradicts_json TEXT NOT NULL,
    quoted_material_json TEXT NOT NULL,
    citation_refs_json TEXT NOT NULL,
    PRIMARY KEY (event_id, ord),
    FOREIGN KEY (event_id) REFERENCES synthesis_events(event_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS synthesis_related_events (
    event_id TEXT NOT NULL,
    ord INTEGER NOT NULL,
    related_event_id TEXT NOT NULL,
    PRIMARY KEY (event_id, ord),
    FOREIGN KEY (event_id) REFERENCES synthesis_events(event_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS synthesis_works_cited (
    date TEXT NOT NULL,
    ord INTEGER NOT NULL,
    work_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    outlet TEXT NOT NULL,
    url TEXT NOT NULL,
    accessed TEXT NOT NULL,
    PRIMARY KEY (date, ord),
    UNIQUE (date, work_id),
    FOREIGN KEY (date) REFERENCES synthesis_days(date) ON DELETE CASCADE
);
"""

FTS_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS synthesis_events_fts USING fts5(
    date UNINDEXED,
    event_id UNINDEXED,
    category,
    subcategory,
    headline,
    summary,
    topics_text,
    actors_text,
    places_text
);
"""


def _has_fts(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'synthesis_events_fts'"
    ).fetchone()
    return row is not None


def connect(db_path: str | Path = ":memory:", *, compact: bool = False) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    if compact:
        conn.execute("PRAGMA page_size = 1024;")
        conn.execute("PRAGMA journal_mode = DELETE;")
    conn.executescript(DDL)
    if not compact:
        conn.executescript(FTS_DDL)
    conn.execute(
        "INSERT OR REPLACE INTO archive_metadata(key, value) VALUES ('schema_version', ?)",
        (SCHEMA_VERSION,),
    )
    conn.commit()
    return conn


def _jdump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=False)


# ---------------------------------------------------------------------------
# Extraction (extraction-1.0) + GDELT import / export
# ---------------------------------------------------------------------------

def import_extraction_doc(conn: sqlite3.Connection, doc: dict[str, Any]) -> None:
    date = doc["date"]
    src = doc["source_page"]
    with conn:
        conn.execute("DELETE FROM sources_wikipedia WHERE date = ?", (date,))
        conn.execute("DELETE FROM gdelt_enrichment WHERE date = ?", (date,))
        conn.execute(
            """
            INSERT INTO sources_wikipedia(
                date, page, revision_id, revision_timestamp, source_mode, source_sha256
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                date,
                src["page"],
                src.get("revision_id"),
                src.get("revision_timestamp"),
                src["source_mode"],
                src["source_sha256"],
            ),
        )
        conn.execute(
            "INSERT INTO extraction_days(date, schema_version) VALUES (?, ?)",
            (date, doc["schema_version"]),
        )
        for cat_ord, cat in enumerate(doc["categories"]):
            conn.execute(
                """
                INSERT INTO extraction_categories(date, ord, name, links_json, citations_json, line, raw)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    date,
                    cat_ord,
                    cat.get("name"),
                    _jdump(cat["links"]),
                    _jdump(cat["citations"]),
                    cat.get("line"),
                    cat.get("raw"),
                ),
            )
            for entry_ord, entry in enumerate(cat["entries"]):
                conn.execute(
                    """
                    INSERT INTO extraction_entries(
                        date, category_ord, ord, role, depth, list_marker,
                        source_path_json, parent_path_json, line, raw, text,
                        links_json, citations_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        date,
                        cat_ord,
                        entry_ord,
                        entry["role"],
                        entry["depth"],
                        entry.get("list_marker"),
                        _jdump(entry["source_path"]),
                        _jdump(entry["parent_path"]) if entry.get("parent_path") is not None else None,
                        entry["line"],
                        entry["raw"],
                        entry["text"],
                        _jdump(entry["links"]),
                        _jdump(entry["citations"]),
                    ),
                )
        for w_ord, warn in enumerate(doc.get("warnings") or []):
            conn.execute(
                "INSERT INTO extraction_warnings(date, ord, warning_json) VALUES (?, ?, ?)",
                (date, w_ord, _jdump(warn)),
            )
        if "gdelt" in doc and doc["gdelt"] is not None:
            conn.execute(
                "INSERT OR REPLACE INTO gdelt_enrichment(date, gdelt_json) VALUES (?, ?)",
                (date, _jdump(doc["gdelt"])),
            )


def export_extraction_doc(conn: sqlite3.Connection, date: str) -> dict[str, Any]:
    src_row = conn.execute("SELECT * FROM sources_wikipedia WHERE date = ?", (date,)).fetchone()
    day_row = conn.execute("SELECT * FROM extraction_days WHERE date = ?", (date,)).fetchone()
    if not src_row or not day_row:
        raise KeyError(f"No extraction record for {date}")

    src_dict: dict[str, Any] = {
        "page": src_row["page"],
        "revision_id": src_row["revision_id"],
        "revision_timestamp": src_row["revision_timestamp"],
        "source_mode": src_row["source_mode"],
        "source_sha256": src_row["source_sha256"],
    }

    cat_rows = conn.execute(
        "SELECT * FROM extraction_categories WHERE date = ? ORDER BY ord ASC",
        (date,),
    ).fetchall()
    categories = []
    for cat_row in cat_rows:
        entry_rows = conn.execute(
            "SELECT * FROM extraction_entries WHERE date = ? AND category_ord = ? ORDER BY ord ASC",
            (date, cat_row["ord"]),
        ).fetchall()
        entries = []
        for er in entry_rows:
            entry_dict: dict[str, Any] = {
                "role": er["role"],
                "depth": er["depth"],
            }
            if er["list_marker"] is not None:
                entry_dict["list_marker"] = er["list_marker"]
            entry_dict.update(
                {
                    "source_path": json.loads(er["source_path_json"]),
                    "parent_path": json.loads(er["parent_path_json"]) if er["parent_path_json"] is not None else None,
                    "line": er["line"],
                    "raw": er["raw"],
                    "text": er["text"],
                    "links": json.loads(er["links_json"]),
                    "citations": json.loads(er["citations_json"]),
                }
            )
            entries.append(entry_dict)
        cat_dict: dict[str, Any] = {
            "name": cat_row["name"],
            "links": json.loads(cat_row["links_json"]),
            "citations": json.loads(cat_row["citations_json"]),
            "entries": entries,
        }
        if cat_row["line"] is not None:
            cat_dict["line"] = cat_row["line"]
        if cat_row["raw"] is not None:
            cat_dict["raw"] = cat_row["raw"]
        categories.append(cat_dict)

    warnings = [
        json.loads(r["warning_json"])
        for r in conn.execute("SELECT warning_json FROM extraction_warnings WHERE date = ? ORDER BY ord ASC", (date,))
    ]
    doc: dict[str, Any] = {
        "schema_version": day_row["schema_version"],
        "date": date,
        "source_page": src_dict,
        "categories": categories,
        "warnings": warnings,
    }
    gdelt_row = conn.execute("SELECT gdelt_json FROM gdelt_enrichment WHERE date = ?", (date,)).fetchone()
    if gdelt_row:
        doc["gdelt"] = json.loads(gdelt_row["gdelt_json"])
    return doc


# ---------------------------------------------------------------------------
# Synthesis (schema 2.2) import / export
# ---------------------------------------------------------------------------

def _importance_to_tier(importance: int) -> int:
    if importance >= 8:
        return 1
    if importance >= 5:
        return 2
    return 3


def import_multisource_feeds(
    conn: sqlite3.Connection,
    date: str,
    raw_sources: list[dict[str, Any]],
    feed_items: list[dict[str, Any]],
) -> None:
    with conn:
        conn.execute("DELETE FROM structured_feed_items WHERE date = ?", (date,))
        conn.execute("DELETE FROM raw_sources WHERE date = ?", (date,))
        for src in raw_sources:
            conn.execute(
                """
                INSERT INTO raw_sources(
                    date, source_id, source_type, title_or_query, uri,
                    revision_id, source_timestamp, fetched_at, sha256,
                    cache_path, summary_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    date,
                    src["source_id"],
                    src["source_type"],
                    src["title_or_query"],
                    src["uri"],
                    src.get("revision_id"),
                    src.get("source_timestamp"),
                    src.get("fetched_at"),
                    src["sha256"],
                    src["cache_path"],
                    src["summary_json"],
                ),
            )
        for item in feed_items:
            conn.execute(
                """
                INSERT INTO structured_feed_items(
                    date, item_id, source_id, feed_type, ord, title,
                    category, actors_text, location_text, metric_value,
                    url, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    date,
                    item["item_id"],
                    item["source_id"],
                    item["feed_type"],
                    item["ord"],
                    item["title"],
                    item["category"],
                    item["actors_text"],
                    item["location_text"],
                    item["metric_value"],
                    item["url"],
                    item["raw_json"],
                ),
            )


def import_synthesis_doc(conn: sqlite3.Connection, doc: dict[str, Any]) -> None:
    date = doc["date"]
    sp = doc["source_page"]
    ds = doc["dataset"]
    comp = ds["compiler"]
    scope = ds["scope"]
    has_fts = _has_fts(conn)
    with conn:
        if has_fts:
            conn.execute("DELETE FROM synthesis_events_fts WHERE date = ?", (date,))
        conn.execute("DELETE FROM synthesis_days WHERE date = ?", (date,))
        conn.execute(
            """
            INSERT INTO synthesis_days(
                date, portal, language, wikipedia_revision_id, schema_version,
                compiler_mode, compiler_status, compiler_reviewed,
                seed_source, enrichment_sources_expected, editorial_policy_json,
                analytical_overview, strategic_conclusion
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                date,
                sp["portal"],
                sp["language"],
                sp.get("wikipedia_revision_id"),
                ds["schema_version"],
                comp["mode"],
                comp["status"],
                1 if comp["reviewed"] else 0,
                scope["seed_source"],
                1 if scope["enrichment_sources_expected"] else 0,
                _jdump(doc["editorial_policy"]),
                doc["analytical_overview"],
                doc["strategic_conclusion"],
            ),
        )
        for ev_ord, ev in enumerate(doc["events"]):
            eid = ev["id"]
            det = ev["details"]
            wp = ev["sources"]["wikipedia_portal"]
            tier = _importance_to_tier(ev["importance"])
            conn.execute(
                """
                INSERT INTO synthesis_events(
                    date, ord, event_id, tier, category, subcategory, topics_json,
                    importance, headline, summary, what_happened_json,
                    why_it_matters_json, uncertainty_notes_json, actors_json,
                    entities_json, geography_json, time_json, casualty_report_json,
                    classification_json, portal_source_json, provenance_json,
                    confidence_json, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    date,
                    ev_ord,
                    eid,
                    tier,
                    ev["category"],
                    ev["subcategory"],
                    _jdump(ev["topics"]),
                    ev["importance"],
                    ev["headline"],
                    ev["summary"],
                    _jdump(det["what_happened"]),
                    _jdump(det["why_it_matters"]),
                    _jdump(det["uncertainty_notes"]),
                    _jdump(ev["actors"]),
                    _jdump(ev["entities"]),
                    _jdump(ev["geography"]),
                    _jdump(ev["time"]),
                    _jdump(ev["casualty_report"]),
                    _jdump(ev["classification"]),
                    _jdump(wp),
                    _jdump(ev["provenance"]),
                    _jdump(ev["confidence"]),
                    ev["notes"],
                ),
            )
            ae_ord = 0
            ent = ev.get("entities") or {}
            for p in ent.get("people") or []:
                conn.execute(
                    "INSERT INTO synthesis_actors_entities(event_id, ord, kind, name, role, country) VALUES (?, ?, 'person', ?, ?, '')",
                    (eid, ae_ord, p["name"], p.get("role") or ""),
                )
                ae_ord += 1
            for o in ent.get("organizations") or []:
                conn.execute(
                    "INSERT INTO synthesis_actors_entities(event_id, ord, kind, name, role, country) VALUES (?, ?, 'organization', ?, ?, '')",
                    (eid, ae_ord, o["name"], o.get("description") or o.get("role") or ""),
                )
                ae_ord += 1
            for st in ent.get("states") or []:
                conn.execute(
                    "INSERT INTO synthesis_actors_entities(event_id, ord, kind, name, role, country) VALUES (?, ?, 'state', ?, 'State actor', ?)",
                    (eid, ae_ord, st, st),
                )
                ae_ord += 1
            for kd_ord, kd in enumerate(ev.get("key_data") or []):
                conn.execute(
                    """
                    INSERT INTO synthesis_key_data(event_id, ord, label, value, citation_refs_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (eid, kd_ord, kd["label"], kd["value"], _jdump(kd["citation_refs"])),
                )
            for s_ord, src in enumerate(ev["sources"].get("external") or []):
                conn.execute(
                    """
                    INSERT INTO synthesis_sources(
                        event_id, ord, source_id, outlet, url, publication_date,
                        source_type, reliability_tier, supports_json, contradicts_json,
                        quoted_material_json, citation_refs_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        eid,
                        s_ord,
                        src["id"],
                        src["outlet"],
                        src["url"],
                        src["publication_date"],
                        src["source_type"],
                        src["reliability_tier"],
                        _jdump(src["supports"]),
                        _jdump(src["contradicts"]),
                        _jdump(src["quoted_material"]),
                        _jdump(src["citation_refs"]),
                    ),
                )
            for r_ord, rel_id in enumerate(ev.get("related_events") or []):
                conn.execute(
                    "INSERT INTO synthesis_related_events(event_id, ord, related_event_id) VALUES (?, ?, ?)",
                    (eid, r_ord, rel_id),
                )
            if has_fts:
                actors_text = ", ".join((ev["actors"].get("primary") or []) + (ev["actors"].get("secondary") or []))
                places_text = ", ".join((ev["geography"].get("countries") or []) + (ev["geography"].get("places") or []))
                conn.execute(
                    """
                    INSERT INTO synthesis_events_fts(
                        date, event_id, category, subcategory, headline, summary,
                        topics_text, actors_text, places_text
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        date,
                        eid,
                        ev["category"],
                        ev["subcategory"],
                        ev["headline"],
                        ev["summary"],
                        ", ".join(ev.get("topics") or []),
                        actors_text,
                        places_text,
                    ),
                )
        for w_ord, w in enumerate(doc.get("works_cited") or []):
            conn.execute(
                """
                INSERT INTO synthesis_works_cited(date, ord, work_id, title, outlet, url, accessed)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (date, w_ord, w["id"], w["title"], w["outlet"], w["url"], w["accessed"]),
            )


def export_synthesis_doc(conn: sqlite3.Connection, date: str) -> dict[str, Any]:
    day = conn.execute("SELECT * FROM synthesis_days WHERE date = ?", (date,)).fetchone()
    if not day:
        raise KeyError(f"No synthesis record for {date}")
    ev_rows = conn.execute(
        "SELECT * FROM synthesis_events WHERE date = ? ORDER BY ord ASC",
        (date,),
    ).fetchall()
    events = []
    for er in ev_rows:
        eid = er["event_id"]
        kd_rows = conn.execute(
            "SELECT * FROM synthesis_key_data WHERE event_id = ? ORDER BY ord ASC",
            (eid,),
        ).fetchall()
        key_data = [
            {
                "label": r["label"],
                "value": r["value"],
                "citation_refs": json.loads(r["citation_refs_json"]),
            }
            for r in kd_rows
        ]
        src_rows = conn.execute(
            "SELECT * FROM synthesis_sources WHERE event_id = ? ORDER BY ord ASC",
            (eid,),
        ).fetchall()
        ext_sources = [
            {
                "id": r["source_id"],
                "outlet": r["outlet"],
                "url": r["url"],
                "publication_date": r["publication_date"],
                "source_type": r["source_type"],
                "reliability_tier": r["reliability_tier"],
                "supports": json.loads(r["supports_json"]),
                "contradicts": json.loads(r["contradicts_json"]),
                "quoted_material": json.loads(r["quoted_material_json"]),
                "citation_refs": json.loads(r["citation_refs_json"]),
            }
            for r in src_rows
        ]
        rel_rows = conn.execute(
            "SELECT related_event_id FROM synthesis_related_events WHERE event_id = ? ORDER BY ord ASC",
            (eid,),
        ).fetchall()
        events.append(
            {
                "id": eid,
                "category": er["category"],
                "subcategory": er["subcategory"],
                "topics": json.loads(er["topics_json"]),
                "importance": er["importance"],
                "headline": er["headline"],
                "summary": er["summary"],
                "key_data": key_data,
                "details": {
                    "what_happened": json.loads(er["what_happened_json"]),
                    "why_it_matters": json.loads(er["why_it_matters_json"]),
                    "uncertainty_notes": json.loads(er["uncertainty_notes_json"]),
                },
                "actors": json.loads(er["actors_json"]),
                "entities": json.loads(er["entities_json"]),
                "geography": json.loads(er["geography_json"]),
                "time": json.loads(er["time_json"]),
                "casualty_report": json.loads(er["casualty_report_json"]),
                "classification": json.loads(er["classification_json"]),
                "sources": {
                    "wikipedia_portal": json.loads(er["portal_source_json"]),
                    "external": ext_sources,
                },
                "provenance": json.loads(er["provenance_json"]),
                "confidence": json.loads(er["confidence_json"]),
                "related_events": [r["related_event_id"] for r in rel_rows],
                "notes": er["notes"],
            }
        )
    works_rows = conn.execute(
        "SELECT * FROM synthesis_works_cited WHERE date = ? ORDER BY ord ASC",
        (date,),
    ).fetchall()
    works_cited = [
        {
            "id": r["work_id"],
            "title": r["title"],
            "outlet": r["outlet"],
            "url": r["url"],
            "accessed": r["accessed"],
        }
        for r in works_rows
    ]
    return {
        "date": day["date"],
        "source_page": {
            "portal": day["portal"],
            "language": day["language"],
            "wikipedia_revision_id": day["wikipedia_revision_id"],
        },
        "dataset": {
            "schema_version": day["schema_version"],
            "compiler": {
                "mode": day["compiler_mode"],
                "status": day["compiler_status"],
                "reviewed": bool(day["compiler_reviewed"]),
            },
            "scope": {
                "seed_source": day["seed_source"],
                "enrichment_sources_expected": bool(day["enrichment_sources_expected"]),
            },
        },
        "editorial_policy": json.loads(day["editorial_policy_json"]),
        "analytical_overview": day["analytical_overview"],
        "events": events,
        "strategic_conclusion": day["strategic_conclusion"],
        "works_cited": works_cited,
    }


def search_synthesis_events(conn: sqlite3.Connection, query: str, limit: int = 25) -> list[dict[str, Any]]:
    if _has_fts(conn):
        rows = conn.execute(
            """
            SELECT date, event_id, category, subcategory, headline, summary
            FROM synthesis_events_fts
            WHERE synthesis_events_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    pat = f"%{query}%"
    rows = conn.execute(
        """
        SELECT date, event_id, category, subcategory, headline, summary
        FROM synthesis_events
        WHERE headline LIKE ? OR summary LIKE ? OR category LIKE ? OR subcategory LIKE ?
              OR topics_json LIKE ? OR actors_json LIKE ? OR geography_json LIKE ?
        ORDER BY date ASC, ord ASC
        LIMIT ?
        """,
        (pat, pat, pat, pat, pat, pat, pat, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def day_sqlite_path(date_str: str, root: Path | None = None) -> Path:
    base = root if root is not None else Path(__file__).resolve().parents[1]
    return base / date_str[:4] / date_str[5:7] / f"{date_str}.sqlite"


def build_day_sqlite(
    date_str: str,
    *,
    db_path: str | Path | None = None,
    synthesis_doc: dict[str, Any] | None = None,
    extraction_doc: dict[str, Any] | None = None,
    include_multisource: bool = True,
) -> Path:
    """Build a compact per-day `.sqlite` file (`<YYYY>/<MM>/<YYYY-MM-DD>.sqlite`, 1 KB page size)."""
    repo_root = Path(__file__).resolve().parents[1]
    target_path = Path(db_path) if db_path is not None else day_sqlite_path(date_str, repo_root)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.exists():
        target_path.unlink()

    if synthesis_doc is None:
        exp_path = repo_root / "expanded" / date_str[:4] / date_str[5:7] / f"{date_str}.yaml"
        if exp_path.exists():
            synthesis_doc = yaml.safe_load(exp_path.read_text(encoding="utf-8"))

    if extraction_doc is None:
        ext_path = repo_root / "provisional" / "extraction-v1" / date_str[:4] / date_str[5:7] / f"{date_str}.yaml"
        if ext_path.exists():
            extraction_doc = yaml.safe_load(ext_path.read_text(encoding="utf-8"))

    conn = connect(target_path, compact=True)
    try:
        conn.execute("INSERT OR REPLACE INTO archive_metadata(key, value) VALUES ('date', ?)", (date_str,))
        if extraction_doc is not None:
            import_extraction_doc(conn, extraction_doc)
        if include_multisource:
            from seed import multisource

            raw_sources, feed_items = multisource.collect_day_feeds(date_str)
            if raw_sources or feed_items:
                import_multisource_feeds(conn, date_str, raw_sources, feed_items)
            conn.execute(
                "INSERT OR REPLACE INTO archive_metadata(key, value) VALUES ('feed_item_count', ?)",
                (str(len(feed_items)),),
            )
        if synthesis_doc is not None:
            import_synthesis_doc(conn, synthesis_doc)
            evs = synthesis_doc.get("events") or []
            t1 = sum(1 for e in evs if _importance_to_tier(e["importance"]) == 1)
            t2 = sum(1 for e in evs if _importance_to_tier(e["importance"]) == 2)
            t3 = sum(1 for e in evs if _importance_to_tier(e["importance"]) == 3)
            for k, v in (
                ("total_events", str(len(evs))),
                ("tier1_count", str(t1)),
                ("tier2_count", str(t2)),
                ("tier3_count", str(t3)),
            ):
                conn.execute("INSERT OR REPLACE INTO archive_metadata(key, value) VALUES (?, ?)", (k, v))
        conn.commit()
        conn.execute("VACUUM;")
    finally:
        conn.close()
    return target_path


def rollup_sqlite(day_db_paths: list[str | Path], output_db_path: str | Path) -> Path:
    """Combine multiple per-day `.sqlite` files into a monthly or master SQLite DB with FTS5."""
    out_path = Path(output_db_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(out_path, compact=False)
    try:
        for p in sorted(Path(x) for x in day_db_paths):
            day_conn = sqlite3.connect(str(p))
            day_conn.row_factory = sqlite3.Row
            try:
                for r in day_conn.execute("SELECT date FROM extraction_days"):
                    import_extraction_doc(conn, export_extraction_doc(day_conn, r["date"]))
                for r in day_conn.execute("SELECT date FROM synthesis_days"):
                    import_synthesis_doc(conn, export_synthesis_doc(day_conn, r["date"]))
                src_rows = [dict(r) for r in day_conn.execute("SELECT * FROM raw_sources ORDER BY source_id ASC")]
                item_rows = [dict(r) for r in day_conn.execute("SELECT * FROM structured_feed_items ORDER BY ord ASC")]
                if src_rows:
                    import_multisource_feeds(conn, src_rows[0]["date"], src_rows, item_rows)
            finally:
                day_conn.close()
        conn.commit()
        conn.execute("VACUUM;")
    finally:
        conn.close()
    return out_path


# ---------------------------------------------------------------------------
# reStructuredText (.rst) & Markdown (.md) Exporters (Daily + Monthly Rollup)
# ---------------------------------------------------------------------------

def _rst_underline(title: str, char: str) -> str:
    return f"{title}\n{char * max(len(title), 4)}"


def render_synthesis_rst(doc: dict[str, Any]) -> str:
    """Render a schema-2.2 synthesis day document as structured reStructuredText (`.rst`)."""
    date = doc["date"]
    sp = doc["source_page"]
    comp = doc["dataset"]["compiler"]
    lines: list[str] = [
        f".. _day-{date}:",
        "",
        _rst_underline(f"Current Events Archive — {date}", "="),
        "",
        f":Date: {date}",
        f":Portal: ``{sp['portal']}``",
        f":Wikipedia Revision ID: ``{sp.get('wikipedia_revision_id')}``",
        f":Schema Version: ``{doc['dataset']['schema_version']}``",
        f":Compiler Status: ``{comp['status']}`` (reviewed: ``{comp['reviewed']}``)",
        "",
        _rst_underline("Analytical Overview", "-"),
        "",
        doc["analytical_overview"].strip(),
        "",
        _rst_underline("Events", "-"),
        "",
    ]
    for ev in doc["events"]:
        eid = ev["id"]
        lines.extend(
            [
                f".. _{eid}:",
                "",
                _rst_underline(f"[{eid}] {ev['headline']}", "~"),
                "",
                f":Category: {ev['category']} / {ev['subcategory']}",
                f":Importance: {ev['importance']}/10",
                f":Topics: {', '.join(ev.get('topics') or [])}",
                f":Countries: {', '.join(ev['geography'].get('countries') or [])}",
                f":Places: {', '.join(ev['geography'].get('places') or [])}",
            ]
        )
        if ev.get("related_events"):
            refs = ", ".join(f":ref:`{rid}`" for rid in ev["related_events"])
            lines.append(f":Related Events: {refs}")
        lines.extend(["", ev["summary"].strip(), ""])

        if ev.get("key_data"):
            lines.extend(
                [
                    ".. list-table:: Key Data",
                    "   :header-rows: 1",
                    "   :widths: 30 55 15",
                    "",
                    "   * - Metric",
                    "     - Value",
                    "     - Citations",
                ]
            )
            for kd in ev["key_data"]:
                cites = ", ".join(f"[{c}]_" for c in kd.get("citation_refs") or [])
                lines.extend(
                    [
                        f"   * - {kd['label']}",
                        f"     - {kd['value']}",
                        f"     - {cites}",
                    ]
                )
            lines.append("")

        det = ev["details"]
        if det.get("what_happened"):
            lines.extend(["**What Happened**", ""])
            for bullet in det["what_happened"]:
                lines.append(f"* {bullet}")
            lines.append("")
        if det.get("why_it_matters"):
            lines.extend(["**Why It Matters**", ""])
            for bullet in det["why_it_matters"]:
                lines.append(f"* {bullet}")
            lines.append("")
        if det.get("uncertainty_notes"):
            lines.append(".. note::")
            for note in det["uncertainty_notes"]:
                lines.append(f"   {note}")
            lines.append("")

        if ev["sources"].get("external"):
            lines.extend(["**Sources & Verbatim Evidence**", ""])
            for src in ev["sources"]["external"]:
                cites = ", ".join(f"[{c}]_" for c in src.get("citation_refs") or [])
                lines.append(
                    f"* **{src['outlet']}** ({src['publication_date']}, ``{src['source_type']}``, "
                    f"tier: ``{src['reliability_tier']}``) <{src['url']}> {cites}"
                )
                for q in src.get("quoted_material") or []:
                    lines.append(f'  - Quote: *"{q}"*')
            lines.append("")

    lines.extend(
        [
            _rst_underline("Strategic Conclusion", "-"),
            "",
            doc["strategic_conclusion"].strip(),
            "",
            _rst_underline("Works Cited", "-"),
            "",
        ]
    )
    for w in doc.get("works_cited") or []:
        lines.append(f".. [{w['id']}] {w['title']} — *{w['outlet']}* (<{w['url']}>, accessed {w['accessed']})")
    lines.append("")
    return "\n".join(lines)


def render_monthly_rst(conn: sqlite3.Connection, year_month: str) -> str:
    """Render a multi-day monthly synthesis rollup in reStructuredText (`.rst`)."""
    rows = conn.execute(
        "SELECT date FROM synthesis_days WHERE date LIKE ? ORDER BY date ASC",
        (f"{year_month}-%",),
    ).fetchall()
    dates = [r["date"] for r in rows]
    docs = [export_synthesis_doc(conn, d) for d in dates]
    total_events = sum(len(d["events"]) for d in docs)
    lines: list[str] = [
        f".. _month-{year_month}:",
        "",
        _rst_underline(f"Monthly Current Events Synthesis — {year_month}", "="),
        "",
        f":Month: {year_month}",
        f":Days Covered: {len(docs)} ({dates[0] if dates else 'none'} to {dates[-1] if dates else 'none'})",
        f":Total Researched Events: {total_events}",
        "",
    ]
    for doc in docs:
        d = doc["date"]
        lines.extend(
            [
                f".. _day-summary-{d}:",
                "",
                _rst_underline(f"{d} ({len(doc['events'])} events)", "-"),
                "",
                doc["analytical_overview"].strip(),
                "",
            ]
        )
        for ev in doc["events"]:
            lines.append(
                f"* **[{ev['id']}] {ev['headline']}** (*{ev['category']}*, importance: {ev['importance']}/10) — {ev['summary'].strip()}"
            )
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SQLite archive import/export and view generator")
    parser.add_argument("--db", default="provisional/archive.sqlite", help="SQLite database path")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ingest_ext = sub.add_parser("ingest-extraction", help="Import extraction-1.0 YAML files into SQLite")
    p_ingest_ext.add_argument("paths", nargs="*", default=["provisional/extraction-v1"], help="Files or directories to import")

    p_ingest = sub.add_parser("ingest-expanded", help="Import expanded synthesis YAML files into SQLite")
    p_ingest.add_argument("paths", nargs="*", default=["expanded"], help="Files or directories to import")

    p_rst = sub.add_parser("export-rst", help="Export a date or YYYY-MM month to reStructuredText (.rst)")
    p_rst.add_argument("target", help="Date (YYYY-MM-DD) or month (YYYY-MM)")
    p_rst.add_argument("--output", required=True, help="Output .rst file path")

    p_search = sub.add_parser("search", help="Search researched events via SQLite FTS5")
    p_search.add_argument("query", help="FTS5 query string")

    p_day = sub.add_parser("build-day-db", help="Build compact per-day <YYYY>/<MM>/<YYYY-MM-DD>.sqlite file(s)")
    p_day.add_argument("dates", nargs="+", help="One or more YYYY-MM-DD dates")

    p_rollup = sub.add_parser("rollup", help="Roll up per-day .sqlite files into a monthly or master SQLite DB with FTS5")
    p_rollup.add_argument("paths", nargs="+", help="Per-day .sqlite files or directories containing them")
    p_rollup.add_argument("--output", required=True, help="Output rollup .sqlite path")

    args = parser.parse_args(argv)

    if args.cmd == "build-day-db":
        for d in args.dates:
            out = build_day_sqlite(d)
            print(f"Built {out} ({out.stat().st_size:,} bytes)")
        return 0

    if args.cmd == "rollup":
        day_files: list[Path] = []
        for raw in args.paths:
            p = Path(raw)
            if p.is_dir():
                day_files.extend(
                    f for f in sorted(p.rglob("*.sqlite")) if len(f.stem) == 10 and f.stem[4] == "-" and f.stem[7] == "-"
                )
            elif p.exists():
                day_files.append(p)
        out = rollup_sqlite(day_files, args.output)
        print(f"Rolled up {len(day_files)} day DB(s) into {out} ({out.stat().st_size:,} bytes)")
        return 0

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)

    if args.cmd == "ingest-extraction":
        count = 0
        for raw in args.paths:
            p = Path(raw)
            files = sorted(p.rglob("*.yaml")) if p.is_dir() else [p]
            for f in files:
                doc = yaml.safe_load(f.read_text(encoding="utf-8"))
                import_extraction_doc(conn, doc)
                count += 1
        print(f"Imported {count} extraction day(s) into {db_path}")
        return 0

    if args.cmd == "ingest-expanded":
        count = 0
        for raw in args.paths:
            p = Path(raw)
            files = sorted(p.rglob("*.yaml")) if p.is_dir() else [p]
            for f in files:
                doc = yaml.safe_load(f.read_text(encoding="utf-8"))
                import_synthesis_doc(conn, doc)
                count += 1
        print(f"Imported {count} synthesis day(s) into {db_path}")
        return 0

    if args.cmd == "export-rst":
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if len(args.target) == 7:
            text = render_monthly_rst(conn, args.target)
        else:
            doc = export_synthesis_doc(conn, args.target)
            text = render_synthesis_rst(doc)
        out_path.write_text(text, encoding="utf-8")
        print(f"Wrote {out_path}")
        return 0

    if args.cmd == "search":
        hits = search_synthesis_events(conn, args.query)
        for h in hits:
            print(f"{h['date']}  {h['event_id']}  [{h['category']}]  {h['headline']}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
