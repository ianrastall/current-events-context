# Handoff: January 2026 deep-context expansion

Last updated: 2026-09-24 (Jan 10 rebuild, Jan 11-14 builds)

## Goal

Upgrade every `2026/01/2026-01-DD.yaml` portal stub to a schema 2.2 deep-context file, then build a single month summary for January 2026 from the finished days.

## Workflow

1. Run a deep-research tool with `llm_prompt.txt`, replacing `DATE_ISO = [insert date]` with the day.
2. Save the Markdown report as `reference/deep-research/2026/01/2026-01-DDa.md`.
3. Convert the report plus the portal stub into schema 2.2 YAML following `reference/schema/AUTHORING_GUIDE.md` (reference files: `2026-01-01.yaml`, `2026-01-02.yaml`).
4. Validate: `python reference/schema/validate.py 2026/01/2026-01-DD.yaml` (install `jsonschema` first; without it the schema check is skipped and unexpanded stubs pass).

Do not use `llm_agent_prompt.txt` or `generate_prompts.py` for conversion as they stand: the embedded template is schema 2.1, which is how `2026-01-07.yaml` ended up in the wrong schema.

## Status by day

| Days | Research report | YAML | Status |
| --- | --- | --- | --- |
| 01-05 | Yes | Schema 2.2 | `reviewed` |
| 06-09 | Yes | Schema 2.2 | `reviewed` (review pass 2026-09-23, see below) |
| 10 | Yes (`2026-01-10b.md`, real URLs) | Schema 2.2 | `draft`, rebuilt 2026-09-24, see below |
| 11 | Yes (`2026-01-11b.md`) | Schema 2.2 | `draft`, built 2026-09-24 |
| 12 | Yes (`2026-01-12b.md`) | Schema 2.2 | `draft`, built 2026-09-24 |
| 13 | Yes (`2026-01-13a.md`) | Schema 2.2 | `draft`, built 2026-09-24 |
| 14 | Yes (`2026-01-14a.md`) | Schema 2.2 | `draft`, built 2026-09-24, see below |
| 15-31 | No | Portal stub | Needs a deep-research run |

All of 01-14 pass `validate.py` with `jsonschema` installed, and every `related_events` link across 01-14 resolves. Days 10-14 are `draft`/`reviewed: false` pending the same human-review pass already done for 01-09 — they have not been machine-verified beyond the quote/URL/schema checks described below.

## Jan 10 rebuild and the monthly-vs-daily portal misattribution (2026-09-24)

The original `2026-01-10a.md` report had no source URLs (see "Open issues," historical). The user ran a fresh browser deep-research pass and supplied `2026-01-10b.md`, which does include URLs, and the day was rebuilt from scratch (15 events, 26 works cited).

While cross-checking `2026-01-10b.md` against already-recorded events, several of its ~18 candidate events turned out to be near-verbatim duplicates of events already dated to Jan 3, Jan 5, and Jan 9. The likely cause: the browser tool appears to have partly scraped Wikipedia's **monthly** portal index (`Portal:Current_events/January_2026`) rather than the **daily** page (`Portal:Current_events/2026_January_10`) for those items, pulling in content correctly dated elsewhere. Excluded from the Jan 10 rebuild for this reason, each confirmed by matching exact wording against the existing YAML before exclusion:

- Kyiv/Lviv Oreshnik strike — duplicate of `evt-2026-01-09-011`
- Nguru/Yobe boat capsize — duplicate of `evt-2026-01-03-017`
- Uganda broadcast ban — duplicate of `evt-2026-01-05-019`
- UNFCCC withdrawal recap — duplicate of `evt-2026-01-07-003`/`evt-2026-01-08-002`

**Lesson for future research requests:** when asking for a re-run because a source lacked URLs, explicitly tell the research tool to use the *daily* portal page, not the monthly index, and expect to re-run this same duplicate check on any report touching a day already covered by earlier days' events.

Also rebuilt/upgraded with real external sources in this pass: the Iran crackdown event (casualty figures left `null` with `uncertainty_notes` rather than asserting an unquoted cumulative figure — HRANA's blackout-era numbers are unverifiable day to day), the Aleppo drone strike, Operation Hawkeye Strike, the Cebu landfill collapse, the Yeison Jiménez crash, the Grok ban, and the FA Cup upset. Two new events were added: Trump's Jan 10 executive order and Delcy Rodríguez's Jan 10 Petare speech (confirmed distinct from her Jan 5 swearing-in via an exact "Today, January 10, one year later..." quote in the source).

## Jan 11 and Jan 12 builds (2026-09-24)

Built from `2026-01-11b.md` (23 events, 35 works cited) and `2026-01-12b.md` (29 events, 49 works cited) using the same methodology: cross-reference the true daily portal bullets, write report-sourced events plus portal-only events for anything the report didn't reach, verify every `quoted_material` string and every `url` against the source report programmatically, fix any script-flagged miss only after confirming it with a direct `grep` (all flagged misses across both days turned out to be curly-quote/ellipsis normalization gaps in the checker, not real fabrications — zero actual mismatches found), then `validate.py` and commit.

Jan 12's initial validation failed on three `sources.external[].supports` entries using `details.uncertainty_notes`, which is not a valid enum value in the schema (valid values: `summary`, `key_data`, `casualty_report`, `details.what_happened`, `details.why_it_matters`) — fixed by repointing those three entries to `details.what_happened`.

Both days needed a few cross-day disambiguations, resolved by matching exact dated phrasing in the sources: the Noem ICE-surge officer deployment and the Victoria bushfire's first confirmed death both belong to Jan 11, not Jan 10 as originally guessed; Jan 12's press-conference coverage of that same bushfire death is recorded as a separate, zero-casualty Jan 12 event cross-linked to the Jan 11 death record so the death itself isn't double-counted.

All three days' `related_events` links were checked against Jan 1-12 for accidental duplicates (recurring stories like the Cambodia scam-center crackdowns and Venezuela prisoner releases are cross-linked rather than duplicated); no unflagged duplicates were found.

## Jan 13 and Jan 14 builds (2026-09-24)

The user supplied `2026-01-13a.md` and `2026-01-14a.md`; both are saved under `reference/deep-research/2026/01/` with the user's `a` suffix. They are different in kind:

- **Jan 13** is a clean, URL-sourced report (16 events, 33 references) that stays on the day. Built as 21 events: the 16 report events (5 merged with portal bullets) plus 5 portal-only events (Argentina inflation, Mali ferry, Walikale landslide, Tren de Aragua arrests, X restored in Venezuela). The Kharkiv postal-facility strike deliberately deferred from `evt-2026-01-12-011` is recorded here as `evt-2026-01-13-002`. The Iran toll event records both attributions of the 2,000 figure (an Iranian official via Reuters; HRAI via the portal) and marks the UN's "hundreds" and AP's activist figure above 2,500 as contradicting sources.
- **Jan 14** is a Gemini-style "intelligence report" with the same monthly-portal problem found on Jan 10. Built as 15 events. Excluded, each confirmed against existing YAML or its own cited dates:
  - Syrian SDF withdrawal from Aleppo: duplicate of `evt-2026-01-11-006` (see also 01-08-007, 01-09-005).
  - U.S. strike toll of 100 in Caracas, 32 Cubans killed, FAA Caribbean ban lifted: duplicates of `evt-2026-01-04-016/017/018` and `evt-2026-01-08-001`.
  - STC collapse in Aden, airport captured, al-Zoubaidi fled via Somaliland: duplicate of `evt-2026-01-08-019`.
  - Iran items: Malard police death and 568 injured police (`evt-2026-01-08-006`), first Starlink shutdown (`evt-2026-01-11-002`), HRAI 483/47 count (`evt-2026-01-11-001`), and a cumulative 3,428 figure sourced to an RFE/RL live blog whose slug belongs to the later Iran war. Only the Jan 14 Kurdish-infiltration portal bullet is kept (`evt-2026-01-14-011`).
  - Luigi Mangione federal murder/weapons charges dismissed: the report's own source dates it January 30. Place it on Jan 30 when that day is researched.
  - DOJ release of 3 million Epstein pages: the final large tranche is a January 30 event, not January 14. Place it on Jan 30.
  - The Sudan section's headline item, the return to Khartoum, is already `evt-2026-01-11-012`; only the January 14 Cairo meeting (The National) is kept as `evt-2026-01-14-003`, with Decree No. 83 recorded with an undated-source caveat.
- One Jan 14 event is taken from a works-cited entry rather than a report section: the AP live page for January 14 is headlined "Senate rejects Venezuela war powers resolution as 2 Republicans flip". It is recorded as `evt-2026-01-14-005` with `detail_accuracy: low` and a note that it rests on that headline alone. A reviewer should confirm the vote tally and names.
- Several Jan 14 report sources are the Wikipedia portal itself ("via Wikipedia Current Events"). Those events (Brazil raid, Copernicus, gold record) are treated as portal-derived with `external: []`, matching earlier days' handling.
- The Danish/Greenlandic ministers' talks in Washington, scheduled for Jan 14 per the Jan 13 sources, are not covered by either the report or the portal. That is a gap a re-run could fill.

Verification: a script checked every `quoted_material` string and every `url` against the day's report (after stripping Markdown escapes such as `\_` and `\&` and normalizing curly quotes), every `text_fragment` against the original portal bullets from git, and every `related_events` id against the archive. Result: zero mismatches on both days. The only portal line not used on Jan 14 is a topic header. Quotations that come from a headline in the report's reference list rather than its body are marked as such in that event's `notes`.

## Review pass on 06-09 (2026-09-23)

Before flipping `status`/`reviewed`/`mode` to reviewed, ran automated checks against each day's source report (`reference/deep-research/2026/01/2026-01-DDa.md`):

- Every `quoted_material` string in every external source verified to appear verbatim in that day's report (136 quotes across 06-09; the checker's first pass flagged 13 false positives from incomplete curly-quote/ellipsis normalization — all 13 confirmed present by direct `grep`).
- Every cited `url` verified to appear verbatim in that day's report (0 mismatches).
- Headlines verified sentence case, `tags`/`event_type` verified kebab-case, `time.date` verified to match the file date — all clean.
- `validate.py` schema + cross-reference checks still pass after the flip.

Day 10 was deliberately left in `draft`: its source report cites outlets by name with no URLs at all (`grep -n "lack URLs\|lack a URL"` in that file shows the gaps), so several of its events can't be attributed to a checkable source. A re-run with a real deep-research tool (browser-based) is underway; see the improved prompt below.

## Deep-research prompt (in use as of 2026-09-23)

`llm_prompt.txt` at the repo root is the base prompt. Two lines were added to its FACT RULES to close the two failure modes actually observed in days 06-10 (future-event leakage from reports compiled in March, and day 10's total lack of URLs):

```
- Report only events that occurred on DATE_ISO or were first reported on DATE_ISO. Do not include events from later dates, even if you find later sources discussing them.
- Every source must include a full, working URL — no citation is valid without one.
```

These are being used for the day-11 and day-10-rerun requests but not yet written back into `llm_prompt.txt` itself — do that once a couple of days confirm the wording holds up.

## Decisions made in the 06-10 conversion

- New files are `status: draft` (`reviewed: false`, mode `llm_deep_research_broad_snapshot`). Flip all three fields after a human read-through.
- Every portal bullet is preserved. Bullets about one real-world event are merged into a single event, with the verbatim texts joined by ` | ` in `text_fragment`.
- Follow-up coverage of an earlier event (for example, Jan 8 reactions to the Jan 7 UN withdrawal) is kept as its own event with `related_events` links. The month summary should deduplicate these.
- If a source had only a month (for example "January 2026"), the day was taken from the URL where possible. Otherwise it was approximated and the approximation is stated in that event's `uncertainty_notes`.
- No URLs were invented. Where the report gave no URL, the source is not listed, and the event says so in its notes.
- Claims the report made without a supporting citation were dropped and listed in `uncertainty_notes`.

## Events excluded as misdated

The deep-research reports were compiled in late March 2026, and several leaked later events into January days:

| Day | Report section | Reason |
| --- | --- | --- |
| 01-06 | Executive synthesis references to U.S./Israeli strikes on Iran's South Pars field and Iranian strikes on Gulf states | Sourced to AP, 2026-03-18 |
| 01-07 | "Iranian Missile Strikes Cause Mass Civilian Casualties in Israel and UAE" | Operation Epic Fury, HRW 2026-03-17; was present in the old 2.1 file |
| 01-07 | "Vietnamese Prime Minister Advances Energy and Security Ties in Moscow Visit" | Visit was 2026-03-23 to 03-25 |
| 01-09 | "Israel Strikes Critical Russian-Iranian Smuggling Hub in the Caspian Sea" | Sole source JNS 2026-03-25, "one week ago" |
| 01-09 | "Benin Ruling Parties Dominate Deeply Contested Legislative Elections" | Results and court appeals postdate the election, which was held after Jan 9; belongs mid-January |
| 01-10 | "U.S. forces capture Venezuela's President Nicolás Maduro" | Recap of Jan 3 with no Jan 10 development |
| 01-10 | "Islamic State-affiliated militants kill 15 in eastern Congo" | Jan 1-2 attack, already `evt-2026-01-03-008` |

## Open issues

- `2026-01-04.yaml`, `evt-2026-01-04-015` (royal commission) is probably misdated. Its only source is an undated Guardian topic page, and it says "Bondi Junction". SBS reported the announcement as new on Jan 9 (see `evt-2026-01-09-014`). Not changed because Jan 4 is already marked reviewed.
- The Benin election results excluded from Jan 9 should be placed on the correct mid-January day when that day is researched. Neither the Jan 13 nor the Jan 14 report covers them.
- Jan 30 should pick up the Mangione federal-charge dismissal and the 3-million-page Epstein release excluded from Jan 14.
- `2026-01-10a.md` (the original, URL-less report) is still on disk alongside `2026-01-10b.md` (the rebuild source). No cleanup requested or performed; `2026-01-10.yaml`'s `notes` fields cite `b` throughout.
- `copilot_prompts/` holds prompts for 01-01 to 01-10 built from the schema 2.1 template. They are now stale; left in place pending the owner's decision.
- `llm_agent_prompt.txt` and `llm_review_prompt.txt` still embed the schema 2.1 template.

## Recommended addition to the deep-research prompt

To cut down on leakage of later events, consider adding to the FACT RULES in `llm_prompt.txt`:

```text
- Report only events that occurred on DATE_ISO or were first reported on DATE_ISO. Do not include events from later dates, even if later sources discuss them.
- Every source must include a full URL. Prefer sources published on DATE_ISO or within two days after it; flag any source published more than a week later.
```

## Next steps

1. Human-review 10-14 and flip them to `reviewed` (same pass already done for 01-09).
2. Run deep research for 15-31, saving each report as `reference/deep-research/2026/01/2026-01-DDb.md` (use the "b" suffix going forward, since "a" now means "the original, possibly weaker report" by precedent) — explicitly instruct the tool to use the daily portal page, not the monthly index, per the Jan 10 lesson above.
3. Convert each day, validate, verify quotes/URLs against the source report, and link `related_events` to prior days.
4. Once all 31 days are expanded, build the January 2026 summary from the YAML files, deduplicating follow-up events via `related_events`.
