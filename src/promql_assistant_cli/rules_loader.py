from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import resources
from typing import Any, Dict, List, Optional

from .errors import ConfigError

try:
    import yaml  # PyYAML
except Exception:  # pragma: no cover
    yaml = None  # type: ignore


@dataclass(frozen=True)
class Rule:
    id: str
    keywords_all: List[str]
    keywords_any: List[str]
    promql: str
    explain: str
    confidence: float = 0.7


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _ensure_yaml() -> None:
    if yaml is None:
        raise ConfigError("PyYAML is required for rules.yaml. Install PyYAML>=6.0.1.")


def load_packaged_rules() -> List[Rule]:
    """
    Load rules from src/promql_assistant_cli/rules.yaml (packaged resource).
    """
    _ensure_yaml()

    try:
        data_bytes = resources.files("promql_assistant_cli").joinpath("rules.yaml").read_bytes()
    except Exception as e:
        raise ConfigError("Could not read packaged rules.yaml") from e

    try:
        doc = yaml.safe_load(data_bytes) or {}
    except Exception as e:
        raise ConfigError("Invalid YAML in rules.yaml") from e

    rules_raw = doc.get("rules", [])
    if not isinstance(rules_raw, list):
        raise ConfigError("rules.yaml: 'rules' must be a list")

    out: List[Rule] = []
    for r in rules_raw:
        if not isinstance(r, dict):
            continue
        out.append(
            Rule(
                id=str(r.get("id", "")).strip(),
                keywords_all=[str(x).lower() for x in (r.get("keywords_all") or [])],
                keywords_any=[str(x).lower() for x in (r.get("keywords_any") or [])],
                promql=str(r.get("promql", "")).strip(),
                explain=str(r.get("explain", "")).strip(),
                confidence=float(r.get("confidence", 0.7)),
            )
        )

    out = [r for r in out if r.id and r.promql]
    if not out:
        raise ConfigError("rules.yaml contains no valid rules")
    return out


def match_rule(prompt: str, rules: List[Rule]) -> Optional[Rule]:
    t = _norm(prompt)
    for r in rules:
        all_ok = all(k in t for k in r.keywords_all) if r.keywords_all else True
        any_ok = any(k in t for k in r.keywords_any) if r.keywords_any else True
        if all_ok and any_ok:
            return r
    return None


def render_template(
    template: str,
    *,
    range_str: str,
    quantile: float,
    metrics: Dict[str, str],
    labels: Dict[str, str],
) -> str:
    # normalize multi-line templates
    s = template.strip()

    # placeholders
    s = s.replace("{range}", range_str)
    s = s.replace("{quantile}", str(quantile))

    for k, v in metrics.items():
        s = s.replace("{metrics." + k + "}", v)
    for k, v in labels.items():
        s = s.replace("{labels." + k + "}", v)

    # Compact YAML block scalars often include newlines; keep them, but strip trailing spaces
    lines = [ln.rstrip() for ln in s.splitlines()]
    return "\n".join(lines).strip()
