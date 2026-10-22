# Disclosed unverified claims: annual-series-1.3

Use `python -m seed.annual_unverified` for annual editions. This successor
implements preservation-release-1.1 and delegates existing editions to their
frozen implementations. Existing publication bytes and research states stay
unchanged. No acquisition policy, extraction schema or source prose changes.

Uncited Wikipedia assertions may be published unchanged without separate
evidence when explicitly disclosed as unverified. Independent corroboration is
optional further research, not a source-preservation prerequisite. This policy
was approved on 2026-10-22. It supersedes the outside-evidence prerequisite only
for editions explicitly selecting this profile. All calendar, exact-byte,
structural, warning, deterministic replay and retirement checks still apply.

Each uncited assertion without an existing editorial review requires a separate
`unverified-source-claim-1.0` JSON input, role `unverified_source_claim`, under
`research/unverified/`. It pins the existing stable review locator (source hash,
category, source path and raw-fragment hash) and complete event-record hash.
It records state `unverified`, an ISO recording date, workflow, generating model
(or null), a disclosure note, search status, and actual queries when searched.
Search status distinguishes `not_researched`, `research_incomplete`, and
`no_separate_evidence_found`; the last requires queries. Absence of found
evidence does not establish falsity. A disclosure must not imply an exhaustive
search. Invalid, duplicated, stale or unmatched locators fail verification.

Records are immutable; changed research requires an explicit supersession
migration or successor edition. Published editions cannot accept new records.
These records do not increment editorial review counts, satisfy independent
verification, or alter the frozen yearbook review report. The publication
report separately counts uncited assertions with editorial evidence and those
disclosed as unverified. Markdown includes the counts, each assertion and its
disclosure/search status before the chronology. Source wording stays unchanged.

New implementation and policy snapshots are embedded and checked. Historical
contracts, draft reports and their earlier factual gates remain preserved;
they describe their own editions and are superseded only within this profile.
