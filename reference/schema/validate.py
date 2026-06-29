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
        return ["(skipped JSON Schema check: `pip install jsonschema` to enable)"]
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    v = Draft202012Validator(schema)
    out = []
    for e in sorted(v.iter_errors(doc), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in e.path) or "(root)"
        out.append(f"{loc}: {e.message}")
    return out


def cross_ref_errors(doc):
    errs = []
    date = doc.get("date", "")
    events = doc.get("events", []) or []

    expected = 1
    for e in events:
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

    def check_refs(refs, where):
        for r in refs or []:
            if r not in valid:
                errs.append(f"{where}: citation_ref {r} has no works_cited entry")

    for e in events:
        for kd in e.get("key_data", []) or []:
            check_refs(kd.get("citation_refs"), f"{e.get('id')} key_data[{kd.get('label')!r}]")
        for s in e.get("sources", {}).get("external", []) or []:
            check_refs(s.get("citation_refs"), f"{e.get('id')} source {s.get('id')}")
    return errs


def validate(path):
    doc = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    errs = schema_errors(doc) + cross_ref_errors(doc)
    real = [e for e in errs if not e.startswith("(skipped")]
    skipped = [e for e in errs if e.startswith("(skipped")]
    for s in skipped:
        print(f"  note: {s}")
    if real:
        print(f"FAIL  {path}  ({len(real)} issue(s))")
        for e in real:
            print(f"    - {e}")
        return False
    n = len(doc.get("events", []))
    print(f"OK    {path}  ({n} events, {len(doc.get('works_cited', []))} works cited)")
    return True


def main(argv):
    if not argv:
        sys.exit(__doc__)
    ok = all(validate(p) for p in argv)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main(sys.argv[1:])
