# Unheaded source categories: annual-series-1.1

This successor profile uses the frozen annual-series-1.0 implementation with
an isolated module namespace and one guarded comparison adapter. Published
1.0, 2024 and 2025 inputs and output bytes remain unchanged. The current CLI
dispatcher is `python -m seed.annual_legacy`; verification and rendering
delegate earlier editions to their existing pinned implementations.

A source bullet can occur before any actual category heading. Its category
has a null name, absent raw heading and absent category line number. Preserve
these absences, the source bullet location, source ordering and parentless
relationship. Do not invent a heading, line number or source role. Empty
markers remain separately labeled non-events under the existing parser rule.

The old comparison indexed a required category line and failed on this valid
absence. The adapter allows matching absence only on both corresponding
unnamed, unheaded categories. It supplies a null sentinel in comparison copies
only, recording the category indexes in the reconciliation report. Canonical
extraction, raw sources and baseline records remain unchanged. A one-sided
missing location, named category or unexplained raw heading is rejected.

The annual database/extraction/publication schemas retain their existing
versions. Per-year configuration, this adapter, this document and all frozen
implementation inputs are embedded and hash-checked. Offline replay, source
coverage, exact-byte retirement and separate editorial-review requirements
are unchanged. The March 23, 2017 exact fixture exercises an empty source
marker before the first heading and verifies that no location is invented.
