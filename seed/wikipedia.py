"""
seed.wikipedia — fetch + parse Wikipedia "Current events" portal pages.

Absorbs wiki_parser.py (parsing), backfill_history.py (page-title candidate
guessing across Wikipedia's ~2001-present naming eras), and backfill_batches.py
(the monthly-page HTML fallback for pre-2004 dates whose daily pages were
never created). All three used to live in separate files with separately
hand-rolled 429 handling; they now share seed.ratelimit.call_with_backoff.

Hierarchy handled by parse_events
----------------------------------
Old-style pages (~2012-2016) use a 4-level structure:

    ;Category                    depth-0  -> top-level section header
    *[[Sub-topic]]:              depth-1  -> sub-category   (ends with ':')
    **[[Sub-sub-topic]]:         depth-2  -> event prefix   (ends with ':')
    ***Actual event text         depth-3  -> individual event

    *Standalone event text       depth-1  -> event filed directly under depth-0 category

New-style pages use a 2-level structure:

    *Category:                   depth-1  -> top-level section header
    **Event text                 depth-2  -> individual event

Naming eras (page-title guessing)
----------------------------------
Era A  ~2004-present
    Daily subpages under the Portal namespace: "Portal:Current events/YYYY Month D".
Era B  ~2001-2003
    Predates the Portal namespace. Daily pages are sparse; monthly pages
    ("Wikipedia:Current events/Month YYYY" or a Portal-namespace equivalent)
    are the norm. When every daily candidate fails for a pre-2004 date,
    fetch_day() automatically falls back to parsing the rendered HTML of the
    monthly page for that one day's <li> entries.
"""

from __future__ import annotations

import calendar
import logging
import re
import time
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

import mwparserfromhell
import requests

from seed.ratelimit import RateLimitError, WIKIPEDIA_POLICY, call_with_backoff
from seed import source

log = logging.getLogger(__name__)

# One session shared for the lifetime of the process (avoids re-handshaking).
_session = requests.Session()

# Normal pause between requests (~40 req/min — well inside Wikipedia's
# documented 200 req/min limit for bots).
REQUEST_DELAY_SECS = 1.5


# ---------------------------------------------------------------------------
# Fetch — wikitext (content API)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WikiFetch:
    content: str
    revision_id: int | None
    source_meta: dict | None = None


def _fetch_wikitext_once(page_title: str, user_agent: str, revision_id=None) -> WikiFetch | None:
    """
    Return (wikitext, revision_id) for *page_title*, or None if the page
    doesn't exist. Raises RateLimitError on HTTP 429 for the caller to retry.
    """
    _session.headers.update({"User-Agent": user_agent})

    params = {
        "action":        "query",
        "prop":          "revisions",
        "titles":        page_title,
        "rvprop":        "content|ids|timestamp",
        "rvslots":       "main",
        "format":        "json",
        "formatversion": "2",
        "redirects":     "true",
    }
    if revision_id is not None:
        params.pop("titles")
        params["revids"] = str(revision_id)

    try:
        r = _session.get("https://en.wikipedia.org/w/api.php", params=params, timeout=20)

        if r.status_code == 429:
            raise RateLimitError(int(r.headers.get("Retry-After", 0)))

        r.raise_for_status()
        data  = r.json()
        pages = data.get("query", {}).get("pages", [])

        if not pages:
            log.warning("API returned no pages for: %s", page_title)
            return None

        page = pages[0]
        if "missing" in page:
            log.info("Page does not exist: %s", page_title)
            return None

        revisions = page.get("revisions", [])
        if not revisions:
            log.warning("Page exists but has no revisions: %s", page_title)
            return None

        revision   = revisions[0]
        obtained_id = revision.get("revid")
        if revision_id is not None and obtained_id != revision_id:
            raise ValueError("Wikipedia returned a different revision from the requested oldid")
        content = revision.get("slots", {}).get("main", {}).get("content", "")
        if not content:
            log.warning("Revision content is empty: %s", page_title)
            return None

        log.debug("Fetched %d chars (rev %s) for: %s", len(content), obtained_id, page_title)
        meta = source.store(content.encode("utf-8"), title=page.get("title", page_title),
                            revision_id=obtained_id, timestamp=revision.get("timestamp"))
        return WikiFetch(content=content, revision_id=obtained_id, source_meta=meta)

    except RateLimitError:
        raise
    except requests.RequestException as e:
        log.error("Network error fetching %s: %s", page_title, e)
        return None
    except ValueError:
        raise  # source identity/hash conflicts must never trigger another source
    except Exception as e:
        log.error("Unexpected error fetching %s: %s", page_title, e)
        return None


def fetch_wikitext(page_title: str, user_agent: str) -> WikiFetch | None:
    """fetch_wikitext with backoff applied — the single call site every caller uses."""
    return call_with_backoff(
        lambda: _fetch_wikitext_once(page_title, user_agent),
        policy=WIKIPEDIA_POLICY,
        label=page_title,
    )


def acquire_revision(page_title: str, revision_id: int, user_agent: str) -> WikiFetch:
    """Explicit acquisition of an existing oldid, never current page state."""
    fetched = call_with_backoff(
        lambda: _fetch_wikitext_once(page_title, user_agent, revision_id),
        policy=WIKIPEDIA_POLICY, label=f"{page_title} oldid={revision_id}")
    if fetched is None:
        raise RuntimeError(f"Could not acquire pinned revision {revision_id}")
    return fetched


def acquire_revision_batch(revision_ids, user_agent):
    """Acquire at most 50 explicit oldids in one MediaWiki request."""
    wanted = set(revision_ids)
    if not wanted or len(wanted) > 50:
        raise ValueError("Revision batches must contain 1-50 explicit oldids")

    def fetch():
        response = _session.get("https://en.wikipedia.org/w/api.php",
            params={"action": "query", "prop": "revisions", "revids": "|".join(map(str, sorted(wanted))),
                    "rvprop": "content|ids|timestamp", "rvslots": "main", "format": "json", "formatversion": "2"},
            headers={"User-Agent": user_agent}, timeout=60)
        if response.status_code == 429:
            raise RateLimitError(int(response.headers.get("Retry-After", 0)))
        response.raise_for_status()
        result = {}
        for page in response.json().get("query", {}).get("pages", []):
            for revision in page.get("revisions", []):
                rev = revision["revid"]
                if rev not in wanted:
                    raise ValueError("MediaWiki returned an unrequested revision")
                content = revision.get("slots", {}).get("main", {}).get("content")
                if content is None:
                    continue
                result[rev] = source.store(content.encode("utf-8"), title=page["title"],
                    revision_id=rev, timestamp=revision.get("timestamp"))
        if set(result) != wanted:
            raise ValueError(f"Missing or suppressed pinned oldids: {sorted(wanted - set(result))}")
        return result

    result = call_with_backoff(fetch, policy=WIKIPEDIA_POLICY, label=f"{len(wanted)} pinned oldids")
    if result is None:
        raise RuntimeError("Pinned revision batch exhausted acquisition retries")
    return result


# ---------------------------------------------------------------------------
# Template extraction + per-line cleaning
# ---------------------------------------------------------------------------

def _extract_event_wikitext(raw: str) -> str:
    """
    Older pages wrap everything in {{Current events|...|content=...}}.
    strip_code() would erase the entire template, so pull |content= out first.
    Returns *raw* unchanged when no such template is found (newer pages).
    """
    parsed = mwparserfromhell.parse(raw)
    for tmpl in parsed.filter_templates():
        if re.search(r"current\s+events", tmpl.name.strip(), re.IGNORECASE):
            if tmpl.has("content"):
                val = str(tmpl.get("content").value)
                log.debug("Extracted |content= from {{Current events}} (%d chars)", len(val))
                return val
    log.debug("No wrapping template — using raw wikitext directly")
    return raw


def _clean(raw_text: str) -> str:
    """Strip wiki markup then remove citation junk and extra whitespace."""
    text = mwparserfromhell.parse(raw_text).strip_code()
    text = re.sub(r"\[\d+\]", "", text)                             # [1] footnotes
    text = re.sub(r"\[https?://[^\s\]]+\s([^\]]+)\]", r"\1", text)  # [url Label]
    text = re.sub(r"\[https?://[^\]]+\]", "", text)                 # bare [url]
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def parse_events_legacy(raw_wikitext: str, page_title: str = "", *, trace=None) -> dict:
    """
    Parse raw wikitext into {category: [event, ...]} respecting the full
    4-level hierarchy. See module docstring for rules.
    """
    event_wikitext = _extract_event_wikitext(raw_wikitext)

    cat0    = "Uncategorized"  # set by ';'
    cat1    = None             # set by '*text:'
    prefix2 = None             # set by '**text:', prepended to '***' events

    result: dict[str, list] = {}

    def ensure(key: str) -> None:
        if key not in result:
            result[key] = []

    def add_event(key: str, text: str) -> None:
        ensure(key)
        result[key].append(text)
        if trace is not None:
            trace.append({"line": line_number, "raw": raw_line, "category": key, "text": text})

    for line_number, raw_line in enumerate(event_wikitext.split("\n"), 1):
        stripped = raw_line.strip()
        if not stripped:
            continue

        if stripped.startswith("***"):
            sigil, rest = "***", stripped[3:].strip()
        elif stripped.startswith("**"):
            sigil, rest = "**",  stripped[2:].strip()
        elif stripped.startswith("*"):
            sigil, rest = "*",   stripped[1:].strip()
        elif stripped.startswith(";"):
            sigil, rest = ";",   stripped[1:].strip()
        else:
            continue  # prose, template tags, HTML comments — skip

        text = _clean(rest)
        if not text:
            continue

        if sigil == ";":
            cat0    = text.rstrip(":").strip()
            cat1    = None
            prefix2 = None
            ensure(cat0)

        elif sigil == "*":
            if text.endswith(":"):
                cat1    = text.rstrip(":").strip()
                prefix2 = None
                ensure(cat1)
            else:
                add_event(cat0, text)

        elif sigil == "**":
            if text.endswith(":"):
                prefix2 = text.rstrip(":").strip()
            else:
                write_to = cat1 if cat1 is not None else cat0
                add_event(write_to, text)
                prefix2 = None

        elif sigil == "***":
            write_to = cat1 if cat1 is not None else cat0
            entry    = f"{prefix2}: {text}" if prefix2 else text
            add_event(write_to, entry)

    final = {k: v for k, v in result.items() if v}

    if not final:
        log.warning("0 events parsed from %s — wikitext sample: %r", page_title, event_wikitext[:300])
    else:
        total = sum(len(v) for v in final.values())
        log.debug("Parsed %d categories, %d events from %s", len(final), total, page_title)

    return final


def parse_events(raw_wikitext: str, page_title: str = "", *, day="1970-01-01") -> dict:
    """Compatibility projection of the hierarchy parser; use extract for archives."""
    from seed.extract import extract, fingerprint, legacy_view
    identity = {"page": page_title, "revision_id": None, "revision_timestamp": None,
                "source_mode": "wikitext", "source_sha256": fingerprint(raw_wikitext)}
    return legacy_view(extract(raw_wikitext, date=day, source=identity))


# ---------------------------------------------------------------------------
# Page-title candidates (Era A / Era B naming)
# ---------------------------------------------------------------------------

def candidate_titles(year: int, month_name: str, day: int) -> list[str]:
    """
    Ordered list of MediaWiki page titles to try for a date, most-likely first.

    1. Portal namespace, no zero-padding on day (dominant format from ~2004 on).
    2. Portal namespace, zero-padded day (occasionally used in some years).
    3. Wikipedia (article) namespace, no zero-padding — pre-Portal, ~2001-2003.
    4. Wikipedia namespace, zero-padded day — uncommon but observed.
    """
    candidates = [
        f"Portal:Current events/{year} {month_name} {day}",
        f"Portal:Current events/{year} {month_name} {day:02d}",
        f"Wikipedia:Current events/{year} {month_name} {day}",
        f"Wikipedia:Current events/{year} {month_name} {day:02d}",
    ]
    seen: set[str] = set()
    unique: list[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


def monthly_candidate_titles(year: int, month_name: str) -> list[str]:
    """Ordered list of monthly-archive page titles to try (Era B fallback)."""
    candidates = [
        f"Portal:Current events/{month_name} {year}",
        f"Portal:Current events/{year} {month_name}",
        f"Wikipedia:Current events/{month_name} {year}",
        f"Wikipedia:Current events/{year} {month_name}",
    ]
    seen: set[str] = set()
    unique: list[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


# ---------------------------------------------------------------------------
# Monthly-page HTML fallback (Era B: pre-2004 dates with no daily page)
# ---------------------------------------------------------------------------

class MonthlyCurrentEventsParser(HTMLParser):
    """Extracts one day's <li> event bullets from a rendered monthly portal page."""

    def __init__(self, year: int, month: int):
        super().__init__(convert_charrefs=True)
        self.year = year
        self.month = month
        self.events_by_day: dict[int, list[str]] = {}
        self.region_day: int | None = None
        self.region_div_depth = 0
        self.content_div_depth = 0
        self.in_li = False
        self.li_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: value or "" for key, value in attrs}

        if tag == "div":
            classes = set(attr.get("class", "").split())
            if self.region_day is None and "current-events-main" in classes:
                day = self._day_from_label(attr.get("aria-label", ""))
                if day is not None:
                    self.region_day = day
                    self.region_div_depth = 1
                    self.content_div_depth = 0
                return

            if self.region_day is not None:
                self.region_div_depth += 1
                if {"current-events-content", "description"}.issubset(classes):
                    self.content_div_depth = 1
                elif self.content_div_depth:
                    self.content_div_depth += 1
                return

        if self.region_day is not None and self.content_div_depth and tag == "li":
            self.in_li = True
            self.li_parts = []

        if self.in_li and tag == "br":
            self.li_parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if self.in_li and tag == "li":
            text = self._clean_text("".join(self.li_parts))
            if text and self.region_day is not None:
                self.events_by_day.setdefault(self.region_day, []).append(text)
            self.in_li = False
            self.li_parts = []
            return

        if self.region_day is not None and tag == "div":
            if self.content_div_depth:
                self.content_div_depth -= 1
            self.region_div_depth -= 1
            if self.region_div_depth <= 0:
                self.region_day = None
                self.region_div_depth = 0
                self.content_div_depth = 0

    def handle_data(self, data: str) -> None:
        if self.in_li:
            self.li_parts.append(data)

    @staticmethod
    def _clean_text(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _day_from_label(label: str) -> int | None:
        match = re.search(r"(\d{1,2})$", label.strip())
        return int(match.group(1)) if match else None


def _fetch_rendered_html_once(page_title: str, user_agent: str) -> str | None:
    params = {
        "action": "parse",
        "page": page_title,
        "prop": "text",
        "format": "json",
        "formatversion": "2",
        "redirects": "true",
    }
    try:
        r = _session.get(
            "https://en.wikipedia.org/w/api.php",
            params=params,
            headers={"User-Agent": user_agent},
            timeout=20,
        )
        if r.status_code == 429:
            raise RateLimitError(int(r.headers.get("Retry-After", 0)))
        r.raise_for_status()
        data = r.json()
        if data.get("error"):
            return None
        parsed = data.get("parse", {})
        html = parsed.get("text")
        if html:
            _rendered_sources[page_title] = source.store(html.encode("utf-8"),
                title=parsed.get("title", page_title), revision_id=parsed.get("revid"),
                timestamp=None, mode="rendered_html")
        return html
    except RateLimitError:
        raise
    except requests.RequestException:
        return None


def fetch_rendered_html(page_title: str, user_agent: str) -> str | None:
    return call_with_backoff(
        lambda: _fetch_rendered_html_once(page_title, user_agent),
        policy=WIKIPEDIA_POLICY,
        label=f"{page_title} (rendered)",
    )


# Cache type: (year, month) -> (matched_title | None, {day: [events]})
MonthlyCache = dict[tuple[int, int], tuple[str | None, dict[int, list[str]]]]
_rendered_sources: dict[str, dict] = {}


def _load_monthly_events(
    year: int, month: int, month_name: str, user_agent: str
) -> tuple[str | None, dict[int, list[str]]]:
    for title in monthly_candidate_titles(year, month_name):
        html = fetch_rendered_html(title, user_agent)
        if not html:
            continue
        parser = MonthlyCurrentEventsParser(year, month)
        parser.feed(html)
        if parser.events_by_day:
            return title, parser.events_by_day
    return None, {}


def monthly_fallback_for_day(
    day: date, user_agent: str, cache: MonthlyCache
) -> tuple[str | None, dict[str, list[str]] | None]:
    """
    Return (source_title, {"Uncategorized": [...]}) for a single day by parsing
    the rendered HTML of its monthly archive page, or (title_or_None, None) if
    nothing was found. *cache* should persist across a whole run so each
    month's page is only fetched once no matter how many days from it are needed.
    """
    key = (day.year, day.month)
    month_name = calendar.month_name[day.month]
    if key not in cache:
        cache[key] = _load_monthly_events(day.year, day.month, month_name, user_agent)

    title, events_by_day = cache[key]
    events = events_by_day.get(day.day, [])
    if not title or not events:
        return title, None

    source_title = f"{title}#{day.year}_{month_name}_{day.day}"
    return source_title, {"Uncategorized": events}


# ---------------------------------------------------------------------------
# High-level: fetch one day, daily page first then monthly-HTML fallback
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WikiDayResult:
    categories: dict[str, list[str]]
    source_title: str
    revision_id: int | None   # None when sourced from the monthly-HTML fallback
    source_meta: dict | None = None
    archive: dict | None = None


def fetch_day(
    year: int, month: int, day: int, user_agent: str, *, monthly_cache: MonthlyCache | None = None
) -> WikiDayResult | None:
    """
    Fetch and parse one day's Current Events, trying daily-page candidates in
    priority order, falling back to the monthly-page HTML parser (Era B) if
    every daily candidate is missing or parses to zero events.
    """
    month_name = calendar.month_name[month]
    candidates = candidate_titles(year, month_name, day)

    for i, title in enumerate(candidates):
        fetched = fetch_wikitext(title, user_agent)
        time.sleep(REQUEST_DELAY_SECS)
        if not fetched:
            continue

        from seed.extract import extract, legacy_view
        meta = fetched.source_meta
        if meta is None:
            raise ValueError("Acquired Wikipedia source has no cache identity")
        identity = {k: meta[k] for k in ("page", "revision_id", "revision_timestamp", "source_mode", "source_sha256")}
        archive = extract(fetched.content, date=date(year, month, day).isoformat(), source=identity)
        events = legacy_view(archive)
        if any(c["entries"] for c in archive["categories"]) or archive["warnings"]:
            if i > 0:
                log.info("Fallback title succeeded for %d %s %d: %s", year, month_name, day, title)
            return WikiDayResult(categories=events, source_title=title, revision_id=fetched.revision_id,
                                 source_meta=fetched.source_meta, archive=archive)

        log.info("Parsed 0 events from %s — trying next candidate / monthly fallback.", title)

    cache = monthly_cache if monthly_cache is not None else {}
    target = date(year, month, day)
    monthly_title, monthly_events = monthly_fallback_for_day(target, user_agent, cache)
    if monthly_events:
        meta = _rendered_sources.get((monthly_title or "").split("#")[0])
        if meta is None:
            raise ValueError("Rendered source has no exact acquisition identity")
        _, payload = source.load(source.CACHE / "rendered_html" / Path(meta["payload"]).stem,
                                 mode="rendered_html")
        from seed.extract import extract, legacy_view
        identity = {k: meta[k] for k in ("page", "revision_id", "revision_timestamp", "source_mode", "source_sha256")}
        archive = extract(payload.decode("utf-8"), date=target.isoformat(), source=identity)
        return WikiDayResult(categories=monthly_events, source_title=monthly_title or "", revision_id=None,
                             source_meta=meta, archive=archive)

    if year < 2004:
        log.warning(
            "All daily candidates and monthly fallback failed for %d %s %d. Tried monthly: %s",
            year, month_name, day, monthly_candidate_titles(year, month_name),
        )
    else:
        log.warning("All daily candidates failed for %d %s %d.", year, month_name, day)

    return None
