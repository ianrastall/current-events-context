# Guarded legacy projection reconciliation: annual-series-1.2

Use `python -m seed.annual_colon` as the annual dispatcher. This successor uses
isolated copies of the frozen 1.1/1.0 engines and delegates older editions to
their existing implementations. It changes no acquisition or extraction schema,
source bytes, list markers, factual prose, hierarchy or published annual bytes.

The November 18, 2014 source uses colon-prefixed lists. The frozen historical
flat parser emits no items for this source, whereas the saved seed contains 15
assertions. The structured extraction accounts for all 20 source list entries,
and its compatibility projection exactly matches every saved category and
assertion, including order and source errors. That is a disclosed, explained
baseline difference, not a successful replay by the older flat parser.

Each explicitly selected baseline rule pins date, exact source payload hash,
exact original daily-file hash and canonical structured-extraction hash. The
verifier also requires exact equality of the structured compatibility projection
and the original seed's categories. Missing, changed, duplicate, out-of-year or
unnecessary rules fail. Unguarded differences remain blockers. Partial-ingest
verification defers rules only for dates not yet ingested; complete-calendar
verification still checks every date.

The per-day `baseline_matches_legacy_replay=false` result remains unchanged.
The annual report separately lists `disclosed_legacy_projection_reconciliations`
and removes only proven dates from the unexplained-difference queue. No existing
review or original input is rewritten. This module, contract and per-year
configuration are embedded and hash-checked under the 1.2 profile. It must never
be retroactively applied to earlier annual editions.

The readable projection also appends citations attached to non-event topic
headers, with their dates and exact source lines. Earlier renderers displayed
topic ancestry but omitted these header citations. Assertion text, topic roles
and original citation records remain unchanged. Unpublished candidates may
adopt this profile only through an explicit migration retaining their earlier
databases and research records; published editions are not silently upgraded.
