#!/usr/bin/env python3
"""
Form filler using browser-use.
Fills forms on a given URL based on field descriptions.
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


async def fill_form(url: str, fields: dict, profile_name: str = "default", submit: bool = False):
    profile_path = Path(PROFILE_DIR) / profile_name

    if CHROME_HOST:
        cdp_url = f"http://{CHROME_HOST}:{CHROME_PORT}"
        browser = BrowserSession(cdp_url=cdp_url)
    else:
        profile = BrowserProfile(
            headless=True,
            user_data_dir=str(profile_path),
        )
        browser = BrowserSession(browser_profile=profile)

    fields_desc = "\n".join([f"- {k}: {v}" for k, v in fields.items()])
    submit_instr = "Submit the form after filling." if submit else "Do NOT submit the form."

    task = (
        f"Go to {url}. Fill in the form with these values:\n{fields_desc}\n"
        f"{submit_instr} Return a summary of what was filled."
    )

    llm = get_llm()
    agent = Agent(task=task, llm=llm, browser_session=browser)

    print(f"[form-filler] Filling form at: {url}")
    result = await agent.run()
    print(f"[form-filler] Result: {result}")

    await browser.close()
    return result


async def main():
    parser = argparse.ArgumentParser(description="Fill a web form")
    parser.add_argument("url", help="URL with the form")
    parser.add_argument("--fields", required=True, help="JSON string of field values")
    parser.add_argument("--profile", default="default", help="Browser profile")
    parser.add_argument("--submit", action="store_true", help="Submit the form")
    args = parser.parse_args()

    fields = json.loads(args.fields)
    await fill_form(args.url, fields, profile_name=args.profile, submit=args.submit)


if __name__ == "__main__":
    asyncio.run(main())
