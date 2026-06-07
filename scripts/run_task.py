#!/usr/bin/env python3
"""Browser-use task runner for homelab.
Supports: local Playwright browser OR connecting to existing Chrome (CDP).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.append(str(SCRIPT_DIR))

from proof_bundle import (
    RUNNER_VERSION_DEFAULT,
    build_metadata,
    build_run_id,
    sanitize_run_summary,
    write_metadata,
)

PROFILE_DIR = os.environ.get("BROWSER_PROFILE_DIR", "/app/profiles")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/app/output")
CHROME_HOST = os.environ.get("CHROME_HOST", "")
CHROME_PORT = os.environ.get("CHROME_PORT", "9222")
DEFAULT_REVIEW_STATE = "not_reviewed"
DEFAULT_WORKFLOW = "task_run"
DEFAULT_PLATFORM = "browser_use"
LATEST_RESULT_NAME = "task-run-latest.json"
LATEST_PROOF_NAME = "task-run-proof-latest.json"


def _load_browser_classes():
    from browser_use import Agent, BrowserSession
    from browser_use.browser.profile import BrowserProfile

    return Agent, BrowserSession, BrowserProfile


def get_llm():
    """Initialize LLM from env vars."""
    from browser_use.llm.litellm import ChatLiteLLM

    provider = os.environ.get("LLM_PROVIDER", "openrouter").lower()
    model = os.environ.get("LLM_MODEL", "anthropic/claude-sonnet-4")

    if provider == "openrouter":
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY not set")
        return ChatLiteLLM(
            model=f"openrouter/{model}",
            api_key=api_key,
            api_base="https://openrouter.ai/api/v1",
            temperature=0.1,
        )

    if provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        return ChatLiteLLM(
            model=f"anthropic/{model}",
            api_key=api_key,
            temperature=0.1,
        )

    if provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")
        return ChatLiteLLM(
            model=f"openai/{model}",
            api_key=api_key,
            temperature=0.1,
        )

    raise ValueError(f"Unknown LLM provider: {provider}")


def build_task_result_record(
    *,
    task: str,
    profile_name: str,
    headless: bool,
    task_id: str,
    worktree_path: str | None,
    review_state: str,
    runner_version: str,
    status: str,
    result_summary: str,
    proof_bundle_path: str,
    proof_run_id: str,
    started_at: int,
    completed_at: int,
    error: str | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "task_id": task_id,
        "proof_run_id": proof_run_id,
        "proof_bundle_path": proof_bundle_path,
        "proof_bundle": proof_bundle_path,
        "task": task,
        "profile": profile_name,
        "headless": headless,
        "worktree_path": worktree_path,
        "review_state": review_state,
        "runner_version": runner_version,
        "status": status,
        "sanitized_run_summary": sanitize_run_summary(result_summary),
        "started_at": started_at,
        "completed_at": completed_at,
    }
    if error:
        record["error"] = sanitize_run_summary(error)
    return record


async def run_task(
    task: str,
    profile_name: str = "default",
    headless: bool = True,
    *,
    task_id: str | None = None,
    worktree_path: str | None = None,
    output_dir: str | Path = OUTPUT_DIR,
    review_state: str = DEFAULT_REVIEW_STATE,
    runner_version: str = RUNNER_VERSION_DEFAULT,
):
    """Run a browser-use task and emit standardized run artifacts."""
    Agent, BrowserSession, BrowserProfile = _load_browser_classes()
    profile_path = Path(PROFILE_DIR) / profile_name
    profile_path.mkdir(parents=True, exist_ok=True)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    started_at = int(time.time())
    task_id = task_id or build_run_id("task", profile_name, timestamp=started_at)

    browser = None
    result: Any = None
    status = "completed"
    error: str | None = None
    proof_path: Path | None = None
    proof_run_id = task_id
    completed_at = started_at

    try:
        # Determine browser backend
        if CHROME_HOST:
            cdp_url = f"http://{CHROME_HOST}:{CHROME_PORT}"
            print(f"[browser-agent] Connecting to Chrome at {cdp_url}")
            browser = BrowserSession(cdp_url=cdp_url)
        else:
            print(f"[browser-agent] Using local Playwright with profile: {profile_path}")
            profile = BrowserProfile(
                headless=headless,
                user_data_dir=str(profile_path),
            )
            browser = BrowserSession(browser_profile=profile)

        llm = get_llm()
        agent = Agent(
            task=task,
            llm=llm,
            browser_session=browser,
        )

        print(f"[browser-agent] Starting task: {task[:80]}...")
        result = await agent.run()
    except Exception as exc:
        status = "failed"
        error = f"{exc.__class__.__name__}: {exc}"
        result = error
        print(f"[browser-agent] Task failed: {error}", file=sys.stderr)
        raise
    finally:
        completed_at = int(time.time())
        if browser is not None:
            try:
                await browser.close()
            except Exception as close_exc:
                print(f"[browser-agent] Browser close warning: {close_exc}", file=sys.stderr)

        summary = sanitize_run_summary(str(result))
        reason = "task_completed" if status == "completed" else "task_failed"
        next_action = "none" if status == "completed" else "inspect failure and rerun"
        proof = build_metadata(
            workflow=DEFAULT_WORKFLOW,
            platform=DEFAULT_PLATFORM,
            profile=profile_name,
            normalized_status=status,
            reason=reason,
            url="about:blank",
            title=task,
            action_type="task_run",
            next_action=next_action,
            started_at=started_at,
            completed_at=completed_at,
            item_id=task_id,
            task_id=task_id,
            worktree_path=worktree_path,
            review_state=review_state,
            runner_version=runner_version,
            sanitized_run_summary=summary,
        )
        proof_path = write_metadata(output_path, proof, latest_name=LATEST_PROOF_NAME)
        proof_run_id = str(proof["run_id"])

        record = build_task_result_record(
            task=task,
            profile_name=profile_name,
            headless=headless,
            task_id=task_id,
            worktree_path=worktree_path,
            review_state=review_state,
            runner_version=runner_version,
            status=status,
            result_summary=summary,
            proof_bundle_path=str(proof_path),
            proof_run_id=proof_run_id,
            started_at=started_at,
            completed_at=completed_at,
            error=error,
        )
        result_file = output_path / "runs" / proof_run_id / "task-run.json"
        result_file.parent.mkdir(parents=True, exist_ok=True)
        result_file.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        latest_result = output_path / LATEST_RESULT_NAME
        latest_result.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        print(f"[browser-agent] Proof saved to: {proof_path}")
        print(f"[browser-agent] Result saved to: {result_file}")
        print(f"[browser-agent] Result: {summary}")

    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run browser-use tasks")
    parser.add_argument("task", help="Natural language task description")
    parser.add_argument("--profile", default="default", help="Browser profile name")
    parser.add_argument("--headed", action="store_true", help="Run with visible browser (for login)")
    parser.add_argument("--task-id", default="", help="Stable task id for proof/run artifacts")
    parser.add_argument("--worktree-path", default="", help="Optional git worktree path for the task")
    parser.add_argument("--output-dir", default=OUTPUT_DIR, help="Directory for proof/result artifacts")
    parser.add_argument(
        "--review-state",
        default=DEFAULT_REVIEW_STATE,
        choices=["not_reviewed", "approved", "blocked", "warned"],
        help="Deterministic review state recorded in the run bundle",
    )
    parser.add_argument(
        "--runner-version",
        default=RUNNER_VERSION_DEFAULT,
        help="Version string recorded in the run bundle",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        asyncio.run(
            run_task(
                args.task,
                profile_name=args.profile,
                headless=not args.headed,
                task_id=args.task_id or None,
                worktree_path=args.worktree_path or None,
                output_dir=args.output_dir,
                review_state=args.review_state,
                runner_version=args.runner_version,
            )
        )
    except Exception:
        raise


if __name__ == "__main__":
    main()
