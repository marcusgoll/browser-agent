#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="${SOURCE_DIR:-/home/orchestrator/repos/local/browser-agent}"
LIVE_DIR="${LIVE_DIR:-/home/orchestrator/browser-agent}"
MODE="dry-run"
ALLOW_DIRTY=0
RUN_TESTS=1

usage() {
  cat <<'USAGE'
Usage: scripts/sync_to_live.sh [--apply] [--dry-run] [--allow-dirty] [--skip-tests]

Safely sync source-controlled browser-agent files into the live ops workspace.
Default mode is --dry-run.

Safety rules:
  - Refuses to run outside /home/orchestrator/repos/local/browser-agent by default.
  - Refuses dirty source tree unless --allow-dirty is set.
  - Runs canonical source tests unless --skip-tests is set.
  - Excludes .git, .env, profiles/, output/, caches, and browser/runtime state.
  - Does not delete extra live files by default.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply)
      MODE="apply"
      ;;
    --dry-run)
      MODE="dry-run"
      ;;
    --allow-dirty)
      ALLOW_DIRTY=1
      ;;
    --skip-tests)
      RUN_TESTS=0
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if [[ ! -d "$SOURCE_DIR/.git" ]]; then
  echo "ERROR: source repo not found: $SOURCE_DIR" >&2
  exit 2
fi
if [[ ! -d "$LIVE_DIR" ]]; then
  echo "ERROR: live workspace not found: $LIVE_DIR" >&2
  exit 2
fi
if [[ "$SOURCE_DIR" != "/home/orchestrator/repos/local/browser-agent" ]]; then
  echo "ERROR: unexpected SOURCE_DIR: $SOURCE_DIR" >&2
  exit 2
fi
if [[ "$LIVE_DIR" != "/home/orchestrator/browser-agent" ]]; then
  echo "ERROR: unexpected LIVE_DIR: $LIVE_DIR" >&2
  exit 2
fi

cd "$SOURCE_DIR"

if [[ "$ALLOW_DIRTY" != "1" ]]; then
  if [[ -n "$(git status --short)" ]]; then
    echo "ERROR: source repo has uncommitted changes. Commit first or use --allow-dirty for development dry-runs." >&2
    git status --short >&2
    exit 1
  fi
fi

if [[ "$RUN_TESTS" == "1" ]]; then
  echo "Running source canonical tests before sync..."
  docker compose run --rm browser-agent scripts/run_tests.py
fi

RSYNC_ARGS=(
  -a
  --itemize-changes
  --exclude .git/
  --include .env.example
  --exclude .env
  --exclude '.env.*'
  --exclude profiles/
  --exclude output/
  --exclude .pytest_cache/
  --exclude __pycache__/
  --exclude '*/__pycache__/'
  --exclude .agent/
)

if [[ "$MODE" == "dry-run" ]]; then
  RSYNC_ARGS+=(--dry-run)
  echo "DRY RUN: source -> live"
else
  echo "APPLY: source -> live"
fi

rsync "${RSYNC_ARGS[@]}" "$SOURCE_DIR/" "$LIVE_DIR/"

if [[ "$MODE" == "dry-run" ]]; then
  echo "Dry-run complete. Re-run with --apply after reviewing changes."
else
  echo "Apply complete. Run live verification: cd $LIVE_DIR && docker compose run --rm browser-agent scripts/run_tests.py"
fi
