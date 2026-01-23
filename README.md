# Speed Bump

**Selective Python slowdown profiler for throughput analysis.**

Speed Bump introduces controlled, selective delays into Python code execution. By slowing specific modules/functions and measuring throughput impact, you can identify which Python code paths actually matter to overall system performance.

This is particularly useful for AI/ML workloads where traditional profiling misses the subtle interactions between Python and GPU execution.

## The Problem

Traditional profilers show where Python spends time, but in GPU-accelerated systems this is misleading. If Python is busy while the GPU is also busy, speeding up Python won't help. Conversely, micro-stalls where the GPU waits for Python won't show up as "hot" in a profiler.

The fundamental issue: **time spent ≠ time that matters**.

Speed Bump inverts the problem: instead of measuring how fast code runs, measure how much throughput drops when code is artificially slowed. If slowing module X doesn't affect throughput, don't bother optimising it.

## Installation

**From source:**
```bash
git clone https://github.com/SonicField/speed-bump.git
cd speed-bump
pip install .
```

**From wheel (if available):**
```bash
pip install speed_bump-0.1.0-cp312-cp312-linux_aarch64.whl
```

**Requirements:**
- Linux (x86_64 or aarch64)
- Python 3.12+

## Quick Start

1. Create a targets file specifying what to slow:

```
# targets.txt
transformers.modeling_llama:LlamaAttention.*
vllm.worker.model_runner:ModelRunner.execute_model
```

2. Run your application with Speed Bump:

```bash
export SPEED_BUMP_TARGETS=/path/to/targets.txt
export SPEED_BUMP_DELAY_NS=10000      # 10µs delay per call
export SPEED_BUMP_START_MS=5000       # Start after 5s warmup
export SPEED_BUMP_DURATION_MS=30000   # Run for 30s

python your_benchmark.py
```

3. Compare throughput with and without `SPEED_BUMP_TARGETS` set.

## Configuration

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `SPEED_BUMP_TARGETS` | Path to targets file | (disabled) |
| `SPEED_BUMP_DELAY_NS` | Delay in nanoseconds per trigger | 1000 |
| `SPEED_BUMP_FREQUENCY` | Trigger every Nth matching call | 1 |
| `SPEED_BUMP_START_MS` | Milliseconds after process start | 0 |
| `SPEED_BUMP_DURATION_MS` | Duration in milliseconds (0 = indefinite) | 0 |

### Target File Format

```
# Comments start with #
# Format: module_glob:qualified_name_glob

# Match all methods of a class
transformers.modeling_llama:LlamaAttention.*

# Match a specific function
vllm.worker.model_runner:ModelRunner.execute_model

# Match everything in a module
mypackage.slow_module:*

# Wildcard module matching
transformers.*:*Attention*
```

## How It Works

Speed Bump uses Python 3.12's PEP 669 (`sys.monitoring`) to register low-overhead callbacks on function calls. When a matching function is called during the active time window, Speed Bump executes a spin-delay loop to introduce the configured latency.

Key design decisions:
- **Spin delay, not sleep**: Delays hold the CPU (and GIL) to accurately simulate slower Python code
- **Clock calibration**: Measures `clock_gettime` overhead at startup to ensure accurate delays
- **Minimal overhead**: PEP 669 allows per-code-object monitoring, so non-matching functions have zero overhead

## Documentation

- **[Methodology Guide](docs/methodology.md)**: The systematic approach to finding Python bottlenecks
- **[Pattern Reference](docs/patterns.md)**: How to write target patterns for different frameworks

## API

```python
import speed_bump

# Calibration results
speed_bump.clock_overhead_ns  # Measured clock_gettime overhead
speed_bump.min_delay_ns       # Minimum achievable delay (2x overhead)

# Low-level delay function (for testing)
speed_bump.spin_delay_ns(1000)  # Spin for 1µs
```

## Development

```bash
git clone https://github.com/SonicField/speed-bump.git
cd speed-bump
pip install -e .[dev]
pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for more details.

## Licence

MIT. See [LICENSE](LICENSE).

## Status

v0.1.0 - Initial release. Core functionality complete:
- [x] Clock calibration
- [x] Spin delay (C extension)
- [x] Target pattern parsing (glob-based)
- [x] PEP 669 monitoring integration
- [x] Timing window control (start delay, duration)
- [x] Frequency control (every Nth call)
- [ ] Statistics collection
