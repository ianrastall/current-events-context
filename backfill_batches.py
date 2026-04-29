"""
Run local Wikipedia Current Events backfills in git-safe batches.

This script is intentionally local-first:

  1. Find missing or undersized dated YAML files.
  2. Fetch and write those files using the existing backfill parser.
  3. Optionally commit one batch at a time.
  4. Optionally push each commit after rebasing on the latest remote branch.

Examples
--------
Plan missing files, grouped by month:

  python backfill_batches.py plan --target missing --chunk month

Backfill one month locally without committing:

  python backfill_batches.py run --start 2026-04-01 --end 2026-04-30

Backfill missing files and commit each month, but do not push:

  python backfill_batches.py run --target missing --chunk month --commit

Backfill, commit, and push each month:

  python backfill_batches.py run --target missing --chunk month --commit --push

Use a GitHub token from the environment for HTTPS push auth:

  $env:GITHUB_TOKEN = "..."
  python backfill_batches.py run --commit --push --token-env GITHUB_TOKEN
"""

from __future__ import annotations

import argparse
import base64
import calendar
import csv
from html.parser import HTMLParser
import os
import re
import subprocess
import sys
import time
from collections import defaultdict
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from backfill_history import (
    USER_AGENT,
    candidate_titles,
    fetch_date_with_fallback,
    save,
)
import requests
from wiki_parser import parse_events


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_START_DATE = date(2002, 1, 1)
_session = requests.Session()


@dataclass(frozen=True)
class WorkItem:
    day: date
    path: Path
    reason: str
    size: int | None


@dataclass
class ProcessResult:
    saved: list[Path]
    skipped: int = 0
    missing: int = 0
    parse_failed: int = 0


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
    return REPO_ROOT / report_dir / f"backfill-{stamp}-{os.getpid()}.csv"


class MonthlyCurrentEventsParser(HTMLParser):
    def __init__(self, year: int, month: int):
        super().__init__(convert_charrefs=True)
        self.year = year
        self.month = month
        self.events_by_day: dict[int, list[str]] = defaultdict(list)
        self.region_day: int | None = None
        self.region_div_depth = 0
        self.content_div_depth = 0
        self.in_li = False
        self.li_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: value or "" for key, value in attrs}

        if tag == "div":
            classes = set(attr.get("class", "").split())
            if self.region_day is None and "current-events-main" in classes:
                day = self._day_from_label(attr.get("aria-label", ""))
                if day is not None:
                    self.region_day = day
                    self.region_div_depth = 1
                    self.content_div_depth = 0
                return

            if self.region_day is not None:
                self.region_div_depth += 1
                if {"current-events-content", "description"}.issubset(classes):
                    self.content_div_depth = 1
                elif self.content_div_depth:
                    self.content_div_depth += 1
                return

        if self.region_day is not None and self.content_div_depth and tag == "li":
            self.in_li = True
            self.li_parts = []

        if self.in_li and tag == "br":
            self.li_parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if self.in_li and tag == "li":
            text = self._clean_text("".join(self.li_parts))
            if text and self.region_day is not None:
                self.events_by_day[self.region_day].append(text)
            self.in_li = False
            self.li_parts = []
            return

        if self.region_day is not None and tag == "div":
            if self.content_div_depth:
                self.content_div_depth -= 1
            self.region_div_depth -= 1
            if self.region_div_depth <= 0:
                self.region_day = None
                self.region_div_depth = 0
                self.content_div_depth = 0

    def handle_data(self, data: str) -> None:
        if self.in_li:
            self.li_parts.append(data)

    @staticmethod
    def _clean_text(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _day_from_label(label: str) -> int | None:
        match = re.search(r"(\d{1,2})$", label.strip())
        if not match:
            return None
        return int(match.group(1))


def monthly_candidate_titles(year: int, month_name: str) -> list[str]:
    candidates = [
        f"Portal:Current events/{month_name} {year}",
        f"Portal:Current events/{year} {month_name}",
        f"Wikipedia:Current events/{month_name} {year}",
        f"Wikipedia:Current events/{year} {month_name}",
    ]
    seen: set[str] = set()
    unique: list[str] = []
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique


def fetch_rendered_html(page_title: str) -> str | None:
    params = {
        "action": "parse",
        "page": page_title,
        "prop": "text",
        "format": "json",
        "formatversion": "2",
        "redirects": "true",
    }

    try:
        response = _session.get(
            "https://en.wikipedia.org/w/api.php",
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=20,
        )
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", "60"))
            print(f"    monthly fallback was rate-limited; waiting {retry_after}s")
            time.sleep(min(retry_after, 600))
            return None
        response.raise_for_status()
        data = response.json()
        error = data.get("error")
        if error:
            return None
        return data.get("parse", {}).get("text")
    except requests.RequestException:
        return None


def load_monthly_events(
    year: int,
    month: int,
    month_name: str,
) -> tuple[str | None, dict[int, list[str]]]:
    for title in monthly_candidate_titles(year, month_name):
        html = fetch_rendered_html(title)
        if not html:
            continue

        parser = MonthlyCurrentEventsParser(year, month)
        parser.feed(html)
        if parser.events_by_day:
            return title, dict(parser.events_by_day)

    return None, {}


def monthly_fallback_for_day(
    day: date,
    cache: dict[tuple[int, int], tuple[str | None, dict[int, list[str]]]],
) -> tuple[str | None, dict[str, list[str]] | None]:
    key = (day.year, day.month)
    month_name = calendar.month_name[day.month]
    if key not in cache:
        cache[key] = load_monthly_events(day.year, day.month, month_name)

    title, events_by_day = cache[key]
    events = events_by_day.get(day.day, [])
    if not title or not events:
        return title, None

    source_title = f"{title}#{day.year}_{month_name}_{day.day}"
    return source_title, {"Uncategorized": events}


def parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"{value!r} is not a valid YYYY-MM-DD date"
        ) from exc


def iter_days(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def output_path(day: date) -> Path:
    return REPO_ROOT / f"{day.year}" / f"{day.month:02d}" / f"{day}.yaml"


def discover_work(
    *,
    start: date,
    end: date,
    target: str,
    max_bytes: int,
) -> list[WorkItem]:
    items: list[WorkItem] = []

    for day in iter_days(start, end):
        path = output_path(day)
        exists = path.exists()
        size = path.stat().st_size if exists else None

        if not exists and target in {"missing", "missing-or-under-size"}:
            items.append(WorkItem(day, path, "missing", None))
        elif (
            exists
            and size is not None
            and size < max_bytes
            and target in {"under-size", "missing-or-under-size"}
        ):
            items.append(WorkItem(day, path, f"under-size<{max_bytes}", size))

    return items


def chunk_key(day: date, chunk: str) -> tuple[int, int, int]:
    if chunk == "day":
        return (day.year, day.month, day.day)
    if chunk == "month":
        return (day.year, day.month, 0)
    if chunk == "year":
        return (day.year, 0, 0)
    raise ValueError(f"unsupported chunk: {chunk}")


def chunk_label(key: tuple[int, int, int], chunk: str) -> str:
    year, month, day = key
    if chunk == "day":
        return f"{year:04d}-{month:02d}-{day:02d}"
    if chunk == "month":
        return f"{year:04d}-{month:02d}"
    if chunk == "year":
        return f"{year:04d}"
    raise ValueError(f"unsupported chunk: {chunk}")


def group_items(items: list[WorkItem], chunk: str) -> list[tuple[str, list[WorkItem]]]:
    grouped: dict[tuple[int, int, int], list[WorkItem]] = defaultdict(list)
    for item in items:
        grouped[chunk_key(item.day, chunk)].append(item)

    result = []
    for key in sorted(grouped):
        result.append((chunk_label(key, chunk), sorted(grouped[key], key=lambda x: x.day)))
    return result


def git(args: list[str], *, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if check and completed.returncode != 0:
        output = ((completed.stdout or "") + (completed.stderr or "")).strip()
        raise RuntimeError(f"git {' '.join(args)} failed:\n{output}")
    return completed


def require_clean_worktree() -> None:
    status = git(["status", "--porcelain"], capture=True).stdout.strip()
    if status:
        raise RuntimeError(
            "Working tree is not clean. Commit, stash, or discard unrelated changes "
            "before running with --commit or --push."
        )


def current_branch() -> str:
    return git(["rev-parse", "--abbrev-ref", "HEAD"], capture=True).stdout.strip()


def sync_latest(branch: str) -> None:
    git(["fetch", "origin", branch], capture=False)
    git(["rebase", f"origin/{branch}"], capture=False)


def token_push_args(branch: str, token_env: str | None) -> list[str]:
    args = []
    if token_env:
        token = os.environ.get(token_env)
        if not token:
            raise RuntimeError(f"--token-env {token_env!r} was set, but the variable is empty")
        raw_auth = f"x-access-token:{token}".encode("utf-8")
        encoded_auth = base64.b64encode(raw_auth).decode("ascii")
        args.extend([
            "-c",
            f"http.https://github.com/.extraheader=AUTHORIZATION: basic {encoded_auth}",
        ])
    args.extend(["push", "origin", f"HEAD:{branch}"])
    return args


def push_with_retry(branch: str, token_env: str | None, attempts: int) -> None:
    last_output = ""
    for attempt in range(1, attempts + 1):
        sync_latest(branch)
        completed = git(token_push_args(branch, token_env), check=False, capture=True)
        if completed.returncode == 0:
            print(f"  pushed HEAD:{branch}")
            return

        last_output = ((completed.stdout or "") + (completed.stderr or "")).strip()
        print(f"  push attempt {attempt}/{attempts} failed; rebasing and retrying")
        if attempt < attempts:
            time.sleep(attempt * 5)

    raise RuntimeError(f"push failed after {attempts} attempts:\n{last_output}")


def git_changed_paths(paths: list[Path]) -> list[Path]:
    if not paths:
        return []
    rels = [str(path.relative_to(REPO_ROOT)) for path in paths]
    completed = git(["status", "--porcelain", "--", *rels], capture=True)
    changed: list[Path] = []
    for line in completed.stdout.splitlines():
        if len(line) >= 4:
            changed.append(REPO_ROOT / line[3:].strip())
    return changed


def commit_paths(paths: list[Path], message: str) -> bool:
    changed = git_changed_paths(paths)
    if not changed:
        print("  no git changes in this batch; skipping commit")
        return False

    rels = [str(path.relative_to(REPO_ROOT)) for path in changed]
    git(["add", "--", *rels], capture=False)
    staged = git(["diff", "--staged", "--quiet"], check=False, capture=True)
    if staged.returncode == 0:
        print("  no staged changes in this batch; skipping commit")
        return False

    git(["commit", "-m", message], capture=False)
    return True


def process_items(
    items: list[WorkItem],
    *,
    batch: str,
    overwrite: bool,
    report: RunReport | None,
) -> ProcessResult:
    result = ProcessResult(saved=[])
    monthly_cache: dict[tuple[int, int], tuple[str | None, dict[int, list[str]]]] = {}

    for item in items:
        size_before = item.path.stat().st_size if item.path.exists() else None

        if item.path.exists() and not overwrite:
            result.skipped += 1
            if report:
                report.write(
                    batch=batch,
                    item=item,
                    status="skipped_existing",
                    size_before=size_before,
                    size_after=size_before,
                )
            continue

        month_name = calendar.month_name[item.day.month]
        print(f"  fetching {item.day} ({item.reason})")

        wikitext, used_title = fetch_date_with_fallback(
            item.day.year,
            month_name,
            item.day.day,
        )
        if not wikitext or not used_title:
            monthly_title, monthly_events = monthly_fallback_for_day(item.day, monthly_cache)
            if monthly_events:
                save(item.day, monthly_title or "", monthly_events)
                size_after = item.path.stat().st_size if item.path.exists() else None
                result.saved.append(item.path)
                print(f"    wrote {item.path.relative_to(REPO_ROOT)} from monthly archive")
                if report:
                    report.write(
                        batch=batch,
                        item=item,
                        status="written_monthly_fallback",
                        source_title=monthly_title or "",
                        size_before=size_before,
                        size_after=size_after,
                    )
                continue

            result.missing += 1
            print(f"    no content found for {item.day}")
            if report:
                tried = "; ".join(candidate_titles(item.day.year, month_name, item.day.day))
                monthly = "; ".join(monthly_candidate_titles(item.day.year, month_name))
                report.write(
                    batch=batch,
                    item=item,
                    status="missing",
                    size_before=size_before,
                    message=(
                        f"No daily candidate returned content. Tried: {tried}. "
                        f"Monthly fallback candidates checked: {monthly}. "
                        f"Matched monthly page: {monthly_title or ''}"
                    ),
                )
            continue

        events_data = parse_events(wikitext, used_title)
        if not events_data:
            monthly_title, monthly_events = monthly_fallback_for_day(item.day, monthly_cache)
            if monthly_events:
                save(item.day, monthly_title or "", monthly_events)
                size_after = item.path.stat().st_size if item.path.exists() else None
                result.saved.append(item.path)
                print(f"    wrote {item.path.relative_to(REPO_ROOT)} from monthly archive")
                if report:
                    report.write(
                        batch=batch,
                        item=item,
                        status="written_monthly_fallback_after_parse_failed",
                        source_title=monthly_title or "",
                        size_before=size_before,
                        size_after=size_after,
                    )
                continue

            result.parse_failed += 1
            print(f"    parser returned no events for {item.day}")
            if report:
                report.write(
                    batch=batch,
                    item=item,
                    status="parse_failed",
                    source_title=used_title,
                    size_before=size_before,
                    message="Wikitext was fetched, but parse_events returned no events.",
                )
            continue

        before = item.path.read_text(encoding="utf-8") if item.path.exists() else None
        save(item.day, used_title, events_data)
        after = item.path.read_text(encoding="utf-8") if item.path.exists() else None
        size_after = item.path.stat().st_size if item.path.exists() else None

        if before != after:
            result.saved.append(item.path)
            print(f"    wrote {item.path.relative_to(REPO_ROOT)}")
            if report:
                report.write(
                    batch=batch,
                    item=item,
                    status="written",
                    source_title=used_title,
                    size_before=size_before,
                    size_after=size_after,
                )
        else:
            result.skipped += 1
            print("    unchanged")
            if report:
                report.write(
                    batch=batch,
                    item=item,
                    status="unchanged",
                    source_title=used_title,
                    size_before=size_before,
                    size_after=size_after,
                )

    return result


def print_plan(groups: list[tuple[str, list[WorkItem]]]) -> None:
    total = sum(len(items) for _, items in groups)
    print(f"Planned batches: {len(groups)}")
    print(f"Planned dates:   {total}")
    for label, items in groups:
        reasons = defaultdict(int)
        for item in items:
            reasons[item.reason] += 1
        reason_text = ", ".join(f"{reason}={count}" for reason, count in sorted(reasons.items()))
        first = items[0].day
        last = items[-1].day
        print(f"  {label}: {len(items)} date(s), {first}..{last}, {reason_text}")


def run_plan(args: argparse.Namespace) -> int:
    items = discover_work(
        start=args.start,
        end=args.end,
        target=args.target,
        max_bytes=args.max_bytes,
    )
    groups = group_items(items, args.chunk)
    if args.limit_chunks is not None:
        groups = groups[: args.limit_chunks]
    print_plan(groups)
    return 0


def run_backfill(args: argparse.Namespace) -> int:
    if args.push and not args.commit:
        raise RuntimeError("--push requires --commit")

    if args.commit:
        require_clean_worktree()
        branch = current_branch()
        if branch != args.branch and not args.allow_other_branch:
            raise RuntimeError(
                f"Current branch is {branch!r}, but --branch is {args.branch!r}. "
                "Switch branches or pass --allow-other-branch deliberately."
            )
        sync_latest(args.branch)

    items = discover_work(
        start=args.start,
        end=args.end,
        target=args.target,
        max_bytes=args.max_bytes,
    )
    groups = group_items(items, args.chunk)
    if args.limit_chunks is not None:
        groups = groups[: args.limit_chunks]

    print_plan(groups)
    if not groups:
        return 0

    overwrite = args.target in {"under-size", "missing-or-under-size"}
    totals = ProcessResult(saved=[])
    report_file = None if args.no_report else report_path(args.report_dir)
    report_context = RunReport(report_file) if report_file else None

    if report_file:
        print(f"Report: {report_file.relative_to(REPO_ROOT)}")
    print("Detailed fetch log: backfill.log")

    with report_context if report_context else nullcontext():
        for label, batch_items in groups:
            print(f"\nBatch {label}: {len(batch_items)} date(s)")
            result = process_items(
                batch_items,
                batch=label,
                overwrite=overwrite,
                report=report_context,
            )
            totals.saved.extend(result.saved)
            totals.skipped += result.skipped
            totals.missing += result.missing
            totals.parse_failed += result.parse_failed

            if args.commit:
                message = f"Backfill current events {label}"
                committed = commit_paths(result.saved, message)
                if committed and args.push:
                    push_with_retry(args.branch, args.token_env, args.push_attempts)

    print("\nDone")
    print(f"  wrote/changed: {len(totals.saved)}")
    print(f"  skipped:       {totals.skipped}")
    print(f"  missing:       {totals.missing}")
    print(f"  parse failed:  {totals.parse_failed}")
    return 0


def add_common_args(parser: argparse.ArgumentParser) -> None:
    today = datetime.now(timezone.utc).date()
    parser.add_argument("--start", type=parse_iso_date, default=DEFAULT_START_DATE)
    parser.add_argument("--end", type=parse_iso_date, default=today)
    parser.add_argument(
        "--target",
        choices=["missing", "under-size", "missing-or-under-size"],
        default="missing",
        help="Which dates to process. Default: missing.",
    )
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=500,
        help="Size threshold for --target under-size or missing-or-under-size.",
    )
    parser.add_argument(
        "--chunk",
        choices=["day", "month", "year"],
        default="month",
        help="Commit/planning batch size. Default: month.",
    )
    parser.add_argument(
        "--limit-chunks",
        type=int,
        default=None,
        help="Only process the first N planned chunks.",
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan and run local backfill batches without relying on GitHub Actions."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan", help="Show planned batches only.")
    add_common_args(plan)
    plan.set_defaults(func=run_plan)

    run = subparsers.add_parser("run", help="Fetch/write batches locally.")
    add_common_args(run)
    run.add_argument("--commit", action="store_true", help="Commit each changed batch.")
    run.add_argument("--push", action="store_true", help="Push after each commit.")
    run.add_argument("--branch", default="main", help="Remote branch to rebase/push. Default: main.")
    run.add_argument(
        "--allow-other-branch",
        action="store_true",
        help="Allow committing from a local branch whose name differs from --branch.",
    )
    run.add_argument(
        "--push-attempts",
        type=int,
        default=3,
        help="Push retry count. Default: 3.",
    )
    run.add_argument(
        "--token-env",
        default=None,
        help="Environment variable containing a GitHub token for HTTPS push auth.",
    )
    run.add_argument(
        "--report-dir",
        type=Path,
        default=Path(".backfill-reports"),
        help="Directory for per-run CSV reports. Default: .backfill-reports.",
    )
    run.add_argument(
        "--no-report",
        action="store_true",
        help="Do not write a per-run CSV report.",
    )
    run.set_defaults(func=run_backfill)

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
