import requests
import yaml
import argparse
import time
import os
from datetime import datetime, timedelta, timezone


# ---------------------------------------------------------------------------
# GDELT theme groups — controls what topics land in your context files.
# Feel free to add/remove GDELT themes to suit your repo's focus.
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

FLAT_THEMES = " OR ".join(
    f"theme:{t}" for themes in THEME_GROUPS.values() for t in themes
)


def fetch_gdelt_articles(target_date_str: str, max_records: int = 75) -> list[dict] | None:
    """
    Fetches top English-language news articles from the GDELT 2.0 Doc API
    for a given date (YYYY-MM-DD).
    Returns a list of article dicts on success (may be empty for quiet days),
    or None on a definitive fetch failure (network/server error).

    NOTE: The GDELT artlist endpoint typically does NOT return a 'themes' field.
    Theme classification in clean_article() will silently produce empty dicts.
    If theme data is required, switch to GDELT's daily CSV exports instead.
    """
    max_records = min(max_records, 250)  # enforce GDELT API hard cap
    clean_date = target_date_str.replace("-", "")
    params = {
        "query":         f"sourcelang:eng ({FLAT_THEMES})",
        "mode":          "artlist",
        "maxrecords":    str(max_records),
        "format":        "json",
        "startdatetime": f"{clean_date}000000",
        "enddatetime":   f"{clean_date}235959",
        # HybridRel balances relevance + recency; alternatives: ToneDesc, DateDesc
        "sort":          "HybridRel",
    }
    headers = {
        "User-Agent": "CurrentEventsYAMLBuilder/1.0"
    }

    print(f"  Querying GDELT for {target_date_str}...")

    for attempt in range(3):
        try:
            r = requests.get(
                "https://api.gdeltproject.org/api/v2/doc/doc",
                params=params,
                headers=headers,
                timeout=30,
            )
        except requests.exceptions.RequestException as e:
            if attempt < 2:
                wait = 5 * (attempt + 1)
                print(f"  Network error ({e}). Retrying in {wait}s... (attempt {attempt+1}/3)")
                time.sleep(wait)
                continue
            print(f"  Network error after 3 attempts: {e}")
            return None

        if r.status_code == 200:
            try:
                return r.json().get("articles", [])
            except ValueError:
                if attempt < 2:
                    print(f"  Invalid JSON response. Retrying... (attempt {attempt+1}/3)")
                    time.sleep(5)
                    continue
                print("  Invalid JSON on all attempts — giving up.")
                return None

        elif r.status_code == 429:
            if attempt < 2:
                wait = 10 * (attempt + 1)
                print(f"  Rate-limited. Waiting {wait}s... (attempt {attempt+1}/3)")
                time.sleep(wait)
            else:
                print("  Rate-limited on final attempt — giving up.")
                return None

        elif r.status_code >= 500:
            if attempt < 2:
                wait = 5 * (attempt + 1)
                print(f"  HTTP {r.status_code} (server error). Retrying in {wait}s... (attempt {attempt+1}/3)")
                time.sleep(wait)
            else:
                print(f"  HTTP {r.status_code} on all attempts — giving up.")
                return None

        else:
            print(f"  HTTP {r.status_code} — giving up.")
            return None

    print("  Exceeded retries.")
    return None


def classify_themes(raw_themes_str: str) -> dict[str, list[str]]:
    """
    Maps a GDELT semicolon-delimited theme string into the THEME_GROUPS buckets.
    Returns a dict of {group: [matched_themes]}, skipping empty groups.
    """
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
    Reduces a raw GDELT article dict to the fields useful for context files.
    Note: GDELT's artlist mode returns 'seendate' (when GDELT indexed it), not
    a true publication date. Field is named 'indexed_at' to reflect this accurately.
    """
    title  = (article.get("title") or "").strip()
    url    = (article.get("url") or "").strip()
    domain = (article.get("domain") or "").strip()

    # seendate format from GDELT: "20260322T120000Z"
    # This is the GDELT index time, not necessarily the article's publication date.
    raw_date = article.get("seendate", "")
    indexed_at = None
    try:
        indexed_at = datetime.strptime(raw_date, "%Y%m%dT%H%M%SZ").strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        if raw_date:
            print(f"  Warning: unparseable seendate {raw_date!r} for {url or 'unknown URL'}")

    try:
        tone = round(float(article.get("tone")), 2)
    except (TypeError, ValueError):
        tone = 0.0

    classified = classify_themes(article.get("themes", ""))

    entry = {
        "title":      title,
        "url":        url,
        "domain":     domain,
        "indexed_at": indexed_at,
        "tone":       tone,   # negative = crisis/conflict framing, positive = positive sentiment
    }
    if classified:
        entry["themes"] = classified

    return entry


def build_context_doc(date_str: str, articles: list[dict]) -> dict:
    """
    Builds the full YAML document structure for a given date.
    """
    cleaned = []
    seen_urls = set()
    for raw in articles:
        entry = clean_article(raw)
        if entry["url"] and entry["url"] not in seen_urls and entry["title"]:
            seen_urls.add(entry["url"])
            cleaned.append(entry)

    # Sort: most negative tone first (crises/conflicts surface at top),
    # then positive. Change to `reverse=True` to flip to most positive first.
    cleaned.sort(key=lambda a: a["tone"])

    return {
        "date":           date_str,
        "generated_at":   datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source":         "GDELT 2.0 Doc API",
        "article_count":  len(cleaned),
        "theme_groups":   list(THEME_GROUPS.keys()),
        "articles":       cleaned,
    }


def output_path(date_str: str, base_dir: str) -> str:
    """
    Returns the full path for a date's YAML file:
      <base_dir>/YYYY/MM/YYYY-MM-DD.yaml
    e.g. reference/yaml/2026/03/2026-03-22.yaml
    """
    year, month, _ = date_str.split("-")
    return os.path.join(base_dir, year, month, f"{date_str}.yaml")


def save_yaml(doc: dict, base_dir: str) -> str:
    """
    Saves the context document to <base_dir>/YYYY/MM/YYYY-MM-DD.yaml.
    Returns the path it was saved to.
    """
    path = output_path(doc["date"], base_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            doc,
            f,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,    # preserve insertion order
            width=120,
        )
    return path


def date_range(start: str, end: str):
    """Yields YYYY-MM-DD strings from start to end (inclusive)."""
    current = datetime.strptime(start, "%Y-%m-%d")
    stop    = datetime.strptime(end,   "%Y-%m-%d")
    while current <= stop:
        yield current.strftime("%Y-%m-%d")
        current += timedelta(days=1)


def valid_date(value: str) -> str:
    """Argparse type validator — ensures YYYY-MM-DD format and a real calendar date."""
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return value
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Invalid date {value!r}. Use YYYY-MM-DD (e.g. 2026-03-21)."
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # GDELT's public archive goes back reliably to about February 2015.
    # Dates before this will return empty results.
    GDELT_EARLIEST = "2015-02-19"

    today     = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)

    parser = argparse.ArgumentParser(
        description=(
            "Fetch GDELT events and save per-day YAML context files.\n"
            "Files are written to <base-dir>/YYYY/MM/YYYY-MM-DD.yaml.\n"
            "Today is always skipped (incomplete data)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    date_group = parser.add_mutually_exclusive_group(required=True)
    date_group.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        type=valid_date,
        help="Fetch a single completed date (not today).",
    )
    date_group.add_argument(
        "--date-range",
        nargs=2,
        metavar=("START", "END"),
        type=valid_date,
        help="Fetch an inclusive date range, e.g. --date-range 2026-03-01 2026-03-07",
    )
    date_group.add_argument(
        "--backfill",
        action="store_true",
        help=(
            "Slowly backfill from yesterday back to GDELT_EARLIEST (~2015-02-19), "
            "skipping dates that already have a file. Uses a longer inter-request "
            "delay to be extremely polite. Safe to interrupt and re-run."
        ),
    )
    parser.add_argument(
        "--base-dir",
        default="reference/yaml",
        help="Base directory for output (default: reference/yaml). "
             "Files land at <base-dir>/YYYY/MM/YYYY-MM-DD.yaml.",
    )
    parser.add_argument(
        "--max-records",
        type=int,
        default=75,
        help="Max articles to fetch per day from GDELT (default: 75, max: 250)",
    )
    args = parser.parse_args()

    # -----------------------------------------------------------------------
    # Build the list of dates to process
    # -----------------------------------------------------------------------
    if args.date:
        d = datetime.strptime(args.date, "%Y-%m-%d").date()
        if d >= today:
            parser.error(f"{args.date} is today or in the future — data is incomplete. Use a past date.")
        if d < datetime.strptime(GDELT_EARLIEST, "%Y-%m-%d").date():
            parser.error(f"{args.date} is before GDELT's reliable archive start ({GDELT_EARLIEST}).")
        dates = [args.date]

    elif args.date_range:
        start_str, end_str = args.date_range
        start_d = datetime.strptime(start_str, "%Y-%m-%d").date()
        end_d   = datetime.strptime(end_str,   "%Y-%m-%d").date()
        gdelt_start = datetime.strptime(GDELT_EARLIEST, "%Y-%m-%d").date()

        if start_d > end_d:
            parser.error(f"Start date {start_str} is after end date {end_str}.")
        if start_d < gdelt_start:
            parser.error(f"Start date {start_str} is before GDELT's reliable archive start ({GDELT_EARLIEST}).")
        if end_d >= today:
            capped = yesterday.strftime("%Y-%m-%d")
            print(f"  Note: end date {end_str} capped to {capped} (today's data is incomplete).")
            end_d = yesterday

        dates = list(date_range(start_str, end_d.strftime("%Y-%m-%d")))
        if not dates:
            print("  No completed dates in that range.")
            raise SystemExit(0)

    else:  # --backfill
        # Walk backwards from yesterday to GDELT_EARLIEST, skip existing files.
        all_dates = list(date_range(GDELT_EARLIEST, yesterday.strftime("%Y-%m-%d")))
        all_dates.reverse()   # most recent first — fills gaps near the present edge first
        dates = [
            d for d in all_dates
            if not os.path.exists(output_path(d, args.base_dir))
        ]
        print(
            f"  Backfill mode: {len(dates)} dates missing "
            f"(out of {len(all_dates)} total since {GDELT_EARLIEST})."
        )

    # -----------------------------------------------------------------------
    # Fetch and save
    # -----------------------------------------------------------------------
    # Backfill uses a longer delay to be extremely polite to GDELT's servers.
    inter_request_delay = 5 if args.backfill else 2

    try:
        for i, d in enumerate(dates):
            print(f"\n[{i+1}/{len(dates)}] {d}")
            result = fetch_gdelt_articles(d, max_records=args.max_records)

            if result is None:
                # Definitive fetch failure (network/server error) — warn and skip.
                print(f"  Fetch failed — skipping. Re-run to retry.")
            elif len(result) == 0:
                # Successful query but genuinely no matching articles that day.
                print(f"  No matching articles for this date.")
            else:
                doc  = build_context_doc(d, result)
                path = save_yaml(doc, args.base_dir)
                print(f"  Saved {doc['article_count']} articles → {path}")

            if i < len(dates) - 1:
                time.sleep(inter_request_delay)

    except KeyboardInterrupt:
        print("\n\nInterrupted. Progress is saved — re-run to continue from where you left off.")
        raise SystemExit(0)

    print("\nDone.")
