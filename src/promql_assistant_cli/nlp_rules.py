from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .errors import RuleMatchError
from .util import parse_duration_to_seconds


@dataclass
class RuleResult:
    promql: str
    explain: str
    warnings: List[str]
    matched_rule: str
    confidence: float = 0.7


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _extract_range(text: str, default: str = "5m") -> str:
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


def convert_to_promql(
    prompt: str,
    *,
    cpu_usage_metric: str,
    mem_working_set_metric: str,
    http_requests_total_metric: str,
    http_duration_bucket_metric: str,
    label_namespace: str,
    label_pod: str,
    label_service: str,
) -> RuleResult:
    """
    Rule-based NL -> PromQL conversion.
    Keeps it deterministic and local-first.
    """
    text = _norm(prompt)
    rng = _extract_range(prompt, default="5m")
    warnings: List[str] = []

    # basic lint: range must be parseable
    try:
        _ = parse_duration_to_seconds(rng)
    except Exception:
        warnings.append(f"Could not parse range {rng!r}; falling back to 5m.")
        rng = "5m"

    # ---- RULE 1: High CPU pods ----
    if ("cpu" in text or "씨피유" in text) and ("pod" in text or "파드" in text) and (
        "90" in text or "high" in text or "over" in text or "넘" in text
    ):
        promql = (
            f"topk(10, sum(rate({cpu_usage_metric}[{rng}])) by ({label_namespace}, {label_pod}))"
        )
        explain = (
            "Intent: find top CPU pods.\n"
            f"- Using rate({cpu_usage_metric}[{rng}]) as CPU usage rate\n"
            f"- Summed by ({label_namespace}, {label_pod})\n"
            "- topk(10, ...) to show most expensive pods"
        )
        return RuleResult(promql=promql, explain=explain, warnings=warnings, matched_rule="high_cpu_pods", confidence=0.78)

    # ---- RULE 2: Memory high pods ----
    if ("memory" in text or "mem" in text or "메모리" in text) and ("pod" in text or "파드" in text):
        promql = f"topk(10, sum({mem_working_set_metric}) by ({label_namespace}, {label_pod}))"
        explain = (
            "Intent: find top memory pods.\n"
            f"- Using {mem_working_set_metric} as working set bytes\n"
            f"- Summed by ({label_namespace}, {label_pod})\n"
            "- topk(10, ...) to show most expensive pods"
        )
        return RuleResult(promql=promql, explain=explain, warnings=warnings, matched_rule="high_mem_pods", confidence=0.74)

    # ---- RULE 3: Error rate (by service) ----
    if ("error rate" in text or "5xx" in text or "에러율" in text or "오류율" in text) and (
        "service" in text or "서비스" in text
    ):
        # Assumes http_requests_total has 'code' label; configurable via metric mapping.
        promql = (
            f"sum(rate({http_requests_total_metric}{{code=~\"5..\"}}[{rng}])) by ({label_service})"
            f" / "
            f"sum(rate({http_requests_total_metric}[{rng}])) by ({label_service})"
        )
        explain = (
            "Intent: HTTP 5xx error rate by service.\n"
            f"- Numerator: rate({http_requests_total_metric}{{code=~\"5..\"}}[{rng}]) by {label_service}\n"
            f"- Denominator: rate({http_requests_total_metric}[{rng}]) by {label_service}\n"
            "- Division gives error ratio per service"
        )
        return RuleResult(promql=promql, explain=explain, warnings=warnings, matched_rule="error_rate_by_service", confidence=0.80)

    # ---- RULE 4: pXX latency (by service) ----
    if ("latency" in text or "지연" in text) and ("p" in text or "percentile" in text or "퍼센타일" in text):
        q = _extract_quantile(prompt, default=0.95)
        promql = (
            f"histogram_quantile({q}, sum(rate({http_duration_bucket_metric}[{rng}])) by (le, {label_service}))"
        )
        explain = (
            f"Intent: p{int(q*100)} latency by service.\n"
            f"- histogram_quantile({q}, ...)\n"
            f"- Buckets: rate({http_duration_bucket_metric}[{rng}])\n"
            f"- Aggregated by (le, {label_service})"
        )
        return RuleResult(promql=promql, explain=explain, warnings=warnings, matched_rule="pXX_latency_by_service", confidence=0.82)

    # ---- RULE 5: Request rate by service ----
    if ("rps" in text or "request rate" in text or "요청" in text) and ("service" in text or "서비스" in text):
        promql = f"sum(rate({http_requests_total_metric}[{rng}])) by ({label_service})"
        explain = (
            "Intent: request rate by service.\n"
            f"- Using rate({http_requests_total_metric}[{rng}])\n"
            f"- Summed by ({label_service})"
        )
        return RuleResult(promql=promql, explain=explain, warnings=warnings, matched_rule="request_rate_by_service", confidence=0.75)

    raise RuleMatchError(
        "No rule matched your prompt yet. Try including intent words like "
        "'cpu pod', 'memory pod', 'p95 latency by service', 'error rate by service', "
        "and a range like 'last 30m'."
    )
