#!/usr/bin/env python3
"""Tests for browser-agent terminal status reports."""
import importlib.util
import json
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "browser_agent_status.py"
spec = importlib.util.spec_from_file_location("browser_agent_status", MODULE_PATH)
status = importlib.util.module_from_spec(spec)
spec.loader.exec_module(status)


def write_json(path: Path, data: dict):
    path.write_text(json.dumps(data) + "\n")


def test_load_auth_status_reads_platform_latest_files(tmp_path):
    write_json(
        tmp_path / "social-auth-x-latest.json",
        {
            "platform": "x",
            "normalized_status": "authenticated",
            "reason": "x_home_loaded",
            "profile": "x-profile",
            "proof_bundle": "/app/output/runs/x/proof.json",
            "checked_at": 100,
        },
    )

    rows = status.load_auth_status(tmp_path, ["x", "linkedin"])

    assert rows[0]["platform"] == "x"
    assert rows[0]["normalized_status"] == "authenticated"
    assert rows[1]["platform"] == "linkedin"
    assert rows[1]["normalized_status"] == "missing"


def test_render_terminal_report_includes_actions_and_proofs(tmp_path):
    write_json(
        tmp_path / "social-auth-x-latest.json",
        {
            "platform": "x",
            "normalized_status": "expired",
            "reason": "x_login_screen",
            "profile": "x-profile",
            "proof_bundle": "/app/output/runs/x/proof.json",
            "checked_at": 100,
        },
    )
    rows = status.load_auth_status(tmp_path, ["x"])
    report = status.render_report(rows)

    assert "browser-agent status" in report
    assert "x: expired" in report
    assert "proof=/app/output/runs/x/proof.json" in report
    assert "next=attended login/session refresh" in report


def test_report_exit_code_warns_on_expired_or_infra_error():
    assert status.exit_code([{"normalized_status": "authenticated"}]) == 0
    assert status.exit_code([{"normalized_status": "expired"}]) == 2
    assert status.exit_code([{"normalized_status": "infra_error"}]) == 2


def test_render_json_report_is_machine_readable(tmp_path):
    rows = [{"platform": "x", "normalized_status": "authenticated"}]
    payload = status.render_json(rows)
    decoded = json.loads(payload)
    assert decoded["summary"]["authenticated"] == 1
    assert decoded["platforms"] == rows
