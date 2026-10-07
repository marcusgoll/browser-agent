#!/usr/bin/env python3
"""Render a local-first proof-of-value metrics HTML report.

The report is intentionally static HTML generated from the emitted metrics JSON.
It does not compute replacement counts; missing or invalid fields stay visible in
report output so operators can trust that every shown count came from the JSON
artifact.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_METRICS_DIRS = (Path("output/opportunities"), Path("/app/output/opportunities"))
REQUIRED_COUNTS: tuple[tuple[str, str], ...] = (
    ("processed", "Processed"),
    ("deduped", "Deduped"),
    ("routed", "Routed"),
    ("note", "Notes"),
    ("idea", "Ideas"),
    ("digest", "Digest"),
    ("cache-hit", "Cache hits"),
)


@dataclass(frozen=True)
class ReportResult:
    """Result of writing a local metrics report."""

    path: Path
    ok: bool
    message: str


def render_report(metrics: dict[str, Any], *, source_name: str = "metrics JSON") -> str:
    """Return static HTML that displays proof-of-value counts from metrics."""
    counts = metrics.get("counts")
    count_values = counts if isinstance(counts, dict) else {}
    problems: list[str] = []
    if not isinstance(counts, dict):
        problems.append("Missing counts object")

    count_rows = []
    for key, label in REQUIRED_COUNTS:
        value = count_values.get(key)
        rendered_value = _render_count_value(value)
        if key not in count_values:
            problems.append(f"Missing expected metric: {label}")
        elif rendered_value == "missing":
            problems.append(f"Missing expected metric: {label}")
        elif rendered_value == "invalid":
            problems.append(f"Invalid expected metric: {label}")
        count_rows.append(f"        <div><dt>{_escape(label)}</dt><dd>{rendered_value}</dd></div>")

    status_heading = "Report needs attention" if problems else "Report healthy"
    status_body = _render_problems(problems)
    schema_version = _escape(str(metrics.get("schema_version") or "unspecified"))
    generated_at = _escape(str(metrics.get("generated_at") or "unknown"))
    source = _escape(str(metrics.get("source") or "unknown"))

    return _page(
        title="Proof-of-Value Metrics",
        source_name=source_name,
        body="\n".join(
            [
                "    <section aria-labelledby=\"report-status\">",
                f"      <h2 id=\"report-status\">{status_heading}</h2>",
                status_body,
                "    </section>",
                "    <section aria-labelledby=\"metric-counts\">",
                "      <h2 id=\"metric-counts\">Metric counts</h2>",
                "      <p>Counts are displayed directly from the emitted metrics JSON.</p>",
                "      <dl>",
                "\n".join(count_rows),
                "      </dl>",
                "    </section>",
                "    <section aria-labelledby=\"metric-source\">",
                "      <h2 id=\"metric-source\">Source details</h2>",
                "      <dl>",
                f"        <div><dt>Schema</dt><dd>{schema_version}</dd></div>",
                f"        <div><dt>Generated</dt><dd>{generated_at}</dd></div>",
                f"        <div><dt>Source</dt><dd>{source}</dd></div>",
                "      </dl>",
                "    </section>",
            ]
        ),
    )


def render_failure_report(*, heading: str, message: str, source_name: str) -> str:
    """Return static HTML for missing or unreadable metrics JSON."""
    return _page(
        title="Proof-of-Value Metrics",
        source_name=source_name,
        body="\n".join(
            [
                "    <section aria-labelledby=\"report-status\">",
                "      <h2 id=\"report-status\">Report needs attention</h2>",
                f"      <p>{_escape(message)}</p>",
                "    </section>",
                "    <section aria-labelledby=\"missing-metrics\">",
                f"      <h2 id=\"missing-metrics\">{_escape(heading)}</h2>",
                "      <p>No counts were substituted or guessed. Fix the metrics JSON and regenerate this report.</p>",
                "    </section>",
            ]
        ),
    )


def load_metrics(path: Path) -> dict[str, Any]:
    """Read a metrics JSON object from disk."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("metrics JSON must be an object")
    return data


def write_report(metrics_path: Path, output_path: Path) -> ReportResult:
    """Read metrics_path and write a local static HTML report to output_path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    source_name = metrics_path.name
    try:
        html_report = render_report(load_metrics(metrics_path), source_name=source_name)
    except FileNotFoundError:
        message = f"missing metrics JSON: {metrics_path}"
        html_report = render_failure_report(
            heading="Missing metrics JSON",
            message=message,
            source_name=source_name,
        )
        output_path.write_text(html_report, encoding="utf-8")
        return ReportResult(output_path, False, message)
    except json.JSONDecodeError as exc:
        message = f"invalid metrics JSON: {metrics_path} ({exc.msg})"
        html_report = render_failure_report(
            heading="Invalid metrics JSON",
            message=message,
            source_name=source_name,
        )
        output_path.write_text(html_report, encoding="utf-8")
        return ReportResult(output_path, False, message)
    except ValueError as exc:
        message = f"invalid metrics JSON: {metrics_path} ({exc})"
        html_report = render_failure_report(
            heading="Invalid metrics JSON",
            message=message,
            source_name=source_name,
        )
        output_path.write_text(html_report, encoding="utf-8")
        return ReportResult(output_path, False, message)

    output_path.write_text(html_report, encoding="utf-8")
    return ReportResult(output_path, True, f"metrics report written to: {output_path}")


def latest_metrics_path() -> Path | None:
    """Return the newest local proof-value metrics JSON path, if present."""
    candidates: list[Path] = []
    for directory in DEFAULT_METRICS_DIRS:
        candidates.extend(directory.glob("proof_value_metrics_*.json"))
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a local proof-of-value metrics HTML report.")
    parser.add_argument(
        "--metrics",
        help="Path to proof_value_metrics_<YYYY-MM-DD>.json. Defaults to the newest output/opportunities file.",
    )
    parser.add_argument("--output", help="Path to write the local HTML report.")
    args = parser.parse_args(argv)

    metrics_path = Path(args.metrics) if args.metrics else latest_metrics_path()
    if metrics_path is None:
        output_path = Path(args.output) if args.output else Path("output/opportunities/proof_value_metrics_report.html")
        result = _write_missing_default_report(output_path)
        print(result.message, file=sys.stderr)
        return 2

    output_path = Path(args.output) if args.output else metrics_path.with_suffix(".html")
    result = write_report(metrics_path, output_path)
    print(result.message, file=sys.stderr if not result.ok else sys.stdout)
    return 0 if result.ok else 2


def _write_missing_default_report(output_path: Path) -> ReportResult:
    message = "missing metrics JSON: no proof_value_metrics_*.json file found in output/opportunities"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_failure_report(
            heading="Missing metrics JSON",
            message=message,
            source_name="output/opportunities/proof_value_metrics_*.json",
        ),
        encoding="utf-8",
    )
    return ReportResult(output_path, False, message)


def _page(*, title: str, source_name: str, body: str) -> str:
    return "\n".join(
        [
            "<!doctype html>",
            "<html lang=\"en\">",
            "<head>",
            "  <meta charset=\"utf-8\">",
            "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
            f"  <title>{_escape(title)}</title>",
            "</head>",
            "<body>",
            "  <main>",
            "    <header>",
            f"      <h1>{_escape(title)}</h1>",
            f"      <p>Local report generated from {_escape(source_name)}.</p>",
            "    </header>",
            body,
            "  </main>",
            "</body>",
            "</html>",
        ]
    )


def _render_problems(problems: list[str]) -> str:
    if not problems:
        return "      <p>All expected metrics are present.</p>"
    items = "".join(f"<li>{_escape(problem)}</li>" for problem in problems)
    return (
        "      <p>Missing expected metrics are shown as missing; invalid values are shown as invalid.</p>\n"
        "      <h3>Missing expected metrics</h3>\n"
        f"      <ul>{items}</ul>"
    )


def _render_count_value(value: Any) -> str:
    if value is None:
        return "missing"
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return "invalid"
    return _escape(str(value))


def _escape(value: str) -> str:
    return html.escape(value, quote=True)


if __name__ == "__main__":
    raise SystemExit(main())
