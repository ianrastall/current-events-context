"""Guarded corrections to authored synthesis, located by event ID and hash."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

import yaml
import inputs

HERE = Path(__file__).resolve().parent


def event_hash(event):
    return hashlib.sha256(json.dumps(event, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def locator(date, event_id):
    selected = inputs.selection(date)
    if selected["mode"] != "authored_snapshot":
        raise ValueError("Authored correction requires an authored snapshot")
    doc = yaml.safe_load(inputs.resolve(selected["snapshot"]).read_bytes())
    events = [e for e in doc["events"] if e["id"] == event_id] if event_id else [doc]
    if len(events) != 1:
        raise ValueError("Event ID must identify exactly one authored event")
    return {"date": date, "snapshot_sha256": selected["snapshot_sha256"],
            "report_sha256": selected["report_sha256"], "event_id": event_id,
            "event_sha256": event_hash(events[0]), "reason": "", "patch": {}}


def merge(target, patch):
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            merge(target[key], value)
        else:
            target[key] = copy.deepcopy(value)


def apply(doc, selected, records):
    result = copy.deepcopy(doc)
    seen = set()
    for record in records:
        if (record["date"] != doc["date"] or record["snapshot_sha256"] != selected["snapshot_sha256"]
                or record["report_sha256"] != selected["report_sha256"]):
            raise ValueError("Authored correction source drift")
        key = record["event_id"]
        if key in seen:
            raise ValueError("Combine corrections to one event into a single guarded patch")
        seen.add(key)
        events = [e for e in result["events"] if e["id"] == key] if key else [result]
        if len(events) != 1 or event_hash(events[0]) != record["event_sha256"]:
            raise ValueError("Authored correction event drift")
        if not record["reason"].strip() or not record["patch"] or "id" in record["patch"]:
            raise ValueError("Correction needs a reason and nonempty patch preserving event ID")
        if key is None and set(record["patch"]) - {"works_cited", "analytical_overview", "strategic_conclusion", "events"}:
            raise ValueError("Document correction may only change synthesis prose, bibliography or events")
        if key is None and len(records) != 1:
            raise ValueError("A document correction must combine all changes under one snapshot guard")
        merge(events[0], record["patch"])
    if records:
        result["dataset"]["compiler"]["status"] = "draft"
        result["dataset"]["compiler"]["reviewed"] = False
        result["dataset"]["compiler"]["mode"] = "llm_deep_research_broad_snapshot"
    return result


def path(date):
    return HERE / "authored-overlays" / (date + ".json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("date")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--event-id")
    target.add_argument("--document", action="store_true")
    args = parser.parse_args()
    print(json.dumps(locator(args.date, args.event_id), ensure_ascii=False, indent=2))
