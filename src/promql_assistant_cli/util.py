from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


_DURATION_RE = re.compile(r"^\s*(\d+)\s*([smhdwy])\s*$", re.IGNORECASE)


def parse_duration_to_seconds(s: str) -> int:
    """
    Parse Prometheus-like duration strings: 30s, 5m, 2h, 7d, 1w, 1y
    """
    m = _DURATION_RE.match(s or "")
    if not m:
        raise ValueError(f"Invalid duration: {s!r} (expected like 30s/5m/1h/7d)")
    n = int(m.group(1))
    unit = m.group(2).lower()
    mult = {
        "s": 1,
        "m": 60,
        "h": 60 * 60,
        "d": 24 * 60 * 60,
        "w": 7 * 24 * 60 * 60,
        "y": 365 * 24 * 60 * 60,
    }[unit]
    return n * mult


def env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name)
    return v if v not in (None, "") else default


@dataclass(frozen=True)
class Paths:
    config_path: Path

    @staticmethod
    def default() -> "Paths":
        # XDG-ish default
        base = Path(env("XDG_CONFIG_HOME") or (Path.home() / ".config"))
        return Paths(config_path=base / "promql-assistant" / "config.toml")
