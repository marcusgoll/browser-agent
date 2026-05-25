#!/usr/bin/env python3
"""
Simple scraper using browser-use.
Extracts text, links, or specific elements from a page.
"""

import os
import sys
import json
import asyncio
import argparse
from pathlib import Path

from browser_use import Agent, BrowserSession
from browser_use.browser.profile import BrowserProfile
from browser_use.llm.litellm import ChatLiteLLM

PROFILE_DIR = os.environ.get("BROWSER_PROFILE_DIR", "/app/profiles")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/app/output")
CHROME_HOST = os.environ.get("CHROME_HOST", "")
CHROME_PORT = os.environ.get("CHROME_PORT", "9222")


def get_llm():
    provider = os.environ.get("LLM_PROVIDER", "openrouter").lower()
    model = os.environ.get("LLM_MODEL", "anthropic/claude-sonnet-4")

    if provider == "openrouter":
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY not set")
        return ChatLiteLLM(
            model=f"openrouter/{model}",
            api_key=api_key,
            api_base="https://openrouter.ai/api/v1",
            temperature=0.1,
        )
    elif provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        return ChatLiteLLM(
            model=f"anthropic/{model}",
            api_key=api_key,
            temperature=0.1,
        )
    elif provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")
        return ChatLiteLLM(
            model=f"openai/{model}",
            api_key=api_key,
            temperature=0.1,
        )
    else:
        raise ValueError(f"Unknown provider: {provider}")


async def scrape(url: str, profile_name: str = "default", extract: str = "text"):
    profile_path = Path(PROFILE_DIR) / profile_name
    output_path = Path(OUTPUT_DIR)
    output_path.mkdir(parents=True, exist_ok=True)

    if CHROME_HOST:
        cdp_url = f"http://{CHROME_HOST}:{CHROME_PORT}"
        browser = BrowserSession(cdp_url=cdp_url)
    else:
        profile = BrowserProfile(
            headless=True,
            user_data_dir=str(profile_path),
        )
        browser = BrowserSession(browser_profile=profile)

    task = f"Go to {url} and extract the {extract}. Return the full content."
    llm = get_llm()
    agent = Agent(task=task, llm=llm, browser_session=browser)

    print(f"[scraper] Scraping: {url}")
    result = await agent.run()

    out_file = output_path / f"scrape_{profile_name}_{asyncio.get_event_loop().time():.0f}.txt"
    with open(out_file, "w") as f:
        f.write(str(result))

    print(f"[scraper] Saved to: {out_file}")
    print(f"[scraper] Preview: {str(result)[:500]}...")

    await browser.close()
    return result


async def main():
    parser = argparse.ArgumentParser(description="Scrape a webpage")
    parser.add_argument("url", help="URL to scrape")
    parser.add_argument("--profile", default="default", help="Browser profile")
    parser.add_argument("--extract", default="text", help="What to extract (text, links, etc.)")
    args = parser.parse_args()

    await scrape(args.url, profile_name=args.profile, extract=args.extract)


if __name__ == "__main__":
    asyncio.run(main())
