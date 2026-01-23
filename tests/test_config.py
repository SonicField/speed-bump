"""Tests for environment variable configuration parsing."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import TYPE_CHECKING
from unittest import mock

import pytest

from speed_bump._config import Config, ConfigError, _PROCESS_START_NS, load_config

if TYPE_CHECKING:
    pass


class TestConfigDisabled:
    """Tests for disabled configuration (no SPEED_BUMP_TARGETS)."""

    def test_no_targets_means_disabled(self) -> None:
        """Config is disabled when SPEED_BUMP_TARGETS is not set."""
        with mock.patch.dict(os.environ, {}, clear=True):
            config = load_config()
        assert config.enabled is False
        assert config.targets == ()

    def test_empty_targets_means_disabled(self) -> None:
        """Config is disabled when SPEED_BUMP_TARGETS is empty string."""
        with mock.patch.dict(os.environ, {"SPEED_BUMP_TARGETS": ""}, clear=True):
            config = load_config()
        assert config.enabled is False


class TestConfigEnabled:
    """Tests for enabled configuration."""

    def test_valid_config(self, sample_targets: Path) -> None:
        """Valid configuration loads successfully."""
        env = {
            "SPEED_BUMP_TARGETS": str(sample_targets),
            "SPEED_BUMP_DELAY_NS": "5000",
            "SPEED_BUMP_FREQUENCY": "10",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            config = load_config()

        assert config.enabled is True
        assert len(config.targets) == 4
        assert config.delay_ns == 5000
        assert config.frequency == 10

    def test_default_values(self, sample_targets: Path) -> None:
        """Default values are used when env vars not specified."""
        env = {"SPEED_BUMP_TARGETS": str(sample_targets)}
        with mock.patch.dict(os.environ, env, clear=True):
            config = load_config()

        assert config.delay_ns == 1000
        assert config.frequency == 1
        assert config.end_ns is None  # indefinite

    def test_targets_file_not_found(self, tmp_path: Path) -> None:
        """ConfigError raised when targets file doesn't exist."""
        env = {"SPEED_BUMP_TARGETS": str(tmp_path / "nonexistent.txt")}
        with mock.patch.dict(os.environ, env, clear=True):
            with pytest.raises(ConfigError) as exc_info:
                load_config()
        assert "file not found" in str(exc_info.value)

    def test_empty_targets_file_disables(self, empty_target_file: Path) -> None:
        """Empty targets file results in disabled config (with warning)."""
        env = {"SPEED_BUMP_TARGETS": str(empty_target_file)}
        with mock.patch.dict(os.environ, env, clear=True):
            config = load_config()
        assert config.enabled is False


class TestConfigParsing:
    """Tests for parsing individual config values."""

    def test_invalid_delay_ns(self, sample_targets: Path) -> None:
        """Invalid SPEED_BUMP_DELAY_NS raises ConfigError."""
        env = {
            "SPEED_BUMP_TARGETS": str(sample_targets),
            "SPEED_BUMP_DELAY_NS": "not_a_number",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            with pytest.raises(ConfigError) as exc_info:
                load_config()
        assert "SPEED_BUMP_DELAY_NS" in str(exc_info.value)
        assert "invalid integer" in str(exc_info.value)

    def test_negative_delay_ns(self, sample_targets: Path) -> None:
        """Negative SPEED_BUMP_DELAY_NS raises ConfigError."""
        env = {
            "SPEED_BUMP_TARGETS": str(sample_targets),
            "SPEED_BUMP_DELAY_NS": "-100",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            with pytest.raises(ConfigError) as exc_info:
                load_config()
        assert "below minimum" in str(exc_info.value)

    def test_zero_frequency_raises(self, sample_targets: Path) -> None:
        """Zero SPEED_BUMP_FREQUENCY raises ConfigError."""
        env = {
            "SPEED_BUMP_TARGETS": str(sample_targets),
            "SPEED_BUMP_FREQUENCY": "0",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            with pytest.raises(ConfigError) as exc_info:
                load_config()
        assert "SPEED_BUMP_FREQUENCY" in str(exc_info.value)
        assert "below minimum" in str(exc_info.value)

    def test_delay_clamped_to_minimum(self, sample_targets: Path) -> None:
        """Delay below minimum is clamped with warning."""
        import speed_bump

        env = {
            "SPEED_BUMP_TARGETS": str(sample_targets),
            "SPEED_BUMP_DELAY_NS": "1",  # Almost certainly below minimum
        }
        with mock.patch.dict(os.environ, env, clear=True):
            config = load_config()

        # Should be clamped to at least the minimum
        assert config.delay_ns >= speed_bump.min_delay_ns


class TestTimingWindow:
    """Tests for start delay and duration configuration."""

    def test_start_delay(self, sample_targets: Path) -> None:
        """Start delay is correctly calculated."""
        env = {
            "SPEED_BUMP_TARGETS": str(sample_targets),
            "SPEED_BUMP_START_MS": "1000",  # 1 second
        }
        with mock.patch.dict(os.environ, env, clear=True):
            config = load_config()

        # Start should be ~1s after process start
        expected_start = _PROCESS_START_NS + 1_000_000_000
        # Allow 100ms tolerance for test execution time
        assert abs(config.start_ns - expected_start) < 100_000_000

    def test_duration(self, sample_targets: Path) -> None:
        """Duration is correctly calculated."""
        env = {
            "SPEED_BUMP_TARGETS": str(sample_targets),
            "SPEED_BUMP_START_MS": "1000",
            "SPEED_BUMP_DURATION_MS": "5000",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            config = load_config()

        assert config.end_ns is not None
        duration = config.end_ns - config.start_ns
        assert duration == 5_000_000_000  # 5 seconds in ns

    def test_zero_duration_means_indefinite(self, sample_targets: Path) -> None:
        """Duration of 0 means run indefinitely."""
        env = {
            "SPEED_BUMP_TARGETS": str(sample_targets),
            "SPEED_BUMP_DURATION_MS": "0",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            config = load_config()

        assert config.end_ns is None


class TestIsInWindow:
    """Tests for Config.is_in_window method."""

    def test_disabled_config_never_in_window(self) -> None:
        """Disabled config is never in window."""
        config = Config(
            enabled=False,
            targets=(),
            delay_ns=1000,
            frequency=1,
            start_ns=0,
            end_ns=None,
        )
        assert config.is_in_window() is False

    def test_before_start(self) -> None:
        """Before start time is not in window."""
        now = time.time_ns()
        config = Config(
            enabled=True,
            targets=(),
            delay_ns=1000,
            frequency=1,
            start_ns=now + 1_000_000_000,  # 1s in future
            end_ns=None,
        )
        assert config.is_in_window(now) is False

    def test_after_start_indefinite(self) -> None:
        """After start time with indefinite duration is in window."""
        now = time.time_ns()
        config = Config(
            enabled=True,
            targets=(),
            delay_ns=1000,
            frequency=1,
            start_ns=now - 1_000_000_000,  # 1s ago
            end_ns=None,
        )
        assert config.is_in_window(now) is True

    def test_after_end(self) -> None:
        """After end time is not in window."""
        now = time.time_ns()
        config = Config(
            enabled=True,
            targets=(),
            delay_ns=1000,
            frequency=1,
            start_ns=now - 2_000_000_000,  # 2s ago
            end_ns=now - 1_000_000_000,  # 1s ago
        )
        assert config.is_in_window(now) is False

    def test_within_window(self) -> None:
        """Within start and end is in window."""
        now = time.time_ns()
        config = Config(
            enabled=True,
            targets=(),
            delay_ns=1000,
            frequency=1,
            start_ns=now - 1_000_000_000,  # 1s ago
            end_ns=now + 1_000_000_000,  # 1s in future
        )
        assert config.is_in_window(now) is True
