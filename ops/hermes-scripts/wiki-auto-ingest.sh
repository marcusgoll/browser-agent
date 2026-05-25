#!/bin/bash
# Wiki Auto-Ingest Pipeline
# Runs weekly: processes X bookmarks, generates digest, syncs to wiki, creates agent feed.
# Also runs wiki lint monthly.

set -euo pipefail

HERMES_SCRIPT_DIR="${HERMES_SCRIPT_DIR:-/home/orchestrator/.hermes/scripts}"
WIKI_PATH="${WIKI_PATH:-/home/orchestrator/wiki}"
LOG_DIR="${WIKI_AUTO_INGEST_LOG_DIR:-/var/odin/devops-monitor}"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/wiki-auto-ingest-$(date +%Y%m%d).log"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "=== Wiki Auto-Ingest Pipeline ==="
echo "Started: $(date)"

run_step() {
  local label="$1"
  local script_name="$2"
  echo "$label"
  if [[ -x "$HERMES_SCRIPT_DIR/$script_name" ]]; then
    bash "$HERMES_SCRIPT_DIR/$script_name" || echo "$script_name failed (non-fatal)"
  else
    echo "$script_name not found, skipping"
  fi
}

run_step "[1/5] Processing X bookmarks..." "x-bookmark-processor.sh"
run_step "[2/5] Generating bookmark digest..." "x-bookmark-digest.sh"
run_step "[3/5] Syncing bookmarks to wiki..." "x-bookmark-wiki-sync.sh"
run_step "[4/5] Generating agent feed..." "x-bookmark-agent-feed.sh"

# 5. Wiki lint (only on first Sunday of month)
DAY_OF_MONTH=$(date +%d)
if [[ "$(date +%u)" -eq 7 && "$DAY_OF_MONTH" -le 7 ]]; then
  echo "[5/5] Running monthly wiki lint..."
  cd "$WIKI_PATH"
  python3 scripts/wiki-search.py --recent 30 --json > /tmp/wiki-recent-pages.json
  echo "Recent pages saved to /tmp/wiki-recent-pages.json"
  # TODO: Add full lint script when available.
fi

echo "Finished: $(date)"
echo "Log: $LOG_FILE"
