# Annual reference archive (`annual-archive-1.1`)

## Decision and scope

The approved destination is one self-contained SQLite file per calendar year,
`archive/<YYYY>.sqlite`. Daily ingestion is incremental; an annual file does
not require an annual model session. No permanent daily export files are
required. Markdown, JSON and yearbook PDF are downstream views, not additional
authoritative corpora. The first migration is 2025.

This is a new, explicitly versioned container contract. The existing
`extraction-1.0` and synthesis `2.2` contracts retain their meanings. The
existing per-day SQLite implementation is a compatibility bridge, not the
annual publication contract. Legacy daily files remain authoritative until
the replacement gate below passes. Nothing in this decision approves factual
claims, silently changes a pinned revision, or marks imported work reviewed.

## Contents and data dictionary

The executable schema is the combination of `seed.sqlite_archive.DDL`, its
FTS schema and `reference/schema/annual-archive.sql`. Copies of these schemas,
this contract and the extraction JSON Schema are embedded in each database.

| Tables or views | Meaning |
|---|---|
| `archive_metadata` | Annual contract version, calendar year, source Git commit, pipeline fingerprint and explicit source/review policies. |
| `archive_blobs` | Exact input bytes, keyed by SHA-256; UTF-8 where applicable. Includes source payloads, original daily files, cache metadata and implementation/schema evidence. No hand edits to immutable inputs. |
| `archive_inputs` | Original repository path, optional date, input role and payload hash. Several paths can refer to one blob. Original YAML is preservation evidence inside the database, not a second filesystem output. |
| `sources_wikipedia`, `extraction_*` | Pinned page/revision/timestamp/hash, ordered categories, topic/event/unknown roles, raw fragments, source/parent paths, wikilinks, citations and regenerated warnings. Existing bridge round-trips the extraction contract without changing it. |
| `gdelt_enrichment` | Optional existing GDELT block, carried through without fetching or promoting feed clusters to researched facts. |
| `raw_sources`, `structured_feed_items` | Compatibility tables for separately identified external feeds. Annual v1 does not automatically acquire or import unrelated feeds. |
| `day_ingestions` | Input identities, canonical extraction hash, prior candidate comparison and source-bullet/leaf reconciliation. This is acquisition/extraction verification, not factual review. |
| `factual_reviews`, `review_evidence` | Scoped publisher findings with exact source/event guards, access outcomes, dates and evidence notes. A checked claim never marks a whole day or year reviewed. Original records are immutable embedded inputs. |
| `unclassified_source` | Malformed source passages preserved without guessing an event role. They remain factual research leads after their extraction handling is resolved. |
| `synthesis_*` | Researched events: headline, summary, date/time, importance/tier, topics, actors/entities, geography, quantities/casualties, explanations, uncertainty, sources, quotations, bibliography and related-event IDs. Empty until researched inputs exist. |
| `generation_runs` | Model, workflow/version, input identities, historical perspective, output hash and optional timestamp for a synthesis operation. Unknown historical generating models remain null. |
| `event_claims`, `claim_evidence` | Explicit claim text and supporting/disputing evidence, source URL, publication date, locator, exact quotation and factual review status. Evidence can reference an archived payload; URLs alone do not imply a cached publisher article. |
| `editorial_sections`, `section_events` | Ordered monthly/thematic/yearbook prose, event links, scope, generation provenance and draft/reviewed state. Never written into extraction. |
| `event_overview`, `event_citations`, `event_links`, `review_queue`, `day_coverage` | Browseable views for ordinary database readers; ordered source events, individual citation/link fields, unresolved warnings and per-day research coverage. |
| `source_text` | Exact UTF-8 archival inputs exposed as readable text without requiring BLOB extraction. |
| `archive_events_fts`, `synthesis_events_fts` | Rebuildable text search indexes. Search does not confer factual confidence. |

## Identity, ordering and semantics

Dates are ISO calendar dates; each annual file accepts only its own year.
Source revision timestamps can be later than the event date. A retrospective
capture is not evidence of what was known on that date. Source errors remain
verbatim. Corrected or independently researched statements belong in synthesis.

Sequence order is explicit (`ord`); SQL views require an explicit `ORDER BY`
when read. Source locators contain date, page, pinned revision/payload hash,
category, source path and raw fragment. Ordinals alone are not override IDs.
Null means unknown/not supplied; zero, empty string and empty list retain
their distinct meanings. Red-link state is unknown without revision-aware
evidence. Categories, topic headers and events remain distinct roles.

Synthesis uses globally unique event IDs and may reference another year's ID;
cross-year references must be checked when publishing a collection. Claims and
yearbook sections default to draft. Generation metadata distinguishes
`contemporaneous` from `retrospective`; later knowledge must be identified.
Completeness is assessed through source coverage and recorded exclusions, not
an event-count quota. No GDELT-scale feed expansion is required.

## Incremental workflow and reproducibility

`python -m seed.annual_archive build 2025` writes a temporary sibling database,
ingests one date per transaction, verifies the full result, then atomically
replaces the destination. A failed build preserves an existing archive.
`ingest-day archive/2025.sqlite 2025-01-01` demonstrates bounded, restartable
daily ingestion. Exact repeated inputs are idempotent; changed inputs require
an explicit migration rather than replacement by proximity or current source.

The builder is offline. It reads only recorded revisions from the immutable
cache and preserves old files as exact bytes. Verification reparses embedded
payloads with network connection attempts blocked, without needing the source
tree. Complete-calendar coverage, hashes, structure, ordering, schema validity,
canonical round trip, source bullet locations, legacy trace mapping, GDELT
preservation and search counts are checked. Prior candidate differences are
reported, never silently accepted as proof of correctness.

Canonical structured hashes use UTF-8 JSON, sorted mapping keys, preserved
array order, no insignificant spaces and no ASCII escaping. Exact input hashes
use original bytes. SQLite physical bytes are not promised identical across
library versions, VACUUM operations or equivalent insertion histories.

## Replacement and yearbook gates

Migration reports live in `archive_checks` inside the database. Verification
prints a compact report; permanent per-day report files are unnecessary.

Deleting the old 2025 filesystem material requires:

1. All 365 dates verified from exact pinned inputs, including exact preservation
   of every proposed deletion and comparison to the previous candidate output.
2. No unresolved structural warnings, unknown roles or unexplained baseline
   differences; a general parser rule or guarded override resolves ambiguity.
3. A recorded factual/coverage review of the intended reference edition.
   Schema validity and lossless migration alone are not a factual review.
4. An exact, dependency-checked deletion manifest and preserved Git checkpoint.
   Shared source caches cannot be removed merely because 2025 embeds a copy.
5. Updated consumers and documentation, followed by a side-by-side review.

An unreviewed source-complete archive may be retained as a candidate, but it is
not a yearbook-ready edition and does not authorize deletion. Yearbook
readiness additionally requires reviewed synthesis and citations, reviewed
editorial sections and cross-event reconciliation. A PDF is generated from a
named archive edition/hash, with source references and recorded generation
inputs; PDF design is outside this initial storage migration.

The self-contained inputs permit migration recovery without Git, but Git
remains useful for code/schema review and historical preservation. Wikipedia
payloads retain attribution and CC BY-SA obligations. Store acquisition/license
information with each new source; do not imply rights to publisher full text.

## Version 1.1 migration and review scope

The 1.0 baseline is preserved outside the working tree. Build 1.1 to a separate
candidate path and compare every source entry before replacing the annual
candidate. No legacy daily paths or immutable caches are removed. The
extraction-1.0 shape is unchanged. The annual container adds scoped factual
review/evidence tables and an unclassified-source view; version 1.0 is not
silently relabeled. Existing research must be explicitly migrated, never
discarded by a source-only rebuild.

Recognized inline templates project only their explicit source arguments.
This is the annual builder's explicit `source_templates=True` extraction
profile. Existing seed/synthesis callers retain their prior default profile;
historical positional-overlay hashes are not refreshed to bypass drift guards.
Computed unit counterparts, live currency conversions, template-implied
redirects and historical red-link state are not inferred. Resolved source
notices preserve exact markup and the projection policy. Topic interpretations
and unclassified passages use source-hash/fragment-hash guarded overrides in
`reference/overrides/2025-extraction.json`. A role override cannot resolve an
unrelated markup or reliability warning.

The approved May 6 malformed football passage, including content accidentally
parsed as extra portal parameters, remains unclassified evidence. No sports
category or source event is invented. Publisher research may establish a
separate synthesis event later. Source reliability tags remain visible to
factual review after their extraction representation is resolved.

`coverage_report()` produces a complete-calendar census with missing citations,
category/month counts, source annotations and remaining publisher-review
counts. This measures the existing source collection; it cannot establish
that Wikipedia covered every significant event. Publisher observations record
their claim scope and accessibility; failed access is not evidence of falsehood.
Retrospective or changing casualty figures require explicit reporting times.
Factual discrepancies become editorial review findings, never silent edits of
source text. No number of sample checks approves the rest of the year.

A literal empty bullet is preserved with the existing `unknown` role and a
resolved `SOURCE_EMPTY_MARKER` notice. It is a known empty marker, not an
ambiguous heading or an event assertion. It is excluded from event/search
counts. Verification reports empty markers separately from unknown headings;
the side-by-side event delta must explicitly account for their removal from
the old event tally. No nonempty source entry may use this exception.
