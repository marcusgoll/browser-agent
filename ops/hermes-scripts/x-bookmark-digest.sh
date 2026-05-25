#!/bin/bash
set -euo pipefail

# X Bookmark Digest Generator
# Generates a formatted digest from the latest bookmark analysis.

BROWSER_AGENT_WORKDIR="${BROWSER_AGENT_WORKDIR:-/home/orchestrator/browser-agent}"
cd "$BROWSER_AGENT_WORKDIR"

# Generate digest.
docker compose run --rm browser-agent scripts/weekly_bookmark_digest.py

latest=$(find output/digests -maxdepth 1 -type f -name 'digest_*.txt' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2- || true)

if [[ -n "${latest:-}" && -f "$latest" ]]; then
  echo "=== LATEST BOOKMARK DIGEST ==="
  cat "$latest"
  echo ""
  echo "Full digest saved to: $latest"
else
  echo "[CRITICAL] No digest generated"
  exit 1
fi
