import pytest

from promql_assistant_cli.errors import RuleMatchError
from promql_assistant_cli.nlp_rules import convert_to_promql


def test_p95_latency_rule():
    rr = convert_to_promql(
        "p95 latency by service last 1h",
        cpu_usage_metric="cpu",
        mem_working_set_metric="mem",
        http_requests_total_metric="req_total",
        http_duration_bucket_metric="dur_bucket",
        label_namespace="namespace",
        label_pod="pod",
        label_service="service",
    )
    assert "histogram_quantile" in rr.promql
    assert "[1h]" in rr.promql


def test_no_match():
    with pytest.raises(RuleMatchError):
        convert_to_promql(
            "tell me something unrelated",
            cpu_usage_metric="cpu",
            mem_working_set_metric="mem",
            http_requests_total_metric="req_total",
            http_duration_bucket_metric="dur_bucket",
            label_namespace="namespace",
            label_pod="pod",
            label_service="service",
        )
