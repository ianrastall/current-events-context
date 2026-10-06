Latest status: see the October 5, 2026 repair pass at the end of this file. Earlier inspection findings are retained as history.

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
   Wikipedia migration. No push, PR publication or deployment was performed.
