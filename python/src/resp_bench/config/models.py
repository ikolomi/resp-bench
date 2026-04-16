"""Configuration dataclasses for resp-bench."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DriverConfig:
    schema_version: str = "1.0"
    description: Optional[str] = None
    driver_id: str = ""
    mode: str = "standalone"
    command_timeout_ms: Optional[int] = None
    tls: Optional[Dict[str, Any]] = None
    auth: Optional[Dict[str, Any]] = None
    specific_driver_config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CompletionConfig:
    type: str = "requests"
    seconds: Optional[int] = None
    requests: Optional[int] = None

    @property
    def duration_based(self) -> bool:
        return self.type == "duration"

    @property
    def request_based(self) -> bool:
        return self.type == "requests"

    @property
    def total_requests(self) -> int:
        return self.requests or 0

    @property
    def duration_seconds(self) -> int:
        return self.seconds or 0


@dataclass
class KeyspaceConfig:
    keys_count: int = 0
    key_size_bytes: int = 16
    key_prefix: str = "bench:"
    generation_alg: str = "sequential_int"
    seed: Optional[int] = None


@dataclass
class CommandConfig:
    command: str = ""
    weight: float = 1.0
    data_size_bytes: int = 256


@dataclass
class PhaseConfig:
    id: str = ""
    description: Optional[str] = None
    connections: int = 1
    cps_limit: int = -1
    rps_limit: int = -1
    pipeline_depth: int = 1
    warmup_requests: int = 1
    completion: CompletionConfig = field(default_factory=CompletionConfig)
    keyspace: KeyspaceConfig = field(default_factory=KeyspaceConfig)
    commands: List[CommandConfig] = field(default_factory=list)


@dataclass
class WorkloadConfig:
    schema_version: str = "1.0"
    benchmark_profile: Dict[str, Any] = field(default_factory=dict)
    phases: List[PhaseConfig] = field(default_factory=list)
