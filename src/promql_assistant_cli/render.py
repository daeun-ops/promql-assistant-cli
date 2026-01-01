from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

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


def print_json(console: Console, obj: Any) -> None:
    console.print_json(json.dumps(obj, ensure_ascii=False))


def print_prometheus_result_table(console: Console, data: Dict[str, Any]) -> None:
    """
    Render Prometheus API JSON for instant vector/scalar/string.
    Keep it simple: show metric labels + value.
    """
    payload = data.get("data") or {}
    result = payload.get("result")
    rtype = payload.get("resultType")

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


# ---------- Range / sparkline ----------

_BLOCKS = "▁▂▃▄▅▆▇█"


def _spark(values: List[float], width: int = 60) -> str:
    if not values:
        return ""
    # downsample to width
    if len(values) > width:
        step = len(values) / float(width)
        picked = []
        i = 0.0
        while int(i) < len(values) and len(picked) < width:
            picked.append(values[int(i)])
            i += step
        values = picked

    vmin = min(values)
    vmax = max(values)
    if vmax == vmin:
        return _BLOCKS[0] * len(values)

    out = []
    for v in values:
        idx = int((v - vmin) / (vmax - vmin) * (len(_BLOCKS) - 1))
        idx = max(0, min(len(_BLOCKS) - 1, idx))
        out.append(_BLOCKS[idx])
    return "".join(out)


def _extract_matrix_series(data: Dict[str, Any]) -> List[Tuple[Dict[str, str], List[Tuple[float, float]]]]:
    """
    Returns [(metric_labels, [(ts,value),...]), ...]
    """
    payload = data.get("data") or {}
    rtype = payload.get("resultType")
    if rtype != "matrix":
        return []

    result = payload.get("result") or []
    if not isinstance(result, list):
        return []

    series = []
    for row in result:
        metric = row.get("metric") or {}
        values = row.get("values") or []
        pts: List[Tuple[float, float]] = []
        for item in values:
            if isinstance(item, list) and len(item) >= 2:
                try:
                    ts = float(item[0])
                    val = float(item[1])
                    pts.append((ts, val))
                except Exception:
                    continue
        series.append((metric, pts))
    return series


def print_range_sparkline(console: Console, data: Dict[str, Any], limit: int = 10) -> None:
    """
    Print compact ASCII graphs for range query results.
    Shows up to `limit` series.
    """
    series = _extract_matrix_series(data)
    if not series:
        console.print("[yellow]No matrix time series returned.[/yellow]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("labels")
    table.add_column("spark")
    table.add_column("min")
    table.add_column("max")
    table.add_column("last")

    for metric, pts in series[:limit]:
        labels = ",".join([f'{k}="{v}"' for k, v in sorted(metric.items())]) or "(no labels)"
        vals = [v for _, v in pts]
        sp = _spark(vals, width=60)
        vmin = min(vals) if vals else 0.0
        vmax = max(vals) if vals else 0.0
        vlast = vals[-1] if vals else 0.0
        table.add_row(labels, sp, f"{vmin:.4g}", f"{vmax:.4g}", f"{vlast:.4g}")

    console.print(table)
