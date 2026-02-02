"""Speed Bump: Selective Python slowdown profiler for throughput analysis.

Speed Bump introduces controlled, selective delays into Python code execution.
By slowing specific modules/functions and measuring throughput impact, you can
identify which Python code paths actually matter to overall system performance.

This is particularly useful for AI/ML workloads where traditional profiling
misses the subtle interactions between Python and GPU execution.

Environment Variables:
    SPEED_BUMP_TARGETS: Path to file containing target patterns (one per line)
    SPEED_BUMP_DELAY_NS: Delay in nanoseconds per trigger (default: 1000)
    SPEED_BUMP_FREQUENCY: Trigger every Nth matching call (default: 1)
    SPEED_BUMP_START_MS: Milliseconds after process start before enabling
    SPEED_BUMP_DURATION_MS: Duration in milliseconds (0 = indefinite)

Example:
    >>> import speed_bump
    >>> speed_bump.clock_overhead_ns
    24
    >>> speed_bump.min_delay_ns
    48
"""

from speed_bump._config import Config, ConfigError, load_config
from speed_bump._core import (
    get_clock_overhead_ns,
    get_min_delay_ns,
    is_calibrated,
    spin_delay_ns,
)
from speed_bump._monitoring import (
    clear_cache,
    get_config,
    install,
    is_installed,
    uninstall,
)

__version__ = "0.1.0"
__all__ = [
    # Config
    "Config",
    "ConfigError",
    "clear_cache",
    # Calibration
    "clock_overhead_ns",
    "get_clock_overhead_ns",
    "get_config",
    "get_min_delay_ns",
    # Monitoring
    "install",
    "is_calibrated",
    "is_installed",
    "load_config",
    "min_delay_ns",
    # Delay
    "spin_delay_ns",
    "uninstall",
]

# Expose calibrated values as module attributes for convenience
clock_overhead_ns: int = get_clock_overhead_ns()
min_delay_ns: int = get_min_delay_ns()
