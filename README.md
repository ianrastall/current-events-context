# current-events-context

Daily current-events context for LLMs. Source extraction and researched
synthesis have separate provenance and are stored separately.

| Path | Purpose |
|---|---|
| `<YYYY>/<MM>/<YYYY-MM-DD>.yaml` | Wikipedia seed archive; some later files still use the legacy shape |
| `expanded/<YYYY>/<MM>/<YYYY-MM-DD>.yaml` | Schema-2.2 researched synthesis |
| `reference/deep-research/` | Source research reports |
| `reference/expansion/inputs.json` | Explicit report/snapshot identities |
| `reference/schema/` | Synthesis contract, authoring guide and validator |
| `reference/sources/wikipedia/` | Exact immutable source payloads and provenance |
| `provisional/extraction-v1/` | Separate, locally regenerated extraction candidates |
| `seed/` | Collection CLI and archival migration tools |

The repository is transitioning from published mixed daily paths to separate
layers. See `reference/reconciliation/README.md` before publication. Imported
review states preserve prior work; draft research still needs factual review.

## Setup and verification

Requires Python 3.10 or later and Git for optional Git workflows.

```
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python reference/schema/validate.py --archive-root expanded expanded/2026/01/2026-01-15.yaml
```

## Collection

```
python -m seed plan 2026-01-01 2026-01-31
python -m seed date 2026-10-04 --no-overwrite
python -m seed range 2026-01-01 2026-01-31 --no-gdelt
```

`date` overwrites by default; `range` skips existing dates by default. These
commands acquire network data and are not parser-replay commands. GDELT is
optional live enrichment. Never use a full refetch to repair historical
extraction or add `--commit`/`--push` to provisional runs.

## Offline source replay

```
python -m seed cache 2026-01-01 2026-01-31
python -m seed reparse 2026-01-01 2026-01-31 --output-root provisional/extraction-v1
```

`cache` acquires the oldids already recorded in seeds. For legacy daily files
without an oldid, `cache --capture-unpinned` explicitly records current revisions
as new inputs without changing their daily files; it cannot recover their
original capture. `--skip-unpinned` instead leaves them out. These policies are
mutually exclusive. `reparse` never acquires network data and fails on missing
inputs by default. `--cached-only` explicitly
permits a partial run with every skipped date recorded in `report.json`.
Candidates retain hierarchy, raw fragments, links, citations and warnings.
See `reference/schema/EXTRACTION_MIGRATION.md` for the public replacement gate.
New network captures also save their raw input and a structured artifact under
`provisional/captures/`; optional Git workflows include the capture's inputs.

## Research and synthesis

Start a research run with `llm_prompt.txt` and the exact daily date. Save the
report under `reference/deep-research/<YYYY>/<MM>/`, then register it:

```
python reference/expansion/inputs.py 2026-01-16 --report reference/deep-research/2026/01/2026-01-16a.md
python generate_prompts.py 2026-01-16
```

Follow `reference/schema/AUTHORING_GUIDE.md`. Write synthesis under
`expanded/`; never replace a seed with model prose. Corrections belong in
durable guarded overlays, followed by regeneration and validation. Check
original publishers for dates, facts, quotations and source disagreements.
Size does not determine whether a file is complete or reviewed.

Unchanged January 2-3 and 5-7 preserve published reviewed status. January 1,
4, 8-9 and 10-15 are draft after import or guarded corrections.
January 16-31 await research. A monthly summary should be generated only
from completed daily inputs, with related developments deduplicated.

The archive is offered under the repository's license; cached Wikipedia
source material retains its CC BY-SA attribution obligations.
