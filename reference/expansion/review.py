"""Regenerate a machine review queue; publisher verification remains explicit."""
import argparse
import html
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit, unquote

import build
import corrections
import inputs


def normalized(value):
    return re.sub(r"[^\w]+", " ", html.unescape(re.sub(r"[\u200b-\u200d\ufeff]", "", value)).lower()).strip()


def review(days):
    records = []
    for day in days:
        selected = inputs.selection(day)
        report = inputs.resolve(selected["report"]).read_text(encoding="utf-8") if selected.get("report") else ""
        text = normalized(report)
        plain = html.unescape(re.sub(r"\\([_&()])", r"\1", report))
        overlay = corrections.path(day)
        extra = json.loads(overlay.read_text(encoding="utf-8")) if overlay.exists() else []
        evidence = {url for record in extra for url in record.get("evidence", [])}
        for event in build.build(day)["events"]:
            flags = []
            sources = event["sources"]["external"]
            if not sources:
                flags.append({"code": "PORTAL_ONLY", "message": "Review the original publisher linked by the portal; no external article is recorded."})
            for source in sources:
                url = source["url"]
                host = (urlsplit(url).hostname or "").lower()
                if host == "cbsnews.com" or host.endswith(".cbsnews.com") or "cbs" in source["outlet"].lower():
                    flags.append({"code": "INDEPENDENT_CORROBORATION_REQUIRED", "source_id": source["id"], "url": url,
                                  "message": "CBS receives no assumed reliability; document independent claim support in the publisher review ledger."})
                if url not in plain and unquote(url) not in unquote(plain) and url not in evidence:
                    flags.append({"code": "URL_NOT_IN_SELECTED_INPUT", "source_id": source["id"], "url": url})
                if urlsplit(url).path in ("", "/"):
                    flags.append({"code": "HOMEPAGE_ONLY", "source_id": source["id"], "url": url})
                if source["publication_date"] > day:
                    flags.append({"code": "LATER_PUBLICATION", "source_id": source["id"], "url": url,
                                  "publication_date": source["publication_date"],
                                  "message": "Check the event date and distinguish later information from contemporary claims."})
                for quote in source["quoted_material"]:
                    parts = [normalized(part) for part in re.split(r"(?:\.{3}|\u2026)", quote)]
                    if not all(part in text for part in parts if part):
                        flags.append({"code": "QUOTE_NOT_IN_SELECTED_REPORT", "source_id": source["id"], "url": url,
                                      "quote_sha256": hashlib.sha256(quote.encode("utf-8")).hexdigest()})
            records.append({"date": day, "event_id": event["id"], "event_sha256": corrections.event_hash(event),
                            "report": selected.get("report"), "report_sha256": selected.get("report_sha256"),
                            "status": "publisher_review_pending", "flags": flags,
                            "source_urls": [s["url"] for s in sources]})
    return {"scope": "Machine checks against selected inputs; no claim of publisher verification or factual review.", "events": records}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dates", nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(review(args.dates), ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
