# Declarative annual preservation profiles: annual-series-1.0

This implementation extends the approved annual source-preservation workflow
to successive years. The annual database, extraction and publication schemas
retain their existing versions. Earlier annual implementations and artifacts
remain immutable. Use `python -m seed.annual_series` as the current dispatcher;
it delegates 2024/2025 to their pinned implementations without changing bytes.

Each new year has one checked-in configuration,
`reference/overrides/YYYY-series.json`. It records an explicit edition date,
source-hash/fragment/category/path guarded role interpretations and source
notice resolutions. Configuration and full implementation/renderer snapshots
are embedded in the database and checked during verification. Contexts select
the declared profile only for single-threaded annual operations; they restore
the original engine on exit. Source acquisition is outside this offline layer.

The standing user-approved handling for structurally ambiguous bare topic
labels is to preserve them as flagged orphan topics, without inventing child
events or parents. Nominal labels with actual indented children are explicit
guarded topics. Unbulleted prose remains unclassified source evidence and a
research lead, with exact raw text and source location. Other unsupported
structures require inspection and an explicit guarded handling decision.

Source depth gaps, empty markers, orphan categories and malformed source markup
remain present with notices. Recognized template displays use literal input
amounts/units, currency labels, spacing and punctuation. There is no exchange
rate, computed counterpart, redirect inference or network template expansion.
Unrecognized templates may be retained verbatim through an explicit source
notice; citation-needed/reliability tags must remain visible, not be erased.

An explicitly approved complete source sentence can be an event even when the
frozen parser marked it unknown; its nesting is preserved, and the candidate
comparison records the assertion-count change. The January 14, 2022 earthquake
sentence is an approved example. Such overrides require
`interpretation: approved_source_statement` and the complete guarded locator.

Real parsed HTML comments identify commented-out entries deterministically.
These retain raw input, text, links, citations, source paths and ordering as
`unknown` non-event material, with a resolved `SOURCE_COMMENTED_ENTRY` notice.
They appear in source handling notes and are excluded from the ordinary event
tally. The profile verifier accounts for these known non-events separately
from unresolved unknown headings, analogous to the existing empty-marker
exception. It removes no actual warning or unexplained unknown-role blocker.
Candidate comparison permits only these proven comment-role changes and the
explicitly approved statement interpretations, recording every delta. The
source-bullet census still includes the preserved commented entries.

A guarded bold category heading followed by a comment can be recognized as a
category. Its raw heading/comment remains exact. Category-relative paths of
affected entries are rebuilt from their actual depth; prior-candidate comparison
normalizes only the declared category/path repair and separately records it.
All raw entries, order, links, citations and original assertions must survive.

Publication requires complete calendar coverage, no unresolved interpretations,
all prior candidate/source differences reconciled, exact-byte preservation and
separate editorial evidence for original uncited assertions. Exhaustive factual
checking remains optional. A partial review never approves unsupported clauses.
Publisher articles are not automatically captured. Original facts remain intact.

Preparation copies into a sibling staged database, embeds original candidates,
checks shared-cache dependencies and writes an immutable publication manifest.
Its date comes from the pinned year configuration. Retirement uses the original
guarded release engine and exact-file preflight; only listed byte-matched files
are unlinked. Shared inputs remain. Markdown is deterministic UTF-8/LF, identifies
the exact database hash, preserves all event prose/citations, and discloses
source handling and factual limits. It adds no PDF work or daily output layer.

```powershell
python -m seed.annual_series build 2023 --output provisional/2023-preservation.sqlite
python -m seed.annual_series verify provisional/2023-preservation.sqlite
# Record scoped editorial evidence, then prepare and review the yearly pair.
python -m seed.annual_series prepare provisional/2023-preservation.sqlite
```

Before each year: fetch/pull the active branch without overwriting concurrent
work, inspect existing data/provenance and preserve the prior Git checkpoint.
Before cutover: verify the complete pair and every proposed removal. After
cutover: replay from embedded inputs, check Markdown and consumers, run tests,
commit and push the year's scoped changes, and verify CI. A tagged GitHub
release may distribute the committed SQLite/Markdown pair with SHA-256 sums.
Releases identify source-preservation status and incomplete independent review.
They do not imply that a separate PDF production is complete.
