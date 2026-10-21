-- book-1.0: researched history built on an annual archive edition.
-- The archive is referenced by SHA-256 and never modified. Rows are built
-- from the JSON records under book/<year>/ by book/tool.py.

CREATE TABLE book_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE chapters (
    id TEXT PRIMARY KEY,
    ord INTEGER NOT NULL UNIQUE,
    part TEXT NOT NULL,
    title TEXT NOT NULL,
    question TEXT NOT NULL,
    word_budget INTEGER NOT NULL CHECK(word_budget > 0),
    status TEXT NOT NULL CHECK(status IN ('planned', 'inventory', 'research', 'drafting', 'verifying', 'reviewed'))
);

CREATE TABLE sections (
    chapter_id TEXT NOT NULL REFERENCES chapters(id),
    ord INTEGER NOT NULL,
    title TEXT NOT NULL,
    span TEXT NOT NULL,
    PRIMARY KEY (chapter_id, ord)
);

-- Archive entries a chapter draws on, guarded by the archive's own locator
-- and structured hash (seed.annual_archive). Drift fails the build.
CREATE TABLE chapter_events (
    chapter_id TEXT NOT NULL REFERENCES chapters(id),
    archive_date TEXT NOT NULL,
    category_ord INTEGER NOT NULL,
    source_path_json TEXT NOT NULL,
    locator_json TEXT NOT NULL,
    event_sha256 TEXT NOT NULL,
    archive_text TEXT NOT NULL,
    section INTEGER,
    role TEXT NOT NULL CHECK(role IN ('core', 'context', 'excluded')),
    note TEXT NOT NULL,
    PRIMARY KEY (chapter_id, archive_date, category_ord, source_path_json)
);

CREATE TABLE sources (
    id TEXT PRIMARY KEY,
    tier INTEGER NOT NULL CHECK(tier BETWEEN 1 AND 4),
    kind TEXT NOT NULL,
    publisher TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    published TEXT,
    accessed TEXT NOT NULL,
    access TEXT NOT NULL CHECK(access IN ('opened', 'blocked', 'not_found')),
    note TEXT NOT NULL
);

-- What a source was used to establish, with a passage locator. Findings are
-- research notes; drafted prose cites claims, not findings.
CREATE TABLE findings (
    id TEXT PRIMARY KEY,
    chapter_id TEXT NOT NULL REFERENCES chapters(id),
    question_id TEXT NOT NULL,
    source_id TEXT NOT NULL REFERENCES sources(id),
    locator TEXT NOT NULL,
    finding TEXT NOT NULL,
    quotation TEXT
);

CREATE TABLE questions (
    id TEXT PRIMARY KEY,
    chapter_id TEXT NOT NULL REFERENCES chapters(id),
    section INTEGER NOT NULL,
    question TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('open', 'partial', 'answered')),
    answer TEXT NOT NULL
);

CREATE TABLE claims (
    id TEXT PRIMARY KEY,
    chapter_id TEXT NOT NULL REFERENCES chapters(id),
    section INTEGER NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('action', 'quantity', 'date', 'quotation', 'reaction', 'interpretation', 'hindsight')),
    claim TEXT NOT NULL,
    date_type TEXT CHECK(date_type IN ('announced', 'signed', 'published', 'effective', 'occurred')),
    status TEXT NOT NULL CHECK(status IN ('draft', 'reviewed', 'disputed', 'cut')),
    assessment TEXT CHECK(assessment IN ('supported', 'partially_supported', 'contradicted', 'unsubstantiated'))
);

CREATE TABLE claim_evidence (
    claim_id TEXT NOT NULL REFERENCES claims(id),
    ord INTEGER NOT NULL,
    source_id TEXT NOT NULL REFERENCES sources(id),
    relationship TEXT NOT NULL CHECK(relationship IN ('supports', 'disputes', 'context')),
    locator TEXT NOT NULL,
    quotation TEXT,
    PRIMARY KEY (claim_id, ord)
);
