# Annual Markdown companion and independent event review

The selected pair is `archive/<YYYY>.sqlite` and `archive/<YYYY>.md`.
The Markdown is a generated, readable interpretation of a named database
edition. It is not an independent authoritative collection. Until research
is complete it is explicitly a draft reference preview, not a finished book.
An illustrated PDF is deferred. A text PDF can follow the reviewed Markdown;
images are not a prerequisite for the storage migration.

## Cutover decision

Every event must be independently checked before the old daily files are
retired. Sampling, attached Wikipedia URLs and earlier scoped checks do not
satisfy this requirement. The annual archive's other replacement and yearbook
gates also remain in force. A commit preserves a candidate; it does not approve
cutover. No original daily files or source caches are removed in this pass.

## Additive editorial record contract: `yearbook-review-1.0`

This contract uses existing `archive_inputs` and `archive_blobs` tables in
`annual-archive-1.1`. It does not alter those tables, reinterpret extraction,
or replace historical parser implementation snapshots. Editorial records have
role `yearbook_event_review`, logical path `yearbook/reviews/<id>.json`, and
the original source date. Exact UTF-8 JSON bytes are immutable embedded inputs.
No permanent per-event review files are required on disk.

Each record contains:

- `contract`, safe `id`, the existing stable factual-review `locator`, and
  `event_sha256` over the complete `event_overview` row. Source or extraction
  drift fails; a nearby item is never substituted.
- ISO `checked_on` and `display_date`; the latter may differ from the original
  portal date. Cross-year moves require a separate explicit migration.
- `state`: `complete` or `partial`, `statement` and an explanatory `note`.
  Complete means the entire original event has been assessed using independent
  evidence and every assertion has a disposition. It does not mean that every
  original assertion was true. Unsubstantiated assertions force partial state.
- `dispositions`: ordered contiguous character spans (`start` inclusive,
  `end` exclusive) covering the complete original event text. Each gives
  `assessment` (`supported`, `contradicted`, `unsubstantiated`, `wording`),
  an explanatory `note` and zero-based indices into `evidence`. A single
  source supporting one figure cannot silently approve unchecked clauses.
- `evidence`: opened public HTTP(S) URL, publisher, publication date or null,
  `access_status=opened`, passage locator and a factual support/limit note.
  These are recorded observations; validation cannot prove the research was
  done or that a claim is true. Publisher text is not automatically cached.
- Generating `model` (null if unknown), `workflow` and retrospective
  `perspective`. Model-authored interpretation remains separate from extraction.

`seed/yearbook.py` and this contract are embedded under versioned
`yearbook/implementation/` paths. Verification compares them to the active
implementation. Future implementation changes need an explicit versioned
migration; do not replace archived bytes. Multiple competing resolutions for
one source entry are rejected pending an explicit supersession design.

`review_report()` distinguishes complete event reviews, partial reviews,
unreviewed events and independent evidence for the original uncited entries.
Original missing-citation counts do not drop when editorial sources are added.
The report never automatically approves deletion or a finished yearbook.

## Commands and serialization

```powershell
python -m seed.yearbook queue archive/2025.sqlite --month 2025-01 --limit 10
python -m seed.yearbook record archive/2025.sqlite <temporary-review.json>
python -m seed.yearbook verify archive/2025.sqlite
python -m seed.yearbook render archive/2025.sqlite
```

`record` reads a prepared research record; it does not acquire data. Research
must open and inspect publisher evidence first. The queue supplies guarded
identities, original wording and archived citation URLs for incremental work.
Previous scoped findings remain separately available in `factual_reviews`.

`verify` checks the original annual contract offline and all editorial guards.
`render` also verifies first, opens the DB read-only and atomically writes
UTF-8 Markdown with LF and exactly one trailing newline. It creates no daily
outputs, uses no network or model calls, and records the exact database file
SHA-256. Rendering the same edition twice produces identical bytes. Close
database writers before rendering; SQLite WAL/journal files are rejected.

All original event assertions appear once, in source date/category/order,
including assertions with corrected editorial dates. Original source dates
remain the navigation anchors; editorial dates are explicit. Topic ancestry
comes from source paths. Original citations and newly researched citations
are labeled separately. Partial and unreviewed accounts are visibly labeled.
HTML/Markdown source text is escaped so markup cannot masquerade as review
labels or executable embedded content. Known empty markers are excluded;
unclassified fragments are disclosed and remain in the database.

The database retains source errors verbatim. A researched statement may narrow
an unsupported assertion, but its original claim stays partial until the
remaining uncertainty is independently resolved. Source coverage is not proof
that all historically significant events were included. Cross-event deduplication,
thematic essays and a final editorial reading are further yearbook work.
