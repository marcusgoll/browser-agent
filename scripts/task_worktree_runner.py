#!/usr/bin/env python3
"""Worktree-backed task runner for browser-agent.

Creates an isolated git worktree, runs the standard browser-agent task command
inside that worktree, and returns a structured summary with the proof bundle
path emitted by scripts/run_task.py.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

DEFAULT_WORKTREE_ROOT = ".worktrees"
DEFAULT_BASE_BRANCH = "main"
DEFAULT_PROFILE = "default"
LATEST_TASK_RESULT = "task-run-latest.json"


def _safe_part(value: str | None) -> str:
    text = re.sub(r"[^A-Za-z0-9_-]+", "-", value or "").strip("-_")
    return text[:80] or "task"


def worktree_path_for(repo_root: str | Path, task_id: str, worktree_root: str | Path | None = None) -> Path:
    root = Path(worktree_root) if worktree_root else Path(repo_root) / DEFAULT_WORKTREE_ROOT
    return root / _safe_part(task_id)


def worktree_branch_for(task_id: str) -> str:
    return f"wt/{_safe_part(task_id)}"


def _run_git(args: list[str], cwd: str | Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=str(cwd), check=check, capture_output=True, text=True)


def _git_status_short(path: str | Path) -> str:
    result = _run_git(["git", "-C", str(path), "status", "--short"], cwd=path, check=True)
    return (result.stdout or "").strip()


def create_task_worktree(
    repo_root: str | Path,
    task_id: str,
    base_branch: str = DEFAULT_BASE_BRANCH,
    worktree_root: str | Path | None = None,
) -> Path:
    repo_root = Path(repo_root)
    worktree_path = worktree_path_for(repo_root, task_id, worktree_root)
    worktree_path.parent.mkdir(parents=True, exist_ok=True)

    if worktree_path.exists():
        if _git_status_short(worktree_path):
            raise RuntimeError(f"dirty worktree refused: {worktree_path}")
        return worktree_path

    _run_git(
        [
            "git",
            "-C",
            str(repo_root),
            "worktree",
            "add",
            str(worktree_path),
            "-b",
            worktree_branch_for(task_id),
            base_branch,
        ],
        cwd=repo_root,
        check=True,
    )
    return worktree_path


def remove_task_worktree(repo_root: str | Path, worktree_path: str | Path) -> None:
    repo_root = Path(repo_root)
    worktree_path = Path(worktree_path)
    if not worktree_path.exists():
        return
    _run_git(["git", "-C", str(repo_root), "worktree", "remove", "--force", str(worktree_path)], cwd=repo_root, check=True)


def build_task_command(
    task: str,
    *,
    profile: str,
    output_dir: str | Path,
    task_id: str,
    worktree_path: str | Path,
    review_state: str,
    runner_version: str,
) -> list[str]:
    return [
        "docker",
        "compose",
        "run",
        "--rm",
        "browser-agent",
        "scripts/run_task.py",
        task,
        "--profile",
        profile,
        "--output-dir",
        str(output_dir),
        "--task-id",
        task_id,
        "--worktree-path",
        str(worktree_path),
        "--review-state",
        review_state,
        "--runner-version",
        runner_version,
    ]


def _read_latest_task_summary(output_dir: str | Path) -> dict[str, Any] | None:
    path = Path(output_dir) / LATEST_TASK_RESULT
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"status": "degraded", "reason": f"invalid json in {path}", "proof_bundle_path": None}


def run_task_worktree(
    repo_root: str | Path,
    task: str,
    *,
    task_id: str,
    base_branch: str = DEFAULT_BASE_BRANCH,
    profile: str = DEFAULT_PROFILE,
    output_dir: str | Path = "/app/output",
    review_state: str = "not_reviewed",
    runner_version: str = "browser-agent-runner-v1",
    worktree_root: str | Path | None = None,
    keep_worktree: bool = False,
) -> dict[str, Any]:
    repo_root = Path(repo_root)
    worktree_path = create_task_worktree(repo_root, task_id, base_branch=base_branch, worktree_root=worktree_root)
    command = build_task_command(
        task,
        profile=profile,
        output_dir=output_dir,
        task_id=task_id,
        worktree_path=worktree_path,
        review_state=review_state,
        runner_version=runner_version,
    )
    completed = subprocess.run(command, cwd=str(worktree_path), capture_output=True, text=True)
    task_summary = _read_latest_task_summary(output_dir) or {}
    proof_bundle_path = task_summary.get("proof_bundle_path") or task_summary.get("proof_bundle")
    record: dict[str, Any] = {
        "task_id": task_id,
        "worktree_path": str(worktree_path),
        "base_branch": base_branch,
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "task_summary": task_summary,
        "proof_bundle_path": proof_bundle_path,
        "removed_worktree": False,
        "kept_worktree": keep_worktree,
    }

    if not keep_worktree:
        remove_task_worktree(repo_root, worktree_path)
        record["removed_worktree"] = True

    record["status"] = "completed" if completed.returncode == 0 else "failed"
    if completed.returncode != 0 and not task_summary:
        record["task_summary"] = {
            "status": "failed",
            "reason": "task command failed before writing task-run-latest.json",
        }
    return record


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run browser-agent tasks in an isolated git worktree")
    parser.add_argument("task", help="Natural language task description")
    parser.add_argument("--repo-root", default=str(Path.cwd()), help="Path to the browser-agent repo root")
    parser.add_argument("--task-id", required=True, help="Stable id for the worktree and proof bundle")
    parser.add_argument("--base-branch", default=DEFAULT_BASE_BRANCH, help="Base branch for the new worktree")
    parser.add_argument("--profile", default=DEFAULT_PROFILE, help="Browser profile name")
    parser.add_argument("--output-dir", default="/app/output", help="Browser-agent output directory")
    parser.add_argument("--review-state", default="not_reviewed", choices=["not_reviewed", "approved", "blocked", "warned"], help="Recorded review state")
    parser.add_argument("--runner-version", default="browser-agent-runner-v1", help="Runner version recorded in artifacts")
    parser.add_argument("--worktree-root", default="", help="Override the .worktrees root")
    parser.add_argument("--keep-worktree", action="store_true", help="Keep the worktree after the task finishes")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    record = run_task_worktree(
        args.repo_root,
        args.task,
        task_id=args.task_id,
        base_branch=args.base_branch,
        profile=args.profile,
        output_dir=args.output_dir,
        review_state=args.review_state,
        runner_version=args.runner_version,
        worktree_root=args.worktree_root or None,
        keep_worktree=args.keep_worktree,
    )
    print(json.dumps(record, indent=2, sort_keys=True))
    return int(record["returncode"])


if __name__ == "__main__":
    raise SystemExit(main())
