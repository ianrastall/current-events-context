# Handoff: January 2026 deep-context expansion

Last updated: 2026-09-23

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
| 06-09 | Yes | Schema 2.2 | `draft`, converted 2026-09-23 |
| 10 | Yes, but no source URLs | Schema 2.2 | `draft`, weak sourcing, re-run recommended |
| 11-31 | No | Portal stub | Needs a deep-research run |

All of 01-10 pass `validate.py` with `jsonschema` installed, and every `related_events` link across 01-10 resolves.

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
- `2026-01-10.yaml` has no external sources because the Jan 10 report contains no URLs. Three events there rest only on that report: Iran crackdown figures, Talaud earthquake, Victoria bushfire death. Re-running Jan 10 is the cleanest fix.
- The Benin election results excluded from Jan 9 should be placed on the correct mid-January day when that day is researched.
- `copilot_prompts/` holds prompts for 01-01 to 01-10 built from the schema 2.1 template. They are now stale; left in place pending the owner's decision.
- `llm_agent_prompt.txt` and `llm_review_prompt.txt` still embed the schema 2.1 template.

## Recommended addition to the deep-research prompt

To cut down on leakage of later events, consider adding to the FACT RULES in `llm_prompt.txt`:

```text
- Report only events that occurred on DATE_ISO or were first reported on DATE_ISO. Do not include events from later dates, even if later sources discuss them.
- Every source must include a full URL. Prefer sources published on DATE_ISO or within two days after it; flag any source published more than a week later.
```

## Next steps

1. Human-review 06-10 and flip them to `reviewed`.
2. Run deep research for 11-31 (and re-run 10), saving each report as `reference/deep-research/2026/01/2026-01-DDa.md`.
3. Convert each day, validate, and link `related_events` to prior days.
4. Once all 31 days are expanded, build the January 2026 summary from the YAML files, deduplicating follow-up events via `related_events`.
