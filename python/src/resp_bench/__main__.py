"""resp-bench Python engine CLI entry point."""

import argparse
import asyncio
import json
import sys

from .client.benchmark_client_factory import BenchmarkClientFactory
from .config.config_loader import ConfigLoader
from .engine.benchmark_engine import BenchmarkEngine


def print_info():
    drivers = BenchmarkClientFactory.supported_drivers()
    print("resp-bench Python Engine")
    print()
    print("Supported drivers:")
    for d in drivers:
        print(f"  - {d}")
    print()
    print("Supported commands: get, set, ping")


def main():
    parser = argparse.ArgumentParser(description="resp-bench Python engine")
    parser.add_argument("--server", help="Server address (host:port)")
    parser.add_argument("--driver", help="Driver config JSON file")
    parser.add_argument("--workload", help="Workload config JSON file")
    parser.add_argument("--metrics", help="Metrics output file (NDJSON)")
    parser.add_argument("--commit-id", help="Git commit ID for metadata")
    parser.add_argument(
        "--mode",
        choices=["sync", "async"],
        default="async",
        help="Execution mode (default: async)",
    )
    parser.add_argument(
        "--info", action="store_true", help="Show supported drivers"
    )

    args = parser.parse_args()

    if args.info:
        print_info()
        return

    if not all([args.server, args.driver, args.workload, args.metrics]):
        parser.error("--server, --driver, --workload, and --metrics are required")

    driver_config = ConfigLoader.load_driver_config(args.driver)
    workload_config = ConfigLoader.load_workload_config(args.workload)

    host, _, port_str = args.server.partition(":")
    port = int(port_str) if port_str else 6379

    engine = BenchmarkEngine(
        host=host,
        port=port,
        driver_config=driver_config,
        workload_config=workload_config,
        metrics_path=args.metrics,
        commit_id=args.commit_id,
        mode=args.mode,
    )

    if args.mode == "async":
        asyncio.run(engine.run_async())
    else:
        engine.run_sync()


if __name__ == "__main__":
    main()
