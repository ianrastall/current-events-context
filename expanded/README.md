# Expanded daily synthesis

Schema-2.2 researched snapshots live at
`expanded/<YYYY>/<MM>/<YYYY-MM-DD>.yaml`, separately from daily seeds and
archival extraction candidates. The contract is
`reference/schema/daily-events.schema.json`; authoring instructions are in
`reference/schema/AUTHORING_GUIDE.md`.

## Current inputs and review state

| Dates | Status | Inputs |
|---|---|---|
| January 2-3 and 5-7, 2026 | reviewed, preserved from publication | Exact authored snapshots pinned in `reference/expansion/inputs.json` |
| January 1, 4, 8-9 and 10-15, 2026 | draft | Published authored inputs, with guarded corrections where needed; January 10-12 use replacement reports |
| March 5-18, 2026 | draft | Pinned portal revisions, selected reports or legacy snapshots, and guarded synthesis overlays |

Importing a reviewed snapshot preserves its recorded state; this pass does
not claim an independent factual review. March 10-11 use earlier synthesis
because no research reports exist. March 18 uses a hash-guarded interpretation
repair for a legacy event whose YAML indentation was flattened.

## Rebuild and validate

```
python reference/expansion/build.py 2026-01-10 2026-03-18
python reference/schema/validate.py --archive-root expanded expanded/2026/01/2026-01-10.yaml expanded/2026/03/2026-03-18.yaml
```

The manifest explicitly selects every input. Drift in a report, authored
snapshot, portal source, parsed portal/report sequence, or positional overlay
fails the build. January snapshots replay byte for byte unless an explicitly
guarded authored correction exists. Correct generated synthesis through
`reference/expansion/authored-overlays/` or the guarded build overlays, then
regenerate. Never edit generated files or immutable source inputs directly.

## Review limitations

Research reports and earlier expansions contain model-authored claims. Schema,
quote-to-report and URL-to-report checks do not verify original publishers.
The archived published handoff at
`reference/reconciliation/published-HANDOFF.md` retains January review leads,
excluded items and dating concerns, including later Uganda counting, Benin
results, and January 30 items. Consult those leads before continuing research.
Historical January positional overlays are inactive for the newer snapshots.

March overlays preserve existing exclusions and uncertainty notes. Reports for
March 6, 13 and 15 were unsuitable for direct conversion, so those days use
legacy synthesis. These draft files still need factual source review; rebuilding
does not change their review state.

Original source facts and Wikipedia prose are retained as source evidence.
Synthesis corrections require documented evidence and must survive a rebuild.

## Guarded corrections in this pass

January 4 records the sportspeople's public appeal, January 8 the official
royal-commission announcement, and January 9 formal establishment and the
follow-up interview. January 9 also records the oil-revenue order's signing;
January 10 distinguishes subsequent reporting from that earlier action.
January 15 excludes provisional Uganda results and arrests reported January
16. January 1 and 12 have repaired bibliography pointers; homepage-only
citations are no longer treated as article support. All affected files remain
draft. Original authored snapshots and reports remain intact.

`reference/reconciliation/january-review-queue.json` covers January 10-15. Its
machine flags are review leads, not findings that every later-published source
is misdated. Full factual review against original publishers remains pending.
