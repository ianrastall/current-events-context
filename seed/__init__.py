"""
seed — consolidated ingest pipeline for daily "seed" YAML files.

Replaces update_data.py, backfill_history.py, backfill_batches.py,
query_gdelt.py, and wiki_parser.py (Stage 0 of the pipeline rewrite;
see HANDOFF.md). Produces <YYYY>/<MM>/<YYYY-MM-DD>.yaml seed files
merging Wikipedia Current Events portal bullets with GDELT articles.

    python -m seed date [DATE]
    python -m seed range START END [options]
    python -m seed plan START END [options]

See seed/cli.py for the full command surface.
"""
