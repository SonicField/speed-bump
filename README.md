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

**Manual build (without pip/setuptools):**

If pip or setuptools are unavailable, build the C extension directly:
```bash
cd speed-bump
PYTHON_INCLUDES=$(python3 -c 'import sysconfig; print(sysconfig.get_config_var("INCLUDEPY"))')
EXT_SUFFIX=$(python3 -c 'import sysconfig; print(sysconfig.get_config_var("EXT_SUFFIX"))')

# Core extension (required for all Python versions)
gcc -shared -fPIC -I"$PYTHON_INCLUDES" -O3 -Wall -std=c11 -D_GNU_SOURCE \
    src/speed_bump/_core.c -o src/speed_bump/_core$EXT_SUFFIX

# Setprofile extension (required for Python 3.10-3.11)
gcc -shared -fPIC -I"$PYTHON_INCLUDES" -O3 -Wall -std=c11 -D_GNU_SOURCE \
    src/speed_bump/_setprofile.c -o src/speed_bump/_setprofile$EXT_SUFFIX

# Then add src/ to PYTHONPATH
export PYTHONPATH=$PWD/src:$PYTHONPATH
python3 -c "import speed_bump; print(speed_bump.clock_overhead_ns)"
```

**Requirements:**
- Linux (x86_64 or aarch64)
- Python 3.10+

## Python Version Support

Speed Bump supports Python 3.10 and later with different backends:

| Python Version | Backend | Notes |
|----------------|---------|-------|
| 3.12+ | PEP 669 (`sys.monitoring`) | Full feature support |
| 3.10-3.11 | `sys.setprofile` (C extension) | `clear_cache()` is a no-op |

**Python 3.10-3.11 Limitations:**
- The match cache is stored in code objects' `co_extra` field and cannot be cleared
- `clear_cache()` has no effect - cache persists for the lifetime of the process
- Qualified name construction is approximate (uses first argument type for methods)
- Use a fresh Python process if you need to change target patterns

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

Speed Bump uses Python's monitoring capabilities to register low-overhead callbacks on function calls:

- **Python 3.12+**: Uses PEP 669 (`sys.monitoring`) for per-code-object monitoring with zero overhead for non-matching functions
- **Python 3.10-3.11**: Uses `sys.setprofile` via a C extension, with match results cached in code objects

When a matching function is called during the active time window, Speed Bump executes a spin-delay loop to introduce the configured latency.

Key design decisions:
- **Spin delay, not sleep**: Delays hold the CPU (and GIL) to accurately simulate slower Python code
- **Clock calibration**: Measures `clock_gettime` overhead at startup to ensure accurate delays
- **Per-code caching**: Match results are cached per code object to minimise overhead

## Limitations

Speed Bump has fundamental constraints to be aware of:

### Only Interpreted Python

Speed Bump's Python monitoring can only slow down Python code that runs through the interpreter. C extensions, NumPy ufuncs, and other native code execute outside Python's monitoring system.

**For native code**, use the `speed_bump.native` module (see [Native Code Probing](#native-code-probing) below), which uses kernel uprobes to inject delays into compiled binaries.

### GIL Holding

The spin delay holds the GIL while waiting. This accurately simulates slower Python code (which would also hold the GIL), but means:
- Other Python threads are blocked during the delay
- In multi-threaded applications, interpret results carefully

### Free-Threaded Python (PEP 703)

**Verified with Python 3.14 free-threaded build (2026-02-01).**

Speed Bump works correctly with free-threaded Python (`--disable-gil` builds):

- The C extension declares `Py_mod_gil = Py_MOD_GIL_NOT_USED`, so it runs without re-enabling the GIL
- Each thread receives accurate per-thread delays
- The spin_delay_ns function is thread-safe
- Parallel execution completes in constant wall-clock time regardless of thread count

**Test Results** (Python 3.14.0 FTP build, LTO):
- Runtime detection: PASS (correctly identifies FTP vs GIL)
- Per-thread delay accuracy: PASS (each thread gets correct delay)
- Parallel performance: PASS (N threads complete in ~1× delay time, not N×)
- Cache thread safety: PASS

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

## Native Code Probing

The `speed_bump.native` module provides uprobe-based delays for native C functions, allowing you to measure sensitivity of compiled code (C extensions, CPython internals, system libraries).

**Requirements:**
- Linux with kernel uprobe support
- The `speed-bump-native-kmod` kernel module loaded
- Root privileges (or appropriate capabilities) for writing to sysfs

### Basic Usage

```python
from speed_bump import native

# Probe a CPython internal function for this process and its children
with native.probe("/usr/bin/python3", "PyObject_GetAttr", delay_ns=1000):
    run_benchmark()  # Only this process tree is affected
```

### API

```python
from speed_bump import native

# Check if kernel module is available
if native.is_available():
    # Context manager for scoped probing
    with native.probe(binary_path, symbol, delay_ns=1000, pid=None):
        # pid defaults to current process (os.getpid())
        # Probe is automatically removed on exit
        pass

    # Manual control
    native.add_probe("/path/to/binary", "function_name", delay_ns=5000)
    native.remove_probe("/path/to/binary", "function_name")
```

### How It Works

The native module writes to `/sys/kernel/speed_bump/targets` to configure the kernel module:
- Add probe: `+/path/to/binary:symbol delay_ns pid=N`
- Remove probe: `-/path/to/binary:symbol`

The kernel module uses uprobes to inject delays when the specified function is called. PID filtering ensures only the specified process and its descendants are affected.

### Finding Symbols

Use standard tools to find symbols in binaries:

```bash
# List symbols in Python
nm -D /usr/bin/python3 | grep PyObject

# List symbols in a shared library
nm -D /usr/lib/libcuda.so | grep cudaLaunch
```

### Kernel Module

The kernel module source is available at `speed-bump-native-kmod`. See that repository's README for building and loading instructions.

## Development

```bash
git clone https://github.com/SonicField/speed-bump.git
cd speed-bump
pip install -e .[dev]
pytest
```

For C-level sanitiser tests (ThreadSanitizer, AddressSanitizer), see [docs/testing.md](docs/testing.md).

See [CONTRIBUTING.md](CONTRIBUTING.md) for more details.

## Licence

MIT. See [LICENSE](LICENSE).

## Status

v0.1.0 - Core functionality complete:
- [x] Clock calibration
- [x] Spin delay (C extension)
- [x] Target pattern parsing (glob-based)
- [x] PEP 669 monitoring integration
- [x] Python 3.10+ support via sys.setprofile backend
- [x] Timing window control (start delay, duration)
- [x] Frequency control (every Nth call)
- [x] Native code probing via kernel uprobes
- [ ] Statistics collection

<!--
NBS NOTE (2026-02-01): We don't know what "Statistics collection" should actually collect.
This TODO predates epistemic discipline. Before implementing, run an /nbs-investigation
to determine: What metrics matter? Per-function call counts? Delay distribution?
Integration with external tools? Don't implement without clear requirements.
-->
