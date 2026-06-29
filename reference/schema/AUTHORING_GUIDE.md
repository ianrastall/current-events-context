# Daily Events Authoring Guide (schema 2.2)

This is the procedure for expanding one day's YAML file by incorporating its
deep-research markdown report. The machine-checkable shape lives in
[`daily-events.schema.json`](daily-events.schema.json); this document covers the
**judgment** the schema can't enforce. Reference implementations:
`2026/01/2026-01-01.yaml` and `2026/01/2026-01-02.yaml`.

## Inputs and outputs

| | Path |
|---|---|
| Deep-research markdown (source) | `reference/deep-research/<YYYY>/<MM>/<YYYY-MM-DD>a.md` |
| Unexpanded portal YAML (seed) | `<YYYY>/<MM>/<YYYY-MM-DD>.yaml` |
| Output | the **same** YAML path, rewritten in schema 2.2 |

The seed YAML has only `Date`, `Source_URI`, and
`Intelligence_Payload.Uncategorized` (a flat list of portal bullets). You replace
it with the full schema-2.2 document.

## Procedure

1. **Read both inputs fully.** The markdown has `## Event:` sections; the seed YAML
   has the portal bullets. Markdown styles vary — some have an intro paragraph,
   key-data tables, and a strategic conclusion (Jan 1 style); others are a terse
   "Global News Sweep" with `entity[...]` markup and `citeturn...` reference
   tokens (Jan 2 style). **Strip `entity[...]` wrappers and `citeturn...` tokens**;
   keep only clean prose and real URLs.

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

## Conventions

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
- **`reliability_tier`**: `high` for major wires/official releases, `medium` for
  local/specialist outlets, `low` if questionable.
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
python reference/schema/validate.py 2026/01/2026-01-02.yaml
```

The validator checks the file against the JSON Schema **and** the cross-references
the schema can't express (sequential event ids, every `citation_refs` resolving to
a `works_cited` id). Fix all errors before considering a day done.
