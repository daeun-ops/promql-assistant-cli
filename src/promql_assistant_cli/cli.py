from __future__ import annotations

import sys
import time
from typing import Optional

import typer
from rich.console import Console

from .config import Settings
from .errors import PrometheusAPIError, RuleMatchError, ValidationError
from .nlp_rules import convert_to_promql
from .prometheus import PrometheusClient
from .render import (
    print_explain,
    print_json,
    print_prometheus_result_table,
    print_promql,
    print_range_sparkline,
)
from .util import Paths

app = typer.Typer(
    add_completion=True,
    help="Describe what you want → get valid PromQL instantly (local-first, deterministic rules).",
)

console = Console(stderr=False)
err_console = Console(stderr=True)


def _build_client(s: Settings, server_override: Optional[str]) -> Optional[PrometheusClient]:
    server = server_override or s.server
    if not server:
        return None

    basic = None
    if s.auth_basic_user and s.auth_basic_pass:
        basic = (s.auth_basic_user, s.auth_basic_pass)

    return PrometheusClient(
        base_url=server,
        timeout_seconds=s.timeout_seconds,
        bearer_token=s.auth_bearer_token,
        basic_auth=basic,
    )


@app.command("ask")
def ask(
    prompt: str = typer.Argument(..., help="Natural language prompt, e.g. 'p95 latency by service last 1h'"),
    server: Optional[str] = typer.Option(None, "--server", help="Prometheus base URL, e.g. http://localhost:9090"),
    range: Optional[str] = typer.Option(None, "--range", help="Force range window, e.g. 30m (overrides prompt parsing)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print PromQL only (no Prometheus API call)"),
    explain: bool = typer.Option(False, "--explain", help="Show mapping logic"),
    validate: bool = typer.Option(False, "--validate", help="Validate PromQL via Prometheus API (requires --server or config)"),
    format: str = typer.Option("table", "--format", help="Output format: table|json|promql|spark"),
    # Range query flags
    start: Optional[int] = typer.Option(None, "--start", help="Range query start (unix seconds). If set, uses query_range."),
    end: Optional[int] = typer.Option(None, "--end", help="Range query end (unix seconds). Default: now"),
    step: str = typer.Option("30s", "--step", help="Range query step, e.g. 15s/30s/1m"),
    spark_limit: int = typer.Option(10, "--spark-limit", help="Max series to show in spark output"),
):
    """
    Main entry: NL -> PromQL. Optionally validate / query Prometheus.
    """
    s = Settings.load()
    client = _build_client(s, server)

    try:
        rr = convert_to_promql(
            prompt,
            range_override=range,
            cpu_usage_metric=s.metrics.cpu_usage,
            mem_working_set_metric=s.metrics.mem_working_set,
            http_requests_total_metric=s.metrics.http_requests_total,
            http_duration_bucket_metric=s.metrics.http_duration_bucket,
            label_namespace=s.label_namespace,
            label_pod=s.label_pod,
            label_service=s.label_service,
        )
    except RuleMatchError as e:
        err_console.print(f"[red]no_match:[/red] {e}")
        raise typer.Exit(code=1)

    # format=promql implies output only
    if format == "promql":
        print_promql(console, rr.promql)
        if explain:
            print_explain(console, rr.explain, rr.warnings)
        raise typer.Exit(code=0)

    # dry run (no server needed)
    if dry_run:
        if format == "json":
            print_json(
                console,
                {
                    "promql": rr.promql,
                    "matched_rule": rr.matched_rule,
                    "confidence": rr.confidence,
                    "explain": rr.explain if explain else None,
                    "warnings": rr.warnings,
                },
            )
        else:
            print_promql(console, rr.promql)
            if explain:
                print_explain(console, rr.explain, rr.warnings)
        raise typer.Exit(code=0)

    # validate
    if validate:
        if not client:
            err_console.print("[red]validate requires a Prometheus server.[/red] Use --server or set config.")
            raise typer.Exit(code=2)
        try:
            client.validate_promql(rr.promql)
        except (PrometheusAPIError, ValidationError) as e:
            err_console.print(f"[red]invalid:[/red] {e}")
            raise typer.Exit(code=2)

    # If no server, fallback to printing only
    if not client:
        if format == "json":
            print_json(
                console,
                {
                    "promql": rr.promql,
                    "matched_rule": rr.matched_rule,
                    "confidence": rr.confidence,
                    "explain": rr.explain if explain else None,
                    "warnings": rr.warnings,
                },
            )
        else:
            print_promql(console, rr.promql)
            if explain:
                print_explain(console, rr.explain, rr.warnings)
        raise typer.Exit(code=0)

    # Optional: metric mismatch warnings when explain is on
    if explain:
        mismatch = client.warn_if_metrics_missing(
            [s.metrics.cpu_usage, s.metrics.mem_working_set, s.metrics.http_requests_total, s.metrics.http_duration_bucket]
        )
        for w in mismatch:
            rr.warnings.append(w)

    # Choose instant vs range query
    use_range = start is not None
    try:
        if use_range:
            start_ts = float(start)
            end_ts = float(end) if end is not None else time.time()
            data = client.query_range(rr.promql, start=start_ts, end=end_ts, step=step)
        else:
            data = client.query_instant(rr.promql)
    except PrometheusAPIError as e:
        err_console.print(f"[red]prometheus_error:[/red] {e}")
        err_console.print("[yellow]Tip:[/yellow] use --dry-run or --validate first.")
        raise typer.Exit(code=3)

    if format == "json":
        out = {"promql": rr.promql, "matched_rule": rr.matched_rule, "confidence": rr.confidence, "result": data}
        if explain:
            out["explain"] = rr.explain
            out["warnings"] = rr.warnings
        print_json(console, out)
        return

    # default/table output
    print_promql(console, rr.promql)
    if explain:
        print_explain(console, rr.explain, rr.warnings)

    # spark output (range query recommended)
    if format == "spark":
        print_range_sparkline(console, data, limit=spark_limit)
        return

    # table output
    print_prometheus_result_table(console, data)


@app.command("suggest")
def suggest(
    what: str = typer.Argument(..., help="metrics|labels|label-values"),
    server: Optional[str] = typer.Option(None, "--server", help="Prometheus base URL"),
    label: Optional[str] = typer.Option(None, "--label", help="Label name for label-values"),
    prefix: Optional[str] = typer.Option(None, "--prefix", help="Filter by prefix (client-side)"),
    format: str = typer.Option("table", "--format", help="Output format: table|json"),
):
    """
    Discovery helpers for on-call:
      - suggest metrics
      - suggest labels
      - suggest label-values --label namespace
    """
    s = Settings.load()
    client = _build_client(s, server)
    if not client:
        err_console.print("[red]suggest requires a Prometheus server.[/red] Use --server or set config.")
        raise typer.Exit(code=2)

    try:
        if what == "metrics":
            items = client.metric_names()
        elif what == "labels":
            items = client.label_names()
        elif what in ("label-values", "label_values"):
            if not label:
                err_console.print("[red]--label is required for label-values[/red]")
                raise typer.Exit(code=2)
            items = client.label_values(label)
        else:
            err_console.print("[red]what must be one of: metrics|labels|label-values[/red]")
            raise typer.Exit(code=2)
    except PrometheusAPIError as e:
        err_console.print(f"[red]prometheus_error:[/red] {e}")
        raise typer.Exit(code=3)

    if prefix:
        items = [x for x in items if x.startswith(prefix)]

    if format == "json":
        print_json(console, {"what": what, "items": items})
    else:
        from rich.table import Table

        t = Table(show_header=True, header_style="bold")
        t.add_column(what)
        for x in items[:2000]:
            t.add_row(x)
        console.print(t)


@app.command("config-path")
def config_path():
    """Print where the config file should live."""
    console.print(str(Paths.default().config_path))


@app.command("version")
def version():
    from . import __version__

    console.print(__version__)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context, prompt: Optional[str] = typer.Argument(None)):
    """
    If user runs: promql-assistant "..."
    treat it as: promql-assistant ask "..."
    """
    if ctx.invoked_subcommand is not None:
        return
    if not prompt:
        err_console.print('Usage: promql-assistant ask "..."  (or just promql-assistant "...")')
        raise typer.Exit(code=1)
    # Re-dispatch
    sys.argv = [sys.argv[0], "ask", prompt]
    app()
