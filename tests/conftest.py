"""Pytest configuration and fixtures for speed-bump tests."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator


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
