#!/usr/bin/env python3
"""Tests for non-secret browser-agent proof bundles."""
import importlib.util
import json
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "proof_bundle.py"
spec = importlib.util.spec_from_file_location("proof_bundle", MODULE_PATH)
proof = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proof)


def test_proof_bundle_metadata_sanitizes_urls_and_records_policy(tmp_path):
    metadata = proof.build_metadata(
        workflow="auth_check",
        platform="x",
        profile="x-profile",
        normalized_status="authenticated",
        reason="x_home_loaded",
        url="https://x.com/home?secret=123#frag",
        title="Home / X",
        action_type="read_only",
        next_action="none",
        started_at=100,
        completed_at=101,
    )

    assert metadata["sanitized_url"] == "https://x.com/home?[redacted]"
    assert metadata["secrets_policy"] == proof.SECRETS_POLICY
    assert metadata["screenshots"] == {}
    assert metadata["account_context"] == {}


def test_proof_bundle_sanitizes_task_summary_and_records_contract_fields(tmp_path):
    metadata = proof.build_metadata(
        workflow="task_run",
        platform="browser_use",
        profile="default",
        normalized_status="completed",
        reason="task_completed",
        url="about:blank",
        title="Inspect workflow",
        action_type="task_run",
        next_action="none",
        started_at=100,
        completed_at=101,
        item_id="task-123",
        task_id="task-123",
        worktree_path="/tmp/worktree",
        review_state="approved",
        runner_version="browser-agent-runner-v1",
        sanitized_run_summary="Run summary with https://example.com/path?secret=1",
    )

    path = proof.write_metadata(tmp_path, metadata, latest_name="task-run-latest.json")
    saved = json.loads(path.read_text())
    latest = json.loads((tmp_path / "task-run-latest.json").read_text())

    assert saved["task_id"] == "task-123"
    assert saved["item_id"] == "task-123"
    assert saved["worktree_path"] == "/tmp/worktree"
    assert saved["review_state"] == "approved"
    assert saved["runner_version"] == "browser-agent-runner-v1"
    assert saved["sanitized_run_summary"] == "Run summary with [redacted-url]"
    assert saved["proof_bundle_path"] == str(path)
    assert latest["proof_bundle_path"] == str(path)


def test_proof_bundle_writes_json_under_output_runs(tmp_path):
    metadata = proof.build_metadata(
        workflow="auth_check",
        platform="linkedin",
        profile="linkedin-profile",
        normalized_status="requires_user",
        reason="checkpoint",
        url="https://www.linkedin.com/checkpoint/?code=abc",
        title="Security Verification",
        action_type="blocked",
        next_action="attended login",
        started_at=100,
        completed_at=101,
    )

    path = proof.write_metadata(tmp_path, metadata, latest_name="social-auth-linkedin-latest.json")
    latest = tmp_path / "social-auth-linkedin-latest.json"

    assert path.exists()
    assert latest.exists()
    saved = json.loads(path.read_text())
    latest_saved = json.loads(latest.read_text())
    assert saved["run_id"] == metadata["run_id"]
    assert latest_saved["run_id"] == metadata["run_id"]
    assert path.parent == tmp_path / "runs" / metadata["run_id"]


def test_proof_bundle_rejects_secret_like_metadata_keys():
    try:
        proof.assert_no_secret_keys({"auth_token": "nope"})
    except ValueError as exc:
        assert "secret-like metadata key" in str(exc)
    else:
        raise AssertionError("expected secret-like key rejection")


def test_build_run_id_is_filesystem_safe():
    run_id = proof.build_run_id("auth/check", "x.com", "X-01")
    assert "/" not in run_id
    assert " " not in run_id
    assert run_id.startswith("auth-check-x-com-X-01-")
