"""
seed.merge — combine a Wikipedia day result and an optional GDELT block into
one seed YAML document, and read/write it at its repo-standard path.

Seed file shape (written to <YYYY>/<MM>/<YYYY-MM-DD>.yaml, same path the old
pipeline used):

    date: '2026-01-06'
    source_page:
      portal: 'Portal:Current events/2026 January 6'
      language: en
      wikipedia_revision_id: 1234567890   # null when unavailable (e.g. monthly-HTML fallback)
    wikipedia:
      categories:
        Uncategorized: [...]
    gdelt:                                 # omitted entirely when not queried
      queried_at: '...Z'
      article_count: 42
      articles: [...]

`source_page` deliberately mirrors daily-events.schema.json's field names
(portal/language/wikipedia_revision_id) so Stage 2 (the schema-2.2 rework
step) can carry it through unchanged instead of re-deriving it.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import yaml

from seed.gdelt import GDELT_EARLIEST

REPO_ROOT = Path(__file__).resolve().parent.parent


def output_path(day: date) -> Path:
    return REPO_ROOT / f"{day.year}" / f"{day.month:02d}" / f"{day.isoformat()}.yaml"


def already_saved(day: date) -> bool:
    return output_path(day).exists()


def should_query_gdelt(day: date) -> bool:
    """GDELT's archive starts 2015-02-19; today's data is always incomplete."""
    gdelt_start = date.fromisoformat(GDELT_EARLIEST)
    today = datetime.now(timezone.utc).date()
    return gdelt_start <= day < today


def build_seed_doc(
    *,
    day: date,
    source_title: str,
    revision_id: int | None,
    categories: dict[str, list[str]],
    gdelt_block: dict | None,
) -> dict:
    doc: dict = {
        "date": day.strftime("%Y-%m-%d"),
        "source_page": {
            "portal": source_title,
            "language": "en",
            "wikipedia_revision_id": revision_id,
        },
        "wikipedia": {
            "categories": categories,
        },
    }
    if gdelt_block is not None:
        doc["gdelt"] = gdelt_block
    return doc


def save(day: date, doc: dict) -> Path:
    path = output_path(day)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(doc, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return path
