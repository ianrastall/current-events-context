# Consecutive citation reconciliation: annual-series-1.5

Use `python -m seed.annual_continuations` as the annual dispatcher. Earlier
profiles delegate to their frozen implementations unchanged. This successor
uses the unchanged 1.3 publication protocol, as profile 1.4 does. The database
extraction profile and implementation namespace independently identify 1.5.

The existing extractor already attaches consecutive adjacent citation-only
lines to their preceding source bullet and preserves one warning per line.
The historical candidate comparator accepts only one such appended warning
fragment. This successor reconciles two or more consecutive lines without
changing extraction, source bytes, citation order, source roles or schema.

Each configured `citation_continuations` rule pins date, source hash, category,
source path, source line and complete old/new extraction-entry hashes. Every
appended line must have one exact matching prior UNSUPPORTED_CONTENT warning
and one current deterministic CITATION_CONTINUATION warning at its consecutive
source line. Duplicate, stale, nonmatching or unnecessary rules fail. A
comparison-only aggregate allows the frozen lossless comparator to check the
whole suffix; separate stored warnings and all entry fields remain unchanged.
The retained reconciliation report discloses each original line and its hash.

Source adjacency records placement, not independent corroboration. On December
28, 2010, the two citation-only lines after the train sentence include a NOLA.com
URL about building-code fines; preserve its source placement without endorsing
its relevance to the train claim. July 9, 2009 similarly has two adjacent citation
lines. No publisher contents were acquired to certify these assertions.

Publication still requires all original structural, calendar, source-coverage,
lossless transfer, offline replay and unverified-claim disclosure checks.
