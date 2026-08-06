"""
seed.report — per-run CSV report for the `range` command.

Carried over unchanged from backfill_batches.py.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from seed.merge import REPO_ROOT


@dataclass(frozen=True)
class WorkItem:
    day: date
    path: Path
    reason: str
    size: int | None


class RunReport:
    fields = [
        "timestamp_utc",
        "batch",
        "date",
        "path",
        "reason",
        "status",
        "source_title",
        "size_before",
        "size_after",
        "message",
    ]

    def __init__(self, path: Path):
        self.path = path
        self.file = None
        self.writer = None

    def __enter__(self) -> "RunReport":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("w", encoding="utf-8", newline="")
        self.writer = csv.DictWriter(self.file, fieldnames=self.fields)
        self.writer.writeheader()
        self.file.flush()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.file:
            self.file.close()

    def write(
        self,
        *,
        batch: str,
        item: WorkItem,
        status: str,
        source_title: str = "",
        size_before: int | None = None,
        size_after: int | None = None,
        message: str = "",
    ) -> None:
        if not self.writer or not self.file:
            return
        self.writer.writerow(
            {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "batch": batch,
                "date": item.day.isoformat(),
                "path": str(item.path.relative_to(REPO_ROOT)),
                "reason": item.reason,
                "status": status,
                "source_title": source_title,
                "size_before": "" if size_before is None else size_before,
                "size_after": "" if size_after is None else size_after,
                "message": message,
            }
        )
        self.file.flush()


def report_path(report_dir: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f-utc")
    return REPO_ROOT / report_dir / f"seed-run-{stamp}-{os.getpid()}.csv"
