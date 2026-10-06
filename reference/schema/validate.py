#!/usr/bin/env python3
"""Validate a daily events YAML file against the schema-2.2 contract.

Usage:
    python reference/schema/validate.py <path-to-day.yaml> [more.yaml ...]

Checks:
  1. JSON Schema conformance (reference/schema/daily-events.schema.json),
     if the `jsonschema` package is installed.
  2. Cross-reference rules the schema can't express:
       - event ids are sequential evt-DATE-001, -002, ... matching the file date
       - every citation_refs integer resolves to a works_cited id
       - works_cited ids are unique
Exit code is non-zero if any file fails.
"""
import json
import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")

SCHEMA_PATH = Path(__file__).with_name("daily-events.schema.json")


def schema_errors(doc):
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        return ["JSON Schema validation requires jsonschema; install requirements.txt"]
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    v = Draft202012Validator(schema)
    out = []
    for e in sorted(v.iter_errors(doc), key=lambda e: tuple(str(p) for p in e.path)):
        loc = "/".join(str(p) for p in e.path) or "(root)"
        out.append(f"{loc}: {e.message}")
    return out


def cross_ref_errors(doc):
    if not isinstance(doc, dict):
        return ["Document must be an object"]
    errs = []
    date = doc.get("date", "")
    events = doc.get("events", []) or []

    expected = 1
    for e in events:
        if not isinstance(e, dict):
            errs.append("Event must be an object")
            continue
        want = f"evt-{date}-{expected:03d}"
        if e.get("id") != want:
            errs.append(f"event #{expected}: id is {e.get('id')!r}, expected {want!r}")
        if e.get("time", {}).get("date") not in (date, None):
            errs.append(f"{e.get('id')}: time.date {e['time']['date']!r} != file date {date!r}")
        expected += 1

    work_ids = [w.get("id") for w in doc.get("works_cited", []) or []]
    if len(work_ids) != len(set(work_ids)):
        errs.append("works_cited contains duplicate ids")
    valid = set(work_ids)
    urls = {w.get("id"): w.get("url") for w in doc.get("works_cited", []) or []}

    def check_refs(refs, where):
        for r in refs or []:
            if r not in valid:
                errs.append(f"{where}: citation_ref {r} has no works_cited entry")

    for e in events:
        if not isinstance(e, dict):
            continue
        for kd in e.get("key_data", []) or []:
            check_refs(kd.get("citation_refs"), f"{e.get('id')} key_data[{kd.get('label')!r}]")
        for s in e.get("sources", {}).get("external", []) or []:
            check_refs(s.get("citation_refs"), f"{e.get('id')} source {s.get('id')}")
            if not any(urls.get(ref) == s.get("url") for ref in s.get("citation_refs", [])):
                errs.append(f"{e.get('id')} source {s.get('id')}: bibliography refs do not identify the cited URL")
    return errs


def related_errors(doc, archive_root):
    errors = []
    loaded = {}
    for event in doc.get("events", []):
        for ref in event.get("related_events", []):
            match = re.fullmatch(r"evt-(\d{4})-(\d{2})-(\d{2})-\d{3}", ref)
            if not match:
                errors.append(f"Invalid related event id: {ref}")
                continue
            year, month, day = match.groups()
            date = f"{year}-{month}-{day}"
            if date not in loaded:
                p = Path(archive_root) / year / month / (date + ".yaml")
                try:
                    other = yaml.safe_load(p.read_text(encoding="utf-8"))
                    loaded[date] = {e["id"] for e in other["events"]}
                except (OSError, yaml.YAMLError, KeyError, TypeError):
                    loaded[date] = set()
            if ref not in loaded[date]:
                errors.append(f"{event['id']}: unresolved related_events id {ref}")
    return errors


def validate(path, archive_root=None):
    try:
        doc = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        errors = schema_errors(doc)
        # Cross-reference checks require schema-shaped data.
        if not errors:
            errors += cross_ref_errors(doc)
            if archive_root is not None:
                errors += related_errors(doc, archive_root)
    except (OSError, yaml.YAMLError, TypeError, KeyError, AttributeError) as exc:
        errors = [str(exc)]
    if errors:
        print(f"FAIL  {path}  ({len(errors)} issue(s))")
        for e in errors:
            print(f"    - {e}")
        return False
    n = len(doc.get("events", []))
    print(f"OK    {path}  ({n} events, {len(doc.get('works_cited', []))} works cited)")
    return True


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", type=Path)
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args(argv)
    ok = all([validate(p, args.archive_root) for p in args.paths])
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main(sys.argv[1:])
