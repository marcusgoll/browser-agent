#!/usr/bin/env python3
"""Non-secret proof-bundle helpers for browser-agent workflows.

These helpers record visible browser state and operator proof metadata only.
They must never store cookies, tokens, localStorage, sessionStorage, saved
passwords, or browser profile database contents.
"""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

SECRET_KEY_PATTERNS = (
    "cookie",
    "token",
    "localstorage",
    "local_storage",
    "sessionstorage",
    "session_storage",
    "password",
    "passwd",
    "secret",
)
ALLOWED_POLICY_KEYS = {"secrets_policy"}
SECRETS_POLICY = "visible browser state only; cookies/tokens/storage/passwords/browser databases not inspected"
RUNNER_VERSION_DEFAULT = "browser-agent-runner-v1"


def sanitize_url(url: str) -> str:
    """Redact query and fragment values before writing a URL to proof metadata."""
    try:
        parsed = urlparse(url or "")
        query = "[redacted]" if parsed.query or parsed.fragment else ""
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", query, ""))
    except Exception:
        return "[unparseable-url]"


def _safe_part(value: str | None) -> str:
    text = re.sub(r"[^A-Za-z0-9_-]+", "-", value or "").strip("-_")
    return text[:80] or "run"


def sanitize_run_summary(summary: str | None) -> str:
    """Normalize a run summary into a short, non-sensitive single line."""
    text = str(summary or "")
    text = re.sub(r"https?://\S+", "[redacted-url]", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:400]


def build_run_id(workflow: str, platform: str | None = None, item_id: str | None = None, timestamp: int | None = None) -> str:
    """Build a filesystem-safe run id."""
    parts = [_safe_part(workflow)]
    if platform:
        parts.append(_safe_part(platform))
    if item_id:
        parts.append(_safe_part(item_id))
    parts.append(str(timestamp or int(time.time())))
    return "-".join(parts)


def assert_no_secret_keys(data: Any, path: str = "") -> None:
    """Reject metadata dictionaries containing secret-like keys."""
    if isinstance(data, dict):
        for key, value in data.items():
            key_text = str(key).lower()
            current = f"{path}.{key}" if path else str(key)
            if key_text not in ALLOWED_POLICY_KEYS and any(pattern in key_text for pattern in SECRET_KEY_PATTERNS):
                raise ValueError(f"secret-like metadata key rejected: {current}")
            assert_no_secret_keys(value, current)
    elif isinstance(data, list):
        for idx, item in enumerate(data):
            assert_no_secret_keys(item, f"{path}[{idx}]")


def build_metadata(
    *,
    workflow: str,
    platform: str | None,
    profile: str | None,
    normalized_status: str,
    reason: str,
    url: str,
    title: str,
    action_type: str,
    next_action: str,
    started_at: int | None = None,
    completed_at: int | None = None,
    screenshots: dict[str, str] | None = None,
    account_context: dict[str, Any] | None = None,
    item_id: str | None = None,
    task_id: str | None = None,
    worktree_path: str | None = None,
    review_state: str | None = None,
    runner_version: str | None = None,
    sanitized_run_summary: str | None = None,
    run_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return proof metadata using the browser-agent proof-bundle contract."""
    start = started_at or int(time.time())
    complete = completed_at or int(time.time())
    metadata: dict[str, Any] = {
        "run_id": run_id or build_run_id(workflow, platform, item_id or task_id, complete),
        "workflow": workflow,
        "platform": platform,
        "profile": profile,
        "started_at": start,
        "completed_at": complete,
        "normalized_status": normalized_status,
        "reason": reason,
        "sanitized_url": sanitize_url(url),
        "title": (title or "")[:160],
        "action_type": action_type,
        "screenshots": screenshots or {},
        "account_context": account_context or {},
        "next_action": next_action,
        "secrets_policy": SECRETS_POLICY,
    }
    if item_id:
        metadata["item_id"] = item_id
    if task_id:
        metadata["task_id"] = task_id
    elif item_id:
        metadata["task_id"] = item_id
    if worktree_path:
        metadata["worktree_path"] = str(worktree_path)
    if review_state:
        metadata["review_state"] = review_state
    if runner_version:
        metadata["runner_version"] = runner_version
    if sanitized_run_summary:
        metadata["sanitized_run_summary"] = sanitize_run_summary(sanitized_run_summary)
    if extra:
        metadata["extra"] = extra
    assert_no_secret_keys(metadata)
    return metadata


def write_metadata(output_dir: str | Path, metadata: dict[str, Any], latest_name: str | None = None) -> Path:
    """Write metadata under output/runs/<run_id>/proof.json and optional latest copy."""
    assert_no_secret_keys(metadata)
    base = Path(output_dir)
    run_dir = base / "runs" / _safe_part(str(metadata["run_id"]))
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "proof.json"
    metadata.setdefault("proof_bundle_path", str(path))
    assert_no_secret_keys(metadata)
    text = json.dumps(metadata, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")
    if latest_name:
        latest_path = base / latest_name
        latest_path.parent.mkdir(parents=True, exist_ok=True)
        latest_path.write_text(text, encoding="utf-8")
    return path


def copy_screenshot_to_run(output_dir: str | Path, run_id: str, screenshot_path: str | Path, label: str) -> str:
    """Copy an existing screenshot into a proof run directory and return the new path."""
    source = Path(screenshot_path)
    run_dir = Path(output_dir) / "runs" / _safe_part(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    suffix = source.suffix or ".png"
    target = run_dir / f"{_safe_part(label)}{suffix}"
    shutil.copy2(source, target)
    return str(target)
