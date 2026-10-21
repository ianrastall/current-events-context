"""Self-contained annual reference archives; acquisition is deliberately absent."""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import subprocess
import tempfile
from unittest.mock import patch

import yaml
from jsonschema import Draft202012Validator

from seed import extract, source, sqlite_archive

ROOT = Path(__file__).resolve().parents[1]
VERSION = "annual-archive-1.1"
SCHEMA = "reference/schema/annual-archive.sql"
CONTRACT = "reference/schema/ANNUAL_ARCHIVE.md"
PARSER_INPUTS = ("seed/extract.py", "seed/inline.py", "seed/rendered.py", "seed/wikipedia.py",
                 "seed/sqlite_archive.py", "seed/annual_archive.py", "requirements.txt",
                 "reference/schema/extraction.schema.json", SCHEMA, CONTRACT)
LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def structured_hash(value):
    return digest(encoded(value))


class TransactionConnection(sqlite3.Connection):
    """Nested bridge imports must not commit an enclosing day transaction."""

    def __enter__(self):
        stack = getattr(self, "_savepoints", [])
        name = f"annual_{len(stack)}"
        self.execute(f"SAVEPOINT {name}")
        stack.append(name)
        self._savepoints = stack
        return self

    def __exit__(self, kind, value, traceback):
        name = self._savepoints.pop()
        if kind is not None:
            self.execute(f"ROLLBACK TO {name}")
        self.execute(f"RELEASE {name}")
        return False


def connect(path, *, readonly=False):
    mode = "ro" if readonly else "rw"
    conn = sqlite3.connect(Path(path).resolve().as_uri() + f"?mode={mode}", uri=True,
                           factory=TransactionConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        version = conn.execute("SELECT value FROM archive_metadata WHERE key='annual_schema_version'").fetchone()
        if version is None or version[0] != VERSION:
            raise ValueError("Unsupported annual archive; an explicit migration is required")
    except BaseException:
        conn.close()
        raise
    return conn


def put_input(conn, path, payload, role, date=None, media_type="text/plain"):
    """Archive immutable input bytes once; never silently replace an identity."""
    key = digest(payload)
    old = conn.execute("SELECT sha256, role, date FROM archive_inputs WHERE path=?", (path,)).fetchone()
    if old is not None and tuple(old) != (key, role, date):
        raise ValueError(f"Archived input drift: {path}")
    conn.execute("INSERT OR IGNORE INTO archive_blobs VALUES(?,?,?)", (key, media_type, payload))
    conn.execute("INSERT OR IGNORE INTO archive_inputs VALUES(?,?,?,?)", (path, date, role, key))
    return key


def input_bytes(conn, path):
    row = conn.execute("SELECT b.payload FROM archive_inputs i JOIN archive_blobs b USING(sha256) WHERE i.path=?", (path,)).fetchone()
    if row is None:
        raise ValueError(f"Missing embedded input: {path}")
    return row[0]


def initialize(path, year, root=ROOT):
    if not 1 <= year <= 9999:
        raise ValueError("Invalid calendar year")
    conn = sqlite3.connect(path, factory=TransactionConnection)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(sqlite_archive.DDL + sqlite_archive.FTS_DDL + (root / SCHEMA).read_text(encoding="utf-8"))
        try:
            commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        except (OSError, subprocess.CalledProcessError):
            commit = "unknown"
        metadata = {
            "schema_version": sqlite_archive.SCHEMA_VERSION,
            "annual_schema_version": VERSION, "year": str(year), "source_git_commit": commit,
            "source_policy": "existing_recorded_oldids; no acquisition; source text retained verbatim",
            "review_policy": "migration verification is not factual review; synthesis defaults to draft",
            "wikipedia_license": "CC BY-SA; attribution via stored page/revision metadata and raw source",
            "historical_perspective": "retrospective source captures; not an as-known-on-the-day dataset",
            "yearbook_status": "not_ready",
        }
        with conn:
            conn.executemany("INSERT INTO archive_metadata VALUES(?,?)", metadata.items())
            for name in PARSER_INPUTS:
                put_input(conn, name, (root / name).read_bytes(), "implementation")
            # Embed the bridge DDL as readable text, not just a Python source listing.
            put_input(conn, "schema/compatibility.sql", (sqlite_archive.DDL + sqlite_archive.FTS_DDL).encode(), "schema", media_type="text/plain")
    except BaseException:
        conn.close()
        raise
    return conn


def reconcile(raw, doc, legacy):
    """Account for source locations and every prior-parser item, without guessing."""
    from seed.wikipedia import parse_events_legacy

    day = doc["date"]
    relevant, offset, _ = extract.body(raw, day)
    source_lines = [n for n, line in enumerate(relevant.splitlines(), offset + 1)
                    if re.match(r"^\s*[*:]+", line)]
    entries = [(ci, e) for ci, c in enumerate(doc["categories"]) for e in c["entries"]]
    represented = [e["line"] for _, e in entries]
    represented += [c["line"] for c in doc["categories"] if re.match(r"^\s*[*:]+", c.get("raw", ""))]
    if sorted(source_lines) != sorted(represented):
        raise ValueError(f"Unaccounted source bullet locations: {day}")
    for category in doc["categories"]:
        by_path = {tuple(e["source_path"]): e for e in category["entries"]}
        if len(by_path) != len(category["entries"]):
            raise ValueError(f"Duplicate structural path: {day}")
        last_line = -1
        for e in category["entries"]:
            if e["line"] <= last_line or e["role"] not in ("event", "topic", "unknown"):
                raise ValueError(f"Invalid ordering or role: {day}")
            last_line = e["line"]
            if e["parent_path"] is not None:
                parent = by_path.get(tuple(e["parent_path"]))
                if parent is None or parent["line"] >= e["line"] or e["source_path"][:-1] != e["parent_path"]:
                    raise ValueError(f"Invalid parent: {day}")
    category_lines = [c.get("line", 0) for c in doc["categories"]]
    if category_lines != sorted(category_lines):
        raise ValueError(f"Invalid category order: {day}")
    trace = []
    replayed = parse_events_legacy(raw, doc["source_page"]["page"], trace=trace)
    roles = {e["line"]: e["role"] for _, e in entries}
    roles.update({c["line"]: "category" for c in doc["categories"] if "line" in c})
    mapped = {role: 0 for role in ("event", "topic", "unknown", "category")}
    for item in trace:
        role = roles.get(item["line"] + offset)
        if role is None:
            raise ValueError(f"Prior parser item missing from source representation: {day}")
        item["source_line"], item["role"] = item["line"] + offset, role
        mapped[role] += 1
    parents = {(ci, tuple(e["parent_path"])) for ci, e in entries if e["parent_path"] is not None}
    old_categories = legacy.get("wikipedia", {}).get("categories", {})
    return {
        "source_bullets": len(source_lines), "represented_bullets": len(represented),
        "prior_flat_items": sum(len(v) for v in old_categories.values()),
        "baseline_matches_legacy_replay": old_categories == replayed,
        "legacy_items_by_role": mapped, "legacy_trace": trace,
        "event_leaves": sum(e["role"] == "event" and (ci, tuple(e["source_path"])) not in parents for ci, e in entries),
        "event_containers": sum(e["role"] == "event" and (ci, tuple(e["source_path"])) in parents for ci, e in entries),
        "events_not_emitted_by_legacy_parser": sum(e["role"] == "event" for _, e in entries) - mapped["event"],
        "unknown_roles": sum(e["role"] == "unknown" for _, e in entries),
        "gdelt_preserved": doc.get("gdelt") == legacy.get("gdelt"),
    }


def make_extraction(day, meta, payload, legacy, overrides=None):
    identity = {k: meta[k] for k in ("page", "revision_id", "revision_timestamp", "source_mode", "source_sha256")}
    doc = extract.extract(payload.decode("utf-8"), date=day, source=identity, overrides=overrides, source_templates=True)
    if "gdelt" in legacy:
        doc["gdelt"] = legacy["gdelt"]
    return doc


def compare_candidate(prior, doc):
    """Explain every structured delta; reject lost entries, links or citations."""
    if prior["date"] != doc["date"] or prior["source_page"] != doc["source_page"]:
        raise ValueError("Candidate comparison changed source policy")
    before = [(ci, e) for ci, c in enumerate(prior["categories"]) for e in c["entries"]]
    after = [(ci, e) for ci, c in enumerate(doc["categories"]) for e in c["entries"]]
    if len(before) != len(after) or len(prior["categories"]) != len(doc["categories"]):
        raise ValueError("Candidate comparison changed entry/category coverage")
    changes = []
    for old_category, new_category in zip(prior["categories"], doc["categories"]):
        if any(old_category.get(k) != new_category.get(k) for k in ("name", "line", "raw", "links", "citations")):
            raise ValueError("Unexplained category change")
    for (ci, old), (new_ci, new) in zip(before, after):
        for key in ("depth", "source_path", "parent_path", "line", "list_marker"):
            if ci != new_ci or old.get(key) != new.get(key):
                raise ValueError("Candidate comparison changed source hierarchy")
        for field in ("links", "citations"):
            remaining = iter(new[field])
            if not all(any(item == candidate for candidate in remaining) for item in old[field]):
                raise ValueError("Candidate comparison dropped or reordered a link or citation")
        reasons = []
        if old["role"] != new["role"]:
            empty_marker = old["role"] == "event" and new["role"] == "unknown" and not old["text"] and re.fullmatch(r"[*:]+\s*", old["raw"].strip())
            if not empty_marker and (old["role"] != "unknown" or new["role"] != "topic"):
                raise ValueError("Unexplained event-role change")
            reasons.append("empty_source_marker_not_event" if empty_marker else "source_topic_rule_or_guarded_heading")
        if old["raw"] != new["raw"]:
            added = new["raw"][len(old["raw"]):]
            if not new["raw"].startswith(old["raw"] + "\n") or added.strip() not in [w["raw"].strip() for w in prior["warnings"]]:
                raise ValueError("Unexplained source fragment change")
            reasons.append("adjacent_citation_continuation")
        if old["text"] != new["text"] or old["links"] != new["links"]:
            reasons.append("explicit_template_argument_projection")
        if old["citations"] != new["citations"] and "adjacent_citation_continuation" not in reasons:
            raise ValueError("Unexplained citation change")
        if reasons:
            changes.append({"category_ord": ci, "source_path": new["source_path"], "reasons": reasons,
                            "before_sha256": structured_hash(old), "after_sha256": structured_hash(new)})
    return {"entry_deltas": changes,
            "event_leaf_delta": sum(e["role"] == "event" for _, e in after) - sum(e["role"] == "event" for _, e in before),
            "entries_preserved": len(before), "source_identity_preserved": True}


def review_locator(row):
    row = dict(row)
    return {"date": row["date"], "category": row["category"], "category_ord": row["category_ord"],
            "source_path": json.loads(row["source_path_json"]), "source_sha256": row["source_sha256"],
            "raw_sha256": extract.fingerprint(row["raw"])}


def locate_review_event(conn, locator):
    found = [dict(r) for r in conn.execute("SELECT * FROM event_overview WHERE date=? AND role='event'", (locator["date"],))
             if review_locator(r) == locator]
    if len(found) != 1:
        raise ValueError("Factual review source locator drift")
    return found[0]


def record_review(conn, record):
    """Store scoped publisher observations, never a blanket factual endorsement."""
    row = locate_review_event(conn, record["locator"])
    if structured_hash(row) != record["event_sha256"]:
        raise ValueError("Factual review extraction drift")
    if not record["scope"].strip() or not record["note"].strip() or not record["evidence"]:
        raise ValueError("Review scope, note and evidence are required")
    if record["assessment"] in ("supported", "partially_supported", "contradicted") and not any(e["access_status"] == "opened" for e in record["evidence"]):
        raise ValueError("A factual assessment requires an opened publisher source")
    path = f"reviews/{record['id']}.json"
    with conn:
        put_input(conn, path, encoded(record), "factual_review", record["locator"]["date"], "application/json")
        old = conn.execute("SELECT id FROM factual_reviews WHERE id=?", (record["id"],)).fetchone()
        if old:
            return
        conn.execute("INSERT INTO factual_reviews VALUES(?,?,?,?,?,?,?,?,?)",
                     (record["id"], record["locator"]["date"], encoded(record["locator"]).decode(),
                      record["event_sha256"], record["scope"], record["assessment"], record["checked_on"], record["note"], path))
        for n, evidence in enumerate(record["evidence"]):
            conn.execute("INSERT INTO review_evidence VALUES(?,?,?,?,?,?,?)",
                         (record["id"], n, evidence["url"], evidence["publisher"], evidence.get("publication_date"), evidence["access_status"], evidence["note"]))
        conn.execute("DELETE FROM archive_checks WHERE name IN ('migration','coverage')")


def verify_review(conn, row):
    record = json.loads(input_bytes(conn, row["input_path"]))
    for key in ("id", "scope", "assessment", "checked_on", "note", "event_sha256"):
        if row[key] != record[key]:
            raise ValueError("Factual review record differs from preserved evidence")
    if json.loads(row["locator_json"]) != record["locator"] or row["date"] != record["locator"]["date"]:
        raise ValueError("Factual review locator corruption")
    event = locate_review_event(conn, record["locator"])
    if structured_hash(event) != record["event_sha256"]:
        raise ValueError("Factual review extraction drift")
    evidence = [(e["url"], e["publisher"], e.get("publication_date"), e["access_status"], e["note"]) for e in record["evidence"]]
    stored = [tuple(r) for r in conn.execute("SELECT url,publisher,publication_date,access_status,note FROM review_evidence WHERE review_id=? ORDER BY ord", (row["id"],))]
    if stored != evidence:
        raise ValueError("Factual review evidence corruption")


def coverage_report(conn):
    monthly = []
    for row in conn.execute("SELECT substr(date,1,7) AS month,count(*) AS days,sum(source_events) AS events,sum(unresolved_warnings) AS warnings,sum(unknown_roles) AS unknown_roles FROM day_coverage GROUP BY month ORDER BY month"):
        monthly.append(dict(row))
    uncited = [dict(r) for r in conn.execute("SELECT date,category_ord,ord,text FROM event_overview e WHERE role='event' AND NOT EXISTS(SELECT 1 FROM event_citations c WHERE c.date=e.date AND c.category_ord=e.category_ord AND c.entry_ord=e.ord) ORDER BY date,category_ord,ord")]
    reviewed = conn.execute("SELECT count(DISTINCT event_sha256) FROM factual_reviews").fetchone()[0]
    total = conn.execute("SELECT count(*) FROM event_overview WHERE role='event'").fetchone()[0]
    return {"scope": "complete-calendar source-coverage census; publisher checks are separately scoped and partial",
            "monthly": monthly, "source_events": total, "events_with_scoped_publisher_review": reviewed,
            "events_without_scoped_publisher_review": total - reviewed,
            "scoped_review_assessments": {r[0]: r[1] for r in conn.execute("SELECT assessment,count(*) FROM factual_reviews GROUP BY assessment")},
            "uncited_source_events": uncited,
            "unclassified_fragments": conn.execute("SELECT count(*) FROM unclassified_source").fetchone()[0],
            "empty_source_markers": conn.execute("SELECT count(*) FROM extraction_warnings WHERE json_extract(warning_json,'$.code')='SOURCE_EMPTY_MARKER'").fetchone()[0],
            "source_reliability_annotations": conn.execute("SELECT count(*) FROM extraction_warnings WHERE json_extract(warning_json,'$.code')='SOURCE_RELIABILITY_TAG'").fetchone()[0],
            "categories": [dict(r) for r in conn.execute("SELECT category,count(*) AS events FROM event_overview WHERE role='event' GROUP BY category ORDER BY events DESC")],
            "yearbook_ready": False, "factual_review_complete": False}


def ingest_day(conn, day, root=ROOT):
    """One date transaction; no daily candidate file is written."""
    parsed = dt.date.fromisoformat(day)
    year = int(conn.execute("SELECT value FROM archive_metadata WHERE key='year'").fetchone()[0])
    if parsed.year != year:
        raise ValueError("Date is outside the archive year")
    old_path = f"{day[:4]}/{day[5:7]}/{day}.yaml"
    legacy_bytes = (root / old_path).read_bytes()
    legacy = yaml.load(legacy_bytes, Loader=LOADER)
    if legacy["date"] != day:
        raise ValueError("Daily input date mismatch")
    revision = legacy["source_page"]["wikipedia_revision_id"]
    if revision is None:
        raise ValueError("Annual v1 migration requires a recorded pinned oldid")
    base = root / "reference/sources/wikipedia/wikitext" / str(revision)
    meta, payload = source.load(base)
    if meta["revision_id"] != revision or meta["page"] != legacy["source_page"]["portal"]:
        raise ValueError("Recorded source identity differs from cached revision")
    override_path = f"reference/overrides/{parsed.year}-extraction.json"
    override_bytes = (root / override_path).read_bytes() if (root / override_path).exists() else None
    selected = [o for o in json.loads(override_bytes or b"[]") if o["date"] == day]
    doc = make_extraction(day, meta, payload, legacy, selected)
    schema = json.loads(input_bytes(conn, "reference/schema/extraction.schema.json"))
    Draft202012Validator(schema).validate(doc)
    check = reconcile(payload.decode("utf-8"), doc, legacy)
    candidate = root / "provisional/extraction-v1" / day[:4] / day[5:7] / f"{day}.yaml"
    if candidate.exists():
        prior = yaml.load(candidate.read_bytes(), Loader=LOADER)
        check["prior_candidate_sha256"] = structured_hash(prior)
        check["prior_candidate_matches"] = prior == doc
        check["prior_candidate_reconciliation"] = compare_candidate(prior, doc)
    else:
        check["prior_candidate_matches"] = None
    old = conn.execute("SELECT extraction_sha256 FROM day_ingestions WHERE date=?", (day,)).fetchone()
    if old is not None and old[0] != structured_hash(doc):
        raise ValueError(f"Extraction drift for {day}; explicit migration required")
    if old is not None and sqlite_archive.export_extraction_doc(conn, day) != doc:
        raise ValueError(f"Stored extraction drift for {day}")
    src_path = base.with_suffix(".wiki").relative_to(root).as_posix()
    with conn:
        if override_bytes is not None:
            put_input(conn, override_path, override_bytes, "extraction_overrides", media_type="application/json")
        put_input(conn, old_path, legacy_bytes, "legacy_seed", day, "application/yaml")
        put_input(conn, src_path, payload, "wikipedia_wikitext", day, "text/x-wiki")
        for suffix in (".json", ".provenance.json"):
            p = base.with_suffix(suffix)
            if p.exists():
                put_input(conn, p.relative_to(root).as_posix(), p.read_bytes(), "source_metadata", day, "application/json")
        if old is not None:
            return
        sqlite_archive.import_extraction_doc(conn, doc)
        conn.execute("INSERT INTO day_ingestions VALUES(?,?,?,?,?,?)",
                     (day, old_path, src_path, encoded(meta).decode(), structured_hash(doc), encoded(check).decode()))
        conn.executemany("INSERT INTO archive_events_fts(date,category,text) VALUES(?,?,?)",
                         [(day, c["name"], e["text"]) for c in doc["categories"] for e in c["entries"] if e["role"] == "event"])
        conn.execute("DELETE FROM archive_checks")


def verify(conn, *, complete=True):
    """Verify using embedded inputs alone, with network connection attempts blocked."""
    if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or conn.execute("PRAGMA foreign_key_check").fetchall():
        raise ValueError("Database integrity or foreign key failure")
    for row in conn.execute("SELECT sha256,payload FROM archive_blobs"):
        if digest(row["payload"]) != row["sha256"]:
            raise ValueError("Embedded input hash mismatch")
    year = int(conn.execute("SELECT value FROM archive_metadata WHERE key='year'").fetchone()[0])
    expected = [str(dt.date(year, 1, 1) + dt.timedelta(days=i)) for i in range(366 if calendar.isleap(year) else 365)]
    dates = [r[0] for r in conn.execute("SELECT date FROM day_ingestions ORDER BY date")]
    if any(day not in expected for day in dates) or (complete and dates != expected):
        raise ValueError("Incomplete or out-of-year calendar coverage")
    if dates != [r[0] for r in conn.execute("SELECT date FROM extraction_days ORDER BY date")]:
        raise ValueError("Untracked extraction dates")
    for name in PARSER_INPUTS:
        if input_bytes(conn, name) != (ROOT / name).read_bytes():
            raise ValueError(f"Implementation differs from recorded pipeline: {name}")
    schema = json.loads(input_bytes(conn, "reference/schema/extraction.schema.json"))
    validator = Draft202012Validator(schema)
    mismatches, baselines, unknown, events, leaves, warnings = [], [], 0, 0, 0, {}
    with patch.object(socket.socket, "connect", side_effect=AssertionError("Annual verification forbids network access")):
        for day in dates:
            row = conn.execute("SELECT * FROM day_ingestions WHERE date=?", (day,)).fetchone()
            legacy = yaml.load(input_bytes(conn, row["legacy_path"]), Loader=LOADER)
            meta = json.loads(row["source_metadata_json"])
            payload = input_bytes(conn, row["source_path"])
            if digest(payload) != meta["source_sha256"]:
                raise ValueError(f"Source hash mismatch: {day}")
            metadata_inputs = [r[0] for r in conn.execute("SELECT path FROM archive_inputs WHERE date=? AND role='source_metadata' ORDER BY path", (day,))]
            originals = [json.loads(input_bytes(conn, p)) for p in metadata_inputs]
            if meta not in originals:
                raise ValueError(f"Source metadata not preserved: {day}")
            if (legacy["date"] != day or legacy["source_page"]["wikipedia_revision_id"] != meta["revision_id"]
                    or legacy["source_page"]["portal"] != meta["page"]):
                raise ValueError(f"Pinned legacy identity mismatch: {day}")
            overrides = []
            for record in conn.execute("SELECT path FROM archive_inputs WHERE role='extraction_overrides'"):
                overrides.extend(o for o in json.loads(input_bytes(conn, record[0])) if o["date"] == day)
            doc = make_extraction(day, meta, payload, legacy, overrides)
            again = make_extraction(day, meta, payload, legacy, overrides)
            exported = sqlite_archive.export_extraction_doc(conn, day)
            validator.validate(exported)
            if doc != again or exported != doc or structured_hash(doc) != row["extraction_sha256"]:
                raise ValueError(f"Extraction replay, idempotence or round-trip failure: {day}")
            check = reconcile(payload.decode("utf-8"), exported, legacy)
            saved = json.loads(row["reconciliation_json"])
            if any(saved.get(k) != v for k, v in check.items()):
                raise ValueError(f"Reconciliation drift: {day}")
            if saved["prior_candidate_matches"] is not True and not saved.get("prior_candidate_reconciliation", {}).get("source_identity_preserved"):
                mismatches.append(day)
            elif saved["prior_candidate_matches"] is True and saved.get("prior_candidate_sha256") != structured_hash(doc):
                raise ValueError(f"Prior candidate comparison hash mismatch: {day}")
            if not check["baseline_matches_legacy_replay"]:
                baselines.append(day)
            unknown += check["unknown_roles"]
            leaves += check["event_leaves"]
            events += check["event_leaves"] + check["event_containers"]
            for w in doc["warnings"]:
                if w["resolution"] is None:
                    warnings[w["code"]] = warnings.get(w["code"], 0) + 1
    fts_rows = list(conn.execute("SELECT date,category,text FROM archive_events_fts ORDER BY date,category,text"))
    event_rows = list(conn.execute("SELECT date,category,text FROM event_overview WHERE role='event' ORDER BY date,category,text"))
    if [tuple(r) for r in fts_rows] != [tuple(r) for r in event_rows]:
        raise ValueError("Source event search index differs from extraction")
    researched_days = conn.execute("SELECT count(*) FROM synthesis_days WHERE compiler_reviewed=1").fetchone()[0]
    empty_markers = conn.execute("SELECT count(*) FROM extraction_warnings WHERE json_extract(warning_json,'$.code')='SOURCE_EMPTY_MARKER'").fetchone()[0]
    for review in conn.execute("SELECT * FROM factual_reviews"):
        verify_review(conn, dict(review))
    blockers = []
    if dates != expected:
        blockers.append("incomplete_calendar")
    if warnings or unknown > empty_markers:
        blockers.append("unresolved_extraction_warnings")
    if mismatches or baselines:
        blockers.append("baseline_reconciliation_required")
    # No automatic operation can turn transfer checks into factual approval.
    blockers.append("factual_coverage_review_not_recorded")
    return {"contract": VERSION, "year": year, "days": len(dates), "calendar_complete": dates == expected,
            "verified": True, "offline_embedded_source_replay": True, "events": events,
            "event_leaves": leaves, "unknown_roles": unknown, "unresolved_warnings": warnings,
            "known_empty_source_markers": empty_markers, "unknown_heading_roles": unknown - empty_markers,
            "prior_candidate_differences_or_missing": mismatches, "legacy_replay_differences": baselines,
            "reviewed_synthesis_days": researched_days, "yearbook_ready": False,
            "scoped_factual_reviews": conn.execute("SELECT count(*) FROM factual_reviews").fetchone()[0],
            "unclassified_source_fragments": conn.execute("SELECT count(*) FROM unclassified_source").fetchone()[0],
            "replacement_ready": False, "replacement_blockers": blockers}


def build_year(year, output=None, root=ROOT):
    target = Path(output) if output else root / "archive" / f"{year}.sqlite"
    if any((root / "expanded" / str(year)).glob("*/*.yaml")):
        raise ValueError("Existing researched synthesis requires a separate annual import migration")
    if target.exists():
        existing = connect(target, readonly=True)
        try:
            for table in ("synthesis_days", "raw_sources", "structured_feed_items", "generation_runs", "editorial_sections", "factual_reviews"):
                if existing.execute(f"SELECT count(*) FROM {table}").fetchone()[0]:
                    raise ValueError("Refusing to rebuild over research or external feeds; migrate explicitly")
            # Prevent dropping any manually preserved additional research inputs.
            if existing.execute("SELECT count(*) FROM archive_inputs WHERE role NOT IN ('implementation','schema','legacy_seed','wikipedia_wikitext','source_metadata')").fetchone()[0]:
                raise ValueError("Refusing to rebuild over additional archived inputs")
        finally:
            existing.close()
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, staging = tempfile.mkstemp(prefix=f".{target.stem}-", suffix=".sqlite", dir=target.parent)
    os.close(handle)
    staging = Path(staging)
    conn = None
    try:
        conn = initialize(staging, year, root)
        days = 366 if calendar.isleap(year) else 365
        with patch.object(socket.socket, "connect", side_effect=AssertionError("Annual build forbids network access")):
            for i in range(days):
                day = str(dt.date(year, 1, 1) + dt.timedelta(days=i))
                ingest_day(conn, day, root)
                if (i + 1) % 50 == 0:
                    print(f"Archived {i + 1}/{days} dates", flush=True)
        report = verify(conn)
        with conn:
            conn.execute("INSERT INTO archive_checks VALUES('migration',?)", (encoded(report).decode(),))
        conn.execute("VACUUM")
        conn.close()
        conn = None
        os.replace(staging, target)
        return report
    finally:
        if conn is not None:
            conn.close()
        staging.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="Build and verify one year offline, replacing only the target DB atomically")
    build.add_argument("year", type=int)
    build.add_argument("--output", type=Path)
    check = sub.add_parser("verify", help="Verify a complete annual archive from its embedded sources")
    check.add_argument("database", type=Path)
    ingest = sub.add_parser("ingest-day", help="Add one date transactionally from existing pinned inputs")
    ingest.add_argument("database", type=Path)
    ingest.add_argument("date")
    args = parser.parse_args(argv)
    if args.command == "build":
        report = build_year(args.year, args.output)
    else:
        conn = connect(args.database, readonly=args.command == "verify")
        try:
            if args.command == "ingest-day":
                with conn:
                    ingest_day(conn, args.date)
                    report = verify(conn, complete=False)
                    conn.execute("INSERT OR REPLACE INTO archive_checks VALUES('migration',?)", (encoded(report).decode(),))
            else:
                report = verify(conn)
        finally:
            conn.close()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
