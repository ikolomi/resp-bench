"""Key generator matching Java/Ruby implementations."""

import threading

from ..config.models import KeyspaceConfig
from .java_random import JavaRandom


class KeyGenerator:
    def __init__(self, config: KeyspaceConfig):
        self._keys_count = config.keys_count
        self._prefix = config.key_prefix or "bench:"
        self._alg = config.generation_alg
        self._counter = 0
        self._lock = threading.Lock()
        if self._alg == "uniform_rand":
            self._rng = JavaRandom(config.seed or 0)

    def next_key(self) -> str:
        if self._alg == "sequential_int":
            with self._lock:
                idx = self._counter % self._keys_count
                self._counter += 1
        else:
            with self._lock:
                idx = self._rng.next_int(self._keys_count)
        return f"{self._prefix}{idx}"

    def fork(self, seed: int) -> "KeyGenerator":
        """Create a new generator with a different seed (for parallel workers)."""
        cfg = KeyspaceConfig(
            keys_count=self._keys_count,
            key_prefix=self._prefix,
            generation_alg=self._alg,
            seed=seed,
        )
        return KeyGenerator(cfg)
