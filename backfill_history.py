"""
backfill_history.py — fetches Wikipedia Current Events pages and saves them as YAML.

Resume behaviour
----------------
If a YAML file already exists for a given date it is skipped, so you can safely
re-run the script after an interruption and it will pick up where it left off.

Rate-limit handling
-------------------
Wikipedia may return HTTP 429 Too Many Requests if requests arrive too fast or
if a sustained session accumulates too many hits.  When that happens the script:

  1. Respects the Retry-After header if the server sends one.
  2. Otherwise uses exponential backoff starting at BACKOFF_BASE_SECS, doubling
     each consecutive 429 up to BACKOFF_MAX_SECS.
  3. Retries the same date up to MAX_RETRIES times before giving up and moving on.
  4. Resets the backoff counter after any successful fetch.

The normal inter-request delay (REQUEST_DELAY_SECS) keeps the steady-state rate
well inside Wikipedia's documented limit of 200 req/min for bots.
"""

import os
import time
import calendar
import logging
import yaml
from datetime import datetime

from wiki_parser import fetch_wikitext, parse_events, RateLimitError

# ---------------------------------------------------------------------------
# Logging — file only, no console output
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("backfill.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

USER_AGENT = "LLM-History-Pipeline/1.0 (ianrastall@github)"
START_YEAR = 2012

# Normal pause between requests (~40 req/min — well inside Wikipedia's limit)
REQUEST_DELAY_SECS = 1.5

# Backoff settings for HTTP 429 responses
BACKOFF_BASE_SECS = 60    # first backoff: 1 minute
BACKOFF_MAX_SECS  = 600   # cap at 10 minutes
MAX_RETRIES       = 5     # give up on a date after this many 429s in a row


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def output_path(year: int, month: int, date_obj) -> str:
    return os.path.join(str(year), f"{month:02d}", f"{date_obj}.yaml")


def already_saved(year: int, month: int, date_obj) -> bool:
    return os.path.exists(output_path(year, month, date_obj))


def save(date_obj, page_title: str, events_data: dict) -> None:
    year, month = date_obj.year, date_obj.month
    dataset = {
        "Date":                 date_obj.strftime("%Y-%m-%d"),
        "Source_URI":           page_title,
        "Intelligence_Payload": events_data,
    }
    dir_path = os.path.join(str(year), f"{month:02d}")
    os.makedirs(dir_path, exist_ok=True)
    path = output_path(year, month, date_obj)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(dataset, f, default_flow_style=False,
                  allow_unicode=True, sort_keys=False)
    log.info("Saved %s", path)


def fetch_with_backoff(page_title: str) -> str | None:
    """
    Fetch wikitext, retrying with exponential backoff on HTTP 429.
    Returns the wikitext string, or None if the page is missing / all retries failed.
    """
    backoff = BACKOFF_BASE_SECS

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fetch_wikitext(page_title, USER_AGENT)

        except RateLimitError as e:
            # Prefer the server's own Retry-After value if it gave one
            wait = e.retry_after if e.retry_after > 0 else backoff
            wait = min(wait, BACKOFF_MAX_SECS)

            if attempt == MAX_RETRIES:
                log.error(
                    "429 on %s — %d retries exhausted, skipping date.",
                    page_title, MAX_RETRIES,
                )
                return None

            log.warning(
                "429 on %s (attempt %d/%d) — backing off for %ds.",
                page_title, attempt, MAX_RETRIES, wait,
            )
            print(f"  Rate-limited. Waiting {wait}s before retry {attempt}/{MAX_RETRIES}...")
            time.sleep(wait)
            backoff = min(backoff * 2, BACKOFF_MAX_SECS)

    return None  # unreachable, but satisfies type checkers


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_backfill() -> None:
    now      = datetime.now()
    end_year = now.year
    skipped  = 0
    saved    = 0
    missing  = 0

    for year in range(START_YEAR, end_year + 1):
        for month in range(1, 13):

            # Skip future months
            if year == now.year and month > now.month:
                continue

            month_name = calendar.month_name[month]
            _, num_days = calendar.monthrange(year, month)

            for day in range(1, num_days + 1):

                target_date = datetime(year, month, day).date()

                # Resume: skip dates we already have
                if already_saved(year, month, target_date):
                    log.debug("Already saved, skipping: %s", target_date)
                    skipped += 1
                    continue

                page_title = f"Portal:Current events/{year} {month_name} {day}"
                log.info("Fetching: %s", page_title)

                wikitext = fetch_with_backoff(page_title)

                # Always sleep after a fetch attempt to stay polite
                time.sleep(REQUEST_DELAY_SECS)

                if not wikitext:
                    missing += 1
                    continue

                events_data = parse_events(wikitext, page_title)
                if not events_data:
                    missing += 1
                    continue

                save(target_date, page_title, events_data)
                saved += 1

    log.info(
        "Backfill complete. saved=%d  skipped(already existed)=%d  missing/failed=%d",
        saved, skipped, missing,
    )
    print(f"Backfill complete. saved={saved}  skipped={skipped}  missing/failed={missing}")


if __name__ == "__main__":
    print("Backfill started — progress logged to backfill.log")
    run_backfill()
