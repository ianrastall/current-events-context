# Archival extraction migration

This plan prepares a separate candidate tree. It does not replace published
daily paths or imply approval of a final public schema.

## Existing contracts

Legacy daily files use `Date`, `Source_URI`, `Intelligence_Payload`. Local seed
files use `date`, `source_page`, `wikipedia.categories` and optional `gdelt`.
Both flatten lists. Synthesis schema 2.2 is a separate contract and remains
unchanged. Published January synthesis is preserved under `expanded/` with
an exact authored-input replay path.

## Candidate extraction contract 1.0

Candidates live in a caller-selected output directory, never ordinary day
paths. Each file has `schema_version: extraction-1.0`, `date`, `source_page`,
ordered `categories`, and `warnings`. Existing GDELT data, if present, is
carried through as the same parsed value without a query.

`source_page` contains page, revision ID/timestamp, source mode and SHA-256.
Null timestamps mean unavailable. Rendered sources are explicitly identified
and do not have the reproducibility guarantees of raw wikitext. Unknown
red-link state remains null. Link targets are preserved as written.

Categories have a name (null before any category) and ordered entries in
source preorder. Category headings also preserve structured links and citations,
and unsupported heading markup produces a warning. Entries contain a role
(`topic`, `event`, `unknown`), actual
depth, original list marker (`*`/`:` or their sequence), source list path, parent path (null for root), original line/raw
fragment, rendered text, structured wikilinks and external citations.
Container entries remain distinct from event leaves. Empty headers remain
present with a warning. Unsupported or ambiguous material remains raw with
a warning; no model classifies it. Source order is authoritative.

Warnings include date, exact source identity, category, source path, raw
fragment, code, interpretation and message. Overrides must guard the payload
hash, path and raw-fragment hash; mismatches fail. A warning resolution belongs
in a general parser rule or an explicit guarded override.

## Replay and serialization

Acquisition stores exact UTF-8 payloads, timestamp and hash under
`reference/sources/wikipedia/`. Entries are immutable and hash-verified on
read. Existing recorded oldids are used for acquisition; uncached inputs fail
offline replay instead of querying current pages. New captures cache the
current revision once. Monthly rendered fallback is cached and identified
separately; existing null-revision seeds require an explicit acquisition policy
and are never silently assigned a current oldid.

For the 58 unpinned daily files from August 7 through October 4, 2026, the
selected policy is to capture current revisions as explicitly new inputs.
`cache --capture-unpinned` records these in `current-captures-report.json`;
the original daily files and their publication identities remain preserved.
These captures cannot establish what the original collector saw. Differences
against those legacy files therefore include source revision changes as well
as parser changes. This choice does not cover missing historical monthly days.

Candidates use UTF-8, LF, preserved mapping/sequence order and one trailing
newline through pinned PyYAML. Tests compare bytes and canonical structures.
GDELT is never called by replay. Extraction candidates do not contain model
prose or synthesis from `expanded/`.

## Replacement gate

Before publication or replacement: golden fixtures and offline replay must
pass; every relevant bullet must be accounted for; event leaves and every
content delta must be reconciled against pinned source, the preserved local
baseline and published output. Verify each historical format era. Report
uncached dates, unresolved warnings and legacy provenance exceptions. Agree
the final public layout/schema and exact replacement range. Bulk acquisition
and full-corpus replacement are distinct operations, not side effects of tests.


For comprehensive replay checks, pass `reparse --verify`: each exact input is
parsed twice, serialized bytes are compared, and a canonical structure is
compared after YAML round trip. The corpus report maps every legacy emitted
item to its source line and candidate role, records event leaves and containers,
and independently checks source list locations. Flat-to-structured count
changes are reconciled by role promotion and legacy omissions, not assumed
to represent deleted events. Unknown roles remain an explicit review queue.
