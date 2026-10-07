#!/bin/bash
set -euo pipefail

# X Bookmark Agent Feed Generator
# Generates high-ROI opportunity routing artifacts from the latest bookmark
# analysis and delivers the operator memo/task queue first. The older passive
# agent feed remains a secondary artifact.

BROWSER_AGENT_WORKDIR="${BROWSER_AGENT_WORKDIR:-/home/orchestrator/browser-agent}"
cd "$BROWSER_AGENT_WORKDIR"

run_started_at=$(date +%s)

docker compose run --rm \
  -e "BOOKMARK_TRIAGE_SCORER=${BOOKMARK_TRIAGE_SCORER:-deterministic}" \
  browser-agent scripts/feed_to_agents.py

latest_memo=$(find output/opportunities -maxdepth 1 -type f -name 'opportunity_memo_*.md' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2- || true)
latest_tasks=$(find output/opportunities -maxdepth 1 -type f -name 'high_roi_tasks_*.md' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2- || true)
latest_feed=$(find output/agent_tasks -maxdepth 1 -type f -name 'agent_feed_*.md' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2- || true)

if [[ -z "${latest_memo:-}" || ! -f "$latest_memo" ]]; then
  echo "[CRITICAL] No opportunity memo generated"
  exit 1
fi

if [[ -z "${latest_tasks:-}" || ! -f "$latest_tasks" ]]; then
  echo "[CRITICAL] No high-ROI task queue generated"
  exit 1
fi

if (( $(stat -c %Y "$latest_memo") < run_started_at || $(stat -c %Y "$latest_tasks") < run_started_at )); then
  echo "[CRITICAL] Generator produced no fresh opportunity artifacts"
  exit 1
fi

echo "=== X BOOKMARK OPPORTUNITY MEMO ==="
echo "Report: $latest_memo"
echo ""
cat "$latest_memo"
echo ""
echo "=== HIGH-ROI TASK QUEUE ==="
echo "Report: $latest_tasks"
echo ""
cat "$latest_tasks"
echo ""

if [[ -n "${latest_feed:-}" && -f "$latest_feed" ]]; then
  echo "=== PASSIVE AGENT FEED ARTIFACT ==="
  echo "Report: $latest_feed"
else
  echo "[WARNING] Passive agent feed artifact not found"
fi
