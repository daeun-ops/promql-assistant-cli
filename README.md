# promql-assistant-cli

Describe what you want → get **valid PromQL** instantly.  
100% local-first, scriptable, and CI-friendly.

---

## start gogogogogi
```bash
# Install (local dev)
pipx install -e .

# Example runs
promql-assistant "p95 latency of checkout_service last 1h" --dry-run
promql-assistant "error rate by namespace last 30m" --server http://localhost:9090 --range 30m
```


###  Features
	•	 Natural language → PromQL conversion (rule-based MVP)
	•	 --explain to show mapping logic
	•	 --dry-run for PromQL-only output
	•	 Optional Prometheus query via --server
	•	 Output: table (default) / json


  ### roadMap
  Version
Goal
0.1
MVP: NL→PromQL, –dry-run, –explain
0.2
promtool validation, richer rules
0.3
optional RAG index, Brew/Scoop packaging
0.4
benchmark & plugin architecture







