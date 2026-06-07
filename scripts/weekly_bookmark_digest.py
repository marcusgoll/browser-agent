#!/usr/bin/env python3
"""
Weekly X Bookmark Digest Generator

Reads the latest bookmark analysis and generates a formatted digest
that can be sent via email, Telegram, or saved to a file.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

OUTPUT_DIR = Path("/app/output")
DIGEST_DIR = Path("/app/output/digests")
WEEKLY_DIGEST_INPUT_SCHEMA_VERSION = "weekly-bookmark-digest-input/v1"
ROUTE_SECTIONS = ("immediate_actions", "research_queue", "knowledge_promotions", "project_routes")
RENDER_MAX_TOP_SIGNALS = 12


def get_latest_summary():
    """Get the most recent bookmark summary file."""
    files = glob.glob(str(OUTPUT_DIR / "bookmark_summary_*.json"))
    if not files:
        return None
    return max(files, key=os.path.getctime)


def generate_digest():
    """Generate a formatted digest from the latest analysis."""
    summary_file = get_latest_summary()
    if not summary_file:
        return "No bookmark analysis found."
    
    with open(summary_file) as f:
        data = json.load(f)
    
    lines = []
    lines.append("=" * 60)
    lines.append("X BOOKMARK WEEKLY DIGEST")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 60)
    lines.append("")
    
    # Summary stats
    total = data.get('total_processed', 0)
    lines.append(f"Bookmarks Processed: {total}")
    lines.append("")
    
    # By folder
    folders = data.get('by_folder', {})
    if folders:
        lines.append("Categories:")
        for folder, count in folders.items():
            lines.append(f"  • {folder}: {count}")
        lines.append("")

    edge_counts = data.get('edge_case_counts', {})
    if edge_counts:
        lines.append("Edge cases:")
        for key, count in edge_counts.items():
            lines.append(f"  • {key}: {count}")
        lines.append("")
    
    # Insights
    insights = data.get('insights', [])
    if insights:
        lines.append("KEY INSIGHTS")
        lines.append("-" * 40)
        for i, insight in enumerate(insights, 1):
            author = insight.get('author', 'Unknown')
            text = insight.get('insight', '')
            url = insight.get('url', '')
            lines.append(f"{i}. @{author}: {text}")
            if url:
                lines.append(f"   {url}")
            lines.append("")
    
    # Action items
    actions = data.get('action_items', [])
    if actions:
        lines.append("ACTION ITEMS")
        lines.append("-" * 40)
        for i, action in enumerate(actions, 1):
            author = action.get('author', 'Unknown')
            text = action.get('action', '')
            url = action.get('url', '')
            lines.append(f"{i}. @{author}: {text}")
            if url:
                lines.append(f"   {url}")
            lines.append("")
    
    lines.append("=" * 60)
    
    return "\n".join(lines)


def save_digest():
    """Generate and save the digest."""
    DIGEST_DIR.mkdir(exist_ok=True)
    
    digest = generate_digest()
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    digest_file = DIGEST_DIR / f"digest_{timestamp}.txt"
    
    with open(digest_file, 'w') as f:
        f.write(digest)
    
    print(f"Digest saved to: {digest_file}")
    print("\n" + digest)
    
    return str(digest_file)


def build_weekly_digest_input(week_start: str, *, output_dir: Path | str = OUTPUT_DIR) -> dict:
    """Build deterministic JSON-serializable input for a fixed bookmark digest week.

    The legacy no-argument digest path intentionally remains separate. Callers opt
    into this aggregation by passing an explicit ISO week_start; inclusion is based
    on artifact processing/generated dates, not the original tweet date.
    """
    start = _parse_iso_date(week_start, "week_start")
    end = start + timedelta(days=7)
    root = Path(output_dir)
    items: dict[str, dict] = {}
    source_counts = {
        "bookmark_summary_runs": 0,
        "bookmark_insights": 0,
        "action_items": 0,
        "route_items": 0,
        "task_items": 0,
        "learning_notes": 0,
        "content_ideas": 0,
    }
    source_files: set[str] = set()
    warnings: list[str] = []
    summary = {
        "total_processed": 0,
        "action_summary": {"ok": 0, "error": 0, "skipped": 0, "by_action": {}},
        "by_folder": {},
        "edge_case_counts": {},
    }

    for path in _weekly_files(root, "bookmark_summary_*.json", start, end):
        data = _read_json(path, warnings)
        if not isinstance(data, dict):
            continue
        source_counts["bookmark_summary_runs"] += 1
        source_files.add(_relative_path(path, root))
        summary["total_processed"] += _int(data.get("total_processed"))
        _merge_count_map(summary["by_folder"], data.get("by_folder") or {})
        _merge_count_map(summary["edge_case_counts"], data.get("edge_case_counts") or {})
        _merge_action_summary(summary["action_summary"], data.get("action_summary") or {})
        for insight in data.get("insights") or []:
            if not isinstance(insight, dict):
                _warn_non_object(warnings, "insight", path, root)
                continue
            source_counts["bookmark_insights"] += 1
            item = _digest_item(items, insight)
            _merge_item(
                item,
                author=insight.get("author"),
                insight=insight.get("insight"),
                signal="bookmark_insight",
                source_file=path,
                root=root,
            )
        for action in data.get("action_items") or []:
            if not isinstance(action, dict):
                _warn_non_object(warnings, "action item", path, root)
                continue
            source_counts["action_items"] += 1
            item = _digest_item(items, action)
            _merge_item(
                item,
                author=action.get("author"),
                action=action.get("action"),
                signal="action_item",
                source_file=path,
                root=root,
            )

    for path in _weekly_files(root / "opportunities", "opportunity_router_*.json", start, end):
        data = _read_json(path, warnings)
        if not isinstance(data, dict):
            continue
        source_files.add(_relative_path(path, root))
        for section in ROUTE_SECTIONS:
            for routed in data.get(section) or []:
                if not isinstance(routed, dict):
                    _warn_non_object(warnings, "route item", path, root, suffix=f"#{section}")
                    continue
                source_counts["route_items"] += 1
                item = _digest_item(items, routed)
                _merge_item(
                    item,
                    author=routed.get("author"),
                    folder=routed.get("folder"),
                    project=routed.get("project"),
                    insight=routed.get("insight"),
                    action=routed.get("action"),
                    why=routed.get("why") or routed.get("route_why"),
                    score=routed.get("score") if routed.get("score") is not None else routed.get("route_score"),
                    signal=f"route:{section}",
                    source_file=path,
                    root=root,
                )

    for path in _weekly_files(root / "opportunities", "high_roi_tasks_*.json", start, end):
        data = _read_json(path, warnings)
        if not isinstance(data, dict):
            continue
        source_files.add(_relative_path(path, root))
        for task in data.get("tasks") or []:
            if not isinstance(task, dict):
                _warn_non_object(warnings, "task item", path, root)
                continue
            source_counts["task_items"] += 1
            item = _digest_item(items, task)
            _merge_item(
                item,
                author=task.get("bookmark_author") or task.get("author"),
                folder=task.get("folder"),
                insight=task.get("insight"),
                action=task.get("suggested_action") or task.get("action") or task.get("title"),
                why=task.get("why"),
                score=task.get("score"),
                priority=task.get("priority"),
                signal="task",
                source_file=path,
                root=root,
            )

    for path in _weekly_note_files(root, start, end, warnings):
        metadata, sections = _read_learning_note(path, warnings)
        if not metadata:
            continue
        source_counts["learning_notes"] += 1
        source_files.add(_relative_path(path, root))
        item = _digest_item(items, metadata)
        _merge_item(
            item,
            author=metadata.get("author"),
            folder=metadata.get("project_bucket"),
            insight=sections.get("takeaway"),
            action=sections.get("action"),
            signal="learning_note",
            source_file=path,
            root=root,
        )

    for path, idea in _weekly_content_ideas(root, start, end, warnings):
        source_counts["content_ideas"] += 1
        source_files.add(_relative_path(path, root))
        item = _digest_item(items, idea)
        _merge_item(
            item,
            author=idea.get("author"),
            folder=idea.get("project_bucket") or idea.get("folder"),
            signal="content_idea",
            source_file=path,
            root=root,
        )
        _add_content_idea(item, idea)

    return {
        "schema_version": WEEKLY_DIGEST_INPUT_SCHEMA_VERSION,
        "week": {"week_start": start.isoformat(), "week_end": end.isoformat()},
        "generated_from": {
            "output_dir": str(root),
            "source_files": sorted(source_files),
        },
        "summary": {
            "total_processed": summary["total_processed"],
            "action_summary": {
                "ok": summary["action_summary"]["ok"],
                "error": summary["action_summary"]["error"],
                "skipped": summary["action_summary"]["skipped"],
                "by_action": _sorted_count_map(summary["action_summary"]["by_action"]),
            },
            "by_folder": _sorted_count_map(summary["by_folder"]),
            "edge_case_counts": _sorted_count_map(summary["edge_case_counts"]),
        },
        "source_counts": source_counts,
        "digest_items": [_finalize_item(item) for item in sorted(items.values(), key=_item_sort_key)],
        "warnings": sorted(warnings),
    }


def render_weekly_digest_input(payload: dict) -> str:
    """Render deterministic, send-ready text from weekly digest input."""
    week = payload.get("week") or {}
    summary = payload.get("summary") or {}
    source_counts = payload.get("source_counts") or {}
    lines = [
        "X BOOKMARK WEEKLY DIGEST",
        f"Week: {week.get('week_start', 'unknown')} to {week.get('week_end', 'unknown')}",
        "",
        "Summary",
        f"- Bookmarks processed: {_int(summary.get('total_processed'))}",
        f"- Categories: {_render_count_list(summary.get('by_folder') or {})}",
        f"- Sources: {_render_source_counts(source_counts)}",
    ]
    action_summary = _render_action_summary(summary.get("action_summary") or {})
    if action_summary:
        lines.append(f"- Actions: {action_summary}")
    edge_cases = _render_count_list(_nonzero_count_map(summary.get("edge_case_counts") or {}))
    if edge_cases != "none":
        lines.append(f"- Edge cases: {edge_cases}")
    lines.append("")

    items = sorted(_coalesced_render_items(payload.get("digest_items") or []), key=_rendered_item_sort_key)
    visible_items = items[:RENDER_MAX_TOP_SIGNALS]
    if len(items) > len(visible_items):
        lines.append(f"Top signals ({len(visible_items)} of {len(items)})")
    else:
        lines.append("Top signals")
    if not visible_items:
        lines.append("- No weekly digest signals found.")
    rendered_why: set[str] = set()
    for index, item in enumerate(visible_items, 1):
        insight = _first_text(item.get("insights") or [])
        action = _first_distinct_text(item.get("actions") or [], [insight])
        headline = insight or action or _content_idea_headline(item) or "Signal captured."
        why = _first_unseen_distinct_text(item.get("why") or [], [headline, action], rendered_why)
        author = _render_authors(item.get("authors") or [])
        lines.append(f"{index}. {author} — {headline}")
        if action:
            lines.append(f"   Action: {action}")
        if why:
            lines.append(f"   Why it matters: {why}")
        signals = _render_signals(item.get("signals") or [])
        if signals:
            lines.append(f"   Signals: {signals}")
        detail_line = _render_item_details(item)
        if detail_line:
            lines.append(f"   {detail_line}")
        content_idea = _render_content_idea(item)
        if content_idea:
            lines.append(f"   Content idea: {content_idea}")
        source_url = str(item.get("source_url") or "").strip()
        if source_url:
            lines.append(f"   Source: {source_url}")
        if index != len(visible_items):
            lines.append("")

    omitted_count = len(items) - len(visible_items)
    if omitted_count > 0:
        suffix = "item" if omitted_count == 1 else "items"
        lines.extend(["", f"Additional signals not shown: {omitted_count} lower-priority {suffix}."])

    warnings = [str(value) for value in payload.get("warnings") or [] if str(value).strip()]
    if warnings:
        lines.extend(["", "Warnings"])
        lines.extend(f"- {warning}" for warning in sorted(warnings))

    return "\n".join(lines)


def _render_count_list(counts: dict) -> str:
    entries = []
    for key in sorted(counts):
        value = counts[key]
        if isinstance(value, int) and not isinstance(value, bool):
            entries.append(f"{key} ({value})")
    return ", ".join(entries) if entries else "none"


def _render_source_counts(source_counts: dict) -> str:
    source_labels = (
        ("bookmark_summary_runs", "summaries"),
        ("bookmark_insights", "insights"),
        ("action_items", "actions"),
        ("route_items", "routes"),
        ("task_items", "tasks"),
        ("learning_notes", "learning notes"),
        ("content_ideas", "content ideas"),
    )
    parts = []
    for key, label in source_labels:
        parts.append(f"{label} {_int(source_counts.get(key))}")
    return ", ".join(parts)


def _render_action_summary(action_summary: dict) -> str:
    ok = _int(action_summary.get("ok"))
    errors = _int(action_summary.get("error"))
    skipped = _int(action_summary.get("skipped"))
    by_action = _nonzero_count_map(action_summary.get("by_action") or {})
    if not (ok or errors or skipped or by_action):
        return ""
    result = f"ok {ok}, errors {errors}, skipped {skipped}"
    action_counts = _render_plain_count_list(by_action)
    if action_counts:
        result += f"; {action_counts}"
    return result


def _render_plain_count_list(counts: dict) -> str:
    entries = []
    for key in sorted(counts):
        value = counts[key]
        if isinstance(value, int) and not isinstance(value, bool):
            entries.append(f"{key} {value}")
    return ", ".join(entries)


def _nonzero_count_map(counts: dict) -> dict:
    return {
        str(key): value
        for key, value in counts.items()
        if isinstance(value, int) and not isinstance(value, bool) and value > 0
    }


def _coalesced_render_items(raw_items: list) -> list[dict]:
    """Merge repeated rendered input records by the same source before display."""
    items: dict[str, dict] = {}
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        key = _dedupe_key(raw_item)
        item = items.get(key)
        if item is None:
            source_url = _normalize_url(_source_url(raw_item))
            item = {
                "id": raw_item.get("id") or f"weekly-digest-render-item-{hashlib.sha256(key.encode('utf-8')).hexdigest()[:12]}",
                "source_url": source_url,
                "authors": [],
                "folders": [],
                "projects": [],
                "signals": [],
                "top_score": 0,
                "priority": None,
                "insights": [],
                "actions": [],
                "why": [],
                "content_ideas": [],
                "source_files": [],
            }
            items[key] = item
        _merge_render_item(item, raw_item)
    return list(items.values())


def _merge_render_item(item: dict, raw_item: dict) -> None:
    for field in ("authors", "folders", "projects", "signals", "insights", "actions", "why", "source_files"):
        _extend_unique_text(item[field], raw_item.get(field) or [])
    for idea in raw_item.get("content_ideas") or []:
        if isinstance(idea, dict) and idea not in item["content_ideas"]:
            item["content_ideas"].append(idea)
    score = raw_item.get("top_score")
    if isinstance(score, (int, float)) and not isinstance(score, bool):
        item["top_score"] = max(item["top_score"], score)
    priority = raw_item.get("priority")
    if isinstance(priority, int) and not isinstance(priority, bool):
        item["priority"] = priority if item["priority"] is None else min(item["priority"], priority)
    source_url = _normalize_url(_source_url(raw_item))
    if source_url and not item.get("source_url"):
        item["source_url"] = source_url


def _extend_unique_text(target: list[str], values) -> None:
    if values is None or isinstance(values, bool):
        return
    if isinstance(values, (str, int, float)):
        iterable = [values]
    elif isinstance(values, (list, tuple, set)):
        iterable = values
    else:
        iterable = [values]
    for value in iterable:
        text = " ".join(str(value or "").split())
        if text and text not in target:
            target.append(text)


def _rendered_item_sort_key(item: dict) -> tuple:
    score = item.get("top_score")
    priority = item.get("priority")
    return (
        -(score if isinstance(score, (int, float)) and not isinstance(score, bool) else 0),
        priority if isinstance(priority, int) and not isinstance(priority, bool) else 999999,
        str(item.get("source_url") or ""),
        str(item.get("id") or ""),
    )


def _first_text(values: list) -> str:
    for value in values:
        text = " ".join(str(value or "").split())
        if text:
            return text
    return ""


def _first_distinct_text(values: list, prior_values: list[str]) -> str:
    prior = {_normalize_text(value) for value in prior_values if value}
    for value in values:
        text = " ".join(str(value or "").split())
        if text and _normalize_text(text) not in prior:
            return text
    return ""


def _first_unseen_distinct_text(values: list, prior_values: list[str], seen_values: set[str]) -> str:
    prior = {_normalize_text(value) for value in prior_values if value}
    for value in values:
        text = " ".join(str(value or "").split())
        normalized = _normalize_text(text)
        if text and normalized not in prior and normalized not in seen_values:
            seen_values.add(normalized)
            return text
    return ""


def _normalize_text(value: str) -> str:
    return " ".join(str(value or "").casefold().split()).rstrip(".")


def _content_idea_headline(item: dict) -> str:
    for idea in item.get("content_ideas") or []:
        if not isinstance(idea, dict):
            continue
        headline = _first_text([idea.get("hook"), idea.get("angle")])
        if headline:
            return headline
    return ""


def _render_authors(authors: list) -> str:
    rendered = []
    for author in authors:
        value = " ".join(str(author or "").split())
        if value:
            rendered.append(value if value.startswith("@") else f"@{value}")
    return ", ".join(rendered) if rendered else "Unknown source"


def _render_signals(signals: list) -> str:
    labels = []
    for signal in signals:
        text = str(signal or "")
        labels.append(
            {
                "action_item": "action item",
                "bookmark_insight": "bookmark insight",
                "content_idea": "content idea",
                "learning_note": "learning note",
                "route:immediate_actions": "immediate action",
                "route:knowledge_promotions": "knowledge promotion",
                "route:project_routes": "project route",
                "route:research_queue": "research queue",
                "task": "task",
            }.get(text, text.replace("_", " ").replace("route:", ""))
        )
    return ", ".join(dict.fromkeys(label for label in labels if label))


def _render_item_details(item: dict) -> str:
    details = []
    score = item.get("top_score")
    if isinstance(score, (int, float)) and not isinstance(score, bool) and score > 0:
        details.append(f"Score: {score:g}")
    folders = [str(value) for value in item.get("folders") or [] if str(value).strip()]
    if folders:
        details.append(f"Folder: {', '.join(folders)}")
    projects = [str(value) for value in item.get("projects") or [] if str(value).strip()]
    if projects:
        details.append(f"Project: {', '.join(projects)}")
    return " | ".join(details)


def _render_content_idea(item: dict) -> str:
    for idea in item.get("content_ideas") or []:
        if not isinstance(idea, dict):
            continue
        hook = _first_text([idea.get("hook")])
        angle = _first_text([idea.get("angle")])
        audience = _first_text([idea.get("audience")])
        if not hook:
            continue
        rendered = f'"{hook}"'
        if audience:
            rendered += f" for {audience}"
        if angle:
            rendered += f" — {angle}"
        return rendered
    return ""


def _parse_iso_date(value: str, field_name: str) -> date:
    if not value:
        raise ValueError(f"{field_name} is required")
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be YYYY-MM-DD") from exc


def _weekly_files(root: Path, pattern: str, start: date, end: date) -> list[Path]:
    if not root.exists():
        return []
    paths = []
    for path in root.glob(pattern):
        artifact_date = _date_from_filename(path)
        if artifact_date and start <= artifact_date < end:
            paths.append(path)
    return sorted(paths, key=lambda path: path.as_posix())


def _date_from_filename(path: Path) -> date | None:
    match = re.search(r"(20\d{2})[-_]?([01]\d)[-_]?([0-3]\d)", path.name)
    if not match:
        return None
    year, month, day = match.groups()
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def _read_json(path: Path, warnings: list[str]):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        warnings.append(f"skipped unreadable JSON {path}: {exc}")
        return None


def _relative_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _int(value) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _merge_count_map(target: dict, source: dict) -> None:
    for key, value in source.items():
        if isinstance(value, int) and not isinstance(value, bool):
            target[str(key)] = target.get(str(key), 0) + value


def _merge_action_summary(target: dict, source: dict) -> None:
    for key in ("ok", "error", "skipped"):
        target[key] += _int(source.get(key))
    _merge_count_map(target["by_action"], source.get("by_action") or {})


def _sorted_count_map(values: dict) -> dict:
    return {key: values[key] for key in sorted(values)}


def _source_url(item: dict) -> str:
    return str(item.get("source_url") or item.get("url") or "")


def _normalize_url(value: str) -> str:
    url = str(value or "").strip()
    if not url:
        return ""
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return url.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "", ""))


def _dedupe_key(item: dict) -> str:
    normalized_url = _normalize_url(_source_url(item))
    if normalized_url:
        return f"url:{normalized_url}"
    for key in ("source_id", "source_item_id", "cache_key", "id"):
        value = str(item.get(key) or "").strip()
        if value:
            return f"{key}:{value}"
    seed = json.dumps(item, sort_keys=True, default=str)
    return f"hash:{hashlib.sha256(seed.encode('utf-8')).hexdigest()}"


def _digest_item(items: dict[str, dict], source: dict) -> dict:
    key = _dedupe_key(source)
    item = items.get(key)
    if item is None:
        source_url = _normalize_url(_source_url(source))
        item = {
            "id": f"weekly-digest-item-{hashlib.sha256(key.encode('utf-8')).hexdigest()[:12]}",
            "source_url": source_url,
            "authors": set(),
            "folders": set(),
            "projects": set(),
            "signals": set(),
            "insights": set(),
            "actions": set(),
            "why": set(),
            "scores": [],
            "priority": None,
            "content_ideas": [],
            "source_files": set(),
        }
        items[key] = item
    return item


def _merge_item(
    item: dict,
    *,
    author=None,
    folder=None,
    project=None,
    insight=None,
    action=None,
    why=None,
    score=None,
    priority=None,
    signal=None,
    source_file: Path | None = None,
    root: Path | None = None,
) -> None:
    _add_text(item["authors"], author)
    _add_text(item["folders"], folder)
    _add_text(item["projects"], project)
    _add_text(item["signals"], signal)
    _add_text(item["insights"], insight)
    _add_text(item["actions"], action)
    _add_text(item["why"], why)
    if isinstance(score, (int, float)) and not isinstance(score, bool):
        item["scores"].append(score)
    if isinstance(priority, int) and not isinstance(priority, bool):
        item["priority"] = priority if item["priority"] is None else min(item["priority"], priority)
    if source_file is not None and root is not None:
        item["source_files"].add(_relative_path(source_file, root))


def _add_text(target: set[str], value) -> None:
    text = " ".join(str(value or "").split())
    if text:
        target.add(text)


def _weekly_note_files(root: Path, start: date, end: date, warnings: list[str]) -> list[Path]:
    paths: list[Path] = []
    for dirname in ("learning_notes", "notes"):
        note_dir = root / dirname
        if not note_dir.exists():
            continue
        for path in sorted(note_dir.glob("*.md"), key=lambda value: value.as_posix()):
            metadata, _sections = _read_learning_note(path, warnings)
            generated_on = _maybe_date(metadata.get("generated_on") if metadata else None)
            if generated_on and start <= generated_on < end:
                paths.append(path)
    return paths


def _read_learning_note(path: Path, warnings: list[str]) -> tuple[dict, dict]:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        warnings.append(f"skipped unreadable note {path}: {exc}")
        return {}, {}
    metadata: dict[str, str] = {}
    lines = content.splitlines()
    if lines[:1] == ["---"]:
        for line in lines[1:]:
            if line == "---":
                break
            key, sep, raw_value = line.partition(":")
            if sep:
                metadata[key.strip()] = _front_matter_value(raw_value.strip())
    return metadata, _markdown_sections(content)


def _front_matter_value(raw_value: str) -> str:
    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError:
        value = raw_value.strip('"')
    return str(value)


def _markdown_sections(content: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current = None
    for line in content.splitlines():
        if line.startswith("## "):
            current = line[3:].strip().lower()
            sections[current] = []
            continue
        if current:
            sections[current].append(line)
    return {key: " ".join("\n".join(value).split()) for key, value in sections.items()}


def _weekly_content_ideas(root: Path, start: date, end: date, warnings: list[str]) -> list[tuple[Path, dict]]:
    ideas: list[tuple[Path, dict]] = []
    for dirname in ("content_ideas", "ideas"):
        idea_dir = root / dirname
        if not idea_dir.exists():
            continue
        for path in sorted(idea_dir.glob("*.json"), key=lambda value: value.as_posix()):
            data = _read_json(path, warnings)
            for idea in _idea_records(data, warnings=warnings, source_path=path, root=root):
                generated_on = _maybe_date(idea.get("generated_on") or idea.get("generated") or idea.get("date"))
                if not generated_on:
                    generated_on = _date_from_filename(path)
                if generated_on and start <= generated_on < end:
                    ideas.append((path, idea))
    return ideas


def _idea_records(
    data,
    *,
    warnings: list[str] | None = None,
    source_path: Path | None = None,
    root: Path | None = None,
) -> list[dict]:
    if isinstance(data, list):
        records = data
    elif isinstance(data, dict):
        if not isinstance(data.get("ideas"), list):
            return [data]
        records = data["ideas"]
    else:
        return []

    ideas = []
    for item in records:
        if isinstance(item, dict):
            ideas.append(item)
        elif warnings is not None and source_path is not None and root is not None:
            _warn_non_object(warnings, "content idea", source_path, root)
    return ideas


def _warn_non_object(warnings: list[str], label: str, path: Path, root: Path, *, suffix: str = "") -> None:
    warnings.append(f"skipped non-object {label} in {_relative_path(path, root)}{suffix}")


def _maybe_date(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _add_content_idea(item: dict, idea: dict) -> None:
    rendered = {
        "hook": str(idea.get("hook") or ""),
        "angle": str(idea.get("angle") or ""),
        "audience": str(idea.get("audience") or ""),
        "proof_point": str(idea.get("proof_point") or idea.get("proof") or ""),
    }
    if any(rendered.values()) and rendered not in item["content_ideas"]:
        item["content_ideas"].append(rendered)


def _item_sort_key(item: dict) -> tuple:
    top_score = max(item["scores"]) if item["scores"] else 0
    priority = item["priority"] if item["priority"] is not None else 999999
    return (-top_score, priority, item["source_url"], item["id"])


def _finalize_item(item: dict) -> dict:
    top_score = max(item["scores"]) if item["scores"] else 0
    result = {
        "id": item["id"],
        "source_url": item["source_url"],
        "authors": sorted(item["authors"]),
        "folders": sorted(item["folders"]),
        "projects": sorted(item["projects"]),
        "signals": sorted(item["signals"]),
        "top_score": top_score,
        "priority": item["priority"],
        "insights": sorted(item["insights"]),
        "actions": sorted(item["actions"]),
        "why": sorted(item["why"]),
        "content_ideas": sorted(item["content_ideas"], key=lambda value: json.dumps(value, sort_keys=True)),
        "source_files": sorted(item["source_files"]),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate X bookmark weekly digest artifacts.")
    parser.add_argument("--week-start", help="Explicit YYYY-MM-DD week start for rendered digest aggregation.")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR), help="Bookmark output directory to read for --week-start.")
    parser.add_argument("--json", action="store_true", help="Print deterministic digest input JSON instead of rendered text.")
    args = parser.parse_args()
    if args.week_start:
        payload = build_weekly_digest_input(args.week_start, output_dir=Path(args.output_dir))
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(render_weekly_digest_input(payload))
        return 0
    save_digest()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
