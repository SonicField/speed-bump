"""Tests for PEP 669 monitoring integration."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

import speed_bump
from speed_bump import Config, install, is_installed, uninstall, clear_cache

if TYPE_CHECKING:
    pass


@pytest.fixture(autouse=True)
def cleanup_monitoring():
    """Ensure monitoring is uninstalled after each test."""
    yield
    uninstall()
    clear_cache()


class TestInstallUninstall:
    """Tests for install/uninstall lifecycle."""

    def test_install_disabled_config_returns_false(self) -> None:
        """Installing with disabled config returns False."""
        config = Config(
            enabled=False,
            targets=(),
            delay_ns=1000,
            frequency=1,
            start_ns=0,
            end_ns=None,
        )
        assert install(config) is False
        assert is_installed() is False

    def test_install_empty_targets_returns_false(self) -> None:
        """Installing with no targets returns False."""
        config = Config(
            enabled=True,
            targets=(),  # No targets
            delay_ns=1000,
            frequency=1,
            start_ns=0,
            end_ns=None,
        )
        assert install(config) is False
        assert is_installed() is False

    def test_install_valid_config_returns_true(self, sample_targets: Path) -> None:
        """Installing with valid config returns True."""
        from speed_bump._patterns import load_targets

        targets = load_targets(sample_targets)
        config = Config(
            enabled=True,
            targets=tuple(targets),
            delay_ns=1000,
            frequency=1,
            start_ns=0,
            end_ns=None,
        )
        assert install(config) is True
        assert is_installed() is True

    def test_uninstall_cleans_up(self, sample_targets: Path) -> None:
        """Uninstall properly cleans up state."""
        from speed_bump._patterns import load_targets

        targets = load_targets(sample_targets)
        config = Config(
            enabled=True,
            targets=tuple(targets),
            delay_ns=1000,
            frequency=1,
            start_ns=0,
            end_ns=None,
        )
        install(config)
        assert is_installed() is True

        uninstall()
        assert is_installed() is False

    def test_uninstall_when_not_installed(self) -> None:
        """Uninstall when not installed is a no-op."""
        uninstall()  # Should not raise
        assert is_installed() is False


class TestCallbackFiring:
    """Tests for callback behavior on function calls."""

    def test_matching_function_is_delayed(self, tmp_path: Path) -> None:
        """A function matching the pattern is delayed."""
        from speed_bump._patterns import load_targets

        # Create targets file matching our test function
        # Use *target_function to match the full qualname which includes <locals>
        targets_file = tmp_path / "targets.txt"
        targets_file.write_text("*:*target_function\n")

        targets = load_targets(targets_file)
        now = time.time_ns()
        config = Config(
            enabled=True,
            targets=tuple(targets),
            delay_ns=100_000,  # 100 microseconds
            frequency=1,
            start_ns=now - 1_000_000_000,  # Started 1s ago
            end_ns=None,
        )
        install(config)

        # Define and call a matching function
        def target_function() -> int:
            return 42

        # Measure time for several calls
        start = time.time_ns()
        for _ in range(10):
            target_function()
        elapsed = time.time_ns() - start

        # Should have added at least 10 * 100µs = 1ms of delay
        # Allow some tolerance for overhead
        assert elapsed >= 800_000  # At least 0.8ms

    def test_non_matching_function_not_delayed(self, tmp_path: Path) -> None:
        """A function not matching patterns is not delayed."""
        from speed_bump._patterns import load_targets

        # Create targets file that won't match our function
        targets_file = tmp_path / "targets.txt"
        targets_file.write_text("*:nonexistent_function\n")

        targets = load_targets(targets_file)
        now = time.time_ns()
        config = Config(
            enabled=True,
            targets=tuple(targets),
            delay_ns=1_000_000,  # 1 millisecond (would be noticeable)
            frequency=1,
            start_ns=now - 1_000_000_000,
            end_ns=None,
        )
        install(config)

        # Define and call a non-matching function
        def other_function() -> int:
            return 42

        # Measure time for many calls
        start = time.time_ns()
        for _ in range(1000):
            other_function()
        elapsed = time.time_ns() - start

        # Should be fast - definitely less than 10ms for 1000 calls
        # (would be 1000ms if delayed)
        assert elapsed < 10_000_000  # Less than 10ms


class TestFrequency:
    """Tests for frequency (every Nth call) behavior."""

    def test_frequency_skips_calls(self, tmp_path: Path) -> None:
        """With frequency=10, only every 10th call is delayed."""
        from speed_bump._patterns import load_targets

        targets_file = tmp_path / "targets.txt"
        targets_file.write_text("*:*freq_test_function\n")

        targets = load_targets(targets_file)
        now = time.time_ns()
        config = Config(
            enabled=True,
            targets=tuple(targets),
            delay_ns=100_000,  # 100 microseconds
            frequency=10,  # Only every 10th call
            start_ns=now - 1_000_000_000,
            end_ns=None,
        )
        install(config)

        def freq_test_function() -> int:
            return 42

        # 100 calls with frequency=10 means 10 delays of 100µs = 1ms total
        start = time.time_ns()
        for _ in range(100):
            freq_test_function()
        elapsed = time.time_ns() - start

        # Should be around 1ms, not 10ms
        # Allow tolerance: between 0.5ms and 5ms
        assert 500_000 <= elapsed <= 5_000_000


class TestTimingWindow:
    """Tests for timing window behavior."""

    def test_before_start_no_delay(self, tmp_path: Path) -> None:
        """Before start time, no delay is applied."""
        from speed_bump._patterns import load_targets

        targets_file = tmp_path / "targets.txt"
        targets_file.write_text("*:*window_test_function\n")

        targets = load_targets(targets_file)
        now = time.time_ns()
        config = Config(
            enabled=True,
            targets=tuple(targets),
            delay_ns=1_000_000,  # 1ms
            frequency=1,
            start_ns=now + 10_000_000_000,  # 10 seconds in future
            end_ns=None,
        )
        install(config)

        def window_test_function() -> int:
            return 42

        start = time.time_ns()
        for _ in range(100):
            window_test_function()
        elapsed = time.time_ns() - start

        # Should be fast - no delays since we're before start
        assert elapsed < 10_000_000  # Less than 10ms

    def test_after_end_no_delay(self, tmp_path: Path) -> None:
        """After end time, no delay is applied."""
        from speed_bump._patterns import load_targets

        targets_file = tmp_path / "targets.txt"
        targets_file.write_text("*:*window_end_test\n")

        targets = load_targets(targets_file)
        now = time.time_ns()
        config = Config(
            enabled=True,
            targets=tuple(targets),
            delay_ns=1_000_000,  # 1ms
            frequency=1,
            start_ns=now - 2_000_000_000,  # 2s ago
            end_ns=now - 1_000_000_000,  # 1s ago (ended)
            )
        install(config)

        def window_end_test() -> int:
            return 42

        start = time.time_ns()
        for _ in range(100):
            window_end_test()
        elapsed = time.time_ns() - start

        # Should be fast - no delays since window has ended
        assert elapsed < 10_000_000  # Less than 10ms


class TestCaching:
    """Tests for match result caching."""

    def test_cache_cleared_between_configs(self, tmp_path: Path) -> None:
        """Cache is properly cleared when calling clear_cache."""
        from speed_bump._patterns import load_targets

        targets_file = tmp_path / "targets.txt"
        targets_file.write_text("*:*cached_function\n")

        targets = load_targets(targets_file)
        now = time.time_ns()
        config = Config(
            enabled=True,
            targets=tuple(targets),
            delay_ns=50_000,  # 50µs
            frequency=1,
            start_ns=now - 1_000_000_000,
            end_ns=None,
        )
        install(config)

        def cached_function() -> int:
            return 42

        # Call once to populate cache
        cached_function()

        # Clear and reinstall with different targets
        uninstall()
        clear_cache()

        # New config that doesn't match
        targets_file2 = tmp_path / "targets2.txt"
        targets_file2.write_text("*:nonexistent\n")
        targets2 = load_targets(targets_file2)

        config2 = Config(
            enabled=True,
            targets=tuple(targets2),
            delay_ns=1_000_000,  # 1ms
            frequency=1,
            start_ns=now - 1_000_000_000,
            end_ns=None,
        )
        install(config2)

        # Should not be delayed with new config
        start = time.time_ns()
        for _ in range(100):
            cached_function()
        elapsed = time.time_ns() - start

        # Should be fast since new targets don't match
        assert elapsed < 10_000_000


class TestGetConfig:
    """Tests for get_config function."""

    def test_get_config_returns_none_when_not_installed(self) -> None:
        """get_config returns None when monitoring is not installed."""
        assert speed_bump.get_config() is None

    def test_get_config_returns_config_when_installed(self, sample_targets: Path) -> None:
        """get_config returns the config when monitoring is installed."""
        from speed_bump._patterns import load_targets

        targets = load_targets(sample_targets)
        config = Config(
            enabled=True,
            targets=tuple(targets),
            delay_ns=1234,
            frequency=5,
            start_ns=0,
            end_ns=None,
        )
        install(config)

        retrieved = speed_bump.get_config()
        assert retrieved is not None
        assert retrieved.delay_ns == 1234
        assert retrieved.frequency == 5
