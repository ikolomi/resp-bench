"""Timed result from a client operation."""

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class TimedResult:
    value: Any = None
    latency_micros: int = 0
    error: Optional[Exception] = None

    @property
    def success(self) -> bool:
        return self.error is None
