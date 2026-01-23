"""Tests for spin delay accuracy."""

from __future__ import annotations

import time

import pytest

import speed_bump


class TestSpinDelay:
    """Tests for spin_delay_ns accuracy."""

    def test_zero_delay_is_fast(self) -> None:
        """Zero delay should return almost immediately."""
        start = time.perf_counter_ns()
        speed_bump.spin_delay_ns(0)
        elapsed = time.perf_counter_ns() - start

        # Should complete in under 1ms even with measurement overhead
        assert elapsed < 1_000_000, f"Zero delay took {elapsed}ns"

    def test_delay_is_at_least_requested(self) -> None:
        """Delay should be at least as long as requested."""
        delay_ns = 10_000  # 10µs

        start = time.perf_counter_ns()
        speed_bump.spin_delay_ns(delay_ns)
        elapsed = time.perf_counter_ns() - start

        assert elapsed >= delay_ns, f"Delay of {delay_ns}ns only took {elapsed}ns"

    def test_delay_is_reasonably_bounded(self) -> None:
        """Delay should not massively overshoot.

        We allow 2x the requested delay as upper bound. This accounts for:
        - Measurement overhead
        - System scheduling jitter
        - Cache effects
        """
        delay_ns = 10_000  # 10µs

        start = time.perf_counter_ns()
        speed_bump.spin_delay_ns(delay_ns)
        elapsed = time.perf_counter_ns() - start

        max_expected = delay_ns * 2
        assert elapsed < max_expected, f"Delay of {delay_ns}ns took {elapsed}ns (>{max_expected}ns)"

    def test_longer_delay_accuracy(self) -> None:
        """Test accuracy for a longer delay (100µs)."""
        delay_ns = 100_000  # 100µs

        start = time.perf_counter_ns()
        speed_bump.spin_delay_ns(delay_ns)
        elapsed = time.perf_counter_ns() - start

        # Should be within 50% of target for longer delays
        assert elapsed >= delay_ns
        assert elapsed < delay_ns * 1.5, f"Delay of {delay_ns}ns took {elapsed}ns"

    def test_millisecond_delay(self) -> None:
        """Test a 1ms delay for reasonable accuracy."""
        delay_ns = 1_000_000  # 1ms

        start = time.perf_counter_ns()
        speed_bump.spin_delay_ns(delay_ns)
        elapsed = time.perf_counter_ns() - start

        # Should be within 20% of target for ms-scale delays
        assert elapsed >= delay_ns
        assert elapsed < delay_ns * 1.2, f"Delay of {delay_ns}ns took {elapsed}ns"

    @pytest.mark.parametrize(
        "delay_ns",
        [1_000, 5_000, 10_000, 50_000, 100_000],
        ids=["1µs", "5µs", "10µs", "50µs", "100µs"],
    )
    def test_various_delays(self, delay_ns: int) -> None:
        """Test various delay durations are at least as long as requested."""
        start = time.perf_counter_ns()
        speed_bump.spin_delay_ns(delay_ns)
        elapsed = time.perf_counter_ns() - start

        assert elapsed >= delay_ns, f"Delay of {delay_ns}ns only took {elapsed}ns"
