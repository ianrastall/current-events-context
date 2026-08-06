"""
seed.gdelt — fetch news articles from the GDELT 2.0 Doc API for a given date.

Absorbs query_gdelt.py. Retry/backoff now goes through seed.ratelimit
(previously an ad hoc 3-attempt loop local to this script); everything else
(theme grouping, article cleaning, dedup/sort) is unchanged.

Known limitation, carried over unchanged: the GDELT artlist endpoint typically
does NOT return a 'themes' field, so classify_themes() will often produce an
empty dict per article. Fixing that (switching to GDELT's daily CSV exports)
is out of scope here.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests

from seed.ratelimit import RateLimitError, GDELT_POLICY, call_with_backoff

log = logging.getLogger(__name__)

# GDELT's public archive goes back reliably to about February 2015.
GDELT_EARLIEST = "2015-02-19"

USER_AGENT = "CurrentEventsYAMLBuilder/1.0"

# ---------------------------------------------------------------------------
# GDELT theme groups — controls what topics land in seed files.
# Feel free to add/remove GDELT themes to suit the repo's focus.
# Full theme list: https://blog.gdeltproject.org/gdelt-2-0-our-global-similarity-graph-2-0/
# ---------------------------------------------------------------------------
THEME_GROUPS = {
    "conflict":    ["CRISISLEX_CONFLICT", "MILITARY", "TERROR", "REBELLION"],
    "politics":    ["LEGISLATION", "ELECTION", "DEMOCRACY", "GOV"],
    "economy":     ["TAX_FNCACT", "ECON_BANKRUPTCY", "ECON_INFLATION", "ECON_TRADE"],
    "environment": ["ENV_CLIMATECHANGE", "ENV_DISASTER", "ENV_DEFORESTATION"],
    "health":      ["HEALTH_PANDEMIC", "MEDICAL", "HEALTH_VACCINATION"],
    "technology":  ["CYBER_ATTACK", "AI_TECHNOLOGY", "SCIENCE"],
}

FLAT_THEMES = " OR ".join(f"theme:{t}" for themes in THEME_GROUPS.values() for t in themes)

_session = requests.Session()


def _fetch_once(target_date_str: str, max_records: int) -> list[dict] | None:
    clean_date = target_date_str.replace("-", "")
    params = {
        "query":         f"sourcelang:eng ({FLAT_THEMES})",
        "mode":          "artlist",
        "maxrecords":    str(min(max_records, 250)),  # GDELT API hard cap
        "format":        "json",
        "startdatetime": f"{clean_date}000000",
        "enddatetime":   f"{clean_date}235959",
        "sort":          "HybridRel",  # balances relevance + recency
    }

    r = _session.get(
        "https://api.gdeltproject.org/api/v2/doc/doc",
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )

    if r.status_code == 429:
        raise RateLimitError(int(r.headers.get("Retry-After", 0)))
    if r.status_code >= 500:
        log.warning("GDELT HTTP %d for %s — treating as retryable.", r.status_code, target_date_str)
        raise RateLimitError(0)  # no Retry-After header from GDELT; use policy backoff
    if r.status_code != 200:
        log.error("GDELT HTTP %d for %s — giving up.", r.status_code, target_date_str)
        return None

    try:
        return r.json().get("articles", [])
    except ValueError:
        # GDELT sometimes returns HTTP 200 with a malformed/truncated body under
        # the same load that produces its 429s — treat it as retryable too,
        # rather than a terminal failure on the first occurrence.
        log.warning("GDELT returned invalid JSON for %s — treating as retryable.", target_date_str)
        raise RateLimitError(0)


def fetch_gdelt_articles(target_date_str: str, max_records: int = 75) -> list[dict] | None:
    """
    Fetch top English-language news articles from GDELT for target_date_str
    (YYYY-MM-DD). Returns a list (possibly empty for a quiet day), or None on
    a definitive fetch failure.
    """
    try:
        return call_with_backoff(
            lambda: _fetch_once(target_date_str, max_records),
            policy=GDELT_POLICY,
            label=f"GDELT {target_date_str}",
        )
    except requests.RequestException as e:
        log.error("Network error querying GDELT for %s: %s", target_date_str, e)
        return None


def classify_themes(raw_themes_str: str) -> dict[str, list[str]]:
    """Maps a GDELT semicolon-delimited theme string into THEME_GROUPS buckets."""
    if not raw_themes_str:
        return {}
    raw = {t.strip() for t in raw_themes_str.split(";")}
    result = {}
    for group, members in THEME_GROUPS.items():
        matched = [t for t in members if t in raw]
        if matched:
            result[group] = matched
    return result


def clean_article(article: dict) -> dict:
    """
    Reduce a raw GDELT article dict to the fields useful for seed files.
    Note: GDELT's artlist mode returns 'seendate' (when GDELT indexed it), not
    a true publication date. Field is named 'indexed_at' to reflect that.
    """
    title  = (article.get("title") or "").strip()
    url    = (article.get("url") or "").strip()
    domain = (article.get("domain") or "").strip()

    raw_date = article.get("seendate", "")  # e.g. "20260322T120000Z"
    indexed_at = None
    try:
        indexed_at = datetime.strptime(raw_date, "%Y%m%dT%H%M%SZ").strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        if raw_date:
            log.warning("Unparseable seendate %r for %s", raw_date, url or "unknown URL")

    try:
        tone = round(float(article.get("tone")), 2)
    except (TypeError, ValueError):
        tone = 0.0

    entry = {
        "title":      title,
        "url":        url,
        "domain":     domain,
        "indexed_at": indexed_at,
        "tone":       tone,  # negative = crisis/conflict framing, positive = positive sentiment
    }
    classified = classify_themes(article.get("themes", ""))
    if classified:
        entry["themes"] = classified
    return entry


def build_gdelt_block(articles: list[dict]) -> dict:
    """Build the seed file's `gdelt:` block from raw GDELT article dicts."""
    cleaned = []
    seen_urls = set()
    for raw in articles:
        entry = clean_article(raw)
        if entry["url"] and entry["url"] not in seen_urls and entry["title"]:
            seen_urls.add(entry["url"])
            cleaned.append(entry)

    # Most negative tone first (crises/conflicts surface at top).
    cleaned.sort(key=lambda a: a["tone"])

    return {
        "queried_at":    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "article_count": len(cleaned),
        "articles":      cleaned,
    }
