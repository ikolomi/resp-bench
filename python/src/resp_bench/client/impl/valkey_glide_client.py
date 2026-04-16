"""valkey-glide sync and async client implementations."""

from ...config.models import DriverConfig
from ..benchmark_client import AsyncBenchmarkClient, BenchmarkClient
from ..timed_result import TimedResult


class ValkeyGlideSyncClient(BenchmarkClient):
    def __init__(self):
        self._client = None

    def connect(self, host: str, port: int, config: DriverConfig) -> None:
        from glide_sync import GlideClient, GlideClientConfiguration, NodeAddress

        addr = NodeAddress(host, port)
        glide_config = GlideClientConfiguration([addr])
        self._client = GlideClient.create(glide_config)

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
        try:
            import glide_sync
            return getattr(glide_sync, "__version__", "unknown")
        except Exception:
            return "unknown"


class ValkeyGlideAsyncClient(AsyncBenchmarkClient):
    def __init__(self):
        self._client = None

    async def connect(self, host: str, port: int, config: DriverConfig) -> None:
        from glide import GlideClient, GlideClientConfiguration, NodeAddress

        addr = NodeAddress(host, port)
        glide_config = GlideClientConfiguration([addr])
        self._client = await GlideClient.create(glide_config)

    async def ping(self) -> TimedResult:
        return await self._measure(self._client.ping())

    async def get(self, key: str) -> TimedResult:
        return await self._measure(self._client.get(key))

    async def set(self, key: str, value: bytes) -> TimedResult:
        return await self._measure(self._client.set(key, value))

    async def close(self) -> None:
        if self._client:
            await self._client.close()

    def driver_version(self) -> str:
        try:
            import glide
            return getattr(glide, "__version__", "unknown")
        except Exception:
            return "unknown"
