"""Guarded publisher review and deterministic Markdown previews of annual archives."""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import html
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import quote, urlsplit

from . import annual_archive as annual

VERSION = "yearbook-review-1.0"
INPUTS = ("seed/yearbook.py", "reference/schema/YEARBOOK.md")
ROLE = "yearbook_event_review"


def event_key(row):
    return (row["date"], row["category_ord"], row["ord"])


def validate_review(conn, record):
    """Validate identity and explicit coverage, without pretending to verify facts."""
    if record["contract"] != VERSION or not re.fullmatch(r"[a-zA-Z0-9_-]+", record["id"]):
        raise ValueError("Unsupported editorial record contract or ID")
    row = annual.locate_review_event(conn, record["locator"])
    if annual.structured_hash(row) != record["event_sha256"]:
        raise ValueError("Editorial review extraction drift")
    for key in ("checked_on", "display_date"):
        if str(dt.date.fromisoformat(record[key])) != record[key]:
            raise ValueError("Editorial dates must use ISO format")
    if record["display_date"][:4] != row["date"][:4]:
        raise ValueError("Cross-year editorial dates require a separate migration")
    if record["state"] not in ("complete", "partial"):
        raise ValueError("Invalid full-event review state")
    if not record["statement"].strip() or not record["note"].strip():
        raise ValueError("Editorial statement and review note are required")
    if record["perspective"] != "retrospective" or not record["workflow"].strip():
        raise ValueError("Review generation provenance is required")
    if "model" not in record:
        raise ValueError("Record the generating model, or null when unknown")
    evidence = record["evidence"]
    if not evidence:
        raise ValueError("Publisher evidence is required")
    for e in evidence:
        if urlsplit(e["url"]).scheme not in ("https", "http") or not urlsplit(e["url"]).netloc:
            raise ValueError("Publisher evidence must have a public HTTP URL")
        if e["access_status"] != "opened" or not all(e[k].strip() for k in ("publisher", "locator", "note")):
            raise ValueError("Editorial evidence must identify opened source passages")
    # Every source character belongs to a claim disposition. Missing clauses
    # cannot accidentally inherit the status of a checked headline or number.
    cursor = 0
    dispositions = record["dispositions"]
    if not dispositions:
        raise ValueError("Every source assertion needs a disposition")
    for claim in dispositions:
        if claim["start"] != cursor or not cursor < claim["end"] <= len(row["text"]):
            raise ValueError("Source claim coverage has gaps or overlaps")
        cursor = claim["end"]
        if claim["assessment"] not in ("supported", "contradicted", "unsubstantiated", "wording"):
            raise ValueError("Invalid claim assessment")
        if not claim["note"].strip() or not claim["evidence"]:
            raise ValueError("Claim assessment needs an evidence explanation")
        if any(type(n) is not int or n < 0 or n >= len(evidence) for n in claim["evidence"]):
            raise ValueError("Claim evidence reference is invalid")
    if cursor != len(row["text"]):
        raise ValueError("Source claim coverage is incomplete")
    if record["state"] == "complete" and any(c["assessment"] == "unsubstantiated" for c in dispositions):
        raise ValueError("Unsubstantiated source claims keep full-event review partial")
    return row


def load_reviews(conn):
    reviews = {}
    for item in conn.execute("SELECT path,date FROM archive_inputs WHERE role=? ORDER BY path", (ROLE,)):
        record = json.loads(annual.input_bytes(conn, item["path"]))
        row = validate_review(conn, record)
        if item["date"] != row["date"] or item["path"] != f"yearbook/reviews/{record['id']}.json":
            raise ValueError("Editorial input identity drift")
        key = event_key(row)
        if key in reviews:
            raise ValueError("Multiple editorial resolutions for one event require an explicit supersession migration")
        reviews[key] = record
    if reviews:
        for name in INPUTS:
            if annual.input_bytes(conn, f"yearbook/implementation/{VERSION}/{name}") != (annual.ROOT / name).read_bytes():
                raise ValueError(f"Editorial implementation drift: {name}")
    return reviews


def record_review(conn, record):
    row = validate_review(conn, record)
    existing = load_reviews(conn).get(event_key(row))
    if existing is not None and existing != record:
        raise ValueError("Editorial resolution is immutable; migrate explicitly")
    with conn:
        for name in INPUTS:
            annual.put_input(conn, f"yearbook/implementation/{VERSION}/{name}",
                             (annual.ROOT / name).read_bytes(), "yearbook_implementation")
        annual.put_input(conn, f"yearbook/reviews/{record['id']}.json", annual.encoded(record),
                         ROLE, row["date"], "application/json")
        conn.execute("DELETE FROM archive_checks WHERE name IN ('yearbook','markdown')")


def review_report(conn):
    reviews = load_reviews(conn)
    rows = list(conn.execute("SELECT * FROM event_overview WHERE role='event' ORDER BY date,category_ord,ord"))
    complete = sum(r["state"] == "complete" for r in reviews.values())
    uncited = [event_key(r) for r in rows if not conn.execute(
        "SELECT 1 FROM event_citations WHERE date=? AND category_ord=? AND entry_ord=? LIMIT 1", event_key(r)).fetchone()]
    missing = [list(k) for k in uncited if k not in reviews]
    return {"contract": VERSION, "source_events": len(rows), "editorial_resolutions": len(reviews),
            "full_event_reviews_complete": complete, "full_event_reviews_partial": len(reviews) - complete,
            "events_without_full_event_review": len(rows) - len(reviews),
            "events_remaining_before_factual_gate": len(rows) - complete,
            "source_events_without_attached_citations": len(uncited),
            "uncited_events_without_editorial_evidence": missing,
            "every_event_independently_checked": complete == len(rows) and bool(rows),
            "replacement_ready": False, "yearbook_ready": False,
            "policy": "Every event requires a complete independent review before cutover; scoped samples do not count. Other migration and synthesis gates also remain."}


def queue(conn, month=None):
    reviews = load_reviews(conn)
    for row in conn.execute("SELECT * FROM event_overview WHERE role='event' ORDER BY date,category_ord,ord"):
        if month and not row["date"].startswith(month):
            continue
        review = reviews.get(event_key(row))
        if review and review["state"] == "complete":
            continue
        yield {"locator": annual.review_locator(row), "event_sha256": annual.structured_hash(dict(row)),
               "text": row["text"], "state": review["state"] if review else "unreviewed",
               "citations": [dict(c) for c in conn.execute(
                   "SELECT url,publisher,display FROM event_citations WHERE date=? AND category_ord=? AND entry_ord=? ORDER BY citation_ord", event_key(row))]}


def safe_text(value):
    value = html.escape(" ".join(str(value).split()), quote=False)
    return re.sub(r"([\\`*_{}\[\]#!|])", r"\\\1", value)


def source_link(publisher, url):
    if urlsplit(url).scheme not in ("https", "http"):
        return safe_text(publisher) + " (non-HTTP source link retained in database)"
    return f"[{safe_text(publisher)}](<{html.escape(url, quote=True)}>)"


def render(conn, database_sha256):
    """Complete chronological preview, with explicit review labels on every event."""
    report = review_report(conn)
    reviews = load_reviews(conn)
    year = conn.execute("SELECT value FROM archive_metadata WHERE key='year'").fetchone()[0]
    rows = list(conn.execute("SELECT * FROM event_overview WHERE role='event' ORDER BY date,category_ord,ord"))
    lines = [f"# {year}: current events chronicle", "", "**Draft reference preview. Independent factual review is incomplete.**", "",
             "This readable companion includes every archived event assertion, grouped by its original portal date. "
             "Most entries reproduce Wikipedia's source account and have not been independently checked. "
             "Editorial passages are explicitly labeled and separately cited. This is not a finished historical yearbook.", "",
             f"Database: [{year}.sqlite]({year}.sqlite). Edition SHA-256: `{database_sha256}`. "
             f"Renderer/review contract: `{VERSION}`.", "",
             f"Source coverage: {len(rows):,} event assertions across {conn.execute('SELECT count(*) FROM extraction_days').fetchone()[0]} dates. "
             f"Full-event reviews complete: {report['full_event_reviews_complete']:,}; partial: {report['full_event_reviews_partial']:,}; "
             f"without a full-event review: {report['events_without_full_event_review']:,}. "
             "Earlier scoped checks are recorded separately in the database and do not approve whole events.", "",
             "The old daily files remain in place until every event passes independent review and the remaining migration gates pass. "
             "Original errors, dates, list hierarchy, source citations and exact revision payloads remain in the database. "
             "A citation copied from Wikipedia does not mean that its article was opened during this review.", "",
             "This edition follows Wikipedia's selection; it does not establish complete global coverage. "
             "Historical casualty totals and attributed claims must be read at their reporting times. "
             "Five retained unclassified fragments concern one malformed May 6 football passage; they are not silently promoted to events. "
             "The empty July 5 source marker is preserved in the database and omitted from this narrative.", "",
             "Wikipedia source text is attributed to the linked revision histories and remains subject to its CC BY-SA terms. "
             "Publisher links identify evidence; publisher full text and images are not reproduced here.", "", "## Contents", ""]
    for month in range(1, 13):
        lines.append(f"- [{calendar.month_name[month]}](#{calendar.month_name[month].lower()})")
    day, month, category = None, None, None
    for row in rows:
        current = row["date"]
        if current[5:7] != month:
            month = current[5:7]
            lines += ["", f"## {calendar.month_name[int(month)]}", ""]
        if current != day:
            day, category = current, None
            url = f"https://en.wikipedia.org/w/index.php?title={quote(row['page'], safe='')}&oldid={row['revision_id']}"
            lines += [f"### {day}", "", f"[Pinned Wikipedia revision {row['revision_id']}](<{url}>).", ""]
        if row["category_ord"] != category:
            category = row["category_ord"]
            lines += [f"#### {safe_text(row['category'])}", ""]
        # Topic ancestry is drawn from exact source paths, never guessed from proximity.
        ancestors, parent = [], row["parent_path_json"]
        while parent is not None:
            p = conn.execute("SELECT text,role,parent_path_json FROM event_overview WHERE date=? AND category_ord=? AND json(source_path_json)=json(?)",
                             (day, category, parent)).fetchone()
            if p is None:
                raise ValueError("Missing parent while rendering")
            ancestors.append(p["text"])
            parent = p["parent_path_json"]
        context = " / ".join(reversed(ancestors))
        key = event_key(row)
        anchor = f"event-{day}-{category}-{row['ord']}"
        lines += [f'<a id="{anchor}"></a>', ""]
        if context:
            lines += [f"Context: {safe_text(context)}.", ""]
        review = reviews.get(key)
        if review:
            lines += [f"**Editorial account; source review {review['state']}.** {safe_text(review['statement'])}", "",
                      f"Editorial date: {review['display_date']}. Checked: {review['checked_on']}. {safe_text(review['note'])}", "",
                      "Evidence: " + "; ".join(source_link(e["publisher"], e["url"]) for e in review["evidence"]) + ".", "",
                      f"Original source account: {safe_text(row['text'])}", ""]
        else:
            lines += [f"**Source account; full-event review pending.** {safe_text(row['text'])}", ""]
        citations = list(conn.execute("SELECT url,publisher,display FROM event_citations WHERE date=? AND category_ord=? AND entry_ord=? ORDER BY citation_ord", key))
        if citations:
            lines += ["Source citations (as archived): " + "; ".join(source_link(c["publisher"] or c["display"] or "Source", c["url"]) for c in citations) + ".", ""]
        elif not review:
            lines += ["No attached source citation; independent evidence still required.", ""]
        else:
            lines += ["The original source entry had no attached citation; independent evidence is supplied above.", ""]
    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("record", "verify", "render", "queue"):
        cmd = sub.add_parser(name)
        cmd.add_argument("database", type=Path)
        if name == "record":
            cmd.add_argument("record", type=Path)
        if name == "render":
            cmd.add_argument("--output", type=Path)
        if name == "queue":
            cmd.add_argument("--month")
            cmd.add_argument("--limit", type=int, default=10)
    args = parser.parse_args(argv)
    conn = annual.connect(args.database, readonly=args.command != "record")
    try:
        if args.command == "record":
            record_review(conn, json.loads(args.record.read_text(encoding="utf-8")))
            result = review_report(conn)
        elif args.command == "queue":
            if args.limit < 1:
                raise ValueError("Queue limit must be positive")
            import itertools
            result = list(itertools.islice(queue(conn, args.month), args.limit))
        elif args.command == "verify":
            result = {"archive": annual.verify(conn), "editorial": review_report(conn)}
        else:
            # Read-only generation binds the Markdown to the exact closed-on-disk
            # edition; it does not change the DB or produce a circular checksum.
            if args.database.with_name(args.database.name + "-wal").exists() or args.database.with_name(args.database.name + "-journal").exists():
                raise ValueError("Close database writers before rendering an edition")
            annual.verify(conn)
            payload = render(conn, annual.digest(args.database.read_bytes()))
            target = args.output or args.database.with_suffix(".md")
            if target.resolve() == args.database.resolve():
                raise ValueError("Markdown output cannot overwrite its database")
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix=f".{target.name}-", dir=target.parent)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(payload)
                os.replace(temporary, target)
            finally:
                Path(temporary).unlink(missing_ok=True)
            result = {"output": str(target), "sha256": annual.digest(payload), "bytes": len(payload), **review_report(conn)}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
