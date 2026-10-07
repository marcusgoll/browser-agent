#!/usr/bin/env python3
"""
Feed Bookmark Insights to Other Agents

Reads the latest bookmark analysis and creates actionable tasks for other agents:
- DevOps agent: Infrastructure/tooling improvements
- PBS agent: Schedule/trading related insights
- Logbook agent: Currency/credential related insights
- Research agent: Deep-dive topics
"""
import json
import glob
import hashlib
import os
import re
from datetime import datetime
from pathlib import Path

OUTPUT_DIR = Path("/app/output")
AGENT_TASKS_DIR = Path("/app/output/agent_tasks")
OPPORTUNITY_DIR = Path("/app/output/opportunities")
LEARNING_NOTES_DIR = Path("/app/output/learning_notes")
LEARNING_NOTE_SCHEMA_VERSION = "learning-note/v1"
LEARNING_NOTE_METADATA_FIELDS = (
    "schema_version",
    "id",
    "source_item_id",
    "source_url",
    "author",
    "project_bucket",
    "source_section",
    "generated_on",
)
LEARNING_NOTE_DISABLED_VALUES = {"0", "false", "no", "off"}
TRIAGE_SCORER_MODE_ENV = "BOOKMARK_TRIAGE_SCORER"
TRIAGE_SECTION_THRESHOLDS = {
    "immediate_actions": 12,
    "research_queue": 10,
    "knowledge_promotions": 10,
}

ACTIVE_PROJECT_KEYWORDS = {
    'hermes': 8, 'agent': 8, 'agents': 8, 'memory': 7, 'context': 7,
    'llm': 6, 'codex': 6, 'automation': 6, 'trading': 8, 'financial': 7,
    'stock': 7, 'alpaca': 9, 'ross': 9, 'paper': 5, 'wiki': 6,
    'knowledge': 5, 'obsidian': 5, 'devops': 6, 'infrastructure': 6,
    'monitoring': 5, 'codebase': 5, 'testing': 5,
}
IMMEDIATE_KEYWORDS = {
    'update': 5, 'add': 5, 'patch': 6, 'implement': 6, 'test': 5,
    'monitoring': 5, 'docs': 4, 'wiki': 4, 'script': 5,
}
RESEARCH_KEYWORDS = {
    'research': 5, 'compare': 5, 'evaluate': 5, 'investigate': 5,
    'study': 4, 'financial': 4, 'trading': 4, 'stock': 4,
}
KNOWLEDGE_KEYWORDS = {
    'concept': 4, 'framework': 5, 'layers': 5, 'pattern': 5, 'memory': 5,
    'context': 5, 'knowledge': 5, 'fundamentals': 4, 'architecture': 5,
}

PROJECT_ROUTE_PRIMARY_MIN_SCORE = 15
PROJECT_ROUTE_SECONDARY_MIN_SCORE = 10
PROJECT_ROUTE_MAX_SECONDARIES = 1
PROJECT_ROUTE_RULES = {
    'hermes_agent': {
        'keywords': {
            'agent': 8, 'agents': 8, 'memory': 7, 'context': 7, 'llm': 6,
            'codex': 6, 'automation': 6, 'autonomous': 5,
        },
        'folders': {'ai_tools': 3, 'coding': 2},
    },
    'trading_research': {
        'keywords': {
            'trading': 8, 'financial': 7, 'finance': 7, 'stock': 7,
            'alpaca': 9, 'ross': 9, 'paper': 5, 'theses': 5,
        },
        'folders': {'business': 2, 'ai_tools': 1},
    },
    'devops_infrastructure': {
        'keywords': {
            'devops': 8, 'infrastructure': 8, 'monitoring': 6, 'docker': 6,
            'deploy': 6, 'server': 5, 'ci': 5, 'security': 5,
        },
        'folders': {'devops': 3, 'coding': 1},
    },
    'knowledge_base': {
        'keywords': {
            'knowledge': 6, 'wiki': 6, 'obsidian': 6, 'concept': 5,
            'framework': 5, 'layers': 5, 'memory': 5, 'context': 5,
            'architecture': 5,
        },
        'folders': {'ai_tools': 1, 'productivity': 1},
    },
    'product_design': {
        'keywords': {
            'css': 8, 'ui': 7, 'ux': 7, 'transition': 6, 'transitions': 6,
            'easing': 6, 'animation': 5, 'interface': 5,
        },
        'folders': {'design': 3},
    },
    'aviation_ops': {
        'keywords': {
            'aviation': 8, 'flying': 8, 'flight': 8, 'faa': 7,
            'logbook': 7, 'currency': 6, 'credential': 6,
        },
        'folders': {'aviation': 3},
    },
    'business_ops': {
        'keywords': {
            'business': 7, 'entrepreneurship': 7, 'sales': 6, 'marketing': 6,
            'customer': 5, 'revenue': 5,
        },
        'folders': {'business': 3},
    },
}

def get_latest_summary():
    files = glob.glob(str(OUTPUT_DIR / "bookmark_summary_*.json"))
    if not files:
        return None
    return max(files, key=os.path.getctime)

def get_latest_analysis():
    files = glob.glob(str(OUTPUT_DIR / "bookmark_analysis_*.json"))
    if not files:
        return None
    return max(files, key=os.path.getctime)

def _keyword_score(text, weights):
    text = text.lower()
    return sum(weight for keyword, weight in weights.items() if keyword in text)

def _analysis_by_url(analysis):
    return {item.get('url'): item for item in analysis or [] if item.get('url')}

def _is_deleted_or_low_value(record):
    if not record:
        return False
    if record.get('folder') == 'delete' or record.get('deleted'):
        return True
    action = record.get('action_result') or {}
    return action.get('action') == 'delete' and action.get('status') == 'ok'


def _contains_route_keyword(text, keyword):
    pattern = rf"(?<![A-Za-z0-9_]){re.escape(keyword.lower())}(?![A-Za-z0-9_])"
    return re.search(pattern, text.lower()) is not None


def _project_keyword_matches(text, weights):
    return [keyword for keyword in weights if _contains_route_keyword(text, keyword)]


def _project_route_scores(text, folder=None):
    scores = []
    for project, rule in PROJECT_ROUTE_RULES.items():
        matches = _project_keyword_matches(text, rule['keywords'])
        if not matches:
            continue
        score = sum(rule['keywords'][keyword] for keyword in matches)
        folder_bonus = (rule.get('folders') or {}).get(str(folder), 0) if folder else 0
        score += folder_bonus
        scores.append({
            'project': project,
            'score': score,
            'matched_keywords': sorted(matches),
            'folder': folder,
            'folder_bonus': folder_bonus,
        })
    return sorted(scores, key=lambda item: (-item['score'], item['project']))


def _route_rationale(prefix, route_score):
    evidence = ", ".join(route_score['matched_keywords'])
    if route_score.get('folder_bonus'):
        evidence = f"{evidence}; folder signal {route_score.get('folder')}"
    return f"{prefix} justified by {evidence}."


def build_project_routes(summary, analysis):
    """Assign optional fixed project buckets without changing opportunity sections."""
    records = _analysis_by_url(analysis)
    actions_by_url = {item.get('url'): item.get('action', '') for item in summary.get('action_items', []) if item.get('url')}
    routes = []
    for item in summary.get('insights', []):
        url = item.get('url', '')
        record = records.get(url, {})
        if _is_deleted_or_low_value(record):
            continue
        insight = item.get('insight', '')
        action = actions_by_url.get(url, '')
        if not insight and not action:
            continue
        folder = record.get('folder') if record else None
        route_scores = _project_route_scores(f"{insight} {action}", folder)
        if not route_scores or route_scores[0]['score'] < PROJECT_ROUTE_PRIMARY_MIN_SCORE:
            continue
        primary = route_scores[0]
        secondary_routes = []
        for secondary in route_scores[1:]:
            if len(secondary_routes) >= PROJECT_ROUTE_MAX_SECONDARIES:
                break
            if secondary['score'] < PROJECT_ROUTE_SECONDARY_MIN_SCORE:
                continue
            secondary_routes.append({
                'project': secondary['project'],
                'score': secondary['score'],
                'why': _route_rationale('secondary route', secondary),
            })
        routes.append({
            'author': item.get('author', 'Unknown'),
            'insight': insight,
            'action': action,
            'url': url,
            'folder': folder,
            'project': primary['project'],
            'route_score': primary['score'],
            'route_why': _route_rationale('primary route', primary),
            'secondary_routes': secondary_routes,
        })
    return sorted(routes, key=lambda item: (-item['route_score'], item['url']))


def _section_item(author, insight, action, url, record, section):
    combined = f"{insight} {action}"
    base_score = _keyword_score(combined, ACTIVE_PROJECT_KEYWORDS)
    if section == 'immediate_actions':
        score = base_score + _keyword_score(action, IMMEDIATE_KEYWORDS)
        why = 'Relevant to active Hermes/trading/devops work and has an executable next step.'
    elif section == 'research_queue':
        score = base_score + _keyword_score(action, RESEARCH_KEYWORDS)
        why = 'Potentially useful but should be researched before changing systems.'
    else:
        score = base_score + _keyword_score(combined, KNOWLEDGE_KEYWORDS)
        why = 'Durable concept worth promoting into wiki/skills if still novel after dedupe.'
    folder = record.get('folder') if record else None
    if folder in ('ai_tools', 'coding', 'devops'):
        score += 3
    if folder in ('business', 'productivity', 'design'):
        score += 1
    source_item_id = (
        (record or {}).get('source_item_id')
        or (record or {}).get('source_id')
        or (record or {}).get('id')
        or (record or {}).get('tweet_id')
    )
    item = {
        'source_item_id': source_item_id,
        'author': author,
        'insight': insight,
        'action': action,
        'url': url,
        'folder': folder,
        'score': score,
        'why': why,
    }
    if os.environ.get(TRIAGE_SCORER_MODE_ENV, 'deterministic').strip().lower() != 'legacy':
        threshold = TRIAGE_SECTION_THRESHOLDS[section]
        reason_codes = []
        if any(keyword in combined.lower() for keyword in ACTIVE_PROJECT_KEYWORDS):
            reason_codes.append('active_project:agent')
        reason_codes.append(f"threshold:{section}:{'met' if score >= threshold else 'missed'}")
        item.update({
            'threshold': threshold,
            'passes_threshold': score >= threshold,
            'reason_codes': reason_codes,
            'why': f"{why} Reason codes: {', '.join(reason_codes)}",
        })
    return item

def build_opportunity_router(summary, analysis, limit_per_section=5):
    """Rank bookmark insights into concrete high-ROI sections."""
    records = _analysis_by_url(analysis)
    actions_by_url = {item.get('url'): item.get('action', '') for item in summary.get('action_items', []) if item.get('url')}
    scorer_mode = os.environ.get(TRIAGE_SCORER_MODE_ENV, 'deterministic').strip().lower()
    if scorer_mode not in {'deterministic', 'legacy'}:
        scorer_mode = 'deterministic'
    routed = {
        'triage_scorer': scorer_mode,
        'generated_from': 'x_bookmark_analysis',
        'total_processed': summary.get('total_processed', 0),
        'action_summary': summary.get('action_summary', {}),
        'immediate_actions': [],
        'research_queue': [],
        'knowledge_promotions': [],
        'project_routes': build_project_routes(summary, analysis),
        'skipped': {'deleted_or_low_value': 0, 'unscored': 0},
    }

    for item in summary.get('insights', []):
        url = item.get('url', '')
        record = records.get(url, {})
        if _is_deleted_or_low_value(record):
            routed['skipped']['deleted_or_low_value'] += 1
            continue
        insight = item.get('insight', '')
        action = actions_by_url.get(url, '')
        author = item.get('author', 'Unknown')
        if not insight and not action:
            routed['skipped']['unscored'] += 1
            continue

        immediate = _section_item(author, insight, action, url, record, 'immediate_actions')
        research = _section_item(author, insight, action, url, record, 'research_queue')
        knowledge = _section_item(author, insight, action, url, record, 'knowledge_promotions')

        if immediate['score'] >= TRIAGE_SECTION_THRESHOLDS['immediate_actions'] and action:
            routed['immediate_actions'].append(immediate)
        if research['score'] >= TRIAGE_SECTION_THRESHOLDS['research_queue']:
            routed['research_queue'].append(research)
        if knowledge['score'] >= TRIAGE_SECTION_THRESHOLDS['knowledge_promotions']:
            routed['knowledge_promotions'].append(knowledge)

    fallback_items = []
    for item in summary.get('insights', []):
        url = item.get('url', '')
        record = records.get(url, {})
        if _is_deleted_or_low_value(record):
            continue
        fallback_items.append(_section_item(item.get('author', 'Unknown'), item.get('insight', ''), actions_by_url.get(url, ''), url, record, 'knowledge_promotions'))
    fallback_items.sort(key=lambda item: item['score'], reverse=True)
    for section in ('immediate_actions', 'research_queue', 'knowledge_promotions'):
        if not routed[section]:
            routed[section] = fallback_items[:limit_per_section]
        routed[section] = sorted(routed[section], key=lambda item: item['score'], reverse=True)[:limit_per_section]
    return routed


def _task_id(item):
    seed = "|".join([item.get('url', ''), item.get('action', ''), item.get('insight', '')])
    return f"x-bookmark-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:12]}"


def _canonical_source_id(item):
    for key in ('canonical_id', 'source_id', 'source_item_id', 'bookmark_id', 'tweet_id', 'id'):
        value = str(item.get(key) or '').strip()
        if value:
            return value
    source_url = _learning_note_source_url(item)
    match = re.search(r"/(?:i/web/)?status(?:es)?/(\d+)", source_url)
    if match:
        return match.group(1)
    raise ValueError("learning note requires a canonical source/bookmark id")


def _learning_note_id(item):
    return _canonical_source_id(item)


def _learning_note_source_url(item):
    return str(item.get('source_url') or item.get('url') or '')


def _learning_note_project_bucket(item):
    return str(item.get('project_bucket') or item.get('project') or item.get('folder') or item.get('source_section') or 'unassigned')


def _safe_note_filename(source_item_id):
    safe = ''.join(char if char.isalnum() or char in ('-', '_', '.') else '-' for char in source_item_id).strip('.-')
    return f"{safe or 'learning-note'}.md"


def _one_line(value):
    return " ".join(str(value or '').split())


def _learning_note_front_matter(metadata):
    lines = ["---"]
    for key in LEARNING_NOTE_METADATA_FIELDS:
        lines.append(f"{key}: {json.dumps(str(metadata[key]))}")
    lines.append("---")
    return "\n".join(lines)


def parse_learning_note_metadata(content):
    """Parse round-trippable learning note front matter without a YAML dependency."""
    lines = content.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("learning note is missing front matter")
    metadata = {}
    for line in lines[1:]:
        if line == "---":
            break
        key, sep, raw_value = line.partition(":")
        if not sep:
            raise ValueError(f"invalid learning note metadata line: {line}")
        metadata[key] = json.loads(raw_value.strip())
    required = list(LEARNING_NOTE_METADATA_FIELDS)
    missing = [key for key in required if key not in metadata]
    if missing:
        raise ValueError(f"learning note metadata missing fields: {', '.join(missing)}")
    return {key: metadata[key] for key in required}


def build_learning_note_artifact(item, generated_on):
    """Render one concise learning note artifact from a routed bookmark item."""
    source_item_id = _learning_note_id(item)
    metadata = {
        "schema_version": LEARNING_NOTE_SCHEMA_VERSION,
        "id": source_item_id,
        "source_item_id": source_item_id,
        "source_url": _learning_note_source_url(item),
        "author": str(item.get('author') or 'Unknown'),
        "project_bucket": _learning_note_project_bucket(item),
        "source_section": str(item.get('source_section') or 'unassigned'),
        "generated_on": str(generated_on),
    }
    takeaway = _one_line(item.get('insight') or item.get('title') or metadata["source_url"])
    action = _one_line(item.get('action') or item.get('suggested_action') or 'Review the source and decide whether it belongs in the project notes.')
    why_now = _one_line(item.get('why') or f"Routed to {metadata['project_bucket']} for review.")
    title = takeaway[:120] or "Learning note"
    content = "\n".join([
        _learning_note_front_matter(metadata),
        f"# {title}",
        "",
        "## Takeaway",
        takeaway,
        "",
        "## Action",
        action,
        "",
        "## Why now",
        why_now,
        "",
        f"Source: {metadata['source_url']}",
    ]) + "\n"
    return {
        "filename": _safe_note_filename(source_item_id),
        "metadata": metadata,
        "content": content,
    }


def build_learning_note_artifacts(routed, generated_on):
    """Render learning note artifacts from the same routed sections used by the opportunity memo."""
    artifacts = []
    seen_note_ids = set()
    for section in ("immediate_actions", "research_queue", "knowledge_promotions"):
        for item in routed.get(section) or []:
            note_item = dict(item)
            note_item.setdefault('source_section', section)
            note_id = _learning_note_id(note_item)
            if note_id in seen_note_ids:
                continue
            seen_note_ids.add(note_id)
            artifacts.append(build_learning_note_artifact(note_item, generated_on=generated_on))
    return artifacts


def write_learning_note_artifacts(artifacts, notes_dir):
    """Persist note artifacts, updating an existing canonical note file instead of duplicating it."""
    notes_dir = Path(notes_dir)
    notes_dir.mkdir(parents=True, exist_ok=True)
    result = {"inserted": 0, "updated": 0, "noop": 0, "files": []}
    seen_filenames = set()
    for artifact in artifacts or []:
        metadata = artifact.get("metadata") or {}
        source_item_id = str(metadata.get("source_item_id") or metadata.get("id") or "")
        filename = artifact.get("filename") or _safe_note_filename(source_item_id)
        if filename in seen_filenames:
            continue
        seen_filenames.add(filename)
        path = notes_dir / filename
        content = artifact["content"]
        action = "inserted"
        if path.exists():
            action = "noop" if path.read_text(encoding="utf-8") == content else "updated"
        if action != "noop":
            path.write_text(content, encoding="utf-8")
        result[action] += 1
        result["files"].append(str(path))
    return result


def learning_notes_enabled(environ=None):
    environ = os.environ if environ is None else environ
    value = str(environ.get("BOOKMARK_LEARNING_NOTES_ENABLED", "1")).strip().lower()
    return value not in LEARNING_NOTE_DISABLED_VALUES


def write_learning_notes_from_routed(routed, generated_on, notes_dir, enabled=True):
    """Write learning notes from routed bookmarks, with a rollback switch for the memo-only path."""
    if not enabled:
        return {"enabled": False, "artifacts": 0, "inserted": 0, "updated": 0, "noop": 0, "files": []}
    artifacts = build_learning_note_artifacts(routed, generated_on=generated_on)
    result = write_learning_note_artifacts(artifacts, notes_dir)
    return {"enabled": True, "artifacts": len(artifacts), **result}


def _task_type_for_section(section):
    if section == 'immediate_actions':
        return 'implementation'
    if section == 'research_queue':
        return 'research'
    return 'knowledge_promotion'


def _title_from_item(item, task_type):
    action = " ".join((item.get('action') or item.get('insight') or '').split())
    prefix = {
        'implementation': 'Execute',
        'research': 'Research',
        'knowledge_promotion': 'Promote knowledge from',
    }[task_type]
    if not action:
        action = item.get('url', 'bookmark opportunity')
    return f"{prefix}: {action[:96]}"


def _deliverable_for_task(item, task_type):
    if task_type == 'implementation':
        return 'A small patch, test, config update, or operator note that directly applies the bookmark action.'
    if task_type == 'research':
        return 'A concise research note comparing the source against active Hermes/trading/wiki work, with adopt/skip recommendation.'
    return 'A deduped wiki/skill promotion candidate with source link, durable concept summary, and novelty check.'


def build_high_roi_task_queue(routed, limit=10):
    """Convert routed bookmark opportunities into a safe operator task queue."""
    section_weights = {
        'immediate_actions': 300,
        'research_queue': 200,
        'knowledge_promotions': 100,
    }
    candidates = []
    seen_ids = set()
    for section, weight in section_weights.items():
        for item in routed.get(section, []) or []:
            task_type = _task_type_for_section(section)
            task = {
                'id': _task_id(item),
                'status': 'proposed',
                'source_section': section,
                'task_type': task_type,
                'title': _title_from_item(item, task_type),
                'deliverable': _deliverable_for_task(item, task_type),
                'bookmark_author': item.get('author', 'Unknown'),
                'source_url': item.get('url', ''),
                'folder': item.get('folder'),
                'score': item.get('score', 0),
                'ranking_score': weight + item.get('score', 0),
                'insight': item.get('insight', ''),
                'suggested_action': item.get('action', ''),
                'why': item.get('why', ''),
                'safety': {'auto_execute': False, 'requires_human_review': True},
            }
            if task['id'] in seen_ids:
                continue
            seen_ids.add(task['id'])
            candidates.append(task)
    candidates.sort(key=lambda task: (-task['ranking_score'], task['id']))
    tasks = candidates[:limit]
    for priority, task in enumerate(tasks, 1):
        task['priority'] = priority
        task.pop('ranking_score', None)
    return tasks


def render_high_roi_task_list(tasks, today):
    lines = [
        f"# High-ROI X Bookmark Tasks - {today}",
        "",
        "Operator task queue generated from the opportunity router.",
        "",
        "## Safety",
        "- auto_execute: false",
        "- requires_human_review: true",
        "- destructive_actions: false",
        "",
        "## Tasks",
    ]
    if not tasks:
        lines.append("- None")
        return "\n".join(lines)
    for task in tasks:
        lines.extend([
            f"{task['priority']}. [{task['task_type']}] {task['title']}",
            f"   - id: {task['id']}",
            f"   - status: {task['status']}",
            f"   - score: {task['score']} ({task['source_section']})",
            f"   - deliverable: {task['deliverable']}",
            f"   - source: {task['source_url']}",
            f"   - why: {task.get('why', '')}",
            "",
        ])
    return "\n".join(lines)


def render_opportunity_memo(routed, today):
    lines = []
    lines.append(f"# X Bookmark Opportunity Router - {today}")
    lines.append("")
    lines.append("Generated from latest X bookmark analysis.")
    lines.append("")
    lines.append("## Action summary")
    action_summary = routed.get('action_summary') or {}
    lines.append(f"- total_processed: {routed.get('total_processed', 0)}")
    lines.append(f"- ok: {action_summary.get('ok', 0)}")
    lines.append(f"- error: {action_summary.get('error', 0)}")
    lines.append(f"- skipped: {action_summary.get('skipped', 0)}")
    for key, value in sorted((routed.get('skipped') or {}).items()):
        lines.append(f"- {key}: {value}")
    lines.append("")

    sections = [
        ('immediate_actions', 'Immediate executable actions'),
        ('research_queue', 'Research queue'),
        ('knowledge_promotions', 'Knowledge-base promotions'),
    ]
    for key, title in sections:
        lines.append(f"## {title}")
        items = routed.get(key) or []
        if not items:
            lines.append("- None")
            lines.append("")
            continue
        for index, item in enumerate(items, 1):
            lines.append(f"{index}. score={item['score']} @{item['author']}")
            if item.get('action'):
                lines.append(f"   - action: {item['action']}")
            lines.append(f"   - insight: {item.get('insight', '')}")
            lines.append(f"   - why: {item.get('why', '')}")
            lines.append(f"   - source: {item.get('url', '')}")
        lines.append("")

    lines.append("## Project routes")
    project_routes = routed.get('project_routes') or []
    if not project_routes:
        lines.append("- None; no explicit project rule met the routing threshold.")
    for index, route in enumerate(project_routes, 1):
        lines.append(f"{index}. primary: {route['project']} score={route['route_score']} @{route['author']}")
        lines.append(f"   - why: {route.get('route_why', '')}")
        for secondary in route.get('secondary_routes') or []:
            lines.append(f"   - secondary: {secondary['project']} score={secondary['score']}")
            lines.append(f"     - why: {secondary.get('why', '')}")
        lines.append(f"   - source: {route.get('url', '')}")
    lines.append("")
    return "\n".join(lines)

def categorize_for_agents(insight, action):
    """Determine which agent should handle this insight."""
    text = (insight + " " + action).lower()
    
    agents = []
    
    # DevOps triggers
    if any(kw in text for kw in ['infrastructure', 'docker', 'server', 'deploy', 'ci/cd', 'monitoring', 'security', 'homelab', 'vps', 'container']):
        agents.append('devops')
    
    # PBS triggers
    if any(kw in text for kw in ['schedule', 'bid', 'trade', 'flica', 'pairing', 'crew', 'airline', 'seniority']):
        agents.append('pbs')
    
    # Logbook triggers
    if any(kw in text for kw in ['logbook', 'currency', 'credential', 'faa', 'flight', 'duty', 'block']):
        agents.append('logbook')
    
    # Research triggers (default for AI, coding, business)
    if any(kw in text for kw in ['ai', 'agent', 'codex', 'llm', 'research', 'study', 'investigate']):
        agents.append('research')
    
    # Coding triggers
    if any(kw in text for kw in ['code', 'programming', 'development', 'software', 'api', 'framework']):
        agents.append('coding')
    
    if not agents:
        agents.append('research')  # Default
    
    return agents

def generate_agent_tasks():
    """Generate task files for other agents."""
    summary_file = get_latest_summary()
    if not summary_file:
        print("No bookmark analysis found.")
        return
    
    with open(summary_file) as f:
        summary = json.load(f)

    analysis_file = get_latest_analysis()
    analysis = []
    if analysis_file:
        with open(analysis_file) as f:
            analysis = json.load(f)
    
    AGENT_TASKS_DIR.mkdir(exist_ok=True)
    OPPORTUNITY_DIR.mkdir(exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    
    tasks_by_agent = {
        'devops': [],
        'pbs': [],
        'logbook': [],
        'research': [],
        'coding': []
    }
    
    # Categorize insights
    for insight in summary.get('insights', []):
        text = insight.get('insight', '')
        action = ''
        
        # Find matching action item
        for act in summary.get('action_items', []):
            if act.get('url') == insight.get('url'):
                action = act.get('action', '')
                break
        
        agents = categorize_for_agents(text, action)
        
        for agent in agents:
            tasks_by_agent[agent].append({
                'insight': text,
                'action': action,
                'source': insight.get('url', ''),
                'author': insight.get('author', 'Unknown')
            })
    
    # Write task files
    for agent, tasks in tasks_by_agent.items():
        if tasks:
            task_file = AGENT_TASKS_DIR / f"{agent}_tasks_{today}.json"
            with open(task_file, 'w') as f:
                json.dump({
                    'generated': today,
                    'source': 'x_bookmark_analysis',
                    'tasks': tasks
                }, f, indent=2)
            print(f"Created {agent} tasks: {task_file} ({len(tasks)} tasks)")
    
    # Create a master feed file
    feed_file = AGENT_TASKS_DIR / f"agent_feed_{today}.md"
    with open(feed_file, 'w') as f:
        f.write(f"# Agent Feed - {today}\n\n")
        f.write(f"Generated from X bookmark analysis.\n\n")
        
        for agent, tasks in tasks_by_agent.items():
            if tasks:
                f.write(f"## {agent.upper()} Agent\n\n")
                for i, task in enumerate(tasks, 1):
                    f.write(f"{i}. **@{task['author']}**: {task['insight'][:100]}...\n")
                    if task['action']:
                        f.write(f"   - Action: {task['action'][:100]}...\n")
                    f.write(f"   - Source: {task['source']}\n\n")

    routed = build_opportunity_router(summary, analysis)
    high_roi_tasks = build_high_roi_task_queue(routed)
    learning_note_result = write_learning_notes_from_routed(
        routed,
        generated_on=today,
        notes_dir=LEARNING_NOTES_DIR,
        enabled=learning_notes_enabled(),
    )
    opportunity_json = OPPORTUNITY_DIR / f"opportunity_router_{today}.json"
    opportunity_memo = OPPORTUNITY_DIR / f"opportunity_memo_{today}.md"
    high_roi_json = OPPORTUNITY_DIR / f"high_roi_tasks_{today}.json"
    high_roi_memo = OPPORTUNITY_DIR / f"high_roi_tasks_{today}.md"
    with open(opportunity_json, 'w') as f:
        json.dump(routed, f, indent=2)
    with open(opportunity_memo, 'w') as f:
        f.write(render_opportunity_memo(routed, today))
    with open(high_roi_json, 'w') as f:
        json.dump({
            'generated': today,
            'source': str(opportunity_json),
            'tasks': high_roi_tasks,
            'safety': {'auto_execute': False, 'requires_human_review': True, 'destructive_actions': False},
        }, f, indent=2)
    with open(high_roi_memo, 'w') as f:
        f.write(render_high_roi_task_list(high_roi_tasks, today))
    
    print(f"\nMaster feed: {feed_file}")
    print(f"Opportunity JSON: {opportunity_json}")
    print(f"Opportunity memo: {opportunity_memo}")
    print(f"High-ROI tasks JSON: {high_roi_json}")
    print(f"High-ROI tasks memo: {high_roi_memo}")
    print(
        "Learning notes: "
        f"{learning_note_result['inserted']} inserted, "
        f"{learning_note_result['updated']} updated, "
        f"{learning_note_result['noop']} noop"
    )
    print("\n=== HIGH-ROI OPPORTUNITY MEMO ===")
    print(render_opportunity_memo(routed, today))
    print("\n=== HIGH-ROI TASK QUEUE ===")
    print(render_high_roi_task_list(high_roi_tasks, today))
    print("Agent feed generation complete!")

if __name__ == "__main__":
    generate_agent_tasks()
