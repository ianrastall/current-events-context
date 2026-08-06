"""
seed.gitops — git helpers for the `range` command's --commit/--push batching.

Carried over unchanged from backfill_batches.py.
"""

from __future__ import annotations

import base64
import os
import subprocess
import time
from pathlib import Path

from seed.merge import REPO_ROOT


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
