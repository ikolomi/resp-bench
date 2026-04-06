"""valkey-py sync and async client implementations."""

import valkey
import valkey.asyncio as aiovalkey

from ...config.models import DriverConfig
from ..benchmark_client import AsyncBenchmarkClient, BenchmarkClient
from ..timed_result import TimedResult


class ValkeyPySyncClient(BenchmarkClient):
    def __init__(self):
        self._client = None

    def connect(self, host: str, port: int, config: DriverConfig) -> None:
        kwargs = {"host": host, "port": port, "decode_responses": False}
        if config.auth:
            if config.auth.get("password"):
                kwargs["password"] = config.auth["password"]
            if config.auth.get("username"):
                kwargs["username"] = config.auth["username"]
        if config.mode == "cluster":
            from valkey.cluster import ValkeyCluster

            self._client = ValkeyCluster(**kwargs)
        else:
            self._client = valkey.Valkey(**kwargs)

    def ping(self) -> TimedResult:
        return self._measure(lambda: self._client.ping())

    def get(self, key: str) -> TimedResult:
        return self._measure(lambda: self._client.get(key))

    def set(self, key: str, value: bytes) -> TimedResult:
        return self._measure(lambda: self._client.set(key, value))

    def close(self) -> None:
        if self._client:
            self._client.close()

    def driver_version(self) -> str:
        return valkey.__version__


class ValkeyPyAsyncClient(AsyncBenchmarkClient):
    def __init__(self):
        self._client = None

    async def connect(self, host: str, port: int, config: DriverConfig) -> None:
        kwargs = {"host": host, "port": port, "decode_responses": False}
        if config.auth:
            if config.auth.get("password"):
                kwargs["password"] = config.auth["password"]
            if config.auth.get("username"):
                kwargs["username"] = config.auth["username"]
        if config.mode == "cluster":
            from valkey.asyncio.cluster import ValkeyCluster

            self._client = ValkeyCluster(**kwargs)
        else:
            self._client = aiovalkey.Valkey(**kwargs)

    async def ping(self) -> TimedResult:
        return await self._measure(self._client.ping())

    async def get(self, key: str) -> TimedResult:
        return await self._measure(self._client.get(key))

    async def set(self, key: str, value: bytes) -> TimedResult:
        return await self._measure(self._client.set(key, value))

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()

    def driver_version(self) -> str:
        return valkey.__version__
