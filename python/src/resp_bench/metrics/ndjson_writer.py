"""NDJSON metrics writer with HDR histogram encoding."""

import base64
import json
import os
import time
from datetime import datetime, timezone
from typing import Optional

from .metrics_collector import MetricsCollector


class NdjsonWriter:
    def __init__(self, path: str):
        self._path = path
        self._commit_id: Optional[str] = None
        self._driver_id: Optional[str] = None
        self._driver_version: Optional[str] = None

    def set_metadata(
        self,
        commit_id: Optional[str] = None,
        driver_id: Optional[str] = None,
        driver_version: Optional[str] = None,
    ):
        self._commit_id = commit_id
        self._driver_id = driver_id
        self._driver_version = driver_version

    def write_phase_results(
        self,
        phase_id: str,
        status: str,
        connections: int,
        collector: MetricsCollector,
    ):
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        record = self._build_phase_json(phase_id, status, connections, collector)
        with open(self._path, "a") as f:
            f.write(json.dumps(record) + "\n")

    def _build_phase_json(self, phase_id, status, connections, collector):
        result = {}

        if self._commit_id or self._driver_id:
            metadata = {}
            if self._commit_id:
                metadata["commit_id"] = self._commit_id
            metadata["timestamp"] = datetime.now(timezone.utc).isoformat()
            if self._driver_id:
                metadata["driver_id"] = self._driver_id
            if self._driver_version:
                metadata["primary_driver_version"] = self._driver_version
            result["metadata"] = metadata

        start_ts = (
            datetime.fromtimestamp(collector.start_time, tz=timezone.utc).isoformat()
            if collector.start_time
            else None
        )
        end_ts = (
            datetime.fromtimestamp(collector.end_time, tz=timezone.utc).isoformat()
            if collector.end_time
            else None
        )

        result["phase"] = {
            "id": phase_id,
            "status": status,
            "start_timestamp": start_ts,
            "finish_timestamp": end_ts,
            "duration_ms": collector.duration_millis,
            "connections": connections,
        }
        result["totals"] = {
            "requests": collector.total_requests,
            "errors": collector.total_errors,
        }
        result["metrics"] = self._build_command_metrics(collector)
        return result

    def _build_command_metrics(self, collector):
        metrics = {}
        for cmd_name, cmd_metrics in collector.all_metrics.items():
            cmd_data = {
                "requests": cmd_metrics.requests,
                "errors": cmd_metrics.errors,
                "latency": {
                    "unit": "us",
                    "count": cmd_metrics.count,
                    "summary": {
                        "min": int(cmd_metrics.min),
                        "p50": int(cmd_metrics.p50),
                        "p95": int(cmd_metrics.p95),
                        "p99": int(cmd_metrics.p99),
                        "p999": int(cmd_metrics.p999),
                        "max": int(cmd_metrics.max),
                    },
                },
            }
            try:
                encoded = cmd_metrics.histogram.encode()
                cmd_data["latency"]["hdr"] = {
                    "format": "hdr",
                    "sigfig": 3,
                    "payload_b64": base64.b64encode(encoded).decode("ascii"),
                }
            except Exception:
                pass
            metrics[cmd_name] = cmd_data
        return metrics
