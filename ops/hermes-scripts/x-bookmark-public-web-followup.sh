#!/bin/bash
set -euo pipefail

BROWSER_AGENT_WORKDIR="${BROWSER_AGENT_WORKDIR:-/home/orchestrator/browser-agent}"
cd "$BROWSER_AGENT_WORKDIR"

docker compose run --rm -e PYTHONDONTWRITEBYTECODE=1 browser-agent scripts/public_web_followup.py --limit "${PUBLIC_WEB_FOLLOWUP_LIMIT:-8}"

latest_report=$(find output/opportunities -maxdepth 1 -type f -name 'public_web_followup_*.md' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2- || true)

if [[ -n "${latest_report:-}" && -f "$latest_report" ]]; then
  cat "$latest_report"
else
  echo "[CRITICAL] No public web follow-up report generated."
  exit 1
fi
