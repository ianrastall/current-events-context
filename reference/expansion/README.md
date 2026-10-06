# Expansion build tooling

Builds the schema-2.2 files in `expanded/` from a pinned portal revision, a
deep-research report and a per-day overlay. Runs offline; nothing here fetches
from the network.

```
python reference/expansion/build.py 2026-01-06            # write expanded/2026/01/2026-01-06.yaml
python reference/expansion/build.py $(cat reference/expansion/days.txt)
python reference/expansion/build.py --report 2026-01-06   # portal matching report only
python reference/expansion/build.py --todo 2026-01-06     # entities still missing a role
python reference/expansion/worksheet.py 2026-01-06        # one-line summary per event
```

Output is deterministic: the same inputs give byte-identical files. This has
been checked across `PYTHONHASHSEED` values.

## Inputs

`inputs.json` is the authoritative report selector. It names the exact report
and checks its SHA-256 after CRLF/LF normalization; neither suffix ordering nor
file size selects a report. January 1-15 replay the newer published authored
snapshots; unchanged replay preserves review state, while guarded corrections
reset review state to draft. Historical positional overlays
for those days are retained as evidence but do not apply to these snapshots.
Changing a registered report requires an explicit, reviewed manifest change.

Register a new day after saving its report:

```
python reference/expansion/inputs.py 2026-01-16 --report reference/deep-research/2026/01/2026-01-16a.md
```

Authored snapshots are immutable source inputs imported from a pinned Git
commit. Building them preserves their exact bytes unless an explicit authored correction
applies. They are synthesis inputs,
not Wikipedia source caches. Their null revision IDs remain unknown.

| Path | Content |
|---|---|
| `wikitext/<date>.wiki`, `.json` | Raw portal wikitext at the revision recorded in the seed file, with title, revision ID, revision timestamp and SHA-256. Fetched once on 2026-09-22 by revision ID. Wikipedia text is CC BY-SA 4.0. |
| `../deep-research/<YYYY>/<MM>/` | Deep-research reports (Markdown) |
| git commit `0f5cbef6` | Earlier schema-2.1 expansions, read with `git show` |
| `legacy_fix/` | Hand re-indented copy of the one event needed from the 2.1 file for 2026-03-18, whose indentation was flattened in the original |
| `overlays/<date>.json` | Per-day judgment layer (below) |
| `roles.json` | Shared roles and descriptions for people and organizations; `__as_org__` reclassifies names the heuristics mistake for people |

The seed source cache under `reference/sources/wikipedia/` imports these exact
inputs and holds additional pinned revisions, including March 10-11. Neither
source cache may be hand-edited. `legacy-fixes.json` guards the original Git
blob and the corrected legacy interpretation. `inputs.json` guards both source
identities and parsed sequences before applying any positional overlay.

## Overlay keys

Event keys are `md:<n>` for the n-th deep-research or 2.1 event (before any
exclusion) and `p:<n>` for the n-th portal bullet in the pinned revision.

| Key | Meaning |
|---|---|
| `mode` | `"legacy"` builds from the 2.1 expansion instead of the report |
| `match` | `{"md:n": portal index or null}` overrides the automatic matching |
| `drop_md` | report events excluded as misdated or unsupported |
| `legacy_extra` | 2.1 events carried forward alongside the report's events |
| `ev` | per-event shorthand: `h` headline, `i` importance, `k`/`w`/`m`/`a`/`d` killed, injured, missing, arrests, displaced, `pl` places, `st` states, `org`/`ppl` entities, `unc` uncertainty notes, `conf` confidence, `note`, `sub`, `cat`, `tags`, `et`, `topics`, `why`, `act`, `act2`, `ongoing` |
| `events` | full deep-merge patches, if shorthand is not enough |
| `additional_works` | new bibliography entries with `title`, `outlet`, `url`, and actual `accessed` date; IDs are assigned deterministically and duplicate URLs fail |
| `related` | groups of event keys to cross-link in `related_events` |
| `analytical_overview`, `strategic_conclusion` | replace the text taken from the report |

## Authored corrections

January authored snapshots use stable event IDs, not positional overlays.
Print a guarded locator for the event you intend to correct:

```
python reference/expansion/corrections.py 2026-01-10 --event-id evt-2026-01-10-001
```

Save one or more locator objects as a JSON array in
`authored-overlays/2026-01-10.json`. Supply a factual `reason` and a nonempty
`patch` containing the synthesis fields to change. The builder verifies the
snapshot hash, selected report hash, event ID and full original event hash.
It rejects drift, duplicate event patches and event-ID changes, validates the
result and resets all three review fields to draft. Corrections require source evidence; an unresolved review lead alone does not
justify a patch. `--document` prints a whole-snapshot guard for a coordinated
prose, bibliography or event change. Such a record must be the sole record in
its overlay and guards the entire original document. The corrected document
passes schema and reference validation before writing.

For historical March build overlays, changing an overlay requires explicit
review of its hashes in `inputs.json`. The portal and parsed-event hashes must
still identify the intended source positions. Never blindly update hashes to
bypass a drift failure. New registered days without historical overlays can
build normally from their explicitly selected report and pinned portal.
Do not edit files in `expanded/` or immutable authored inputs by hand.

## Machine review queue

```
python reference/expansion/review.py 2026-01-10 2026-01-11 --output reference/reconciliation/january-review-queue.json
```

Supply every intended date; the command regenerates its output. It checks
URLs and quotations against selected reports and records portal-only events
and later publication dates for publisher review. It does not mark any file
reviewed. Bibliography validation also requires each external reference to
identify the source URL, rather than an unrelated existing entry.
