"""Metrics collection using HdrHistogram."""

import threading
import time
from typing import Dict, Optional

from hdrh.histogram import HdrHistogram


MAX_LATENCY = 600_000_000  # 600 seconds in microseconds


class CommandMetrics:
    def __init__(self, command_name: str):
        self.command_name = command_name
        self.requests = 0
        self.errors = 0
        self.histogram = HdrHistogram(1, MAX_LATENCY, 3)

    def record(self, latency_micros: int, success: bool):
        self.requests += 1
        if success:
            self.histogram.record_value(min(latency_micros, MAX_LATENCY))
        else:
            self.errors += 1

    def merge_from(self, other: "CommandMetrics"):
        self.requests += other.requests
        self.errors += other.errors
        self.histogram.add(other.histogram)

    @property
    def count(self):
        return self.histogram.total_count

    @property
    def min(self):
        return self.histogram.get_min_value()

    @property
    def max(self):
        return self.histogram.get_max_value()

    @property
    def p50(self):
        return self.histogram.get_value_at_percentile(50)

    @property
    def p95(self):
        return self.histogram.get_value_at_percentile(95)

    @property
    def p99(self):
        return self.histogram.get_value_at_percentile(99)

    @property
    def p999(self):
        return self.histogram.get_value_at_percentile(99.9)


class MetricsCollector:
    def __init__(self):
        self._command_metrics: Dict[str, CommandMetrics] = {}
        self._lock = threading.Lock()
        self.total_requests = 0
        self.total_errors = 0
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None

    def start(self):
        self.start_time = time.time()

    def stop(self):
        self.end_time = time.time()

    def record(self, command_name: str, latency_micros: int, success: bool):
        self.total_requests += 1
        if not success:
            self.total_errors += 1
        with self._lock:
            if command_name not in self._command_metrics:
                self._command_metrics[command_name] = CommandMetrics(command_name)
        self._command_metrics[command_name].record(latency_micros, success)

    def merge_from(self, other: "MetricsCollector"):
        self.total_requests += other.total_requests
        self.total_errors += other.total_errors
        for name, metrics in other._command_metrics.items():
            with self._lock:
                if name not in self._command_metrics:
                    self._command_metrics[name] = CommandMetrics(name)
            self._command_metrics[name].merge_from(metrics)

    @property
    def duration_millis(self) -> int:
        if self.start_time and self.end_time:
            return int((self.end_time - self.start_time) * 1000)
        return 0

    @property
    def all_metrics(self) -> Dict[str, CommandMetrics]:
        return self._command_metrics
