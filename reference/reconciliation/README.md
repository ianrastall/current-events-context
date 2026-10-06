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

Guarded factual and bibliography repairs now regenerate selected January
drafts. The unchanged reviewed dates are January 2-3 and 5-7. The original
authored inputs remain byte-identical; corrected output is not marked reviewed.
`january-review-queue.json` records outstanding publisher review for January
10-15. Its machine checks do not verify the underlying facts.

`unpinned-source-plan.json` preserves publication identities for the 58 daily
files from August 7 through October 4, 2026. Their approved migration policy
uses current revisions as new inputs; the old daily files remain preserved.
Candidate extraction differences for these dates may reflect source changes.

The completed offline replay produced 8,891 side-by-side candidates under
`provisional/extraction-v1/`, leaving 152 historical dates unavailable.
`extraction-report.json` records per-date reconciliation;
`extraction-summary.json`, `warnings-summary.json`, and
`unresolved-roles.json` summarize coverage and unresolved interpretations.
The 637 unknown entries remain explicit rather than receiving guessed roles.
`verification.json` records executed checks and their limits, with cross-process
serialization results in `cross-process-check.json`. The final work-pass section
in `HANDOFF.md` lists changed files, commands, source access, and next steps.
