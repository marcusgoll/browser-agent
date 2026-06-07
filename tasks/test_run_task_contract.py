#!/usr/bin/env python3
"""Tests for the standardized browser-use task run contract."""
import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_task.py"
spec = importlib.util.spec_from_file_location("run_task", MODULE_PATH)
assert spec and spec.loader
run_task = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_task)


def test_build_task_result_record_has_standard_fields():
    record = run_task.build_task_result_record(
        task="Do the thing",
        profile_name="default",
        headless=True,
        task_id="task-123",
        worktree_path="/tmp/worktree",
        review_state="approved",
        runner_version="browser-agent-runner-v1",
        status="failed",
        result_summary="See https://example.com/path?secret=1",
        proof_bundle_path="/app/output/runs/task-123/proof.json",
        proof_run_id="task-123-1700000000",
        started_at=1,
        completed_at=2,
        error="RuntimeError: bad thing",
    )

    assert record["task_id"] == "task-123"
    assert record["proof_bundle_path"] == "/app/output/runs/task-123/proof.json"
    assert record["proof_bundle"] == "/app/output/runs/task-123/proof.json"
    assert record["worktree_path"] == "/tmp/worktree"
    assert record["review_state"] == "approved"
    assert record["runner_version"] == "browser-agent-runner-v1"
    assert record["sanitized_run_summary"] == "See [redacted-url]"
    assert record["error"] == "RuntimeError: bad thing"
    assert record["proof_run_id"] == "task-123-1700000000"


def test_run_task_module_imports_without_browser_use_dependency():
    assert hasattr(run_task, "build_task_result_record")
    assert hasattr(run_task, "run_task")
