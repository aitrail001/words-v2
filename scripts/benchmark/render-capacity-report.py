from __future__ import annotations

import csv
import json
import os
import statistics
import sys
from pathlib import Path


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def metric_value(summary: dict, metric: str, field: str) -> float | None:
    metric_obj = summary.get("metrics", {}).get(metric)
    if not metric_obj:
        return None
    values = metric_obj.get("values", {})
    value = values.get(field)
    if value is None:
        return None
    return float(value)


def parse_cpu(value: str) -> float:
    return float(value.strip().rstrip("%"))


def format_float(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}"


def summarize_stats(path: Path) -> dict[str, dict[str, float]]:
    samples: dict[str, list[float]] = {}
    with path.open("r", encoding="utf-8") as handle:
      reader = csv.DictReader(handle)
      for row in reader:
        container = row["container"]
        samples.setdefault(container, []).append(parse_cpu(row["cpu_perc"]))
    summary: dict[str, dict[str, float]] = {}
    for container, values in samples.items():
      summary[container] = {
        "avg_cpu": round(statistics.mean(values), 2),
        "max_cpu": round(max(values), 2),
      }
    return summary


def load_sql_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def select_container_summary(
    stats_summary: dict[str, dict[str, float]],
    *,
    preferred_names: list[str],
    suffixes: list[str],
) -> dict[str, float]:
    for name in preferred_names:
        if name in stats_summary:
            return stats_summary[name]
    for suffix in suffixes:
        for name, values in stats_summary.items():
            if name.endswith(suffix):
                return values
    return {}


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: render-capacity-report.py <results-dir> <report-path> <host-budget>", file=sys.stderr)
        return 1

    results_dir = Path(sys.argv[1])
    report_path = Path(sys.argv[2])
    host_budget = sys.argv[3]
    report_title = os.environ.get("CAPACITY_REPORT_TITLE", "Single-Host Capacity Report")
    workload_target = os.environ.get(
        "CAPACITY_WORKLOAD_TARGET",
        "p95 < 500ms and error rate < 5% on the mixed API workload",
    )

    stage_dirs = sorted(
        (path for path in results_dir.iterdir() if path.is_dir()),
        key=lambda path: int(path.name.split("-")[-1]),
    )
    rows = []
    safe_vus = None
    top_total_sql = load_sql_rows(results_dir / "pg-stat-statements-top-total.csv")
    top_mean_sql = load_sql_rows(results_dir / "pg-stat-statements-top-mean.csv")

    for stage_dir in stage_dirs:
        summary = load_json(stage_dir / "k6-summary.json")
        stats = summarize_stats(stage_dir / "docker-stats.csv")
        vus = int(stage_dir.name.split("-")[-1])
        p95 = metric_value(summary, "http_req_duration", "p(95)")
        p99 = metric_value(summary, "http_req_duration", "p(99)")
        error_rate = metric_value(summary, "http_req_failed", "rate")
        rps = metric_value(summary, "http_reqs", "rate")
        backend_cpu = select_container_summary(
            stats,
            preferred_names=["words-prod-backend", "words-srs-review-backend"],
            suffixes=["-backend"],
        )
        postgres_cpu = select_container_summary(
            stats,
            preferred_names=["words-prod-postgres", "words-srs-review-postgres"],
            suffixes=["-postgres"],
        )
        rows.append(
            {
                "vus": vus,
                "p95": p95,
                "p99": p99,
                "error_rate": error_rate,
                "rps": rps,
                "backend_cpu": backend_cpu.get("max_cpu", 0.0),
                "postgres_cpu": postgres_cpu.get("max_cpu", 0.0),
            }
        )
        if (
            p95 is not None
            and error_rate is not None
            and p95 <= 500
            and error_rate < 0.05
        ):
            safe_vus = vus

    lines = [
        f"# {report_title}",
        "",
        f"**Host budget under test:** {host_budget}",
        f"**Results directory:** `{results_dir}`",
        "",
        "## Summary",
        "",
        f"- Highest tested stage meeting the initial p95/error bar: `{safe_vus if safe_vus is not None else 'none'}` VUs",
        f"- User-experience target used for the first pass: `{workload_target}`",
        "",
        "## Stage Results",
        "",
        "| VUs | RPS | p95 ms | p99 ms | Error rate | Backend max CPU % | Postgres max CPU % |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]

    for row in rows:
        lines.append(
            f"| {row['vus']} | {format_float(row['rps'])} | {format_float(row['p95'])} | {format_float(row['p99'])} | {format_float(row['error_rate'], 4)} | {format_float(row['backend_cpu'])} | {format_float(row['postgres_cpu'])} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This report is valid only for the production-like single-host Docker stack used in this run.",
            "- It is not a universal production concurrency claim.",
            "- If a later stage breaches the target, the prior passing stage is the initial safe tested envelope.",
        ]
    )

    if top_total_sql:
        lines.extend(
            [
                "",
                "## Top SQL by Total Execution Time",
                "",
                "| Calls | Total ms | Mean ms | Rows | Query |",
                "|---:|---:|---:|---:|---|",
            ]
        )
        for row in top_total_sql[:10]:
            lines.append(
                f"| {row['calls']} | {row['total_exec_time_ms']} | {row['mean_exec_time_ms']} | {row['rows']} | `{row['query'][:180]}` |"
            )

    if top_mean_sql:
        lines.extend(
            [
                "",
                "## Top SQL by Mean Execution Time",
                "",
                "| Calls | Total ms | Mean ms | Rows | Query |",
                "|---:|---:|---:|---:|---|",
            ]
        )
        for row in top_mean_sql[:10]:
            lines.append(
                f"| {row['calls']} | {row['total_exec_time_ms']} | {row['mean_exec_time_ms']} | {row['rows']} | `{row['query'][:180]}` |"
            )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
