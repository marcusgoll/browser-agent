#!/usr/bin/env python3
"""Safe public-web follow-up research for X bookmark opportunities.

This script turns the passive opportunity router into promotion-candidate
reports. It does not write canonical wiki pages. Firecrawl is optional; if
FIRECRAWL_API_KEY is absent or a fetch fails, bounded local extraction uses
existing bookmark snippets and safe urllib fetching for public URLs.
"""

import argparse
import html.parser
import ipaddress
import json
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
OPPORTUNITY_DIR = OUTPUT_DIR / "opportunities"
FIRECRAWL_URL = os.environ.get("FIRECRAWL_SCRAPE_URL", "https://api.firecrawl.dev/v1/scrape")
FETCH_TIMEOUT = int(os.environ.get("PUBLIC_WEB_FETCH_TIMEOUT", "8"))
FETCH_MAX_BYTES = int(os.environ.get("PUBLIC_WEB_FETCH_MAX_BYTES", "1000000"))


class MetadataParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.description = ""
        self._in_title = False
        self._text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            name = (attrs.get("name") or attrs.get("property") or "").lower()
            if name in {"description", "og:description", "twitter:description"} and not self.description:
                self.description = attrs.get("content", "")[:1000]

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        clean = " ".join(data.split())
        if not clean:
            return
        if self._in_title:
            self.title += clean[:300]
        elif len(" ".join(self._text)) < 4000:
            self._text.append(clean)

    @property
    def text(self):
        return " ".join(self._text)[:4000]


def _load_json(path):
    with open(path) as f:
        return json.load(f)


def latest_file(pattern):
    files = list(OUTPUT_DIR.glob(pattern)) if not str(pattern).startswith("/") else list(Path("/").glob(str(pattern).lstrip("/")))
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def is_public_http_url(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
        return False
    if host in {"x.com", "twitter.com", "mobile.twitter.com"} or host.endswith(".x.com") or host.endswith(".twitter.com"):
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return False
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            return False
    return True


def select_followup_sources(router, analysis, limit=8):
    """Select public external sources connected to high-scoring opportunities."""
    by_bookmark = {item.get("url"): item for item in analysis or [] if item.get("url")}
    selected = []
    seen = set()
    for section in ("knowledge_promotions", "research_queue", "immediate_actions"):
        for opportunity in router.get(section, []) or []:
            bookmark_url = opportunity.get("url")
            record = by_bookmark.get(bookmark_url, {})
            action = record.get("action_result") or {}
            if record.get("folder") == "delete" or action.get("action") == "delete":
                continue
            for enriched in record.get("link_enrichment") or []:
                source_url = enriched.get("url") or enriched.get("original_url")
                if not source_url or source_url in seen or not is_public_http_url(source_url):
                    continue
                seen.add(source_url)
                selected.append({
                    "source_url": source_url,
                    "bookmark_url": bookmark_url,
                    "author": opportunity.get("author") or record.get("author") or "unknown",
                    "insight": opportunity.get("insight", ""),
                    "action": opportunity.get("action", ""),
                    "score": opportunity.get("score", 0),
                    "existing_title": enriched.get("title", ""),
                    "existing_snippet": enriched.get("text_snippet", ""),
                    "section": section,
                })
                if len(selected) >= limit:
                    return selected
    return selected


def _http_post_json(url, headers, body, timeout):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        text = response.read(FETCH_MAX_BYTES).decode("utf-8", errors="replace")
        return response.status, json.loads(text)


def fetch_with_firecrawl(url, api_key, http_post=_http_post_json):
    """Fetch public URL through Firecrawl. Result never includes the API key."""
    if not api_key:
        return {"status": "skipped", "provider": "firecrawl", "reason": "missing_api_key"}
    if not is_public_http_url(url):
        return {"status": "blocked", "provider": "firecrawl", "reason": "non_public_url"}
    try:
        status, payload = http_post(
            FIRECRAWL_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            body={"url": url, "formats": ["markdown"], "onlyMainContent": True, "timeout": FETCH_TIMEOUT * 1000},
            timeout=FETCH_TIMEOUT,
        )
    except Exception as exc:  # network provider fallback path
        return {"status": "error", "provider": "firecrawl", "reason": exc.__class__.__name__}
    data = payload.get("data") or payload if isinstance(payload, dict) else {}
    metadata = data.get("metadata") or {}
    markdown = data.get("markdown") or data.get("content") or ""
    return {
        "status": "ok" if 200 <= status < 300 and markdown else "error",
        "provider": "firecrawl",
        "title": metadata.get("title") or data.get("title") or "",
        "text": markdown[:4000],
        "bytes": len(markdown.encode("utf-8")),
    }


def fetch_with_local_fallback(url, existing_snippet=""):
    if not is_public_http_url(url):
        return {"status": "blocked", "provider": "local", "reason": "non_public_url", "text": existing_snippet[:4000]}
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 HermesBookmarkResearch/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as response:
            raw = response.read(FETCH_MAX_BYTES)
            content_type = response.headers.get("Content-Type", "")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"status": "fallback", "provider": "local", "reason": exc.__class__.__name__, "text": existing_snippet[:4000]}
    parser = MetadataParser()
    if "html" in content_type.lower():
        parser.feed(raw.decode("utf-8", errors="replace"))
        return {"status": "ok", "provider": "local", "title": parser.title.strip(), "description": parser.description, "text": parser.text or existing_snippet[:4000], "bytes": len(raw)}
    text = raw.decode("utf-8", errors="replace")[:4000]
    return {"status": "ok", "provider": "local", "title": "", "description": "", "text": text or existing_snippet[:4000], "bytes": len(raw)}


def fetch_source(source, api_key=None):
    firecrawl = fetch_with_firecrawl(source["source_url"], api_key) if api_key else {"status": "skipped", "provider": "firecrawl", "reason": "missing_api_key"}
    if firecrawl.get("status") == "ok":
        return firecrawl
    local = fetch_with_local_fallback(source["source_url"], source.get("existing_snippet", ""))
    if not local.get("title") and source.get("existing_title"):
        local["title"] = source["existing_title"]
    if not local.get("text") and source.get("existing_snippet"):
        local["text"] = source["existing_snippet"][:4000]
    local["firecrawl_status"] = firecrawl.get("status")
    local["firecrawl_reason"] = firecrawl.get("reason")
    return local


def build_promotion_candidate_report(sources, fetch_results, today):
    lines = [
        f"# Public Web Bookmark Follow-Up Candidates - {today}",
        "",
        "Promotion candidates only. This report does not auto-write canonical wiki pages.",
        "",
        "## Safety",
        "- auto-promoted: false",
        "- broker_calls: false",
        "- trading_intents_created: false",
        "- live_trading_allowed: false",
        "",
        "## Candidates",
    ]
    if not sources:
        lines.append("- No public external follow-up sources selected.")
        return "\n".join(lines)
    for idx, (source, result) in enumerate(zip(sources, fetch_results), 1):
        title = result.get("title") or source.get("existing_title") or source["source_url"]
        text = (result.get("text") or source.get("existing_snippet") or "").replace("\n", " ")[:800]
        lines.extend([
            f"{idx}. {title}",
            f"   - status: {result.get('status')} via {result.get('provider')}",
            f"   - score: {source.get('score')}",
            f"   - source: {source['source_url']}",
            f"   - bookmark: {source['bookmark_url']}",
            f"   - author: @{source.get('author')}",
            f"   - suggested_target: wiki promotion candidate",
            f"   - rationale: {source.get('insight', '')[:400]}",
            f"   - excerpt: {text}",
            "",
        ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate public-web follow-up promotion candidates from X bookmark opportunities.")
    parser.add_argument("--router", help="Path to opportunity_router JSON")
    parser.add_argument("--analysis", help="Path to bookmark_analysis JSON")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()

    router_path = Path(args.router) if args.router else latest_file("opportunities/opportunity_router_*.json")
    analysis_path = Path(args.analysis) if args.analysis else latest_file("bookmark_analysis_*.json")
    if not router_path or not analysis_path:
        raise SystemExit("Missing opportunity router or bookmark analysis JSON")

    router = _load_json(router_path)
    analysis = _load_json(analysis_path)
    sources = select_followup_sources(router, analysis, limit=args.limit)
    api_key = os.environ.get("FIRECRAWL_API_KEY", "")
    results = [fetch_source(source, api_key=api_key) for source in sources]
    report = build_promotion_candidate_report(sources, results, args.date)

    OPPORTUNITY_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OPPORTUNITY_DIR / f"public_web_followup_{args.date}.json"
    md_path = OPPORTUNITY_DIR / f"public_web_followup_{args.date}.md"
    json_path.write_text(json.dumps({
        "date": args.date,
        "router": str(router_path),
        "analysis": str(analysis_path),
        "firecrawl_enabled": bool(api_key),
        "sources": sources,
        "fetch_results": results,
        "safety": {"auto_promoted": False, "broker_calls": False, "trading_intents_created": False, "live_trading_allowed": False},
    }, indent=2))
    md_path.write_text(report)
    print(f"selected_sources={len(sources)}")
    print(f"json={json_path}")
    print(f"report={md_path}")


if __name__ == "__main__":
    main()
