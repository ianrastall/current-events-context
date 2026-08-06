"""
seed.ratelimit — one retry/backoff path, shared by every fetch in the pipeline.

This module exists because of a bug in the pre-rewrite pipeline: update_data.py
(the daily cron entrypoint) never caught wiki_parser.RateLimitError, so a single
HTTP 429 crashed the script outright. It only "worked" because the GitHub
Actions workflow retried the whole script up to 4 times — an accident of the
workflow shape, not a designed backoff path, and one that never honoured the
server's Retry-After header.

call_with_backoff() is now used identically by every code path — the single
-date cron command, bulk range/backfill runs, and GDELT queries — so there is
exactly one place backoff behaviour is decided.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable, TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")


class RateLimitError(Exception):
    """Raised by a fetch function when the server responds HTTP 429."""

    def __init__(self, retry_after: int = 0):
        self.retry_after = retry_after  # seconds suggested by server, 0 if not given
        super().__init__(f"HTTP 429 — server suggested retry_after={retry_after}s")


@dataclass(frozen=True)
class BackoffPolicy:
    base_secs: float
    max_secs: float
    max_retries: int


# Tuned constants carried over unchanged from the scripts being replaced.
WIKIPEDIA_POLICY = BackoffPolicy(base_secs=60, max_secs=600, max_retries=5)   # backfill_history.py
GDELT_POLICY     = BackoffPolicy(base_secs=10, max_secs=60,  max_retries=3)   # query_gdelt.py


def call_with_backoff(
    fn: Callable[[], T],
    *,
    policy: BackoffPolicy,
    label: str,
) -> T | None:
    """
    Call fn(), retrying on RateLimitError with backoff.

    - Honours the server's Retry-After value when it provided one.
    - Otherwise backs off exponentially from policy.base_secs, doubling each
      consecutive 429 up to policy.max_secs.
    - Gives up after policy.max_retries attempts and returns None (logged at
      ERROR) rather than raising — callers treat None the same as "no content".
    - Resets implicitly each call (backoff state is local to this invocation).
    """
    backoff = policy.base_secs

    for attempt in range(1, policy.max_retries + 1):
        try:
            return fn()
        except RateLimitError as e:
            wait = e.retry_after if e.retry_after > 0 else backoff
            wait = min(wait, policy.max_secs)

            if attempt == policy.max_retries:
                log.error(
                    "429 on %s — %d retries exhausted, giving up.",
                    label, policy.max_retries,
                )
                return None

            log.warning(
                "429 on %s (attempt %d/%d) — backing off for %ds.",
                label, attempt, policy.max_retries, wait,
            )
            time.sleep(wait)
            backoff = min(backoff * 2, policy.max_secs)

    return None  # unreachable, satisfies type checkers
