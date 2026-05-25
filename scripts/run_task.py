#!/usr/bin/env python3
"""
Browser-use task runner for homelab.
Supports: local Playwright browser OR connecting to existing Chrome (CDP).
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
    """Initialize LLM from env vars."""
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
        raise ValueError(f"Unknown LLM provider: {provider}")


async def run_task(task: str, profile_name: str = "default", headless: bool = True):
    """Run a browser-use task."""
    profile_path = Path(PROFILE_DIR) / profile_name
    profile_path.mkdir(parents=True, exist_ok=True)

    output_path = Path(OUTPUT_DIR)
    output_path.mkdir(parents=True, exist_ok=True)

    # Determine browser backend
    if CHROME_HOST:
        cdp_url = f"http://{CHROME_HOST}:{CHROME_PORT}"
        print(f"[browser-agent] Connecting to Chrome at {cdp_url}")
        browser = BrowserSession(cdp_url=cdp_url)
    else:
        print(f"[browser-agent] Using local Playwright with profile: {profile_path}")
        profile = BrowserProfile(
            headless=headless,
            user_data_dir=str(profile_path),
        )
        browser = BrowserSession(browser_profile=profile)

    llm = get_llm()

    agent = Agent(
        task=task,
        llm=llm,
        browser_session=browser,
    )

    print(f"[browser-agent] Starting task: {task[:80]}...")
    result = await agent.run()

    # Save result
    result_file = output_path / f"result_{profile_name}_{asyncio.get_event_loop().time():.0f}.json"
    with open(result_file, "w") as f:
        json.dump({
            "task": task,
            "result": str(result),
            "profile": profile_name,
        }, f, indent=2)

    print(f"[browser-agent] Result saved to: {result_file}")
    print(f"[browser-agent] Result: {result}")

    await browser.close()
    return result


async def main():
    parser = argparse.ArgumentParser(description="Run browser-use tasks")
    parser.add_argument("task", help="Natural language task description")
    parser.add_argument("--profile", default="default", help="Browser profile name")
    parser.add_argument("--headed", action="store_true", help="Run with visible browser (for login)")
    args = parser.parse_args()

    await run_task(args.task, profile_name=args.profile, headless=not args.headed)


if __name__ == "__main__":
    asyncio.run(main())
