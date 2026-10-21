# Source-preservation publication: `preservation-release-1.0`

Long-term preservation is the primary publication purpose. A source archive
may be released without independently checking every event. Exact preservation,
replayable extraction, attribution, disclosed source errors and explicit
research limits remain mandatory. This supersedes the exhaustive factual-check
gate in the embedded annual and draft yearbook contracts. Those historical
inputs and their reports remain unchanged; they do not govern this edition's
publication status. Neither a source citation nor publication certifies a fact.
Source selection is not guaranteed exhaustive or impartial.

The yearly publication pair is `archive/YYYY.sqlite` and `archive/YYYY.md`.
The database is authoritative; Markdown is a deterministic readable projection
of its exact file hash. PDF is a later interpretation of a named edition.
An archival chronicle can precede a fully researched historical yearbook.

This is an additive policy/publication contract, not an extraction schema
change. `annual-archive-1.1`, `extraction-1.0` and `yearbook-review-1.0` retain
their original meanings and immutable implementation inputs. Existing scoped
and full-event review states remain honest. Corrected editorial prose never
replaces source facts. Optional future research must use an explicit successor
edition and preserve earlier review records and implementation identities.

## Preservation and retirement manifest

One immutable `archive_inputs` record, role `preservation_publication`, stores
`publication/YYYY.json`. It identifies contract, year, edition, date, the prior
Git checkpoint, publication policy, known limits, retained shared sources and
an exact file manifest (repository path, role, SHA-256, byte length). Every
retired file has identical bytes in `archive_blobs`. Prior local extraction
candidates are also embedded before their filesystem duplicates are removed.
No full publisher articles or pictures are newly acquired by this operation.

Publication embeds versioned implementation bytes for `seed/archive_release.py`,
`seed/archive_access.py` and this contract. Changes require an explicit
successor migration; archived implementation bytes are never edited in place.
The manifest and all hashes are checked by publication verification, along
with full annual offline replay and editorial guards. All seven originally
uncited entries must have separate opened publisher evidence. Structural
warnings and unexplained content loss still block publication. Independent
research completion is reported separately and is not a preservation gate.

Retirement checks all remaining listed bytes before unlinking any file, and
confines paths to the selected year's daily/candidate trees and source cache.
It never recursively deletes a directory. Repeated retirement is idempotent.
Raw cache pairs referenced by other daily seeds, expansion caches or capture
pointers remain on disk. Exact retired bytes can be recovered from the database
or the recorded Git checkpoint. The published annual file is the default
source for its year. Shared cache infrastructure and other years are unchanged.

## Consumers and commands

`seed.archive_access` supplies original legacy bytes, pinned source metadata/
payloads and canonical extraction read-only from published annual editions.
Daily planning treats those dates as present, acquisition fails before network
access, and the writer refuses to recreate daily files. Offline replay and
expansion parsing use the annual source. Missing raw cache revisions can be
served from the annual database without requerying Wikipedia. Explicit custom
caches remain isolated; incomplete cache pairs are not silently bypassed.

```powershell
python -m seed.archive_release verify archive/2025.sqlite
python -m seed.archive_release render archive/2025.sqlite
```

The initial cutover uses `prepare` and `retire` after a Git checkpoint and
consumer verification. Preparation is staged through a sibling DB and installed
atomically; it does not alter source or prior research bytes. A source-only
rebuild must not overwrite a published edition. Retirement is limited to its
recorded manifest. The published Markdown includes every event once, explicit
review qualifications, original citations and known unclassified-source limits.
UTF-8, LF, one trailing newline and an exact database SHA-256 define its export
contract. Render verification creates no network/model calls or daily outputs.

The older `seed.yearbook` module remains the pinned draft renderer/review tool.
Use `seed.archive_release render` for preservation editions. Its publication
report distinguishes verified archival transfer from incomplete historical
research; legacy `replacement_ready=false` reports remain historical evidence,
not active exhaustive-check requirements.
