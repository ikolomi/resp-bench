"""Factory for creating benchmark clients by driver ID."""


# Lazy imports to avoid requiring all client libraries at once
_SYNC_DRIVERS = {
    "redis-py": ("resp_bench.client.impl.redis_py_client", "RedisPySyncClient"),
    "valkey-py": ("resp_bench.client.impl.valkey_py_client", "ValkeyPySyncClient"),
    "valkey-glide": (
        "resp_bench.client.impl.valkey_glide_client",
        "ValkeyGlideSyncClient",
    ),
    "valkey-glide-python": (
        "resp_bench.client.impl.valkey_glide_client",
        "ValkeyGlideSyncClient",
    ),
}

_ASYNC_DRIVERS = {
    "redis-py": ("resp_bench.client.impl.redis_py_client", "RedisPyAsyncClient"),
    "valkey-py": ("resp_bench.client.impl.valkey_py_client", "ValkeyPyAsyncClient"),
    "valkey-glide": (
        "resp_bench.client.impl.valkey_glide_client",
        "ValkeyGlideAsyncClient",
    ),
    "valkey-glide-python": (
        "resp_bench.client.impl.valkey_glide_client",
        "ValkeyGlideAsyncClient",
    ),
}


def _load_class(module_name: str, class_name: str):
    import importlib

    mod = importlib.import_module(module_name)
    return getattr(mod, class_name)


class BenchmarkClientFactory:
    @staticmethod
    def create_sync(driver_id: str) -> BenchmarkClient:
        if driver_id not in _SYNC_DRIVERS:
            raise ValueError(
                f"Unknown driver: {driver_id}. "
                f"Supported: {', '.join(_SYNC_DRIVERS.keys())}"
            )
        mod, cls = _SYNC_DRIVERS[driver_id]
        return _load_class(mod, cls)()

    @staticmethod
    def create_async(driver_id: str) -> AsyncBenchmarkClient:
        if driver_id not in _ASYNC_DRIVERS:
            raise ValueError(
                f"Unknown driver: {driver_id}. "
                f"Supported: {', '.join(_ASYNC_DRIVERS.keys())}"
            )
        mod, cls = _ASYNC_DRIVERS[driver_id]
        return _load_class(mod, cls)()

    @staticmethod
    def supported_drivers():
        return list(_SYNC_DRIVERS.keys())
