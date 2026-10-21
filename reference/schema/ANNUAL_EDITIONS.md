# Successor annual source profiles

The annual container remains `annual-archive-1.1`, extraction shape remains
`extraction-1.0`, and publication remains `preservation-release-1.0`. This
additive implementation profile changes neither the pinned revision policy nor
the factual-review policy. The original modules/contracts and published 2025
SQLite/Markdown remain unchanged and reproducible. New profiles are explicit
metadata (`archive_metadata.extraction_profile`), with complete immutable
implementation, override and renderer snapshots inside their annual database.

Use `python -m seed.annual_editions verify archive/YYYY.sqlite` and `render`
for current annual editions. Unprofiled 2025 delegates to its frozen original
publication implementation, including its original Markdown bytes. The frozen
low-level `seed.annual_archive`/`seed.archive_release` commands alone do not
select successor profiles. Compatibility consumers retain their existing
publication contract and read stored canonical extraction/source bytes.

## `preservation-extraction-2024-1.0`

Approved for the leap year 2024 only. Existing exact recorded revisions and
source bytes are authoritative. Network access is forbidden during building and
replay. Original daily seeds, metadata, provisional candidates, source ordering,
list depth, wikilinks, external citations and original errors are retained.

Additional template projections display literal source amounts/units, ranges,
ship-name arguments, railway-station labels, chemical formula arguments and the
explicit Mww scale label. No counterpart measurements, exchange rates, target
redirects or template-generated facts/links are inferred. Unsupported templates
remain verbatim with unresolved warnings. Source templates retain audit notices.

Two exact bare labels (January 27 and May 5) are user-approved orphan topics.
Their source-hash/fragment/path-guarded role overrides live in
`reference/overrides/2024-extraction.json`. Orphan notices remain visible in the
database and Markdown; following events stay at actual source depth and acquire
no inferred parent. Four depth gaps retain their original structure. An
unmatched closing wikilink delimiter on February 23 remains verbatim.

On February 26 the literal bold `Law and crime` heading is immediately followed
by an HTML comment. The successor recognizes this explicit category and retains
the complete heading/comment. Its one original following bullet moves from the
frozen parser's incorrect International relations category to this category;
prose, depth, links and citations are unchanged. Category-relative path becomes
`[1]`; absolute source line and raw fragment retain its stable source identity.
Every other bullet and category remains ordered. Prior candidate comparison
records this exact category/path repair and rejects event/evidence changes.

All eight exceptional source notices have hash-, line-, category- and path-
guarded resolutions in `reference/overrides/2024-preservation.json`. Drift fails;
no nearest-looking match or manual edit to generated output is allowed.

The implementation uses scoped compatibility contexts around the frozen annual
engine. Run these annual operations in a single-threaded process. Contexts are
restored on exit and are never applied when verifying the unprofiled 2025
edition. The successor verifier checks all original snapshots plus all profile
snapshots, full offline replay/idempotence, structural reconciliation and prior
candidate differences before publication or retirement.

The year-appropriate Markdown front matter discloses actual event/date/review
counts and all exceptional source handling. It does not copy 2025-specific
football fragments or source errors into 2024. Independent checks are limited
to explicitly recorded editorial findings; publication does not certify the
remaining events. Uncited original entries require separate opened evidence,
with unsupported details remaining explicitly partial.

Build beside existing files, then verify and prepare before cutover:

```powershell
python -m seed.annual_editions build 2024 --output provisional/2024-preservation.sqlite
python -m seed.annual_editions verify provisional/2024-preservation.sqlite
```

After recording separate editorial evidence, `prepare` embeds prior candidates
and an exact dependency-checked retirement manifest using the frozen release
engine. Verify the new Markdown and consumer recovery before `retire`. Only
listed, byte-matched files may be removed; shared source inputs remain on disk.
The final public pair is `archive/2024.sqlite` and `archive/2024.md`. PDF and
other derivative work is outside this migration.
