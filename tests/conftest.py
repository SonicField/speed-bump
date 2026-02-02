"""Pytest configuration and fixtures for speed-bump tests."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    pass


# =============================================================================
# Free-Threaded Python Detection
# =============================================================================


def is_free_threaded() -> bool:
    """Return True if running on free-threaded Python (no GIL)."""
    return hasattr(sys, "_is_gil_enabled") and not sys._is_gil_enabled()


def is_gil_python() -> bool:
    """Return True if running on GIL Python."""
    return not hasattr(sys, "_is_gil_enabled") or sys._is_gil_enabled()


# Skip markers for conditional tests
requires_ftp = pytest.mark.skipif(
    is_gil_python(), reason="Requires free-threaded Python (--disable-gil)"
)

requires_gil = pytest.mark.skipif(is_free_threaded(), reason="Requires GIL Python")

requires_gil_detection = pytest.mark.skipif(
    not hasattr(sys, "_is_gil_enabled"), reason="Requires Python 3.13+ with sys._is_gil_enabled()"
)


@pytest.fixture
def runtime_info() -> dict:
    """Return information about the Python runtime."""
    return {
        "version": sys.version,
        "has_gil_api": hasattr(sys, "_is_gil_enabled"),
        "gil_enabled": sys._is_gil_enabled() if hasattr(sys, "_is_gil_enabled") else True,
        "is_free_threaded": is_free_threaded(),
    }


@pytest.fixture
def target_file(tmp_path: Path) -> Path:
    """Create a temporary target file path."""
    return tmp_path / "targets.txt"


@pytest.fixture
def sample_targets(target_file: Path) -> Path:
    """Create a target file with sample patterns."""
    target_file.write_text(
        """\
# Sample target patterns for testing
# This is a comment

transformers.modeling_llama:LlamaAttention.*
transformers.modeling_llama:LlamaMLP.forward
vllm.worker.*:*

# Another comment
mypackage.module:MyClass.method
"""
    )
    return target_file


@pytest.fixture
def empty_target_file(target_file: Path) -> Path:
    """Create an empty target file."""
    target_file.write_text("")
    return target_file


@pytest.fixture
def comments_only_file(target_file: Path) -> Path:
    """Create a target file with only comments and blank lines."""
    target_file.write_text(
        """\
# This file has no actual patterns
# Just comments

# And blank lines
"""
    )
    return target_file
