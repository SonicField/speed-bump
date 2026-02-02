"""Tests for thread scaling behaviour with speed-bump delays.

These tests verify that delays scale correctly with thread count:
- On GIL Python: total time scales with N (serialised)
- On FTP: total time is constant (parallel)

Falsification methodology:
- Each test documents what it claims to prove
- Each test documents how it would fail if the claim was false
- Parametrised tests cover 1, 2, 4, 8 thread counts
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

import speed_bump

# Import detection utilities from conftest
from conftest import is_free_threaded, is_gil_python, requires_ftp, requires_gil


class TestThreadScaling:
    """Tests for 1, 2, 4, 8 thread scaling."""

    DELAY_NS = 50_000  # 50μs base delay

    def run_parallel_delays(
        self, n_threads: int, delay_ns: int
    ) -> tuple[int, list[int]]:
        """Run delays in parallel, return (total_time, per_thread_times)."""
        barrier = threading.Barrier(n_threads)
        per_thread = [0] * n_threads

        def worker(idx):
            barrier.wait()  # Synchronise start
            start = time.perf_counter_ns()
            speed_bump.spin_delay_ns(delay_ns)
            per_thread[idx] = time.perf_counter_ns() - start

        threads = [
            threading.Thread(target=worker, args=(i,)) for i in range(n_threads)
        ]

        start = time.perf_counter_ns()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        total = time.perf_counter_ns() - start

        return total, per_thread

    @pytest.mark.parametrize("n_threads", [1, 2, 4, 8])
    def test_per_thread_delay_accuracy(self, n_threads: int):
        """Claim: Each thread gets accurate delay regardless of thread count.
        Falsification: Per-thread delay would be wrong if delay mechanism broken.
        """
        _, per_thread = self.run_parallel_delays(n_threads, self.DELAY_NS)

        for i, elapsed in enumerate(per_thread):
            ratio = elapsed / self.DELAY_NS
            assert 0.5 <= ratio <= 3.0, (
                f"Thread {i}/{n_threads} delay wrong: {elapsed}ns vs "
                f"{self.DELAY_NS}ns (ratio={ratio:.2f})"
            )

    @requires_ftp
    @pytest.mark.parametrize("n_threads", [1, 2, 4, 8])
    def test_ftp_total_time_is_constant(self, n_threads: int):
        """Claim: In FTP, total time is ~constant regardless of thread count.
        Falsification: Total time would scale with N if delays serialised.

        On FTP, parallel delays should complete in ~1×delay regardless of N.
        """
        total, _ = self.run_parallel_delays(n_threads, self.DELAY_NS)

        # In FTP, total should be ~1×delay regardless of N
        # Allow 3× tolerance for scheduling overhead
        max_expected = self.DELAY_NS * 3

        assert total <= max_expected, (
            f"With {n_threads} FTP threads, total={total}ns but "
            f"expected <={max_expected}ns (parallel). "
            f"Delays may be serialising incorrectly."
        )

    @requires_gil
    @pytest.mark.parametrize("n_threads", [1, 2, 4, 8])
    def test_gil_total_time_scales_with_n(self, n_threads: int):
        """Control: In GIL Python, total time scales with thread count.
        Falsification: Would not scale if GIL was somehow bypassed.

        On GIL Python, serialised delays should complete in ~N×delay.
        """
        total, _ = self.run_parallel_delays(n_threads, self.DELAY_NS)

        # On GIL, total should be ~N×delay
        min_expected = self.DELAY_NS * n_threads * 0.5

        assert total >= min_expected, (
            f"With {n_threads} GIL threads, total={total}ns but "
            f"expected >={min_expected}ns (serialised). "
            f"Delays may be parallelising unexpectedly."
        )


class TestScalingWithMonitoring:
    """Tests for scaling behaviour when monitoring is active."""

    DELAY_NS = 30_000  # 30μs base delay

    @pytest.fixture(autouse=True)
    def setup_monitoring(self):
        """Install and uninstall monitoring around each test."""
        from speed_bump._patterns import parse_pattern

        pattern = parse_pattern("*:*", 1)
        config = speed_bump.Config(
            enabled=True,
            targets=(pattern,),
            delay_ns=1000,  # 1μs monitoring delay
            frequency=1,
            start_ns=0,
            end_ns=None,
        )

        speed_bump.clear_cache()
        speed_bump.install(config)
        yield
        speed_bump.uninstall()

    @pytest.mark.parametrize("n_threads", [1, 2, 4])
    def test_monitoring_overhead_with_threads(self, n_threads: int):
        """Claim: Monitoring doesn't cause excessive overhead per thread.
        Falsification: Overhead would be > 10× if monitoring was broken.
        """
        barrier = threading.Barrier(n_threads)
        results = [0] * n_threads

        def worker(idx):
            barrier.wait()
            start = time.perf_counter_ns()
            # Call a function that will trigger monitoring
            for _ in range(100):
                def dummy():
                    pass
                dummy()
            results[idx] = time.perf_counter_ns() - start

        threads = [
            threading.Thread(target=worker, args=(i,)) for i in range(n_threads)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Check that no thread had excessive overhead
        for i, elapsed in enumerate(results):
            # 100 iterations × 1μs delay = ~100μs minimum
            # Allow up to 10× overhead for scheduling etc.
            max_expected = 100 * 1000 * 10  # 1ms
            assert elapsed <= max_expected, (
                f"Thread {i} monitoring overhead excessive: {elapsed}ns"
            )
