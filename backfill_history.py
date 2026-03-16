"""
backfill_history.py — fetches Wikipedia Current Events pages and saves them as YAML.

Usage
-----
  python backfill_history.py                  # forward pass (2012 → today)
  python backfill_history.py --mode forward   # same as above, explicit
  python backfill_history.py --mode backward  # backward pass (2011 → 2001)
  python backfill_history.py --mode both      # backward first, then forward

Both modes honour resume behaviour: existing YAML files are skipped.

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

Naming-convention notes (backward pass)
----------------------------------------
Wikipedia's Current Events archive evolved through at least three structural eras:

  Era A  ~2004 – present
      Daily subpages under the Portal namespace.
      Title pattern: "Portal:Current events/YYYY Month D"
      Example:       "Portal:Current events/2007 March 4"
      This is the same scheme the forward pass uses and should parse cleanly.

  Era B  ~2001 – 2003
      Content predates the Portal namespace.  Pages lived under the article
      namespace as "Wikipedia:Current events/YYYY Month D" or, more commonly,
      as *monthly* pages ("Wikipedia:Current events/November 2001").
      Daily pages are sparse; monthly pages are the norm.
      The wikitext structure differs markedly from Era A — wiki_parser may
      return an empty payload for these, which is logged but not treated as
      an error.  The file is simply not written, so a later re-run (once
      wiki_parser is extended) can pick them up.

  Redirect handling
      Some early URLs are redirects to a canonical location.  fetch_wikitext
      (in wiki_parser) should follow HTTP 3xx redirects transparently.
      The candidate_titles() function below tries the most-likely pattern
      first, then falls back to known alternatives, so the first hit wins.
"""

import argparse
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

# The forward pass starts here; the backward pass starts at START_YEAR - 1.
START_YEAR = 2012

# Earliest year we attempt to collect.  Wikipedia's Current Events content
# before this point is extremely sparse and structurally inconsistent.
LEGACY_START_YEAR = 2001

# Normal pause between requests (~40 req/min — well inside Wikipedia's limit)
REQUEST_DELAY_SECS = 1.5

# Backoff settings for HTTP 429 responses
BACKOFF_BASE_SECS = 60    # first backoff: 1 minute
BACKOFF_MAX_SECS  = 600   # cap at 10 minutes
MAX_RETRIES       = 5     # give up on a date after this many 429s in a row


# ---------------------------------------------------------------------------
# Page-title candidates
# ---------------------------------------------------------------------------

def candidate_titles(year: int, month_name: str, day: int) -> list[str]:
    """
    Return an ordered list of MediaWiki page titles to try for a given date.

    The list is ordered from most-likely to least-likely so that fetch logic
    can stop at the first successful response.

    Rationale for each candidate
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    1. Portal namespace, space-separated date (dominant format from ~2004 on).
       Wikipedia uses NO zero-padding on the day component in this scheme.
    2. Portal namespace with zero-padded day — occasionally used in some years.
    3. Wikipedia (article) namespace, space-separated — pre-Portal convention
       used approximately 2001–2003.
    4. Wikipedia namespace with zero-padded day — uncommon but observed.

    Monthly-page fallback (Era B)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    For dates before 2004 the most likely surviving page is a *monthly* page
    rather than a daily one.  We do NOT include those here because a monthly
    page, if parsed successfully, would produce data for the entire month at
    once and should be handled by a separate monthly-backfill routine.  The
    caller is responsible for deciding what to do when all daily candidates
    fail (see fetch_date_with_fallback).
    """
    candidates = [
        # Candidate 1 — standard Portal daily page (no zero-padding)
        f"Portal:Current events/{year} {month_name} {day}",
        # Candidate 2 — Portal daily page with zero-padded day
        f"Portal:Current events/{year} {month_name} {day:02d}",
        # Candidate 3 — pre-Portal Wikipedia namespace (no zero-padding)
        f"Wikipedia:Current events/{year} {month_name} {day}",
        # Candidate 4 — pre-Portal Wikipedia namespace (zero-padded day)
        f"Wikipedia:Current events/{year} {month_name} {day:02d}",
    ]
    # De-duplicate while preserving order (candidates 1 and 2 are identical
    # when day >= 10, so collapse them to avoid a redundant API call).
    seen: set[str] = set()
    unique: list[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


def monthly_candidate_title(year: int, month_name: str) -> str:
    """
    Return the most common monthly-archive page title for the given month.

    This is a *diagnostic* helper — it is logged when all daily candidates
    fail for a pre-2004 date so that the operator knows which monthly page
    to inspect manually or handle with a future monthly-backfill routine.
    """
    return f"Wikipedia:Current events/{month_name} {year}"


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


def fetch_date_with_fallback(
    year: int, month_name: str, day: int
) -> tuple[str | None, str | None]:
    """
    Try each candidate title for the given date in priority order.

    Returns (wikitext, successful_title) on the first hit, or (None, None)
    if every candidate either returned no content or raised a non-rate-limit
    error.  Rate-limit errors are retried with backoff inside fetch_with_backoff
    before this function gives up on a candidate.

    For pre-2004 dates where all daily candidates fail, the monthly page title
    is logged at WARNING level so the operator can investigate manually.
    """
    candidates = candidate_titles(year, month_name, day)

    for title in candidates:
        log.info("Trying title: %s", title)
        wikitext = fetch_with_backoff(title)
        time.sleep(REQUEST_DELAY_SECS)

        if wikitext:
            if title != candidates[0]:
                # A fallback pattern succeeded — worth noting in the log
                log.info(
                    "Fallback title succeeded for %d %s %d: %s",
                    year, month_name, day, title,
                )
            return wikitext, title

    # All daily candidates failed.  For pre-2004 dates, hint at the monthly page.
    if year < 2004:
        monthly = monthly_candidate_title(year, month_name)
        log.warning(
            "All daily candidates failed for %d %s %d. "
            "A monthly page may exist: %s",
            year, month_name, day, monthly,
        )

    return None, None


# ---------------------------------------------------------------------------
# Core backfill logic (direction-agnostic)
# ---------------------------------------------------------------------------

def process_date_range(
    year_range,
    month_range_fn,
    *,
    now: datetime,
    label: str,
) -> tuple[int, int, int]:
    """
    Iterate over a range of (year, month, day) triples and fetch/save each one.

    Parameters
    ----------
    year_range      : iterable of years (may be ascending or descending)
    month_range_fn  : callable(year) → iterable of months
    now             : current datetime (used to skip future months)
    label           : display name for progress messages ("forward" / "backward")

    Returns (saved, skipped, missing) counts.
    """
    skipped = saved = missing = 0

    for year in year_range:
        for month in month_range_fn(year):

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

                wikitext, used_title = fetch_date_with_fallback(
                    year, month_name, day
                )

                if not wikitext:
                    log.info(
                        "[%s] No content for %s — all candidates exhausted.",
                        label, target_date,
                    )
                    missing += 1
                    continue

                events_data = parse_events(wikitext, used_title)
                if not events_data:
                    log.info(
                        "[%s] parse_events returned empty for %s (title: %s). "
                        "Page may use an unsupported legacy format.",
                        label, target_date, used_title,
                    )
                    missing += 1
                    continue

                save(target_date, used_title, events_data)
                saved += 1

    return saved, skipped, missing


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def run_forward() -> None:
    """
    Forward pass: START_YEAR → current year (the original behaviour).
    """
    now      = datetime.now()
    end_year = now.year

    print(f"[forward] Collecting {START_YEAR} → {end_year} …")
    log.info("[forward] Starting forward pass %d → %d", START_YEAR, end_year)

    saved, skipped, missing = process_date_range(
        year_range      = range(START_YEAR, end_year + 1),
        month_range_fn  = lambda _year: range(1, 13),
        now             = now,
        label           = "forward",
    )

    _report("forward", saved, skipped, missing)


def run_backward() -> None:
    """
    Backward pass: (START_YEAR - 1) → LEGACY_START_YEAR.

    Months within each year are iterated in reverse (December → January) so
    that the most recent un-collected dates are filled first, making partial
    runs maximally useful.
    """
    now        = datetime.now()
    back_start = START_YEAR - 1   # first year not covered by forward pass
    back_end   = LEGACY_START_YEAR

    print(f"[backward] Collecting {back_start} → {back_end} …")
    log.info(
        "[backward] Starting backward pass %d → %d",
        back_start, back_end,
    )

    saved, skipped, missing = process_date_range(
        year_range      = range(back_start, back_end - 1, -1),
        month_range_fn  = lambda _year: range(12, 0, -1),
        now             = now,
        label           = "backward",
    )

    _report("backward", saved, skipped, missing)


def _report(label: str, saved: int, skipped: int, missing: int) -> None:
    msg = (
        f"[{label}] Complete. "
        f"saved={saved}  skipped(already existed)={skipped}  "
        f"missing/failed={missing}"
    )
    log.info(msg)
    print(msg)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch Wikipedia Current Events pages and save them as YAML. "
            "Existing files are never overwritten (resume-safe)."
        )
    )
    parser.add_argument(
        "--mode",
        choices=["forward", "backward", "both"],
        default="forward",
        help=(
            "forward  — %(prog)s collects START_YEAR (%(default)s) → today  "
            "backward — collects (START_YEAR-1) → LEGACY_START_YEAR (oldest)  "
            "both     — backward first, then forward  "
            "(default: %(default)s)"
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    print(f"Backfill started (mode={args.mode}) — progress logged to backfill.log")

    if args.mode == "forward":
        run_forward()
    elif args.mode == "backward":
        run_backward()
    elif args.mode == "both":
        run_backward()
        run_forward()


if __name__ == "__main__":
    main()
