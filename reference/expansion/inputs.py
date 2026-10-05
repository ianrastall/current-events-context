"""Explicit, hash-guarded synthesis inputs. No network access."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = Path(__file__).with_name("inputs.json")


def digest(path, *, text=False):
    payload = Path(path).read_bytes()
    if text:
        payload = payload.replace(b"\r\n", b"\n")
    return hashlib.sha256(payload).hexdigest()


def resolve(relative):
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError(f"Input escapes repository: {relative}")
    return path


def selection(date):
    records = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if date not in records:
        raise ValueError(f"No explicit input for {date}; register it with inputs.py")
    record = records[date]
    report = resolve(record["report"])
    if digest(report, text=True) != record["report_sha256"]:
        raise ValueError(f"Research input drift for {date}: {report.name}")
    if record["mode"] == "authored_snapshot":
        snapshot = resolve(record["snapshot"])
        if digest(snapshot) != record["snapshot_sha256"]:
            raise ValueError(f"Authored snapshot drift for {date}")
    elif record["mode"] != "build":
        raise ValueError(f"Unsupported input mode for {date}")
    return record


def register(date, report):
    from datetime import date as Date
    Date.fromisoformat(date)
    path = Path(report).resolve()
    if not path.is_relative_to(ROOT / "reference" / "deep-research"):
        raise ValueError("Report must live under reference/deep-research")
    if not path.stem.startswith(date):
        raise ValueError("Report filename must start with its ISO date")
    records = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if date in records:
        raise ValueError("Input already registered; review a manifest change explicitly")
    records[date] = {"mode": "build", "report": path.relative_to(ROOT).as_posix(),
                     "report_sha256": digest(path, text=True)}
    MANIFEST.write_text(json.dumps(dict(sorted(records.items())), ensure_ascii=False,
                                   indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("date")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    register(args.date, args.report)
