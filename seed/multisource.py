"""Multi-source acquisition, immutable caching, and deterministic feed extraction.

Supports historical and modern dates (starting at 2000-01-01) across:
1. Wikipedia retrospective/annual/country/day-of-year pages (via `seed.source`)
2. Wikidata SPARQL day-precision (`wikibase:timePrecision 11`) event records (CC0)
3. USGS ComCat Earthquake API (`minmagnitude=4.5` GeoJSON feed)
4. GDELT 1.0 historical CAMEO event archive (`https://data.gdeltproject.org/events/<YYYY>.zip`)
5. UN OCHA ReliefWeb v2 API (when `RELIEFWEB_APPNAME` is provided)
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import struct
import zlib
from pathlib import Path
from typing import Any

import requests

from seed import extract, source

REPO_ROOT = Path(__file__).resolve().parents[1]
MULTISOURCE_CACHE = REPO_ROOT / "reference" / "sources"
USER_AGENT = "current-events-context/1.0 (https://github.com/ian/current-events-context)"

CAMEO_ROOT_LABELS = {
    "01": "Make public statement",
    "02": "Appeal",
    "03": "Express intent to cooperate",
    "04": "Consult / diplomatic visit",
    "05": "Engage in diplomatic cooperation",
    "06": "Engage in material cooperation",
    "07": "Provide aid",
    "08": "Yield / release / de-escalate",
    "09": "Investigate",
    "10": "Demand",
    "11": "Disapprove / criticize",
    "12": "Reject",
    "13": "Threaten",
    "14": "Protest",
    "15": "Exhibit military posture",
    "16": "Reduce relations",
    "17": "Coerce / arrest / seize",
    "18": "Assault / hijack / abduct",
    "19": "Fight / armed battle",
    "20": "Use unconventional mass violence",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_cached_json(subpath: str, payload: dict[str, Any]) -> tuple[Path, str]:
    path = MULTISOURCE_CACHE / subpath
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    digest = _sha256_bytes(raw)
    if not path.exists() or path.read_bytes() != raw:
        path.write_bytes(raw)
    return path, digest


def _read_cached_json(subpath: str) -> tuple[Path, str, dict[str, Any]]:
    path = MULTISOURCE_CACHE / subpath
    raw = path.read_bytes()
    return path, _sha256_bytes(raw), json.loads(raw.decode("utf-8"))


# ---------------------------------------------------------------------------
# 1. Wikipedia Retrospective / Topical / Day-of-Year Pages (for 2000-2001+)
# ---------------------------------------------------------------------------

DEFAULT_RETROSPECTIVE_SUFFIXES = [
    "",
    " in the United States",
    " in Canada",
    " in the United Kingdom",
    " in Ireland",
    " in France",
    " in Germany",
    " in Russia",
    " in Israel",
    " in India",
    " in China",
    " in Japan",
    " in South Africa",
    " in Australia",
    " in New Zealand",
    " in aviation",
    " in science",
    " in spaceflight",
]


def acquire_wikipedia_retrospective(
    year: int,
    day_titles: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Acquire and cache retrospective Wikipedia pages for `year`, preserving already-pinned revisions."""
    manifest_path = MULTISOURCE_CACHE / "wikipedia_retrospective" / f"{year}.json"
    existing_by_title: dict[str, dict[str, Any]] = {}
    if manifest_path.exists():
        existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for p in existing_manifest.get("pages", []):
            existing_by_title[p["page"]] = p

    desired_titles = [f"{year}{suffix}" for suffix in DEFAULT_RETROSPECTIVE_SUFFIXES]
    if day_titles:
        for dt_title in day_titles:
            if dt_title not in desired_titles:
                desired_titles.append(dt_title)
    else:
        for default_day in ("January 1", "January 2"):
            if default_day not in desired_titles:
                desired_titles.append(default_day)

    missing_titles = [t for t in desired_titles if t not in existing_by_title]
    for i in range(0, len(missing_titles), 20):
        batch = missing_titles[i : i + 20]
        resp = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "titles": "|".join(batch),
                "prop": "revisions",
                "rvprop": "ids|timestamp|content",
                "rvslots": "main",
                "format": "json",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=30,
        )
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
        for page in pages.values():
            if "revisions" not in page:
                continue
            rev = page["revisions"][0]
            content = rev["slots"]["main"]["*"].encode("utf-8")
            meta = source.store(
                content,
                title=page["title"],
                revision_id=rev["revid"],
                timestamp=rev.get("timestamp"),
            )
            existing_by_title[page["title"]] = meta

    stored = sorted(existing_by_title.values(), key=lambda m: m["page"])
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps({"year": year, "pages": stored}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return stored


def extract_wikipedia_retrospective_day(date_str: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Deterministically extract day items from cached retrospective Wikipedia pages."""
    d = dt.date.fromisoformat(date_str)
    year = d.year
    month_name = d.strftime("%B")
    day_num = d.day
    month_day = f"{month_name} {day_num}"
    day_month = f"{day_num} {month_name}"

    manifest_path = MULTISOURCE_CACHE / "wikipedia_retrospective" / f"{year}.json"
    if not manifest_path.exists():
        return [], []

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_sources: list[dict[str, Any]] = []
    feed_items: list[dict[str, Any]] = []
    core_titles = {
        f"{year}",
        f"{year} in the United States",
        f"{year} in the United Kingdom",
        f"{year} in Australia",
        month_day,
    }

    for meta in manifest.get("pages", []):
        title = meta["page"]
        is_year_page = title == str(year) or title.startswith(f"{year} in ")
        if not is_year_page and title != month_day:
            continue

        rev_id = meta["revision_id"]
        _, raw_bytes = source.revision(rev_id)
        wikitext = raw_bytes.decode("utf-8")
        src_id = f"wiki-retro-{rev_id}"
        page_items: list[dict[str, Any]] = []

        if title == month_day:
            # Day-of-year page (e.g. 'January 1' or 'January 3'): find '* [[2000]]' or '* 2000'
            section = "Events"
            for line in wikitext.splitlines():
                sec_match = re.match(r"^==\s*([^=]+?)\s*==$", line.strip())
                if sec_match:
                    section = sec_match.group(1).strip()
                    continue
                if section not in ("Events", "Deaths"):
                    continue
                if re.match(rf"^\*\s*(?:\[\[{year}\]\]|{year})\s*(?:–|—|-|&ndash;)", line.strip()):
                    body_part = re.sub(rf"^\*\s*(?:\[\[{year}\]\]|{year})\s*(?:–|—|-|&ndash;)\s*", "", line.strip())
                    text, links, cites, _ = extract.fragment(body_part)
                    page_items.append(
                        {
                            "item_id": f"{src_id}-{len(feed_items) + len(page_items) + 1}",
                            "source_id": src_id,
                            "feed_type": f"wikipedia_anniversary_{section.lower()}",
                            "ord": len(feed_items) + len(page_items),
                            "title": text,
                            "category": "Deaths" if section == "Deaths" else "Historical events",
                            "actors_text": ", ".join(l["surface"] for l in links[:5]),
                            "location_text": "",
                            "metric_value": str(year),
                            "url": cites[0]["url"] if cites else f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                            "raw_json": json.dumps({"raw": line, "links": links, "citations": cites}, ensure_ascii=False),
                        }
                    )
        else:
            # Year or 'Year in Country/Topic' page: parse ===January=== section (or whole page if no month header)
            m = re.search(rf"===+\s*{month_name}\s*===+", wikitext)
            if m:
                sub = wikitext[m.end():]
                next_sec = re.search(r"\n==+[^=]", sub)
                if next_sec:
                    sub = sub[: next_sec.start()]
            else:
                sub = wikitext

            active_day = False
            in_births = False
            for line in sub.splitlines():
                stripped = line.strip()
                if stripped.startswith("=="):
                    active_day = False
                    sec_hdr = stripped.strip("=").strip().lower()
                    in_births = sec_hdr == "births"
                    continue
                if in_births or not stripped.startswith("*"):
                    continue
                depth = len(re.match(r"^\*+", stripped).group(0))
                content = stripped[depth:].strip()
                if depth == 1:
                    pat = rf"^(?:\[\[{month_day}\]\]|\[\[{day_month}\]\]|{month_day}\b|{day_month}\b)(?!\s*[–—-]\s*\d)"
                    if re.match(pat, content):
                        active_day = True
                        rem = re.sub(pat, "", content).strip()
                        rem = re.sub(r"^(?:–|—|-|&ndash;|:)\s*", "", rem).strip()
                        if rem:
                            text, links, cites, _ = extract.fragment(rem)
                            page_items.append(
                                {
                                    "item_id": f"{src_id}-{len(feed_items) + len(page_items) + 1}",
                                    "source_id": src_id,
                                    "feed_type": "wikipedia_retrospective",
                                    "ord": len(feed_items) + len(page_items),
                                    "title": text,
                                    "category": title,
                                    "actors_text": ", ".join(l["surface"] for l in links[:5]),
                                    "location_text": title.replace(f"{year} in ", "") if " in " in title else "Global",
                                    "metric_value": date_str,
                                    "url": cites[0]["url"] if cites else f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                                    "raw_json": json.dumps({"raw": line, "links": links, "citations": cites}, ensure_ascii=False),
                                }
                            )
                    else:
                        active_day = False
                elif depth >= 2 and active_day:
                    text, links, cites, _ = extract.fragment(content)
                    page_items.append(
                        {
                            "item_id": f"{src_id}-{len(feed_items) + len(page_items) + 1}",
                            "source_id": src_id,
                            "feed_type": "wikipedia_retrospective",
                            "ord": len(feed_items) + len(page_items),
                            "title": text,
                            "category": title,
                            "actors_text": ", ".join(l["surface"] for l in links[:5]),
                            "location_text": title.replace(f"{year} in ", "") if " in " in title else "Global",
                            "metric_value": date_str,
                            "url": cites[0]["url"] if cites else f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                            "raw_json": json.dumps({"raw": line, "links": links, "citations": cites}, ensure_ascii=False),
                        }
                    )

        if title in core_titles or page_items:
            raw_sources.append(
                {
                    "source_id": src_id,
                    "source_type": "wikipedia_retrospective_wikitext",
                    "title_or_query": title,
                    "uri": f"https://en.wikipedia.org/w/index.php?oldid={rev_id}",
                    "revision_id": rev_id,
                    "source_timestamp": meta.get("revision_timestamp"),
                    "fetched_at": meta.get("revision_timestamp"),
                    "sha256": meta["source_sha256"],
                    "cache_path": f"reference/sources/wikipedia/wikitext/{rev_id}.wiki",
                    "summary_json": json.dumps({"page": title, "revision_id": rev_id, "items_matched": len(page_items)}),
                }
            )
            feed_items.extend(page_items)

    return raw_sources, feed_items


# ---------------------------------------------------------------------------
# 2. Wikidata SPARQL Day-Precision Events (CC0)
# ---------------------------------------------------------------------------

def acquire_wikidata_days(dates: list[str]) -> Path:
    values = " ".join(f'"{d}T00:00:00Z"^^xsd:dateTime' for d in dates)
    query = f"""SELECT DISTINCT ?item ?itemLabel ?itemDescription ?date ?sl WHERE {{
  VALUES ?date {{ {values} }}
  ?item p:P585/psv:P585 ?tn .
  ?tn wikibase:timeValue ?date ; wikibase:timePrecision 11 .
  ?item wikibase:sitelinks ?sl . FILTER(?sl >= 1)
  FILTER NOT EXISTS {{ ?item wdt:P31 wd:Q5 }}
  FILTER NOT EXISTS {{ ?item wdt:P31 wd:Q482994 }}
  FILTER NOT EXISTS {{ ?item wdt:P31 wd:Q134556 }}
  FILTER NOT EXISTS {{ ?item wdt:P31 wd:Q11424 }}
  FILTER NOT EXISTS {{ ?item wdt:P31 wd:Q13406463 }}
  FILTER NOT EXISTS {{ ?item wdt:P31 wd:Q577 }}
  FILTER NOT EXISTS {{ ?item wdt:P31 wd:Q39911 }}
  FILTER NOT EXISTS {{ ?item wdt:P31 wd:Q5398426 }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}} ORDER BY DESC(?sl) LIMIT 100"""
    resp = requests.get(
        "https://query.wikidata.org/sparql",
        params={"query": query, "format": "json"},
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    resp.raise_for_status()
    bindings = resp.json().get("results", {}).get("bindings", [])
    fetched_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    by_date: dict[str, list[dict[str, Any]]] = {d: [] for d in dates}
    seen: set[tuple[str, str]] = set()
    for b in bindings:
        d = b["date"]["value"][:10]
        qid = b["item"]["value"].rsplit("/", 1)[-1]
        if (d, qid) in seen or d not in by_date:
            continue
        seen.add((d, qid))
        by_date[d].append(
            {
                "qid": qid,
                "label": b.get("itemLabel", {}).get("value", qid),
                "description": b.get("itemDescription", {}).get("value", ""),
                "sitelinks": int(b.get("sl", {}).get("value", 0)),
                "url": f"https://www.wikidata.org/wiki/{qid}",
            }
        )
    last_path = MULTISOURCE_CACHE
    for d, items in by_date.items():
        last_path, _ = _write_cached_json(
            f"wikidata/{d}.json",
            {
                "date": d,
                "fetched_at": fetched_at,
                "query_endpoint": "https://query.wikidata.org/sparql",
                "time_precision": 11,
                "items": items,
            },
        )
    return last_path


def extract_wikidata_day(date_str: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    subpath = f"wikidata/{date_str}.json"
    if not (MULTISOURCE_CACHE / subpath).exists():
        return [], []
    _, sha, data = _read_cached_json(subpath)
    src_id = f"wikidata-{date_str}"
    raw_source = {
        "source_id": src_id,
        "source_type": "wikidata_sparql_day_precision",
        "title_or_query": f"Wikidata P585/P580 precision=11 for {date_str}",
        "uri": data["query_endpoint"],
        "revision_id": None,
        "source_timestamp": date_str,
        "fetched_at": data.get("fetched_at"),
        "sha256": sha,
        "cache_path": f"reference/sources/{subpath}",
        "summary_json": json.dumps({"item_count": len(data.get("items", []))}),
    }
    items = []
    for idx, it in enumerate(data.get("items", [])):
        items.append(
            {
                "item_id": f"{src_id}-{it['qid']}",
                "source_id": src_id,
                "feed_type": "wikidata_event",
                "ord": idx,
                "title": f"{it['label']} ({it['qid']})" + (f" — {it['description']}" if it.get("description") else ""),
                "category": "Wikidata structured item",
                "actors_text": it["label"],
                "location_text": "",
                "metric_value": f"sitelinks={it['sitelinks']}",
                "url": it["url"],
                "raw_json": json.dumps(it, ensure_ascii=False),
            }
        )
    return [raw_source], items


# ---------------------------------------------------------------------------
# 3. USGS Earthquake ComCat API (M4.5+)
# ---------------------------------------------------------------------------

def acquire_usgs_day(date_str: str) -> Path:
    start = dt.date.fromisoformat(date_str)
    end = start + dt.timedelta(days=1)
    resp = requests.get(
        "https://earthquake.usgs.gov/fdsnws/event/1/query",
        params={
            "format": "geojson",
            "starttime": start.isoformat(),
            "endtime": end.isoformat(),
            "minmagnitude": "4.5",
            "orderby": "magnitude",
        },
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    resp.raise_for_status()
    geo = resp.json()
    fetched_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    features = []
    for feat in geo.get("features", []):
        props = feat.get("properties", {})
        coords = feat.get("geometry", {}).get("coordinates", [None, None, None])
        t_ms = props.get("time")
        iso_time = (
            dt.datetime.fromtimestamp(t_ms / 1000.0, tz=dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            if t_ms is not None
            else None
        )
        features.append(
            {
                "id": feat.get("id"),
                "mag": props.get("mag"),
                "place": props.get("place"),
                "time_utc": iso_time,
                "url": props.get("url"),
                "longitude": coords[0],
                "latitude": coords[1],
                "depth_km": coords[2],
            }
        )
    path, _ = _write_cached_json(
        f"usgs/{date_str}.json",
        {
            "date": date_str,
            "fetched_at": fetched_at,
            "endpoint": "https://earthquake.usgs.gov/fdsnws/event/1/query",
            "minmagnitude": 4.5,
            "earthquakes": features,
        },
    )
    return path


def extract_usgs_day(date_str: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    subpath = f"usgs/{date_str}.json"
    if not (MULTISOURCE_CACHE / subpath).exists():
        return [], []
    _, sha, data = _read_cached_json(subpath)
    src_id = f"usgs-{date_str}"
    quakes = data.get("earthquakes", [])
    raw_source = {
        "source_id": src_id,
        "source_type": "usgs_comcat_geojson",
        "title_or_query": f"USGS ComCat M4.5+ earthquakes for {date_str}",
        "uri": data["endpoint"],
        "revision_id": None,
        "source_timestamp": date_str,
        "fetched_at": data.get("fetched_at"),
        "sha256": sha,
        "cache_path": f"reference/sources/{subpath}",
        "summary_json": json.dumps({"earthquake_count": len(quakes)}),
    }
    items = []
    for idx, q in enumerate(quakes):
        items.append(
            {
                "item_id": f"{src_id}-{q['id']}",
                "source_id": src_id,
                "feed_type": "usgs_earthquake",
                "ord": idx,
                "title": f"M {q['mag']} earthquake — {q['place']} ({q['time_utc']})",
                "category": "Disasters and accidents",
                "actors_text": "USGS ANSS ComCat",
                "location_text": q.get("place") or "",
                "metric_value": f"M{q['mag']} (depth {q['depth_km']} km)",
                "url": q.get("url") or f"https://earthquake.usgs.gov/earthquakes/eventpage/{q['id']}",
                "raw_json": json.dumps(q, ensure_ascii=False),
            }
        )
    return [raw_source], items


# ---------------------------------------------------------------------------
# 4. GDELT 1.0 Historical Event Archive (1979-2013 CAMEO Stream)
# ---------------------------------------------------------------------------

def acquire_gdelt_v1_days(year: int, target_dates: list[str], top_k: int = 25) -> list[Path]:
    """Stream `https://data.gdeltproject.org/events/<YYYY>.zip` and cache daily CAMEO summaries."""
    day_keys = {d.replace("-", ""): d for d in target_dates}
    max_key = max(day_keys.keys())
    rows_by_day: dict[str, list[list[str]]] = {k: [] for k in day_keys}

    url = f"https://data.gdeltproject.org/events/{year}.zip"
    fetched_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with requests.get(url, headers={"User-Agent": USER_AGENT}, stream=True, timeout=30) as resp:
        resp.raise_for_status()
        it = resp.iter_content(chunk_size=65536)
        first = next(it)
        fn_len, ex_len = struct.unpack("<HH", first[26:30])
        dec = zlib.decompressobj(-zlib.MAX_WBITS)
        buf = dec.decompress(first[30 + fn_len + ex_len :]).decode("utf-8", errors="replace")
        for chunk in it:
            buf += dec.decompress(chunk).decode("utf-8", errors="replace")
            *complete, buf = buf.split("\n")
            stop = False
            for line in complete:
                cols = line.split("\t")
                if len(cols) > 52:
                    d_key = cols[1]
                    if d_key in rows_by_day:
                        rows_by_day[d_key].append(cols)
                    elif d_key > max_key and any(rows_by_day.values()):
                        stop = True
            if stop:
                break

    written: list[Path] = []
    for d_key, iso_date in sorted(day_keys.items()):
        rlist = rows_by_day[d_key]
        sorted_rows = sorted(rlist, key=lambda c: (int(c[31] or 0), int(c[33] or 0)), reverse=True)
        clusters = []
        seen: set[tuple[str, str, str, str]] = set()
        country_counts: dict[str, int] = {}

        def _row_to_cluster(c: list[str]) -> dict[str, Any]:
            a1 = c[6].strip()
            a2 = c[16].strip()
            cameo = c[26].strip()
            geo = c[50].strip()
            root_code = c[28].strip().zfill(2) if c[28].strip() else cameo[:2]
            return {
                "global_event_id": c[0],
                "actor1_name": a1 or None,
                "actor1_country_code": c[7].strip() or None,
                "actor2_name": a2 or None,
                "actor2_country_code": c[17].strip() or None,
                "event_code": cameo,
                "event_root_code": root_code,
                "event_root_label": CAMEO_ROOT_LABELS.get(root_code, "Event"),
                "quad_class": int(c[29]) if c[29].isdigit() else None,
                "goldstein_scale": float(c[30]) if c[30] else 0.0,
                "num_mentions": int(c[31] or 0),
                "num_sources": int(c[32] or 0),
                "num_articles": int(c[33] or 0),
                "avg_tone": round(float(c[34]), 3) if c[34] else 0.0,
                "action_geo_name": geo or None,
                "action_geo_country_code": c[51].strip() or None,
            }

        # Pass 1: Top 20 overall clusters by mention count
        primary_limit = min(20, top_k)
        for c in sorted_rows:
            a1 = c[6].strip()
            a2 = c[16].strip()
            cameo = c[26].strip()
            geo = c[50].strip()
            if not a1 and not a2:
                continue
            dedup_key = (a1, a2, cameo, geo)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            cl = _row_to_cluster(c)
            clusters.append(cl)
            cc = cl.get("action_geo_country_code") or ""
            country_counts[cc] = country_counts.get(cc, 0) + 1
            if len(clusters) >= primary_limit:
                break

        # Pass 2: Regional/country diversification up to top_k
        if len(clusters) < top_k:
            for c in sorted_rows:
                a1 = c[6].strip()
                a2 = c[16].strip()
                cameo = c[26].strip()
                geo = c[50].strip()
                cc = c[51].strip()
                if not a1 and not a2:
                    continue
                dedup_key = (a1, a2, cameo, geo)
                if dedup_key in seen:
                    continue
                if cc and country_counts.get(cc, 0) >= 2:
                    continue
                seen.add(dedup_key)
                cl = _row_to_cluster(c)
                clusters.append(cl)
                country_counts[cc] = country_counts.get(cc, 0) + 1
                if len(clusters) >= top_k:
                    break

        path, _ = _write_cached_json(
            f"gdelt_v1/{iso_date}.json",
            {
                "date": iso_date,
                "source_archive": url,
                "fetched_at": fetched_at,
                "total_cameo_events": len(rlist),
                "top_clusters": clusters,
            },
        )
        written.append(path)
    return written


def extract_gdelt_v1_day(date_str: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    subpath = f"gdelt_v1/{date_str}.json"
    if not (MULTISOURCE_CACHE / subpath).exists():
        return [], []
    _, sha, data = _read_cached_json(subpath)
    src_id = f"gdelt-v1-{date_str}"
    clusters = data.get("top_clusters", [])
    raw_source = {
        "source_id": src_id,
        "source_type": "gdelt_v1_cameo_archive",
        "title_or_query": f"GDELT 1.0 historical CAMEO events for {date_str}",
        "uri": data["source_archive"],
        "revision_id": None,
        "source_timestamp": date_str,
        "fetched_at": data.get("fetched_at"),
        "sha256": sha,
        "cache_path": f"reference/sources/{subpath}",
        "summary_json": json.dumps(
            {
                "total_cameo_events": data.get("total_cameo_events", 0),
                "top_clusters_stored": len(clusters),
            }
        ),
    }
    items = []
    for idx, cl in enumerate(clusters):
        a1 = cl.get("actor1_name") or "UNSPECIFIED"
        a2 = cl.get("actor2_name") or "UNSPECIFIED"
        items.append(
            {
                "item_id": f"{src_id}-{cl['global_event_id']}",
                "source_id": src_id,
                "feed_type": "gdelt_v1_cameo",
                "ord": idx,
                "title": f"{a1} -> {a2}: {cl['event_root_label']} (CAMEO {cl['event_code']})",
                "category": cl["event_root_label"],
                "actors_text": ", ".join(x for x in (cl.get("actor1_name"), cl.get("actor2_name")) if x),
                "location_text": cl.get("action_geo_name") or "",
                "metric_value": f"mentions={cl['num_mentions']}, articles={cl['num_articles']}, goldstein={cl['goldstein_scale']}",
                "url": data["source_archive"],
                "raw_json": json.dumps(cl, ensure_ascii=False),
            }
        )
    return [raw_source], items


def collect_day_feeds(date_str: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Combine all cached multi-source records and structured feed items for `date_str`."""
    raw_sources: list[dict[str, Any]] = []
    feed_items: list[dict[str, Any]] = []

    for extractor in (
        extract_wikipedia_retrospective_day,
        extract_wikidata_day,
        extract_usgs_day,
        extract_gdelt_v1_day,
    ):
        srcs, items = extractor(date_str)
        raw_sources.extend(srcs)
        for it in items:
            it["ord"] = len(feed_items)
            feed_items.append(it)
    return raw_sources, feed_items


def acquire_all_for_dates(dates: list[str], top_k_gdelt: int = 35) -> None:
    """Acquire and cache all 4 source layers for a list of ISO dates."""
    by_year: dict[int, list[str]] = {}
    for d in sorted(set(dates)):
        by_year.setdefault(int(d[:4]), []).append(d)

    for year, y_dates in sorted(by_year.items()):
        day_titles = [f"{dt.date.fromisoformat(d).strftime('%B')} {dt.date.fromisoformat(d).day}" for d in y_dates]
        acquire_wikipedia_retrospective(year, day_titles=day_titles)
        acquire_wikidata_days(y_dates)
        for d in y_dates:
            acquire_usgs_day(d)
        if year <= 2013:
            acquire_gdelt_v1_days(year, y_dates, top_k=top_k_gdelt)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Multi-source acquisition and offline feed inspection")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_acq = sub.add_parser("acquire", help="Acquire and cache all multi-source layers for one or more dates")
    p_acq.add_argument("dates", nargs="+", help="ISO dates (YYYY-MM-DD)")

    p_ins = sub.add_parser("inspect", help="Print cached multi-source feed items for one or more dates")
    p_ins.add_argument("dates", nargs="+", help="ISO dates (YYYY-MM-DD)")

    args = parser.parse_args(argv)
    if args.cmd == "acquire":
        acquire_all_for_dates(args.dates)
        for d in args.dates:
            srcs, items = collect_day_feeds(d)
            print(f"{d}: cached {len(srcs)} raw sources, {len(items)} structured feed items")
        return 0
    if args.cmd == "inspect":
        for d in args.dates:
            srcs, items = collect_day_feeds(d)
            print(f"=== {d} ({len(srcs)} sources, {len(items)} feed items) ===")
            for it in items:
                print(f"  [{it['feed_type']}] {it['title']} | {it['location_text']} | {it['metric_value']}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
