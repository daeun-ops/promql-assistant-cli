from typing import Tuple, Optional
import re

def nl_to_promql(nl: str) -> Tuple[str, str]:
    """
    Convert natural language → PromQL + explanation.
    """
    q = nl.lower().strip()
    rng = _extract_range(q) or "1h"

    if "p95" in q and "latency" in q:
        svc = _extract_service(q) or "checkout_service"
        prom = (
            f"histogram_quantile(0.95, sum(rate(request_duration_seconds_bucket"
            f"{{service=\"{svc}\"}}[{rng}])) by (le))"
        )
        exp = f"p95 latency for {svc}, range={rng}"
        return prom, exp

    if ("error rate" in q) or ("5xx" in q):
        ns = _extract_namespace(q) or "default"
        prom = (
            f"sum(rate(http_requests_total{{status=~\"5..\", namespace=\"{ns}\"}}[{rng}])) "
            f"by (namespace) / sum(rate(http_requests_total{{namespace=\"{ns}\"}}[{rng}])) by (namespace)"
        )
        exp = f"5xx error rate by namespace={ns}, range={rng}"
        return prom, exp

    if "cpu" in q and "throttl" in q:
        ns = _extract_namespace(q) or "default"
        prom = (
            f"sum(rate(container_cpu_cfs_throttled_periods_total{{namespace=\"{ns}\"}}[{rng}])) / "
            f"sum(rate(container_cpu_cfs_periods_total{{namespace=\"{ns}\"}}[{rng}]))"
        )
        exp = f"CPU throttling ratio in {ns}, range={rng}"
        return prom, exp

    prom = f"rate(http_requests_total[{rng}])"
    exp = f"default rule: http request rate over {rng}"
    return prom, exp


def _extract_range(q: str) -> Optional[str]:
    m = re.search(r"(?:last\s+)?(\d+)(m|h|d)", q)
    return f"{m.group(1)}{m.group(2)}" if m else None

def _extract_service(q: str) -> Optional[str]:
    m = re.search(r"(?:service|svc)\s*[:=]?\s*([a-z0-9\-_]+)", q)
    return m.group(1) if m else None

def _extract_namespace(q: str) -> Optional[str]:
    m = re.search(r"(?:namespace|ns)\s*[:=]?\s*([a-z0-9\-_]+)", q)
    return m.group(1) if m else None
