from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from .errors import ConfigError
from .util import Paths, env

try:
    import tomllib  # py311+
except Exception:  # pragma: no cover
    tomllib = None  # type: ignore


def _load_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    if tomllib is None:
        # Fallback for py310 users: require tomli only if config file is used.
        try:
            import tomli  # type: ignore
        except Exception as e:  # pragma: no cover
            raise ConfigError(
                "Config file detected but tomllib not available. "
                "Install tomli (pip install tomli) or use Python 3.11+."
            ) from e
        with path.open("rb") as f:
            return tomli.load(f)
    with path.open("rb") as f:
        return tomllib.load(f)


@dataclass
class MetricCatalog:
    """
    Metric name mapping (company/cluster-specific).
    Override via config.toml:
      [metrics]
      cpu_usage = "container_cpu_usage_seconds_total"
      mem_working_set = "container_memory_working_set_bytes"
      http_requests_total = "http_requests_total"
      http_duration_bucket = "http_request_duration_seconds_bucket"
    """

    cpu_usage: str = "container_cpu_usage_seconds_total"
    mem_working_set: str = "container_memory_working_set_bytes"
    http_requests_total: str = "http_requests_total"
    http_duration_bucket: str = "http_request_duration_seconds_bucket"


@dataclass
class Settings:
    server: Optional[str] = None
    timeout_seconds: float = 10.0
    auth_bearer_token: Optional[str] = None
    auth_basic_user: Optional[str] = None
    auth_basic_pass: Optional[str] = None

    # default labels used in rules
    label_namespace: str = "namespace"
    label_pod: str = "pod"
    label_job: str = "job"
    label_service: str = "service"

    metrics: MetricCatalog = field(default_factory=MetricCatalog)

    @staticmethod
    def load(path: Optional[Path] = None) -> "Settings":
        paths = Paths.default()
        cfg_path = path or paths.config_path

        # env overrides (highest priority)
        env_server = env("PROMQL_ASSISTANT_SERVER")
        env_timeout = env("PROMQL_ASSISTANT_TIMEOUT")
        env_bearer = env("PROMQL_ASSISTANT_BEARER_TOKEN")
        env_basic_user = env("PROMQL_ASSISTANT_BASIC_USER")
        env_basic_pass = env("PROMQL_ASSISTANT_BASIC_PASS")

        data = _load_toml(cfg_path)

        s = Settings()

        # file config
        try:
            if "server" in data:
                s.server = str(data["server"]) if data["server"] else None
            if "timeout_seconds" in data:
                s.timeout_seconds = float(data["timeout_seconds"])
            if "labels" in data and isinstance(data["labels"], dict):
                labels: Dict[str, str] = data["labels"]
                s.label_namespace = labels.get("namespace", s.label_namespace)
                s.label_pod = labels.get("pod", s.label_pod)
                s.label_job = labels.get("job", s.label_job)
                s.label_service = labels.get("service", s.label_service)
            if "metrics" in data and isinstance(data["metrics"], dict):
                m: Dict[str, str] = data["metrics"]
                s.metrics = MetricCatalog(
                    cpu_usage=m.get("cpu_usage", s.metrics.cpu_usage),
                    mem_working_set=m.get("mem_working_set", s.metrics.mem_working_set),
                    http_requests_total=m.get("http_requests_total", s.metrics.http_requests_total),
                    http_duration_bucket=m.get("http_duration_bucket", s.metrics.http_duration_bucket),
                )
        except Exception as e:
            raise ConfigError(f"Invalid config file: {cfg_path}") from e

        # apply env overrides
        if env_server:
            s.server = env_server
        if env_timeout:
            try:
                s.timeout_seconds = float(env_timeout)
            except Exception as e:
                raise ConfigError("PROMQL_ASSISTANT_TIMEOUT must be a number") from e
        if env_bearer:
            s.auth_bearer_token = env_bearer
        if env_basic_user:
            s.auth_basic_user = env_basic_user
        if env_basic_pass:
            s.auth_basic_pass = env_basic_pass

        return s
