from promql_assistant_cli.rules import nl_to_promql

def test_latency_rule():
    prom, exp = nl_to_promql("p95 latency of checkout_service last 1h")
    assert "histogram_quantile" in prom
    assert "checkout_service" in prom
    assert "1h" in prom
    assert "p95 latency" in exp
