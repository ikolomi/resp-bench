"""Load configuration from JSON files."""

import json

from .models import (
    CommandConfig,
    CompletionConfig,
    DriverConfig,
    KeyspaceConfig,
    PhaseConfig,
    WorkloadConfig,
)


class ConfigLoader:
    @staticmethod
    def load_driver_config(path: str) -> DriverConfig:
        with open(path) as f:
            data = json.load(f)
        return ConfigLoader._parse_driver_config(data)

    @staticmethod
    def load_workload_config(path: str) -> WorkloadConfig:
        with open(path) as f:
            data = json.load(f)
        return ConfigLoader._parse_workload_config(data)

    @staticmethod
    def _parse_driver_config(data: dict) -> DriverConfig:
        return DriverConfig(
            schema_version=data.get("schema_version", "1.0"),
            description=data.get("description"),
            driver_id=data.get("driver_id", ""),
            mode=data.get("mode", "standalone"),
            command_timeout_ms=data.get("command_timeout_ms"),
            tls=data.get("tls"),
            auth=data.get("auth"),
            specific_driver_config=data.get("specific_driver_config", {}),
        )

    @staticmethod
    def _parse_workload_config(data: dict) -> WorkloadConfig:
        phases = [ConfigLoader._parse_phase(p) for p in data.get("phases", [])]
        return WorkloadConfig(
            schema_version=data.get("schema_version", "1.0"),
            benchmark_profile=data.get("benchmark_profile", {}),
            phases=phases,
        )

    @staticmethod
    def _parse_phase(data: dict) -> PhaseConfig:
        completion = data.get("completion", {})
        keyspace = data.get("keyspace", {})
        commands = [ConfigLoader._parse_command(c) for c in data.get("commands", [])]
        return PhaseConfig(
            id=data.get("id", ""),
            description=data.get("description"),
            connections=data.get("connections", 1),
            cps_limit=data.get("cps_limit", -1) or -1,
            rps_limit=data.get("rps_limit", -1) or -1,
            pipeline_depth=data.get("pipeline_depth", 1) or 1,
            warmup_requests=data.get("warmup_requests", 1) or 1,
            completion=CompletionConfig(
                type=completion.get("type", "requests"),
                seconds=completion.get("seconds"),
                requests=completion.get("requests"),
            ),
            keyspace=KeyspaceConfig(
                keys_count=keyspace.get("keys_count", 0),
                key_size_bytes=keyspace.get("key_size_bytes", 16) or 16,
                key_prefix=keyspace.get("key_prefix", "bench:") or "bench:",
                generation_alg=keyspace.get("generation_alg", "sequential_int"),
                seed=keyspace.get("seed"),
            ),
            commands=commands,
        )

    @staticmethod
    def _parse_command(data: dict) -> CommandConfig:
        return CommandConfig(
            command=data.get("command", "").lower(),
            weight=float(data.get("weight", 1.0)),
            data_size_bytes=data.get("data_size_bytes", 256) or 256,
        )
