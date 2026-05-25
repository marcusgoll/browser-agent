#!/usr/bin/env python3
"""Test scrape task for browser-use using ChatLiteLLM."""
import asyncio
import os
from browser_use import Agent, BrowserSession
from browser_use.llm.litellm import ChatLiteLLM

async def main():
    browser = BrowserSession(headless=True)
    llm = ChatLiteLLM(
        model='openrouter/anthropic/claude-sonnet-4',
        api_key=os.environ['OPENROUTER_API_KEY'],
        api_base='https://openrouter.ai/api/v1',
        temperature=0.1,
    )
    agent = Agent(
        task='Go to http://example.com and extract the page title and all visible text',
        llm=llm,
        browser_session=browser,
    )
    result = await agent.run()
    print('RESULT:', result)
    await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
