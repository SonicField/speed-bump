"""Target pattern parsing and matching.

Target files contain glob patterns for matching Python code objects.
Format: one pattern per line, comments start with #.

Pattern format: module_glob:qualified_name_glob

Examples:
    # Match all methods of LlamaAttention class
    transformers.modeling_llama:LlamaAttention.*

    # Match specific function
    vllm.worker.model_runner:ModelRunner.execute_model

    # Match everything in a module
    mypackage.slow_module:*
"""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class TargetPattern:
    """A compiled target pattern for matching code objects."""

    module_pattern: str
    name_pattern: str
    original: str

    def matches(self, module_name: str, qualified_name: str) -> bool:
        """Check if this pattern matches the given code object.

        Args:
            module_name: The __module__ of the code object (e.g., "transformers.modeling_llama")
            qualified_name: The __qualname__ of the code object (e.g., "LlamaAttention.forward")

        Returns:
            True if both module and name patterns match.
        """
        return fnmatch.fnmatch(module_name, self.module_pattern) and fnmatch.fnmatch(
            qualified_name, self.name_pattern
        )


class PatternError(Exception):
    """Error in pattern syntax or file format."""


def parse_pattern(line: str, line_number: int) -> TargetPattern:
    """Parse a single pattern line.

    Args:
        line: The pattern line (already stripped of whitespace).
        line_number: Line number for error messages.

    Returns:
        A compiled TargetPattern.

    Raises:
        PatternError: If the pattern syntax is invalid.
    """
    if ":" not in line:
        raise PatternError(
            f"Line {line_number}: Invalid pattern '{line}' - missing ':' separator. "
            f"Expected format: module_glob:name_glob"
        )

    parts = line.split(":", 1)
    module_pattern = parts[0].strip()
    name_pattern = parts[1].strip()

    if not module_pattern:
        raise PatternError(f"Line {line_number}: Empty module pattern in '{line}'")
    if not name_pattern:
        raise PatternError(f"Line {line_number}: Empty name pattern in '{line}'")

    return TargetPattern(
        module_pattern=module_pattern,
        name_pattern=name_pattern,
        original=line,
    )


def load_targets(path: str | os.PathLike[str]) -> list[TargetPattern]:
    """Load target patterns from a file.

    Args:
        path: Path to the targets file.

    Returns:
        List of compiled TargetPattern objects.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        PatternError: If any pattern is invalid.
    """
    path = Path(path)
    patterns: list[TargetPattern] = []

    with path.open() as f:
        for line_number, line in enumerate(f, start=1):
            # Strip whitespace
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            patterns.append(parse_pattern(line, line_number))

    return patterns


def matches_any(patterns: list[TargetPattern], module_name: str, qualified_name: str) -> bool:
    """Check if any pattern matches the given code object.

    Args:
        patterns: List of patterns to check.
        module_name: The __module__ of the code object.
        qualified_name: The __qualname__ of the code object.

    Returns:
        True if any pattern matches.
    """
    return any(p.matches(module_name, qualified_name) for p in patterns)
