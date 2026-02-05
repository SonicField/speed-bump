"""Native C function probing via kernel module uprobes.

This module provides a Python API to control the speed-bump kernel module's
native uprobe functionality with per-process filtering.

The kernel module must be loaded and the sysfs interface must be available
at /sys/kernel/speed_bump/targets for this module to work.

Example:
    >>> from speed_bump import native
    >>>
    >>> # Probe PyObject_GetAttr for this process + children
    >>> with native.probe("/path/to/python3", "PyObject_GetAttr", delay_ns=1000):
    ...     # Run benchmark - only this process tree is affected
    ...     run_benchmark()
"""

import os
import contextlib
from typing import Optional, Generator

SYSFS_TARGETS = "/sys/kernel/speed_bump/targets"


def _write_target(spec: str) -> None:
    """Write a target specification to the kernel module.

    Args:
        spec: The target specification string to write.

    Raises:
        OSError: If the sysfs interface is not available or write fails.
    """
    with open(SYSFS_TARGETS, "w") as f:
        f.write(spec)


def add_probe(
    binary_path: str,
    symbol: str,
    delay_ns: int = 0,
    pid: Optional[int] = None,
) -> None:
    """Add a probe for a native function.

    Args:
        binary_path: Path to the binary containing the symbol.
        symbol: The symbol name to probe.
        delay_ns: Delay in nanoseconds to inject (default: 0).
        pid: Process ID to filter (default: current process).

    Raises:
        OSError: If the sysfs interface is not available or write fails.
    """
    if pid is None:
        pid = os.getpid()
    spec = f"+{binary_path}:{symbol} {delay_ns} pid={pid}"
    _write_target(spec)


def remove_probe(binary_path: str, symbol: str) -> None:
    """Remove a probe for a native function.

    Args:
        binary_path: Path to the binary containing the symbol.
        symbol: The symbol name to remove.

    Raises:
        OSError: If the sysfs interface is not available or write fails.
    """
    spec = f"-{binary_path}:{symbol}"
    _write_target(spec)


@contextlib.contextmanager
def probe(
    binary_path: str,
    symbol: str,
    delay_ns: int = 0,
    pid: Optional[int] = None,
) -> Generator[None, None, None]:
    """Context manager for scoped native probing.

    Adds a probe on entry and removes it on exit, ensuring cleanup
    even if an exception occurs.

    Args:
        binary_path: Path to the binary containing the symbol.
        symbol: The symbol name to probe.
        delay_ns: Delay in nanoseconds to inject (default: 0).
        pid: Process ID to filter (default: current process).

    Yields:
        None

    Example:
        >>> with native.probe("/usr/bin/python3", "PyObject_GetAttr", delay_ns=1000):
        ...     # Code here runs with the probe active
        ...     pass
    """
    add_probe(binary_path, symbol, delay_ns, pid)
    try:
        yield
    finally:
        remove_probe(binary_path, symbol)


def is_available() -> bool:
    """Check if the kernel module sysfs interface is available.

    Returns:
        True if the sysfs interface exists and is writable.
    """
    return os.path.exists(SYSFS_TARGETS) and os.access(SYSFS_TARGETS, os.W_OK)


def format_add_spec(
    binary_path: str,
    symbol: str,
    delay_ns: int = 0,
    pid: Optional[int] = None,
) -> str:
    """Format an add probe specification string.

    Useful for testing or debugging without writing to sysfs.

    Args:
        binary_path: Path to the binary containing the symbol.
        symbol: The symbol name to probe.
        delay_ns: Delay in nanoseconds to inject (default: 0).
        pid: Process ID to filter (default: current process).

    Returns:
        The formatted specification string.
    """
    if pid is None:
        pid = os.getpid()
    return f"+{binary_path}:{symbol} {delay_ns} pid={pid}"


def format_remove_spec(binary_path: str, symbol: str) -> str:
    """Format a remove probe specification string.

    Useful for testing or debugging without writing to sysfs.

    Args:
        binary_path: Path to the binary containing the symbol.
        symbol: The symbol name to remove.

    Returns:
        The formatted specification string.
    """
    return f"-{binary_path}:{symbol}"
