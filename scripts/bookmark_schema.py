#!/usr/bin/env python3
"""Canonical, versioned schema adapters for X bookmark processor artifacts.

The bookmark processor has historically emitted two legacy JSON shapes:
- bookmark_analysis_*.json: a list of per-bookmark analysis records.
- bookmark_summary_*.json: a summary dictionary consumed by feed_to_agents.py.

This module keeps those legacy payloads usable while defining a stable v1
artifact envelope for new downstream consumers.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

CURRENT_SCHEMA_VERSION = "bookmark-artifact/v1"
SUPPORTED_ARTIFACT_TYPES = {"bookmark_analysis", "bookmark_summary", "bookmark_run"}
REQUIRED_ARTIFACT_FIELDS = {"schema_version", "artifact_type", "generated_at", "data", "metadata"}

BOOKMARK_ARTIFACT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://schemas.hermes.local/bookmark-artifact/v1.json",
    "title": "X Bookmark Processor Artifact",
    "type": "object",
    "required": sorted(REQUIRED_ARTIFACT_FIELDS),
    "additionalProperties": False,
    "properties": {
        "schema_version": {"const": CURRENT_SCHEMA_VERSION},
        "artifact_type": {"enum": sorted(SUPPORTED_ARTIFACT_TYPES)},
        "generated_at": {"type": "string", "minLength": 1},
        "source": {"type": "string"},
        "metadata": {"type": "object"},
        "data": {},
    },
}


class BookmarkSchemaError(ValueError):
    """Raised when a bookmark artifact does not match the supported schema."""


def _generated_at(value: str | None = None) -> str:
    return value or datetime.now().isoformat()


def _record_count_for_summary(summary: dict[str, Any]) -> int:
    total = summary.get("total_processed", 0)
    return total if isinstance(total, int) else 0


def _artifact(
    *,
    artifact_type: str,
    data: Any,
    generated_at: str | None = None,
    metadata: dict[str, Any] | None = None,
    source: str = "x_bookmark_processor",
) -> dict[str, Any]:
    artifact = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "artifact_type": artifact_type,
        "generated_at": _generated_at(generated_at),
        "source": source,
        "metadata": metadata or {},
        "data": deepcopy(data),
    }
    validate_artifact(artifact)
    return artifact


def wrap_legacy_analysis(analysis: list[dict[str, Any]], generated_at: str | None = None) -> dict[str, Any]:
    """Wrap the legacy bookmark_analysis list in the canonical v1 envelope."""
    if not isinstance(analysis, list):
        raise BookmarkSchemaError("legacy analysis must be a list")
    return _artifact(
        artifact_type="bookmark_analysis",
        data=analysis,
        generated_at=generated_at,
        metadata={"record_count": len(analysis)},
    )


def wrap_legacy_summary(summary: dict[str, Any], generated_at: str | None = None) -> dict[str, Any]:
    """Wrap the legacy bookmark_summary dict in the canonical v1 envelope."""
    if not isinstance(summary, dict):
        raise BookmarkSchemaError("legacy summary must be a dict")
    return _artifact(
        artifact_type="bookmark_summary",
        data=summary,
        generated_at=generated_at,
        metadata={"record_count": _record_count_for_summary(summary)},
    )


def build_bookmark_run_artifact(
    *,
    summary: dict[str, Any],
    analysis: list[dict[str, Any]],
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build one canonical artifact containing both current output payloads."""
    if not isinstance(summary, dict):
        raise BookmarkSchemaError("summary must be a dict")
    if not isinstance(analysis, list):
        raise BookmarkSchemaError("analysis must be a list")
    return _artifact(
        artifact_type="bookmark_run",
        data={"summary": deepcopy(summary), "analysis": deepcopy(analysis)},
        generated_at=generated_at,
        metadata={
            "record_count": len(analysis),
            "summary_total_processed": _record_count_for_summary(summary),
        },
    )


def is_versioned_artifact(value: Any) -> bool:
    return isinstance(value, dict) and "schema_version" in value and "artifact_type" in value


def validate_artifact(artifact: dict[str, Any]) -> None:
    """Validate the supported v1 artifact envelope and expected data container shape."""
    if not isinstance(artifact, dict):
        raise BookmarkSchemaError("artifact must be a dict")
    missing = sorted(REQUIRED_ARTIFACT_FIELDS - artifact.keys())
    if missing:
        raise BookmarkSchemaError(f"missing required fields: {', '.join(missing)}")
    version = artifact.get("schema_version")
    if version != CURRENT_SCHEMA_VERSION:
        raise BookmarkSchemaError(f"unsupported schema_version: {version}")
    artifact_type = artifact.get("artifact_type")
    if artifact_type not in SUPPORTED_ARTIFACT_TYPES:
        raise BookmarkSchemaError(f"unsupported artifact_type: {artifact_type}")
    if not artifact.get("generated_at") or not isinstance(artifact.get("generated_at"), str):
        raise BookmarkSchemaError("generated_at must be a non-empty string")
    if not isinstance(artifact.get("metadata"), dict):
        raise BookmarkSchemaError("metadata must be a dict")

    data = artifact.get("data")
    if artifact_type == "bookmark_analysis" and not isinstance(data, list):
        raise BookmarkSchemaError("bookmark_analysis data must be a list")
    if artifact_type == "bookmark_summary" and not isinstance(data, dict):
        raise BookmarkSchemaError("bookmark_summary data must be a dict")
    if artifact_type == "bookmark_run":
        if not isinstance(data, dict):
            raise BookmarkSchemaError("bookmark_run data must be a dict")
        if not isinstance(data.get("summary"), dict):
            raise BookmarkSchemaError("bookmark_run data.summary must be a dict")
        if not isinstance(data.get("analysis"), list):
            raise BookmarkSchemaError("bookmark_run data.analysis must be a list")


def unwrap_analysis(value: Any) -> list[dict[str, Any]]:
    """Return legacy analysis records from either legacy or v1 artifact input."""
    if isinstance(value, list):
        return value
    if is_versioned_artifact(value):
        validate_artifact(value)
        if value["artifact_type"] == "bookmark_analysis":
            return value["data"]
        if value["artifact_type"] == "bookmark_run":
            return value["data"]["analysis"]
    raise BookmarkSchemaError("input does not contain bookmark analysis data")


def unwrap_summary(value: Any) -> dict[str, Any]:
    """Return legacy summary data from either legacy or v1 artifact input."""
    if isinstance(value, dict) and not is_versioned_artifact(value):
        return value
    if is_versioned_artifact(value):
        validate_artifact(value)
        if value["artifact_type"] == "bookmark_summary":
            return value["data"]
        if value["artifact_type"] == "bookmark_run":
            return value["data"]["summary"]
    raise BookmarkSchemaError("input does not contain bookmark summary data")
