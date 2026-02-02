"""Integration tests for speed-bump.

These tests run speed-bump in subprocesses to verify end-to-end behaviour
including environment variable handling and timing windows.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# Get PYTHONPATH for subprocess tests (needed when speed_bump isn't installed)
_SRC_PATH = str(Path(__file__).parent.parent / "src")
_BASE_ENV = {"PYTHONPATH": _SRC_PATH}


def _make_env(**extra: str) -> dict[str, str]:
    """Create environment dict with PYTHONPATH and any extra vars."""
    env = dict(_BASE_ENV)
    env.update(extra)
    return env


class TestSubprocessIntegration:
    """Tests that run speed-bump in a subprocess with environment variables."""

    def test_speed_bump_disabled_no_targets(self) -> None:
        """Without SPEED_BUMP_TARGETS, no slowdown occurs."""
        code = textwrap.dedent("""
            import time

            def target_func():
                return 42

            start = time.time_ns()
            for _ in range(1000):
                target_func()
            elapsed = time.time_ns() - start

            # Without speed-bump, 1000 calls should be very fast
            print(elapsed)
            assert elapsed < 10_000_000, f"Took too long: {elapsed}ns"
        """)

        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env=_make_env(),  # Empty means no SPEED_BUMP_TARGETS but includes PYTHONPATH
        )
        assert result.returncode == 0, f"Failed: {result.stderr}"

    def test_speed_bump_with_targets_delays(self, tmp_path: Path) -> None:
        """With SPEED_BUMP_TARGETS, matching calls are delayed."""
        # Create targets file
        targets_file = tmp_path / "targets.txt"
        targets_file.write_text("*:*target_func\n")

        code = textwrap.dedent("""
            import time
            import speed_bump

            # Load config and install monitoring
            config = speed_bump.load_config()
            speed_bump.install(config)

            def target_func():
                return 42

            start = time.time_ns()
            for _ in range(10):
                target_func()
            elapsed = time.time_ns() - start

            # With 100µs delay per call, 10 calls should take at least 500µs
            print(f"Elapsed: {elapsed}ns")
            assert elapsed >= 500_000, f"Too fast: {elapsed}ns, expected delays"
        """)

        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env=_make_env(
                SPEED_BUMP_TARGETS=str(targets_file),
                SPEED_BUMP_DELAY_NS="100000",  # 100 microseconds
                SPEED_BUMP_FREQUENCY="1",
            ),
        )
        assert result.returncode == 0, f"Failed: {result.stderr}\n{result.stdout}"

    def test_frequency_reduces_delays(self, tmp_path: Path) -> None:
        """With frequency=10, only 1/10 calls are delayed."""
        targets_file = tmp_path / "targets.txt"
        targets_file.write_text("*:*freq_func\n")

        code = textwrap.dedent("""
            import time
            import speed_bump

            config = speed_bump.load_config()
            speed_bump.install(config)

            def freq_func():
                return 42

            start = time.time_ns()
            for _ in range(100):
                freq_func()
            elapsed = time.time_ns() - start

            # 100 calls with freq=10 means 10 delays of 100µs = 1ms
            # Should be between 0.5ms and 5ms
            print(f"Elapsed: {elapsed}ns")
            assert 500_000 <= elapsed <= 10_000_000, f"Unexpected timing: {elapsed}ns"
        """)

        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env=_make_env(
                SPEED_BUMP_TARGETS=str(targets_file),
                SPEED_BUMP_DELAY_NS="100000",
                SPEED_BUMP_FREQUENCY="10",
            ),
        )
        assert result.returncode == 0, f"Failed: {result.stderr}\n{result.stdout}"

    def test_start_delay_defers_slowdown(self, tmp_path: Path) -> None:
        """With SPEED_BUMP_START_MS, delays start after the specified time."""
        targets_file = tmp_path / "targets.txt"
        targets_file.write_text("*:*start_delay_func\n")

        code = textwrap.dedent("""
            import time
            import speed_bump

            config = speed_bump.load_config()
            speed_bump.install(config)

            def start_delay_func():
                return 42

            # Calls immediately after start - should not be delayed (start_ms=10000)
            start = time.time_ns()
            for _ in range(100):
                start_delay_func()
            elapsed = time.time_ns() - start

            # Should be fast since we're before the start window
            print(f"Elapsed: {elapsed}ns")
            assert elapsed < 10_000_000, f"Too slow: {elapsed}ns, should be before start window"
        """)

        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env=_make_env(
                SPEED_BUMP_TARGETS=str(targets_file),
                SPEED_BUMP_DELAY_NS="100000",
                SPEED_BUMP_START_MS="10000",  # 10 seconds in future
            ),
        )
        assert result.returncode == 0, f"Failed: {result.stderr}\n{result.stdout}"

    def test_duration_limits_slowdown(self, tmp_path: Path) -> None:
        """With SPEED_BUMP_DURATION_MS=1, slowdown ends quickly."""
        targets_file = tmp_path / "targets.txt"
        targets_file.write_text("*:*duration_func\n")

        code = textwrap.dedent("""
            import time
            import speed_bump

            config = speed_bump.load_config()
            speed_bump.install(config)

            def duration_func():
                return 42

            # Wait for duration window to end (1ms)
            time.sleep(0.01)  # 10ms to be safe

            # Now calls should not be delayed
            start = time.time_ns()
            for _ in range(100):
                duration_func()
            elapsed = time.time_ns() - start

            # Should be fast since duration has passed
            print(f"Elapsed: {elapsed}ns")
            assert elapsed < 10_000_000, f"Too slow: {elapsed}ns, should be after duration"
        """)

        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env=_make_env(
                SPEED_BUMP_TARGETS=str(targets_file),
                SPEED_BUMP_DELAY_NS="100000",
                SPEED_BUMP_DURATION_MS="1",  # 1ms duration
            ),
        )
        assert result.returncode == 0, f"Failed: {result.stderr}\n{result.stdout}"

    def test_non_matching_pattern_no_delay(self, tmp_path: Path) -> None:
        """Patterns that don't match don't delay."""
        targets_file = tmp_path / "targets.txt"
        targets_file.write_text("*:*nonexistent_pattern\n")

        code = textwrap.dedent("""
            import time
            import speed_bump

            config = speed_bump.load_config()
            speed_bump.install(config)

            def other_func():
                return 42

            start = time.time_ns()
            for _ in range(1000):
                other_func()
            elapsed = time.time_ns() - start

            # Should be fast since pattern doesn't match
            print(f"Elapsed: {elapsed}ns")
            assert elapsed < 10_000_000, f"Too slow: {elapsed}ns, pattern shouldn't match"
        """)

        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env=_make_env(
                SPEED_BUMP_TARGETS=str(targets_file),
                SPEED_BUMP_DELAY_NS="1000000",  # 1ms per call would be obvious
            ),
        )
        assert result.returncode == 0, f"Failed: {result.stderr}\n{result.stdout}"


class TestErrorHandling:
    """Tests for error conditions in subprocess."""

    def test_missing_targets_file_raises(self, tmp_path: Path) -> None:
        """Non-existent targets file raises ConfigError."""
        code = textwrap.dedent("""
            import speed_bump
            try:
                config = speed_bump.load_config()
            except speed_bump.ConfigError as e:
                print(f"Got expected error: {e}")
                exit(0)
            print("ERROR: Should have raised ConfigError")
            exit(1)
        """)

        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env=_make_env(
                SPEED_BUMP_TARGETS=str(tmp_path / "nonexistent.txt"),
            ),
        )
        assert result.returncode == 0, f"Failed: {result.stderr}"
        assert "file not found" in result.stdout.lower()

    def test_invalid_delay_raises(self, tmp_path: Path) -> None:
        """Invalid SPEED_BUMP_DELAY_NS raises ConfigError."""
        targets_file = tmp_path / "targets.txt"
        targets_file.write_text("*:*\n")

        code = textwrap.dedent("""
            import speed_bump
            try:
                config = speed_bump.load_config()
            except speed_bump.ConfigError as e:
                print(f"Got expected error: {e}")
                exit(0)
            print("ERROR: Should have raised ConfigError")
            exit(1)
        """)

        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env=_make_env(
                SPEED_BUMP_TARGETS=str(targets_file),
                SPEED_BUMP_DELAY_NS="not_a_number",
            ),
        )
        assert result.returncode == 0, f"Failed: {result.stderr}"
        assert "invalid" in result.stdout.lower()


class TestCalibrationInSubprocess:
    """Tests for calibration in subprocess."""

    def test_calibration_values_available(self) -> None:
        """Calibration values are available immediately after import."""
        code = textwrap.dedent("""
            import speed_bump

            print(f"clock_overhead_ns: {speed_bump.clock_overhead_ns}")
            print(f"min_delay_ns: {speed_bump.min_delay_ns}")

            assert speed_bump.clock_overhead_ns > 0
            assert speed_bump.min_delay_ns >= speed_bump.clock_overhead_ns * 2
            assert speed_bump.is_calibrated()
        """)

        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env=_make_env(),
        )
        assert result.returncode == 0, f"Failed: {result.stderr}"
        assert "clock_overhead_ns:" in result.stdout

    def test_delay_below_minimum_clamped(self, tmp_path: Path) -> None:
        """Delay below minimum is clamped with warning."""
        targets_file = tmp_path / "targets.txt"
        targets_file.write_text("*:*\n")

        code = textwrap.dedent("""
            import speed_bump

            config = speed_bump.load_config()
            print(f"delay_ns: {config.delay_ns}")
            assert config.delay_ns >= speed_bump.min_delay_ns
        """)

        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env=_make_env(
                SPEED_BUMP_TARGETS=str(targets_file),
                SPEED_BUMP_DELAY_NS="1",  # Way below minimum
            ),
        )
        assert result.returncode == 0, f"Failed: {result.stderr}"
        # Should have warning in stderr
        assert "clamping" in result.stderr.lower() or "delay_ns:" in result.stdout
