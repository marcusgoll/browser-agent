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
import difflib
from datetime import datetime
from pathlib import Path

OUTPUT_DIR = Path("/app/output")
AGENT_TASKS_DIR = Path("/app/output/agent_tasks")
OPPORTUNITY_DIR = Path("/app/output/opportunities")
CONTENT_IDEAS_DIR = Path("/app/output/content_ideas")

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


CONTENT_IDEA_SCHEMA_VERSION = "content-idea/v1"
CONTENT_IDEA_ARTIFACT_TYPE = "content_idea"
CONTENT_IDEA_SECTIONS = ("immediate_actions", "research_queue", "knowledge_promotions")
CONTENT_IDEA_DUPLICATE_REJECT_THRESHOLD = 0.86
CONTENT_IDEA_DUPLICATE_REVISE_THRESHOLD = 0.72
CONTENT_IDEA_GENERIC_PHRASES = (
    "interesting idea",
    "write a post",
    "could be useful",
    "share insights",
    "thought leadership",
    "valuable content",
    "engaging content",
    "key takeaways",
)
CONTENT_IDEA_ROUTER_RATIONALES = (
    "Relevant to active Hermes/trading/devops work and has an executable next step.",
    "Potentially useful but should be researched before changing systems.",
    "Durable concept worth promoting into wiki/skills if still novel after dedupe.",
)
CONTENT_IDEA_STOPWORDS = {
    "about", "after", "agent", "agents", "before", "bookmark", "bookmarks",
    "browser", "from", "into", "more", "post", "source", "that", "this",
    "turn", "with", "write", "your",
}


def _one_line(value):
    return " ".join(str(value or "").split())


def _content_source_item_id(item):
    return str(item.get("id") or item.get("source_item_id") or _task_id(item))


def _content_source_url(item):
    return str(item.get("source_url") or item.get("url") or "")


def _content_project_bucket(item):
    return str(item.get("project_bucket") or item.get("primary_route") or item.get("folder") or item.get("source_section") or "unassigned")


def _first_content_text(candidates):
    for path, value in candidates:
        text = _one_line(value)
        if text:
            return text, path
    return "", candidates[0][0] if candidates else ""


def _is_router_rationale(value):
    text = _one_line(value).lower()
    return any(text == rationale.lower() for rationale in CONTENT_IDEA_ROUTER_RATIONALES)


def _content_text_with_paths(item):
    learning_note = item.get("learning_note") or {}
    reason_codes = " ".join(item.get("reason_codes") or [])
    insight = _first_content_text([
        ("insight", item.get("insight")),
        ("title", item.get("title")),
        ("learning_note.takeaway", learning_note.get("takeaway")),
        ("learning_note.summary", learning_note.get("summary")),
    ])
    action = _first_content_text([
        ("action", item.get("action")),
        ("suggested_action", item.get("suggested_action")),
        ("learning_note.action", learning_note.get("action")),
    ])
    why = _first_content_text([
        ("why", item.get("why")),
        ("reason_codes", reason_codes),
        ("learning_note.why_now", learning_note.get("why_now")),
    ])
    if _is_router_rationale(why[0]) and insight[0]:
        why = insight
    values = {"insight": insight, "action": action, "why": why}
    return {
        "parts": {key: value[0] for key, value in values.items()},
        "paths": {key: value[1] for key, value in values.items()},
    }


def _content_hash(prefix, parts, length):
    seed = "|".join(_one_line(part).lower() for part in parts)
    return f"{prefix}-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:length]}"


def _content_tokens(value):
    tokens = []
    for raw in _one_line(value).lower().split():
        token = raw.strip(".,:;!?()[]{}\"'")
        if len(token) > 2 and token not in CONTENT_IDEA_STOPWORDS:
            tokens.append(token)
    return tokens


def _content_concrete_terms(value):
    return set(_content_tokens(value))


def _grounding(source_paths, evidence_excerpt, grounding_note):
    excerpt = _one_line(evidence_excerpt)
    return {
        "source_paths": list(source_paths) if excerpt else [],
        "evidence_excerpt": excerpt,
        "grounding_note": grounding_note if excerpt else "",
    }


def _source_metadata(item):
    return {
        "source_item_id": _content_source_item_id(item),
        "source_url": _content_source_url(item),
        "source_author": str(item.get("author") or item.get("author_name") or "Unknown"),
        "source_section": str(item.get("source_section") or "unassigned"),
        "project_bucket": _content_project_bucket(item),
        "score": item.get("score", 0),
        "priority": item.get("priority"),
        "folder": item.get("folder"),
    }


def _base_content_idea(item, generated_on):
    source = _source_metadata(item)
    source_fingerprint = _content_hash(
        "source",
        [source["source_item_id"], source["source_url"], source["source_author"]],
        16,
    )
    return {
        "schema_version": CONTENT_IDEA_SCHEMA_VERSION,
        "artifact_type": CONTENT_IDEA_ARTIFACT_TYPE,
        "content_idea_id": "",
        "generated_on": str(generated_on),
        "status": "pending_novelty_check",
        "source_fingerprint": source_fingerprint,
        "idea_fingerprint": "",
        "source_metadata": source,
        "source_material": {},
        "hook": "",
        "angle": "",
        "audience": "",
        "proof_point": "",
        "field_grounding": {
            "hook": _grounding([], "", ""),
            "angle": _grounding([], "", ""),
            "audience": _grounding([], "", ""),
            "proof_point": _grounding([], "", ""),
        },
        "novelty_signal": {"status": "not_checked", "reason_codes": [], "nearest_prior_idea_id": None},
        "duplicate_policy": {
            "status": "not_checked",
            "duplicate_score": 0.0,
            "nearest_prior_idea_id": None,
            "reason_codes": [],
        },
    }


def build_content_idea_draft(item, generated_on):
    """Build a local content-idea/v1 draft from one routed bookmark item.

    The returned draft is intentionally not accepted. It stays
    ``pending_novelty_check`` until ``build_content_idea_with_checks`` runs the
    local generic/duplicate gate.
    """
    idea = _base_content_idea(item, generated_on)
    text = _content_text_with_paths(item)
    parts = text["parts"]
    paths = text["paths"]
    source = idea["source_metadata"]
    idea["source_material"] = {
        "insight": parts["insight"],
        "action": parts["action"],
        "why": parts["why"],
        "source_url": source["source_url"],
        "source_author": source["source_author"],
        "source_section": source["source_section"],
        "project_bucket": source["project_bucket"],
    }

    if parts["insight"]:
        idea["hook"] = f"{parts['insight']}"
        idea["field_grounding"]["hook"] = _grounding(
            [paths["insight"]],
            parts["insight"],
            "Hook is copied from the routed source takeaway, not invented from a generic prompt.",
        )
    if parts["action"]:
        idea["angle"] = f"Use this as the {source['project_bucket']} operator angle: {parts['action']}"
        idea["field_grounding"]["angle"] = _grounding(
            [paths["action"], "project_bucket"],
            parts["action"],
            "Angle is anchored to the routed next action and project bucket.",
        )
    idea["audience"] = f"{source['project_bucket']} operators reviewing {source['source_section']} bookmarks from @{source['source_author']}"
    idea["field_grounding"]["audience"] = _grounding(
        ["project_bucket", "source_section", "source_author"],
        idea["audience"],
        "Audience is derived from source metadata only.",
    )
    if parts["why"]:
        idea["proof_point"] = parts["why"]
        idea["field_grounding"]["proof_point"] = _grounding(
            [paths["why"]],
            parts["why"],
            "Proof point is traceable to routed why/reason evidence; no external claim is added.",
        )

    idea["idea_fingerprint"] = _content_hash(
        "idea",
        [idea["hook"], idea["angle"], idea["audience"], idea["proof_point"]],
        16,
    )
    idea["content_idea_id"] = _content_hash(
        "content-idea",
        [idea["source_fingerprint"], idea["idea_fingerprint"]],
        12,
    )
    return idea


def _generic_reasons(idea):
    combined = " ".join([
        idea.get("hook", ""),
        idea.get("angle", ""),
        idea.get("audience", ""),
        idea.get("proof_point", ""),
    ]).lower()
    reasons = [f"generic_phrase.{phrase.replace(' ', '_')}" for phrase in CONTENT_IDEA_GENERIC_PHRASES if phrase in combined]
    if len(_content_concrete_terms(combined)) < 8:
        reasons.append("generic.low_source_specificity")
    return reasons


def _weak_evidence_reasons(idea):
    proof_grounding = idea["field_grounding"]["proof_point"]
    proof = idea.get("proof_point", "")
    if not proof_grounding["source_paths"] or len(_content_tokens(proof)) < 6:
        return ["weak_proof_point"]
    source_terms = _content_concrete_terms(" ".join(str(v) for v in idea.get("source_material", {}).values()))
    proof_terms = _content_concrete_terms(proof)
    if proof_terms and source_terms and len(proof_terms & source_terms) == 0:
        return ["proof_not_traceable_to_source_material"]
    return []


def _idea_text(idea):
    return " ".join([idea.get("hook", ""), idea.get("angle", ""), idea.get("audience", ""), idea.get("proof_point", "")])


def _token_similarity(left, right):
    left_tokens = _content_concrete_terms(left)
    right_tokens = _content_concrete_terms(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _source_backed_delta(candidate, prior):
    candidate_terms = _content_concrete_terms(candidate.get("proof_point", "") + " " + candidate.get("angle", ""))
    prior_terms = _content_concrete_terms(prior.get("proof_point", "") + " " + prior.get("angle", ""))
    return len(candidate_terms - prior_terms) >= 4 and bool(candidate["field_grounding"]["proof_point"]["source_paths"])


def _duplicate_policy(candidate, prior_ideas):
    best = {"score": 0.0, "nearest_prior_idea_id": None, "reason_codes": ["comparison_set_empty"] if not prior_ideas else []}
    candidate_text = _idea_text(candidate)
    for prior in prior_ideas or []:
        if not isinstance(prior, dict):
            continue
        prior_text = _idea_text(prior)
        reason_codes = []
        if candidate.get("idea_fingerprint") and candidate.get("idea_fingerprint") == prior.get("idea_fingerprint"):
            score = 1.0
            reason_codes.append("duplicate.exact_idea_fingerprint")
        elif candidate.get("source_fingerprint") and candidate.get("source_fingerprint") == prior.get("source_fingerprint"):
            if _source_backed_delta(candidate, prior):
                score = 0.69
                reason_codes.extend(["same_source_item", "source_backed_delta"])
            else:
                score = 1.0
                reason_codes.append("duplicate.same_source_item")
        else:
            sequence = difflib.SequenceMatcher(None, candidate_text.lower(), prior_text.lower()).ratio() if candidate_text and prior_text else 0.0
            token_score = _token_similarity(candidate_text, prior_text)
            score = (0.52 * sequence) + (0.48 * token_score)
            if token_score >= 0.55 and sequence >= 0.50:
                score = max(score, 0.74)
            same_source_url = candidate["source_metadata"].get("source_url") and candidate["source_metadata"].get("source_url") == (prior.get("source_metadata") or {}).get("source_url")
            if same_source_url:
                reason_codes.append("same_source_url")
                score += 0.05
                if score < CONTENT_IDEA_DUPLICATE_REJECT_THRESHOLD and _source_backed_delta(candidate, prior):
                    score = min(score, 0.69)
                    reason_codes.append("source_backed_delta")
            if token_score >= 0.45:
                reason_codes.append("token_overlap")
            if sequence >= 0.72:
                reason_codes.append("sequence_similarity")
        if score > best["score"]:
            best = {
                "score": min(score, 1.0),
                "nearest_prior_idea_id": prior.get("content_idea_id"),
                "reason_codes": reason_codes or ["distinct_material_angle"],
            }
    score = round(best["score"], 3)
    if score >= CONTENT_IDEA_DUPLICATE_REJECT_THRESHOLD:
        status = "rejected_duplicate"
    elif score >= CONTENT_IDEA_DUPLICATE_REVISE_THRESHOLD:
        status = "needs_revision"
    else:
        status = "accepted"
        if best["nearest_prior_idea_id"] and "source_backed_delta" not in best["reason_codes"]:
            best["reason_codes"].append("distinct_material_angle")
    return {
        "status": status,
        "duplicate_score": score,
        "nearest_prior_idea_id": best["nearest_prior_idea_id"],
        "reason_codes": best["reason_codes"],
    }


def _set_needs_review_manifest_unavailable(idea):
    idea["status"] = "needs_review"
    idea["novelty_signal"] = {
        "status": "needs_review",
        "reason_codes": ["manifest_unavailable"],
        "nearest_prior_idea_id": None,
    }
    idea["duplicate_policy"] = {
        "status": "not_checked",
        "duplicate_score": 0.0,
        "nearest_prior_idea_id": None,
        "reason_codes": ["manifest_unavailable"],
    }
    return idea


def build_content_idea_with_checks(item, generated_on, prior_manifest=None):
    """Build one content idea and run local generic/duplicate checks before acceptance."""
    idea = build_content_idea_draft(item, generated_on)
    generic_reasons = _generic_reasons(idea)
    if generic_reasons:
        idea["status"] = "rejected_generic"
        idea["novelty_signal"] = {"status": "reject", "reason_codes": generic_reasons, "nearest_prior_idea_id": None}
        return idea

    weak_reasons = _weak_evidence_reasons(idea)
    if weak_reasons:
        idea["status"] = "rejected_weak_evidence"
        idea["novelty_signal"] = {"status": "reject", "reason_codes": weak_reasons, "nearest_prior_idea_id": None}
        return idea

    duplicate = _duplicate_policy(idea, list(prior_manifest or []))
    idea["duplicate_policy"] = duplicate
    if duplicate["status"] == "rejected_duplicate":
        idea["status"] = "rejected_duplicate"
        novelty_status = "reject"
    elif duplicate["status"] == "needs_revision":
        idea["status"] = "needs_revision"
        novelty_status = "revise"
    else:
        idea["status"] = "accepted"
        novelty_status = "accept"
    idea["novelty_signal"] = {
        "status": novelty_status,
        "reason_codes": duplicate["reason_codes"],
        "nearest_prior_idea_id": duplicate["nearest_prior_idea_id"],
        "duplicate_score": duplicate["duplicate_score"],
    }
    return idea


def _load_prior_content_ideas(prior_manifest=None, prior_manifest_path=None):
    if prior_manifest_path:
        try:
            loaded = json.loads(Path(prior_manifest_path).read_text())
        except (OSError, json.JSONDecodeError):
            return None, "manifest_unavailable"
        if isinstance(loaded, dict) and isinstance(loaded.get("ideas"), list):
            return loaded["ideas"], None
        if isinstance(loaded, list):
            return loaded, None
        return None, "manifest_unavailable"
    if prior_manifest is None:
        return None, "manifest_unavailable"
    if isinstance(prior_manifest, list):
        return prior_manifest, None
    if isinstance(prior_manifest, dict) and isinstance(prior_manifest.get("ideas"), list):
        return prior_manifest["ideas"], None
    return None, "manifest_unavailable"


def build_content_idea_artifacts(routed, generated_on, prior_manifest=None, prior_manifest_path=None, enabled=True):
    """Generate checked content ideas from router output without mutating the route payload."""
    if not enabled:
        return []
    prior_ideas, manifest_error = _load_prior_content_ideas(prior_manifest=prior_manifest, prior_manifest_path=prior_manifest_path)
    ideas = []
    accepted_prior = list(prior_ideas or [])
    for section in CONTENT_IDEA_SECTIONS:
        for item in routed.get(section, []) or []:
            idea_item = dict(item)
            idea_item.setdefault("source_section", section)
            if manifest_error:
                idea = _set_needs_review_manifest_unavailable(build_content_idea_draft(idea_item, generated_on))
            else:
                idea = build_content_idea_with_checks(idea_item, generated_on=generated_on, prior_manifest=accepted_prior)
                if idea.get("status") == "accepted":
                    accepted_prior.append(idea)
            ideas.append(idea)
    return ideas


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
    CONTENT_IDEAS_DIR.mkdir(exist_ok=True)
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
    content_idea_generation_enabled = os.getenv("CONTENT_IDEA_GENERATION_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}
    content_idea_prior_manifest = os.getenv("CONTENT_IDEA_PRIOR_MANIFEST") or str(CONTENT_IDEAS_DIR / "prior_content_ideas.json")
    content_ideas = build_content_idea_artifacts(
        routed,
        generated_on=today,
        prior_manifest_path=content_idea_prior_manifest,
        enabled=content_idea_generation_enabled,
    )
    opportunity_json = OPPORTUNITY_DIR / f"opportunity_router_{today}.json"
    opportunity_memo = OPPORTUNITY_DIR / f"opportunity_memo_{today}.md"
    high_roi_json = OPPORTUNITY_DIR / f"high_roi_tasks_{today}.json"
    high_roi_memo = OPPORTUNITY_DIR / f"high_roi_tasks_{today}.md"
    content_ideas_json = CONTENT_IDEAS_DIR / f"content_ideas_{today}.json"
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
    if content_idea_generation_enabled:
        with open(content_ideas_json, 'w') as f:
            json.dump({
                'schema_version': 'content-idea-manifest/v1',
                'generated': today,
                'source': str(opportunity_json),
                'ideas': content_ideas,
                'rollback': {'CONTENT_IDEA_GENERATION_ENABLED': '0 disables this content-idea output while preserving routing'},
            }, f, indent=2)
    
    print(f"\nMaster feed: {feed_file}")
    print(f"Opportunity JSON: {opportunity_json}")
    print(f"Opportunity memo: {opportunity_memo}")
    print(f"High-ROI tasks JSON: {high_roi_json}")
    print(f"High-ROI tasks memo: {high_roi_memo}")
    if content_idea_generation_enabled:
        print(f"Content ideas JSON: {content_ideas_json}")
    else:
        print("Content idea generation disabled by CONTENT_IDEA_GENERATION_ENABLED; routing output preserved.")
    print("\n=== HIGH-ROI OPPORTUNITY MEMO ===")
    print(render_opportunity_memo(routed, today))
    print("\n=== HIGH-ROI TASK QUEUE ===")
    print(render_high_roi_task_list(high_roi_tasks, today))
    print("Agent feed generation complete!")

if __name__ == "__main__":
    generate_agent_tasks()
