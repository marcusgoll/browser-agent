#!/bin/bash
set -euo pipefail

# X Bookmark Processor - Approved execute path
# This is intentionally not the scheduled default. It mutates X bookmarks by
# moving/deleting according to process_bookmarks.py analysis and must be run only
# after Marcus approves the exact execution scope.

BROWSER_AGENT_WORKDIR="${BROWSER_AGENT_WORKDIR:-/home/orchestrator/browser-agent}"
cd "$BROWSER_AGENT_WORKDIR"

MAX_BOOKMARKS="${X_BOOKMARK_MAX:-50}"
APPROVAL_NOTE="${X_BOOKMARK_APPROVAL_NOTE:-}"

if [[ "${X_BOOKMARK_APPROVED_EXECUTE:-0}" != "1" ]]; then
  echo "[BLOCKED] Approved execute requires X_BOOKMARK_APPROVED_EXECUTE=1"
  echo "Set X_BOOKMARK_APPROVAL_NOTE to the human approval context before running."
  exit 2
fi

if [[ -z "$APPROVAL_NOTE" ]]; then
  echo "[BLOCKED] X_BOOKMARK_APPROVAL_NOTE is required for audit context"
  exit 2
fi

echo "[APPROVED EXECUTE] X bookmark mutations enabled"
echo "Approval note: $APPROVAL_NOTE"
echo "Max bookmarks: $MAX_BOOKMARKS"

before_latest=$(find output -maxdepth 1 -type f -name 'bookmark_summary_*.json' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2- || true)

docker compose run --rm browser-agent scripts/process_bookmarks.py --execute --max "$MAX_BOOKMARKS"

latest=$(find output -maxdepth 1 -type f -name 'bookmark_summary_*.json' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2- || true)

if [[ -z "${latest:-}" || ! -f "$latest" ]]; then
  echo "[CRITICAL] No bookmark analysis generated after approved execute"
  exit 1
fi

if [[ -n "${before_latest:-}" && "$latest" == "$before_latest" ]]; then
  echo "[CRITICAL] Approved execute did not create a new summary file"
  echo "Latest existing report: $latest"
  exit 1
fi

echo "=== X Bookmark Approved Execute Results ==="
echo "Report: $latest"
echo ""
cat "$latest"
echo ""
echo "=== Degraded-run check ==="

python3 - "$latest" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text())
action_summary = data.get("action_summary") or {}
errors = int(action_summary.get("error") or 0)
dry_run = bool(data.get("dry_run"))
print(f"dry_run: {dry_run}")
print(f"action_errors: {errors}")
if dry_run:
    print("[CRITICAL] Approved execute produced dry-run output; mutations did not run")
    sys.exit(2)
if errors:
    print(f"[DEGRADED] Processor reported {errors} action errors during approved execute")
    sys.exit(1)
print("[OK] Approved execute completed with no reported action errors")
PY
