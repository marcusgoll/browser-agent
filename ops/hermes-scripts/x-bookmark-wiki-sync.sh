#!/bin/bash
set -euo pipefail

# X Bookmark Wiki Sync
# Syncs bookmark insights to the wiki.

BROWSER_AGENT_WORKDIR="${BROWSER_AGENT_WORKDIR:-/home/orchestrator/browser-agent}"
WIKI_PATH="${WIKI_PATH:-/home/orchestrator/wiki}"
cd "$BROWSER_AGENT_WORKDIR"

docker compose run --rm -v "$WIKI_PATH:/app/wiki" browser-agent scripts/wiki_sync.py

echo "Wiki sync complete"
echo "Check $WIKI_PATH for updates"
