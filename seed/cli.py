"""
seed.cli — `python -m seed <date|range|plan|cache|reparse> ...`

Replaces update_data.py (daily cron), backfill_history.py (bulk forward/
backward CLI), and backfill_batches.py (git-aware batch runner) with one
CLI. See HANDOFF.md, Stage 0.

    seed date [DATE]              fetch one day (default: yesterday UTC).
                                   Overwrites by default — this is the cron
                                   entrypoint, always regenerating the target day.

    seed plan START END [opts]    dry-run: list which dates a `range` run
                                   would touch, grouped into commit-sized chunks.

    seed range START END [opts]   fetch a date range. Skips existing files by
                                   default (resume-safe bulk/backfill mode).
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from seed.gdelt import build_gdelt_block, fetch_gdelt_articles
from seed.gitops import commit_paths, current_branch, require_clean_worktree, sync_latest
from seed.merge import already_saved, build_seed_doc, output_path, save, should_query_gdelt
from seed.report import RunReport, WorkItem, report_path
from seed.wikipedia import MonthlyCache, WikiDayResult, fetch_day

USER_AGENT = "current-events-context-seed/1.0 (https://github.com/ianrastall/current-events-context)"

log = logging.getLogger(__name__)


def _configure_logging(log_file: str, *, console: bool) -> None:
    handlers: list[logging.Handler] = [logging.FileHandler(log_file, encoding="utf-8")]
    if console:
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.DEBUG if not console else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
        force=True,
    )


def parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{value!r} is not a valid YYYY-MM-DD date") from exc


# ---------------------------------------------------------------------------
# Shared: fetch one day (Wikipedia + optional GDELT) and save it
# ---------------------------------------------------------------------------

def fetch_and_save_day(
    day: date, *, no_gdelt: bool, monthly_cache: MonthlyCache
) -> tuple[bool, str, dict]:
    """
    Returns (success, source_title_or_reason, info) where info carries
    extra detail for reporting (e.g. gdelt article count).
    """
    wiki_result: WikiDayResult | None = fetch_day(
        day.year, day.month, day.day, USER_AGENT, monthly_cache=monthly_cache
    )
    if wiki_result is None:
        return False, "", {"reason": "no wikipedia content (daily + monthly fallback exhausted)"}

    gdelt_block = None
    if not no_gdelt and should_query_gdelt(day):
        articles = fetch_gdelt_articles(day.isoformat())
        if articles is not None:
            gdelt_block = build_gdelt_block(articles)
        else:
            log.warning("GDELT fetch failed for %s — seed file will omit the gdelt block.", day)

    doc = build_seed_doc(
        day=day,
        source_title=wiki_result.source_title,
        revision_id=wiki_result.revision_id,
        categories=wiki_result.categories,
        gdelt_block=gdelt_block,
    )
    if wiki_result.source_meta is not None:
        from seed.source import capture
        capture(day.isoformat(), wiki_result.source_meta)
    if wiki_result.archive is not None:
        from seed.replay import save_capture
        save_capture(day.isoformat(), wiki_result.archive, gdelt_block)
    save(day, doc)
    return True, wiki_result.source_title, {
        "revision_id": wiki_result.revision_id,
        "gdelt_articles": gdelt_block["article_count"] if gdelt_block else 0,
    }


# ---------------------------------------------------------------------------
# `date` command
# ---------------------------------------------------------------------------

def run_date(args: argparse.Namespace) -> int:
    _configure_logging("update.log", console=True)

    target_date = args.date or (datetime.now(timezone.utc).date() - timedelta(days=1))

    if not args.overwrite and already_saved(target_date):
        log.info("Already saved, skipping (use --overwrite to force): %s", target_date)
        return 0

    log.info("Processing: %s", target_date)
    ok, source_title, info = fetch_and_save_day(target_date, no_gdelt=args.no_gdelt, monthly_cache={})

    if not ok:
        log.warning("No data found for %s (%s)", target_date, info.get("reason"))
        return 1

    log.info(
        "Saved %s (source=%s, revision_id=%s, gdelt_articles=%d)",
        output_path(target_date), source_title, info["revision_id"], info["gdelt_articles"],
    )
    return 0


# ---------------------------------------------------------------------------
# `plan` / `range` commands
# ---------------------------------------------------------------------------

def iter_days(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def discover_work(*, start: date, end: date, target: str, max_bytes: int) -> list[WorkItem]:
    items: list[WorkItem] = []
    for day in iter_days(start, end):
        path = output_path(day)
        exists = path.exists()
        size = path.stat().st_size if exists else None

        if target == "all":
            items.append(WorkItem(day, path, "all", size))
        elif not exists and target in {"missing", "missing-or-under-size"}:
            items.append(WorkItem(day, path, "missing", None))
        elif (
            exists and size is not None and size < max_bytes
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
    return f"{year:04d}"


def group_items(items: list[WorkItem], chunk: str) -> list[tuple[str, list[WorkItem]]]:
    grouped: dict[tuple[int, int, int], list[WorkItem]] = defaultdict(list)
    for item in items:
        grouped[chunk_key(item.day, chunk)].append(item)
    return [
        (chunk_label(key, chunk), sorted(grouped[key], key=lambda x: x.day))
        for key in sorted(grouped)
    ]


def print_plan(groups: list[tuple[str, list[WorkItem]]]) -> None:
    total = sum(len(items) for _, items in groups)
    print(f"Planned batches: {len(groups)}")
    print(f"Planned dates:   {total}")
    for label, items in groups:
        reasons: dict[str, int] = defaultdict(int)
        for item in items:
            reasons[item.reason] += 1
        reason_text = ", ".join(f"{reason}={count}" for reason, count in sorted(reasons.items()))
        print(f"  {label}: {len(items)} date(s), {items[0].day}..{items[-1].day}, {reason_text}")


def run_plan(args: argparse.Namespace) -> int:
    items = discover_work(start=args.start, end=args.end, target=args.target, max_bytes=args.max_bytes)
    groups = group_items(items, args.chunk)
    if args.limit_chunks is not None:
        groups = groups[: args.limit_chunks]
    print_plan(groups)
    return 0


@dataclass
class ProcessResult:
    saved: list[Path]
    skipped: int = 0
    missing: int = 0
    acquisition_paths: list[Path] | None = None


def process_items(
    items: list[WorkItem], *, batch: str, report: RunReport | None, no_gdelt: bool, monthly_cache: MonthlyCache
) -> ProcessResult:
    result = ProcessResult(saved=[], acquisition_paths=[])

    for item in items:
        size_before = item.path.stat().st_size if item.path.exists() else None
        before = item.path.read_text(encoding="utf-8") if item.path.exists() else None

        print(f"  fetching {item.day} ({item.reason})")
        ok, source_title, info = fetch_and_save_day(item.day, no_gdelt=no_gdelt, monthly_cache=monthly_cache)

        if not ok:
            result.missing += 1
            print(f"    no content found for {item.day}")
            if report:
                report.write(batch=batch, item=item, status="missing", size_before=size_before, message=info.get("reason", ""))
            continue

        after = item.path.read_text(encoding="utf-8") if item.path.exists() else None
        size_after = item.path.stat().st_size if item.path.exists() else None
        from seed.source import capture_paths
        result.acquisition_paths.extend(capture_paths(item.day.isoformat()))

        if before != after:
            result.saved.append(item.path)
            print(f"    wrote {item.path}")
            if report:
                report.write(
                    batch=batch, item=item, status="written", source_title=source_title,
                    size_before=size_before, size_after=size_after,
                )
        else:
            result.skipped += 1
            print("    unchanged")
            if report:
                report.write(
                    batch=batch, item=item, status="unchanged", source_title=source_title,
                    size_before=size_before, size_after=size_after,
                )

    return result


def run_range(args: argparse.Namespace) -> int:
    _configure_logging("backfill.log", console=False)

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

    items = discover_work(start=args.start, end=args.end, target=args.target, max_bytes=args.max_bytes)
    groups = group_items(items, args.chunk)
    if args.limit_chunks is not None:
        groups = groups[: args.limit_chunks]

    print_plan(groups)
    if not groups:
        return 0

    monthly_cache: MonthlyCache = {}
    totals = ProcessResult(saved=[])
    report_file = None if args.no_report else report_path(args.report_dir)
    report_context = RunReport(report_file) if report_file else None

    if report_file:
        print(f"Report: {report_file}")
    print("Detailed fetch log: backfill.log")

    with report_context if report_context else nullcontext():
        for label, batch_items in groups:
            print(f"\nBatch {label}: {len(batch_items)} date(s)")
            result = process_items(
                batch_items, batch=label, report=report_context,
                no_gdelt=args.no_gdelt, monthly_cache=monthly_cache,
            )
            totals.saved.extend(result.saved)
            totals.skipped += result.skipped
            totals.missing += result.missing

            if args.commit:
                committed = commit_paths(list(dict.fromkeys(result.saved + result.acquisition_paths)), f"Seed current events {label}")
                if committed and args.push:
                    from seed.gitops import push_with_retry
                    push_with_retry(args.branch, args.token_env, args.push_attempts)

    print("\nDone")
    print(f"  wrote/changed: {len(totals.saved)}")
    print(f"  skipped:       {totals.skipped}")
    print(f"  missing:       {totals.missing}")
    return 0


# ---------------------------------------------------------------------------
# argparse wiring
# ---------------------------------------------------------------------------

def _add_common_range_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("start", type=parse_iso_date)
    parser.add_argument("end", type=parse_iso_date)
    parser.add_argument(
        "--target", choices=["missing", "under-size", "missing-or-under-size", "all"],
        default="missing", help="Which dates to process. 'all' forces a full re-fetch. Default: missing.",
    )
    parser.add_argument("--max-bytes", type=int, default=500, help="Size threshold for under-size targets.")
    parser.add_argument("--chunk", choices=["day", "month", "year"], default="month", help="Commit/planning batch size.")
    parser.add_argument("--limit-chunks", type=int, default=None, help="Only process the first N planned chunks.")
    parser.add_argument("--no-gdelt", action="store_true", help="Skip GDELT enrichment entirely.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m seed",
        description="Fetch Wikipedia Current Events + GDELT and write seed YAML files.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    from seed.replay import run_cache, run_reparse
    cache_cmd = subparsers.add_parser("cache", help="Import existing cache and explicitly acquire recorded oldids.")
    cache_cmd.add_argument("start", nargs="?", type=parse_iso_date)
    cache_cmd.add_argument("end", nargs="?", type=parse_iso_date)
    cache_cmd.add_argument("--batch-size", type=int, choices=range(1, 51), default=50)
    policy = cache_cmd.add_mutually_exclusive_group()
    policy.add_argument("--skip-unpinned", action="store_true", help="Report legacy/missing days without assigning a new source")
    policy.add_argument("--capture-unpinned", action="store_true", help="Explicitly capture current revisions as new inputs for unpinned daily seeds")
    cache_cmd.set_defaults(func=run_cache)
    replay_cmd = subparsers.add_parser("reparse", help="Generate separate extraction candidates offline.")
    replay_cmd.add_argument("start", type=parse_iso_date)
    replay_cmd.add_argument("end", type=parse_iso_date)
    replay_cmd.add_argument("--output-root", type=Path, required=True)
    replay_cmd.add_argument("--cached-only", action="store_true", help="Explicit partial run; report uncached/missing dates.")
    replay_cmd.add_argument("--verify", action="store_true", help="Repeat each parse and verify bytes, structural round trip and source locations.")
    replay_cmd.add_argument("--overrides", type=Path)
    replay_cmd.set_defaults(func=run_reparse)

    date_cmd = subparsers.add_parser("date", help="Fetch one day (default: yesterday UTC).")
    date_cmd.add_argument("date", nargs="?", type=parse_iso_date, default=None)
    date_cmd.add_argument("--overwrite", dest="overwrite", action="store_true", default=True)
    date_cmd.add_argument("--no-overwrite", dest="overwrite", action="store_false")
    date_cmd.add_argument("--no-gdelt", action="store_true")
    date_cmd.set_defaults(func=run_date)

    plan_cmd = subparsers.add_parser("plan", help="Show planned batches only, fetch nothing.")
    _add_common_range_args(plan_cmd)
    plan_cmd.set_defaults(func=run_plan)

    range_cmd = subparsers.add_parser("range", help="Fetch/write a date range. Resume-safe by default.")
    _add_common_range_args(range_cmd)
    range_cmd.add_argument("--commit", action="store_true", help="Commit each changed batch.")
    range_cmd.add_argument("--push", action="store_true", help="Push after each commit.")
    range_cmd.add_argument("--branch", default="main")
    range_cmd.add_argument("--allow-other-branch", action="store_true")
    range_cmd.add_argument("--push-attempts", type=int, default=3)
    range_cmd.add_argument("--token-env", default=None, help="Env var holding a GitHub token for HTTPS push auth.")
    range_cmd.add_argument("--report-dir", type=Path, default=Path(".backfill-reports"))
    range_cmd.add_argument("--no-report", action="store_true")
    range_cmd.set_defaults(func=run_range)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
