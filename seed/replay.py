"""Explicit acquisition and offline candidate generation, separated by command."""
from __future__ import annotations
import copy
import json
import re
from functools import lru_cache
from pathlib import Path
import yaml
from jsonschema import Draft202012Validator
from seed import source
from seed.extract import body, canonical, extract, fingerprint
from seed.merge import REPO_ROOT


def seed_path(day):
    return REPO_ROOT / day[:4] / day[5:7] / (day + ".yaml")


def seed_doc(day):
    return yaml.load(seed_path(day).read_text(encoding="utf-8"), Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))


@lru_cache(maxsize=1)
def extraction_validator():
    schema = json.loads((REPO_ROOT / "reference/schema/extraction.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def source_title(doc):
    return doc.get("source_page", {}).get("portal") or doc.get("Source_URI")


def cached_input(day, doc):
    revision = doc.get("source_page", {}).get("wikipedia_revision_id")
    if revision is not None:
        return source.revision(revision)
    meta, raw = source.captured(day)
    title = source_title(doc)
    if title is None or title.split("#")[0] != meta["page"]:
        raise ValueError(f"No matching pinned source identity for {day}")
    return meta, raw


def candidate(day, *, overrides=None):
    doc = seed_doc(day)
    meta, raw = cached_input(day, doc)
    identity = {k: meta[k] for k in ("page", "revision_id", "revision_timestamp", "source_mode", "source_sha256")}
    result = extract(raw.decode("utf-8"), date=day, source=identity, overrides=overrides)
    if "gdelt" in doc:
        result["gdelt"] = copy.deepcopy(doc["gdelt"])
    extraction_validator().validate(result)
    return result


def dump(doc):
    return yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=1000,
                          default_flow_style=False, line_break="\n").rstrip("\n") + "\n"


def write_if_changed(path, text):
    payload = text.encode("utf-8")
    if not path.exists() or path.read_bytes() != payload:
        path.write_bytes(payload)


def save_capture(day, archive, gdelt=None):
    """New acquisitions retain a hierarchy artifact without replacing old output."""
    doc = copy.deepcopy(archive)
    if gdelt is not None:
        doc["gdelt"] = copy.deepcopy(gdelt)
    extraction_validator().validate(doc)
    path = REPO_ROOT / "provisional/captures" / day[:4] / day[5:7] / (day + ".yaml")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump(doc), encoding="utf-8", newline="\n")
    path.with_suffix(".warnings.jsonl").write_text("".join(json.dumps(w, ensure_ascii=False) + "\n" for w in doc["warnings"]), encoding="utf-8", newline="\n")


def run_cache(args):
    if args.start and args.end and args.end < args.start:
        raise ValueError("End date precedes start date")
    source.import_expansion_cache()
    if args.start is None:
        print("Imported and verified existing exact wikitext inputs")
        return 0
    from seed.cli import iter_days, USER_AGENT
    from seed.wikipedia import acquire_revision_batch, fetch_wikitext, REQUEST_DELAY_SECS
    import time
    from datetime import datetime, timezone
    pending, skipped, current = [], [], []
    for day in iter_days(args.start, args.end or args.start):
        if not seed_path(day.isoformat()).exists():
            skipped.append({"date": str(day), "reason": "missing_seed"})
            continue
        doc = seed_doc(day.isoformat())
        rev = doc.get("source_page", {}).get("wikipedia_revision_id")
        if rev is None:
            if getattr(args, "capture_unpinned", False):
                title = source_title(doc)
                if not title or "#" in title:
                    raise ValueError(f"{day}: explicit daily source title required for current capture")
                try:
                    meta, _ = cached_input(str(day), doc)
                    reused = True
                except FileNotFoundError:
                    fetched = fetch_wikitext(title, USER_AGENT)
                    if fetched is None or fetched.source_meta is None:
                        raise ValueError(f"{day}: current source acquisition failed")
                    meta = fetched.source_meta
                    if meta["page"] != title:
                        raise ValueError(f"{day}: acquired title differs from recorded source identity")
                    source.capture(str(day), meta)
                    reused = False
                    time.sleep(REQUEST_DELAY_SECS)
                current.append({"date": str(day), "policy": "current_revision_as_new_input",
                                "original_capture_revision": None, "reused_capture": reused,
                                "source": meta})
                print(f"Current capture: {day} oldid={meta['revision_id']}", flush=True)
                continue
            if not args.skip_unpinned:
                raise ValueError(f"{day}: no recorded oldid; choose an acquisition policy explicitly")
            skipped.append({"date": str(day), "reason": "unpinned_legacy"})
            continue
        try:
            source.revision(rev)
        except FileNotFoundError:
            pending.append(rev)
    acquired = 0
    for index in range(0, len(pending), args.batch_size):
        group = pending[index:index + args.batch_size]
        acquire_revision_batch(group, USER_AGENT)
        acquired += len(group)
        print(f"Acquired pinned oldids: {acquired}/{len(pending)}", flush=True)
        if acquired < len(pending):
            time.sleep(REQUEST_DELAY_SECS)
    report = {"requested_range": [str(args.start), str(args.end or args.start)],
              "acquired": acquired, "skipped": skipped}
    if getattr(args, "capture_unpinned", False):
        report.update({"recorded_at": datetime.now(timezone.utc).isoformat(), "new_source_captures": current,
                       "policy": "Current revisions are new inputs; original legacy files are preserved."})
    report_name = "current-captures-report.json" if getattr(args, "capture_unpinned", False) else "acquisition-report.json"
    (source.CACHE / report_name).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Exact acquisition complete; {len(skipped)} dates without a pinned seed")
    return 0


def run_reparse(args):
    if args.end < args.start:
        raise ValueError("End date precedes start date")
    from seed.cli import iter_days
    output = args.output_root.resolve()
    forbidden = [REPO_ROOT.resolve(), (REPO_ROOT / "expanded").resolve(), (REPO_ROOT / "reference").resolve()]
    if output in forbidden or any(p.name.isdigit() and len(p.name) == 4 for p in [output, *output.parents] if p != REPO_ROOT):
        raise ValueError("Candidate output must be separate from canonical/source trees")
    if any(output.is_relative_to(p) for p in forbidden[1:]):
        raise ValueError("Candidate output cannot overwrite synthesis or sources")
    selected = json.loads(args.overrides.read_text(encoding="utf-8")) if args.overrides else []
    unknown_override_days = {o["date"] for o in selected}
    prepared, missing, checks = [], [], []
    for day_obj in iter_days(args.start, args.end):
        day = day_obj.isoformat()
        if not seed_path(day).exists():
            missing.append({"date": day, "reason": "missing_seed"})
            continue
        try:
            result = candidate(day, overrides=[o for o in selected if o["date"] == day])
        except FileNotFoundError:
            missing.append({"date": day, "reason": "uncached_source"})
            continue
        unknown_override_days.discard(day)
        old = seed_doc(day)
        meta, payload = cached_input(day, old)
        entries = [e for c in result["categories"] for e in c["entries"]]
        if getattr(args, "verify", False):
            repeated = candidate(day, overrides=[o for o in selected if o["date"] == day])
            serialized = dump(result)
            if serialized != dump(repeated) or canonical(result) != canonical(yaml.load(serialized, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))):
                raise ValueError(f"Non-idempotent or lossy structural replay for {day}")
            lines = [c.get("line", c["entries"][0]["line"] if c["entries"] else 0) for c in result["categories"]]
            if lines != sorted(lines) or any([e["line"] for e in c["entries"]] != sorted(e["line"] for e in c["entries"]) for c in result["categories"]):
                raise ValueError(f"Source ordering mismatch for {day}")
        if meta["source_mode"] == "wikitext":
            relevant, offset, _ = body(payload.decode("utf-8"), day)
            bullets = sum(bool(re.match(r"^\s*[*:]+", line)) for line in relevant.splitlines())
            represented = len(entries) + sum(bool(re.match(r"^\s*[*:]+", c.get("raw", ""))) for c in result["categories"])
            if bullets != represented and not result["warnings"]:
                raise ValueError(f"Unaccounted source bullets for {day}")
            source_lines = [index for index, line in enumerate(relevant.splitlines(), offset + 1) if re.match(r"^\s*[*:]+", line)]
            output_lines = [e["line"] for e in entries] + [c["line"] for c in result["categories"] if re.match(r"^\s*[*:]+", c.get("raw", ""))]
            if sorted(source_lines) != sorted(output_lines):
                raise ValueError(f"Source location coverage mismatch for {day}")
        else:
            bullets, represented = None, len(entries)
        from seed.wikipedia import parse_events_legacy
        trace = []
        replayed = parse_events_legacy(payload.decode("utf-8"), meta["page"], trace=trace) if meta["source_mode"] == "wikitext" else None
        old_categories = old.get("wikipedia", {}).get("categories", old.get("Intelligence_Payload", {}))
        legacy_count = sum(len(v) for v in replayed.values()) if replayed is not None else None
        events = sum(e["role"] == "event" for e in entries)
        topics = sum(e["role"] == "topic" for e in entries)
        unknown = sum(e["role"] == "unknown" for e in entries)
        mapped = {e["line"]: e["role"] for e in entries}
        mapped.update({c["line"]: "category" for c in result["categories"] if "line" in c})
        trace_roles = {role: 0 for role in ("event", "topic", "unknown", "category", "unmapped")}
        for item in trace:
            item["source_line"] = item["line"] + offset
            item["role"] = mapped.get(item["source_line"], "unmapped")
            trace_roles[item["role"]] += 1
        if trace_roles["unmapped"]:
            raise ValueError(f"Legacy event content cannot be located in source for {day}")
        parent_lines = {(ci, tuple(e["parent_path"])) for ci, c in enumerate(result["categories"]) for e in c["entries"] if e["parent_path"] is not None}
        leaves = sum(e["role"] == "event" and (ci, tuple(e["source_path"])) not in parent_lines for ci, c in enumerate(result["categories"]) for e in c["entries"])
        checks.append({"date": day, "source_bullets": bullets, "represented_bullets": represented,
                       "prior_flat_items": sum(len(v) for v in old_categories.values()),
                       "source_policy": "recorded_oldid" if old.get("source_page", {}).get("wikipedia_revision_id") is not None else "current_revision_as_new_input",
                       "legacy_replayed_items": legacy_count,
                       "baseline_matches_legacy_replay": replayed == old_categories,
                       "events": events, "topics": topics,
                       "event_leaves": leaves, "event_containers": events - leaves,
                       "unknown": unknown, "warnings": len(result["warnings"]),
                       "gdelt_preserved": result.get("gdelt") == old.get("gdelt"),
                       "delta_explanation": {
                           "legacy_items_by_candidate_role": trace_roles,
                           "legacy_mapping_sha256": fingerprint(json.dumps(trace, ensure_ascii=False, sort_keys=True)),
                           "events_not_emitted_by_legacy_parser": events - trace_roles["event"],
                           "baseline_item_delta_from_legacy_replay": sum(len(v) for v in old_categories.values()) - (legacy_count or 0),
                           "retained_bullets_by_role": {"event": events, "topic": topics, "unknown": unknown},
                           "category_bullets": represented - len(entries),
                           "legacy_omitted_bullets": bullets - legacy_count if legacy_count is not None else None,
                           "unrepresented_bullets": bullets - represented if bullets is not None else None,
                           "source_locations": "Every retained bullet has line, raw text and category/path in the candidate; ambiguous roles require review."}})
        prepared.append((day, result))
        if len(prepared) % 250 == 0:
            print(f"Prepared offline candidates: {len(prepared)}", flush=True)
    if unknown_override_days:
        raise ValueError(f"Overrides not applied to exact sources: {sorted(unknown_override_days)}")
    if missing and not args.cached_only:
        raise ValueError(f"Incomplete offline inputs: {len(missing)} days; first {missing[0]}. Acquire oldids or explicitly use --cached-only")
    output.mkdir(parents=True, exist_ok=True)
    for day, result in prepared:
        path = output / day[:4] / day[5:7] / (day + ".yaml")
        path.parent.mkdir(parents=True, exist_ok=True)
        write_if_changed(path, dump(result))
        write_if_changed(path.with_suffix(".warnings.jsonl"), "".join(json.dumps(w, ensure_ascii=False) + "\n" for w in result["warnings"]))
    report = {"complete": not missing, "requested_range": [str(args.start), str(args.end)],
              "verified_idempotence_and_round_trip": getattr(args, "verify", False),
              "generated": len(prepared), "missing": missing, "reconciliation": checks}
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Offline candidates: {len(prepared)}; missing inputs: {len(missing)}; report: {output / 'report.json'}")
    return 0
