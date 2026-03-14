"""
wiki_parser.py — shared fetch + parse logic for backfill_history.py and update_data.py.

Hierarchy handled
-----------------
Old-style pages (≈ 2012–2016) use a 4-level structure:

    ;Category                    depth-0  → top-level section header
    *[[Sub-topic]]:              depth-1  → sub-category   (ends with ':')
    **[[Sub-sub-topic]]:         depth-2  → event prefix   (ends with ':')
    ***Actual event text         depth-3  → individual event

    *Standalone event text       depth-1  → event filed directly under depth-0 category

New-style pages use a 2-level structure:

    *Category:                   depth-1  → top-level section header
    **Event text                 depth-2  → individual event

Parsing rules
-------------
- strip_code() is NOT called on the whole block — it erases the '*' and ';' sigils.
  Instead we detect sigils on raw lines, then call strip_code() on the text portion only.
- depth-0 (;)     → sets `cat0`; resets cat1 and prefix2.
- depth-1 (*x:)   → sets `cat1`; resets prefix2. Events filed here.
- depth-1 (*x)    → standalone event filed under cat0 (not cat1).
- depth-2 (**x:)  → sets `prefix2`. Sub-events filed under cat1 with this prefix.
- depth-2 (**x)   → event filed under cat1 (no prefix).
- depth-3 (***x)  → event filed under cat1, with prefix2 prepended if set.
  Each *** line becomes its own separate list entry (never concatenated).

Rate-limiting
-------------
fetch_wikitext raises RateLimitError on HTTP 429.  The caller (backfill_history.py)
is responsible for backing off and retrying — keeping that logic out of this module
makes it easier to test and reason about.

Server politeness
-----------------
- A single requests.Session() is reused across all calls (avoids re-handshaking).
- The session honours the Retry-After header value when available.
- Caller controls sleep intervals; this module does not sleep.
- User-Agent is passed in by the caller.
- Timeouts are always set.
"""

import re
import logging
import requests
import mwparserfromhell

log = logging.getLogger(__name__)

# One session shared for the lifetime of the process.
_session = requests.Session()


# ---------------------------------------------------------------------------
# Custom exception for rate limiting
# ---------------------------------------------------------------------------

class RateLimitError(Exception):
    """Raised when the server responds with HTTP 429 Too Many Requests."""
    def __init__(self, retry_after: int = 0):
        self.retry_after = retry_after  # seconds suggested by server, 0 if not given
        super().__init__(f"HTTP 429 — server suggested retry_after={retry_after}s")


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def fetch_wikitext(page_title: str, user_agent: str) -> str | None:
    """
    Return raw wikitext for *page_title*, or None if the page doesn't exist.
    Raises RateLimitError on HTTP 429 so the caller can back off and retry.
    """
    _session.headers.update({"User-Agent": user_agent})

    params = {
        "action":        "query",
        "prop":          "revisions",
        "titles":        page_title,
        "rvprop":        "content",
        "rvslots":       "main",
        "format":        "json",
        "formatversion": "2",
        "redirects":     "true",
    }

    try:
        r = _session.get(
            "https://en.wikipedia.org/w/api.php",
            params=params,
            timeout=20,
        )

        # Surface rate-limit errors to the caller so it can back off properly
        if r.status_code == 429:
            retry_after = int(r.headers.get("Retry-After", 0))
            raise RateLimitError(retry_after)

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

        content = (
            revisions[0]
            .get("slots", {})
            .get("main", {})
            .get("content", "")
        )
        if not content:
            log.warning("Revision content is empty: %s", page_title)
            return None

        log.debug("Fetched %d chars for: %s", len(content), page_title)
        return content

    except RateLimitError:
        raise   # let caller handle it
    except requests.RequestException as e:
        log.error("Network error fetching %s: %s", page_title, e)
        return None
    except Exception as e:
        log.error("Unexpected error fetching %s: %s", page_title, e)
        return None


# ---------------------------------------------------------------------------
# Template extraction
# ---------------------------------------------------------------------------

def _extract_event_wikitext(raw: str) -> str:
    """
    Older pages wrap everything in {{Current events|...|content=...}}.
    strip_code() would erase the entire template, so we pull the |content=
    value out first and return it as raw wikitext.
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


# ---------------------------------------------------------------------------
# Per-line text cleaning
# ---------------------------------------------------------------------------

def _clean(raw_text: str) -> str:
    """Strip wiki markup then remove citation junk and extra whitespace."""
    text = mwparserfromhell.parse(raw_text).strip_code()
    text = re.sub(r"\[\d+\]", "", text)                             # [1] footnotes
    text = re.sub(r"\[https?://[^\s\]]+\s([^\]]+)\]", r"\1", text) # [url Label]
    text = re.sub(r"\[https?://[^\]]+\]", "", text)                 # bare [url]
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def parse_events(raw_wikitext: str, page_title: str = "") -> dict:
    """
    Parse raw wikitext into {category: [event, ...]} respecting the full
    4-level hierarchy.  See module docstring for rules.
    """
    event_wikitext = _extract_event_wikitext(raw_wikitext)

    # Category state
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

    for raw_line in event_wikitext.split("\n"):
        stripped = raw_line.strip()
        if not stripped:
            continue

        # ------------------------------------------------------------------
        # Detect sigil depth on the raw line
        # ------------------------------------------------------------------
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

        # ------------------------------------------------------------------
        # Route by sigil
        # ------------------------------------------------------------------
        if sigil == ";":
            # Depth-0: top-level section header
            cat0    = text.rstrip(":").strip()
            cat1    = None
            prefix2 = None
            ensure(cat0)

        elif sigil == "*":
            if text.endswith(":"):
                # Depth-1 sub-category header
                cat1    = text.rstrip(":").strip()
                prefix2 = None
                ensure(cat1)
            else:
                # Depth-1 standalone event — always filed under cat0
                add_event(cat0, text)

        elif sigil == "**":
            if text.endswith(":"):
                # Depth-2 sub-sub header — stored as a prefix for *** events
                prefix2 = text.rstrip(":").strip()
            else:
                # Depth-2 event — filed under cat1 (no prefix)
                write_to = cat1 if cat1 is not None else cat0
                add_event(write_to, text)
                prefix2 = None  # a ** event resets any pending prefix

        elif sigil == "***":
            # Depth-3 event — each one is a separate list entry
            write_to = cat1 if cat1 is not None else cat0
            entry    = f"{prefix2}: {text}" if prefix2 else text
            add_event(write_to, entry)

    # Drop categories that ended up with no events
    final = {k: v for k, v in result.items() if v}

    if not final:
        log.warning(
            "0 events parsed from %s — wikitext sample: %r",
            page_title,
            event_wikitext[:300],
        )
    else:
        total = sum(len(v) for v in final.values())
        log.debug(
            "Parsed %d categories, %d events from %s",
            len(final), total, page_title,
        )

    return final
