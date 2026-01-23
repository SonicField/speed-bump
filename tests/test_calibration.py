"""Tests for clock calibration."""

from __future__ import annotations

import speed_bump


class TestCalibration:
    """Tests for clock_gettime calibration."""

    def test_clock_overhead_is_positive(self) -> None:
        """Clock overhead must be positive."""
        assert speed_bump.clock_overhead_ns > 0

    def test_clock_overhead_is_plausible(self) -> None:
        """Clock overhead should be between 1ns and 1000ns on modern systems.

        If this fails, either:
        - The system is unusually slow (VM, emulation, etc.)
        - The calibration code has a bug
        """
        overhead = speed_bump.clock_overhead_ns
        assert 1 <= overhead <= 1000, f"Implausible overhead: {overhead}ns"

    def test_clock_overhead_is_stable(self) -> None:
        """Repeated calls return the same value (calibration only runs once)."""
        val1 = speed_bump.get_clock_overhead_ns()
        val2 = speed_bump.get_clock_overhead_ns()
        assert val1 == val2

    def test_min_delay_is_double_overhead(self) -> None:
        """Minimum delay should be 2x the overhead."""
        assert speed_bump.min_delay_ns == 2 * speed_bump.clock_overhead_ns

    def test_is_calibrated(self) -> None:
        """Module should report as calibrated after import."""
        assert speed_bump.is_calibrated() is True

    def test_module_attributes_match_functions(self) -> None:
        """Module attributes should match function return values."""
        assert speed_bump.clock_overhead_ns == speed_bump.get_clock_overhead_ns()
        assert speed_bump.min_delay_ns == speed_bump.get_min_delay_ns()
