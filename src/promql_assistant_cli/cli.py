import json
import typer
import requests
from typing import Optional
from rich.console import Console
from rich.table import Table
from .rules import nl_to_promql
from . import __version__

app = typer.Typer(add_completion=False)
console = Console()

@app.command()
def main(
    query: str = typer.Argument(..., help="Natural language query"),
    server: Optional[str] = typer.Option(None, "--server", "-s", help="Prometheus base URL"),
    time_range: Optional[str] = typer.Option(None, "--range", "-r", help="Override time window"),
    explain: bool = typer.Option(False, "--explain", help="Show mapping explanation"),
    output: str = typer.Option("table", "--format", "-f", help="table|json"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Only print PromQL"),
    version: bool = typer.Option(False, "--version", help="Show version"),
):
    if version:
        console.print(f"promql-assistant-cli {__version__}")
        raise typer.Exit()

    promql, exp = nl_to_promql(query if not time_range else f"{query} {time_range}")

    if dry_run:
        if explain:
            console.print(f"[bold]Explanation:[/bold] {exp}")
        console.print(promql)
        raise typer.Exit()

    if not server:
        console.print("[red]No --server provided. Use --dry-run for preview.[/red]")
        raise typer.Exit(2)

    url = f"{server.rstrip('/')}/api/v1/query"
    res = requests.get(url, params={"query": promql}, timeout=10)
    res.raise_for_status()
    data = res.json()

    if output == "json":
        console.print_json(json.dumps(data))
        return

    table = Table(title="Prometheus Query Result")
    table.add_column("metric")
    table.add_column("value")
    for item in data.get("data", {}).get("result", []):
        table.add_row(json.dumps(item.get("metric", {})), json.dumps(item.get("value")))
    if explain:
        console.print(f"[bold]Explanation:[/bold] {exp}")
    console.print(f"[bold]PromQL:[/bold] {promql}")
    console.print(table)
