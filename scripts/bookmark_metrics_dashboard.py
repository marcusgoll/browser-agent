#!/usr/bin/env python3
"""Render a minimal local-first X bookmark metrics dashboard.

The dashboard is intentionally a static HTML report generated from a local JSON
artifact. It avoids charts and client-side aggregation so the displayed numbers
stay traceable to the emitted metrics file.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from typing import Any

METRIC_ROWS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("processed", "Processed", ("total_processed", "processed_count")),
    ("deduped", "Deduped", ("deduped_count", "duplicates_suppressed")),
    ("routed", "Routed", ("routed_count", "route_items")),
    ("note", "Notes", ("note_count", "notes", "note_generated", "notes_generated", "learning_notes")),
    ("idea", "Ideas", ("idea_count", "ideas", "idea_generated", "ideas_generated", "content_ideas")),
    ("digest", "Digests", ("digest_count", "digests", "digest_generated", "digests_generated")),
    ("cache-hit", "Cache hits", ("cache_hit_count", "cache_hits", "cache_hit")),
)


def render_dashboard(metrics: dict[str, Any], *, source_name: str = "metrics.json") -> str:
    """Return a compact static HTML report for an emitted metrics JSON object."""
    counts = _extract_counts(metrics)
    missing = [label for key, label, aliases in METRIC_ROWS if _metric_value(counts, key, aliases) is None]
    rows = "\n".join(_metric_row(counts, key, label, aliases) for key, label, aliases in METRIC_ROWS)
    failures = _render_failures(metrics)
    failure_summary = _render_failure_summary(metrics)
    runs = _render_runs(metrics)
    metrics_state = _render_metrics_state(metrics, missing)
    warnings = _render_missing_metrics(missing)
    schema_version = _text(metrics.get("schema_version") or "unspecified")
    generated_at = _text(metrics.get("generated_at") or metrics.get("generated_on") or "unknown")

    return "\n".join(
        [
            "<!doctype html>",
            "<html lang=\"en\">",
            "<head>",
            "  <meta charset=\"utf-8\">",
            "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
            "  <title>X Bookmark Metrics</title>",
            "</head>",
            "<body>",
            "  <main>",
            "    <header>",
            "      <h1>X Bookmark Metrics</h1>",
            "      <p>Local report generated from " + _escape(source_name) + ".</p>",
            "      <p>Schema: " + _escape(schema_version) + " · Generated: " + _escape(generated_at) + "</p>",
            "    </header>",
            metrics_state,
            warnings,
            "    <section aria-labelledby=\"metric-counts\">",
            "      <h2 id=\"metric-counts\">Metric counts</h2>",
            "      <table>",
            "        <caption>Counts copied directly from the metrics JSON.</caption>",
            "        <thead>",
            "          <tr><th scope=\"col\">Metric</th><th scope=\"col\">Count</th></tr>",
            "        </thead>",
            "        <tbody>",
            rows,
            "        </tbody>",
            "      </table>",
            "    </section>",
            failure_summary,
            failures,
            runs,
            "  </main>",
            "</body>",
            "</html>",
        ]
    )


def load_metrics(path: Path) -> dict[str, Any]:
    """Read a metrics JSON object from disk."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("metrics JSON must be an object")
    return data


def write_dashboard(metrics_path: Path, output_path: Path) -> Path:
    """Read metrics_path and write a static HTML dashboard to output_path."""
    metrics = load_metrics(metrics_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_dashboard(metrics, source_name=metrics_path.name),
        encoding="utf-8",
    )
    return output_path


def render_error_dashboard(*, source_name: str, title: str, message: str, counts_message: str) -> str:
    """Return an HTML report that makes an input/load error visible."""
    return "\n".join(
        [
            "<!doctype html>",
            "<html lang=\"en\">",
            "<head>",
            "  <meta charset=\"utf-8\">",
            "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
            "  <title>X Bookmark Metrics — Error</title>",
            "</head>",
            "<body>",
            "  <main>",
            "    <header>",
            "      <h1>Metrics unavailable</h1>",
            "      <p>Local report could not load " + _escape(source_name) + ".</p>",
            "    </header>",
            "    <section aria-labelledby=\"metrics-error\">",
            "      <h2 id=\"metrics-error\">" + _escape(title) + "</h2>",
            "      <p>" + _escape(_redact_absolute_paths(message)) + "</p>",
            "    </section>",
            "    <section aria-labelledby=\"metric-counts\">",
            "      <h2 id=\"metric-counts\">Metric counts</h2>",
            "      <p>" + _escape(counts_message) + "</p>",
            "    </section>",
            "  </main>",
            "</body>",
            "</html>",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a local X bookmark metrics dashboard HTML file.")
    parser.add_argument("--metrics", required=True, help="Path to emitted bookmark metrics JSON.")
    parser.add_argument("--output", required=True, help="Path to write the local HTML report.")
    args = parser.parse_args(argv)

    try:
        report_path = write_dashboard(Path(args.metrics), Path(args.output))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        metrics_path = Path(args.metrics)
        output_path = Path(args.output)
        title, counts_message = _error_state_labels(exc)
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                render_error_dashboard(
                    source_name=metrics_path.name,
                    title=title,
                    message=_safe_error_message(exc, metrics_path.name),
                    counts_message=counts_message,
                ),
                encoding="utf-8",
            )
        except OSError as write_exc:
            print(f"failed to write metrics error dashboard: {write_exc}", file=sys.stderr)
        print(f"failed to render metrics dashboard: {exc}", file=sys.stderr)
        return 2

    print(f"Metrics dashboard written to: {report_path}")
    return 0


def _error_state_labels(exc: BaseException) -> tuple[str, str]:
    if isinstance(exc, json.JSONDecodeError):
        return "JSON parse error", "No counts were rendered from unreadable data."
    if isinstance(exc, FileNotFoundError):
        return "Input file unavailable", "No counts were rendered from missing data."
    if isinstance(exc, OSError):
        return "Input file unavailable", "No counts were rendered from unavailable data."
    return "Metrics format error", "No counts were rendered from invalid data."


def _safe_error_message(exc: BaseException, source_name: str) -> str:
    if isinstance(exc, FileNotFoundError):
        return f"Metrics file is unavailable: {source_name}"
    return _redact_absolute_paths(str(exc))


def _redact_absolute_paths(message: str) -> str:
    return re.sub(r"(?<![\w.-])/(?:[^/\s'\":<>]+/)+([^/\s'\":<>]+)", r"<path:\1>", message)


def _extract_counts(metrics: dict[str, Any]) -> dict[str, Any]:
    counts = metrics.get("counts")
    if isinstance(counts, dict):
        return counts
    return {}


def _latest_run(metrics: dict[str, Any]) -> dict[str, Any]:
    runs = metrics.get("runs")
    if isinstance(runs, list) and runs:
        latest = runs[-1]
        if isinstance(latest, dict):
            return latest
    return {}


def _metric_row(counts: dict[str, Any], key: str, label: str, aliases: tuple[str, ...]) -> str:
    value = _metric_value(counts, key, aliases)
    rendered_value = "missing" if value is None else _escape(str(value))
    return f"          <tr><th scope=\"row\">{_escape(label)}</th><td>{rendered_value}</td></tr>"


def _metric_value(counts: dict[str, Any], key: str, aliases: tuple[str, ...]) -> int | float | str | None:
    value = counts.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, str)) and str(value).strip() != "":
        return value
    return None


def _render_metrics_state(metrics: dict[str, Any], missing: list[str]) -> str:
    reasons = _metrics_degraded_reasons(metrics, missing)
    if not reasons:
        return ""
    items = "".join(f"<li>{_escape(reason)}</li>" for reason in reasons)
    return (
        "    <section aria-labelledby=\"metrics-degraded\">\n"
        "      <h2 id=\"metrics-degraded\">Metrics data degraded</h2>\n"
        "      <p>Some metrics are absent, null, or incomplete; missing values are shown as missing instead of zero.</p>\n"
        f"      <ul>{items}</ul>\n"
        "    </section>"
    )


def _metrics_degraded_reasons(metrics: dict[str, Any], missing: list[str]) -> list[str]:
    reasons = []
    if "counts" not in metrics:
        reasons.append("counts object is missing")
    else:
        raw_counts = metrics.get("counts")
        if raw_counts is None:
            reasons.append("counts object is null")
        elif not isinstance(raw_counts, dict):
            reasons.append("counts object is not an object")
    if missing:
        reasons.append("required count fields are missing or null: " + ", ".join(missing))
    return reasons


def _render_missing_metrics(missing: list[str]) -> str:
    if not missing:
        return "    <p>All required metrics are present.</p>"
    items = "".join(f"<li>{_escape(label)}</li>" for label in missing)
    return (
        "    <section aria-labelledby=\"missing-metrics\">\n"
        "      <h2 id=\"missing-metrics\">Missing metrics</h2>\n"
        "      <p>The report keeps partial data visible instead of filling missing counts with zero.</p>\n"
        f"      <ul>{items}</ul>\n"
        "    </section>"
    )


def _render_failure_summary(metrics: dict[str, Any]) -> str:
    summary = metrics.get("failure_summary")
    if not isinstance(summary, dict):
        return (
            "    <section aria-labelledby=\"failure-summary\">\n"
            "      <h2 id=\"failure-summary\">Failure summary</h2>\n"
            "      <p>No failure_summary object was included in the metrics JSON.</p>\n"
            "    </section>"
        )
    if not summary:
        return (
            "    <section aria-labelledby=\"failure-summary\">\n"
            "      <h2 id=\"failure-summary\">Failure summary</h2>\n"
            "      <p>failure_summary was present but empty.</p>\n"
            "    </section>"
        )
    rows = []
    expected_keys = ("status", "action_errors", "route_skipped", "warnings", "missing_optional_outputs")
    for key in expected_keys:
        if key not in summary:
            rows.append(_summary_row(key, "missing"))
            continue
        rows.append(_summary_row(key, _summary_value(summary[key])))
    extra_keys = sorted(key for key in summary if key not in expected_keys)
    for key in extra_keys:
        rows.append(_summary_row(key, _summary_value(summary[key])))
    return (
        "    <section aria-labelledby=\"failure-summary\">\n"
        "      <h2 id=\"failure-summary\">Failure summary</h2>\n"
        "      <p>Failure signals are rendered from failure_summary so partial or degraded runs stay visible.</p>\n"
        "      <table>\n"
        "        <caption>Failure summary fields copied from the metrics JSON.</caption>\n"
        "        <thead><tr><th scope=\"col\">Field</th><th scope=\"col\">Value</th></tr></thead>\n"
        "        <tbody>\n"
        + "\n".join(rows)
        + "\n        </tbody>\n"
        "      </table>\n"
        "    </section>"
    )


def _summary_row(key: str, value: str) -> str:
    return f"          <tr><th scope=\"row\">{_escape(key)}</th><td>{_escape(value)}</td></tr>"


def _summary_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return _text(value)


def _render_failures(metrics: dict[str, Any]) -> str:
    failures = _failure_entries(metrics)
    if not failures:
        if _failure_summary_has_indicators(metrics):
            return (
                "    <section aria-labelledby=\"failures\">\n"
                "      <h2 id=\"failures\">Failures</h2>\n"
                "      <p>Failure indicators present in failure_summary even though no standalone failures/errors entries were emitted.</p>\n"
                "    </section>"
            )
        return (
            "    <section aria-labelledby=\"failures\">\n"
            "      <h2 id=\"failures\">Failures</h2>\n"
            "      <p>No failures reported.</p>\n"
            "    </section>"
        )
    items = "".join(f"<li>{_escape(_failure_text(failure))}</li>" for failure in failures)
    return (
        "    <section aria-labelledby=\"failures\">\n"
        "      <h2 id=\"failures\">Failures</h2>\n"
        "      <p>Failures are listed separately so they are not hidden behind aggregate counts.</p>\n"
        f"      <ul>{items}</ul>\n"
        "    </section>"
    )


def _failure_entries(metrics: dict[str, Any]) -> list[Any]:
    failures: list[Any] = []
    for key in ("failures", "errors", "error"):
        value = metrics.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, list):
            failures.extend(value)
            continue
        failures.append(value)
    return failures


def _failure_text(failure: Any) -> str:
    if not isinstance(failure, dict):
        return str(failure)
    parts = []
    for key in ("stage", "message", "count", "source"):
        value = failure.get(key)
        if value not in (None, ""):
            parts.append(f"{key}: {value}")
    if parts:
        return " — ".join(parts)
    return json.dumps(failure, sort_keys=True)


def _failure_summary_has_indicators(metrics: dict[str, Any]) -> bool:
    summary = metrics.get("failure_summary")
    if not isinstance(summary, dict):
        return False
    status = _text(summary.get("status", "")).lower()
    if status and status not in {"ok", "complete", "completed", "success", "succeeded", "healthy", "none"}:
        return True
    for key in ("action_errors", "route_skipped", "warnings", "missing_optional_outputs"):
        if _has_failure_signal(summary.get(key)):
            return True
    return False


def _has_failure_signal(value: Any) -> bool:
    if value in (None, "", 0, False):
        return False
    if isinstance(value, (int, float)):
        return value > 0
    if isinstance(value, str):
        return value.strip() != "" and value.strip() != "0"
    if isinstance(value, dict):
        return any(_has_failure_signal(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_failure_signal(item) for item in value)
    return True


def _render_runs(metrics: dict[str, Any]) -> str:
    runs = metrics.get("runs")
    if not isinstance(runs, list) or not runs:
        return (
            "    <section aria-labelledby=\"run-summary\">\n"
            "      <h2 id=\"run-summary\">Run summary</h2>\n"
            "      <p>No run rows were included in the metrics JSON.</p>\n"
            "    </section>"
        )
    rows = []
    for index, run in enumerate(runs, start=1):
        if not isinstance(run, dict):
            rows.append(
                "          <tr>"
                f"<th scope=\"row\">Run {index}</th>"
                f"<td>{_escape(str(run))}</td>"
                "</tr>"
            )
            continue
        run_id = run.get("id") or run.get("run_id") or f"Run {index}"
        status = run.get("status") or run.get("outcome") or "unknown"
        rows.append(
            "          <tr>"
            f"<th scope=\"row\">{_escape(str(run_id))}</th>"
            f"<td>{_escape(str(status))}</td>"
            "</tr>"
        )
    return (
        "    <section aria-labelledby=\"run-summary\">\n"
        "      <h2 id=\"run-summary\">Run summary</h2>\n"
        "      <table>\n"
        "        <caption>Run-level status remains visible for failed or partial runs.</caption>\n"
        "        <thead><tr><th scope=\"col\">Run</th><th scope=\"col\">Status</th></tr></thead>\n"
        "        <tbody>\n"
        + "\n".join(rows)
        + "\n        </tbody>\n"
        "      </table>\n"
        "    </section>"
    )


def _text(value: Any) -> str:
    return " ".join(str(value).split())


def _escape(value: str) -> str:
    return html.escape(value, quote=True)


if __name__ == "__main__":
    raise SystemExit(main())
