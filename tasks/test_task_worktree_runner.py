#!/usr/bin/env python3
"""Tests for the worktree-backed browser-agent task runner."""
import importlib.util
from pathlib import Path
from subprocess import CompletedProcess

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "task_worktree_runner.py"
spec = importlib.util.spec_from_file_location("task_worktree_runner", MODULE_PATH)
assert spec and spec.loader
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def test_worktree_path_defaults_under_project_local_root(tmp_path):
    path = runner.worktree_path_for(tmp_path, "task-123")
    assert path == tmp_path / ".worktrees" / "task-123"


def test_create_task_worktree_refuses_dirty_existing_checkout(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    worktree_path = repo_root / ".worktrees" / "task-123"
    worktree_path.mkdir(parents=True)
    monkeypatch.setattr(runner, "_git_status_short", lambda path: " M scripts/run_task.py")

    try:
        runner.create_task_worktree(repo_root, "task-123")
    except RuntimeError as exc:
        assert "dirty worktree refused" in str(exc)
    else:
        raise AssertionError("expected dirty worktree refusal")


def test_run_task_worktree_cleans_up_on_success(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    worktree_path = repo_root / ".worktrees" / "task-123"
    calls: list[tuple[str, Path]] = []

    monkeypatch.setattr(runner, "create_task_worktree", lambda *args, **kwargs: worktree_path)
    monkeypatch.setattr(runner, "remove_task_worktree", lambda repo, path: calls.append(("remove", Path(path))))
    monkeypatch.setattr(runner, "_read_latest_task_summary", lambda output_dir: {"proof_bundle_path": "/app/output/runs/task-123/proof.json"})
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(args[0], 0, stdout="ok\n", stderr=""),
    )

    record = runner.run_task_worktree(
        repo_root,
        "Ship the task",
        task_id="task-123",
        output_dir=tmp_path / "output",
        keep_worktree=False,
    )

    assert record["status"] == "completed"
    assert record["proof_bundle_path"] == "/app/output/runs/task-123/proof.json"
    assert record["removed_worktree"] is True
    assert calls == [("remove", worktree_path)]


def test_run_task_worktree_keeps_worktree_on_request(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    worktree_path = repo_root / ".worktrees" / "task-123"
    calls: list[tuple[str, Path]] = []

    monkeypatch.setattr(runner, "create_task_worktree", lambda *args, **kwargs: worktree_path)
    monkeypatch.setattr(runner, "remove_task_worktree", lambda repo, path: calls.append(("remove", Path(path))))
    monkeypatch.setattr(runner, "_read_latest_task_summary", lambda output_dir: {"proof_bundle_path": "/app/output/runs/task-123/proof.json"})
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(args[0], 1, stdout="", stderr="boom\n"),
    )

    record = runner.run_task_worktree(
        repo_root,
        "Ship the task",
        task_id="task-123",
        output_dir=tmp_path / "output",
        keep_worktree=True,
    )

    assert record["status"] == "failed"
    assert record["proof_bundle_path"] == "/app/output/runs/task-123/proof.json"
    assert record["removed_worktree"] is False
    assert calls == []
