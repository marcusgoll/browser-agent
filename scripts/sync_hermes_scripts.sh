#!/bin/bash
set -euo pipefail

SOURCE_DIR="${SOURCE_DIR:-ops/hermes-scripts}"
TARGET_DIR="${HERMES_SCRIPT_DIR:-/home/orchestrator/.hermes/scripts}"
MODE="dry-run"
ALLOW_DIRTY=0

usage() {
  cat <<'USAGE'
Usage: scripts/sync_hermes_scripts.sh [--dry-run|--apply] [--allow-dirty]

Copies versioned Hermes wrapper scripts from ops/hermes-scripts/ into
/home/orchestrator/.hermes/scripts/ as real executable files. Hermes cron rejects
symlinked scripts, so this intentionally copies files instead of linking them.

Defaults to dry-run. Refuses dirty source repo unless --allow-dirty is provided.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) MODE="dry-run" ;;
    --apply) MODE="apply" ;;
    --allow-dirty) ALLOW_DIRTY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if ! git rev-parse --show-toplevel >/dev/null 2>&1; then
  echo "[ERROR] Run from inside the browser-agent source repo" >&2
  exit 2
fi

REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT"

if [[ ! -d "$SOURCE_DIR" ]]; then
  echo "[ERROR] Source script directory not found: $SOURCE_DIR" >&2
  exit 2
fi

if [[ "$ALLOW_DIRTY" != "1" && -n "$(git status --porcelain)" ]]; then
  echo "[BLOCKED] Source tree is dirty. Commit/revert first, or pass --allow-dirty for a deliberate local deployment." >&2
  git status --short >&2
  exit 2
fi

mapfile -t scripts < <(find "$SOURCE_DIR" -maxdepth 1 -type f -name '*.sh' | sort)
if [[ ${#scripts[@]} -eq 0 ]]; then
  echo "[ERROR] No scripts found in $SOURCE_DIR" >&2
  exit 2
fi

echo "Mode: $MODE"
echo "Source: $REPO_ROOT/$SOURCE_DIR"
echo "Target: $TARGET_DIR"
echo "Scripts: ${#scripts[@]}"

if [[ "$MODE" == "dry-run" ]]; then
  for script in "${scripts[@]}"; do
    target="$TARGET_DIR/$(basename "$script")"
    if [[ -f "$target" ]]; then
      if cmp -s "$script" "$target"; then
        echo "UNCHANGED $(basename "$script")"
      else
        echo "UPDATE    $(basename "$script")"
      fi
    else
      echo "CREATE    $(basename "$script")"
    fi
  done
  echo "Dry-run complete. Re-run with --apply after reviewing changes."
  exit 0
fi

mkdir -p "$TARGET_DIR"
for script in "${scripts[@]}"; do
  target="$TARGET_DIR/$(basename "$script")"
  install -m 0755 "$script" "$target"
  echo "INSTALLED $target"
done

echo "Hermes scripts installed."
