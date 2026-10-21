Latest status: see the October 20, 2026 pass at the end of this file. Earlier inspection and repair passes are retained as history.

# HANDOFF: Wikipedia extraction and seed-schema rewrite

Latest inspection: see **Repository and January research inspection
2026-10-05** at the end of this file. It distinguishes the newer published
January work from this checkout and corrects earlier unverified claims.

Read `AGENTS.md` first. It contains durable rules. This file records the current known implementation, defects, migration constraints, and next work.

## Provenance of this handoff

This handoff is based on:

- the prior `AGENTS.md` and `HANDOFF.md`;
- one previously examined generated daily YAML example;
- the supplied collection modules:
  - `cli.py`
  - `gdelt.py`
  - `gitops.py`
  - `merge.py`
  - `ratelimit.py`
  - `report.py`
  - `wikipedia.py`

The repository itself has not been fully inspected in this chat. Facts about files not represented by those inputs remain unverified.

Do not infer repository-wide facts from this subset when direct inspection is possible.

## Executive summary

The collection pipeline is already substantially implemented in Python under the `seed` package. The central problem is not "write a scraper from scratch."

The current Wikipedia parser recognizes several source-depth patterns, but its return type is still `dict[str, list[str]]`. That data model cannot preserve the source hierarchy, wikilinks, or structured citations. The parser also strips markup before those annotations are captured.

The current fetch and parse paths are coupled. Daily Wikipedia pages are fetched by title at their current revision each time. There is no persistent raw-wikitext cache in the supplied code. The pre-2004 fallback parses rendered monthly HTML and records no revision ID.

The daily YAML also contains optional GDELT enrichment. A Wikipedia-only parser rewrite must not refetch GDELT and accidentally change unrelated historical enrichment.

There is also a newer local corpus state that did not exist in the repository version described by the earlier handoff. The user has spent roughly four days regenerating the daily YAML files with the current collection code. As of 2026-08-09 that run was nearly complete and had progressed to approximately April 2026. These locally regenerated files are reported to be materially more semantic than the files currently published in the repository, although they still exhibit the extraction defects described below.

Treat that local regeneration as valuable migration evidence and a comparison baseline. Do not assume the published GitHub corpus is the best available representation, and do not discard or overwrite the regenerated local corpus before inspecting it. Conversely, do not treat the intermediate regenerated YAML shape as the target schema merely because it is newer. The exact Wikipedia source remains authoritative.

The migration should therefore proceed in this order:

1. inspect and preserve the current local regeneration state before changing generated files;
2. inspect the full repository, schema, Git state, and differences between published and local regenerated output;
3. establish immutable source caching and revision-pinned replay;
4. create era/edge-case fixtures using exact source plus representative local outputs;
5. define the hierarchy-preserving schema and warning/override contracts;
6. rewrite the parser against cached sources;
7. regenerate to a third, separate comparison location while preserving existing GDELT blocks;
8. reconcile exact source vs. published output vs. intermediate local output vs. candidate output before replacement or publication.

Do not begin with a blind full-corpus `seed range --target all`; that path refetches network sources and rewrites seed files.

## Three corpus states to distinguish

At the start of the parser rewrite there may be three materially different representations of the same dates. Keep them conceptually and operationally separate.

### A. Published repository corpus

This is the version currently committed/pushed to GitHub. It may contain older, less-semantic YAML than the user's current local regeneration. Do not assume it is the best baseline merely because it is published.

### B. Intermediate local regenerated corpus

The user has been running a multi-day regeneration with the current collection code. This corpus is newer and reportedly more semantic than the published files, but it still predates the hierarchy/link/citation rewrite described in this handoff.

Before parser work:

- determine the exact date range successfully regenerated;
- determine whether the run completed cleanly;
- identify which files differ from `HEAD`;
- sample outputs across multiple source-format eras;
- identify semantic improvements already present so they are not accidentally regressed;
- preserve the corpus before any command that could overwrite it.

Preferred preservation is a dedicated local checkpoint branch or other explicit WIP/checkpoint commit after the regeneration run finishes. A checkpoint commit is for preservation and diffability; it does not declare the intermediate schema canonical and need not be pushed to `main`. If the user chooses not to commit it, make an equivalent safe copy before destructive work.

### C. Candidate corrected corpus

This is output from the new revision-pinned, cache-backed, hierarchy-preserving parser. Generate it separately from both A and B until verification is complete.

Comparisons should therefore distinguish:

```text
exact cached Wikipedia source
    -> published corpus (A)
    -> intermediate regenerated corpus (B)
    -> candidate corrected corpus (C)
```

The target is not "make C look like B." The target is "make C faithfully represent the exact cached source under the approved schema," while using A and B to detect regressions, prior improvements, dropped content, and migration effects.

## Confirmed current architecture

### CLI

The documented entry point is:

```text
python -m seed
```

Commands:

- `seed date [DATE]`
  - defaults to yesterday UTC;
  - regenerates the target day by default;
  - `--no-gdelt` skips enrichment.
- `seed plan START END`
  - dry-run planning;
  - groups dates into day/month/year chunks.
- `seed range START END`
  - range/backfill path;
  - defaults to processing missing files only;
  - `--target all` forces every date in range through the fetch/write path;
  - can optionally commit and push each batch.

`range` writes a CSV run report unless disabled and can batch Git commits.

### Daily flow

The current high-level path is:

```text
seed.cli.fetch_and_save_day()
    -> seed.wikipedia.fetch_day()
    -> optional seed.gdelt.fetch_gdelt_articles()
    -> seed.merge.build_seed_doc()
    -> seed.merge.save()
```

### Output path

Current seed files are written to:

```text
<repo>/<YYYY>/<MM>/<YYYY-MM-DD>.yaml
```

### Current seed shape

The supplied writer constructs approximately:

```yaml
date: 'YYYY-MM-DD'
source_page:
  portal: Portal:Current events/...
  language: en
  wikipedia_revision_id: 1234567890
wikipedia:
  categories:
    Category name:
      - event string
gdelt:
  queried_at: '...Z'
  article_count: 42
  articles: [...]
```

The GDELT block is omitted when not queried.

`seed.merge` says `source_page` intentionally mirrors `daily-events.schema.json` and refers to a later "schema-2.2 rework" stage. Inspect that schema and any stage documentation before choosing the replacement shape.

## Confirmed Wikipedia behavior

### Fetch path

`fetch_day()` tries several daily page-title candidates. Daily pages are fetched through the MediaWiki API with:

- `prop=revisions`;
- `rvprop=content|ids`;
- no explicit `rvstartid`/`oldid` pin.

The returned revision ID is whatever revision the title resolves to when the request runs.

For each daily candidate:

1. fetch current wikitext;
2. parse it;
3. return on the first candidate yielding events;
4. otherwise continue to fallback candidates.

A 1.5-second delay is applied between Wikipedia daily-page requests.

### Source-format logic already present

`seed.wikipedia` already recognizes multiple broad patterns.

It documents old-style pages roughly as:

```text
;Category
*Sub-topic:
**Sub-sub-topic:
***Actual event
```

with standalone events also possible directly beneath the semicolon category.

It documents newer pages roughly as:

```text
*Category:
**Event
```

The code also includes page-title candidate logic for Portal-namespace and older Wikipedia-namespace pages.

This is important: do not discard the existing era knowledge and replace it with a parser based only on the 2015 sample.

### Legacy monthly fallback

When daily candidates fail, the code can fall back to rendered monthly-page HTML, especially for pre-2004 dates.

That path:

- parses rendered HTML `<li>` text;
- collapses events into `{"Uncategorized": [...]}`;
- stores a synthetic source title with a day anchor;
- returns `wikipedia_revision_id=None`;
- caches the parsed monthly page only in memory for the duration of the run.

This fallback does not currently meet the target revision-pinned/offline-replay standard.

## Defect 1: hierarchy is still flattened by the data model

The parser comments say hierarchy is handled, but the output contract is still:

```python
dict[str, list[str]]
```

That forces structural information to be collapsed.

Current examples of loss:

- `;Category` becomes `cat0`.
- A `*Sub-topic:` is assigned to `cat1` and then becomes a dictionary key rather than a child object under `cat0`.
- A `**Sub-sub-topic:` is stored in `prefix2`.
- A following `***Actual event` is emitted as a single string such as `"prefix2: event text"`.

This preserves some words but not the actual source tree.

The replacement parser must represent source hierarchy explicitly rather than encoding it in dictionary-key selection or string concatenation.

Do not assume there are only two levels. Parse actual list depth.

## Defect 2: wikilinks are destroyed before output

`_clean()` currently calls:

```python
mwparserfromhell.parse(raw_text).strip_code()
```

That removes wiki markup before the output structure can retain link targets and surface text.

The target extraction must capture wikilinks first, including at least:

```yaml
surface: displayed text
target: target as written
```

Redirect resolution belongs elsewhere.

Historical red-link state is not present in raw wikitext. Do not invent it during parse. If desired, add it later from revision-aware metadata.

## Defect 3: citation URLs and citation structure are destroyed

After `strip_code()`, `_clean()` also contains regexes that replace labeled external links with their label and remove bare external links.

That behavior is incompatible with preserving citation URLs.

The source variants previously observed include:

- single source parentheticals;
- adjacent source links with no separator;
- comma-separated source parentheticals;
- syndication chains using "via";
- separate language annotations.

Capture external links and surrounding citation structure before prose cleanup.

Do not treat a whole citation parenthetical as an opaque string if the source markup exposes separate URL/label components.

## Defect 4: no persistent raw-source cache

The supplied code has no on-disk raw-wikitext cache.

`MonthlyCache` is only:

```text
(year, month) -> (matched monthly title, parsed events by day)
```

and lives in memory during a run.

This means ordinary parser iteration currently triggers network fetching, and `--target all` would refetch the corpus rather than reparse a stable input set.

The first architectural change must be to split source acquisition from source parsing.

## Defect 5: current-revision fetch defeats deterministic reparse

The daily API fetch records a revision ID but does not request a previously recorded revision.

This creates an opportunity for migration:

### Recommended migration rule

For an existing YAML file whose `source_page.wikipedia_revision_id` is non-null:

1. read the existing revision ID;
2. fetch that exact historical revision once;
3. cache its raw wikitext;
4. preserve the existing source title;
5. reparse from that cached payload thereafter.

Do not fetch the page's latest revision merely because parser code changed.

For new captures, fetch current once, record/cache that revision, then treat it as pinned for all future reparses.

## Defect 6: legacy monthly fallback has an unavoidable provenance gap

The existing monthly-HTML fallback returns `revision_id=None`.

For already-generated files made through that path, the exact historical rendered input may not be recoverable from current output alone.

During repository inspection:

1. identify every file with null Wikipedia revision;
2. determine whether the corresponding monthly page can be represented by raw wikitext at a specific revision;
3. inspect Git history/logs for evidence of the acquisition date or prior source payload;
4. propose a one-time migration policy for any unrecoverable cases.

Do not silently assign a current revision and imply it is the original source.

If rendered HTML remains necessary, cache the exact HTML used and mark the source mode explicitly.

## Defect 7: GDELT makes naive whole-file regeneration non-deterministic

`seed.cli.fetch_and_save_day()` fetches Wikipedia and then optionally queries GDELT before rewriting the YAML.

GDELT results include:

```yaml
queried_at: current UTC time
```

and the API result set may change independently of Wikipedia.

Therefore, running the existing fetch/write path merely to repair Wikipedia extraction can change the GDELT block too.

### Migration rule

For the Wikipedia rewrite, preserve the existing GDELT block from each existing YAML file. Do not requery GDELT unless the user explicitly brings GDELT regeneration into scope.

A future deterministic GDELT replay design can cache its acquisition payload separately.

The existing GDELT `artlist` theme-field limitation is known and explicitly out of scope in the supplied code. Do not fold that unrelated issue into this parser migration.

## Defect 8: warnings and overrides are not implemented in the supplied subset

The previous design correctly called for a warnings queue and durable overrides, but no such mechanism appears in the supplied modules.

Implement them before relying on agent/human cleanup of ambiguous cases.

### Warning identity

A warning needs stable source identity, not merely a generated-output position. Include:

- date;
- source page;
- revision ID/source hash;
- list/bullet path;
- warning code;
- raw fragment;
- parser message.

### Override identity

Do not key an override solely by `date + flat item position`.

Hierarchy repair will move positions.

Use stable source coordinates such as revision/source hash plus source bullet path, with a raw-fragment fingerprint as a guard against drift.

Overrides should correct parse interpretation. They should not "fix" factual or spelling errors present in Wikipedia.

## Defect 9: parser verification needs fixtures before corpus regeneration

No tests or fixture structure were supplied. Inspect the repository before asserting that none exist.

If equivalent fixtures are absent, add golden cases for each source era and each structural/citation/link edge case listed in `AGENTS.md`.

The parser should be exercised against exact cached inputs without network access.

## Schema migration requirement

The existing writer and comments reference `daily-events.schema.json`.

Before parser code changes the output shape:

1. inspect that schema;
2. inspect consumers of the current YAML;
3. identify whether schema 2.2 already describes any intended hierarchy;
4. propose the replacement structure;
5. assign/version the schema;
6. define GDELT carry-through semantics;
7. define legacy source provenance;
8. generate into a separate location or branch for comparison.

Do not regenerate canonical files in place until the new schema is approved and verified.

## Provisional structural target

The exact syntax remains contingent on repository/schema inspection. The important properties are:

```yaml
date: '2015-07-01'
schema_version: <approved version>
source_page:
  portal: Portal:Current events/2015 July 1
  language: en
  wikipedia_revision_id: 1076194341
  revision_timestamp: <captured if available>
  source_mode: wikitext
  source_sha256: <hash>
wikipedia:
  categories:
    - name: Armed conflicts and attacks
      entries:
        - topic:
            text: Yemeni Civil War (2015-present)
            links:
              - surface: Yemeni Civil War (2015-present)
                target: Yemeni Civil War (2015-present)
          events:
            - text: Shells fired by Houthi forces...
              source_path: [1, 1]
              links:
                - surface: Houthi forces
                  target: Houthi movement
              citations:
                - publisher: Reuters
                  url: <captured URL>
                  via: null
                  language: null
        - topic: null
          events:
            - text: Parentless event...
              source_path: [2]
gdelt:
  <existing block carried through unchanged during this migration>
```

Do not treat the field names above as approved merely because they appear here. Inspect `daily-events.schema.json` first. The structural requirements are the authoritative part.

## Repository inspection checklist

Complete this before editing the parser.

1. Read:
   - `README.md`;
   - current `AGENTS.md`;
   - current `HANDOFF.md`;
   - `daily-events.schema.json`;
   - packaging/dependency files;
   - test configuration;
   - GitHub Actions;
   - any stage/snapshot/roadmap documents.
2. Confirm actual `seed/` paths and `python -m seed` wiring.
3. Search for:
   - other cache implementations;
   - warnings/override files;
   - other Wikipedia parsers;
   - schema consumers;
   - summary/long-snapshot generators.
4. Determine corpus:
   - earliest/latest date;
   - total YAML count;
   - count with non-null Wikipedia revision;
   - count with null revision;
   - count containing GDELT;
   - distinct category keys;
   - files already committed/published.
5. Determine the local regeneration state separately from the published corpus:
   - exact regenerated date range and whether the four-day run completed;
   - changed/untracked file count relative to `HEAD`;
   - whether regenerated files are all products of one code version/configuration;
   - representative structural differences between published and local files;
   - whether any local regenerated files contain data that would be lost by rerunning the current fetch path.
6. Preserve the completed or partial local regeneration before parser changes, preferably as a dedicated checkpoint/WIP commit or branch, unless the user explicitly chooses another safe snapshot method.
7. Inspect Git history around both the published defective generation and the newer local regeneration code.
8. Fill any still-unknown project facts in `AGENTS.md`.
9. Report findings before choosing the final schema.

## Implementation sequence

After inspection and preservation of the current local baseline:

### Phase 0: checkpoint and characterize the intermediate regeneration

- allow an already-running regeneration to finish unless there is a concrete reason to stop it;
- record the exact completion range and any failures/warnings;
- inspect representative regenerated YAML from each identified era;
- compare representative regenerated files with `HEAD`;
- preserve the local corpus before changing parser/writer behavior;
- do not merge or push this checkpoint to `main` merely to make it safe.

The purpose of Phase 0 is preservation and understanding, not schema approval.

### Phase 1: establish source replay

- add persistent source-cache storage;
- add explicit acquisition functions for exact Wikipedia revisions;
- make parsing accept cached/raw source input directly;
- ensure an offline parser/reparse path exists;
- do not route reparse through `fetch_and_save_day()`.

### Phase 2: build fixtures

- collect representative exact source payloads from each era;
- encode expected hierarchy, links, citations, and warnings;
- include legacy fallback cases.

### Phase 3: rewrite Wikipedia parse representation

- replace `dict[str, list[str]]` as the internal parse result;
- parse list depth structurally;
- capture markup before text stripping;
- retain source paths;
- emit warnings rather than guessing.

### Phase 4: warnings and overrides

- define schemas and paths;
- apply overrides after parse but before serialization;
- validate override locators against source identity.

### Phase 5: writer/schema migration

- update the approved schema/version;
- define deterministic serialization;
- carry existing GDELT blocks forward unchanged;
- write provisional output separately from both the published/canonical files and the preserved intermediate local regeneration.

### Phase 6: verification

Run:

- golden fixture tests;
- offline reparse test;
- structural invariants;
- source-bullet coverage;
- leaf-count reconciliation;
- era spot checks;
- deterministic repeated parse;
- three-way corpus comparison where available: published vs. intermediate local vs. candidate corrected output.

Always ground the final judgment in the exact cached source. Explain every content delta that is not purely structural, and identify useful semantics present in the intermediate local corpus that the candidate would otherwise regress.

### Phase 7: publication

Only after verification:

- replace canonical output;
- run schema validation over the corpus;
- report warnings and exceptions;
- commit/push only when explicitly requested.

## Commands to avoid during the rewrite

Until source replay and side-by-side output are implemented, do not use this as a parser-regeneration command:

```text
python -m seed range START END --target all
```

It is a network fetch/write path and may also refetch GDELT.

Do not use `--commit` or `--push` for provisional regeneration.

## What should remain unchanged unless separately requested

The following supplied behavior is not the target of this migration:

- shared retry/backoff infrastructure;
- Git batch helpers;
- CSV range-run reporting;
- GDELT theme-group redesign;
- GDELT daily-CSV migration;
- summary-generation content.

Modify those only when required by the source-cache/schema separation or by a separately approved task.

## Completion criteria for this handoff

The extraction rewrite is not complete when the parser merely "looks better."

Completion requires:

- exact-source replay for the supported Wikipedia paths;
- persistent cached source inputs;
- hierarchy-preserving structured parse;
- structured wikilinks and citations;
- stable warnings and overrides;
- approved/versioned output schema;
- no accidental GDELT regeneration;
- offline fixture and corpus reparse capability;
- reconciled side-by-side corpus output;
- explicit accounting for legacy null-revision cases;
- reported verification results.

## Status update 2026-09-22

- Working copy is `D:\dev\proj\current-events-context`. A separate clone at
  `D:\GitHub\current-events-context` (re-cloned 2026-09-18) only tracks
  `origin/main`. It holds no unique work.
- Local `main` merged `origin/main` (commit `97991f36`). That brought in 47
  GitHub Actions daily commits for 2026-08-06 to 2026-09-21. Those 46 new files
  use the legacy `Date`/`Source_URI`/`Intelligence_Payload` shape, because the
  workflow on `origin` still runs `update_data.py`. For the
  `2026/08/2026-08-06.yaml` conflict, the local seed-shape file was kept. Nothing
  has been pushed; local is about 300 commits ahead of `origin`.
- The 2026-08-09 seed regeneration overwrote the 25 previously expanded 2026
  day files with seed output. Those expansions now live in the separate
  `expanded/` tree (see `expanded/README.md`). Pushing local `main` would
  replace the published expanded files at the day paths with seed files, and
  the expansions would appear under `expanded/` instead.
- Parser evidence from the expansion build: the local seed output for 2026
  pages puts every bullet, including topic headers, into one flat
  `Uncategorized` list. Raw wikitext for the same revisions has real categories
  and nesting. For 2026-03-07 (revision 1343328007), the seed dropped the
  "Shield of the Americas" bullet (Trump meets leaders from twelve countries).
  The pinned wikitext for 19 days is in `reference/expansion/wikitext/` and can
  seed parser fixtures.

## Immediate next action

Inspect the repository and `daily-events.schema.json`, then report the inspection checklist results.

Do not write the hierarchy parser first.

The highest-value facts to resolve immediately are:

1. whether any persistent cache already exists outside the supplied modules;
2. what schema 2.2 already specifies;
3. how much of the corpus has non-null recorded revision IDs;
4. how many files came from the monthly rendered-HTML fallback;
5. whether the defective generation has been committed or published;
6. what tests and downstream consumers already exist.

Those findings determine the smallest safe implementation path.

## Repository and January research inspection 2026-10-05

This was an inspection and verification pass, not a parser migration or a
research/conversion run. Earlier sections remain historical context. The
findings below supersede their statements about current publication, cache
availability, January progress, and the March 7 missing-bullet example.

### Baselines and publication

- Local `main`: `8ae99350` (2026-09-22).
- Fetched `origin/main`: `0e2e43d3` (daily update for 2026-10-04).
- Local `main` is 301 commits ahead and 29 behind the fetched remote. No merge,
  rebase, checkout, commit, push, or corpus replacement was performed.
- Before this pass, `HANDOFF.md` was already modified and `AGENTS.md` was
  untracked. Five untracked January reports existed: `2026-01-10b.md`,
  `2026-01-11b.md`, `2026-01-12b.md`, `2026-01-13a.md`, `2026-01-14a.md`.
  All five match the corresponding published reports after CRLF/LF
  normalization. They are not additional unpublished research.
- Local regeneration is already preserved in committed history, following
  checkpoint `0f5cbef6` and seed consolidation `09bf4464`. Local expansion
  tooling/output is preserved in `fead6104`; exact cached bytes are protected
  by `8ae99350` and `.gitattributes`.
- Public GitHub has no open issues or pull requests at inspection time. The
  five most recent scheduled workflow runs were successful, including the
  run creating the 2026-10-04 file. Success indicates execution, not parser
  correctness or factual review.
- The branch comparison changes 8,963 files. Daily paths comprise 8,742
  modified files, 89 local additions, and 12 remote-only files. A broad push
  or an automatic conflict resolution would affect much more than January.

### How the layers interoperate

1. Local `python -m seed` calls `seed.cli.main`. `date` fetches one day and
   overwrites by default; `range` skips existing days by default; `plan` only
   discovers work. Acquisition/parser behavior is in `seed.wikipedia`;
   `seed.gdelt` adds optional live enrichment; `seed.merge` writes the seed.
   Retry policies, Git batch helpers, and range CSV reports are separate
   modules. There is no schema validation in the seed writer.
2. Published automation still calls `update_data.py`, backed by
   `wiki_parser.py`, and writes `Date`, `Source_URI`, `Intelligence_Payload`.
   It does not store Wikipedia revision IDs. The local workflow calls
   `python -m seed date` instead. The consolidation has not been published.
3. Research Markdown lives in `reference/deep-research/`. The published
   January workflow converts reports and portal stubs into schema-2.2 files
   at the ordinary daily paths. Local September work instead keeps seeds at
   those paths and synthesis under `expanded/`.
4. Local `reference/expansion/build.py` operates offline from pinned wikitext,
   research reports, overlays, entity roles, and sometimes schema-2.1 files
   read from commit `0f5cbef6`. It writes synthesis through a deterministic
   custom serializer. It is separate from `seed.wikipedia`.
5. `reference/schema/daily-events.schema.json` describes expanded synthesis,
   including review state, events, bibliography, and analytical text. Its
   flat event list is not the proposed archival hierarchy schema. Local and
   remote copies of the JSON schema agree; their validators and authoring
   paths differ.
6. No monthly-summary generator or external application consuming the YAML
   was found. The published handoff intends a January summary after all
   daily expansions are finished, deduplicating related developments.

### Corpus and regeneration inventory

| Baseline | Daily YAML count | Range | Shapes |
|---|---:|---|---|
| Local ordinary day paths | 8,877 | 2002-01-01 through 2026-09-21 | 8,831 seed files; 46 legacy files |
| Published ordinary day paths | 8,800 | 2002-01-01 through 2026-10-04 | 8,772 legacy; 15 schema-2.2 expansions; 12 schema-2.1 expansions; one malformed March expansion |
| Local `expanded/` | 24 | January 1-12 and selected March days | Five reviewed; 19 draft; all schema 2.2 |

All 8,877 local ordinary-day files parsed as YAML. All 8,831 seed files have
non-null revision IDs and nonempty Wikipedia lists. None contains GDELT.
There are 4,214 seed files whose only category is `Uncategorized`. Category
labels also include topics incorrectly promoted to categories.

The local corpus has 153 missing dates within its range: 142 in 2002, ten in
2003, and 2014-11-18. Absence does not establish that the source day had no
events. No backfill was attempted.

The large regeneration CSV ends on 2026-08-06 at
2026-08-09T21:06:41Z: 8,984 attempted days, 8,831 written, 153 missing. It
reached its recorded final day. The report alone does not prove a clean
process exit or preserve every acquisition option. The 46 later local files
are inherited legacy daily output, not part of that regeneration.

No seed file in this checkout has a null revision ID; the monthly-HTML gap
remains a code-path risk rather than an observed seed population here. All
15 published January synthesis files have null revision IDs, for a different
reason: they came through the unpinned legacy/authoring workflow. Do not
classify these synthesis nulls as evidence of monthly fallback.

### Actual January stopping point

| Days | Published state | Local state |
|---|---|---|
| January 1-5 | Schema 2.2, reviewed | Same synthesis copies in `expanded/`; ordinary paths are seeds |
| January 6-9 | Schema 2.2, reviewed | Older draft expansions in `expanded/` |
| January 10-12 | Newer schema-2.2 drafts using replacement `b.md` reports | Older draft expansions using `a.md`; replacement reports are untracked locally |
| January 13-14 | Schema-2.2 drafts and reports | Reports only; no local expansion/cache for these days |
| January 15 | Schema-2.2 draft and first report from revised research prompt | Report and expansion absent locally |
| January 16-31 | Legacy stubs; no research reports | Seeds; no research reports |

All 15 published January expansions pass JSON Schema and the validator's
event/citation reference checks. Every `related_events` ID used across those
15 files resolves within that set. This does not independently verify claims,
article dates, quotations, or URLs against the original publishers.

The published handoff records unresolved review work: January 4's royal
commission item may be misdated; January 14's Senate vote rests on a headline
and the Danish/Greenlandic Washington talks are a possible coverage gap;
January 15 mixes in later Uganda counting. It also carries forward Benin
election-results placement and two January 30 items excluded from earlier
reports. These are review leads, not newly verified factual conclusions.

### Findings that need addressing

1. **Reconcile the histories before using this checkout for new January
   work.** The public January files are newer than the local expansion
   baseline. Preserve both sets and compare them explicitly. Importing the
   newer synthesis into `expanded/` would preserve the local layer separation,
   but moving public day-path expansions remains a publication migration
   requiring a reviewed plan. Do not resolve conflicts by blindly retaining
   either complete tree.
2. **The local expansion builder selects obsolete reports.**
   `md_path_for()` only tries `<date>a.md` and `<date>.md`; it ignores `b.md`.
   Confirmed selection for January 10-12 is the older `a.md`. Rebuilding now
   would reproduce stale content, not the published corrections. Use an
   explicit input manifest/selection and pin its identity before rebuilding.
3. **The research and conversion entrypoints disagree.** Published
   `llm_prompt.txt` was rewritten to require the true daily portal, date
   checks, real URLs, and excluded-items lists. The local copy is older.
   `llm_agent_prompt.txt`, `llm_review_prompt.txt`, and existing Copilot prompts
   still describe schema 2.1. `generate_prompts.py` also hardcodes an old clone
   location and targets ordinary seed paths, contradicting local synthesis
   separation. Do not run these as-is.
4. **Seed extraction remains lossy.** Replaying all 19 cached days reproduces
   their local seed categories exactly; every one is a flat `Uncategorized`
   list. The parser ignores bold category lines, strips structured links and
   citations, and caps its handling at three sigils. It cannot satisfy the
   archival hierarchy invariants. No seed-wide replay cache, structured
   warnings queue, or stable extraction override system was found.
5. **Expansion cache and overlays are useful but incomplete safeguards.**
   All 19 cached payload hashes match and their revision IDs match the seeds.
   `wikiportal.parse()` does not verify these hashes itself and uses presence
   of an external citation to distinguish events from topic headers. Its
   overlays use positional `md:n`/`p:n` keys without source-drift guards.
   These synthesis tools cannot be adopted unchanged as the archival parser.
6. **Validation and packaging need small repairs.** No checked-in tests,
   requirements/lock file, package metadata, or lint/format configuration was
   found. `jsonschema` is optional in the validator; without it, schema checks
   are reported as skipped but the command can still succeed. Local batch
   validation short-circuits on the first failure; the remote already fixed
   that issue. Validation does not check cross-file `related_events` links.
7. **Published March output remains mixed and partly malformed.** March
   10-11 remain schema 2.1 and are not in the local synthesis tree; March 18
   fails YAML parsing. Treat that separately from January completion.

Correction to the September 22 note: the March 7 "Shield of the Americas"
bullet is present in both the local seed and the local expanded file
(`evt-2026-03-07-009`). Its cached source matches the seed revision. The
earlier assertion that the seed dropped it is not supported by this pass.
The confirmed problem is lost structure, not loss of that specific bullet.

### Verification actually performed

- Git commands: `status`, `fetch origin`, `rev-list --left-right --count`,
  `log`, `diff`, `ls-tree`, `show`, `cat-file --batch`, and branch/remote reads.
  GitHub connector reads checked repository metadata, open issues/PRs, and
  five recent workflow runs.
- Read/search commands: `rg`, `rg --files`, `Get-Content`, `Get-ChildItem`;
  inspected package modules, workflows, schema/validator, prompts, synthesis
  tools, handoffs, sample sources, and regeneration CSVs.
- `python --version`: 3.12.10. Imports of `requests`, `mwparserfromhell`,
  `yaml`, and `jsonschema` succeeded. No dependencies were installed.
- `python -m seed --help` succeeded. `python -m seed plan 2026-01-01
  2026-01-31` succeeded with zero missing local dates and no network access.
- Ad hoc `python -` / `python -u -` scripts inventoried local YAML and the
  published Git tree; validated all 24 local expansions and all 15 published
  January expansions using the schema and cross-reference functions directly
  (avoiding the local batch short circuit); checked January related IDs;
  checked cached SHA-256/revisions; and compared the five untracked reports
  with published copies after newline normalization.
- With socket connection and `requests.Session.request` calls disabled,
  replayed all 19 cache inputs through both parsers. Repeated expansion parse
  results matched. Seed replay matched the checked-in seed categories.
- Built/serialized all 19 draft expansion days twice in memory: every pair
  was byte-identical and matched its checked-in LF output. Every event
  fragment returned by the expansion parser appeared exactly once in each
  generated file. No generated file or cached input was written.
- Parsed the AST of all 16 inspected local Python source files successfully.
- Failed check: published March 18 YAML parsing. No checked-in fixture test
  suite exists. Full offline seed reparse, independent source-bullet coverage,
  hierarchy invariants, era-by-era source acquisition, complete leaf
  reconciliation, cross-process hash-seed tests, original-publisher factual
  review, and migration corpus generation were not performed. Coverage of
  parser-returned fragments is not independent proof of raw-source coverage.

Network/source access was limited to GitHub connector reads and `git fetch`.
Wikipedia, GDELT, and research publishers were not queried; existing cached
sources and Git objects supplied the verification inputs.

### Changes, risks, and recommended next pass

Only `AGENTS.md` and this handoff were edited, preserving their pre-existing
contents. No code, prompt, schema, daily output, research report, or cache was
changed. No warning queue was generated or resolved. The March 7 assertion
was corrected in documentation; other review leads remain unresolved.

Recommended order:

1. Preserve the current uncommitted instructions/handoff and establish a
   branch for reconciling local work with the latest published January work.
   Carry forward the corrected January files and prompt without regenerating
   them. Keep the existing local expansions as a comparison baseline.
2. Decide/document the public seed-versus-synthesis layout before publication,
   fix explicit report selection and conversion instructions, and retain the
   remote validator repair. These changes can be narrow; they do not require
   completing the entire archival parser migration first.
3. Review January 10-15 against the original sources and resolve the earlier
   January review leads. Do not mark them reviewed merely because validation
   passed. Preserve corrections in durable synthesis inputs/overlays.
4. Continue with January 16 using the newer research prompt, then January
   17-31. Validate and cross-check related events at each conversion. Build
   the January summary after the daily inputs are complete and reviewed.
5. Run source replay/parser/schema migration as a separate engineering pass:
   broaden exact-source caching and fixtures first, then propose the archival
   schema and generate/reconcile candidates separately.

The immediate next unresearched date is **2026-01-16**. The immediate
repository task is **baseline reconciliation**, not a fresh bulk regeneration.

## October 5, 2026 repair pass

Engineering repairs and confirmed synthesis corrections are implemented on
`codex/repository-repairs`. This branch is local and has not been pushed.
The extraction migration remains a candidate migration: unknown roles,
source-change reconciliation, historical gaps, and the public layout/schema
replacement gate remain open. Full publisher review is also incomplete.
Earlier audit sections above are retained as historical findings.

### Changes and files

- Preserved the older local corpus and research at
  `codex/checkpoint-before-repairs` (`4d198b05`), then reconciled the published
  history without discarding pinned local seeds. Published January 1-15
  synthesis is preserved as immutable authored inputs under
  `reference/expansion/authored/` and replayed under `expanded/`.
- Fixed explicit report selection in `reference/expansion/inputs.json` and
  its builder: January 10-12 select their replacement `b.md` reports.
  Guarded synthesis overlays and legacy repairs reject source drift.
  All 29 synthesis files reproduce from their registered inputs.
- Aligned the conversion/review prompts, `generate_prompts.py`, all 15 January
  Copilot prompts, and authoring documentation with schema 2.2 and separate
  synthesis paths. Generated prompts use portable repository-relative paths
  and include durable corrections that supersede original report claims.
- Added pinned direct dependencies in `requirements.txt`, mandatory schema
  validation, complete batch validation, cited-URL/bibliography checks,
  cross-day related-event checks, and `.github/workflows/verify.yaml`.
  Daily/range Git workflows include each acquisition's exact input,
  metadata, pointer, structured artifact and warnings.
- Added immutable source storage and offline replay in `seed/source.py`,
  `seed/replay.py`, `seed/extract.py`, `seed/rendered.py`, and CLI wiring.
  `reference/schema/extraction.schema.json` and `EXTRACTION_MIGRATION.md`
  define candidate extraction-1.0, ordering/null semantics, serialization,
  enrichment preservation and the replacement gate. Headings and entries
  retain raw text, structured links and citations. Unknown structures warn.
- Cached 8891 exact Wikipedia inputs under
  `reference/sources/wikipedia/`. Existing recorded oldids remain pinned.
  For the 58 unpinned August 7-October 4 daily files, the selected policy
  captures current revisions as new inputs. Their original published Git
  blobs are unchanged; their original capture revisions remain unknown.
  `unpinned-source-plan.json` and `current-captures-report.json` record this.
- Filled November 18, 2014 and September 22, 2026 from explicitly new current
  captures, without GDELT. The former contains colon-indented lists that the
  old collector missed. Existing daily files were not bulk-regenerated.
- Repaired confirmed January chronology and bibliography problems through
  `reference/expansion/authored-overlays/`, then regenerated January 1, 4,
  8-10, 12 and 15. Corrections distinguish the commission appeal,
  announcement and formal establishment; January 9 oil-policy actions;
  later Aleppo withdrawal; and later Uganda counting. Unsupported homepage
  citation claims are cleared. Changed snapshots remain draft.
- Regenerated March 10-11 as schema-2.2 drafts and made the March 18 YAML
  repair durable. March citation pointer repairs also regenerate.
  Original reports, authored snapshots and cached inputs remain preserved.
- Added `tests/`, per-date corpus reconciliation, warning/unknown queues,
  nine era spot checks and cross-process verification artifacts under
  `reference/reconciliation/`. Reproducible candidates remain locally under
  `provisional/extraction-v1/`, separate from canonical output.

### Commands and verification actually run

- `python -m unittest discover -s tests -v`: 20 methods passed, including
  16 golden fixture cases, hierarchy/parent/order checks, citation hazards,
  guarded drift rejection, immutable cache checks, GDELT carry-through,
  offline replay, complete validator behavior and prompt contract checks.
  Early implementation/test failures were repaired before this final pass.
- `python -m seed cache 2002-01-01 2026-10-04 --skip-unpinned` acquired the
  existing recorded revisions, using explicit oldid batches. The initial
  acquisition report remains preserved. The two missing-date captures used
  the collection path with GDELT disabled.
- `python -m seed cache 2026-08-07 2026-10-04 --capture-unpinned` captured
  the selected 58 current revisions without changing those daily outputs.
  A Git-blob comparison verified all 58 original files were preserved.
- `reparse 2002-01-01 2026-10-04 --cached-only --verify --output-root
  provisional/extraction-v1`, invoked with both socket connections and
  `requests.Session.request` disabled: 8891 candidates
  verified, 152 missing dates explicitly reported.
  Every input was parsed twice; serialized bytes and canonical YAML round
  trips matched. Ordering and parent checks passed. All cache file hashes
  matched before and after the complete run. Preliminary runs were stopped
  to repair heading metadata and uncited-parent role classification; only the
  final run supplies these totals.
- Independent source-location coverage accounted for all
  175,996 relevant bullets. The candidates contain
  118,598 events (118,459 leaves,
  139 event containers), 56,539 topics, and
  637 unknown entries. Every legacy emission maps to a retained
  source location; none is unmapped. `extraction-report.json` explains count
  deltas per date, including role promotions and omitted-depth recovery.
- All 8,831 original pinned baselines equal legacy replay. The 60 baseline
  mismatches are exactly the 58 new current-source captures and the two
  newly filled dates. New-source differences still need semantic review
  before canonical replacement; they are not all parser regressions.
- All 29 synthesis files passed schema, bibliography and related-event
  validation. Regeneration matched their parsed content. After the final
  Aleppo overlay, its file was regenerated and validated again.
- Separate processes using Python hash seeds 1 and 777 produced identical
  bytes for 29 synthesis documents and all 16 fixtures. The changed January
  10 output was rechecked after its last correction.
- AST checks passed for collection, synthesis, generator, test and
  reconciliation code. Workflow YAML and two embedded Python scripts
  parsed successfully. `git diff --check` passed for staged repair changes.
  GitHub Actions itself was not run. No lint/format command is configured.
- `python reference/reconciliation/summarize.py provisional/extraction-v1`
  generated the final report summary and queues. Real daily-page era spot
  checks cover flat, listed-category, semicolon, colon and bold formats;
  monthly rendered handling has a fixture, not a real historical capture.

### Source/network access and warnings

GitHub connector reads and `git fetch` supplied the published baseline.
Wikipedia acquisition used exact recorded oldids, the two newly filled
current-source dates, and the 58 explicitly selected current captures.
Publisher/government web reads verified focused synthesis corrections;
`publisher-spot-checks.json` records additional checks and access limits.
No GDELT query was performed. All parser tests and final corpus replay were
offline; no cached payload was edited.

The final parser emits 5,108 warning records: {"AMBIGUOUS_ROLE": 637, "DEPTH_JUMP": 26, "INLINE_TEMPLATE": 4091, "MALFORMED_MARKUP": 5, "ORPHAN_CATEGORY": 3, "ORPHAN_TOPIC": 5, "UNSUPPORTED_CITATION": 2, "UNSUPPORTED_CONTENT": 339}.
These expose formerly silent unsupported content rather than remove it.
`unresolved-roles.json` holds 655 warning records associated with 637 unknown
entries. Uncited prose parents are not assumed to be topic headers. Hidden
comments and citation annotations do not alter visible linked-header roles.
Source spelling/errors remain untouched. Orphan headings remain present and
warned about. General rules or guarded overrides must resolve interpretations;
no flat output was hand-edited to hide warnings.

### Remaining risks and next work

1. Finish the original-publisher review of January 10-15. The machine queue
   covers 118 events, including 35 portal-only entries and 18 later-publication
   flags. These are review leads, not proof that each flagged event is wrong.
   Quotations are matched to selected reports, not fully verified against
   publishers. Al Jazeera's liveblog body was unavailable in the focused
   check. No daily review status was promoted by this pass.
2. Re-review changed earlier January drafts. Only unchanged January 2-3 and
   5-7 retain their published reviewed status. January 1, 4, 8-9 and 10-15
   remain draft. January 16 is the next unresearched date; continue through
   January 31 before building a model-attributed monthly summary.
3. Resolve unknown extraction roles and material warnings, inspect source
   differences for the 58 new captures, and approve the exact public
   layout/schema and replacement range before replacing canonical output.
   Side-by-side generation and pinned-source mapping are complete for the
   available corpus, but this is not approval of public replacement.
4. The remaining 152 missing dates are 142 in 2002 and 10 in 2003. Their
   historical monthly-source acquisition/interpretation is a separate gap;
   the selected 58-date current-source policy does not settle it. Prefer
   pinned raw monthly input where possible and document any rendered-only
   provenance policy before historical backfill.
5. Live GDELT queries remain non-reproducible unless their complete inputs
   are cached. The artlist/theme limitation is unchanged and outside this
   Wikipedia migration. No push, PR publication or deployment was performed
   during that repair pass; subsequent branch publication is recorded below.

## October 5, 2026: branch publication and scoped publisher review

### Publication and changed scope

The completed repair work was pushed to `codex/repository-repairs`, at
`66a7d2bb9133773adf3ad71bfbf7873801d66c3b`. GitHub Actions run
`37402556671` succeeded. The remote default branch was not merged or
replaced. Provisional extraction remains separate and unpublished.

This follow-up changes seven synthesis outputs: January 4, 8, 9, 10, 11,
15 and March 18, 2026. Corresponding guarded overlays, the March overlay
manifest hash, authoring guidance, three prompt templates, all 15 January
conversion prompts, the review queue and publisher ledgers change with them.
`build.py` now accepts explicit additional bibliography records with actual
access dates; its regression check verifies the new March references.
January 11 uses one event guard, preserving the other events logically;
regeneration also normalizes its former authored serialization. The exact
semantic event changes are listed in `publisher-review/verification.json`.
No ordinary daily extraction, raw source cache, authored snapshot or original
research report was changed. Event IDs and counts remain unchanged.

### Findings and durable corrections

- CBS and affiliates receive no assumed reliability in synthesis. The
  authoring guide and prompts require independent material-claim support,
  distinguish wire copies from independent reporting, and retain uncertainty.
  The machine queue flags future active CBS citations for corroboration.
  Seven previously active CBS citations have been replaced by independently
  assessed support. Historical CBS bibliography and immutable input evidence
  remain preserved; this policy does not presume every CBS statement false.
- January 10 now has observations for all 15 events. Corrections qualify
  blackout observation times, publisher dates, strike chronology, Cebu counts,
  crash-cause uncertainty, xAI attribution, future embassy handback, projected
  parliamentary figures, earthquake agency differences and the recirculated
  December Honduran pledge. Its overview and conclusion regenerate with those
  corrections. January 10 remains a draft, with access and quote checks pending.
- Focused checks of the other CBS-linked events corroborate victim
  identification, the Iran outage, the Minnesota deployment and recall counts.
  The unsupported repeated-fatal-attack claim and exact officer-arrival schedule
  are excluded. The two primary recall notices disagree on the earlier recall
  date; that disagreement is explicit, and Target exclusivity applies only to
  the new model. The March arrest entry now distinguishes allegations from
  guilt, leaves legal transfer status unspecified and records conflicting
  arrest-site accounts instead of asserting operational effects.

### Commands, checks and source access actually performed

- `git fetch origin`, `git push --set-upstream origin codex/repository-repairs`,
  remote-head checks and `gh run list`: original repairs pushed; CI succeeded.
- `python reference/expansion/build.py` for the seven dates above: all outputs
  rebuilt with schema/reference validation and structural YAML round trips.
- `python generate_prompts.py` for January 1-15 with `--include-reviewed`:
  prompts refreshed; January 11 regenerated again after narrowing its guard.
- `python reference/expansion/review.py` for January 10-15: 118 event leads,
  30 portal-only flags and 21 later-publication flags. These are review leads,
  not defect certifications. Corrected files remain draft.
- `python -m unittest discover -s tests -v`: all 20 methods passed, including
  16 golden fixtures, offline extraction/replay, drift guards, bibliography
  support and the new actual-access-date regression check.
- Batch `reference/schema/validate.py` with `--archive-root expanded`: all
  29 synthesis files passed schema, bibliography and related-event validation.
- An inline verification harness blocked socket connections and requests,
  built the seven changed dates in separate processes with hash seeds 1 and
  777, and matched every output byte hash. It checked 22 ledger event guards,
  unchanged event IDs/counts, no active CBS synthesis source records and no
  changes to immutable or ordinary daily input paths. Results are recorded in
  `reference/reconciliation/publisher-review/verification.json`.
- `git diff --check` passed. The full 8,891-date extraction replay was not
  repeated because extraction code and inputs did not change in this pass.

Network access comprised GitHub fetch/push/status and publisher/government
web reads, including AP, Reuters syndications, CPSC, VIPD and other sources
named in the ledgers. No Wikipedia reacquisition or GDELT query occurred.
Publisher pages were read live; no full articles or new exact quotation
strings were copied into the repository. The ledgers distinguish article
reads, indexed-only retrieval, inaccessible pages and sources not checked.

### Limits and next work

The January 10 publisher pass is partial: inaccessible articles, exact quote
comparisons, the original Honduras video and several independently unverified
claims remain open. The CBS assessment is a focused core-claim check, not
complete review of those days. No human-reviewed status was granted.
Parser warning totals are unchanged; new synthesis uncertainty notes expose
remaining date, attribution and source conflicts. Publisher pages may change;
these dated observations are not immutable publisher replay inputs.

Continue the complete January 11-15 publisher review and finish January 10's
remaining checks. Re-review the changed earlier drafts before marking any day
reviewed. January 16 remains the next unresearched date. Canonical extraction
replacement, unknown-role resolution and historical backfill still require
the separate decisions described in the prior work pass.

### CI follow-up

The synthesis follow-up was pushed as `b8cb854e`; run `37404538403`
passed. Its annotations exposed deprecated action runtimes and a pending
`ubuntu-latest` image transition. Both workflows now use the documented
`actions/checkout@v7` and `actions/setup-python@v7` Node 24 actions, with
`ubuntu-24.04` selected explicitly. The upstream action definitions and tags
were verified through official GitHub web/API reads. Workflow YAML and both
embedded Python blocks were parsed, and `git diff --check` passed. The
scheduled publishing workflow was not dispatched for this check; doing so
would acquire and publish new daily data. This small follow-up changes only
the two workflow files and this handoff; no corpus or source inputs change.

## October 20, 2026: January 16, 2026 expansion and SQLite-first archive contract

### Changes and files

- Authored deep-research report `reference/deep-research/2026/01/2026-01-16a.md` covering all nine Wikipedia portal items from pinned revision `1334014870` (`reference/sources/wikipedia/wikitext/1334014870.wiki`) plus five global broad-sweep developments (14 events total, 27 external primary/wire/major-outlet sources with exact URLs, publication dates, and verbatim quotes).
- Registered `2026-01-16` in `reference/expansion/inputs.json` (`mode: "build"`) with all five SHA-256 drift guards (`report_sha256`, `portal_sha256`, `portal_items_sha256`, `report_events_sha256`, `overlay_sha256`).
- Added guarded overlay `reference/expansion/overlays/2026-01-16.json` (importance overrides, `time_detail` strings, internal `related` pair `md:5`/`md:6`, and cross-day `related_events` links to earlier January 2026 events) and updated `reference/expansion/roles.json` with 53 person/organization role entries and 3 `__as_org__` entries (`South African National Parks`, `National Unity Platform`, `Northrop Grumman`).
- Generated `expanded/2026/01/2026-01-16.yaml` (`status: draft`, `reviewed: false`) via `python reference/expansion/build.py 2026-01-16` and `copilot_prompts/agent_prompt_2026-01-16.txt` via `python generate_prompts.py 2026-01-16`.
- Documented the side-by-side SQLite-first storage and view-export architecture in `reference/schema/SQLITE_ARCHITECTURE.md` (`schema_version: sqlite-archive-1.0`) and implemented `seed/sqlite_archive.py` plus unit tests in `tests/test_sqlite_archive.py`.
- Populated `provisional/archive.sqlite` (30 expanded synthesis days and 31 January 2026 `extraction-1.0` candidate days) and exported daily (`provisional/views/2026-01-16.rst`) and monthly (`provisional/views/2026-01.rst`) reStructuredText views. Updated `.gitignore` to keep `/provisional/archive.sqlite` and `/provisional/views/` separate from canonical paths.

### Verification actually run

- `python reference/expansion/build.py 2026-01-16`: built `expanded/2026/01/2026-01-16.yaml` offline from pinned wikitext `1334014870` and `2026-01-16a.md`.
- `python reference/schema/validate.py --archive-root expanded` across all 30 files in `expanded/` (`2026-01-01` through `2026-01-16` and `2026-03-05` through `2026-03-18`): all 30 passed schema, bibliography, and cross-day `related_events` checks.
- `reference/expansion/review.py` on `2026-01-16`: 14 events checked, 0 machine flags (`PORTAL_ONLY`, `INDEPENDENT_CORROBORATION_REQUIRED`, `URL_NOT_IN_SELECTED_INPUT`, `HOMEPAGE_ONLY`, `LATER_PUBLICATION`, `QUOTE_NOT_IN_SELECTED_REPORT` all zero).
- `python -m unittest discover -s tests -v`: 24 unit tests passed offline (including 4 new tests in `tests/test_sqlite_archive.py` verifying lossless `extraction-1.0`, `rendered_html`, and `synthesis-2.2` SQLite round-trips, byte-identical YAML dumps, FTS5 search, and `.rst` daily/monthly export).

### Remaining risks and next steps

- `expanded/2026/01/2026-01-16.yaml` remains `status: draft` and `reviewed: false` pending explicit human/publisher review.
- Continue deep research and schema-2.2 expansion for **January 17–31, 2026** (`2026-01-17` is the next unresearched date), then generate the complete January 2026 monthly synthesis report.
- `seed/sqlite_archive.py` operates side-by-side (`provisional/archive.sqlite`) until full corpus cutover is approved.

## October 20, 2026: Per-day SQLite (`<YYYY>/<MM>/<YYYY-MM-DD>.sqlite`) and multi-source archive starting at 2000-01-01

### Scope and design decisions

- Established the per-day compact SQLite layout (`<YYYY>/<MM>/<YYYY-MM-DD>.sqlite`) starting from the chronological beginning of the century (`2000-01-01` and `2000-01-02`) so that no existing `2002–2026` files need to be deleted during the historical build-out.
- Defined the **3-Tier Daily Scope & Granularity Standard** in `reference/schema/SQLITE_ARCHITECTURE.md`:
  - **Tier 1 — Global & Systemic (`importance 8–10`, 1–3 events/day)**: Sovereign leadership transitions, wars/ceasefires, global infrastructure milestones, M6.5+ or destructive earthquakes, and systemic macro shocks.
  - **Tier 2 — Major National & Sectoral (`importance 5–7`, 5–8 events/day)**: National elections/legislation, major insurgencies/clashes, bilateral summits, M4.5–6.4 felt earthquakes, and major aviation/maritime crises.
  - **Tier 3 — Archival & Digest (`importance 1–4`, 2–5 events/day)**: Cultural/scientific milestones, notable ceremonies, and localized incidents needed for complete daily coverage.
  - Raw structured feeds (all USGS M4.5+ earthquakes, Wikidata day-precision items, and deduplicated GDELT 1.0 CAMEO event clusters) are stored in `structured_feed_items` inside each day's `.sqlite` database without bloating the curated `synthesis_events` narrative table.

### Changes and files

- Added multi-source acquisition and offline parser `seed/multisource.py`:
  - **Layer 1 (Wikipedia retrospective + Wikidata SPARQL)**: Cached revision-pinned Wikipedia wikitext for `2000` (`1380003199`), `2000 in the United States` (`1380499372`), `2000 in the United Kingdom` (`1379961343`), `2000 in Australia` (`1346965372`), `January 1` (`1380939391`), and `January 2` (`1379393571`) under `reference/sources/wikipedia/`, indexed in `reference/sources/wikipedia_retrospective/2000.json`. Cached Wikidata SPARQL day-precision (`wikibase:timePrecision 11`) event payloads in `reference/sources/wikidata/2000-01-01.json` and `2000-01-02.json`.
  - **Layer 2 (USGS ComCat GeoJSON)**: Cached `minmagnitude=4.5` earthquake feeds in `reference/sources/usgs/2000-01-01.json` (11 earthquakes, including `usp0009kmr`, the M5.2 Kipawa earthquake in Quebec/Ontario) and `reference/sources/usgs/2000-01-02.json` (8 earthquakes, including twin M5.8 earthquakes in Adak, Alaska `usp0009kng` and Kolonga, Tonga `usp0009knu`). Note: ReliefWeb API v1 returns `410 Gone` and v2 requires a pre-approved `appname`.
  - **Layer 3 (Contemporary open news & government archives)**: Integrated primary and contemporary reporting from BBC News (2000 archive), The Guardian, The Washington Post, The Telegraph, Kremlin Transcripts, U.S. Department of State, Indian Ministry of External Affairs, National Archives of Australia, Natural Resources Canada, and the American Presidency Project.
  - **Layer 4 (GDELT 1.0 historical CAMEO events)**: Streamed `https://data.gdeltproject.org/events/2000.zip` via HTTP chunked range streaming and cached daily summaries plus top 25 deduplicated CAMEO event clusters in `reference/sources/gdelt_v1/2000-01-01.json` (`6,361` total CAMEO rows, `45,879` mentions) and `reference/sources/gdelt_v1/2000-01-02.json` (`5,446` total CAMEO rows, `29,884` mentions). Documented the GDELT 1.0 Tripoli (`LBY` vs `LBN`) geocoding error in the `2000-01-01` synthesis uncertainty notes.
- Extended `reference/expansion/wikiportal.py` so `parse_structured()` falls back to `reference/sources/wikipedia_retrospective/<YYYY>.json` for 2000–2001 dates while preserving SHA-256 verification.
- Authored deep-research reports `reference/deep-research/2000/01/2000-01-01a.md` (13 events, 17 works cited) and `reference/deep-research/2000/01/2000-01-02a.md` (10 events, 14 works cited, 5 cross-day `related_events` links to `2000-01-01`), overlays `reference/expansion/overlays/2000-01-01.json` and `2000-01-02.json`, role entries in `reference/expansion/roles.json`, and input guards in `reference/expansion/inputs.json`.
- Built `expanded/2000/01/2000-01-01.yaml` and `expanded/2000/01/2000-01-02.yaml` via `reference/expansion/build.py`.
- Upgraded `seed/sqlite_archive.py` and `reference/schema/SQLITE_ARCHITECTURE.md` (`schema_version: sqlite-archive-1.1`) with compact 1 KB page size (`PRAGMA page_size = 1024; PRAGMA journal_mode = DELETE; VACUUM;`), `raw_sources`, `structured_feed_items`, `synthesis_actors_entities`, `tier` (`1`, `2`, `3`), `build-day-db`, and `rollup` CLI subcommands.
- Built canonical per-day SQLite files `2000/01/2000-01-01.sqlite` (189,440 bytes), `2000/01/2000-01-02.sqlite` (150,528 bytes), `2000/01/2000-01-03.sqlite` (192,512 bytes), `2000/01/2000-01-04.sqlite` (189,440 bytes), and `2000/01/2000-01-05.sqlite` (190,464 bytes), rolled all 5 days up into `provisional/2000-01.sqlite` (1,105,920 bytes), and exported daily `.rst` views (`provisional/views/2000-01-01.rst` through `2000-01-05.rst`) and the monthly rollup (`provisional/views/2000-01.rst`).
- Expanded `seed/multisource.py` to cache 18 year-2000 retrospective/country/topical Wikipedia pages (`2000`, `2000 in the United States`, `2000 in Canada`, `2000 in the United Kingdom`, `2000 in Ireland`, `2000 in France`, `2000 in Germany`, `2000 in Russia`, `2000 in Israel`, `2000 in India`, `2000 in China`, `2000 in Japan`, `2000 in South Africa`, `2000 in Australia`, `2000 in New Zealand`, `2000 in aviation`, `2000 in science`, `2000 in spaceflight`) plus day-of-year pages (`January 1` through `January 5`), and added country-diversified GDELT 1.0 CAMEO cluster extraction (up to 35 clusters/day) across `2000-01-01` through `2000-01-05`.
- Authored `reference/deep-research/2000/01/2000-01-03a.md` (15 events, 17 works cited), `2000-01-04a.md` (15 events, 19 works cited), and `2000-01-05a.md` (15 events, 19 works cited), overlays `2000-01-03.json`, `2000-01-04.json`, and `2000-01-05.json`, and generated `expanded/2000/01/2000-01-03.yaml`, `2000-01-04.yaml`, and `2000-01-05.yaml` at the single-pass comprehensive daily standard (15–18 global events per day).

### Verification actually run

- `python reference/expansion/build.py 2000-01-01 2000-01-02 2000-01-03 2000-01-04 2000-01-05`: generated `expanded/2000/01/2000-01-01.yaml` through `2000-01-05.yaml` offline from cached inputs.
- `python reference/schema/validate.py --archive-root expanded` across all 35 files in `expanded/` (`2000-01-01..05`, `2026-01-01..16`, `2026-03-05..18`): all 35 passed JSON Schema, bibliography, and cross-day `related_events` checks.
- `review.review(["2000-01-01", "2000-01-02", "2000-01-03", "2000-01-04", "2000-01-05"])`: 68 events checked; 0 `PORTAL_ONLY`, 0 `INDEPENDENT_CORROBORATION_REQUIRED`, 0 `URL_NOT_IN_SELECTED_INPUT`, 0 `HOMEPAGE_ONLY`, and 0 `QUOTE_NOT_IN_SELECTED_REPORT` flags.
- `python -m unittest discover -s tests -v`: all 25 unit tests passed offline, including `test_per_day_compact_sqlite_multisource_and_rollup` verifying 1 KB page size (`PRAGMA page_size = 1024`), `raw_sources`, `structured_feed_items`, `synthesis_actors_entities`, `tier` classification, lossless schema-2.2 export, and monthly rollup FTS5 search.

### Remaining risks and next steps

- `expanded/2000/01/2000-01-01.yaml` through `2000-01-05.yaml` remain `status: draft` and `reviewed: false` pending explicit human review.
- Continue acquiring multi-source feeds and building per-day `.sqlite` files for **January 6–10, 2000 (`2000-01-06` through `2000-01-10`)** at the single-pass 15–18 event daily standard.

## October 21, 2026: January 6–10, 2000 (`2000-01-06` to `2000-01-10`) multi-source acquisition, synthesis, and per-day SQLite archive

### Changes and files

- Executed `python -m seed.multisource acquire 2000-01-06 2000-01-07 2000-01-08 2000-01-09 2000-01-10` to acquire and immutably cache all four source layers for January 6–10, 2000:
  - **Layer 1 (Wikipedia retrospective + Wikidata SPARQL)**: Cached revision-pinned Wikipedia day-of-year wikitext for `January 6` (`1346798144`), `January 7` (`1346638909`), `January 8` (`1346962004`), `January 9` (`1346642442`), and `January 10` (`1346965031`) under `reference/sources/wikipedia/` and updated `reference/sources/wikipedia_retrospective/2000.json` while preserving all existing 2000 page revisions. Cached Wikidata SPARQL day-precision (`wikibase:timePrecision 11`) event payloads in `reference/sources/wikidata/2000-01-06.json` through `2000-01-10.json`.
  - **Layer 2 (USGS ComCat GeoJSON)**: Cached `minmagnitude=4.5` earthquake feeds in `reference/sources/usgs/2000-01-06.json` (8 earthquakes, including the `M5.8` Juneau/Haines, Alaska earthquake `usp0009kwe` and `M5.1` Zambales, Luzon earthquake `usp0009kwr`), `2000-01-07.json` (7 earthquakes, including `M5.0` Luzon `usp0009kxm`), `2000-01-08.json` (22 earthquakes, including `M7.2` Tongan Islands `usp0009kzv`, `M6.5` Solomon Islands `usp0009kzd`, and `M6.4` Woodlark Basin `usp0009kyn`), `2000-01-09.json` (10 earthquakes, including `M6.5` Fiji `usp0009m12`), and `2000-01-10.json` (3 earthquakes).
  - **Layer 3 (Contemporary open news & government archives)**: Integrated primary and contemporary reporting from BBC News (2000 archive), The Guardian, The New York Times, The Washington Post, Los Angeles Times, CNN Money, Financial Times, Deseret News, The Irish Times, The Christian Science Monitor, U.S. Department of Labor (`BLS`), Federal Reserve Board, USGS, and Swiss `AAIB` Final Report No. 1781.
  - **Layer 4 (GDELT 1.0 historical CAMEO events)**: Streamed `https://data.gdeltproject.org/events/2000.zip` and cached daily summaries plus top 35 country-diversified CAMEO event clusters in `reference/sources/gdelt_v1/2000-01-06.json` (`11,297` rows, `55,007` mentions), `2000-01-07.json` (`10,636` rows, `50,829` mentions), `2000-01-08.json` (`5,637` rows, `27,006` mentions), `2000-01-09.json` (`6,003` rows, `29,745` mentions), and `2000-01-10.json` (`11,648` rows, `55,392` mentions). Documented the GDELT 1.0 Chechnya geocoding errors (`Argun` -> `Irkutskaya Oblast'`, `Shali` -> `Tatarstan` on `2000-01-09`) and the `January 10` Wikipedia anniversary page fatality discrepancy for Crossair Flight 498 (`13` vs. `10` confirmed fatalities) in the synthesis uncertainty notes.
- Updated `reference/expansion/wikiportal.py` so `parse_structured()` deduplicates repeated retrospective bullets across `2000` and topical/country pages for `date >= "2000-01-06"` (merging their external citations) while keeping `2000-01-01` through `2000-01-05` byte-identical.
- Authored single-pass comprehensive deep-research reports (`15 events/day` across Tiers 1, 2, and 3) and guarded overlays for January 6–10, 2000:
  - `reference/deep-research/2000/01/2000-01-06a.md` + `reference/expansion/overlays/2000-01-06.json` (15 events, 20 works cited; covers the collapse of the 17th Karmapa Urgyen Trinley Dorje's custody in Dharamshala, Bradley/Gore New Hampshire debate, Yeltsin in Bethlehem, Russian election registration & Chechnya, Mumbai IC-814 arrests, extinction of the Pyrenean ibex Celia, Sri Lanka Colombo sweeps, King Abdullah II in Moscow, Orthodox Epiphany summit, Lagos OPC police sweeps, Khmer Rouge trial talks, Northern Alliance offensive in Samangan, M5.8 Southeast Alaska & M5.1 Luzon earthquakes, and death of GM Alexey Vyzmanavin).
  - `reference/deep-research/2000/01/2000-01-07a.md` + `reference/expansion/overlays/2000-01-07.json` (15 events, 17 works cited; covers Russian ceasefire suspension & Grozny ultimatum, China's condemnation of the Karmapa's flight, Beverley McLachlin sworn in as Chief Justice of Canada, U.S. December jobs report & Dow record 11,522.56, Jakarta Ambon jihad rally, Konrad Kalejs deported from UK to Australia, Israel–Syria Shepherdstown talks Day 5, General Klaus Reinhardt apologizing after Orahovac search, 22 bodies found at Diyarbakır Hezbollah safe house, Colombian FARC/military clashes, M5.0 Luzon earthquake, and deaths of Makhmud Esambayev, Klaus Wennemann, and Gary Albright).
  - `reference/deep-research/2000/01/2000-01-08a.md` + `reference/expansion/overlays/2000-01-08.json` (15 events, 19 works cited; covers President Clinton publishing draft U.S. working paper at Shepherdstown, Chechen counter-offensive at Shali/Argun/Gudermes, China charging scholar Song Yongyi, M7.2 Tongan Islands and M6.5 Solomon Islands earthquakes, Angolan army capturing Jamba, Tennessee Titans' "Music City Miracle", Bashir–Garang peace talks, SFOR raid for Radovan Karadžić in Pale, Pope John Paul II naming 32 new saints, South Carolina GOP debate, Spanish megacryometeor ice falls, Bill D'Arcy conviction in Queensland, and deaths of Fritz Thiedemann and Hilary Smart).
  - `reference/deep-research/2000/01/2000-01-09a.md` + `reference/expansion/overlays/2000-01-09.json` (15 events, 19 works cited; covers Islam Karimov's 91.9% re-election in Uzbekistan, Russia sealing Chechen border to males aged 10–60 and bombing Shali/Argun, 150,000-strong Tel Aviv pro-Golan rally, U.S. Central Command report on Operation Southern Watch, Turkish coalition summit on Abdullah Öcalan, German bishops defying Pope on abortion counseling, British Customs intercepting Scud missile parts for Libya, U.S. Army ordering No Gun Ri probe, Italian Coast Guard rescuing 752 Kurdish/Iraqi migrants in Otranto Channel, M6.5 Fiji earthquake, *The Sixth Sense* VHS/DVD milestone, deaths of Sir Arnold Hall and Nigel Tranter, and secret Sunday board approval of the AOL–Time Warner merger).
  - `reference/deep-research/2000/01/2000-01-10a.md` + `reference/expansion/overlays/2000-01-10.json` (15 events, 20 works cited; covers the $162B–$165B AOL–Time Warner merger announcement, Crossair Flight 498 crash near Zurich killing 10, adjournment of Round 1 of Shepherdstown Israel–Syria talks, Iranian FM Kamal Kharrazi's historic London visit, CDU Chairman Wolfgang Schäuble's confession of 100,000 DM Schreiber cash donation, Putin promoting Mikhail Kasyanov and firing Pavel Borodin, Russian forces retaking central Argun, Florida court granting temporary custody of Elián González to Lazaro González, 16 Serbian opposition parties signing joint anti-Milošević pact, Australia's CASA grounding 5,000 piston aircraft over Mobil fuel contamination, Boeing cutting 6,500 jobs, German rail strike warning, Cherie Blair ticket fine, death of producer Sam Jaffe, and Tajik parliamentary election date announcement).
- Registered `2000-01-06` through `2000-01-10` in `reference/expansion/inputs.json`, added 75 person/organization entries and 4 `__as_org__` entries (`Holy See`, `Royal Aircraft Establishment`, `America Online`, `Time Warner`, `Ordesa y Monte Perdido National Park`) to `reference/expansion/roles.json`, and generated `expanded/2000/01/2000-01-06.yaml` through `2000-01-10.yaml`.
- Built compact per-day SQLite files `2000/01/2000-01-06.sqlite` (194,560 bytes), `2000/01/2000-01-07.sqlite` (182,272 bytes), `2000/01/2000-01-08.sqlite` (193,536 bytes), `2000/01/2000-01-09.sqlite` (185,344 bytes), and `2000/01/2000-01-10.sqlite` (203,776 bytes), rolled all 10 days (`2000-01-01` to `2000-01-10`) into `provisional/2000-01.sqlite` (1,871,872 bytes), and exported `.rst` views for `2000-01-06` through `2000-01-10` and `2000-01` under `provisional/views/`.

### Verification actually run

- `python -X utf8 reference/expansion/build.py --todo 2000-01-06 2000-01-07 2000-01-08 2000-01-09 2000-01-10`: `0` missing entity roles or organization descriptions across all 5 days.
- `python -X utf8 reference/expansion/build.py 2000-01-06 2000-01-07 2000-01-08 2000-01-09 2000-01-10`: built `expanded/2000/01/2000-01-06.yaml` through `2000-01-10.yaml` offline from cached inputs.
- `python reference/schema/validate.py --archive-root expanded` across all 40 files in `expanded/` (`2000-01-01..10`, `2026-01-01..16`, `2026-03-05..18`): all 40 passed JSON Schema, bibliography, and cross-day `related_events` checks.
- `review.review(["2000-01-06", "2000-01-07", "2000-01-08", "2000-01-09", "2000-01-10"])`: 75 events checked; `0` `PORTAL_ONLY`, `0` `INDEPENDENT_CORROBORATION_REQUIRED`, `0` `URL_NOT_IN_SELECTED_INPUT`, `0` `HOMEPAGE_ONLY`, and `0` `QUOTE_NOT_IN_SELECTED_REPORT` flags (`LATER_PUBLICATION` informational notes only on retrospective/next-day print editions).
- `python -m unittest discover -s tests -v`: all 25 unit tests passed offline (`Ran 25 tests in 16.652s — OK`).

### Remaining risks and next steps

- `expanded/2000/01/2000-01-01.yaml` through `2000-01-10.yaml` remain `status: draft` and `reviewed: false` pending explicit human review.
- Continue acquiring multi-source feeds and building per-day `.sqlite` files for **January 11–15, 2000 (`2000-01-11` through `2000-01-15`)** at the single-pass 15–18 event daily standard.

## October 21, 2026: Annual SQLite destination and initial 2025 migration

This section supersedes the preceding next-step recommendation. The selected
priority is a self-contained annual SQLite reference archive, starting with
2025. The user approved designing the fields and structure for eventual
yearbook use, incremental daily ingestion, and replacement of other annual
material only after verification. No cutover or deletion has occurred.

### Changes and files

- Added `reference/schema/ANNUAL_ARCHIVE.md` and `annual-archive.sql` defining
  `annual-archive-1.0`, ordering/null semantics, pinned source policy, embedded
  evidence, source/editorial separation, and explicit replacement/yearbook gates.
- Added `seed/annual_archive.py`: offline annual build, transactional per-day
  ingestion, immutable embedded input identities, original-byte preservation,
  source replay, reconciliation, browseable views, source-event FTS, and atomic
  database replacement. A source-only rebuild refuses to discard research.
- The annual schema incorporates the existing lossless extraction/synthesis
  bridge and adds claim evidence, generation provenance, ordered yearbook
  sections, self-contained blobs/input manifests, and internal check reports.
  Existing per-day SQLite files and other years are unchanged.
- Created `archive/2025.sqlite` (25,628,672 bytes; SHA-256
  `065f15d534291cc68ec9a934147f9936959c69320b280ffa55810ec213e7d650`).
  It contains all 365 days, 5,454 event leaves, 10,096 total structural entries,
  6,595 citations, and 32,000 wikilinks. There are no researched 2025 synthesis
  inputs in the repository; no model-generated historical prose was invented.
- Added `tests/test_annual_archive.py`; updated root `README.md`,
  `.gitattributes`, and `.gitignore`. No permanent daily outputs or external
  report files were generated. The verification report is `archive_checks` in
  the database; unresolved issues are visible through `review_queue`.

### Commands and verification actually run

- Inspected Git status, the existing schemas/bridge/parser/source cache,
  authoring/migration documentation, and a complete 2025 input inventory.
  The worktree started clean at `26843942` on `codex/repository-repairs`.
- `python -X utf8 -m seed.annual_archive build 2025`: complete offline build
  and verification, followed by atomic installation of the candidate database.
- `python -X utf8 -m seed.annual_archive verify archive/2025.sqlite`: a second,
  independent process passed integrity/foreign-key checks, exact embedded
  payload hashes, complete calendar coverage, extraction schema validation,
  parent/order/source-bullet checks, canonical structural round trips,
  repeated-parser idempotence, legacy item mapping/leaf reconciliation,
  GDELT preservation and source-event search reconciliation. Socket connection
  attempts were blocked during parsing and replay. Every prior 2025 candidate
  matched; every old seed matched the legacy parser on the same pinned source.
- Compared embedded hashes against all 1,104 corresponding existing files:
  zero byte differences. The additional embedded input is the generated bridge
  SQL definition. No source inputs were mutated.
- Manually compared source and extracted structures on January 1, July 1,
  September 1 (top/bottom wrapper variant), and December 31. This was a
  structural check, not publisher-level verification of the events.
- `python -m unittest discover -s tests -v`: 30 tests passed before adding the
  last research-preservation case. Then
  `python -m unittest discover -s tests -p test_annual_archive.py -v`: all six
  annual tests passed, including the additional case. Tests cover day rollback
  across nested bridge transactions, atomic failed builds, exact CRLF input
  preservation, idempotent ingestion, hash/content/search corruption, date/year
  checks, incomplete calendars, and protection of existing research.
- `git diff --check`: passed. No commit or push performed. No network or new
  source acquisition performed in this implementation pass.

### Warnings, limits, and next step

- All 140 existing unresolved 2025 warnings remain explicit: 122
  `INLINE_TEMPLATE`, nine `AMBIGUOUS_ROLE`, and nine `UNSUPPORTED_CONTENT`.
  Nine entries retain the structural role `unknown`. None were guessed away;
  no parser warnings were introduced or resolved in this pass.
- Migration correctness is verified; factual coverage and yearbook readiness
  are not. The internal report explicitly sets `replacement_ready=false` and
  `yearbook_ready=false`. No full publisher review, yearbook prose, or PDF was
  produced. A pinned Wikipedia capture may postdate its event date.
- Keep all old 2025 daily files and shared immutable source caches until the
  documented replacement gate passes. Embedding a shared source does not
  establish that other years/tools no longer depend on its filesystem copy.
- Next: resolve the 2025 extraction queue through tested general rules or
  guarded source interpretations, then perform factual/coverage review and
  add researched material directly to the annual container. Before deletion,
  produce a dependency-checked exact manifest, preserve a Git checkpoint, and
  migrate affected consumers. Do not resume the 2000 five-day expansion by
  default. Current verification requires the recorded parser/tool implementation;
  changing it requires an explicit archive replay/migration, not silent drift.

## October 21, 2026: 2025 extraction reconciliation and initial factual coverage review

### Scope and result

The original 2025 extraction queue is reconciled. Factual review is explicitly
partial. No legacy daily files or immutable source caches were removed, and no
yearbook-ready or complete factual-review claim is made.

The user selected preservation of the malformed May 6 football passage as
unclassified source material, with a separate factual-research lead. Do not
promote it into an inferred sports category or extraction event.

### Changed files and behavior

- `seed/inline.py` and `seed/extract.py`: conservative projections of explicit
  inline-template arguments, interlanguage target/surface capture with unknown
  red-link state, portal metadata notices, citation-only continuation handling,
  nominal topic labels, retained reliability tags, and retention of unexpected
  portal parameters after unescaped pipes. No unit conversion, live exchange
  rate, source spelling correction, or Wikipedia refetch occurs.
- The annual builder explicitly selects `source_templates=True`. Existing
  synthesis/seed callers retain the historical default interpretation profile.
  An initial test caught changed interpretation in the March 11, 2026 positional
  synthesis overlay; this was fixed through profile isolation. No historical
  guard hashes or 2026 generated outputs were changed to bypass the failure.
- Added `reference/overrides/2025-extraction.json`: two exact guarded nominal
  heading interpretations and five guarded unclassified-fragment retentions.
  Locators use date, source hash and raw-fragment hash, with source path/category
  or warning code/line. A role override no longer resolves unrelated warnings.
- `reference/schema/annual-archive.sql`, `ANNUAL_ARCHIVE.md`, and
  `seed/annual_archive.py`: version `annual-archive-1.1`, explicit side-by-side
  migration, normalized scoped review/evidence tables, a factual-review queue,
  complete-calendar coverage census, and per-entry prior-candidate delta checks.
  The extraction JSON shape remains `extraction-1.0`.
- Extended `tests/test_extraction.py`, `tests/test_annual_archive.py`; added
  exact-input golden fixtures `tests/fixtures/template_arguments.wiki` and
  `.json`. Updated root `README.md` and this handoff.
- Replaced only the initial annual candidate `archive/2025.sqlite` after
  separate candidate verification and comparison. The original container is
  preserved in a local temporary checkpoint outside the repository. Its hash
  is recorded in the internal comparison report; no private local path is
  written into repository artifacts.

### Current annual database

- `archive/2025.sqlite`: 25,870,336 bytes; SHA-256
  `9fe1b43abbc5467c119b75ec03583240266c4ea58d501a694f18e78269fd5318`.
- All 365 dates, 5,453 nonempty event entries/leaves, 6,596 citations and 32,025
  structured links. Nine formerly unknown headings are topics. The event-leaf
  delta is -1: one literal empty bullet is now a known marker rather than an
  event. No nonempty event content was removed. There are 120 changed entries
  across 95 days, explained through template argument projection, source topic
  rules/guards, one citation continuation or the empty-marker rule.
- The old and new annual containers have identical identities/bytes for all
  1,095 original daily seed, Wikipedia payload and source-metadata inputs.
  Filesystem inputs were also checked after installation: no hash differences.
- There are zero unresolved extraction warnings and zero unknown heading roles.
  One known empty marker retains the existing `unknown` structural role,
  separately reported from ambiguous headings and excluded from event/search
  counts. All 10,096 original structural entries remain represented.
  Audit notices remain: 121 `SOURCE_TEMPLATE`, five `SOURCE_METADATA`, one
  `CITATION_CONTINUATION`, one `SOURCE_RELIABILITY_TAG`, two guarded
  `AMBIGUOUS_ROLE`, three guarded `UNSUPPORTED_CONTENT` and two guarded
  `UNASSIGNED_TEMPLATE_PARAMETER`, plus one `SOURCE_EMPTY_MARKER` (136 resolved
  notices total).
- The five unclassified fragments all belong to the one May 6 passage, not
  five missing events. Extra portal parameters previously concealed by an
  unescaped pipe are now explicit retained evidence. UEFA independently
  supports the football result in an embedded research lead; extraction remains
  unclassified as selected.
- Seven nonempty source event entries have no attached citation. The literal
  empty `*` bullet on July 5 is preserved with a resolved notice under the
  existing extraction contract's `unknown` role and excluded from event/search
  counts and yearbook narrative. The seven uncited events remain identifiable
  in the coverage census; some now have separate publisher
  evidence, which is not written back into Wikipedia extraction.

### Factual coverage and findings

The complete-calendar census is stored as `archive_checks.coverage`.
`factual_reviews`, `review_evidence`, `factual_review_queue` and immutable
embedded review records expose the partial publisher/source review. There are
17 scoped records across all twelve months: seven supported within scope,
five partially supported, three contradicted and two needing research.
There are 5,436 event entries without such a record. A record may concern only
one claim; it never approves the entire event, day or year.

Three concrete discrepancies were recorded without changing source text:

- January 25 women's doubles final: the Australian Open organizer places the
  final on January 26. Winners and score match; calendar placement differs.
- April 2 tariff entry: the official announcement distinguishes the April 5
  baseline tariff from higher reciprocal rates effective April 9 and lists
  exclusions. The portal's combined effective-date statement is misleading.
- September 8 Nepal protests: the cited Sky body gives 17 deaths in Kathmandu
  and two in Itahari; the portal sentence assigns all 19 to Kathmandu.

Additional limits include rolling casualty totals for Myanmar, Texas and
Bondi; a source-marked unreliable military claim; and insufficient opened
evidence for detailed 99-year Armenia corridor terms. Failed publisher access
is recorded as an access limit, not as evidence that a claim is false. Original
raw source claims, errors, dates and citations remain intact.

### Commands, network access and verification actually run

- Inspected every original warning, template family and all nine ambiguous
  heading contexts from cached source. Checked template documentation through
  Wikipedia pages. Publisher browsing included the Australian Open, UEFA,
  Bundestag, German election authority, White House, Vatican News, GSI Japan,
  Nobel Committee, Armenian prime minister, Sky, El Pais, UConn-hosted AP, NWS,
  ABC Australia and initial AAIB report text. Several other original citations
  were blocked, unavailable or timed out. No raw-source acquisition cache was
  rewritten, and no GDELT request was made.
- `python -m unittest discover -s tests -p test_extraction.py -v`: passed during
  fixture work. Final `python -m unittest discover -s tests -v`: all 37 tests
  passed after correcting the March synthesis compatibility regression. Tests
  include network-blocked parsing, new golden fixtures, source-only numeric
  projections, guarded interpretation drift, source citation continuation,
  extra portal parameters, empty source markers, scoped review corruption and
  event-loss rejection.
- In-memory side-by-side checks covered all 365 inputs before rebuilding.
- `python -X utf8 -m seed.annual_archive build 2025 --output
  archive/.2025-review.sqlite`, followed by a final marker-corrected build to
  `archive/.2025-final.sqlite`: complete verified offline candidate builds.
  Earlier provisional builds were stopped while correcting the interpretation
  profile; their temporary files were removed after successful completion.
- A separate local review-recording process inserted the 17 scoped findings
  and two research leads, compared every prior/current extraction, checked all
  original input identities, and ran `annual_archive.verify()` against the
  completed candidate. Complete calendar, schema, structure/parent/order,
  source bullet coverage, leaf reconciliation, repeated parse idempotence,
  canonical round trips, prior output deltas, source/event search contents,
  GDELT preservation, input hashes and review guards all passed. Socket
  connections were blocked during annual build/replay verification.
- Candidate quick-check passed before atomic installation, and foreign-key
  checks passed afterward. `git diff --check` passed. Exactly one annual DB
  remains in `archive/`; no permanent per-day output/report files were created.
  No commit or push was performed. The separate full 40-file synthesis
  validation command was not rerun; existing synthesis compatibility was
  exercised through the final full test suite.

### Next step and remaining gate

Continue factual review, starting with the seven nonempty uncited source
entries and the three documented discrepancies. Put corrected dates, geographic
totals and reporting-time qualifications in researched synthesis with explicit
evidence; never silently repair Wikipedia's archival text. The empty marker,
source reliability tag and unclassified football passage remain separate
coverage/editorial leads. Independent broader research is needed to assess
events absent from Wikipedia; a source census cannot prove global completeness.

The database still reports `replacement_ready=false` and
`yearbook_ready=false`. Full-year factual coverage review, researched yearbook
content, dependency-checked deletion manifest and checkpoint/cutover work have
not been completed. Keep the old 2025 files and shared caches intact.

## 2026-10-21: cited editorial resolutions and Markdown checkpoint

### Decisions and scope

The selected yearly pair is `archive/<YYYY>.sqlite` plus
`archive/<YYYY>.md`. The user explicitly requires independent checking of
every event before cutover. An unreviewed source chronicle is not sufficient
grounds to delete the old daily files. The current Markdown is a clearly
labeled draft preview, not the finished historical yearbook. PDF production,
especially illustrations, is deferred until the reference content is ready.

### Changes and files

- Added `seed/yearbook.py` and `reference/schema/YEARBOOK.md`: additive,
  versioned `yearbook-review-1.0` records inside existing annual input/blob
  tables, full-event review queue, guarded recording, verification and
  deterministic Markdown rendering. No annual extraction/schema snapshot is
  replaced. The earlier 17 scoped findings remain distinct.
- Updated `archive/2025.sqlite` with eight editorial resolution records and
  embedded implementation/contract inputs. All seven originally uncited
  entries now have separate opened publisher evidence. The original
  extraction still correctly reports seven missing source citations.
- Added `archive/2025.md`: every one of the 5,453 archived event assertions,
  all 365 dates, month/day navigation, topic ancestry, pinned source revisions,
  original citations, explicit review labels and eight cited editorial accounts.
  Original wording remains alongside editorial corrections. Navigation uses
  the portal date; corrected editorial dates are explicit.
- Added `tests/test_yearbook.py` and annual/companion checks in
  `.github/workflows/verify.yaml`. Updated README and `.gitattributes` for
  companion use and exact replay bytes across platforms. The captured
  `seed/wikipedia.py` has historical mixed line endings: preserve those exact
  bytes through Git rather than normalize an embedded implementation silently.
  This changes Git's representation of that file, not its executable content.
- This checkpoint also includes the previously uncommitted annual container,
  parser fixes, guarded overrides, schema/contract, fixtures and tests described
  in the preceding two passes. All old 2025 daily files and shared source
  caches remain intact. No source revisions or acquisition policy changed.

### Research results and limits

Five full-event reviews are complete: January 9 wildfires, January 25 tennis
entry, April 2 tariffs, April 6 UConn and May 11 balloon accident. Corrections
and qualifications are confined to editorial records:

- The Australian Open final belongs to January 26; both pairs and score agree
  with the organizer. There is no matching final already in January 26's
  pinned extraction.
- The April 2 tariff announcement distinguishes April 5 baseline duties from
  April 9 scheduled higher duties; Annex I lists EU 20% and China 34%.
  Exemptions and additional-duty status prevent an all-imports interpretation.
- Reuters' later January 9 wildfire toll supports the original lower bound,
  but is reported with its own time scope rather than a final annual count.
- UConn's result and Fudd's award are supported by the AP game report hosted
  by the university. La Jornada's correspondent supports the balloon fatality,
  hanging/fall sequence, Zacatecas location and two other injuries.

Three records remain partial despite supported narrower editorial accounts:

- April 15 Titanic: PA's dated photo caption supports the Belfast City Hall
  service; the source's worldwide extent is not established by that evidence.
- September 8 Nepal: the Sky report separates 17 Kathmandu deaths from two
  in Itahari. It supports injuries and a curfew in parts of the capital; the
  portal's claim about all government buildings is still unsubstantiated.
- September 10 France: official sources establish September 9 appointment,
  September 10 handover and September 8 confidence defeat. They do not
  substantiate the source's oath-taking terminology.

Thus 5,445 events have no full-event review, three have partial reviews and
5,448 remain short of the factual cutover gate. The 17 earlier scoped records
are not silently counted as complete-event approval. No unresolved source
structure warning was introduced; factual uncertainties remain explicit.
Broader selection completeness, researched synthesis, deduplication, editorial
reading, consumer migration and a dependency-checked deletion manifest also
remain outstanding. No claim is made that the full year has been fact-checked.

### Access and checks actually performed

Publisher browsing opened the Australian Open report, White House tariff
order and two-page Annex I, UConn-hosted AP report, La Jornada correspondence,
Sky's Nepal report, French presidency appointment PDF, government handover
transcript, parliamentary vote record, Reuters via Investing.com and PA Images
caption via Getty Images. Also inspected the Independent's limited-access
Titanic report; its article text was not reproduced. Elysee HTML and Belfast
Telegraph video pages failed to open; they were not counted as opened evidence.
No images were downloaded, no GDELT query was made, and no cached Wikipedia
input was reacquired or edited. Research records identify passages, dates,
access results and source limits. Unknown model identity is explicitly null.

Commands and verification:

- `python -m unittest discover -s tests -p test_yearbook.py -v`: four new
  tests passed, including incomplete claim coverage, inaccessible evidence,
  source/implementation drift, immutable records, gate counts and rendering.
- `python -m unittest discover -s tests -v`: all 41 tests passed.
- `python -X utf8 -m seed.yearbook render archive/2025.sqlite`: completed after
  full annual offline verification; wrote the companion atomically.
- A separate read-only verification invoked `annual_archive.verify()`,
  `yearbook.review_report()` and two identical renders. All 365 pinned inputs
  replayed offline; schema, hierarchy, ordering, leaf counts, citations,
  round-trip, idempotence, hashes, source coverage, baseline reconciliation,
  FTS, review guards and database integrity passed. The Markdown has exactly
  365 day headings and 5,453 event anchors and matches the current DB hash.
- Compared every extraction/source/ingestion/GDELT and prior factual-review
  table against a preserved pre-editorial database: unchanged. All 1,095
  original daily/source/metadata files still match their embedded hashes.
- Ran `reference/schema/validate.py --archive-root expanded` with every
  existing synthesis path explicitly supplied: all 40 files passed.
- `git diff --cached --check`: passed after declaring the preserved
  acquisition module's CR-at-EOL convention. Every staged parser/schema/
  editorial implementation byte sequence matches its embedded snapshot;
  staged SQLite and Markdown bytes match their verified editions. Compared
  the acquisition module to HEAD with CRLF normalized: no content changes.
- No deletion, cutover, PDF generation or push was performed. Full-year
  independent factual research is incomplete, not a skipped test presented
  as success. The commit preserves a reviewable candidate and companion.

Edition identities before commit (the commit does not rewrite archive bytes):

- Database SHA-256:
  `6ca041ad0f057382378b1e3513136fb761b4d6eac0bea1e28b930b28d42dbc38`.
- Markdown: 2,744,739 UTF-8 bytes, SHA-256
  `ea3ccd80224d6988ae2ff4d54a479a9aeb3135c114b9692dc2c63ee88dd2f730`.

### Next pass

Continue independent event review in bounded chronological batches using
`python -m seed.yearbook queue archive/2025.sqlite --month 2025-01 --limit 10`.
Open and assess all assertions, including casualty reporting times and topic
context; record claim dispositions inside the database and regenerate the
single companion. Prioritize unresolved partial findings and the existing
source reliability/research leads as well. Do not delete daily files or caches
until all events meet the user's requirement and the other migration gates
pass. A final Markdown yearbook and optional PDF follow that gate.

## 2026-10-21: 2025 preservation edition and filesystem cutover

This section supersedes the preceding exhaustive-check publication gate.
The approved priority is long-term source preservation. Independent checking
of every event is optional follow-up research, not a prerequisite for publishing
the verified source archive. Exact provenance, extraction coverage, source-error
preservation, attribution and honest disclosure remain required. Publication
does not claim exhaustive, impartial or independently verified news coverage.

### Publication, files and compatibility

- `archive/2025.sqlite` and `archive/2025.md` are now the 2025 preservation
  edition. The Markdown has every event assertion, original citations,
  pinned source links and separate editorial accounts. Its front matter
  discloses incomplete independent review. All 17 earlier scoped findings,
  evidence access limits and uncertainties are also rendered for readers.
- Added `seed/archive_release.py`, `seed/archive_access.py` and
  `reference/schema/PRESERVATION_RELEASE.md`. The additive publication contract
  is `preservation-release-1.0`; the extraction, annual container and earlier
  draft-review contracts retain their original immutable inputs. Historical
  `replacement_ready=false` reports are retained as prior-policy evidence;
  `archive_checks.preservation_publication` records the active preservation
  verification and its explicit non-exhaustive-review policy.
- The embedded immutable `publication/2025.json` manifest identifies checkpoint
  `7b3bc18c`, publication policy, all preserved/retired paths, byte lengths,
  hashes and shared-source checks. It embeds 730 old local provisional files
  before their removal. Retired files: 365 daily YAML files under `2025/`,
  730 dedicated Wikipedia cache payload/metadata files and 730 ignored local
  extraction candidates under `provisional/extraction-v1/2025/`: 1,825 in total.
  There were no cache pairs shared by another daily seed, expansion input or
  capture pointer in this set. Other years and shared cache infrastructure
  remain intact. Git records 1,095 tracked deletions; the 730 provisional
  candidates were ignored and never tracked.
- Retirement verified every remaining listed file against its embedded exact
  bytes before unlinking any. No computed directory was recursively deleted.
  All 1,825 originals are recoverable from the SQLite input/blob tables.
  Checkpoint comparison additionally found 730 byte-exact Git cache files and
  365 legacy YAML files differing only in Git's LF versus original working-tree
  CRLF convention. The database retains the actual original YAML bytes; Git
  supplies a content-equivalent additional checkpoint.
- `seed/source.py`, `seed/replay.py`, `seed/merge.py`, `seed/cli.py`,
  `reference/expansion/wikiportal.py` and `reference/expansion/build.py` now
  recognize published annual inputs. Source revisions and legacy inputs are
  served read-only from SQLite after cache retirement. Offline candidates use
  the canonical annual extraction. Expansion preserves topic hierarchy and
  cites the annual location. Planning treats annual dates as present, and
  acquisition/writes refuse a published year before fetching or recreating
  daily outputs. Explicit custom caches remain isolated.
- Added `tests/test_archive_release.py`, updated `.github/workflows/verify.yaml`
  to verify and reproduce preservation editions, and updated README, AGENTS.md
  and `.gitattributes`. The frozen draft renderer remains available as historical
  implementation evidence; use `seed.archive_release render` for publication.

### Verification, access and limits

No new publisher research, source capture or GDELT queries were made. Network
access was Git fetch, followed by the explicitly requested branch push. Source
facts, all 17 earlier scoped findings, the eight editorial records and their
review states were preserved. There are still five complete full-event reviews
and three partial reviews; publication has not relabeled the remainder reviewed.
No extraction warning was introduced or silently resolved by the policy change.
Known source errors, the unreliable military claim, rolling casualty-count
limits and unclassified football passage remain disclosed.

Commands and checks:

- `python -m unittest discover -s tests -p test_archive_release.py -v` passed
  after its first run exposed Windows SQLite backup handles left open during
  atomic replacement. Explicit connection closing fixed this before real
  cutover. Tests cover guarded retirement, changed originals, shared caches,
  read-only recovery, pre-network write protection and honest review status.
- `python -m unittest discover -s tests -v`: all 44 tests passed before and
  after cutover, including existing 2000/2026 synthesis compatibility.
- `python -X utf8 -m seed.archive_release prepare archive/2025.sqlite`:
  staged, verified and atomically installed the preservation edition.
- `python -X utf8 -m seed.archive_release render archive/2025.sqlite`:
  generated the published companion after complete offline verification.
- `python -X utf8 -m seed.archive_release retire archive/2025.sqlite`:
  verified preservation and removed exactly 1,825 listed files.
- Independent Git blob and embedded-input comparison accounted for all 1,095
  tracked deletions and all 1,825 preserved identities, with only the legacy
  newline distinction described above. Git checkpoint source-cache bytes
  matched exactly. No source or original seed content was lost.
- After retirement, a separate socket-blocked verification passed full annual
  replay, publication manifest checks, editorial guards and byte-identical
  Markdown regeneration (365 day headings and 5,453 event anchors). Expansion
  parsing across all 365 dates returned all 5,453 events from SQLite. The full
  2025 `replay.run_reparse()` with verification wrote temporary external outputs:
  365 dates, zero missing inputs, 5,453 event leaves. These temporary outputs
  were removed by the test's owned temporary-directory cleanup. All-range
  collection planning returned no work for 2025. All 40 existing synthesis
  files passed `reference/schema/validate.py --archive-root expanded` with
  their explicit paths. No archived source tree was needed for these checks.

Edition identities:

- SQLite: 39,067,648 bytes, SHA-256
  `5b21f969460809b03b64a21be2c638023cde5abfe321fac9ead653964eb373bd`.
- Markdown: 2,655,719 UTF-8 bytes, SHA-256
  `a780e95180a948d08866e1cfcbc5ae112d6494078bc642ab8387a65720941117`.

### Remaining work

The source-preservation edition is publishable; a finished historical
interpretation/yearbook is separate work. PDF production is deferred until
after this publication and can begin with text, navigation and source notes;
illustrations need not be commissioned or acquired first. Optional factual
research should focus on recorded discrepancies and uncertainty, rather than
an obligatory pass over every statement. Future extraction/editorial changes
must use an explicit successor edition, preserving immutable implementation
snapshots and earlier research. Publish to `codex/repository-repairs`; do not
silently merge the unrelated daily-update divergence on `origin/main`.

### Remote verification follow-up

The preservation commit `3a8da632` was pushed successfully to
`origin/codex/repository-repairs`. Its first remote workflow found a pre-existing
test dependency on ignored local output:
`tests/test_sqlite_archive.py` read a January 16, 2026 provisional candidate
that was present locally but absent in a clean checkout. The test now rebuilds
its input from tracked pinned source using offline replay, explicitly removes
GDELT before checking enrichment insertion/removal, and keeps its byte-level
round-trip assertions. This changes the test only, not the published archive,
its frozen implementation or its Markdown checksum. Local passing results
above did not catch this clean-checkout dependency; the failed remote run is
recorded rather than represented as successful verification.

## Preservation exports and print layer (2026-10-21)

The adopted direction separates canonical annual SQLite/Markdown from derived
release assets. Keep the current annual paths; do not recreate daily outputs or
move the unrelated January 2000 databases as part of this pass. The authoritative
2025 database and Markdown bytes and source/review policies remain unchanged.

Added `PRIMER.txt`, `tools/build_tiers.py`, `tools/PRESERVATION.md` and
`tests/test_preservation_bundle.py`. The new `preservation-bundle-1.0` export
contract is a separate derivative, not an annual database schema change.
The exporter copies the exact annual pair, reads SQLite with `mode=ro` and
`query_only`, and creates UTF-8 SQL plus reversible typed TSV. NULL, empty text,
empty BLOB, binary bytes, embedded controls and Unicode remain distinct. It
exports 29 logical tables and eight reading views for 2025; FTS5 shadow tables
are rebuilt from logical rows. Unsupported virtual-table configurations fail.

The exporter restores both SQL and TSV into temporary databases and compares
all logical table/view row hashes and counts, schema and header pragmas. It
also runs database integrity, foreign-key and FTS integrity checks. Source
hashes must remain unchanged. An explicitly allowlisted USTAR includes the
original pair, recovery scripts/instructions, schema, typed exports, verification
report, standard SHA-256 manifest and a size/CRC-32/SHA-256 TSV manifest. Both
manifests exclude themselves and each other. Every other TAR member is covered
and verified before atomic installation. No repository-wide file sweep occurs.

One generated annual TAR remains under ignored `dist/`; temporary expanded
exports/restores are cleaned up. SQL and TSV are deliberately distributed in
the release bundle instead of committing large duplicate representations.
The base 2025 bundle is 173,537,280 bytes. Checksums detect damage, not repair
or authenticate it. Recovery SQL/scripts must come from trusted bundles.

Added optional `reference/yearbook/build.py`, `verify.py`, `requirements.txt`
and `README.md`. The existing print work is retained as a release derivative,
with a complete 888-page 2025 reference chronicle, original event prose,
separate editorial notes, calendars/charts, printed evidence registers and a
subject index. It preserves 5,453 source assertions, prints 6,564 publisher
URLs and covers 13,878 event/topic-ancestor wikilink targets. It includes all
365 pinned source revision/hash records, 21 bookmarks and embedded used font
subsets. It is not claimed to be PDF/A or independently checked history.
PDF output defaults to ignored `dist/`; previews and visual QA stay under
ignored `tmp/pdfs/`. Optional print dependencies do not change collection
requirements. Windows font defaults and explicit portable font options are
documented. The PDF remains a reading projection, not a complete binary backup.

Updated README, `.gitignore`, `.gitattributes` and verification CI. CI runs the
real annual bundle build and both recovery checks, in addition to existing
offline tests, annual replay/Markdown verification and synthesis validation.
No generated TAR, PDF, private consultation material or font files are staged.

Checks executed:

- `python -m unittest discover -s tests -v`: all 47 tests passed in 23.774s.
  Three new tests cover typed control/binary/null distinctions, SQL/TSV and
  FTS restoration, identical repeated bundle builds, source byte preservation,
  network-blocked operation, checksum-detected damage and unsupported FTS.
- `python tools/build_tiers.py build archive/2025.sqlite`: full 2025 SQL and
  TSV restores passed, all 29 tables/eight views matched, source pair unchanged.
- `python tools/build_tiers.py verify dist/2025-preservation.tar`: all 46
  payload members and both manifest coverages passed.
- The complete print verifier passed for 888 pages, every event assertion,
  event ID, publisher URL, pinned source record, index subject, embedded used
  font and bookmark. A verifier defect that discarded multi-line fragments
  using their visitor coordinates was fixed by removing the builder's checked
  four-line furniture prefix instead. Earlier failed checks were verifier
  failures, not established losses of printed source prose.
- Print QA included Poppler-rendered chapter/boundary/reference/index pages
  and full-book geometric bounds checks. Earlier repeated print generation
  was byte-identical. A final rebuild records the current generator hash.
- `git diff --check` passed. Existing extraction warnings, scoped findings
  and factual-review limits were unchanged; no new archival data was collected.

Network access in this pass was technical verification against SQLite and
Library of Congress documentation, plus Git publication/CI checks. No publisher
research, GDELT query, source revision change or new acquisition service occurred.

Deferred deliberately: page rasters, recovery barcodes, PAR2 recovery blocks,
C bootstrap reader, inscription digest/layout and equipment-specific G-code.
Do not call Group 4 TIFF uncompressed, claim universal machine compatibility,
guaranteed media lifetimes or tested physical recovery without actual tests.
Next: distribute the verified annual bundle and optional print derivative as
release assets; retain the small canonical annual pair in Git. Physical layers
can then be developed as explicit, tested build stages without another data
format migration or multiplication of permanent daily files.

Final local derivative checks passed after rebuilding with the current print
generator: PDF 4,451,552 bytes, SHA-256
`b82b61b133381b1ba0d0d8d4478b2703dc4de61c8ef8ddb81a5ed16752b8d40f`.
Its changed colophon was rendered and visually checked. The bundle including
that PDF is 177,991,680 bytes, SHA-256
`29672ea6af1e22aee002d7a6fe61325cf2448cc88acae67b8db72cf6e23f30e4`.
Both SQL/TSV restores and the final bundle's manifests passed again. Files are
`dist/2025.pdf` and `dist/2025-preservation.tar`, prepared locally rather than
uploaded to a new GitHub release.
