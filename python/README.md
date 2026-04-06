# resp-bench Python Engine

Python implementation of the resp-bench benchmark suite, supporting both sync and async execution modes.

## Supported Drivers

| Driver | Package | Sync | Async |
|--------|---------|------|-------|
| redis-py | `redis` | ✅ | ✅ |
| valkey-py | `valkey` | ✅ | ✅ |
| valkey-glide | `valkey-glide` | ✅ | ✅ |

## Installation

```bash
cd python
pip install -e .
```

## Usage

```bash
# Run benchmark (async mode, default)
python -m resp_bench \
  --server localhost:6379 \
  --driver ../configs/drivers/example-redis-py-standalone.json \
  --workload ../configs/workloads/example-workload.json \
  --metrics output.ndjson

# Run in sync mode
python -m resp_bench \
  --server localhost:6379 \
  --driver ../configs/drivers/example-redis-py-standalone.json \
  --workload ../configs/workloads/example-workload.json \
  --metrics output.ndjson \
  --mode sync

# Show supported drivers
python -m resp_bench --info
```

## Using with Makefile

```bash
# Default (async)
make python-run DRIVER=configs/drivers/example-redis-py-standalone.json \
  WORKLOAD=configs/workloads/example-workload.json

# Explicit sync
make python-run-sync DRIVER=configs/drivers/example-redis-py-standalone.json \
  WORKLOAD=configs/workloads/example-workload.json

# Explicit async
make python-run-async DRIVER=configs/drivers/example-redis-py-standalone.json \
  WORKLOAD=configs/workloads/example-workload.json
```

## Testing valkey-glide PRs

To benchmark a specific valkey-glide PR branch:

```bash
# Install the PR branch
pip install git+https://github.com/valkey-io/valkey-glide.git@<branch-name>#subdirectory=python

# Run benchmark
make python-run \
  DRIVER=configs/drivers/example-valkey-glide-python-standalone.json \
  WORKLOAD=configs/workloads/example-workload.json
```

## Architecture

- **Async mode**: Uses `asyncio` with one coroutine per connection. Best for I/O-bound workloads with many connections.
- **Sync mode**: Uses `ThreadPoolExecutor` with one thread per connection. Each thread has its own `MetricsCollector` to avoid lock contention, merged after the phase completes.

Both modes support:
- HdrHistogram latency collection (1µs–600s, 3 significant figures)
- NDJSON output compatible with the resp-bench graph generator
- Java-compatible deterministic key generation (LCG PRNG)
- Token bucket rate limiting (CPS/RPS)
- Request-count and duration-based completion criteria

## Supported Commands

- `get` — GET key
- `set` — SET key value
- `ping` — PING
