"""Abstract benchmark client interface."""

import time
from abc import ABC, abstractmethod
from typing import List

from ..config.models import DriverConfig
from .timed_result import TimedResult


class BenchmarkClient(ABC):
    """Base class for sync benchmark clients."""

    @abstractmethod
    def connect(self, host: str, port: int, config: DriverConfig) -> None:
        pass

    @abstractmethod
    def ping(self) -> TimedResult:
        pass

    @abstractmethod
    def get(self, key: str) -> TimedResult:
        pass

    @abstractmethod
    def set(self, key: str, value: bytes) -> TimedResult:
        pass

    @abstractmethod
    def close(self) -> None:
        pass

    @abstractmethod
    def driver_version(self) -> str:
        pass

    def _measure(self, func):
        start = time.perf_counter_ns()
        try:
            result = func()
            latency = (time.perf_counter_ns() - start) // 1000
            return TimedResult(value=result, latency_micros=latency)
        except Exception as e:
            latency = (time.perf_counter_ns() - start) // 1000
            return TimedResult(latency_micros=latency, error=e)


class AsyncBenchmarkClient(ABC):
    """Base class for async benchmark clients."""

    @abstractmethod
    async def connect(self, host: str, port: int, config: DriverConfig) -> None:
        pass

    @abstractmethod
    async def ping(self) -> TimedResult:
        pass

    @abstractmethod
    async def get(self, key: str) -> TimedResult:
        pass

    @abstractmethod
    async def set(self, key: str, value: bytes) -> TimedResult:
        pass

    @abstractmethod
    async def close(self) -> None:
        pass

    @abstractmethod
    def driver_version(self) -> str:
        pass

    async def _measure(self, coro):
        start = time.perf_counter_ns()
        try:
            result = await coro
            latency = (time.perf_counter_ns() - start) // 1000
            return TimedResult(value=result, latency_micros=latency)
        except Exception as e:
            latency = (time.perf_counter_ns() - start) // 1000
            return TimedResult(latency_micros=latency, error=e)
