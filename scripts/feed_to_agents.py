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
from datetime import datetime
from pathlib import Path

OUTPUT_DIR = Path("/app/output")
AGENT_TASKS_DIR = Path("/app/output/agent_tasks")
OPPORTUNITY_DIR = Path("/app/output/opportunities")

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
    return {
        'author': author,
        'insight': insight,
        'action': action,
        'url': url,
        'folder': folder,
        'score': score,
        'why': why,
    }

def build_opportunity_router(summary, analysis, limit_per_section=5):
    """Rank bookmark insights into concrete high-ROI sections."""
    records = _analysis_by_url(analysis)
    actions_by_url = {item.get('url'): item.get('action', '') for item in summary.get('action_items', []) if item.get('url')}
    routed = {
        'generated_from': 'x_bookmark_analysis',
        'total_processed': summary.get('total_processed', 0),
        'action_summary': summary.get('action_summary', {}),
        'immediate_actions': [],
        'research_queue': [],
        'knowledge_promotions': [],
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

        if immediate['score'] >= 12 and action:
            routed['immediate_actions'].append(immediate)
        if research['score'] >= 10:
            routed['research_queue'].append(research)
        if knowledge['score'] >= 10:
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
    print("\n=== HIGH-ROI OPPORTUNITY MEMO ===")
    print(render_opportunity_memo(routed, today))
    print("\n=== HIGH-ROI TASK QUEUE ===")
    print(render_high_roi_task_list(high_roi_tasks, today))
    print("Agent feed generation complete!")

if __name__ == "__main__":
    generate_agent_tasks()
