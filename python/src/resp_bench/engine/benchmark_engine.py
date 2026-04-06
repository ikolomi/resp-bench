"""Benchmark engine - orchestrates phases, connections, and metrics."""

import asyncio
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from ..client.benchmark_client_factory import BenchmarkClientFactory
from ..command.command_factory import create_all_commands
from ..config.models import DriverConfig, PhaseConfig, WorkloadConfig
from ..engine.command_selector import CommandSelector
from ..engine.key_generator import KeyGenerator
from ..engine.rate_limiter import AsyncRateLimiter, RateLimiter
from ..metrics.metrics_collector import MetricsCollector
from ..metrics.ndjson_writer import NdjsonWriter

PROGRESS_INTERVAL = 5  # seconds


class BenchmarkEngine:
    def __init__(
        self,
        host: str,
        port: int,
        driver_config: DriverConfig,
        workload_config: WorkloadConfig,
        metrics_path: str,
        commit_id: Optional[str] = None,
        mode: str = "async",
    ):
        self._host = host
        self._port = port
        self._driver_config = driver_config
        self._workload_config = workload_config
        self._writer = NdjsonWriter(metrics_path)
        self._commit_id = commit_id
        self._mode = mode

    # ── Async execution ──────────────────────────────────────────────────

    async def run_async(self):
        driver_id = self._driver_config.driver_id
        print(f"[INFO] Starting async benchmark with driver: {driver_id}")

        # Get driver version from a temporary client
        tmp = BenchmarkClientFactory.create_async(driver_id)
        version = tmp.driver_version()
        self._writer.set_metadata(
            commit_id=self._commit_id,
            driver_id=driver_id,
            driver_version=version,
        )

        for phase in self._workload_config.phases:
            await self._run_phase_async(phase)

        print("[INFO] Benchmark complete.")

    async def _run_phase_async(self, phase: PhaseConfig):
        print(f"[INFO] Phase '{phase.id}': {phase.connections} connections")

        # Create clients
        clients = []
        for _ in range(phase.connections):
            c = BenchmarkClientFactory.create_async(self._driver_config.driver_id)
            await c.connect(self._host, self._port, self._driver_config)
            clients.append(c)

        commands = create_all_commands(phase.commands)
        key_gen = KeyGenerator(phase.keyspace)
        selector = CommandSelector(commands)
        rps_limiter = AsyncRateLimiter(phase.rps_limit)
        collector = MetricsCollector()

        total_requests = phase.completion.total_requests
        duration_secs = phase.completion.duration_seconds
        collector.start()

        # Distribute work across async tasks (one per connection)
        if phase.completion.request_based:
            per_conn = total_requests // phase.connections
            remainder = total_requests % phase.connections
            tasks = []
            for i, client in enumerate(clients):
                n = per_conn + (1 if i < remainder else 0)
                tasks.append(
                    self._async_worker_requests(
                        client, selector, key_gen, rps_limiter, collector, n
                    )
                )
            await asyncio.gather(*tasks)
        else:
            end_time = time.monotonic() + duration_secs
            tasks = [
                self._async_worker_duration(
                    client, selector, key_gen, rps_limiter, collector, end_time
                )
                for client in clients
            ]
            await asyncio.gather(*tasks)

        collector.stop()

        for c in clients:
            await c.close()

        self._log_phase_summary(phase, collector)
        self._writer.write_phase_results(
            phase_id=phase.id,
            status="COMPLETED",
            connections=phase.connections,
            collector=collector,
        )

    async def _async_worker_requests(
        self, client, selector, key_gen, limiter, collector, count
    ):
        for _ in range(count):
            await limiter.acquire()
            cmd = selector.select()
            result = await cmd.execute_async(client, key_gen)
            collector.record(result.command_name, result.latency_micros, result.success)

    async def _async_worker_duration(
        self, client, selector, key_gen, limiter, collector, end_time
    ):
        while time.monotonic() < end_time:
            await limiter.acquire()
            cmd = selector.select()
            result = await cmd.execute_async(client, key_gen)
            collector.record(result.command_name, result.latency_micros, result.success)

    # ── Sync execution ───────────────────────────────────────────────────

    def run_sync(self):
        driver_id = self._driver_config.driver_id
        print(f"[INFO] Starting sync benchmark with driver: {driver_id}")

        tmp = BenchmarkClientFactory.create_sync(driver_id)
        version = tmp.driver_version()
        self._writer.set_metadata(
            commit_id=self._commit_id,
            driver_id=driver_id,
            driver_version=version,
        )

        for phase in self._workload_config.phases:
            self._run_phase_sync(phase)

        print("[INFO] Benchmark complete.")

    def _run_phase_sync(self, phase: PhaseConfig):
        print(f"[INFO] Phase '{phase.id}': {phase.connections} connections")

        clients = []
        for _ in range(phase.connections):
            c = BenchmarkClientFactory.create_sync(self._driver_config.driver_id)
            c.connect(self._host, self._port, self._driver_config)
            clients.append(c)

        commands = create_all_commands(phase.commands)
        key_gen = KeyGenerator(phase.keyspace)
        selector = CommandSelector(commands)
        rps_limiter = RateLimiter(phase.rps_limit)

        # Each thread gets its own collector, merge after
        collectors = [MetricsCollector() for _ in clients]
        total_requests = phase.completion.total_requests
        duration_secs = phase.completion.duration_seconds

        main_collector = MetricsCollector()
        main_collector.start()

        if phase.completion.request_based:
            per_conn = total_requests // phase.connections
            remainder = total_requests % phase.connections
            with ThreadPoolExecutor(max_workers=phase.connections) as pool:
                futures = []
                for i, client in enumerate(clients):
                    n = per_conn + (1 if i < remainder else 0)
                    futures.append(
                        pool.submit(
                            self._sync_worker_requests,
                            client,
                            selector,
                            key_gen,
                            rps_limiter,
                            collectors[i],
                            n,
                        )
                    )
                for f in futures:
                    f.result()
        else:
            end_time = time.monotonic() + duration_secs
            with ThreadPoolExecutor(max_workers=phase.connections) as pool:
                futures = [
                    pool.submit(
                        self._sync_worker_duration,
                        client,
                        selector,
                        key_gen,
                        rps_limiter,
                        collectors[i],
                        end_time,
                    )
                    for i, client in enumerate(clients)
                ]
                for f in futures:
                    f.result()

        main_collector.stop()
        for c in collectors:
            main_collector.merge_from(c)

        for c in clients:
            c.close()

        self._log_phase_summary(phase, main_collector)
        self._writer.write_phase_results(
            phase_id=phase.id,
            status="COMPLETED",
            connections=phase.connections,
            collector=main_collector,
        )

    def _sync_worker_requests(
        self, client, selector, key_gen, limiter, collector, count
    ):
        for _ in range(count):
            limiter.acquire()
            cmd = selector.select()
            result = cmd.execute_sync(client, key_gen)
            collector.record(result.command_name, result.latency_micros, result.success)

    def _sync_worker_duration(
        self, client, selector, key_gen, limiter, collector, end_time
    ):
        while time.monotonic() < end_time:
            limiter.acquire()
            cmd = selector.select()
            result = cmd.execute_sync(client, key_gen)
            collector.record(result.command_name, result.latency_micros, result.success)

    # ── Helpers ───────────────────────────────────────────────────────────

    def _log_phase_summary(self, phase, collector):
        rps = 0
        if collector.duration_millis > 0:
            rps = int(collector.total_requests / (collector.duration_millis / 1000))
        print(
            f"[INFO] Phase '{phase.id}' complete: "
            f"{collector.total_requests} requests, "
            f"{collector.total_errors} errors, "
            f"{collector.duration_millis}ms, "
            f"~{rps} rps"
        )
        for name, m in collector.all_metrics.items():
            print(
                f"  {name}: p50={int(m.p50)}us p99={int(m.p99)}us "
                f"p999={int(m.p999)}us max={int(m.max)}us"
            )
