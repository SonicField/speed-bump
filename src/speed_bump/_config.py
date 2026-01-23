"""Configuration parsing from environment variables.

Environment Variables:
    SPEED_BUMP_TARGETS: Path to file containing target patterns (required to enable)
    SPEED_BUMP_DELAY_NS: Delay in nanoseconds per trigger (default: 1000)
    SPEED_BUMP_FREQUENCY: Trigger every Nth matching call (default: 1)
    SPEED_BUMP_START_MS: Milliseconds after process start before enabling (default: 0)
    SPEED_BUMP_DURATION_MS: Duration in milliseconds, 0 = indefinite (default: 0)
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from speed_bump._core import get_min_delay_ns
from speed_bump._patterns import TargetPattern, load_targets

if TYPE_CHECKING:
    pass


# Process start time in nanoseconds (monotonic clock approximation via time.time_ns)
# We use time.time_ns at import because time.monotonic_ns doesn't have a defined epoch
_PROCESS_START_NS: int = time.time_ns()


@dataclass(frozen=True, slots=True)
class Config:
    """Speed Bump configuration."""

    enabled: bool
    """Whether speed bump is enabled (targets file was specified and loaded)."""

    targets: tuple[TargetPattern, ...]
    """Compiled target patterns."""

    delay_ns: int
    """Delay in nanoseconds per trigger."""

    frequency: int
    """Trigger every Nth matching call."""

    start_ns: int
    """Absolute time (time.time_ns) when slowdown should start."""

    end_ns: int | None
    """Absolute time (time.time_ns) when slowdown should end, or None for indefinite."""

    def is_in_window(self, now_ns: int | None = None) -> bool:
        """Check if the current time is within the active window.

        Args:
            now_ns: Current time from time.time_ns(). If None, calls time.time_ns().

        Returns:
            True if slowdown should be active.
        """
        if not self.enabled:
            return False

        if now_ns is None:
            now_ns = time.time_ns()

        if now_ns < self.start_ns:
            return False

        if self.end_ns is not None and now_ns >= self.end_ns:
            return False

        return True


class ConfigError(Exception):
    """Error in configuration."""


def _parse_int(name: str, default: int, min_value: int = 0) -> int:
    """Parse an integer environment variable.

    Args:
        name: Environment variable name.
        default: Default value if not set.
        min_value: Minimum allowed value.

    Returns:
        The parsed integer.

    Raises:
        ConfigError: If the value is invalid.
    """
    value_str = os.environ.get(name)
    if value_str is None:
        return default

    try:
        value = int(value_str)
    except ValueError:
        raise ConfigError(f"{name}: invalid integer '{value_str}'") from None

    if value < min_value:
        raise ConfigError(f"{name}: value {value} is below minimum {min_value}")

    return value


def load_config() -> Config:
    """Load configuration from environment variables.

    Returns:
        A Config object with the parsed configuration.

    Raises:
        ConfigError: If configuration is invalid.
    """
    # Check if targets file is specified
    targets_path = os.environ.get("SPEED_BUMP_TARGETS")

    if not targets_path:
        # Speed bump is disabled
        return Config(
            enabled=False,
            targets=(),
            delay_ns=0,
            frequency=1,
            start_ns=0,
            end_ns=None,
        )

    # Load targets
    path = Path(targets_path)
    if not path.exists():
        raise ConfigError(f"SPEED_BUMP_TARGETS: file not found: {targets_path}")

    try:
        targets = load_targets(path)
    except Exception as e:
        raise ConfigError(f"SPEED_BUMP_TARGETS: {e}") from None

    if not targets:
        _warn(f"SPEED_BUMP_TARGETS: no patterns found in {targets_path}")
        return Config(
            enabled=False,
            targets=(),
            delay_ns=0,
            frequency=1,
            start_ns=0,
            end_ns=None,
        )

    # Parse other settings
    delay_ns = _parse_int("SPEED_BUMP_DELAY_NS", default=1000, min_value=0)
    frequency = _parse_int("SPEED_BUMP_FREQUENCY", default=1, min_value=1)
    start_ms = _parse_int("SPEED_BUMP_START_MS", default=0, min_value=0)
    duration_ms = _parse_int("SPEED_BUMP_DURATION_MS", default=0, min_value=0)

    # Validate delay against minimum
    min_delay = get_min_delay_ns()
    if delay_ns < min_delay:
        _warn(
            f"SPEED_BUMP_DELAY_NS: requested delay {delay_ns} ns < minimum {min_delay} ns\n"
            f"  Clamping to minimum. For smaller effective delays, increase SPEED_BUMP_FREQUENCY."
        )
        delay_ns = min_delay

    # Calculate absolute times
    start_ns = _PROCESS_START_NS + (start_ms * 1_000_000)

    if duration_ms > 0:
        end_ns: int | None = start_ns + (duration_ms * 1_000_000)
    else:
        end_ns = None

    config = Config(
        enabled=True,
        targets=tuple(targets),
        delay_ns=delay_ns,
        frequency=frequency,
        start_ns=start_ns,
        end_ns=end_ns,
    )

    # Report configuration
    _report_config(config, targets_path)

    return config


def _warn(message: str) -> None:
    """Print a warning to stderr."""
    print(f"speed_bump: WARNING: {message}", file=sys.stderr)


def _report_config(config: Config, targets_path: str) -> None:
    """Print configuration summary to stderr."""
    print(f"speed_bump: targets loaded: {len(config.targets)} patterns from {targets_path}",
          file=sys.stderr)
    print(f"speed_bump: delay: {config.delay_ns} ns, frequency: {config.frequency}",
          file=sys.stderr)

    if config.start_ns > _PROCESS_START_NS:
        start_offset_ms = (config.start_ns - _PROCESS_START_NS) // 1_000_000
        print(f"speed_bump: start delay: {start_offset_ms} ms", file=sys.stderr)

    if config.end_ns is not None:
        duration_ms = (config.end_ns - config.start_ns) // 1_000_000
        print(f"speed_bump: duration: {duration_ms} ms", file=sys.stderr)
    else:
        print("speed_bump: duration: indefinite", file=sys.stderr)
