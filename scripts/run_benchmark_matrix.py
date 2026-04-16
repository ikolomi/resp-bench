#!/usr/bin/env python3
"""
run_benchmark_matrix.py — Matrix-based benchmark orchestrator.

Runs benchmarks across a Cartesian product of configurable dimensions,
producing results that can be visualized with generate_interactive_graphs.py.

Supports arbitrary dimension sweeps:
  - Different drivers in the same run
  - Glide JNI thread configurations (env vars)
  - Pool size sweeps for Spring Data drivers
  - Any combination of the above

Dimensions can be:
  - Arrays: participate in Cartesian product (free dimensions)
  - Bindings ("$other_dim"): mirrors another dimension's value per data point
  - Scalars: fixed value, not varied
  - Objects with "values" + "applies_to": conditional dimensions that only
    apply to matching driver configs (glob matching on driver_config path)

One dimension is designated as the X axis (typically "connections").
All other free dimensions form the series (one line per unique combo).

Output is a flat directory with one NDJSON file per series label:
    <output-dir>/<label>.ndjson
    <output-dir>/<label>.cpu.ndjson
    <output-dir>/_manifest.json

The _manifest.json records the full configuration for each variant,
allowing generate_interactive_graphs.py to build rich legends.

Usage:
    python scripts/run_benchmark_matrix.py \\
        --matrix configs/matrices/glide-thread-sweep.json \\
        --output-dir results/glide-thread-sweep \\
        --server-host 10.0.0.5

    python scripts/run_benchmark_matrix.py \\
        --matrix configs/matrices/driver-comparison-high-tps.json \\
        --output-dir results/driver-comparison \\
        --server-host localhost
"""

import argparse
import copy
import fnmatch
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from system_monitor import SystemMonitor

# ═══════════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════════

SYSTEM_MONITOR_INTERVAL = 0.5

# Well-known dimension names with special handling
DIM_CONNECTIONS = "connections"
DIM_DRIVER_CONFIG = "driver_config"
DIM_POOL_SIZE = "pool_size"
DIM_ENV = "env"

# Dimensions that map to driver config JSON overrides
DRIVER_CONFIG_DIMS = {DIM_POOL_SIZE, "use_pooling", "share_native_connection"}

# Map driver_id → engine make target (for multi-engine support)
DRIVER_ENGINE_MAP = {
    # Java drivers
    "jedis": "java",
    "lettuce": "java",
    "valkey-glide": "java",
    "redisson": "java",
    "spring-data-valkey": "java",
    "spring-data-redis": "java",
    # Ruby drivers
    "redis-rb": "ruby",
    "valkey-glide-ruby": "ruby",
    # C# drivers
    "stackexchange-redis": "csharp",
    "valkey-glide-csharp": "csharp",
    # Python drivers
    "redis-py": "python",
    "valkey-py": "python",
    "valkey-glide-python": "python",
    # Recording (default to java)
    "recording": "java",
}


def detect_engine_for_driver(driver_config_path):
    """Detect the correct engine (make target) for a driver config file.

    Reads the driver_id from the JSON file and maps it to the engine name.
    Falls back to 'java' if unknown.
    """
    try:
        with open(driver_config_path) as f:
            config = json.load(f)
        driver_id = config.get("driver_id", "").lower()
        return DRIVER_ENGINE_MAP.get(driver_id, "java")
    except (json.JSONDecodeError, OSError, KeyError):
        return "java"


# ═══════════════════════════════════════════════════════════════════════════════
# Matrix Config Parsing
# ═══════════════════════════════════════════════════════════════════════════════

class DimensionSpec:
    """Parsed specification for a single dimension."""

    def __init__(self, name, raw_value):
        self.name = name
        self.raw = raw_value

        if isinstance(raw_value, dict) and "values" in raw_value:
            # Extended form: {"values": [...], "applies_to": {...}}
            self.values = raw_value["values"]
            self.applies_to = raw_value.get("applies_to", None)
        elif isinstance(raw_value, list):
            # Simple array
            self.values = raw_value
            self.applies_to = None
        elif isinstance(raw_value, str) and raw_value.startswith("$"):
            # Binding reference
            self.values = [raw_value]
            self.applies_to = None
        else:
            # Scalar (fixed value)
            self.values = [raw_value]
            self.applies_to = None

    @property
    def is_binding_only(self):
        """True if ALL values are bindings (e.g., ["$connections"])."""
        return all(isinstance(v, str) and v.startswith("$") for v in self.values)

    @property
    def is_scalar(self):
        """True if this is a single fixed value (not a binding)."""
        return len(self.values) == 1 and not self.is_binding_only

    def matches_driver(self, driver_config_path):
        """Check if this dimension applies to the given driver config path."""
        if self.applies_to is None:
            return True  # No filter = applies to all

        for filter_dim, patterns in self.applies_to.items():
            if filter_dim == DIM_DRIVER_CONFIG:
                basename = Path(driver_config_path).stem
                full_path = str(driver_config_path)
                if not any(
                    fnmatch.fnmatch(basename, p) or fnmatch.fnmatch(full_path, p)
                    for p in patterns
                ):
                    return False
        return True


def parse_matrix_config(matrix_path):
    """Parse and validate a matrix configuration JSON file.

    Returns:
        config: dict with keys:
            - description: str
            - x_axis: str (dimension name)
            - iterations: int
            - server_host: str (optional)
            - port: int (optional)
            - workload_template: str (optional)
            - dimensions: dict[name] -> DimensionSpec
    """
    with open(matrix_path) as f:
        raw = json.load(f)

    config = {
        "description": raw.get("description", ""),
        "x_axis": raw.get("x_axis", DIM_CONNECTIONS),
        "iterations": raw.get("iterations", 10),
        "server_host": raw.get("server_host", None),
        "port": raw.get("port", 6379),
        "workload_template": raw.get("workload_template"),
        "cpu_interval": raw.get("cpu_interval", SYSTEM_MONITOR_INTERVAL),
    }

    dimensions = {}
    for name, spec in raw.get("dimensions", {}).items():
        dimensions[name] = DimensionSpec(name, spec)

    config["dimensions"] = dimensions

    # Validation
    x_axis = config["x_axis"]
    if x_axis not in dimensions:
        raise ValueError(f"x_axis '{x_axis}' not found in dimensions: {list(dimensions.keys())}")

    if DIM_DRIVER_CONFIG not in dimensions:
        raise ValueError(f"'{DIM_DRIVER_CONFIG}' dimension is required")

    if not config["workload_template"]:
        raise ValueError("'workload_template' is required in matrix config")

    return config


# ═══════════════════════════════════════════════════════════════════════════════
# Cartesian Product with Filtering and Binding Resolution
# ═══════════════════════════════════════════════════════════════════════════════

def resolve_binding(value, resolved_values):
    """Resolve a binding reference like '$connections' to its current value."""
    if isinstance(value, str) and value.startswith("$"):
        ref_dim = value[1:]
        if ref_dim in resolved_values:
            return resolved_values[ref_dim]
        raise ValueError(f"Binding '{value}' references unknown dimension '{ref_dim}'")
    return value


def generate_series_combos(config):
    """Generate all series combinations (non-x-axis dimension combos).

    For each driver_config, filters dimensions by applies_to and computes
    the Cartesian product of applicable dimensions.

    Returns list of dicts, each representing one series:
        {
            "label": "sdv-glide_pool8_threads16x16",
            "driver_config": "configs/drivers/...",
            "params": {"pool_size": 8, "env": {...}, ...},
            "bindings": {"pool_size": "$connections", ...}  # if any
        }
    """
    dims = config["dimensions"]
    x_axis = config["x_axis"]

    # Get driver configs
    driver_dim = dims[DIM_DRIVER_CONFIG]
    driver_configs = driver_dim.values

    # Identify series dimensions (everything except x_axis and driver_config)
    series_dim_names = [
        name for name in dims
        if name != x_axis and name != DIM_DRIVER_CONFIG
    ]

    all_combos = []

    for driver_cfg in driver_configs:
        driver_label = Path(driver_cfg).stem

        # Filter series dimensions by applies_to
        applicable_dims = []
        for dim_name in series_dim_names:
            dim_spec = dims[dim_name]
            if dim_spec.matches_driver(driver_cfg):
                applicable_dims.append(dim_spec)

        # Separate free dimensions (array values) from pure bindings
        free_dims = []
        binding_dims = []
        for dim_spec in applicable_dims:
            # Check if ALL values are bindings
            if dim_spec.is_binding_only:
                binding_dims.append(dim_spec)
            else:
                # Separate concrete values from binding values
                concrete_vals = []
                binding_vals = []
                for v in dim_spec.values:
                    if isinstance(v, str) and v.startswith("$"):
                        binding_vals.append(v)
                    else:
                        concrete_vals.append(v)
                if concrete_vals or binding_vals:
                    free_dims.append((dim_spec.name, concrete_vals + binding_vals))

        if not free_dims:
            # No series dimensions for this driver — single series
            all_combos.append({
                "label": driver_label,
                "driver_config": driver_cfg,
                "params": {},
                "bindings": {d.name: d.values[0] for d in binding_dims},
            })
            continue

        # Cartesian product of free dimensions
        dim_names = [name for name, _ in free_dims]
        dim_values = [vals for _, vals in free_dims]

        for combo in itertools.product(*dim_values):
            params = {}
            bindings = {}

            for name, value in zip(dim_names, combo):
                if isinstance(value, str) and value.startswith("$"):
                    bindings[name] = value
                else:
                    params[name] = value

            # Add pure binding dims
            for dim_spec in binding_dims:
                bindings[dim_spec.name] = dim_spec.values[0]

            # Build label: driver_name@param1=val,param2=val
            # The @ separator cleanly delimits driver name from params
            param_parts = []
            for name, value in sorted(params.items()):
                if isinstance(value, dict):
                    # For env dicts, create compact key=value pairs
                    for k, v in sorted(value.items()):
                        short_key = k.replace("GLIDE_TOKIO_WORKER_THREADS", "tw") \
                                     .replace("GLIDE_CALLBACK_WORKER_THREADS", "cb")
                        param_parts.append(f"{short_key}={v}")
                else:
                    param_parts.append(f"{name}={value}")

            for name, binding in sorted(bindings.items()):
                ref = binding[1:]  # strip $
                param_parts.append(f"{name}={ref}")

            label = driver_label if not param_parts else f"{driver_label}@{','.join(param_parts)}"

            all_combos.append({
                "label": label,
                "driver_config": driver_cfg,
                "params": params,
                "bindings": bindings,
            })

    return all_combos


# ═══════════════════════════════════════════════════════════════════════════════
# Workload & Driver Config Generation
# ═══════════════════════════════════════════════════════════════════════════════

def generate_workload(template_path, connections):
    """Generate a workload JSON with the given connection count."""
    with open(template_path) as f:
        workload = json.load(f)

    for phase in workload.get("phases", []):
        phase["connections"] = connections

    return workload


def generate_driver_config(base_config_path, overrides):
    """Generate a modified driver config JSON with overrides applied.

    overrides is a dict of specific_driver_config keys to set,
    e.g. {"pool_size": 32, "use_pooling": true}.
    """
    with open(base_config_path) as f:
        config = json.load(f)

    if overrides:
        sdc = config.get("specific_driver_config", {})
        sdc.update(overrides)
        config["specific_driver_config"] = sdc

    return config


# ═══════════════════════════════════════════════════════════════════════════════
# Benchmark Execution
# ═══════════════════════════════════════════════════════════════════════════════

def flush_server(server_host, port):
    """Run redis-cli FLUSHALL on the server."""
    subprocess.run(
        ["redis-cli", "-h", server_host, "-p", str(port), "flushall"],
        check=True,
        capture_output=True,
    )


def run_benchmark(server, driver_file, workload_file, metrics_output, env_overrides=None):
    """Run a single benchmark via `make java-run`."""
    env = os.environ.copy()
    if env_overrides:
        env.update({k: str(v) for k, v in env_overrides.items()})

    subprocess.run(
        [
            "make", "java-run",
            f"SERVER={server}",
            f"DRIVER={driver_file}",
            f"WORKLOAD={workload_file}",
            f"METRICS_OUTPUT={metrics_output}",
        ],
        check=True,
        env=env,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Manifest
# ═══════════════════════════════════════════════════════════════════════════════

def write_manifest(output_dir, config, series_combos):
    """Write _manifest.json describing the matrix run."""
    variants = {}
    for combo in series_combos:
        variant_info = {
            "driver_config": combo["driver_config"],
            "driver_name": Path(combo["driver_config"]).stem,
        }
        if combo["params"]:
            variant_info["params"] = combo["params"]
        if combo["bindings"]:
            variant_info["bindings"] = combo["bindings"]
        variants[combo["label"]] = variant_info

    manifest = {
        "description": config["description"],
        "x_axis": config["x_axis"],
        "iterations": config["iterations"],
        "variants": variants,
    }

    manifest_path = output_dir / "_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote manifest: {manifest_path}")


# ═══════════════════════════════════════════════════════════════════════════════
# Main Orchestration Loop
# ═══════════════════════════════════════════════════════════════════════════════

def run_matrix(config, output_dir, server_host, port):
    """Main orchestration loop: for each iteration × x_value × series_combo, run benchmark."""
    dims = config["dimensions"]
    x_axis = config["x_axis"]
    x_values = dims[x_axis].values
    iterations = config["iterations"]
    cpu_interval = config["cpu_interval"]
    workload_template = config["workload_template"]

    server = f"{server_host}:{port}"

    # Generate series combos
    series_combos = generate_series_combos(config)

    print("=" * 70)
    print(f"Matrix Benchmark Run")
    print(f"  Description: {config['description']}")
    print(f"  Server:      {server}")
    print(f"  X axis:      {x_axis} = {x_values}")
    print(f"  Series:      {len(series_combos)}")
    for combo in series_combos:
        print(f"    - {combo['label']}")
        if combo['params']:
            print(f"      params: {combo['params']}")
        if combo['bindings']:
            print(f"      bindings: {combo['bindings']}")
    print(f"  Iterations:  {iterations}")
    print(f"  Total runs:  {len(x_values) * len(series_combos) * iterations}")
    print("=" * 70)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Write manifest
    write_manifest(output_dir, config, series_combos)

    # Create temp dir for generated configs
    tmpdir = Path(tempfile.mkdtemp(prefix="resp-bench-matrix-"))

    try:
        for iteration in range(1, iterations + 1):
            for x_val in x_values:
                for combo in series_combos:
                    label = combo["label"]
                    driver_cfg_path = combo["driver_config"]
                    params = dict(combo["params"])
                    bindings = combo["bindings"]

                    # Resolve bindings for this x_value
                    resolved = {x_axis: x_val}
                    resolved.update(params)
                    for dim_name, binding in bindings.items():
                        resolved[dim_name] = resolve_binding(binding, resolved)
                        params[dim_name] = resolved[dim_name]

                    print(f"\n=== iter={iteration}  {x_axis}={x_val}  "
                          f"series={label} ===")

                    # Flush server
                    flush_server(server_host, port)

                    # Generate workload
                    if x_axis == DIM_CONNECTIONS:
                        connections = x_val
                    else:
                        connections = resolved.get(DIM_CONNECTIONS, 1)

                    workload = generate_workload(workload_template, connections)
                    workload_path = tmpdir / f"workload_{label}_{x_val}.json"
                    workload_path.write_text(json.dumps(workload, indent=2))

                    # Generate driver config with overrides
                    driver_overrides = {}
                    for dim_name, dim_val in resolved.items():
                        if dim_name in DRIVER_CONFIG_DIMS:
                            driver_overrides[dim_name] = dim_val

                    driver_config = generate_driver_config(driver_cfg_path, driver_overrides)
                    driver_path = tmpdir / f"driver_{label}_{x_val}.json"
                    driver_path.write_text(json.dumps(driver_config, indent=2))

                    # Collect env overrides
                    env_overrides = {}
                    env_val = resolved.get(DIM_ENV)
                    if env_val and isinstance(env_val, dict):
                        env_overrides.update(env_val)
                    elif DIM_ENV in params and isinstance(params[DIM_ENV], dict):
                        env_overrides.update(params[DIM_ENV])

                    # Output paths
                    metrics_output = str(output_dir / f"{label}.ndjson")
                    system_output = str(output_dir / f"{label}.system.ndjson")

                    # Prepare benchmark command
                    bench_env = os.environ.copy()
                    if env_overrides:
                        bench_env.update({k: str(v) for k, v in env_overrides.items()})

                    # Auto-detect engine from driver config
                    engine = detect_engine_for_driver(str(driver_path))
                    bench_cmd = [
                        "make", f"{engine}-run",
                        f"SERVER={server}",
                        f"DRIVER={str(driver_path)}",
                        f"WORKLOAD={str(workload_path)}",
                        f"METRICS_OUTPUT={metrics_output}",
                    ]

                    try:
                        # Launch benchmark as subprocess, get its PGID for memory tracking
                        bench_proc = subprocess.Popen(
                            bench_cmd,
                            env=bench_env,
                            start_new_session=True,  # new process group
                        )
                        pgid = os.getpgid(bench_proc.pid)

                        # Start system monitor with process group tracking
                        with SystemMonitor(system_output, interval=cpu_interval, target_pgid=pgid):
                            bench_proc.wait()

                        if bench_proc.returncode != 0:
                            raise subprocess.CalledProcessError(bench_proc.returncode, bench_cmd)

                    except subprocess.CalledProcessError as e:
                        print(f"ERROR: Benchmark failed for {label} with "
                              f"{x_axis}={x_val} (iter {iteration}): {e}",
                              file=sys.stderr)

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    print("\n" + "=" * 70)
    print("Matrix benchmark completed!")
    print(f"Results in: {output_dir}")
    print(f"Generate graphs with:")
    print(f"  python scripts/generate_interactive_graphs.py {output_dir}")
    print("=" * 70)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def parse_args():
    parser = argparse.ArgumentParser(
        description="Run benchmarks across a configurable matrix of dimensions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Glide thread configuration sweep
  python scripts/run_benchmark_matrix.py \\
      --matrix configs/matrices/valkey-glide-thread-sweep.json \\
      --output-dir results/valkey-glide-thread-sweep \\
      --server-host 10.0.0.5

  # Compare all drivers with default configs
  python scripts/run_benchmark_matrix.py \\
      --matrix configs/matrices/driver-comparison-high-tps.json \\
      --output-dir results/driver-comparison \\
      --server-host localhost

  # Dry run to see what would be executed
  python scripts/run_benchmark_matrix.py \\
      --matrix configs/matrices/valkey-glide-thread-sweep.json \\
      --output-dir /tmp/test \\
      --dry-run
""",
    )
    parser.add_argument(
        "--matrix", "-m",
        required=True,
        help="Path to matrix configuration JSON file",
    )
    parser.add_argument(
        "--output-dir", "-o",
        required=True,
        help="Directory to write benchmark results",
    )
    parser.add_argument(
        "--server-host",
        default=None,
        help="Hostname/IP of the Valkey/Redis server (overrides matrix config, default: localhost)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port of the Valkey/Redis server (overrides matrix config, default: 6379)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=None,
        help="Override iterations from matrix config",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be executed without actually running benchmarks",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    config = parse_matrix_config(args.matrix)

    # CLI overrides
    server_host = args.server_host or config.get("server_host") or "localhost"
    port = args.port or config.get("port", 6379)
    if args.iterations:
        config["iterations"] = args.iterations

    output_dir = Path(args.output_dir)

    if args.dry_run:
        series_combos = generate_series_combos(config)
        dims = config["dimensions"]
        x_axis = config["x_axis"]
        x_values = dims[x_axis].values

        print("=" * 70)
        print("DRY RUN — Matrix Benchmark Plan")
        print(f"  Description: {config['description']}")
        print(f"  Server:      {server_host}:{port}")
        print(f"  X axis:      {x_axis} = {x_values}")
        print(f"  Series:      {len(series_combos)}")
        for combo in series_combos:
            print(f"\n  Series: {combo['label']}")
            print(f"    driver_config: {combo['driver_config']}")
            if combo['params']:
                print(f"    params: {json.dumps(combo['params'], indent=6)}")
            if combo['bindings']:
                print(f"    bindings: {combo['bindings']}")
        print(f"\n  Iterations:  {config['iterations']}")
        print(f"  Total runs:  {len(x_values) * len(series_combos) * config['iterations']}")
        print(f"  Output:      {output_dir}")

        # Show per-x-value resolution for all series with bindings
        for combo in series_combos:
            if combo["bindings"]:
                print(f"\n  Binding resolution for '{combo['label']}':")
                for x_val in x_values:
                    resolved = {x_axis: x_val}
                    resolved.update(combo["params"])
                    for dim_name, binding in combo["bindings"].items():
                        resolved[dim_name] = resolve_binding(binding, resolved)
                    print(f"    {x_axis}={x_val} → {dict((k, v) for k, v in resolved.items() if k != x_axis)}")

        print("\n" + "=" * 70)
        return

    run_matrix(config, output_dir, server_host, port)


if __name__ == "__main__":
    main()
