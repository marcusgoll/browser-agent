#!/usr/bin/env python3
"""Terminal status report for browser-agent readiness.

Reads normalized auth monitor outputs only. Does not inspect browser profiles,
cookies, tokens, storage, passwords, or browser databases.
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

DEFAULT_PLATFORMS = ["x", "linkedin", "reddit"]
ACTION_BY_STATUS = {
    "authenticated": "ready",
    "requires_user": "attended challenge/MFA",
    "expired": "attended login/session refresh",
    "ambiguous": "manual browser review",
    "infra_error": "investigate browser-agent infra",
    "missing": "run auth monitor",
}
WARN_STATUSES = {"requires_user", "expired", "ambiguous", "infra_error", "missing"}


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        return {"normalized_status": "infra_error", "reason": f"invalid json: {exc}", "source": str(path)}


def load_auth_status(output_dir: str | Path, platforms: list[str] | None = None) -> list[dict[str, Any]]:
    base = Path(output_dir)
    rows: list[dict[str, Any]] = []
    for platform in platforms or DEFAULT_PLATFORMS:
        path = base / f"social-auth-{platform}-latest.json"
        data = _read_json(path)
        if not data:
            rows.append(
                {
                    "platform": platform,
                    "normalized_status": "missing",
                    "status": "missing",
                    "reason": "latest auth result not found",
                    "profile": None,
                    "proof_bundle": None,
                    "source": str(path),
                    "checked_at": None,
                }
            )
            continue
        normalized = data.get("normalized_status") or data.get("status") or "ambiguous"
        rows.append(
            {
                "platform": data.get("platform") or platform,
                "normalized_status": normalized,
                "status": data.get("status") or normalized,
                "reason": data.get("reason") or "not provided",
                "profile": data.get("profile"),
                "proof_bundle": data.get("proof_bundle"),
                "source": str(path),
                "checked_at": data.get("checked_at") or data.get("completed_at"),
                "screenshot": data.get("screenshot"),
            }
        )
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, int]:
    return dict(Counter(row.get("normalized_status", "unknown") for row in rows))


def _format_time(value: Any) -> str:
    if not value:
        return "never"
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(value)))
    except Exception:
        return str(value)


def render_report(rows: list[dict[str, Any]]) -> str:
    summary = summarize(rows)
    lines = ["browser-agent status", "====================", f"summary: {json.dumps(summary, sort_keys=True)}", ""]
    for row in rows:
        status = row.get("normalized_status", "unknown")
        action = ACTION_BY_STATUS.get(status, "manual review")
        proof = row.get("proof_bundle") or "none"
        checked = _format_time(row.get("checked_at"))
        profile = row.get("profile") or "unknown-profile"
        reason = row.get("reason") or "not provided"
        lines.append(f"{row.get('platform')}: {status}")
        lines.append(f"  profile={profile}")
        lines.append(f"  reason={reason}")
        lines.append(f"  checked_at={checked}")
        lines.append(f"  proof={proof}")
        lines.append(f"  next={action}")
    return "\n".join(lines).rstrip() + "\n"


def render_json(rows: list[dict[str, Any]]) -> str:
    return json.dumps({"summary": summarize(rows), "platforms": rows}, indent=2, sort_keys=True) + "\n"


def exit_code(rows: list[dict[str, Any]]) -> int:
    return 2 if any(row.get("normalized_status") in WARN_STATUSES for row in rows) else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize browser-agent auth/proof readiness")
    parser.add_argument("--output-dir", default="/app/output", help="Directory containing social-auth-*-latest.json files")
    parser.add_argument("--platform", action="append", dest="platforms", help="Platform to include; repeatable")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON instead of terminal report")
    parser.add_argument("--no-fail", action="store_true", help="Always exit 0 after rendering report")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = load_auth_status(args.output_dir, args.platforms or DEFAULT_PLATFORMS)
    print(render_json(rows) if args.json else render_report(rows), end="")
    return 0 if args.no_fail else exit_code(rows)


if __name__ == "__main__":
    raise SystemExit(main())
