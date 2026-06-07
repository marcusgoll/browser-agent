#!/usr/bin/env python3
"""Tests for provider-agnostic bookmark LLM selection."""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import ANY, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import process_bookmarks as pb  # noqa: E402


class BookmarkLLMProviderTests(unittest.TestCase):
    def test_default_openrouter_provider_prefixes_model_and_uses_openrouter_key(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "or-key"}, clear=True), patch.object(
            pb, "ChatLiteLLM"
        ) as mock_llm:
            mock_llm.return_value = object()

            result = pb.get_llm()

        self.assertIs(result, mock_llm.return_value)
        mock_llm.assert_called_once_with(
            model="openrouter/anthropic/claude-sonnet-4",
            api_key="or-key",
            api_base="https://openrouter.ai/api/v1",
            temperature=0.3,
        )

    def test_anthropic_provider_uses_provider_specific_model_name(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "anth-key"}, clear=True), patch.object(
            pb, "ChatLiteLLM"
        ) as mock_llm:
            mock_llm.return_value = object()

            result = pb.get_llm()

        self.assertIs(result, mock_llm.return_value)
        mock_llm.assert_called_once_with(
            model="anthropic/claude-sonnet-4",
            api_key="anth-key",
            temperature=0.3,
        )

    def test_custom_openai_compatible_provider_uses_base_url(self):
        with patch.dict(
            os.environ,
            {
                "LLM_PROVIDER": "custom",
                "LLM_BASE_URL": "https://hermes.example/v1",
                "LLM_API_KEY": "custom-key",
            },
            clear=True,
        ), patch.object(pb, "ChatOpenAI") as mock_llm:
            mock_llm.return_value = object()

            result = pb.get_llm()

        self.assertIs(result, mock_llm.return_value)
        mock_llm.assert_called_once_with(
            model="gpt-4o-mini",
            api_key=ANY,
            base_url="https://hermes.example/v1",
            temperature=0.3,
        )

    def test_heuristic_fallback_routes_url_only_bookmarks_to_delete(self):
        bookmark = {"text": "https://t.co/abc123", "url": "https://x.com/user/status/1"}
        result = pb._heuristic_bookmark_analysis(bookmark, "boom")

        self.assertEqual(result["folder"], "delete")
        self.assertIn("Heuristic fallback", result["reason"])

    def test_heuristic_fallback_routes_agent_bookmarks_to_ai_tools(self):
        bookmark = {
            "text": "Claude Code feels different with skills and multi-agent orchestration.",
            "url": "https://x.com/user/status/2",
        }
        result = pb._heuristic_bookmark_analysis(bookmark, "boom")

        self.assertEqual(result["folder"], "ai_tools")
        self.assertIsNotNone(result["actionable"])


if __name__ == "__main__":
    unittest.main()
