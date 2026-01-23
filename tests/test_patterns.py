"""Tests for target pattern parsing and matching."""

from __future__ import annotations

from pathlib import Path

import pytest

from speed_bump._patterns import (
    PatternError,
    TargetPattern,
    load_targets,
    matches_any,
    parse_pattern,
)


class TestParsePattern:
    """Tests for parse_pattern function."""

    def test_valid_pattern(self) -> None:
        """Valid pattern parses correctly."""
        pattern = parse_pattern("module.name:Class.method", 1)
        assert pattern.module_pattern == "module.name"
        assert pattern.name_pattern == "Class.method"
        assert pattern.original == "module.name:Class.method"

    def test_pattern_with_globs(self) -> None:
        """Glob patterns are preserved."""
        pattern = parse_pattern("transformers.*:LlamaAttention.*", 1)
        assert pattern.module_pattern == "transformers.*"
        assert pattern.name_pattern == "LlamaAttention.*"

    def test_pattern_with_whitespace(self) -> None:
        """Whitespace around colon is stripped."""
        pattern = parse_pattern("module : name", 1)
        assert pattern.module_pattern == "module"
        assert pattern.name_pattern == "name"

    def test_missing_colon_raises(self) -> None:
        """Pattern without colon raises PatternError."""
        with pytest.raises(PatternError) as exc_info:
            parse_pattern("no_colon_here", 5)
        assert "Line 5" in str(exc_info.value)
        assert "missing ':'" in str(exc_info.value)

    def test_empty_module_raises(self) -> None:
        """Empty module pattern raises PatternError."""
        with pytest.raises(PatternError) as exc_info:
            parse_pattern(":name", 3)
        assert "Line 3" in str(exc_info.value)
        assert "Empty module" in str(exc_info.value)

    def test_empty_name_raises(self) -> None:
        """Empty name pattern raises PatternError."""
        with pytest.raises(PatternError) as exc_info:
            parse_pattern("module:", 7)
        assert "Line 7" in str(exc_info.value)
        assert "Empty name" in str(exc_info.value)


class TestTargetPatternMatching:
    """Tests for TargetPattern.matches method."""

    def test_exact_match(self) -> None:
        """Exact patterns match exactly."""
        pattern = TargetPattern("mymodule", "MyClass.method", "mymodule:MyClass.method")
        assert pattern.matches("mymodule", "MyClass.method") is True
        assert pattern.matches("mymodule", "MyClass.other") is False
        assert pattern.matches("other", "MyClass.method") is False

    def test_wildcard_name(self) -> None:
        """Wildcard in name pattern matches any name."""
        pattern = TargetPattern("mymodule", "*", "mymodule:*")
        assert pattern.matches("mymodule", "anything") is True
        assert pattern.matches("mymodule", "Class.method") is True
        assert pattern.matches("other", "anything") is False

    def test_wildcard_module(self) -> None:
        """Wildcard in module pattern matches any module."""
        pattern = TargetPattern("*", "func", "*:func")
        assert pattern.matches("anymodule", "func") is True
        assert pattern.matches("deep.nested.module", "func") is True
        assert pattern.matches("anymodule", "other") is False

    def test_glob_star_pattern(self) -> None:
        """Star glob matches partial strings."""
        pattern = TargetPattern("transformers.*", "Llama*", "transformers.*:Llama*")
        assert pattern.matches("transformers.modeling_llama", "LlamaAttention") is True
        assert pattern.matches("transformers.modeling_llama", "LlamaMLP") is True
        assert pattern.matches("transformers.tokenization", "LlamaTokenizer") is True
        assert pattern.matches("transformers.modeling_llama", "BertAttention") is False
        assert pattern.matches("torch.nn", "LlamaAttention") is False

    def test_question_mark_glob(self) -> None:
        """Question mark matches single character."""
        pattern = TargetPattern("mod?le", "func", "mod?le:func")
        assert pattern.matches("module", "func") is True
        assert pattern.matches("modele", "func") is True
        assert pattern.matches("modle", "func") is False


class TestLoadTargets:
    """Tests for load_targets function."""

    def test_load_sample_targets(self, sample_targets: Path) -> None:
        """Sample targets file loads correctly."""
        patterns = load_targets(sample_targets)
        assert len(patterns) == 4

        # Check first pattern
        assert patterns[0].module_pattern == "transformers.modeling_llama"
        assert patterns[0].name_pattern == "LlamaAttention.*"

    def test_load_empty_file(self, empty_target_file: Path) -> None:
        """Empty file returns empty list."""
        patterns = load_targets(empty_target_file)
        assert patterns == []

    def test_load_comments_only(self, comments_only_file: Path) -> None:
        """File with only comments returns empty list."""
        patterns = load_targets(comments_only_file)
        assert patterns == []

    def test_file_not_found(self, tmp_path: Path) -> None:
        """Missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_targets(tmp_path / "nonexistent.txt")

    def test_invalid_pattern_in_file(self, target_file: Path) -> None:
        """Invalid pattern in file raises PatternError with line number."""
        target_file.write_text(
            """\
valid.pattern:name
invalid_no_colon
another.valid:pattern
"""
        )
        with pytest.raises(PatternError) as exc_info:
            load_targets(target_file)
        assert "Line 2" in str(exc_info.value)


class TestMatchesAny:
    """Tests for matches_any function."""

    def test_matches_first_pattern(self) -> None:
        """First matching pattern triggers match."""
        patterns = [
            TargetPattern("module1", "func1", "module1:func1"),
            TargetPattern("module2", "func2", "module2:func2"),
        ]
        assert matches_any(patterns, "module1", "func1") is True

    def test_matches_last_pattern(self) -> None:
        """Last matching pattern triggers match."""
        patterns = [
            TargetPattern("module1", "func1", "module1:func1"),
            TargetPattern("module2", "func2", "module2:func2"),
        ]
        assert matches_any(patterns, "module2", "func2") is True

    def test_no_match(self) -> None:
        """No matching pattern returns False."""
        patterns = [
            TargetPattern("module1", "func1", "module1:func1"),
            TargetPattern("module2", "func2", "module2:func2"),
        ]
        assert matches_any(patterns, "module3", "func3") is False

    def test_empty_patterns(self) -> None:
        """Empty pattern list returns False."""
        assert matches_any([], "module", "func") is False
