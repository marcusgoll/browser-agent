#!/usr/bin/env python3
"""
X Bookmark Processor

Reads X bookmarks, extracts insights using LLM, and organizes them:
- Create folders (e.g., "AI Tools", "DevOps", "Ideas")
- Move bookmarks to appropriate folders
- Delete low-value bookmarks

Usage:
    docker compose run --rm browser-agent scripts/process_bookmarks.py --dry-run
    docker compose run --rm browser-agent scripts/process_bookmarks.py --execute
"""

import os
import sys
import json
import asyncio
import argparse
import hashlib
import html
import ipaddress
import re
import shutil
import socket
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright
from browser_use.llm.litellm import ChatLiteLLM
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

import bookmark_schema

PROFILE_DIR = os.environ.get("BROWSER_PROFILE_DIR", "/app/profiles")
OUTPUT_DIR = Path("/app/output")
OUTPUT_DIR.mkdir(exist_ok=True)
BOOKMARK_ANALYSIS_CACHE_FILE = OUTPUT_DIR / "bookmark_analysis_cache_v1.json"
BOOKMARK_ANALYSIS_CACHE_VERSION = "bookmark-analysis-cache-v2"
BOOKMARK_ANALYSIS_POLICY_VERSION = "bookmark-analysis-policy-v1"
FETCH_TIMEOUT_SECONDS = int(os.environ.get("BOOKMARK_LINK_FETCH_TIMEOUT", "8"))
FETCH_MAX_BYTES = int(os.environ.get("BOOKMARK_LINK_FETCH_MAX_BYTES", str(1024 * 1024)))
FETCH_SNIPPET_CHARS = int(os.environ.get("BOOKMARK_LINK_SNIPPET_CHARS", "2500"))
MAX_ENRICHED_LINKS_PER_BOOKMARK = int(os.environ.get("BOOKMARK_MAX_ENRICHED_LINKS", "3"))
VIDEO_TRANSCRIPTION_ENABLED = os.environ.get("BOOKMARK_TRANSCRIBE_VIDEO", "0").lower() in ("1", "true", "yes")
VIDEO_FETCH_TIMEOUT_SECONDS = int(os.environ.get("BOOKMARK_VIDEO_FETCH_TIMEOUT", "20"))
VIDEO_FETCH_MAX_BYTES = int(os.environ.get("BOOKMARK_VIDEO_FETCH_MAX_BYTES", str(25 * 1024 * 1024)))
VIDEO_TRANSCRIBE_MAX_SECONDS = int(os.environ.get("BOOKMARK_VIDEO_TRANSCRIBE_MAX_SECONDS", "120"))
VIDEO_TRANSCRIBE_PROVIDER = os.environ.get("BOOKMARK_VIDEO_TRANSCRIBE_PROVIDER", "openrouter").lower()
VIDEO_TRANSCRIBE_MODEL = os.environ.get(
    "BOOKMARK_VIDEO_TRANSCRIBE_MODEL",
    "gpt-4o-mini-transcribe" if VIDEO_TRANSCRIBE_PROVIDER == "openai" else "openrouter/anthropic/claude-sonnet-4",
)
X_BEARER_TOKEN = os.environ.get("X_BEARER_TOKEN", "")
GRAPHQL_OPERATION_IDS = {
    "DeleteBookmark": "Wlmlj2-xzyS1GN3a6cj-mQ",
    "BookmarkFoldersSlice": "i78YDd0Tza-dV4SYs58kRg",
    "bookmarkTweetToFolder": "4KHZvvNbHNf07bsgnL9gWA",
    "createBookmarkFolder": "6Xxqpq8TM_CREYiuof_h5w",
}

# Categories for organizing bookmarks
FOLDERS = {
    "ai_tools": "AI Tools & Agents",
    "devops": "DevOps & Infrastructure", 
    "coding": "Coding & Development",
    "design": "Design & UX",
    "ideas": "Ideas & Inspiration",
    "productivity": "Productivity & Tools",
    "aviation": "Aviation & Flying",
    "business": "Business",
    "archive": "Archive (Processed)",
    "delete": "__DELETE__"
}


def _env_first(*names, default=""):
    for name in names:
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()
    return default


def _provider_model_name(provider, model):
    if model.startswith(f"{provider}/"):
        return model
    return f"{provider}/{model}"


def get_llm():
    """Initialize an LLM client from the active provider env vars."""
    provider = _env_first(
        "LLM_PROVIDER",
        "HERMES_LLM_PROVIDER",
        "HERMES_PROVIDER",
        "HERMES_MODEL_PROVIDER",
        default="openrouter",
    ).lower()
    default_model = {
        "openrouter": "anthropic/claude-sonnet-4",
        "anthropic": "claude-sonnet-4",
        "openai": "gpt-4o-mini",
        "custom": "gpt-4o-mini",
        "openai-compatible": "gpt-4o-mini",
        "endpoint": "gpt-4o-mini",
    }.get(provider, "anthropic/claude-sonnet-4")
    model = _env_first("LLM_MODEL", "HERMES_LLM_MODEL", "HERMES_MODEL", default=default_model)
    temperature = float(_env_first("LLM_TEMPERATURE", "HERMES_LLM_TEMPERATURE", default="0.3"))

    if provider == "openrouter":
        api_key = _env_first("OPENROUTER_API_KEY", "HERMES_OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY not set")
        return ChatLiteLLM(
            model=_provider_model_name("openrouter", model),
            api_key=api_key,
            api_base="https://openrouter.ai/api/v1",
            temperature=temperature,
        )

    if provider == "anthropic":
        api_key = _env_first("ANTHROPIC_API_KEY", "HERMES_ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        return ChatLiteLLM(
            model=_provider_model_name("anthropic", model),
            api_key=api_key,
            temperature=temperature,
        )

    if provider == "openai":
        api_key = _env_first("OPENAI_API_KEY", "HERMES_OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")
        return ChatLiteLLM(
            model=_provider_model_name("openai", model),
            api_key=api_key,
            temperature=temperature,
        )

    if provider in {"custom", "openai-compatible", "endpoint"}:
        base_url = _env_first("LLM_BASE_URL", "HERMES_LLM_BASE_URL", "OPENAI_BASE_URL", "HERMES_OPENAI_BASE_URL")
        if not base_url:
            raise ValueError("LLM_BASE_URL not set for custom provider")
        api_key = _env_first("LLM_API_KEY", "HERMES_LLM_API_KEY", "OPENAI_API_KEY", "HERMES_OPENAI_API_KEY")
        if not api_key:
            raise ValueError("LLM_API_KEY not set for custom provider")
        return ChatOpenAI(
            model=model,
            api_key=lambda: api_key,
            base_url=base_url,
            temperature=temperature,
        )

    raise ValueError(f"Unknown LLM provider: {provider}")


def _first_string(value):
    """Return the first non-empty string from X GraphQL card binding value shapes."""
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return ''
    for key in ('string_value', 'scribe_key', 'type'):
        if value.get(key):
            return value[key]
    image = value.get('image_value') or {}
    if image.get('url'):
        return image['url']
    user = value.get('user_value') or {}
    if user.get('id_str'):
        return user['id_str']
    return ''


def _extract_card(card):
    """Extract article/card metadata from X's legacy card shape."""
    if not isinstance(card, dict):
        return None

    legacy = card.get('legacy') or card
    raw_bindings = legacy.get('binding_values') or []
    bindings = {}
    for item in raw_bindings:
        key = item.get('key')
        if key:
            bindings[key] = _first_string(item.get('value'))

    unified = bindings.get('unified_card')
    if unified:
        try:
            parsed = json.loads(unified)
            bindings['unified_card_parsed'] = parsed
        except Exception:
            bindings['unified_card_parse_error'] = True

    url = (
        bindings.get('card_url')
        or bindings.get('vanity_url')
        or bindings.get('domain')
        or bindings.get('player_url')
    )
    title = bindings.get('title') or bindings.get('player_title') or bindings.get('summary_title')
    description = bindings.get('description') or bindings.get('summary_description')

    return {
        'name': legacy.get('name') or card.get('name'),
        'url': url,
        'title': title,
        'description': description,
        'domain': bindings.get('domain') or bindings.get('vanity_url'),
        'binding_keys': sorted(bindings.keys()),
        'bindings': bindings,
    }


def _extract_urls(legacy):
    urls = []
    for item in (legacy.get('entities') or {}).get('urls', []):
        expanded = item.get('expanded_url') or item.get('url')
        if expanded:
            urls.append({
                'url': item.get('url'),
                'expanded_url': expanded,
                'display_url': item.get('display_url'),
            })
    return urls


def _best_video_variant(variants):
    """Pick the highest-bitrate MP4 variant for LLM/context use without downloading media."""
    mp4_variants = [
        variant for variant in variants
        if variant.get('content_type') == 'video/mp4' and variant.get('url')
    ]
    if not mp4_variants:
        return None
    return max(mp4_variants, key=lambda variant: variant.get('bitrate') or 0)


def _extract_media(legacy):
    media_items = []
    for item in (legacy.get('extended_entities') or {}).get('media', []):
        variants = []
        video_info = item.get('video_info') or {}
        for variant in video_info.get('variants', []):
            if variant.get('url'):
                variants.append({
                    'content_type': variant.get('content_type'),
                    'bitrate': variant.get('bitrate'),
                    'url': variant.get('url'),
                })
        original_info = item.get('original_info') or {}
        sizes = item.get('sizes') or {}
        media_items.append({
            'id': item.get('id_str') or item.get('id'),
            'type': item.get('type'),
            'media_url': item.get('media_url_https') or item.get('media_url'),
            'expanded_url': item.get('expanded_url'),
            'display_url': item.get('display_url'),
            'alt_text': item.get('ext_alt_text') or '',
            'duration_millis': video_info.get('duration_millis'),
            'duration_seconds': round(video_info.get('duration_millis') / 1000, 2) if video_info.get('duration_millis') else None,
            'aspect_ratio': video_info.get('aspect_ratio') or [],
            'width': original_info.get('width') or (sizes.get('large') or {}).get('w'),
            'height': original_info.get('height') or (sizes.get('large') or {}).get('h'),
            'video_variants': variants,
            'best_video_variant': _best_video_variant(variants),
        })
    return media_items


def _unwrap_tweet_result(result):
    """Normalize X tweet result wrappers."""
    if not isinstance(result, dict):
        return {}
    if 'tweet' in result and isinstance(result['tweet'], dict):
        return result['tweet']
    if 'result' in result and isinstance(result['result'], dict):
        return _unwrap_tweet_result(result['result'])
    return result


def _extract_tweet_result(result, deleted=False):
    result = _unwrap_tweet_result(result)
    tweet_id = result.get('rest_id') or result.get('id_str') or ''
    legacy = result.get('legacy') or {}
    note_text = (((result.get('note_tweet') or {}).get('note_tweet_results') or {}).get('result') or {}).get('text')
    text = note_text or legacy.get('full_text') or legacy.get('text') or ''

    user_result = (((result.get('core') or {}).get('user_results') or {}).get('result') or {})
    user_core = user_result.get('core') or {}
    user_legacy = user_result.get('legacy') or {}
    author = user_core.get('screen_name') or user_legacy.get('screen_name') or 'unknown'
    author_name = user_core.get('name') or user_legacy.get('name') or ''

    quoted = None
    quoted_result = ((result.get('quoted_status_result') or {}).get('result') or {})
    if quoted_result:
        quoted = _extract_tweet_result(quoted_result)

    url = f'https://x.com/{author}/status/{tweet_id}' if tweet_id and author != 'unknown' else ''
    return {
        'id': tweet_id,
        'author': author,
        'author_name': author_name,
        'text': text,
        'url': url,
        'timestamp': legacy.get('created_at') or '',
        'deleted': deleted,
        'external_urls': _extract_urls(legacy),
        'media': _extract_media(legacy),
        'card': _extract_card(result.get('card')),
        'quoted_tweet': quoted,
        'conversation_id': legacy.get('conversation_id_str') or '',
        'lang': legacy.get('lang') or '',
    }


def _extract_bookmarks_from_graphql(data):
    bookmarks = []
    timeline = ((data.get('data') or {}).get('bookmark_timeline_v2') or {}).get('timeline') or {}
    for instruction in timeline.get('instructions', []):
        for entry in instruction.get('entries', []):
            entry_id = entry.get('entryId', '')
            if not entry_id.startswith('tweet-'):
                continue
            tweet_id = entry_id.replace('tweet-', '')
            item = (entry.get('content') or {}).get('itemContent') or {}
            tweet_results = item.get('tweet_results') or {}
            if not tweet_results:
                bookmarks.append({
                    'id': tweet_id,
                    'author': 'unknown',
                    'author_name': '',
                    'text': '',
                    'url': f'https://x.com/i/web/status/{tweet_id}',
                    'timestamp': '',
                    'deleted': True,
                    'external_urls': [],
                    'media': [],
                    'card': None,
                    'quoted_tweet': None,
                    'conversation_id': '',
                    'lang': '',
                })
                continue
            bookmark = _extract_tweet_result(tweet_results.get('result') or {})
            if not bookmark.get('id'):
                bookmark['id'] = tweet_id
            if not bookmark.get('url'):
                bookmark['url'] = f'https://x.com/i/web/status/{tweet_id}'
            bookmarks.append(bookmark)
    return bookmarks


async def fetch_bookmarks_dom_fallback(page, max_scrolls=5):
    """Fallback DOM scraper. GraphQL is preferred because DOM misses cards/media/deleted tweets."""
    bookmarks = []
    seen_urls = set()
    for scroll in range(max_scrolls):
        tweets = await page.query_selector_all('article[data-testid="tweet"]')
        for tweet in tweets:
            try:
                author_el = await tweet.query_selector('a[href^="/"]')
                author = await author_el.get_attribute('href') if author_el else '/unknown'
                author = author.strip('/')
                text_el = await tweet.query_selector('[data-testid="tweetText"]')
                text = await text_el.inner_text() if text_el else ''
                link_el = await tweet.query_selector('a[href*="/status/"]')
                tweet_url = ''
                if link_el:
                    href = await link_el.get_attribute('href')
                    tweet_url = f'https://x.com{href}' if href else ''
                time_el = await tweet.query_selector('time')
                timestamp = await time_el.get_attribute('datetime') if time_el else ''
                if tweet_url in seen_urls:
                    continue
                seen_urls.add(tweet_url)
                bookmarks.append({
                    'author': author,
                    'author_name': '',
                    'text': text,
                    'url': tweet_url,
                    'timestamp': timestamp,
                    'deleted': False,
                    'external_urls': [],
                    'media': [],
                    'card': None,
                    'quoted_tweet': None,
                })
            except Exception:
                continue
        await page.evaluate('() => window.scrollTo(0, document.body.scrollHeight)')
        await page.wait_for_timeout(2000)
    return bookmarks


async def fetch_bookmarks(page, max_scrolls=5):
    """Fetch bookmarked tweets via X GraphQL interception, with DOM fallback."""
    global X_BEARER_TOKEN
    bookmarks_by_id = {}
    captured_bearer_token = X_BEARER_TOKEN

    async def handle_response(response):
        nonlocal captured_bearer_token
        if 'Bookmarks?' not in response.url:
            return
        try:
            request_headers = getattr(response.request, 'headers', {}) or {}
            auth_header = request_headers.get('authorization') or request_headers.get('Authorization') or ''
            if auth_header.lower().startswith('bearer ') and not captured_bearer_token:
                captured_bearer_token = auth_header.split(' ', 1)[1].strip()
        except Exception:
            pass
        try:
            data = await response.json()
        except Exception:
            return
        for bookmark in _extract_bookmarks_from_graphql(data):
            key = bookmark.get('id') or bookmark.get('url')
            if key:
                bookmarks_by_id[key] = bookmark

    page.on('response', handle_response)
    await page.goto('https://x.com/i/bookmarks', wait_until='domcontentloaded', timeout=30000)
    await page.wait_for_timeout(4000)

    for _ in range(max_scrolls):
        await page.evaluate('() => window.scrollTo(0, document.body.scrollHeight)')
        await page.wait_for_timeout(2500)

    if bookmarks_by_id:
        if captured_bearer_token and not X_BEARER_TOKEN:
            X_BEARER_TOKEN = captured_bearer_token
        return list(bookmarks_by_id.values())

    if captured_bearer_token and not X_BEARER_TOKEN:
        X_BEARER_TOKEN = captured_bearer_token
    return await fetch_bookmarks_dom_fallback(page, max_scrolls=max_scrolls)


class _MetadataHTMLParser(HTMLParser):
    """Small stdlib HTML metadata/text extractor for bounded link enrichment."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ''
        self.meta = {}
        self.paragraphs = []
        self._in_title = False
        self._capture_tag = None
        self._capture = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('script', 'style', 'noscript', 'svg'):
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == 'title':
            self._in_title = True
        elif tag == 'meta':
            key = attrs.get('property') or attrs.get('name')
            value = attrs.get('content')
            if key and value:
                self.meta[key.lower()] = html.unescape(value).strip()
        elif tag in ('p', 'h1', 'h2', 'article'):
            self._capture_tag = tag
            self._capture = []

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript', 'svg') and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag == 'title':
            self._in_title = False
            self.title = _clean_text(' '.join(self._capture)) or self.title
            self._capture = []
        elif self._capture_tag == tag:
            text = _clean_text(' '.join(self._capture))
            if text and len(text) > 40:
                self.paragraphs.append(text)
            self._capture_tag = None
            self._capture = []

    def handle_data(self, data):
        if self._skip_depth:
            return
        if self._in_title or self._capture_tag:
            self._capture.append(data)


def _clean_text(text):
    return re.sub(r'\s+', ' ', html.unescape(text or '')).strip()


TRACKING_QUERY_KEYS = {
    'fbclid',
    'gclid',
    'mc_cid',
    'mc_eid',
    'ref_src',
}


def _stable_hash(payload):
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _is_x_status_url(parsed):
    host = (parsed.hostname or '').lower()
    return host in ('x.com', 'www.x.com', 'twitter.com', 'www.twitter.com') and re.search(r'/status/\d+', parsed.path)


def normalize_bookmark_url(url):
    """Return a deterministic URL identity for bookmark dedupe/cache keys."""
    url = _normalize_candidate_url(url)
    if not url:
        return ''

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        return ''

    scheme = parsed.scheme.lower()
    hostname = parsed.hostname.lower()
    if hostname in ('twitter.com', 'www.twitter.com', 'www.x.com'):
        hostname = 'x.com'
    port = f":{parsed.port}" if parsed.port and (scheme, parsed.port) not in (('http', 80), ('https', 443)) else ''
    netloc = f"{hostname}{port}"

    path = urllib.parse.unquote(parsed.path or '/')
    path = re.sub(r'/+', '/', path).rstrip('/') or '/'

    status_match = re.search(r'/status/(\d+)', path)
    if _is_x_status_url(parsed) and status_match:
        path = f"/i/web/status/{status_match.group(1)}"
        query = ''
    else:
        query_pairs = []
        for key, value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True):
            key_lower = key.lower()
            if key_lower.startswith('utm_') or key_lower in TRACKING_QUERY_KEYS:
                continue
            query_pairs.append((key, value))
        query_pairs.sort()
        query = urllib.parse.urlencode(query_pairs, doseq=True)

    return urllib.parse.urlunparse((scheme, netloc, path, '', query, ''))


def bookmark_content_hash(bookmark):
    """Hash stable content fields when a bookmark has no usable canonical URL."""
    external_urls = []
    for item in bookmark.get('external_urls') or []:
        normalized = normalize_bookmark_url(item.get('expanded_url') or item.get('url'))
        if normalized:
            external_urls.append(normalized)
    card = bookmark.get('card') or {}
    media = bookmark.get('media') or []
    payload = {
        'author': (bookmark.get('author') or '').lower(),
        'text': _clean_text(bookmark.get('text') or ''),
        'timestamp': bookmark.get('timestamp') or '',
        'external_urls': sorted(set(external_urls)),
        'card': {
            'url': normalize_bookmark_url(card.get('url') or ''),
            'title': _clean_text(card.get('title') or ''),
            'description': _clean_text(card.get('description') or ''),
        },
        'media': [
            {
                'id': item.get('id'),
                'type': item.get('type'),
                'media_url': normalize_bookmark_url(item.get('media_url') or ''),
                'alt_text': _clean_text(item.get('alt_text') or ''),
            }
            for item in media
        ],
    }
    return _stable_hash(payload)


def bookmark_dedupe_key(bookmark):
    normalized_url = normalize_bookmark_url(bookmark.get('url') or '')
    if normalized_url:
        return f"url:{normalized_url}"
    return f"content:{bookmark_content_hash(bookmark)}"


def _cache_analysis_payload(result):
    return {
        'folder': result.get('folder'),
        'reason': result.get('reason'),
        'insights': result.get('insights'),
        'actionable': result.get('actionable'),
    }


def _cache_result_payload(result):
    return {
        key: value
        for key, value in (result or {}).items()
        if key not in ('cache_status', 'cache_key')
    }


def _bookmark_analysis_policy_signature():
    provider = _env_first(
        "LLM_PROVIDER",
        "HERMES_LLM_PROVIDER",
        "HERMES_PROVIDER",
        "HERMES_MODEL_PROVIDER",
        default="openrouter",
    ).lower()
    default_model = {
        "openrouter": "anthropic/claude-sonnet-4",
        "anthropic": "claude-sonnet-4",
        "openai": "gpt-4o-mini",
        "custom": "gpt-4o-mini",
        "openai-compatible": "gpt-4o-mini",
        "endpoint": "gpt-4o-mini",
    }.get(provider, "anthropic/claude-sonnet-4")
    return {
        'policy_version': os.environ.get('BOOKMARK_ANALYSIS_POLICY_VERSION', BOOKMARK_ANALYSIS_POLICY_VERSION),
        'provider': provider,
        'model': _env_first("LLM_MODEL", "HERMES_LLM_MODEL", "HERMES_MODEL", default=default_model),
        'temperature': _env_first("LLM_TEMPERATURE", "HERMES_LLM_TEMPERATURE", default="0.3"),
        'enrichment': {
            'fetch_timeout_seconds': FETCH_TIMEOUT_SECONDS,
            'fetch_max_bytes': FETCH_MAX_BYTES,
            'fetch_snippet_chars': FETCH_SNIPPET_CHARS,
            'max_enriched_links': MAX_ENRICHED_LINKS_PER_BOOKMARK,
            'video_transcription_enabled': VIDEO_TRANSCRIPTION_ENABLED,
            'video_fetch_timeout_seconds': VIDEO_FETCH_TIMEOUT_SECONDS,
            'video_fetch_max_bytes': VIDEO_FETCH_MAX_BYTES,
            'video_transcribe_max_seconds': VIDEO_TRANSCRIBE_MAX_SECONDS,
            'video_transcribe_provider': VIDEO_TRANSCRIBE_PROVIDER,
            'video_transcribe_model': VIDEO_TRANSCRIBE_MODEL,
        },
    }


def bookmark_analysis_signature(bookmark, cache_key=None):
    """Hash the inputs that make a cached bookmark analysis reusable."""
    return _stable_hash({
        'cache_version': BOOKMARK_ANALYSIS_CACHE_VERSION,
        'cache_key': cache_key or bookmark_dedupe_key(bookmark),
        'content_hash': bookmark_content_hash(bookmark),
        'policy': _bookmark_analysis_policy_signature(),
    })


def _fresh_bookmark_analysis_cache(load_error=None):
    cache = {'version': BOOKMARK_ANALYSIS_CACHE_VERSION, 'entries': {}}
    if load_error:
        cache['load_error'] = load_error
    return cache


def _prepare_bookmark_analysis_cache(cache):
    """Validate cache shape/version without silently reusing stale entries."""
    if not isinstance(cache, dict):
        return _fresh_bookmark_analysis_cache('invalid cache shape')

    version = cache.get('version')
    if version not in (None, BOOKMARK_ANALYSIS_CACHE_VERSION):
        cache.clear()
        cache.update(_fresh_bookmark_analysis_cache(
            f'cache version mismatch: {version} != {BOOKMARK_ANALYSIS_CACHE_VERSION}'
        ))
        return cache

    entries = cache.get('entries')
    if entries is None:
        cache['entries'] = {}
    elif not isinstance(entries, dict):
        cache.clear()
        cache.update(_fresh_bookmark_analysis_cache('invalid cache entries shape'))
        return cache

    cache['version'] = BOOKMARK_ANALYSIS_CACHE_VERSION
    cache.pop('load_error', None)
    return cache


async def analyze_bookmarks_with_cache(bookmarks, analyze_func, cache=None):
    """Deduplicate same-run inputs and reuse cached analysis across repeated runs."""
    cache = _prepare_bookmark_analysis_cache(cache if cache is not None else {})
    entries = cache['entries']
    stats = {'hits': 0, 'misses': 0, 'duplicates_suppressed': 0}
    duplicates = []
    results = []
    seen = {}

    for index, bookmark in enumerate(bookmarks or []):
        key = bookmark_dedupe_key(bookmark)
        if key in seen:
            stats['duplicates_suppressed'] += 1
            duplicates.append({
                'duplicate_index': index,
                'original_index': seen[key],
                'cache_key': key,
                'url': bookmark.get('url') or '',
            })
            continue
        seen[key] = index

        signature = bookmark_analysis_signature(bookmark, key)
        cached = entries.get(key)
        if (
            cached
            and cached.get('analysis_signature') == signature
            and isinstance(cached.get('result'), dict)
        ):
            stats['hits'] += 1
            result = {**cached['result'], **bookmark}
            result['cache_status'] = 'hit'
            result['cache_key'] = key
            results.append(result)
            continue

        stats['misses'] += 1
        analyzed = await analyze_func(bookmark)
        result = {**bookmark, **analyzed}
        result['cache_status'] = 'miss'
        result['cache_key'] = key
        entries[key] = {
            'analysis': _cache_analysis_payload(result),
            'result': _cache_result_payload(result),
            'analysis_signature': signature,
            'cached_at': datetime.now().isoformat(),
            'source_url': bookmark.get('url') or '',
            'content_hash': bookmark_content_hash(bookmark),
        }
        results.append(result)

    return {'results': results, 'cache': cache, 'cache_stats': stats, 'duplicates': duplicates}


def load_bookmark_analysis_cache(path=BOOKMARK_ANALYSIS_CACHE_FILE):
    try:
        with open(path) as f:
            cache = json.load(f)
    except FileNotFoundError:
        return _fresh_bookmark_analysis_cache()
    except Exception as exc:
        return _fresh_bookmark_analysis_cache(str(exc)[:300])
    return _prepare_bookmark_analysis_cache(cache)


def save_bookmark_analysis_cache(cache, path=BOOKMARK_ANALYSIS_CACHE_FILE):
    path.parent.mkdir(exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + '.tmp')
    with open(tmp_path, 'w') as f:
        json.dump(cache, f, indent=2, sort_keys=True)
    os.replace(tmp_path, path)


def _parse_html_metadata(source_url, content_type, body):
    parser = _MetadataHTMLParser()
    parser.feed(body)
    title = (
        parser.meta.get('og:title')
        or parser.meta.get('twitter:title')
        or parser.title
    )
    description = (
        parser.meta.get('og:description')
        or parser.meta.get('twitter:description')
        or parser.meta.get('description')
    )
    snippet = _clean_text(' '.join(parser.paragraphs))[:FETCH_SNIPPET_CHARS]
    return {
        'url': source_url,
        'status': 'ok',
        'content_type': content_type,
        'title': _clean_text(title),
        'description': _clean_text(description),
        'text_snippet': snippet,
    }


def _is_private_or_local(hostname):
    if not hostname:
        return True
    if hostname in ('localhost', '0.0.0.0') or hostname.endswith('.local'):
        return True
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            return True
    return False


def _safe_fetch_url(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        return {'url': url, 'status': 'skipped', 'error': f'unsupported scheme: {parsed.scheme}'}
    if _is_private_or_local(parsed.hostname):
        return {'url': url, 'status': 'skipped', 'error': 'private/local host blocked'}

    request = urllib.request.Request(
        url,
        headers={
            'User-Agent': 'Mozilla/5.0 (compatible; HermesBookmarkAgent/1.0)',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
            content_type = response.headers.get('content-type', '').split(';')[0].lower()
            final_url = response.geturl()
            body_bytes = response.read(FETCH_MAX_BYTES + 1)
            truncated = len(body_bytes) > FETCH_MAX_BYTES
            body_bytes = body_bytes[:FETCH_MAX_BYTES]
            if 'html' not in content_type and 'xml' not in content_type and not content_type.startswith('text/'):
                return {
                    'url': url,
                    'final_url': final_url,
                    'status': 'skipped',
                    'content_type': content_type,
                    'error': 'non-text content',
                    'truncated': truncated,
                }
            charset = response.headers.get_content_charset() or 'utf-8'
            body = body_bytes.decode(charset, errors='replace')
            result = _parse_html_metadata(final_url, content_type, body)
            result['original_url'] = url
            result['truncated'] = truncated
            return result
    except Exception as exc:
        return {'url': url, 'status': 'error', 'error': str(exc)[:300]}


async def _browser_fetch_x_article(page, url):
    """Fetch same-origin X article text with browser cookies when possible."""
    article_page = None
    try:
        article_page = await page.context.new_page()
        response = await article_page.goto(url, wait_until='domcontentloaded', timeout=FETCH_TIMEOUT_SECONDS * 1000)
        await article_page.wait_for_timeout(2500)
        data = await article_page.evaluate(
            """({maxChars}) => {
                const meta = (selector) => document.querySelector(selector)?.getAttribute('content') || '';
                const article = document.querySelector('article')?.innerText || '';
                const main = document.querySelector('main')?.innerText || '';
                const body = article || main || document.body?.innerText || '';
                return {
                    title: document.title || meta('meta[property="og:title"]') || meta('meta[name="twitter:title"]'),
                    description: meta('meta[property="og:description"]') || meta('meta[name="twitter:description"]') || meta('meta[name="description"]'),
                    text: body.slice(0, maxChars),
                    final_url: location.href,
                };
            }""",
            {'maxChars': FETCH_SNIPPET_CHARS},
        )
        status = response.status if response else None
        if status and status >= 400:
            return {'url': url, 'status': 'error', 'error': f'browser goto HTTP {status}', 'fetch_mode': 'browser'}
        return {
            'url': data.get('final_url') or url,
            'original_url': url,
            'status': 'ok',
            'content_type': response.headers.get('content-type', '') if response else '',
            'title': _clean_text(data.get('title')),
            'description': _clean_text(data.get('description')),
            'text_snippet': _clean_text(data.get('text'))[:FETCH_SNIPPET_CHARS],
            'truncated': len(data.get('text') or '') >= FETCH_SNIPPET_CHARS,
            'fetch_mode': 'browser',
        }
    except Exception as exc:
        return {'url': url, 'status': 'error', 'error': str(exc)[:300], 'fetch_mode': 'browser'}
    finally:
        if article_page:
            await article_page.close()


def _normalize_candidate_url(url):
    """Normalize X card/link URLs before safe fetching."""
    url = (url or '').strip()
    if not url:
        return ''
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme in ('http', 'https'):
        return url
    if not parsed.scheme and re.match(r'^[A-Za-z0-9.-]+\.[A-Za-z]{2,}(/.*)?$', url):
        return f'https://{url}'
    return ''


def _collect_candidate_links(bookmark):
    candidates = []

    def add(url, source):
        normalized_url = _normalize_candidate_url(url)
        if normalized_url:
            candidates.append({'url': normalized_url, 'source': source})

    for item in bookmark.get('external_urls') or []:
        add(item.get('expanded_url') or item.get('url'), 'tweet_external_url')
    card = bookmark.get('card') or {}
    add(card.get('url'), 'tweet_card')

    quoted = bookmark.get('quoted_tweet') or {}
    for item in quoted.get('external_urls') or []:
        add(item.get('expanded_url') or item.get('url'), 'quoted_external_url')
    quoted_card = quoted.get('card') or {}
    add(quoted_card.get('url'), 'quoted_card')

    seen = set()
    deduped = []
    for item in candidates:
        normalized = urllib.parse.urldefrag(item['url'])[0]
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append({'url': normalized, 'source': item['source']})
    return deduped[:MAX_ENRICHED_LINKS_PER_BOOKMARK]


async def enrich_bookmark_links(page, bookmark):
    """Fetch bounded metadata/snippets for external URLs and X article links."""
    enrichments = []
    for item in _collect_candidate_links(bookmark):
        url = item['url']
        parsed = urllib.parse.urlparse(url)
        is_x_article = parsed.netloc in ('x.com', 'twitter.com', 'www.x.com', 'www.twitter.com') and parsed.path.startswith('/i/article/')
        if is_x_article and parsed.scheme == 'http':
            url = urllib.parse.urlunparse(parsed._replace(scheme='https'))
            parsed = urllib.parse.urlparse(url)
        if is_x_article:
            enrichment = await _browser_fetch_x_article(page, url)
            if enrichment.get('status') != 'ok':
                enrichment = await asyncio.to_thread(_safe_fetch_url, url)
        else:
            enrichment = await asyncio.to_thread(_safe_fetch_url, url)
        enrichment['source'] = item['source']
        enrichments.append(enrichment)
    bookmark['link_enrichment'] = enrichments
    return bookmark


def _is_x_media_host(hostname):
    hostname = (hostname or '').lower()
    return hostname == 'video.twimg.com' or hostname.endswith('.video.twimg.com')


def _select_transcribable_video_url(media):
    best = media.get('best_video_variant') or {}
    if best.get('content_type') == 'video/mp4' and best.get('url'):
        return best.get('url')
    mp4_variants = [
        variant for variant in media.get('video_variants') or []
        if variant.get('content_type') == 'video/mp4' and variant.get('url')
    ]
    if not mp4_variants:
        return ''
    return max(mp4_variants, key=lambda variant: variant.get('bitrate') or 0).get('url') or ''


def _download_bounded_video(url, destination):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != 'https':
        return {'status': 'skipped', 'error': 'video download requires https', 'url': url}
    if not _is_x_media_host(parsed.hostname):
        return {'status': 'skipped', 'error': 'non-X video host blocked', 'url': url}
    if _is_private_or_local(parsed.hostname):
        return {'status': 'skipped', 'error': 'private/local host blocked', 'url': url}

    request = urllib.request.Request(
        url,
        headers={
            'User-Agent': 'Mozilla/5.0 (compatible; HermesBookmarkAgent/1.0)',
            'Accept': 'video/mp4,video/*;q=0.8,*/*;q=0.5',
        },
    )
    try:
        total = 0
        with urllib.request.urlopen(request, timeout=VIDEO_FETCH_TIMEOUT_SECONDS) as response:
            content_type = response.headers.get('content-type', '').split(';')[0].lower()
            final_url = response.geturl()
            final_parsed = urllib.parse.urlparse(final_url)
            if not _is_x_media_host(final_parsed.hostname) or _is_private_or_local(final_parsed.hostname):
                return {'status': 'skipped', 'error': 'unsafe video redirect blocked', 'url': url, 'final_url': final_url}
            if 'video' not in content_type and content_type != 'application/octet-stream':
                return {'status': 'skipped', 'error': f'unexpected video content-type: {content_type}', 'url': url, 'final_url': final_url}
            with open(destination, 'wb') as out:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > VIDEO_FETCH_MAX_BYTES:
                        return {'status': 'skipped', 'error': 'video exceeds byte limit', 'url': url, 'final_url': final_url, 'bytes': total}
                    out.write(chunk)
        return {'status': 'ok', 'url': url, 'final_url': final_url, 'content_type': content_type, 'bytes': total}
    except Exception as exc:
        return {'status': 'error', 'url': url, 'error': str(exc)[:300]}


def _extract_audio_for_transcription(video_path, audio_path):
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        return {'status': 'skipped', 'error': 'ffmpeg not installed'}
    cmd = [
        ffmpeg,
        '-hide_banner',
        '-loglevel', 'error',
        '-y',
        '-t', str(VIDEO_TRANSCRIBE_MAX_SECONDS),
        '-i', video_path,
        '-vn',
        '-ac', '1',
        '-ar', '16000',
        '-f', 'mp3',
        audio_path,
    ]
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=VIDEO_FETCH_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return {'status': 'error', 'error': 'ffmpeg audio extraction timed out'}
    if completed.returncode != 0:
        return {'status': 'error', 'error': (completed.stderr or completed.stdout)[:300]}
    if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
        return {'status': 'skipped', 'error': 'no audio track extracted'}
    return {'status': 'ok', 'audio_bytes': os.path.getsize(audio_path)}


def _transcribe_audio_file(audio_path):
    if VIDEO_TRANSCRIBE_PROVIDER == 'openrouter':
        return {
            'status': 'skipped',
            'error': 'OpenRouter chat models are configured for bookmark analysis; no OpenRouter audio transcription endpoint is available in this agent',
            'model': VIDEO_TRANSCRIBE_MODEL,
            'provider': 'openrouter',
        }
    if VIDEO_TRANSCRIBE_PROVIDER != 'openai':
        return {'status': 'skipped', 'error': f'unsupported transcription provider: {VIDEO_TRANSCRIBE_PROVIDER}', 'provider': VIDEO_TRANSCRIBE_PROVIDER}
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        return {'status': 'skipped', 'error': 'OPENAI_API_KEY not set', 'provider': 'openai'}
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        with open(audio_path, 'rb') as audio_file:
            transcription = client.audio.transcriptions.create(
                model=VIDEO_TRANSCRIBE_MODEL,
                file=audio_file,
            )
        text = getattr(transcription, 'text', None) or str(transcription)
        return {'status': 'ok', 'text': _clean_text(text)[:FETCH_SNIPPET_CHARS], 'model': VIDEO_TRANSCRIBE_MODEL, 'provider': VIDEO_TRANSCRIBE_PROVIDER}
    except Exception as exc:
        return {'status': 'error', 'error': str(exc)[:300], 'model': VIDEO_TRANSCRIBE_MODEL, 'provider': VIDEO_TRANSCRIBE_PROVIDER}


def _transcribe_video_url(url):
    with tempfile.TemporaryDirectory(prefix='bookmark-video-') as tmpdir:
        video_path = os.path.join(tmpdir, 'video.mp4')
        audio_path = os.path.join(tmpdir, 'audio.mp3')
        download = _download_bounded_video(url, video_path)
        if download.get('status') != 'ok':
            return download
        audio = _extract_audio_for_transcription(video_path, audio_path)
        if audio.get('status') != 'ok':
            return {**download, **audio}
        transcript = _transcribe_audio_file(audio_path)
        return {**download, 'audio_bytes': audio.get('audio_bytes'), **transcript}


async def enrich_bookmark_media(bookmark):
    """Optionally transcribe bounded native X videos. Disabled by default."""
    enrichments = []
    for media in bookmark.get('media') or []:
        video_url = _select_transcribable_video_url(media)
        if not video_url:
            continue
        enrichment = {
            'media_id': media.get('id'),
            'type': media.get('type'),
            'url': video_url,
            'duration_seconds': media.get('duration_seconds'),
            'status': 'skipped',
            'error': 'video transcription disabled',
        }
        if VIDEO_TRANSCRIPTION_ENABLED:
            enrichment = await asyncio.to_thread(_transcribe_video_url, video_url)
            enrichment.update({
                'media_id': media.get('id'),
                'type': media.get('type'),
                'duration_seconds': media.get('duration_seconds'),
            })
        enrichments.append(enrichment)
    bookmark['media_enrichment'] = enrichments
    return bookmark


def _extract_folder_entities(payload):
    """Extract X bookmark folder id/name pairs from BookmarkFoldersSlice response shapes."""
    folders = []
    seen = set()

    def visit(value):
        if isinstance(value, dict):
            folder_id = value.get('id') or value.get('id_str') or value.get('rest_id')
            name = value.get('name')
            if folder_id and name and folder_id not in seen:
                seen.add(folder_id)
                folders.append({'id': str(folder_id), 'name': str(name)})
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)
    return folders


def _folder_name_for_key(folder_key):
    return FOLDERS.get(folder_key, folder_key)


def _should_move_to_folder(folder_key):
    return folder_key and folder_key != 'delete'


async def x_graphql_request(page, operation_name, variables=None, query_id=None):
    """Call X GraphQL from the authenticated browser context."""
    query_id = query_id or GRAPHQL_OPERATION_IDS.get(operation_name)
    if not query_id:
        return {'ok': False, 'status': 0, 'error': f'missing query id for {operation_name}'}
    if not X_BEARER_TOKEN:
        return {'ok': False, 'status': 0, 'error': 'X_BEARER_TOKEN is required for X GraphQL mutations'}
    variables = variables or {}
    return await page.evaluate(
        """async ({operationName, queryId, variables, bearerToken}) => {
            const csrf = document.cookie.match(/(?:^|; )ct0=([^;]+)/)?.[1] || '';
            const response = await fetch(`https://x.com/i/api/graphql/${queryId}/${operationName}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Csrf-Token': decodeURIComponent(csrf),
                    'Authorization': `Bearer ${bearerToken}`,
                    'X-Twitter-Auth-Type': 'OAuth2Session',
                    'X-Twitter-Active-User': 'yes',
                    'Accept': '*/*',
                },
                credentials: 'include',
                body: JSON.stringify({variables, queryId}),
            });
            const text = await response.text();
            let json = null;
            try { json = JSON.parse(text); } catch (_) {}
            return {ok: response.ok, status: response.status, text, json};
        }""",
        {
            'operationName': operation_name,
            'queryId': query_id,
            'variables': variables,
            'bearerToken': X_BEARER_TOKEN,
        },
    )


async def fetch_bookmark_folders(page):
    result = await x_graphql_request(page, 'BookmarkFoldersSlice', {})
    if not result.get('ok'):
        return {'status': 'error', 'error': result.get('text') or result.get('error'), 'folders': [], 'raw': result}
    return {'status': 'ok', 'folders': _extract_folder_entities(result.get('json') or {}), 'raw': result}


async def create_bookmark_folder(page, name):
    result = await x_graphql_request(page, 'createBookmarkFolder', {'name': name})
    folders = _extract_folder_entities(result.get('json') or {})
    if result.get('ok') and folders:
        return {'status': 'ok', 'folder': folders[0], 'raw': result}
    return {'status': 'error', 'error': result.get('text') or result.get('error'), 'raw': result}


async def ensure_bookmark_folder(page, folder_key, folder_cache):
    name = _folder_name_for_key(folder_key)
    if name in folder_cache:
        return {'status': 'ok', 'folder': folder_cache[name], 'created': False}

    fetched = await fetch_bookmark_folders(page)
    if fetched.get('status') == 'ok':
        for folder in fetched.get('folders', []):
            folder_cache[folder['name']] = folder
        if name in folder_cache:
            return {'status': 'ok', 'folder': folder_cache[name], 'created': False}

    created = await create_bookmark_folder(page, name)
    if created.get('status') == 'ok':
        folder_cache[name] = created['folder']
        return {'status': 'ok', 'folder': created['folder'], 'created': True}
    return {'status': 'error', 'error': created.get('error') or fetched.get('error') or f'could not ensure folder {name}'}


async def delete_bookmark(page, tweet_id):
    result = await x_graphql_request(page, 'DeleteBookmark', {'tweet_id': str(tweet_id)})
    data = (result.get('json') or {}).get('data') or {}
    if result.get('ok') and data.get('tweet_bookmark_delete') == 'Done':
        return {'action': 'delete', 'status': 'ok', 'tweet_id': str(tweet_id)}
    return {'action': 'delete', 'status': 'error', 'tweet_id': str(tweet_id), 'error': result.get('text') or result.get('error'), 'raw_status': result.get('status')}


async def move_bookmark_to_folder(page, tweet_id, folder_id, folder_name):
    variables = {'bookmark_collection_id': str(folder_id), 'tweet_id': str(tweet_id)}
    result = await x_graphql_request(page, 'bookmarkTweetToFolder', variables)
    data = (result.get('json') or {}).get('data') or {}
    if result.get('ok') and data.get('bookmark_collection_tweet_put') == 'Done':
        return {'action': 'move', 'status': 'ok', 'tweet_id': str(tweet_id), 'folder_id': str(folder_id), 'folder_name': folder_name}
    return {'action': 'move', 'status': 'error', 'tweet_id': str(tweet_id), 'folder_id': str(folder_id), 'folder_name': folder_name, 'error': result.get('text') or result.get('error'), 'raw_status': result.get('status')}


async def apply_bookmark_action(page, result, folder_cache):
    """Apply the analyzed bookmark action. Dry-run callers should not call this."""
    tweet_id = result.get('id')
    folder_key = result.get('folder')
    if not tweet_id:
        return {'action': 'skip', 'status': 'skipped', 'error': 'missing tweet id'}
    if folder_key == 'delete' or result.get('deleted'):
        return await delete_bookmark(page, tweet_id)
    if _should_move_to_folder(folder_key):
        folder = await ensure_bookmark_folder(page, folder_key, folder_cache)
        if folder.get('status') != 'ok':
            return {'action': 'move', 'status': 'error', 'tweet_id': str(tweet_id), 'folder_name': _folder_name_for_key(folder_key), 'error': folder.get('error')}
        folder_info = folder['folder']
        return await move_bookmark_to_folder(page, tweet_id, folder_info['id'], folder_info['name'])
    return {'action': 'skip', 'status': 'skipped', 'tweet_id': str(tweet_id), 'reason': f'no executable action for folder {folder_key}'}


def summarize_action_results(action_results):
    summary = {'ok': 0, 'error': 0, 'skipped': 0, 'by_action': {}}
    for item in action_results or []:
        status = item.get('status', 'skipped')
        action = item.get('action', 'unknown')
        if status in summary:
            summary[status] += 1
        summary['by_action'][action] = summary['by_action'].get(action, 0) + 1
    return summary


def write_bookmark_outputs(results, summary, output_dir=OUTPUT_DIR, timestamp=None, generated_at=None):
    """Write legacy analysis/summary files plus the canonical versioned run artifact."""
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)
    timestamp = timestamp or datetime.now().strftime('%Y%m%d_%H%M%S')
    generated_at = generated_at or datetime.now().isoformat()

    analysis_file = output_dir / f"bookmark_analysis_{timestamp}.json"
    summary_file = output_dir / f"bookmark_summary_{timestamp}.json"
    artifact_file = output_dir / f"bookmark_artifact_{timestamp}.json"

    with open(analysis_file, 'w') as f:
        json.dump(results, f, indent=2)
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)

    artifact = bookmark_schema.build_bookmark_run_artifact(
        summary=summary,
        analysis=results,
        generated_at=generated_at,
    )
    with open(artifact_file, 'w') as f:
        json.dump(artifact, f, indent=2)

    return {
        'analysis': str(analysis_file),
        'summary': str(summary_file),
        'artifact': str(artifact_file),
    }


def _media_analysis_context(media_items):
    """Compact native X media details for LLM analysis without huge URL payloads."""
    summaries = []
    for media in media_items or []:
        best_video = media.get('best_video_variant') or {}
        summaries.append({
            'type': media.get('type'),
            'media_url': media.get('media_url'),
            'expanded_url': media.get('expanded_url'),
            'alt_text': (media.get('alt_text') or '')[:500],
            'duration_seconds': media.get('duration_seconds'),
            'aspect_ratio': media.get('aspect_ratio'),
            'width': media.get('width'),
            'height': media.get('height'),
            'video_variant_count': len(media.get('video_variants') or []),
            'best_video_bitrate': best_video.get('bitrate'),
            'best_video_url': best_video.get('url'),
        })
    return summaries


def _bookmark_analysis_context(bookmark):
    """Compact bookmark metadata for LLM analysis."""
    context = {
        'author': bookmark.get('author'),
        'author_name': bookmark.get('author_name'),
        'content': (bookmark.get('text') or '')[:1200],
        'url': bookmark.get('url'),
        'deleted_or_unavailable': bookmark.get('deleted', False),
        'external_urls': [u.get('expanded_url') for u in bookmark.get('external_urls', []) if u.get('expanded_url')],
        'media': _media_analysis_context(bookmark.get('media')),
        'article_or_card': bookmark.get('card'),
        'media_enrichment': [
            {
                'media_id': item.get('media_id'),
                'type': item.get('type'),
                'status': item.get('status'),
                'duration_seconds': item.get('duration_seconds'),
                'bytes': item.get('bytes'),
                'audio_bytes': item.get('audio_bytes'),
                'transcript': (item.get('text') or '')[:1200],
                'error': item.get('error'),
            }
            for item in bookmark.get('media_enrichment', [])
        ],
        'link_enrichment': [
            {
                'source': item.get('source'),
                'url': item.get('url') or item.get('original_url'),
                'status': item.get('status'),
                'content_type': item.get('content_type'),
                'title': item.get('title'),
                'description': item.get('description'),
                'text_snippet': (item.get('text_snippet') or '')[:1200],
                'error': item.get('error'),
            }
            for item in bookmark.get('link_enrichment', [])
        ],
        'quoted_tweet': None,
    }
    quoted = bookmark.get('quoted_tweet')
    if quoted:
        context['quoted_tweet'] = {
            'author': quoted.get('author'),
            'content': (quoted.get('text') or '')[:700],
            'url': quoted.get('url'),
            'external_urls': [u.get('expanded_url') for u in quoted.get('external_urls', []) if u.get('expanded_url')],
            'media': _media_analysis_context(quoted.get('media')),
        }
    return json.dumps(context, indent=2, ensure_ascii=False)


def _heuristic_bookmark_analysis(bookmark, reason):
    """Local fallback when the LLM provider fails."""
    text = " ".join(
        str(part or "")
        for part in [
            bookmark.get('text', ''),
            bookmark.get('url', ''),
            bookmark.get('author', ''),
            bookmark.get('author_name', ''),
        ]
    ).strip()
    lower = text.lower()

    if not lower or lower.startswith('https://t.co/') or len(lower) < 30:
        return {
            "folder": "delete",
            "reason": f"Heuristic fallback after LLM failure: {reason}",
            "insights": bookmark.get('text', '')[:100],
            "actionable": None,
        }

    scored = []
    folder_keywords = {
        "ai_tools": ["claude", "codex", "hermes", "agent", "agents", "llm", "mcp", "prompt", "skill", "worktree", "workflow", "automation", "openrouter", "anthropic", "openai"],
        "devops": ["docker", "kubernetes", "server", "vps", "devops", "infra", "cloudflare", "tailscale", "fail2ban", "ufw", "deployment", "monitoring", "ssh"],
        "coding": ["typescript", "javascript", "python", "rust", "react", "frontend", "backend", "api", "graphql", "git", "repo", "code", "programming"],
        "design": ["design", "ux", "ui", "typography", "animation", "visual", "product design", "figma", "icon", "frontend"],
        "productivity": ["obsidian", "note", "notes", "knowledge", "memory", "schedule", "kanban", "task", "productivity", "workflow"],
        "aviation": ["aviation", "pilot", "flying", "checkride", "logbook", "airline", "cfi", "pic", "sic", "flight"],
        "business": ["business", "startup", "entrepreneur", "marketing", "sales", "revenue", "customers", "newsletter", "side hustle", "wealth"],
        "ideas": ["idea", "inspiration", "thought", "insight", "lessons", "strategy", "metaphor"],
    }
    for folder, keywords in folder_keywords.items():
        score = sum(2 if keyword in lower else 0 for keyword in keywords)
        if score:
            scored.append((score, folder))

    if scored:
        scored.sort(reverse=True)
        folder = scored[0][1]
    else:
        folder = 'archive'

    insight = bookmark.get('text', '')[:180].strip() or bookmark.get('url', '')
    actionable_map = {
        'ai_tools': 'Review the linked agent workflow or skill pack and extract reusable patterns.',
        'devops': 'Compare the workflow against your current infra and note any hardening or automation ideas.',
        'coding': 'Check the implementation details or repo and see whether the pattern fits an existing codebase.',
        'design': 'Evaluate whether the design pattern or UI treatment is worth reusing.',
        'productivity': 'Decide whether this should become a reusable note, template, or workflow.',
        'aviation': 'Review for any operational, instructional, or logbook value.',
        'business': 'Assess whether the idea is actionable as a product, marketing, or revenue lever.',
        'ideas': 'Capture the core concept in a note and link it to related work.',
        'archive': None,
    }
    return {
        "folder": folder,
        "reason": f"Heuristic fallback after LLM failure: {reason}",
        "insights": insight,
        "actionable": actionable_map.get(folder),
    }


async def analyze_bookmark(llm, bookmark):
    """Analyze a single bookmark and recommend action."""
    prompt = f"""You are a critical but open-minded curator. Analyze this X bookmark and decide what to do with it.

Bookmark metadata, including native X videos/images, article cards, quoted tweets, and outside links when present:
{_bookmark_analysis_context(bookmark)}

Available actions:
- ai_tools: AI tools, agents, LLM techniques, automation
- devops: Infrastructure, Docker, Kubernetes, servers, monitoring
- coding: Programming languages, frameworks, code quality
- design: UI/UX, design systems, visual design
- ideas: Concepts, inspiration, thought-provoking content
- productivity: Tools, workflows, efficiency
- aviation: Flying, aviation tech, pilot stuff
- business: Startups, entrepreneurship, marketing
- archive: Worth keeping but no immediate action needed
- delete: Low value, outdated, or not useful

Respond in this exact JSON format:
{{
    "folder": "one of the action keys above",
    "reason": "brief explanation of why",
    "insights": "key takeaway or idea to remember",
    "actionable": "specific action item if applicable, or null"
}}

Be critical but fair. If it's just hype without substance, suggest delete. If it has a genuine insight, capture it."""
    
    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        content = response.content if hasattr(response, 'content') else str(response)
        
        # Extract JSON from response
        json_start = content.find('{')
        json_end = content.rfind('}') + 1
        if json_start >= 0 and json_end > json_start:
            result = json.loads(content[json_start:json_end])
            return result
        else:
            return {
                "folder": "archive",
                "reason": "Could not parse LLM response",
                "insights": bookmark['text'][:100],
                "actionable": None
            }
    except Exception as e:
        return _heuristic_bookmark_analysis(bookmark, str(e))


async def process_bookmarks(dry_run=True, max_bookmarks=20):
    """Main processing workflow."""
    print(f"[{'DRY RUN' if dry_run else 'EXECUTE'}] Processing X bookmarks...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=f"{PROFILE_DIR}/x-profile",
            headless=True,
            args=['--no-sandbox']
        )
        page = await browser.new_page()
        
        # Fetch bookmarks
        print("\n[1/4] Fetching bookmarks...")
        bookmarks = await fetch_bookmarks(page)
        print(f"Found {len(bookmarks)} bookmarks")
        
        if not bookmarks:
            print("No bookmarks found")
            await browser.close()
            return
        
        # Initialize LLM
        print("\n[2/4] Initializing LLM...")
        llm = get_llm()
        
        # Analyze each unique bookmark, reusing cached analysis where the input is unchanged.
        print(f"\n[3/4] Enriching and analyzing bookmarks (max {max_bookmarks})...")
        action_results = []
        folder_cache = {}
        target_bookmarks = bookmarks[:max_bookmarks]
        analysis_cache = load_bookmark_analysis_cache()
        if analysis_cache.get('load_error'):
            print(f"    → Analysis cache reset: {analysis_cache['load_error']}")

        async def analyze_miss(bookmark):
            print(f"\n  [MISS] @{bookmark['author']}: {bookmark['text'][:60]}...")
            enriched = await enrich_bookmark_links(page, bookmark)
            enriched = await enrich_bookmark_media(enriched)
            if enriched.get('link_enrichment'):
                ok = sum(1 for item in enriched['link_enrichment'] if item.get('status') == 'ok')
                print(f"    → Link enrichment: {ok}/{len(enriched['link_enrichment'])} ok")
            if enriched.get('media_enrichment'):
                ok = sum(1 for item in enriched['media_enrichment'] if item.get('status') == 'ok')
                print(f"    → Media enrichment: {ok}/{len(enriched['media_enrichment'])} ok")
            analysis = await analyze_bookmark(llm, enriched)
            return {**enriched, **analysis}

        analysis_run = await analyze_bookmarks_with_cache(target_bookmarks, analyze_miss, cache=analysis_cache)
        results = analysis_run['results']
        save_bookmark_analysis_cache(analysis_run['cache'])
        cache_stats = analysis_run['cache_stats']
        print(
            "    → Analysis cache: "
            f"{cache_stats['hits']} hits, {cache_stats['misses']} misses, "
            f"{cache_stats['duplicates_suppressed']} duplicates suppressed"
        )

        for i, result in enumerate(results):
            result['processed_at'] = datetime.now().isoformat()
            analysis = _cache_analysis_payload(result)
            print(
                f"\n  [{i+1}/{len(results)}] {result.get('cache_status', 'miss').upper()} "
                f"@{result.get('author', 'unknown')}: {(result.get('text') or '')[:60]}..."
            )
            print(f"    → Cache key: {result.get('cache_key')}")
            print(f"    → Folder: {FOLDERS.get(analysis['folder'], analysis['folder'])}")
            print(f"    → Reason: {analysis['reason']}")
            if analysis.get('insights'):
                print(f"    → Insight: {analysis['insights'][:100]}")

            planned_action = 'delete' if analysis.get('folder') == 'delete' or result.get('deleted') else 'move'
            result['planned_action'] = planned_action
            result['planned_folder_name'] = _folder_name_for_key(analysis.get('folder'))

            if dry_run:
                action_result = {
                    'action': planned_action,
                    'status': 'skipped',
                    'reason': 'dry-run',
                    'tweet_id': str(result.get('id') or ''),
                    'folder_name': result['planned_folder_name'],
                }
            else:
                action_result = await apply_bookmark_action(page, result, folder_cache)
                await page.wait_for_timeout(1500)
            result['action_result'] = action_result
            action_results.append(action_result)
            print(f"    → Action: {action_result.get('action')} / {action_result.get('status')}")
        
        # Save results
        print("\n[4/4] Saving results...")
        
        # Summary report
        summary = {
            'total_processed': len(results),
            'raw_bookmarks_seen': len(bookmarks),
            'input_bookmarks_considered': len(target_bookmarks),
            'dry_run': dry_run,
            'dedupe_cache': analysis_run['cache_stats'],
            'duplicate_bookmarks': analysis_run['duplicates'],
            'action_summary': summarize_action_results(action_results),
            'by_folder': {},
            'insights': [],
            'action_items': [],
            'edge_case_counts': {
                'deleted_or_unavailable': 0,
                'with_external_urls': 0,
                'with_media': 0,
                'with_media_alt_text': 0,
                'with_video': 0,
                'with_video_best_variant': 0,
                'with_media_enrichment': 0,
                'with_successful_media_transcript': 0,
                'with_media_enrichment_errors': 0,
                'with_cards': 0,
                'with_quoted_tweets': 0,
                'with_link_enrichment': 0,
                'with_successful_link_enrichment': 0,
                'with_link_enrichment_errors': 0,
            }
        }
        
        for r in results:
            folder = r['folder']
            summary['by_folder'][folder] = summary['by_folder'].get(folder, 0) + 1
            edge_counts = summary['edge_case_counts']
            if r.get('deleted'):
                edge_counts['deleted_or_unavailable'] += 1
            if r.get('external_urls'):
                edge_counts['with_external_urls'] += 1
            media_items = r.get('media', [])
            if media_items:
                edge_counts['with_media'] += 1
            if any(m.get('alt_text') for m in media_items):
                edge_counts['with_media_alt_text'] += 1
            if any(m.get('type') in ('video', 'animated_gif') or m.get('video_variants') for m in media_items):
                edge_counts['with_video'] += 1
            if any(m.get('best_video_variant') for m in media_items):
                edge_counts['with_video_best_variant'] += 1
            media_enrichment = r.get('media_enrichment', [])
            if media_enrichment:
                edge_counts['with_media_enrichment'] += 1
            if any(item.get('status') == 'ok' and item.get('text') for item in media_enrichment):
                edge_counts['with_successful_media_transcript'] += 1
            if any(item.get('status') == 'error' for item in media_enrichment):
                edge_counts['with_media_enrichment_errors'] += 1
            if r.get('card'):
                edge_counts['with_cards'] += 1
            if r.get('quoted_tweet'):
                edge_counts['with_quoted_tweets'] += 1
            if r.get('link_enrichment'):
                edge_counts['with_link_enrichment'] += 1
            if any(item.get('status') == 'ok' for item in r.get('link_enrichment', [])):
                edge_counts['with_successful_link_enrichment'] += 1
            if any(item.get('status') == 'error' for item in r.get('link_enrichment', [])):
                edge_counts['with_link_enrichment_errors'] += 1
            if r.get('insights'):
                summary['insights'].append({
                    'author': r['author'],
                    'insight': r['insights'],
                    'url': r['url']
                })
            if r.get('actionable'):
                summary['action_items'].append({
                    'author': r['author'],
                    'action': r['actionable'],
                    'url': r['url']
                })
        
        written_outputs = write_bookmark_outputs(results, summary)
        print(f"Saved full analysis to: {written_outputs['analysis']}")
        print(f"Saved summary to: {written_outputs['summary']}")
        print(f"Saved versioned artifact to: {written_outputs['artifact']}")
        
        # Print summary
        print("\n" + "="*60)
        print("PROCESSING SUMMARY")
        print("="*60)
        print(f"\nTotal bookmarks fetched: {len(bookmarks)}")
        print(f"Total bookmarks analyzed: {len(results)}")
        print("\nDedupe/cache:")
        print(f"  hits: {summary['dedupe_cache']['hits']}")
        print(f"  misses: {summary['dedupe_cache']['misses']}")
        print(f"  duplicates_suppressed: {summary['dedupe_cache']['duplicates_suppressed']}")
        print("\nBy folder:")
        for folder, count in sorted(summary['by_folder'].items(), key=lambda x: -x[1]):
            print(f"  {FOLDERS.get(folder, folder)}: {count}")
        
        print("\nEdge cases detected:")
        for key, count in summary['edge_case_counts'].items():
            print(f"  {key}: {count}")

        print("\nBookmark actions:")
        print(f"  ok: {summary['action_summary']['ok']}")
        print(f"  error: {summary['action_summary']['error']}")
        print(f"  skipped: {summary['action_summary']['skipped']}")
        for action, count in sorted(summary['action_summary']['by_action'].items()):
            print(f"  {action}: {count}")
        
        print(f"\nKey insights ({len(summary['insights'])}):")
        for item in summary['insights'][:5]:
            print(f"  • @{item['author']}: {item['insight'][:80]}...")
        
        if summary['action_items']:
            print(f"\nAction items ({len(summary['action_items'])}):")
            for item in summary['action_items'][:5]:
                print(f"  • @{item['author']}: {item['action'][:80]}...")
        
        if dry_run:
            print("\n[DRY RUN] No changes made to bookmarks")
            print("Run with --execute to apply changes")
        
        await browser.close()
        return results


async def main():
    parser = argparse.ArgumentParser(description='Process X bookmarks with AI analysis')
    parser.add_argument('--dry-run', action='store_true', default=True, help='Analyze without making changes')
    parser.add_argument('--execute', action='store_true', help='Actually move/delete bookmarks')
    parser.add_argument('--max', type=int, default=20, help='Maximum bookmarks to process')
    args = parser.parse_args()
    
    dry_run = not args.execute
    await process_bookmarks(dry_run=dry_run, max_bookmarks=args.max)


if __name__ == "__main__":
    asyncio.run(main())
