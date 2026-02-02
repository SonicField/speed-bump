"""Monitoring integration for selective slowdown.

This module provides function call monitoring with delays for matching targets.
It automatically selects the appropriate backend based on Python version:
- Python 3.12+: Uses PEP 669 (sys.monitoring)
- Python 3.10-3.11: Uses sys.setprofile via C extension
"""

from __future__ import annotations

import sys
import threading
from typing import TYPE_CHECKING

from speed_bump._config import Config

if TYPE_CHECKING:
    from types import CodeType

# Version detection: PEP 669 requires Python 3.12+
_USE_PEP669 = sys.version_info >= (3, 12)


# ============================================================================
# Shared State
# ============================================================================

# Global state (used by both backends)
_config: Config | None = None


# ============================================================================
# PEP 669 Backend (Python 3.12+)
# ============================================================================

if _USE_PEP669:
    import time

    from speed_bump._core import spin_delay_ns
    from speed_bump._patterns import matches_any

    # Tool ID for speed_bump monitoring (use 3 as a mid-range ID)
    TOOL_ID = 3

    # Cache for code object match results: code_id -> (matches, qualified_name)
    # Using id() as key since code objects are long-lived
    _match_cache: dict[int, bool] = {}
    _cache_lock = threading.Lock()

    # Thread-local storage for call counters
    # Key is code object id, value is call count
    _call_counters: threading.local = threading.local()

    # PEP 669 enabled flag
    _pep669_enabled: bool = False

    def _get_counter_dict() -> dict[int, int]:
        """Get the thread-local counter dictionary."""
        if not hasattr(_call_counters, "counters"):
            _call_counters.counters = {}
        return _call_counters.counters

    def _get_code_qualified_name(code: CodeType) -> str:
        """Extract the qualified name from a code object.

        Returns the qualname from the code object. For methods, this includes
        the class name (e.g., "MyClass.method"). For nested functions, this
        includes the outer function names.
        """
        return code.co_qualname

    def _check_match(code: CodeType, config: Config) -> bool:
        """Check if a code object matches any target pattern.

        Results are cached per code object to avoid repeated matching.
        """
        code_id = id(code)

        # Fast path: check cache without lock
        if code_id in _match_cache:
            return _match_cache[code_id]

        # Slow path: compute match and cache
        with _cache_lock:
            # Double-check after acquiring lock
            if code_id in _match_cache:
                return _match_cache[code_id]

            # Get module and qualified name
            module = code.co_filename
            # Try to extract module name from code object
            # co_filename is the file path, but we want the module name
            # For matching, we use the filename (allows glob on paths)
            qualified_name = _get_code_qualified_name(code)

            result = matches_any(config.targets, module, qualified_name)
            _match_cache[code_id] = result
            return result

    def _call_handler(code: CodeType, instruction_offset: int) -> object:
        """Callback for PY_START events (function call start).

        This is invoked by sys.monitoring when a function call begins.
        We check if the code object matches our patterns and apply delay
        if within the timing window and frequency threshold.

        Args:
            code: The code object of the function being called.
            instruction_offset: Byte offset of the instruction (unused).

        Returns:
            sys.monitoring.DISABLE to disable monitoring for this code object
            if it doesn't match our patterns. None otherwise.
        """
        global _config

        if _config is None or not _config.enabled:
            return sys.monitoring.DISABLE

        # Check if code object matches patterns (cached)
        if not _check_match(code, _config):
            # Disable monitoring for this code object - it will never match
            return sys.monitoring.DISABLE

        # Check timing window
        now_ns = time.time_ns()
        if not _config.is_in_window(now_ns):
            # Outside timing window, skip delay but don't disable
            # (we might enter the window later)
            return None

        # Handle frequency: only delay every Nth call
        if _config.frequency > 1:
            counters = _get_counter_dict()
            code_id = id(code)
            count = counters.get(code_id, 0) + 1
            counters[code_id] = count

            if count % _config.frequency != 0:
                # Not the Nth call, skip delay
                return None

        # Apply delay
        spin_delay_ns(_config.delay_ns)
        return None

    def install(config: Config) -> bool:
        """Install speed_bump monitoring with the given configuration.

        Args:
            config: The parsed configuration.

        Returns:
            True if monitoring was installed, False if disabled or error.
        """
        global _config, _pep669_enabled

        if not config.enabled:
            return False

        if not config.targets:
            return False

        _config = config

        try:
            # Register our tool
            sys.monitoring.use_tool_id(TOOL_ID, "speed_bump")

            # Register callback for PY_START events (function call start)
            sys.monitoring.register_callback(
                TOOL_ID,
                sys.monitoring.events.PY_START,
                _call_handler,
            )

            # Enable PY_START events globally
            sys.monitoring.set_events(TOOL_ID, sys.monitoring.events.PY_START)

            _pep669_enabled = True
            return True

        except Exception as e:
            print(f"speed_bump: ERROR: Failed to install monitoring: {e}", file=sys.stderr)
            return False

    def uninstall() -> None:
        """Uninstall speed_bump monitoring."""
        global _config, _pep669_enabled

        if not _pep669_enabled:
            return

        try:
            # Disable events
            sys.monitoring.set_events(TOOL_ID, 0)

            # Unregister callback
            sys.monitoring.register_callback(
                TOOL_ID,
                sys.monitoring.events.PY_START,
                None,
            )

            # Free tool ID
            sys.monitoring.free_tool_id(TOOL_ID)

        except Exception:
            pass  # Best effort cleanup

        _pep669_enabled = False
        _config = None

    def is_installed() -> bool:
        """Check if speed_bump monitoring is installed."""
        return _pep669_enabled

    def clear_cache() -> None:
        """Clear the match cache. Useful for testing."""
        global _match_cache
        with _cache_lock:
            _match_cache.clear()


# ============================================================================
# setprofile Backend (Python 3.10-3.11)
# ============================================================================

else:
    # Import the C extension for setprofile-based monitoring
    from speed_bump._setprofile import (
        install_setprofile,
        is_installed_setprofile,
        uninstall_setprofile,
    )

    def install(config: Config) -> bool:
        """Install speed_bump monitoring with the given configuration.

        Args:
            config: The parsed configuration.

        Returns:
            True if monitoring was installed, False if disabled or error.
        """
        global _config

        if not config.enabled:
            return False

        if not config.targets:
            return False

        _config = config

        # Convert Config to dict for C extension
        config_dict = {
            'targets': list(config.targets),
            'delay_ns': config.delay_ns,
            'frequency': config.frequency,
            'start_ns': config.start_ns,
            'end_ns': config.end_ns if config.end_ns is not None else 0,
        }

        try:
            install_setprofile(config_dict)
            return True
        except Exception as e:
            print(f"speed_bump: ERROR: Failed to install monitoring: {e}", file=sys.stderr)
            return False

    def uninstall() -> None:
        """Uninstall speed_bump monitoring."""
        global _config
        uninstall_setprofile()
        _config = None

    def is_installed() -> bool:
        """Check if speed_bump monitoring is installed."""
        return is_installed_setprofile()

    def clear_cache() -> None:
        """Clear the match cache.

        For setprofile backend, the cache is stored in code objects'
        co_extra and cannot easily be cleared. This is a no-op.
        """
        pass


# ============================================================================
# Common API
# ============================================================================

def get_config() -> Config | None:
    """Get the current configuration. Useful for testing."""
    return _config
