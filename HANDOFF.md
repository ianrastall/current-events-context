# Handoff: January 2026 deep-context expansion

Last updated: 2026-09-24 (Jan 10 rebuild, Jan 11-15 builds)

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
| 15 | Yes (`2026-01-15a.md`, first run of the rewritten prompt) | Schema 2.2 | `draft`, built 2026-09-24, see below |
| 16-31 | No | Portal stub | Needs a deep-research run |

All of 01-15 pass `validate.py` with `jsonschema` installed, and every `related_events` link across 01-15 resolves. Days 10-15 are `draft`/`reviewed: false` pending the same human-review pass already done for 01-09 — they have not been machine-verified beyond the quote/URL/schema checks described below.

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

## Jan 15 build (2026-09-24)

`2026-01-15a.md` (uploaded as `January_2026_Daily_News_Record.md`) is the first report made with the rewritten `llm_prompt.txt`. It stayed on the day much better than the Jan 14 report. It covered all 12 daily-portal bullets, added 3 non-portal events (Maharashtra municipal elections, Carney in Beijing, Trump's Insurrection Act threat), and gave `Date Check` lines and an excluded-items list. Built as 15 events.

The prompt was only partly followed, and the same kinds of error still got through:

- Footnote numbers glued to sentences, summary tables and speculative "Why It Matters" prose were still present. A Wikipedia article and a children's-encyclopedia mirror (kiddle.co) were cited. Quotes carried zero-width characters (U+200B/C/D), which the verifier now strips.
- **Conflated incidents:** the Insurrection Act section described the Jan 14 Minneapolis shooting as fatal and attached Vance's "a tragedy of her own making" remarks "on Thursday". The Jan 14 shooting was non-fatal (`evt-2026-01-14-015`), and Vance's remarks concern Renée Good and appear to date from Thursday Jan 8. Only Trump's threat and AP's federal-agent figures are kept. The Vance remarks are not recorded anywhere in the archive yet; a reviewer may want to add them to Jan 8 with a source.
- **Wrong name:** the Greenland section named Mute Egede as Greenland's prime minister; it is Jens-Frederik Nielsen (`evt-2026-01-13-005`). That claim was dropped.
- **Later information:** the Uganda section mixed in later counting (provisional >70%/19%, and a final 24.7% for Bobi Wine). The final figure was dropped; the provisional tally is kept with a note that it probably reflects Jan 16 counting. Check this when building Jan 16-17 to avoid double counting.
- **Wrong-date source:** the Maharashtra section's 3.48 crore voter figure was sourced to a December 2025 article and was dropped.
- Weak sources kept but rated `low`: AffairsCloud (Yemen PM), World Socialist Web Site (Japan-Philippines $6 million figure), BCIT News (Carney quotes).

The report's "Excluded or uncertain items", for placement on later days:
- A Canadian dying "at the hands of the Iranian authorities" (Jan 15; its only source was BCIT News).
- The attack on Bobi Wine's wife (Jan 24).
- Erfan Soltani released on bail in Iran (date unknown).
- Coordinated Balochistan Liberation Army attacks with 33 killed (date unknown).

Arctic Endurance: `evt-2026-01-14-006` left its start date open; `evt-2026-01-15-006` records Macron saying on Jan 15 that it had already begun.

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

## Deep-research prompt (rewritten 2026-09-24)

`llm_prompt.txt` was rewritten from scratch so a fresh run does not need extra instructions. It now covers every failure mode seen in days 06-14:

- It names the daily Wikipedia page (`Portal:Current_events/YYYY_Month_D`) and forbids the monthly index. This caused the Jan 10 and Jan 14 duplicates.
- A date check for every event: only things that happened, or were first reported, on the day. It excludes later events and recaps of earlier ones, and each event gets a `Date Check` line stating what was new that day. This addresses the March leakage into 06-09 and the Jan 30 items in the Jan 14 report.
- Wikipedia is never a source. Portal items must be traced to the outlet the portal cites, or listed as not covered. Some Jan 14 events cited only "via Wikipedia".
- Every source needs a full URL, its publication date, and an exact quote from the article body. Headlines must be labelled `Headline:`. The Jan 10a report had no URLs, and Jan 13-14 had headline-only quotes.
- URLs must be plain text: no Markdown escaping, tracking parameters or citation tokens. Jan 14 had `\_`/`\&` escapes, embedded images and `utm_source` links.
- No executive summary, risk matrix, forecasts or strategic conclusion. The Jan 14 report's speculative framing had to be stripped.
- The report ends with two sections used during conversion. "Portal items not covered" becomes portal-only events. "Excluded or uncertain items" goes into this handoff for placement on the right day.

The `## Event:` layout and field labels are unchanged, apart from the new `Date Check` field, a `Missing` casualty field, and one-line pipe-separated source entries. The conversion procedure in `reference/schema/AUTHORING_GUIDE.md` still applies.

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

## Next steps

1. Human-review 10-15 and flip them to `reviewed` (same pass already done for 01-09).
2. Run deep research for 16-31 with `llm_prompt.txt` as it now stands (only the `DATE_ISO` line needs editing), saving each report as `reference/deep-research/2026/01/2026-01-DDa.md`. Use the next free letter if a day is re-run. Check the report's "Excluded or uncertain items" list against this file's open issues (Benin results, and the Jan 30 Mangione and Epstein items).
3. Convert each day, validate, verify quotes/URLs against the source report, and link `related_events` to prior days.
4. Once all 31 days are expanded, build the January 2026 summary from the YAML files, deduplicating follow-up events via `related_events`.
