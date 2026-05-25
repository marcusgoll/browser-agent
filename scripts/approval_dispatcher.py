#!/usr/bin/env python3
"""One-at-a-time social approval-card dispatcher.

Safety boundaries:
- Emits approval cards only; never publishes.
- Records decisions as durable JSONL events; callbacks/text approval are not direct write permission.
- Sends at most one outstanding card until a decision event exists.
- Does not inspect secrets, browser profiles, cookies, tokens, or platform stores.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from social_voice_review import format_review_for_card, review_social_copy  # noqa: E402

VALID_PENDING_STATUSES = {"needs-review", "needs_review", "proposed", "pending", "draft"}
TRACKER_PENDING_STATUSES = {"needs-review", "needs_review", "proposed", "pending", "draft", "awaiting approval"}
VALID_DECISIONS = {"approve", "revise", "later", "reject"}
DEFAULT_QUEUE_DIRS = [Path("/app/queue"), Path("/app/output")]
DEFAULT_APPROVALS_DIR = Path("/app/approvals")
ITEM_HEADER_RE = re.compile(r"^\s*(?P<item_id>(?:XReply|LinkedIn-Article|LinkedIn|Reddit|X)-\d{2})\s+-\s+(?P<title>.+?)\s*$", re.MULTILINE)
SECTION_STOP_RE = re.compile(r"^\s*(?:media|links|source_evidence|risk_notes|proposed_time|rollback_plan|approval):\s*", re.IGNORECASE)


def slug_from_path(path: Path) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", path.stem).strip("-._") or "approval-item"


def extract_section(text: str, heading: str) -> str:
    pattern = rf"(?ims)^##\s+{re.escape(heading)}\s*\n(?P<body>.*?)(?=\n##\s+|\Z)"
    match = re.search(pattern, text)
    return match.group("body").strip() if match else ""


def extract_status(text: str) -> str:
    match = re.search(r"(?im)^Status:\s*(.+?)\s*$", text)
    return match.group(1).strip().lower() if match else "needs-review"


def _platform_for_item_id(item_id: str) -> str:
    if item_id.startswith("XReply") or item_id.startswith("X-"):
        return "X"
    if item_id.startswith("LinkedIn"):
        return "LinkedIn"
    if item_id.startswith("Reddit"):
        return "Reddit"
    return "Unknown"


def _type_for_item_id(item_id: str, title: str = "") -> str:
    if item_id.startswith("XReply"):
        return "reply"
    if "Article" in item_id or "outline" in title.lower():
        return "article outline"
    if item_id.startswith("Reddit"):
        return "comment opportunity"
    return "post"


def _clean_batch_lines(lines: list[str]) -> list[str]:
    cleaned: list[str] = []
    for line in lines:
        cleaned.append(line[2:] if line.startswith("  ") else line)
    return cleaned


def _extract_reply_copy(lines: list[str]) -> tuple[str, str | None, str | None]:
    target_url = None
    target_context = None
    reply_start = None
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.lower().startswith("target url:"):
            target_url = stripped.split(":", 1)[1].strip()
        elif stripped.lower().startswith("target context:"):
            target_context = stripped.split(":", 1)[1].strip()
        elif stripped.lower() == "reply:":
            reply_start = idx + 1
            break
    if reply_start is None:
        return "\n".join(line.rstrip() for line in lines).strip(), target_url, target_context
    return "\n".join(line.rstrip() for line in lines[reply_start:]).strip(), target_url, target_context


def load_social_batch_items(path: Path, text: str) -> list[dict[str, Any]]:
    """Split the social-media-manager batch packet format into per-item cards."""
    if "exact_content:" not in text or not ITEM_HEADER_RE.search(text):
        return []
    raw_lines = text.splitlines()
    items: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current, current_lines
        if not current:
            return
        body_lines = _clean_batch_lines(current_lines)
        copy, target_url, target_context = _extract_reply_copy(body_lines) if current["type"] == "reply" else ("\n".join(line.rstrip() for line in body_lines).strip(), None, None)
        current["copy"] = copy
        if target_url:
            current["target_url"] = target_url
        if target_context:
            current["goal"] = target_context
        items.append(current)
        current = None
        current_lines = []

    for line in raw_lines:
        if current and SECTION_STOP_RE.match(line):
            flush()
            break
        match = ITEM_HEADER_RE.match(line)
        if match:
            flush()
            item_id = match.group("item_id")
            title = match.group("title").strip()
            current = {
                "item_id": item_id,
                "platform": _platform_for_item_id(item_id),
                "type": _type_for_item_id(item_id, title),
                "goal": "Review and approve exact content.",
                "risk": "unknown",
                "copy": "",
                "status": extract_status(text),
                "source_path": str(path),
                "title": title,
            }
            current_lines = []
        elif current is not None:
            current_lines.append(line)
    flush()
    return [item for item in items if item.get("copy")]


def load_markdown_item(path: Path) -> dict[str, Any] | None:
    text = path.read_text(encoding="utf-8")
    batch_items = load_social_batch_items(path, text)
    if batch_items:
        return None
    status = extract_status(text)
    if status not in VALID_PENDING_STATUSES:
        return None
    platform = extract_section(text, "Target surface").splitlines()[0].strip() if extract_section(text, "Target surface") else "Unknown"
    copy = extract_section(text, "Exact content")
    risk_text = extract_section(text, "Risk notes")
    risk = "unknown"
    low_text = risk_text.lower()
    if "high" in low_text:
        risk = "high"
    elif "medium" in low_text:
        risk = "medium"
    elif "low" in low_text:
        risk = "low"
    return {
        "item_id": slug_from_path(path),
        "platform": platform,
        "type": "post",
        "goal": "Review and approve exact content.",
        "risk": risk,
        "copy": copy,
        "status": status,
        "source_path": str(path),
    }


def _item_copy(data: dict[str, Any]) -> str:
    for key in ("copy", "text", "content", "exact_content", "suggested_action", "title"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def load_json_items(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(raw_items, list):
        return []
    items: list[dict[str, Any]] = []
    for idx, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            continue
        status = str(raw.get("status") or "needs-review").lower()
        if status not in VALID_PENDING_STATUSES:
            continue
        item_id = str(raw.get("id") or raw.get("item_id") or f"{path.stem}-{idx + 1}")
        items.append(
            {
                "item_id": item_id,
                "platform": str(raw.get("platform") or raw.get("target_surface") or "Unknown"),
                "type": str(raw.get("type") or raw.get("task_type") or "post"),
                "goal": str(raw.get("goal") or raw.get("why") or "Review and approve exact content."),
                "risk": str(raw.get("risk") or raw.get("risk_level") or "unknown"),
                "copy": _item_copy(raw),
                "status": status,
                "source_path": str(path),
            }
        )
    return items


def load_queue_items(queue_dirs: list[str | Path]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for queue_dir in queue_dirs:
        root = Path(queue_dir)
        if not root.exists():
            continue
        files = sorted([*root.glob("*.md"), *root.glob("*.json")])
        for path in files:
            loaded: list[dict[str, Any]] = []
            try:
                if path.suffix.lower() == ".md":
                    text = path.read_text(encoding="utf-8")
                    batch_items = load_social_batch_items(path, text)
                    if batch_items:
                        loaded = batch_items
                    else:
                        item = load_markdown_item(path)
                        loaded = [item] if item else []
                elif path.suffix.lower() == ".json":
                    loaded = load_json_items(path)
            except Exception:
                continue
            for item in loaded:
                if item["item_id"] in seen:
                    continue
                seen.add(item["item_id"])
                items.append(item)
    return items


def registry_path(approvals_dir: str | Path) -> Path:
    return Path(approvals_dir) / "sent-approval-cards.json"


def events_path(approvals_dir: str | Path) -> Path:
    return Path(approvals_dir) / "events" / "telegram-social-approvals.jsonl"


def load_registry(approvals_dir: str | Path) -> dict[str, Any]:
    path = registry_path(approvals_dir)
    if not path.exists():
        return {"sent": [], "outstanding": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if "cards" in data:
            cards = data.get("cards") or {}
            sent = list(cards.values()) if isinstance(cards, dict) else []
            last_sent = data.get("last_sent_item_id")
            outstanding = cards.get(last_sent) if isinstance(cards, dict) and last_sent else None
            return {"sent": sent, "outstanding": outstanding, "legacy_cards": cards}
        return {"sent": list(data.get("sent") or []), "outstanding": data.get("outstanding")}
    except Exception:
        return {"sent": [], "outstanding": None}


def write_registry(approvals_dir: str | Path, registry: dict[str, Any]) -> None:
    path = registry_path(approvals_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_events(approvals_dir: str | Path) -> list[dict[str, Any]]:
    path = events_path(approvals_dir)
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def latest_decisions(approvals_dir: str | Path) -> dict[str, dict[str, Any]]:
    decisions: dict[str, dict[str, Any]] = {}
    for event in load_events(approvals_dir):
        item_id = event.get("item_id")
        action = event.get("action")
        if item_id and action in VALID_DECISIONS:
            decisions[item_id] = event
    return decisions


def load_tracker_statuses(tracker_path: str | Path | None) -> dict[str, str]:
    if not tracker_path:
        return {}
    path = Path(tracker_path)
    if not path.exists():
        return {}
    statuses: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "---" in stripped or " ID " in stripped:
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) >= 4 and cells[0]:
            statuses[cells[0]] = cells[3].lower()
    return statuses


def item_allowed_by_tracker(item: dict[str, Any], tracker_statuses: dict[str, str]) -> bool:
    if not tracker_statuses:
        return True
    status = tracker_statuses.get(item["item_id"])
    return status in TRACKER_PENDING_STATUSES


def render_card(item: dict[str, Any]) -> str:
    copy = (item.get("copy") or "").strip()
    if len(copy) > 1200:
        copy = copy[:1197].rstrip() + "..."
    item_id = item["item_id"]
    voice_review = review_social_copy(copy, platform=str(item.get("platform") or "Unknown"), kind=str(item.get("type") or "post"))
    voice_text = ""
    if voice_review["status"] != "pass":
        voice_text = f"\n{format_review_for_card(voice_review)}\n"
    return (
        f"SOCIAL APPROVAL {item_id}\n"
        f"Platform: {item.get('platform') or 'Unknown'}\n"
        f"Type: {item.get('type') or 'post'}\n"
        f"Goal: {item.get('goal') or 'Review and approve exact content.'}\n"
        f"Risk: {item.get('risk') or 'unknown'}\n"
        f"{voice_text}\n"
        f"Copy:\n{copy}\n\n"
        f"Actions: approve {item_id} | revise {item_id}: <change> | later {item_id} | reject {item_id}"
    )


def dispatch_next(
    queue_dirs: list[str | Path],
    approvals_dir: str | Path,
    dry_run: bool = False,
    tracker_path: str | Path | None = None,
) -> dict[str, Any]:
    approvals = Path(approvals_dir)
    registry = load_registry(approvals)
    decisions = latest_decisions(approvals)
    tracker_statuses = load_tracker_statuses(tracker_path)
    outstanding = registry.get("outstanding")
    if outstanding and outstanding.get("item_id") not in decisions:
        return {"status": "waiting", "outstanding": outstanding}

    sent_ids = {entry.get("item_id") for entry in registry.get("sent", [])}
    items = load_queue_items(queue_dirs)
    for item in items:
        item_id = item["item_id"]
        if not item_allowed_by_tracker(item, tracker_statuses):
            continue
        if item_id in decisions or item_id in sent_ids:
            continue
        voice_review = review_social_copy(
            item.get("copy") or "",
            platform=str(item.get("platform") or "Unknown"),
            kind=str(item.get("type") or "post"),
        )
        if voice_review["blocking"]:
            return {"status": "voice_blocked", "item": item, "voice_review": voice_review}
        sent_record = {
            "item_id": item_id,
            "sent_at": int(time.time()),
            "source_path": item.get("source_path"),
            "platform": item.get("platform"),
        }
        card = render_card(item)
        if not dry_run:
            registry.setdefault("sent", []).append(sent_record)
            registry["outstanding"] = sent_record
            write_registry(approvals, registry)
        return {"status": "would_send" if dry_run else "sent", "item": item, "card": card}
    return {"status": "empty", "message": "no pending approval cards"}


def record_decision(approvals_dir: str | Path, item_id: str, action: str, actor: str = "operator", note: str | None = None) -> dict[str, Any]:
    action = action.lower().strip()
    if action not in VALID_DECISIONS:
        raise ValueError(f"invalid approval action: {action}")
    event = {
        "event": "approval_decision",
        "item_id": item_id,
        "action": action,
        "actor": actor,
        "note": note,
        "recorded_at": int(time.time()),
    }
    path = events_path(approvals_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, sort_keys=True) + "\n")
    return event


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dispatch one social approval card at a time")
    parser.add_argument("--queue-dir", action="append", dest="queue_dirs", help="Queue directory to scan; repeatable")
    parser.add_argument("--approvals-dir", default=str(DEFAULT_APPROVALS_DIR), help="Approval state directory")
    parser.add_argument("--tracker", help="Optional approval tracker Markdown table used to filter pending items")
    parser.add_argument("--dry-run", action="store_true", help="Render next card without writing registry")
    parser.add_argument("--json", action="store_true", help="Emit JSON result")
    parser.add_argument("--record-decision", choices=sorted(VALID_DECISIONS), help="Append a decision event instead of dispatching")
    parser.add_argument("--item-id", help="Item ID for --record-decision")
    parser.add_argument("--actor", default="operator")
    parser.add_argument("--note")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    approvals_dir = Path(args.approvals_dir)
    if args.record_decision:
        if not args.item_id:
            raise SystemExit("--item-id required with --record-decision")
        result = record_decision(approvals_dir, args.item_id, args.record_decision, args.actor, args.note)
    else:
        queue_dirs = [Path(p) for p in (args.queue_dirs or DEFAULT_QUEUE_DIRS)]
        result = dispatch_next(queue_dirs, approvals_dir, dry_run=args.dry_run, tracker_path=args.tracker)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result.get("card"):
        print(result["card"])
    elif result.get("status") not in {"waiting", "empty"}:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
