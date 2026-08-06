# HANDOFF: current-events-context rewrite

## Status

Stage 0 (consolidated seed ingest module) is implemented, live-tested against
Wikipedia/GDELT, and sitting **uncommitted** in the working tree pending
review. Nothing has been pushed. If you are picking this up cold: read
"Where things stand" below, review the diff (`git status`, `git diff`), then
either commit it or ask for changes.

Stages 1-3 (contribution intake, automated verify+rework, monthly rollup) are
still just the plan described in "Remaining stages" below — no code for them
exists yet.

## Where things stand (this session)

**The repo now lives at `D:\dev\proj\current-events-context`.** It did not
start there: this session initially found that folder empty, went looking for
"the real repo," found a populated clone at `D:\GitHub\current-events-context`
matching the audit and the hardcoded path in `generate_prompts.py`, and did
all of the Stage 0 work described below there — without checking first that
`D:\GitHub` was actually meant to be superseded (it was; the user had to
correct this explicitly). Once caught, the full repo (`.git` and all, so the
two local-only commits below came along intact) was copied into
`D:\dev\proj\current-events-context` — verified identical (commit history,
working-tree diff, and file counts all matched) before the old
`D:\GitHub\current-events-context` copy was deleted. **If some future session
finds this repo anywhere other than `D:\dev\proj\current-events-context`,
stop and ask before assuming that's the right location** — don't repeat this.

Before any of the Stage 0 work: an architecture audit done in a separate
Claude.ai conversation (findings below, still accurate) plus a git-status
surprise found in the (then-current) local clone — 19 unpushed-from-origin
commits to pull *and* real uncommitted work sitting in the tree that wasn't
mentioned in the original audit (6 manually-reworked Jan 2026 deep-schema
files, 2 contributed research drafts, 2 backfilled 2002 seed files, plus
`diagnose_monthly_page.py`/`diagnostic_output.html`). That was committed as a
checkpoint (`c4067f9`) and merged with origin (`66ba544`) before any rewrite
work began — both are local-only, not pushed.

Stage 0 was then designed (plan approved by user) and built:

- **New package `seed/`** (`ratelimit.py`, `wikipedia.py`, `gdelt.py`,
  `merge.py`, `gitops.py`, `report.py`, `cli.py`, `__main__.py`) replaces
  `update_data.py`, `backfill_history.py`, `backfill_batches.py`,
  `query_gdelt.py`, and `wiki_parser.py` — all five deleted (`git rm`, not yet
  committed). One CLI: `python -m seed {date|range|plan} ...`.
- **Bug fixed:** `seed.ratelimit.call_with_backoff` is now the single retry
  path used by *every* fetch, including the daily-cron `date` command —
  closing the old gap where `update_data.py` had no 429 handling at all.
  Confirmed live: a real GDELT 429 during testing was retried with proper
  backoff and the run still completed cleanly (Wikipedia data saved, `gdelt`
  block simply omitted) instead of crashing.
- **Bug fixed:** `wikipedia_revision_id` is now populated (added `rvprop=ids`
  to the MediaWiki fetch). Confirmed live on 2026-08-05
  (`wikipedia_revision_id: 1368004410`).
- **New seed file shape** — `source_page` now mirrors
  `daily-events.schema.json`'s field names (`portal`/`language`/
  `wikipedia_revision_id`) so Stage 2 can carry it through unchanged later.
  Wikipedia categories and GDELT articles sit as sibling blocks. See
  `seed/merge.py` docstring for the exact shape.
- **Also fixed along the way (found during live testing, not in the original
  plan):** the old `query_gdelt.py` retried HTTP 429 and 5xx but *not*
  malformed/truncated JSON on a 200 response — observed live, GDELT appears to
  degrade to bad JSON under the same load that produces its 429s. Now
  retryable too (`seed/gdelt.py`).
- `.github/workflows/daily_update.yaml` updated to call `python -m seed date
  "$TARGET_DATE"`; the outer bash retry loop trimmed from 4 attempts to 2
  (real backoff now happens inside `seed`, so stacking the old 4-attempt outer
  loop on top could turn a persistent outage into an hours-long stuck run).
- `README.md` left untouched — it has no CLI usage section referencing the
  old scripts, so there was nothing there to update.
- **Not done, deliberately out of scope for Stage 0, still flagged from the
  original audit:** `.gitignore` is still the full Visual Studio template.
  Trivial to fix, just wasn't part of the approved Stage-0 plan — do it as a
  one-line follow-up whenever convenient.

Full design record: `C:\Users\Ian\.claude\plans\zany-strolling-toucan.md` on
the machine this was built on (not in the repo).

**Not yet done:** committing this work, re-running the full backfill with
`seed/` (the agreed from-scratch re-backfill of all ~8,700 days hasn't
started — Stage 0 needs sign-off first), Stages 1-3.

## Original audit findings (from the Claude.ai session that started this)

Repo audited: README.md, update_data.py, backfill_history.py,
backfill_batches.py, wiki_parser.py, query_gdelt.py, generate_prompts.py,
diagnose_monthly_page.py, diagnostic_output.html, plus the live GitHub repo's
`.github/workflows/`, `reference/schema/`, `reference/deep-research/`, prompt
files, `filepaths.txt`, `.gitignore`, `copilot_prompts/`.

1. Three independent implementations of "fetch a Wikipedia day, write seed
   YAML" existed (`update_data.py`, `backfill_history.py`,
   `backfill_batches.py`) — **resolved by Stage 0**.
2. `update_data.py` didn't catch `RateLimitError` — **resolved by Stage 0**.
3. Real Deep Context coverage is 44 of 8,741 day files (~0.5%) — **unresolved,
   Stage 1 (contribution intake) is the fix.**
4. `generate_prompts.py` hardcodes a Windows path
   (`D:\GitHub\current-events-context`) — **unresolved, and now doubly
   stale**: that path was deleted this session (see above); the repo lives at
   `D:\dev\proj\current-events-context` now. Not touched this session (out of
   scope for Stage 0; belongs with the Stage 1/2 prompt work, and should
   probably stop hardcoding an absolute path at all rather than get a new one).
5. `llm_agent_prompt.txt` embeds a hand-duplicated schema template that has
   drifted from `daily-events.schema.json` (wrong `schema_version`, illegal
   status enum value, missing 4 of 8 required top-level keys) — **unresolved**,
   Stage 2 work (prompts should generate from the JSON Schema, not hand-copy it).
6. `query_gdelt.py` was a fully separate, unintegrated pipeline writing to a
   `reference/yaml/` path that didn't exist in the committed tree — **resolved
   by Stage 0** (GDELT now merges into the same seed file as Wikipedia).
7. `.gitignore` is the full default Visual Studio template in a pure-Python
   repo — **unresolved**, flagged again above.
8. `daily-events.schema.json`'s `source_page.wikipedia_revision_id` was never
   populated — **resolved by Stage 0**.

## Decisions already made (carried over, still in force)

- Total rewrite, not incremental patching.
- A full re-backfill of all ~8,700 seed days from scratch is acceptable —
  owner is willing to redo it if it means it's done right.
- GDELT merges into the seed stage alongside Wikipedia (done, Stage 0).
- The schema is suspected of being over-built; of the 44 existing schema-2.2
  files, only a handful will be kept as reference examples once Stage 2 is
  built — exact count/criteria still undecided.
- Stage 2 (verify + rework) must be fully automated — no daily manual
  attention from the owner.
- Implementation happens in Claude Code / VS Code, not the Claude.ai browser.

## Remaining stages (unbuilt — plan only)

**Stage 1 — Contribution.** A volunteer runs the research prompt
(`llm_prompt.txt`, lightly cleaned) against a date and drops the raw markdown
into `contrib/<date>.md` via PR/issue. No YAML or schema knowledge required.

**Stage 2 — Verify and rework, automated.** Seed file + contributed markdown
in; verify prompt (checks claims, writes nothing) then rework prompt (merges
into schema-2.2, generated from the live JSON Schema so it can't drift again)
then `reference/schema/validate.py` before anything is written. Must run
without manual copy-paste. Open question: what dispatches it in production
(scheduled GitHub Action calling an LLM API directly? a periodic Claude Code
task? something else) — still undecided.

**Stage 3 — Monthly rollup.** New capability: once a month's days are through
Stage 2, a synthesis prompt produces a month-level deep dive referencing the
`evt-` IDs already established across those days, using the existing
`related_events`/`works_cited` cross-reference fields.

## Open decisions — still unresolved

- Which of the 44 existing Deep Context files (if any) to keep as reference
  examples once Stage 2 exists, and on what basis.
- What the trimmed schema actually cuts — needs a field-by-field pass against
  `daily-events.schema.json` and `reference/schema/validate.py`, done inside
  Claude Code rather than round-tripped through chat.
- What dispatches Stage 2 in production (see above).

## Recommended next action

Review the Stage 0 diff (`git status`, `git diff` in
`D:\dev\proj\current-events-context`) and the live-test results recorded
above. Once approved: commit, decide whether/when to push, then either (a)
kick off the full seed re-backfill with `python -m seed range 2001-01-01
<today> --target all --commit --push --chunk month`, or (b) move straight to
designing Stage 1 (contribution intake) — owner's call on ordering.
