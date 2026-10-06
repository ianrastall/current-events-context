# Daily Events Authoring Guide (schema 2.2)

This is the procedure for expanding one day's YAML file by incorporating its
deep-research markdown report. The machine-checkable shape lives in
[`daily-events.schema.json`](daily-events.schema.json); this document covers the
**judgment** the schema can't enforce. Reference implementations:
`expanded/2026/01/2026-01-01.yaml` and `expanded/2026/01/2026-01-02.yaml`.

## Inputs and outputs

The authoritative input selection is `reference/expansion/inputs.json`.
Replacement `b.md` reports are explicitly selected for January 10-12.
Never use filename precedence or a size threshold to choose a source.
January 1-15 replay immutable authored snapshots imported from GitHub;
the older positional overlays do not apply to those inputs. Preserve review
state only for an unchanged replay; new or corrected synthesis is draft until
its factual review is recorded.

| | Path |
|---|---|
| Deep-research markdown (source) | `reference/deep-research/<YYYY>/<MM>/<YYYY-MM-DD>a.md` |
| Portal bullets (seed) | `<YYYY>/<MM>/<YYYY-MM-DD>.yaml` |
| Output | `expanded/<YYYY>/<MM>/<YYYY-MM-DD>.yaml` |

The seed file is extraction output and is never rewritten by an expansion. It
may be in the current seed shape (`source_page` and `wikipedia.categories`) or
the legacy shape (`Date`, `Source_URI`, `Intelligence_Payload.Uncategorized`).
Take the portal revision from its `source_page.wikipedia_revision_id` when
present. The expansion is written to a separate file under `expanded/`; see
`expanded/README.md`.

`reference/expansion/build.py` automates the mechanical steps below: parsing
the report, matching portal bullets, building `works_cited`, and emitting and
validating the file. The judgment steps are recorded in per-day overlays. See
`reference/expansion/README.md`.

## Procedure

1. **Read both inputs fully.** The markdown has `## Event:` sections; the seed YAML
   has the portal bullets. Markdown styles vary — some have an intro paragraph,
   key-data tables, and a strategic conclusion (Jan 1 style); others are a terse
   "Global News Sweep" with `entity[...]` markup and `citeturn...` reference
   tokens (Jan 2 style). **Strip `entity[...]` wrappers and `citeturn...` tokens**;
   keep only clean prose and real URLs.
   Reports produced with the current `llm_prompt.txt` also carry a `Date Check`
   line per event and end with "Portal items not covered" (convert each into a
   portal-only event) and "Excluded or uncertain items" (do not convert; record
   them in `HANDOFF.md` so they can be placed on the right day).

2. **Build the event list as a union of two sets:**
   - **One event per markdown `## Event:` section**, fully enriched.
   - **Plus every portal bullet that has no matching markdown event**, preserved as
     a portal-only event (see below). Never drop a portal bullet.

   Number events `evt-YYYY-MM-DD-NNN` sequentially from `001`. Put the enriched
   markdown events first, then the portal-only ones.

3. **For each event, fill every field** required by the schema. Match the prose
   density and tone of the reference files.

4. **Capture disagreement.** When outlets report different figures (very common),
   do not silently pick one:
   - Note the conflict in `details.uncertainty_notes`.
   - On the dissenting source, list the disputed field in `contradicts`
     (e.g. `casualty_report`).
   - In `casualty_report`, record the most-supported / latest figure; mention the
     alternative in `uncertainty_notes`.

5. **Write `analytical_overview` and `strategic_conclusion`** grounded only in the
   day's events. If the markdown supplies them (Jan 1 style), adapt that text. If
   not (Jan 2 style), synthesize a concise version — descriptive, not speculative
   (`editorial_policy.allow_inference` is `false`).

6. **Build `works_cited`.** Assign each distinct external source a sequential
   integer `id` starting at 1; add the Wikipedia portal as the final entry. Every
   `citation_refs` integer (in `key_data` and in each external source) must resolve
   to a `works_cited` id.

7. **Validate** before finishing (see below).

## Portal-only events (the Parmelin pattern)

A portal bullet with no deep-research coverage still becomes a full event, but:

- `sources.wikipedia_portal.included: true` with the verbatim bullet in
  `text_fragment`.
- `sources.external: []` — **do not invent URLs.**
- `provenance.extracted_from_portal_bullet: true`, `enriched_manually: false`.
- `notes:` say it's portal-derived and name the outlet the portal cited
  (e.g. "reported by MyRepublica per the Wikipedia portal").
- `key_data` may cite the portal entry in `works_cited` (the last id).

Reference: `evt-2026-01-01-017` (Parmelin) and `evt-2026-01-02-014..018`.

## Source assessment

CBS News and its affiliates receive no assumed reliability in synthesis.
Corroborate material claims through independent reporting or an appropriate
primary record before treating them as established. For syndicated stories,
identify the original wire and check its copy; multiple republications of one
dispatch are one reporting source. Record inaccessible sources and unresolved
claims explicitly. This policy does not presume every CBS claim false.
Preserve historical reports, authored inputs and Wikipedia extraction as
archival evidence; apply corrections through guarded synthesis overlays.

Publisher review evidence belongs under
`reference/reconciliation/publisher-review/`. Record the exact event hash,
URLs, access limits, checked claims and remaining checks. An automated or
partial publisher pass does not confer human-reviewed status.

## Field conventions

- **`importance` (1–10):** mass-casualty disasters, wars, and systemic
  economic/political shifts rank highest (8–10); routine accidents and
  administrative items lowest (4–5).
- **`included: false`** on `wikipedia_portal` for markdown-only events (event has
  no portal bullet); `text_fragment: null` then.
- **`time.time_detail`** only when `time.time_known: true`.
- **`casualty_report`** numbers are integers or `null` (unknown). Use `0` only when
  genuinely zero (e.g. an economic-policy event).
- **`event_type` / `tags`** are kebab-case.
- **`source_type`**: one of the schema enum
  (`news_report`, `official_release`, `encyclopedia`, `broadcast`, `ngo_report`,
  `advocacy_organization`, `specialist_publication`, `trade_publication`).
- **`reliability_tier`**: assess the cited article and its reporting basis.
  Major wires and appropriate official records can warrant `high`; local or
  specialist reporting may warrant `medium`; questionable support warrants
  `low`. An outlet name alone does not establish reliability. Official
  statements establish what an authority said, not necessarily disputed facts.
- **Review state — three fields that must move together.** `status`, `reviewed`,
  and the `mode` suffix all encode the same thing, so set them as a unit
  (the validator enforces this):
  - **Draft (freshly generated):** `status: draft`, `reviewed: false`,
    `mode: llm_deep_research_broad_snapshot`.
  - **Reviewed (after a human reads the file):** `status: reviewed`,
    `reviewed: true`, `mode: llm_deep_research_broad_snapshot_reviewed`.

  If you mark a file reviewed by hand, change all three (or just `status` and
  re-run `validate.py`, which will tell you the other two are out of sync).

## Validate

```bash
python reference/schema/validate.py expanded/2026/01/2026-01-02.yaml
```

The validator checks the file against the JSON Schema **and** the cross-references
the schema can't express (sequential event ids, every `citation_refs` resolving to
a `works_cited` id). Fix all errors before considering a day done.

Install `requirements.txt` first; missing `jsonschema` is an error, never a
successful partial check. To check cross-day links, also pass
`--archive-root expanded`. Batch validation reports every supplied file.
