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

| Path | Content |
|---|---|
| `wikitext/<date>.wiki`, `.json` | Raw portal wikitext at the revision recorded in the seed file, with title, revision ID, revision timestamp and SHA-256. Fetched once on 2026-09-22 by revision ID. Wikipedia text is CC BY-SA 4.0. |
| `../deep-research/<YYYY>/<MM>/` | Deep-research reports (Markdown) |
| git commit `0f5cbef6` | Earlier schema-2.1 expansions, read with `git show` |
| `legacy_fix/` | Hand re-indented copy of the one event needed from the 2.1 file for 2026-03-18, whose indentation was flattened in the original |
| `overlays/<date>.json` | Per-day judgment layer (below) |
| `roles.json` | Shared roles and descriptions for people and organizations; `__as_org__` reclassifies names the heuristics mistake for people |

This wikitext cache serves only this build. It is not the persistent source
cache planned for the seed parser rewrite (see `HANDOFF.md`), although it
records the same identity fields.

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
| `related` | groups of event keys to cross-link in `related_events` |
| `analytical_overview`, `strategic_conclusion` | replace the text taken from the report |

To correct a generated file, change its overlay or `roles.json` and rebuild.
Do not edit files in `expanded/` by hand.
