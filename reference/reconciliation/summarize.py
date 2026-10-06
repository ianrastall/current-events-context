"""Summarize a completed side-by-side offline replay without modifying inputs."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path


def summarize(candidate_root, destination):
    root, output = Path(candidate_root), Path(destination)
    report_bytes = (root / "report.json").read_bytes()
    report = json.loads(report_bytes)
    checks = report["reconciliation"]
    counts, samples, unresolved = Counter(), defaultdict(list), []
    for path in sorted(root.glob("20*/*/*.warnings.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            warning = json.loads(line)
            counts[warning["code"]] += 1
            if len(samples[warning["code"]]) < 5:
                samples[warning["code"]].append(warning)
            if warning["interpretation"] == "unknown" and not warning.get("resolution"):
                unresolved.append(warning)
    totals = {key: sum(c[key] or 0 for c in checks) for key in (
        "source_bullets", "represented_bullets", "prior_flat_items", "legacy_replayed_items",
        "events", "topics", "event_leaves", "event_containers", "unknown", "warnings")}
    mismatch = [c["date"] for c in checks if not c["baseline_matches_legacy_replay"]]
    summary = {
        "schema": "extraction-1.0", "generated": report["generated"], "complete": report["complete"],
        "missing": report["missing"], "report_sha256": hashlib.sha256(report_bytes).hexdigest(),
        "verified_idempotence_and_round_trip": report["verified_idempotence_and_round_trip"],
        "totals": totals, "warning_counts": dict(sorted(counts.items())),
        "source_coverage_passed": all(c["source_bullets"] == c["represented_bullets"] for c in checks),
        "gdelt_preserved": all(c["gdelt_preserved"] for c in checks),
        "legacy_items_unmapped": sum(c["delta_explanation"]["legacy_items_by_candidate_role"]["unmapped"] for c in checks),
        "baseline_replay_mismatch_dates": mismatch,
        "new_current_capture_dates": [c["date"] for c in checks if c["source_policy"] == "current_revision_as_new_input"],
        "flat_count_changed_dates": sum(c["prior_flat_items"] != c["events"] for c in checks),
        "interpretation": "Role promotion, colon-list recovery and legacy omissions are mapped per date in extraction-report.json. For new captures, baseline differences also include revision changes. Unknown roles remain unresolved; candidate generation does not approve public replacement."
    }
    output.mkdir(parents=True, exist_ok=True)
    artifacts = {"extraction-summary.json": summary,
                 "warnings-summary.json": {"counts": dict(sorted(counts.items())), "samples": samples},
                 "unresolved-roles.json": unresolved}
    for name, doc in artifacts.items():
        (output / name).write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    (output / "extraction-report.json").write_bytes(report_bytes)
    print(json.dumps({"generated": report["generated"], "missing": len(report["missing"]), "totals": totals,
                      "warning_counts": dict(sorted(counts.items())), "unresolved": len(unresolved), "baseline_mismatches": len(mismatch)}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate_root", type=Path)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    summarize(args.candidate_root, args.output)
