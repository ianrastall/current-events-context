-- annual-archive-1.1 extensions to the extraction/synthesis compatibility schema.
CREATE TABLE archive_blobs (
    sha256 TEXT PRIMARY KEY CHECK(length(sha256) = 64),
    media_type TEXT NOT NULL,
    payload BLOB NOT NULL
);
CREATE TABLE archive_inputs (
    path TEXT PRIMARY KEY,
    date TEXT,
    role TEXT NOT NULL,
    sha256 TEXT NOT NULL REFERENCES archive_blobs(sha256)
);
CREATE TABLE day_ingestions (
    date TEXT PRIMARY KEY REFERENCES extraction_days(date),
    legacy_path TEXT NOT NULL REFERENCES archive_inputs(path),
    source_path TEXT NOT NULL REFERENCES archive_inputs(path),
    source_metadata_json TEXT NOT NULL,
    extraction_sha256 TEXT NOT NULL,
    reconciliation_json TEXT NOT NULL
);
CREATE TABLE archive_checks (
    name TEXT PRIMARY KEY,
    report_json TEXT NOT NULL
);
CREATE TABLE factual_reviews (
    id TEXT PRIMARY KEY,
    date TEXT NOT NULL REFERENCES extraction_days(date),
    locator_json TEXT NOT NULL,
    event_sha256 TEXT NOT NULL,
    scope TEXT NOT NULL,
    assessment TEXT NOT NULL CHECK(assessment IN ('supported','partially_supported','contradicted','inaccessible','needs_research')),
    checked_on TEXT NOT NULL,
    note TEXT NOT NULL,
    input_path TEXT NOT NULL REFERENCES archive_inputs(path)
);
CREATE TABLE review_evidence (
    review_id TEXT NOT NULL REFERENCES factual_reviews(id),
    ord INTEGER NOT NULL,
    url TEXT NOT NULL,
    publisher TEXT NOT NULL,
    publication_date TEXT,
    access_status TEXT NOT NULL CHECK(access_status IN ('opened','blocked','not_found','not_opened')),
    note TEXT NOT NULL,
    PRIMARY KEY(review_id,ord)
);
CREATE VIEW unclassified_source AS
SELECT date, ord, json_extract(warning_json,'$.line') AS line,
       json_extract(warning_json,'$.raw') AS raw,
       json_extract(warning_json,'$.resolution') AS resolution
FROM extraction_warnings
WHERE json_extract(warning_json,'$.interpretation')='unclassified_source_requires_factual_research';
CREATE TABLE generation_runs (
    id TEXT PRIMARY KEY,
    date TEXT,
    model TEXT,
    workflow TEXT NOT NULL,
    workflow_version TEXT NOT NULL,
    perspective TEXT NOT NULL CHECK(perspective IN ('contemporaneous', 'retrospective')),
    generated_at TEXT,
    input_identities_json TEXT NOT NULL,
    output_sha256 TEXT NOT NULL
);
CREATE TABLE event_claims (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES synthesis_events(event_id),
    ord INTEGER NOT NULL CHECK(ord >= 0),
    claim TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'reviewed', 'disputed')),
    review_note TEXT,
    UNIQUE(event_id, ord)
);
CREATE TABLE claim_evidence (
    claim_id TEXT NOT NULL REFERENCES event_claims(id),
    ord INTEGER NOT NULL CHECK(ord >= 0),
    relationship TEXT NOT NULL CHECK(relationship IN ('supports', 'disputes', 'context')),
    url TEXT NOT NULL,
    publisher TEXT,
    publication_date TEXT,
    locator TEXT,
    quotation TEXT,
    payload_sha256 TEXT REFERENCES archive_blobs(sha256),
    PRIMARY KEY(claim_id, ord)
);
CREATE TABLE editorial_sections (
    id TEXT PRIMARY KEY,
    scope TEXT NOT NULL,
    ord INTEGER NOT NULL CHECK(ord >= 0),
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'reviewed')),
    generation_id TEXT REFERENCES generation_runs(id),
    UNIQUE(scope, ord)
);
CREATE TABLE section_events (
    section_id TEXT NOT NULL REFERENCES editorial_sections(id),
    ord INTEGER NOT NULL CHECK(ord >= 0),
    event_id TEXT NOT NULL REFERENCES synthesis_events(event_id),
    PRIMARY KEY(section_id, ord),
    UNIQUE(section_id, event_id)
);
CREATE VIRTUAL TABLE archive_events_fts USING fts5(date UNINDEXED, category, text);
CREATE VIEW event_overview AS
SELECT e.date, c.name AS category, e.category_ord, e.ord, e.role, e.depth,
       e.text, s.page, s.revision_id, s.source_sha256, e.line,
       e.source_path_json, e.parent_path_json, e.raw
FROM extraction_entries e
JOIN extraction_categories c ON c.date=e.date AND c.ord=e.category_ord
JOIN sources_wikipedia s ON s.date=e.date;
CREATE VIEW event_citations AS
SELECT e.date, e.category_ord, e.ord AS entry_ord, j.key AS citation_ord,
       json_extract(j.value,'$.url') AS url,
       json_extract(j.value,'$.display') AS display,
       json_extract(j.value,'$.publisher') AS publisher,
       json_extract(j.value,'$.via') AS via,
       json_extract(j.value,'$.language') AS language,
       json_extract(j.value,'$.raw') AS raw
FROM extraction_entries e, json_each(e.citations_json) j;
CREATE VIEW event_links AS
SELECT e.date, e.category_ord, e.ord AS entry_ord, j.key AS link_ord,
       json_extract(j.value,'$.surface') AS surface,
       json_extract(j.value,'$.target') AS target,
       json_extract(j.value,'$.red_link') AS red_link
FROM extraction_entries e, json_each(e.links_json) j;
CREATE VIEW factual_review_queue AS
SELECT e.date,e.category,e.category_ord,e.ord,e.text,
       COALESCE((SELECT group_concat(r.assessment, '; ') FROM factual_reviews r
          WHERE r.date=e.date AND json_extract(r.locator_json,'$.category_ord')=e.category_ord
          AND json(json_extract(r.locator_json,'$.source_path'))=json(e.source_path_json)), 'unreviewed') AS scoped_findings
FROM event_overview e WHERE e.role='event';
CREATE VIEW review_queue AS
SELECT date, ord, json_extract(warning_json,'$.code') AS code,
       json_extract(warning_json,'$.message') AS message,
       json_extract(warning_json,'$.raw') AS raw,
       warning_json
FROM extraction_warnings
WHERE json_extract(warning_json,'$.resolution') IS NULL;
CREATE VIEW day_coverage AS
SELECT d.date,
       (SELECT count(*) FROM extraction_entries e WHERE e.date=d.date AND e.role='event') AS source_events,
       (SELECT count(*) FROM extraction_entries e WHERE e.date=d.date AND e.role='unknown') AS unknown_roles,
       (SELECT count(*) FROM review_queue q WHERE q.date=d.date) AS unresolved_warnings,
       (SELECT count(*) FROM synthesis_events s WHERE s.date=d.date) AS researched_events,
       (SELECT compiler_status FROM synthesis_days s WHERE s.date=d.date) AS synthesis_status
FROM extraction_days d;
CREATE VIEW source_text AS
SELECT i.path, i.date, i.role, i.sha256, b.media_type, CAST(b.payload AS TEXT) AS text
FROM archive_inputs i JOIN archive_blobs b USING(sha256)
WHERE b.media_type LIKE 'text/%' OR b.media_type IN ('application/json', 'application/yaml');
