from __future__ import annotations

import json
from typing import Any, Dict, Optional

from rich.console import Console
from rich.table import Table


def print_promql(console: Console, promql: str) -> None:
    console.print(promql)


def print_explain(console: Console, explain: str, warnings: Optional[list[str]] = None) -> None:
    if warnings:
        for w in warnings:
            console.print(f"[yellow]warning:[/yellow] {w}")
    console.print("[bold]explain[/bold]")
    console.print(explain)


def print_prometheus_result_table(console: Console, data: Dict[str, Any]) -> None:
    """
    Render Prometheus API JSON for instant vector/scalar/string.
    Keep it simple: show metric labels + value.
    """
    result = (data.get("data") or {}).get("result")
    rtype = (data.get("data") or {}).get("resultType")

    if rtype in ("scalar", "string"):
        console.print(result)
        return

    if not isinstance(result, list):
        console.print(result)
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("labels")
    table.add_column("value")

    for row in result:
        metric = row.get("metric", {})
        value = row.get("value", [])
        labels = ",".join([f'{k}="{v}"' for k, v in sorted(metric.items())])
        val = value[1] if isinstance(value, list) and len(value) >= 2 else str(value)
        table.add_row(labels, str(val))

    console.print(table)


def print_json(console: Console, obj: Any) -> None:
    console.print_json(json.dumps(obj, ensure_ascii=False))
