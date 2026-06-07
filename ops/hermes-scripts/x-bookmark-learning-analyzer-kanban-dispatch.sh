#!/bin/bash
set -euo pipefail

MODE="dry-run"
BOARD="${HERMES_KANBAN_BOARD:-main}"
PAYLOAD_FILE="${PAYLOAD_FILE:-/home/orchestrator/repos/local/browser-agent/docs/superpowers/plans/2026-06-03-x-bookmark-learning-analyzer-kanban-create-payloads.md}"
CREATED_BY="${CREATED_BY:-kanban-orchestrator}"

usage() {
  cat <<'USAGE'
Usage: x-bookmark-learning-analyzer-kanban-dispatch.sh [--dry-run|--apply] [--board <slug>] [--payload-file <path>]

Creates the X Bookmark Learning Analyzer Kanban graph in dependency order.
Default mode is dry-run. Use --apply to create cards.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) MODE="dry-run" ;;
    --apply) MODE="apply" ;;
    --board)
      shift
      [[ $# -gt 0 ]] || { echo "[ERROR] --board requires a value" >&2; exit 2; }
      BOARD="$1"
      ;;
    --payload-file)
      shift
      [[ $# -gt 0 ]] || { echo "[ERROR] --payload-file requires a value" >&2; exit 2; }
      PAYLOAD_FILE="$1"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[ERROR] Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if [[ ! -f "$PAYLOAD_FILE" ]]; then
  echo "[ERROR] Payload file not found: $PAYLOAD_FILE" >&2
  exit 2
fi

python3 - "$MODE" "$PAYLOAD_FILE" "$BOARD" "$CREATED_BY" <<'PY'
import json
import os
import re
import subprocess
import sys
from pathlib import Path

mode, payload_file, board, created_by = sys.argv[1:5]
text = Path(payload_file).read_text()
blocks = re.findall(r"```json\s*(\{.*?\})\s*```", text, flags=re.S)
expected_titles = [
    "FX-0: synthesize P0 workflows for X Bookmark Learning Analyzer",
    "P0-1: bookmark schema",
    "P0-2: deduplication and caching",
    "P0-3: triage scoring model",
    "P0-4: project routing",
    "P0-5: learning note output",
    "P0-VALUE-GATE: evaluate whether the P0 slice is useful",
    "P1-6: content idea output",
    "P1-7: weekly digest",
    "P1-8: metrics dashboard",
]
placeholder_names = [
    "FX0_ID",
    "P0_1_ID",
    "P0_2_ID",
    "P0_3_ID",
    "P0_4_ID",
    "P0_5_ID",
    "P0_VALUE_GATE_ID",
    "P1_6_ID",
    "P1_7_ID",
    "P1_8_ID",
]

if len(blocks) != len(expected_titles):
    print(f"[ERROR] Expected {len(expected_titles)} JSON payload blocks, found {len(blocks)} in {payload_file}", file=sys.stderr)
    sys.exit(2)

tasks = []
for i, block in enumerate(blocks):
    task = json.loads(block)
    if task.get("title") != expected_titles[i]:
        print(f"[ERROR] Payload block {i+1} title mismatch: expected {expected_titles[i]!r}, got {task.get('title')!r}", file=sys.stderr)
        sys.exit(2)
    tasks.append(task)

created = {}


def resolve_parents(parent_specs):
    resolved = []
    for parent in parent_specs or []:
        if parent in created:
            resolved.append(created[parent])
        else:
            resolved.append(parent)
    return resolved


def priority_to_int(priority):
    if isinstance(priority, int):
        return priority
    if isinstance(priority, str):
        normalized = priority.strip().upper()
        if normalized.startswith("P") and normalized[1:].isdigit():
            return int(normalized[1:])
        if normalized.isdigit():
            return int(normalized)
    return 0


def build_command(task, parent_ids):
    cmd = ["hermes", "kanban"]
    if board:
        cmd += ["--board", board]
    cmd += [
        "create",
        task["title"],
        "--assignee",
        task["assignee"],
        "--priority",
        str(priority_to_int(task.get("priority", 0))),
        "--body",
        task["body"],
        "--created-by",
        task.get("created_by", created_by),
        "--idempotency-key",
        task["idempotency_key"],
        "--json",
    ]
    for parent_id in parent_ids:
        cmd += ["--parent", parent_id]
    return cmd


if mode == "dry-run":
    print(f"Mode: dry-run")
    print(f"Payload file: {payload_file}")
    print(f"Board: {board or '(current board)'}")
    print(f"Created-by: {created_by}")
    print("")
    for idx, task in enumerate(tasks):
        parent_specs = task.get("parents") or []
        resolved = resolve_parents(parent_specs)
        placeholder = placeholder_names[idx]
        print(f"[{idx+1}/10] {placeholder} -> {task['title']}")
        print(f"       assignee={task['assignee']} priority={task.get('priority', 'P0')} parents={parent_specs}")
        if resolved and any(p not in created.values() for p in resolved):
            unresolved = [p for p in parent_specs if p not in created]
            if unresolved:
                print(f"       note=parents will resolve at apply time: {unresolved}")
        else:
            print("       note=ready")
    print("")
    print("Dry-run complete. Re-run with --apply to create the graph.")
    sys.exit(0)

print(f"Mode: apply")
print(f"Payload file: {payload_file}")
print(f"Board: {board or '(current board)'}")
print(f"Created-by: {created_by}")
print("")

for idx, task in enumerate(tasks):
    placeholder = placeholder_names[idx]
    parent_specs = task.get("parents") or []
    parent_ids = resolve_parents(parent_specs)
    if parent_specs and any(parent not in created and parent in placeholder_names for parent in parent_specs):
        missing = [p for p in parent_specs if p in placeholder_names and p not in created]
        if missing:
            print(f"[ERROR] Cannot create {task['title']!r}; unresolved parent placeholders: {missing}", file=sys.stderr)
            sys.exit(2)
    cmd = build_command(task, parent_ids)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[ERROR] hermes kanban create failed for {task['title']!r}", file=sys.stderr)
        if result.stdout:
            print(result.stdout, file=sys.stderr)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        sys.exit(result.returncode)
    raw = result.stdout.strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print(f"[ERROR] Expected JSON from hermes kanban create for {task['title']!r}", file=sys.stderr)
        print(raw, file=sys.stderr)
        sys.exit(2)
    task_id = data.get("id") or data.get("task_id")
    if not task_id:
        print(f"[ERROR] Create response missing task id for {task['title']!r}", file=sys.stderr)
        print(raw, file=sys.stderr)
        sys.exit(2)
    created[placeholder] = task_id
    parent_note = ", ".join(parent_ids) if parent_ids else "(none)"
    print(f"CREATED {placeholder} -> {task_id}")
    print(f"  title: {task['title']}")
    print(f"  parents: {parent_note}")

print("")
print("ID mapping:")
for placeholder in placeholder_names:
    print(f"  {placeholder}={created.get(placeholder, '')}")
PY
