# AGENTS.md

Project-scoped instructions for `current-events-context`.

This file contains durable rules. Current defects, migration state, inspection findings, and in-flight work belong in `HANDOFF.md`.

## Project purpose

`current-events-context` builds structured day-by-day current-events archives for use as LLM context. The supplied collection code combines Wikipedia Current Events material with optional GDELT news enrichment in per-day YAML seed files.

The archive and enrichment layers have different provenance and reproducibility properties. Do not treat them as interchangeable.

## Confirmed project facts

The following facts are confirmed by the supplied `seed` code. Inspect the repository before filling any fact not listed here.

| Fact | Confirmed value |
|---|---|
| Project name | `current-events-context` |
| Primary language | Python |
| Collection package | `seed` |
| Documented CLI | `python -m seed` |
| CLI commands | `date`, `plan`, `range`, `cache`, `reparse` |
| Wikipedia collector/parser | `seed.wikipedia` acquisition; `seed.extract` / `seed.rendered` extraction |
| GDELT collector | `seed.gdelt` |
| Seed document builder/writer | `seed.merge` |
| Rate-limit handling | `seed.ratelimit` |
| Git batch helpers | `seed.gitops` |
| Range-run reports | `seed.report` |
| Seed output path | `<repo>/<YYYY>/<MM>/<YYYY-MM-DD>.yaml` |
| Current Wikipedia result shape | `dict[str, list[str]]` categories/events |
| Current seed content | Wikipedia block plus optional GDELT block |
| Current Wikipedia fetch | MediaWiki API by page title; returns the revision current at fetch time |
| Persistent raw-source cache | Immutable payload/metadata pairs under `reference/sources/wikipedia/`, verified by hash |
| Existing expansion source cache | `reference/expansion/wikitext/`; imported without changing raw bytes |
| Pre-2004 fallback | Rendered monthly-page HTML; `wikipedia_revision_id` is currently `null` |
| Python libraries visibly required | `requests`, `mwparserfromhell`, `PyYAML`, `jsonschema`; direct versions in `requirements.txt` |
| External executable visibly required | `git` for `--commit` / `--push` workflows |

The supplied code references `daily-events.schema.json` and a "schema-2.2 rework" stage. That schema and any broader repository plan must be inspected before changing the output contract.

Still inspect and record: repository layout, packaging/build metadata, exact `__main__` wiring, dependency lock/requirements files, tests, lint/format commands, GitHub Actions workflows, corpus date range, published-output status, schema files, summary-generation code, and any cache or override machinery elsewhere in the repository.

## Pipeline layers

Keep these concerns separate even if the current seed YAML stores more than one of them together.

### 1. Source acquisition

Network access belongs here.

Acquisition obtains an exact source payload and provenance sufficient to identify it later. A source payload must be cacheable before parser iteration is considered complete.

### 2. Wikipedia extraction

Extraction is a deterministic transform of one exact Wikipedia source payload into structured archival data.

No model judgment belongs in this layer.

### 3. GDELT enrichment

GDELT is external enrichment, not part of the Wikipedia source hierarchy. Current GDELT results are not revision-pinned and include a query timestamp. Do not let a Wikipedia parser rewrite silently refetch or replace an existing GDELT block.

### 4. Synthesis

Monthly summaries and any long-form/deep-research snapshots are synthesis artifacts. Model-authored content is acceptable there and should record its generating model and source inputs.

Never write synthesis content back into an extraction artifact.

## Wikipedia extraction invariants

These rules define the target behavior for daily Wikipedia extraction.

1. Parse from raw wikitext whenever raw wikitext exists. Do not prefer rendered HTML merely because it is easier to scrape.
2. Preserve actual list depth. Do not assume exactly two levels and do not flatten parent/child relationships into sibling strings.
3. Represent topic headers and events as different structural roles.
4. Represent an event with no topic header explicitly as parentless; do not infer a parent from proximity.
5. Preserve category and event ordering as it appears in the source.
6. Preserve wikilinks as structured records containing at minimum surface text and target-as-written. Do not destroy them with `strip_code()` before they are captured.
7. Preserve external citations as structured records. Capture the URL and the displayed source/publisher text before markup stripping. Split syndication and language annotations into fields only when the source supports that interpretation.
8. Preserve source text and source errors. This is an archive. Do not silently correct names, spelling, grammar, or facts found in the source.
9. Store link targets as written. Redirect resolution, Wikidata IDs, entity typing, and similar enrichment belong in separate fields or sidecars.
10. Do not infer historical red-link state from wikitext. Raw wikitext does not encode whether a target existed at that revision. Record red-link state only if it is acquired from revision-aware metadata; otherwise leave it unknown.
11. Retain source provenance sufficient to identify the exact input: page title, revision ID when available, revision timestamp when obtainable, source mode, and a stable payload hash.
12. A parser must not silently discard unrecognized structural content. Emit a structured warning with source location and raw input.

## Revision policy and source cache

The target architecture separates acquisition from parsing.

### Existing daily pages with a recorded revision ID

For migration, treat the `wikipedia_revision_id` already stored in an existing seed file as the default pinned source revision unless repository documentation or the user explicitly selects another policy.

Fetch that exact `oldid` once, cache its raw wikitext, and reparse from the cache. Do not refetch the page's current revision merely to perform a parser rewrite.

### New daily captures

A new capture may query the page current at capture time. Once obtained, record its revision metadata and cache the exact raw payload. Later parser iterations must use that cached payload or the same explicit revision, not current page state.

### Legacy monthly fallback

The supplied pre-2004 path parses rendered monthly-page HTML and stores a null revision ID. That is a known provenance gap.

Prefer replacing it with a revision-pinned raw-source path if the historical page structure makes that possible. If rendered HTML is genuinely required, cache the exact rendered payload and record enough provenance to distinguish it from raw-wikitext extraction. Do not pretend it has the same reproducibility guarantees as a pinned wikitext revision.

### Cache requirements

The persistent source cache is immutable input, not generated output to be edited.

- Key cached Wikipedia inputs by stable source identity, including revision ID where available.
- Store a hash of the exact cached payload.
- Re-extraction must run with network access disabled.
- Parser tests and full reparse runs must not mutate cached inputs.
- If a cached payload is believed to be wrong, reacquire it through the acquisition path; never hand-edit it.

## GDELT reproducibility

The current collector queries GDELT at run time, and the resulting block contains `queried_at`. Therefore whole-file byte-for-byte reproducibility is not currently guaranteed when GDELT is refetched.

For the Wikipedia extraction migration:

- preserve an existing GDELT block rather than requerying GDELT;
- do not make parser correctness depend on GDELT availability;
- if GDELT is later made reproducible, cache the exact acquisition input or otherwise define and document a deterministic replay contract.

The known `artlist` limitation around missing GDELT themes is separate from the Wikipedia extraction rewrite unless explicitly brought into scope.

## Generated files and manual corrections

Generated daily seed/snapshot files are outputs. Do not hand-edit them to repair parser behavior.

Manual corrections must live outside generated output and survive regeneration.

Overrides are for extraction interpretation, not for silently correcting Wikipedia's facts or prose.

Do not key overrides only by a flat list position. Positions can move when hierarchy is repaired. An override locator should include enough stable source identity to detect drift, for example:

- date;
- revision ID or source payload hash;
- category or source section;
- source bullet/list path;
- raw-fragment fingerprint.

If an override locator no longer matches the cached source, warn or fail. Never apply it to the nearest-looking item.

## Warnings queue

Ambiguous or unsupported source structures go to a machine-readable warnings queue rather than being guessed away.

Each warning should include, at minimum:

- stable warning code;
- date;
- source page;
- revision ID or source hash;
- category/section when known;
- source list/bullet path when known;
- raw source fragment;
- parser interpretation, if any;
- human-readable message.

Warnings should be regenerated from source plus parser state. A human resolution becomes either:

1. a general parser rule with tests; or
2. an explicit stable override.

Do not turn a resolution into an untracked edit of generated output.

## Schema governance

The current writer emits the existing seed shape, and `seed.merge` explicitly references `daily-events.schema.json`. Inspect that schema before implementation.

A hierarchy-preserving output is a schema change.

Before replacing published or existing output:

1. document the current schema and the proposed schema;
2. assign or update an explicit schema version;
3. define ordering and null semantics;
4. define how legacy monthly-fallback provenance is represented;
5. define how existing GDELT content is carried through;
6. generate new output side by side with the old output;
7. validate and reconcile differences before replacement.

Do not silently reinterpret old files in place.

## Serialization contract

If byte-level reproducibility is a project requirement, define the serializer contract instead of assuming that logically equivalent YAML is byte-identical.

Pin or test at least:

- UTF-8 encoding;
- newline convention;
- key ordering;
- sequence ordering;
- scalar quoting policy where relevant;
- trailing newline;
- serializer/library behavior that can alter output.

Byte idempotence may be claimed only for layers whose complete inputs are pinned or cached.

## Testing and fixtures

Do not use the whole corpus as the first test suite.

Create checked-in golden fixtures spanning each source-format era and each known structural hazard. At minimum cover:

- new-style category/event pages;
- old-style semicolon category plus nested topic hierarchy;
- three-or-more-level nesting;
- standalone parentless events;
- multiple adjacent citations;
- comma-separated citations;
- syndication/"via" citations;
- language annotations;
- wikilinks with distinct surface/target text;
- inline templates/HTML entities/`nowiki`;
- malformed or surprising source structure;
- legacy monthly fallback.

Each fixture should pair exact source input with expected structured output and expected warnings.

## Verification

Editing code is not completion. Report which checks actually ran.

Required checks for a parser/schema migration:

1. **Fixture tests:** all golden fixtures pass.
2. **Offline check:** parser and full reparse tests run without network access.
3. **Structural checks:** every event has a defined structural role; no item is both header and event; parent paths are valid; ordering is preserved.
4. **Orphan handling:** a source header with no child is preserved and warned about, not silently deleted merely to satisfy an invariant.
5. **Leaf reconciliation:** compare event-leaf counts with the prior generation and explain every delta. Hierarchy promotion may change container counts but must not silently drop event content.
6. **Source coverage:** account for every structurally relevant source bullet or emit a warning explaining why it was not represented.
7. **Structural round trip:** compare a canonical structural representation, not an undefined "approximate wikitext" textual diff.
8. **Era spot checks:** manually verify at least one date from each identified portal-format era.
9. **Idempotence:** parsing the same cached source twice produces identical structured output. Whole-file byte idempotence is required only when every included layer, including enrichment, has deterministic inputs.
10. **Side-by-side corpus diff:** regenerate to a separate location and reconcile changed files before replacing the existing corpus.

Never claim a check passed if it was not executed.

## Corpus baseline and checkpoint safety

Generated output can exist in multiple states at once: published, locally regenerated with newer code, and provisional output from an in-flight rewrite. Do not collapse those states merely for convenience.

Before a parser/schema migration overwrites generated files:

- inspect the working tree for a newer local regenerated corpus;
- preserve any substantial local regeneration that would be expensive or impossible to reproduce exactly;
- prefer a dedicated checkpoint/WIP branch or commit when that gives a clean, diffable baseline;
- do not interpret a preservation commit as approval of that output schema;
- generate migration candidates in a separate location until verified.

When multiple prior outputs exist, the exact cached source is authoritative. Newer local output is valuable evidence for detecting regressions and previously implemented semantics, but it is not automatically the target specification.

## Git and publication safety

The CLI supports automatic commit and push for range runs. Do not use `--commit` or `--push` during exploratory parser work, cache construction, schema design, or provisional regeneration unless explicitly requested.

Before publication:

- inspect whether defective output is already published;
- inspect whether a newer local regenerated corpus exists and preserve it before destructive replacement;
- keep provisional regeneration separate from both canonical output and preserved intermediate baselines;
- require a clean worktree before automated commit/push;
- summarize the exact files and corpus range to be replaced.

## Escalation criteria

Stop and ask rather than silently deciding when:

- a source structure cannot be classified without guessing;
- the choice would alter the source/revision policy;
- a proposed change would alter the public schema without an approved migration plan;
- an existing published artifact would be rewritten incompatibly;
- the legacy monthly fallback cannot be made reproducible without choosing a new provenance policy;
- a change adds a new external service or changes what network data is collected;
- a correction would alter source facts rather than extraction interpretation.

Routine parser implementation within an approved schema and source policy does not require repeated confirmation.

## Reporting

Every completed work pass ends with:

- what changed;
- files changed;
- commands run;
- source/network access performed;
- tests and verification checks passed, failed, or skipped;
- warnings introduced or resolved;
- remaining risks;
- recommended next step.

Do not bury caveats. Partial fixes are described as partial.

## Style and repository privacy

Repository Markdown is plain and scannable. Avoid decorative icons and promotional formatting.

This is a public repository. Do not add personal, medical, account, credential, or private working-context information to repository files.

## Verified repository wiring

The following additional facts were checked by repository inspection on
2026-10-05. Current corpus and publication state belong in `HANDOFF.md`.

- `seed/__main__.py` imports `seed.cli.main` and exits with its return code.
- `seed.cli` coordinates acquisition, optional GDELT enrichment, seed writing,
  range planning, CSV reports, and optional Git batches. `plan` does not fetch.
- The local daily workflow is `.github/workflows/daily_update.yaml`; publication
  state must be checked against the remote before relying on its local copy.
- `reference/schema/daily-events.schema.json` defines synthesis schema 2.2.
  It is not a schema for the current seed shape or a hierarchy-preserving
  archival extraction contract.
- `reference/schema/validate.py` checks synthesis schema and event/citation
  references. JSON Schema validation requires `jsonschema` to be installed.
- Local synthesis tooling is under `reference/expansion/`: `build.py`,
  `wikiportal.py`, `entities.py`, per-day overlays, and `roles.json`.
  Its output is `expanded/<YYYY>/<MM>/<YYYY-MM-DD>.yaml`.
- The expansion tool has its own pinned wikitext inputs under
  `reference/expansion/wikitext/`, with revision metadata and payload hashes.
  The source cache in `seed.source` also imports these inputs. `cache` acquires
  explicit recorded oldids; `reparse` consumes cached inputs without acquisition.
  `reference/schema/extraction.schema.json` defines the separate candidate
  extraction contract. Candidates never replace canonical daily paths.
- `reference/schema/AUTHORING_GUIDE.md` and `expanded/README.md` describe the
  local synthesis workflow. A generator run must use the correct research
  input explicitly; filename suffixes alone are not a reliable selection rule.
- The repository is operated directly from Python source. `requirements.txt`
  pins direct dependencies; `tests/` uses unittest and checked-in golden
  fixtures. `.github/workflows/verify.yaml` runs offline tests and synthesis
  validation. No packaging metadata or lint/format configuration is present.
  Record checks actually executed in the handoff.
- No monthly-summary generator was found. Summary generation remains a
  separate synthesis task.
