from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from .errors import RuleMatchError
from .rules_loader import Rule, load_packaged_rules, match_rule, render_template
from .util import parse_duration_to_seconds


@dataclass
class RuleResult:
    promql: str
    explain: str
    warnings: List[str]
    matched_rule: str
    confidence: float = 0.7


_DURATION_RE = re.compile(r"^\s*(\d+)\s*([smhdwy])\s*$", re.IGNORECASE)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _extract_range_from_text(text: str, default: str = "5m") -> str:
    """
    Extract 'last 30m', '지난 30분', '최근 1h' etc.
    Supports 30s/5m/1h/7d.
    """
    t = _norm(text)

    # English-ish
    m = re.search(r"(?:last|past)\s+(\d+\s*[smhdwy])", t)
    if m:
        return m.group(1).replace(" ", "")

    # Korean-ish
    m = re.search(r"(?:최근|지난)\s*(\d+)\s*(초|분|시간|일|주|년)", t)
    if m:
        n = m.group(1)
        unit = m.group(2)
        map_ = {"초": "s", "분": "m", "시간": "h", "일": "d", "주": "w", "년": "y"}
        return f"{n}{map_[unit]}"

    # Raw [5m] style
    m = re.search(r"\[(\d+\s*[smhdwy])\]", t)
    if m:
        return m.group(1).replace(" ", "")

    return default


def _extract_quantile(text: str, default: float = 0.95) -> float:
    t = _norm(text)
    # p95, p99
    m = re.search(r"\bp(\d{2})\b", t)
    if m:
        v = int(m.group(1))
        return max(0.0, min(1.0, v / 100.0))
    # 95th percentile
    m = re.search(r"\b(\d{2})th percentile\b", t)
    if m:
        v = int(m.group(1))
        return max(0.0, min(1.0, v / 100.0))
    return default


def _validate_range(range_str: str, warnings: List[str]) -> str:
    try:
        _ = parse_duration_to_seconds(range_str)
        return range_str
    except Exception:
        warnings.append(f"Could not parse range {range_str!r}; falling back to 5m.")
        return "5m"


def convert_to_promql(
    prompt: str,
    *,
    # hard override from CLI (real option)
    range_override: Optional[str] = None,
    quantile_override: Optional[float] = None,
    # config mappings
    cpu_usage_metric: str,
    mem_working_set_metric: str,
    http_requests_total_metric: str,
    http_duration_bucket_metric: str,
    label_namespace: str,
    label_pod: str,
    label_service: str,
) -> RuleResult:
    """
    YAML-rule based NL -> PromQL conversion.
    Deterministic and local-first.
    """
    warnings: List[str] = []
    rules: List[Rule] = load_packaged_rules()

    # Determine range (CLI override wins)
    range_str = range_override or _extract_range_from_text(prompt, default="5m")
    range_str = _validate_range(range_str, warnings)

    quantile = quantile_override if quantile_override is not None else _extract_quantile(prompt, default=0.95)

    r = match_rule(prompt, rules)
    if not r:
        raise RuleMatchError(
            "No rule matched your prompt yet. Try including intent words like "
            "'cpu pod', 'memory pod', 'p95 latency by service', 'error rate by service', "
            "and a range like 'last 30m'."
        )

    metrics: Dict[str, str] = {
        "cpu_usage": cpu_usage_metric,
        "mem_working_set": mem_working_set_metric,
        "http_requests_total": http_requests_total_metric,
        "http_duration_bucket": http_duration_bucket_metric,
    }
    labels: Dict[str, str] = {
        "namespace": label_namespace,
        "pod": label_pod,
        "service": label_service,
    }

    promql = render_template(
        r.promql,
        range_str=range_str,
        quantile=float(quantile),
        metrics=metrics,
        labels=labels,
    )
    explain = render_template(
        r.explain,
        range_str=range_str,
        quantile=float(quantile),
        metrics=metrics,
        labels=labels,
    )

    return RuleResult(
        promql=promql,
        explain=explain,
        warnings=warnings,
        matched_rule=r.id,
        confidence=r.confidence,
    )
