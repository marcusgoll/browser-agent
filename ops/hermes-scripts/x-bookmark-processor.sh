#!/bin/bash
set -euo pipefail

# X Bookmark Processor - Weekly safe report
# Default scheduled behavior is non-destructive. It reads/analyzes bookmarks and
# reports planned moves/deletes without mutating X bookmark folders.

BROWSER_AGENT_WORKDIR="${BROWSER_AGENT_WORKDIR:-/home/orchestrator/browser-agent}"
APPROVED_EXECUTE_WRAPPER="${APPROVED_EXECUTE_WRAPPER:-/home/orchestrator/.hermes/scripts/x-bookmark-processor-approved-execute.sh}"
cd "$BROWSER_AGENT_WORKDIR"

MAX_BOOKMARKS="${X_BOOKMARK_MAX:-50}"
MODE="dry-run"

if [[ "${X_BOOKMARK_APPROVED_EXECUTE:-0}" == "1" ]]; then
  echo "[BLOCKED] This scheduled wrapper is dry-run only."
  echo "Use $APPROVED_EXECUTE_WRAPPER after explicit approval."
  exit 2
fi

before_latest=$(find output -maxdepth 1 -type f -name 'bookmark_summary_*.json' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2- || true)

# Run the processor in report-only mode.
docker compose run --rm browser-agent scripts/process_bookmarks.py --dry-run --max "$MAX_BOOKMARKS"

latest=$(find output -maxdepth 1 -type f -name 'bookmark_summary_*.json' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2- || true)

if [[ -z "${latest:-}" || ! -f "$latest" ]]; then
  echo "[CRITICAL] No bookmark analysis generated"
  exit 1
fi

if [[ -n "${before_latest:-}" && "$latest" == "$before_latest" ]]; then
  echo "[CRITICAL] Processor did not create a new summary file"
  echo "Latest existing report: $latest"
  exit 1
fi

echo "=== X Bookmark Analysis Results ($MODE) ==="
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
planned_deletes = sum(
    1 for item in data.get("by_folder", {}).items()
    if item[0] == "delete"
)
print(f"dry_run: {dry_run}")
print(f"action_errors: {errors}")
print(f"planned_delete_folder_count: {planned_deletes}")
if not dry_run:
    print("[CRITICAL] Scheduled processor produced non-dry-run output")
    sys.exit(2)
if errors:
    print(f"[WARNING] Processor reported {errors} action errors in dry-run planning")
else:
    print("[OK] No action errors reported")
PY

echo ""
echo "No X bookmark mutations were performed."
echo "Use approved-execute wrapper only after reviewing the report and approving exact scope."
