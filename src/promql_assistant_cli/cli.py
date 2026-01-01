from __future__ import annotations

import sys
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
    range: Optional[str] = typer.Option(None, "--range", help="Override time range, e.g. 30m (optional)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print PromQL only (no Prometheus API call)"),
    explain: bool = typer.Option(False, "--explain", help="Show mapping logic"),
    validate: bool = typer.Option(False, "--validate", help="Validate PromQL via Prometheus API (requires --server or config)"),
    format: str = typer.Option("table", "--format", help="Output format: table|json|promql"),
):
    """
    Main entry: NL -> PromQL. Optionally validate / query Prometheus.
    """
    s = Settings.load()
    client = _build_client(s, server)

    # If user provided --range, append into prompt for rule extraction
    effective_prompt = prompt
    if range:
        effective_prompt = f"{prompt} last {range}"

    try:
        rr = convert_to_promql(
            effective_prompt,
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

    # format=promql implies dry output
    if format == "promql":
        print_promql(console, rr.promql)
        if explain:
            print_explain(console, rr.explain, rr.warnings)
        raise typer.Exit(code=0)

    if dry_run:
        if format == "json":
            print_json(console, {"promql": rr.promql, "explain": rr.explain if explain else None, "warnings": rr.warnings})
        else:
            print_promql(console, rr.promql)
            if explain:
                print_explain(console, rr.explain, rr.warnings)
        raise typer.Exit(code=0)

    if validate:
        if not client:
            err_console.print("[red]validate requires a Prometheus server.[/red] Use --server or set config.")
            raise typer.Exit(code=2)
        try:
            client.validate_promql(rr.promql)
        except (PrometheusAPIError, ValidationError) as e:
            err_console.print(f"[red]invalid:[/red] {e}")
            raise typer.Exit(code=2)

    # If no server, we can only output PromQL
    if not client:
        if format == "json":
            print_json(console, {"promql": rr.promql, "explain": rr.explain if explain else None, "warnings": rr.warnings})
        else:
            print_promql(console, rr.promql)
            if explain:
                print_explain(console, rr.explain, rr.warnings)
        raise typer.Exit(code=0)

    # Query Prometheus (instant query)
    try:
        data = client.query_instant(rr.promql)
    except PrometheusAPIError as e:
        err_console.print(f"[red]prometheus_error:[/red] {e}")
        err_console.print("[yellow]Tip:[/yellow] use --dry-run or --validate first.")
        raise typer.Exit(code=3)

    if format == "json":
        out = {"promql": rr.promql, "result": data}
        if explain:
            out["explain"] = rr.explain
            out["warnings"] = rr.warnings
        print_json(console, out)
    else:
        print_promql(console, rr.promql)
        if explain:
            print_explain(console, rr.explain, rr.warnings)
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
        # simple list table
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
        err_console.print("Usage: promql-assistant ask \"...\"  (or just promql-assistant \"...\")")
        raise typer.Exit(code=1)
    # Re-dispatch
    sys.argv = [sys.argv[0], "ask", prompt]
    app()
