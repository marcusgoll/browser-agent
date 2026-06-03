# X Bookmark Artifact Schema v1

## Purpose

Bookmark processing now has a canonical, versioned artifact envelope so downstream
processors can depend on an explicit schema version while legacy consumers keep
reading the historical JSON payloads.

## Legacy outputs still emitted

`process_bookmarks.py` continues to write the existing files unchanged:

- `bookmark_analysis_<timestamp>.json` — legacy list of per-bookmark records.
- `bookmark_summary_<timestamp>.json` — legacy summary dictionary used by
  `feed_to_agents.py` and existing opportunity routing tests.

These files are intentionally not wrapped so current consumers do not need an
immediate migration.

## New canonical artifact

Each run also writes:

- `bookmark_artifact_<timestamp>.json`

Envelope shape:

```json
{
  "schema_version": "bookmark-artifact/v1",
  "artifact_type": "bookmark_run",
  "generated_at": "2026-05-31T09:04:10",
  "source": "x_bookmark_processor",
  "metadata": {
    "record_count": 2,
    "summary_total_processed": 2
  },
  "data": {
    "summary": {"total_processed": 2},
    "analysis": []
  }
}
```

The schema/adapters live in `scripts/bookmark_schema.py`:

- `CURRENT_SCHEMA_VERSION` is the only supported version.
- `BOOKMARK_ARTIFACT_SCHEMA` documents the JSON envelope.
- `build_bookmark_run_artifact(summary=..., analysis=...)` creates the combined
  artifact.
- `wrap_legacy_summary(...)` and `wrap_legacy_analysis(...)` create single-payload
  artifacts.
- `unwrap_summary(...)` and `unwrap_analysis(...)` accept either legacy payloads
  or v1 artifacts, preserving adapter compatibility.
- `validate_artifact(...)` fails loudly on missing fields, unsupported versions,
  unsupported artifact types, or incompatible data container shapes.

## Compatibility notes

- Existing summary and analysis JSON payloads remain byte-shape-compatible at the
  top level: downstream code that expects a dict summary or list analysis can keep
  reading the legacy files.
- New consumers should read `bookmark_artifact_<timestamp>.json` and gate behavior
  on `schema_version == "bookmark-artifact/v1"`.
- Consumers that may receive either legacy or canonical payloads should use
  `bookmark_schema.unwrap_summary(...)` and `bookmark_schema.unwrap_analysis(...)`
  instead of branching on file names.
- Rollback is safe: remove/ignore `bookmark_artifact_<timestamp>.json` generation
  and keep the legacy files. The adapters still accept historical output fixtures.
