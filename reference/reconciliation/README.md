# Reconciled baselines

The pre-repair checkout is preserved at branch
`codex/checkpoint-before-repairs` (`4d198b05`). This includes the older local
expansions, regenerated seeds, and uncommitted inspection documents/reports.

`baseline.json` pins the published commit used for reconciliation.
`published-HANDOFF.md` preserves its January research and review notes.
The latest published January 1-15 expansions are imported byte for byte as
immutable synthesis inputs in `reference/expansion/authored/` and replayed
under `expanded/`. Seeds at ordinary daily paths retain their recorded
revision IDs. January review states and null provenance remain as published;
importing a snapshot does not claim it has been independently reviewed.

The two layers must be published together under a documented migration:
ordinary paths hold extraction; `expanded/` holds synthesis. This branch has
not been pushed. Before publication, reconcile candidate extraction against
cached sources and review the exact corpus/path changes. The checkpoint is
preservation, not schema approval.

Do not edit immutable authored inputs. Subsequent synthesis corrections
belong in guarded overlays or a newly identified authored input with recorded
provenance, followed by a rebuild.
