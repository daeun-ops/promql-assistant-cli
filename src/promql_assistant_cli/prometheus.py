from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .errors import PrometheusAPIError, ValidationError


@dataclass
class PrometheusClient:
    base_url: str
    timeout_seconds: float = 10.0
    bearer_token: Optional[str] = None
    basic_auth: Optional[Tuple[str, str]] = None

    def _headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {"Accept": "application/json"}
        if self.bearer_token:
            h["Authorization"] = f"Bearer {self.bearer_token}"
        return h

    def _auth(self) -> Optional[Tuple[str, str]]:
        return self.basic_auth

    def _url(self, path: str) -> str:
        return self.base_url.rstrip("/") + path

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                r = client.get(self._url(path), params=params, headers=self._headers(), auth=self._auth())
                r.raise_for_status()
                data = r.json()
        except Exception as e:
            raise PrometheusAPIError(f"Prometheus request failed: GET {path} ({e})") from e

        if not isinstance(data, dict) or data.get("status") != "success":
            raise PrometheusAPIError(f"Prometheus API error: {data}")
        return data

    # ---- queries ----

    def query_instant(self, promql: str, ts: Optional[float] = None) -> Dict[str, Any]:
        params = {"query": promql}
        if ts is not None:
            params["time"] = ts
        return self._get("/api/v1/query", params=params)

    def query_range(self, promql: str, start: float, end: float, step: str) -> Dict[str, Any]:
        params = {"query": promql, "start": start, "end": end, "step": step}
        return self._get("/api/v1/query_range", params=params)

    def validate_promql(self, promql: str) -> None:
        # Use query endpoint to force PromQL parse/validation.
        # If query is invalid, Prometheus returns status=error (non-success).
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                r = client.get(
                    self._url("/api/v1/query"),
                    params={"query": promql, "time": time.time()},
                    headers=self._headers(),
                    auth=self._auth(),
                )
                # Prometheus returns 200 with {"status":"error"} for parse errors
                data = r.json()
        except Exception as e:
            raise PrometheusAPIError(f"Validation request failed: {e}") from e

        if not isinstance(data, dict):
            raise ValidationError("Invalid response from Prometheus during validation.")
        if data.get("status") == "success":
            return

        # status=error
        err_type = data.get("errorType")
        err = data.get("error")
        raise ValidationError(f"PromQL validation failed ({err_type}): {err}")

    # ---- discovery ----

    def metric_names(self) -> List[str]:
        data = self._get("/api/v1/label/__name__/values")
        values = data.get("data", [])
        return list(values) if isinstance(values, list) else []

    def label_names(self) -> List[str]:
        data = self._get("/api/v1/labels")
        values = data.get("data", [])
        return list(values) if isinstance(values, list) else []

    def label_values(self, label: str) -> List[str]:
        data = self._get(f"/api/v1/label/{label}/values")
        values = data.get("data", [])
        return list(values) if isinstance(values, list) else []
