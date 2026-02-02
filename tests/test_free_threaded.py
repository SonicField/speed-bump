"""Tests for free-threaded Python (FTP) behaviour.

These tests verify that speed-bump correctly detects and behaves under
free-threaded Python (--disable-gil builds).

Falsification methodology:
- Each test documents what it claims to prove
- Each test documents how it would fail if the claim was false
- Control tests run on the opposite runtime to verify detection

Timing robustness:
- GC is disabled during timing-sensitive measurements
- Auto-deflake: if test fails with excessive overshoot, retry twice
  - Both retries must pass to recover from a flake
"""

from __future__ import annotations

import gc
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

# Import detection utilities from conftest
from conftest import (
    is_free_threaded,
    is_gil_python,
    requires_ftp,
    requires_gil,
    requires_gil_detection,
)

import speed_bump
from speed_bump._patterns import parse_pattern


def with_deflake(
    test_fn: Callable[[], None],
    is_overshoot: Callable[[AssertionError], bool],
    retries: int = 2,
) -> None:
    """Run a timing test with auto-deflake on overshoot failures.

    If test_fn raises AssertionError and is_overshoot returns True,
    retry up to `retries` times. All retries must pass to recover.
    """
    try:
        test_fn()
    except AssertionError as e:
        if not is_overshoot(e):
            raise

        for _ in range(retries):
            try:
                test_fn()
            except AssertionError:
                raise e from None


class TestRuntimeDetection:
    """Tests for FTP/GIL detection."""

    @requires_gil_detection
    def test_detection_api_exists(self):
        """Claim: sys._is_gil_enabled exists on Python 3.13+.
        Falsification: Would fail on Python 3.12 or earlier.
        """
        assert hasattr(sys, "_is_gil_enabled"), (
            "sys._is_gil_enabled() not found. Requires Python 3.13+ for GIL/FTP detection."
        )

    @requires_ftp
    def test_ftp_detected_correctly(self):
        """Claim: On FTP, sys._is_gil_enabled() returns False.
        Falsification: Would fail if detection was inverted or broken.
        """
        assert sys._is_gil_enabled() is False, "Expected GIL disabled on free-threaded Python"

    @requires_gil
    @requires_gil_detection
    def test_gil_detected_correctly(self):
        """Claim: On GIL Python, sys._is_gil_enabled() returns True.
        Falsification: Would fail if detection was inverted or broken.
        """
        assert sys._is_gil_enabled() is True, "Expected GIL enabled on standard Python"

    def test_helper_functions_consistent(self):
        """Claim: is_free_threaded() and is_gil_python() are mutually exclusive.
        Falsification: Would fail if both returned True or both False.
        """
        ftp = is_free_threaded()
        gil = is_gil_python()
        assert ftp != gil, f"Inconsistent: is_free_threaded={ftp}, is_gil_python={gil}"


class TestDelayPerThread:
    """Tests that delay works correctly in each thread."""

    def measure_delay(self, target_ns: int) -> int:
        """Measure actual delay vs requested."""
        start = time.perf_counter_ns()
        speed_bump.spin_delay_ns(target_ns)
        return time.perf_counter_ns() - start

    def test_delay_works_in_main_thread(self):
        """Claim: Delay works in main thread.
        Falsification: Measured time would be << requested if delay broken.
        """
        target = 100_000  # 100μs
        elapsed = self.measure_delay(target)
        ratio = elapsed / target
        assert 0.5 <= ratio <= 3.0, (
            f"Delay inaccurate: {elapsed}ns vs {target}ns (ratio={ratio:.2f})"
        )

    def test_delay_works_in_worker_thread(self):
        """Claim: Delay works in spawned thread.
        Falsification: Measured time would be wrong if delay broken in threads.
        """
        target = 100_000  # 100μs
        result = [0]

        def worker():
            result[0] = self.measure_delay(target)

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        ratio = result[0] / target
        assert 0.5 <= ratio <= 3.0, (
            f"Delay in thread inaccurate: {result[0]}ns vs {target}ns (ratio={ratio:.2f})"
        )

    def test_delay_works_in_thread_pool(self):
        """Claim: Delay works in ThreadPoolExecutor workers.
        Falsification: Some workers would have wrong delay.
        """
        target = 50_000  # 50μs
        n_workers = 4

        def worker(_):
            return self.measure_delay(target)

        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            results = list(executor.map(worker, range(n_workers)))

        for i, elapsed in enumerate(results):
            ratio = elapsed / target
            assert 0.5 <= ratio <= 3.0, (
                f"Worker {i} delay wrong: {elapsed}ns vs {target}ns (ratio={ratio:.2f})"
            )


class TestFTPParallelism:
    """Tests specific to free-threaded Python parallel behaviour."""

    @requires_ftp
    def test_ftp_delays_are_parallel(self):
        """Claim: In FTP, N threads delaying in parallel complete in ~1xdelay time.
        Falsification: If delays serialised, would take Nxdelay.

        This is the KEY FTP test - proves delays don't hold a global lock.

        Uses two-barrier synchronisation to measure only spin delay time,
        excluding thread startup/teardown overhead. GC disabled during timing.
        Auto-deflake on overshoot failures.
        """
        delay_ns = 100_000  # 100μs per thread
        n_threads = 4
        serialised_would_be = delay_ns * n_threads
        max_expected = serialised_would_be * 0.6

        def is_overshoot(e: AssertionError) -> bool:
            # Any failure here is an overshoot (time too long)
            return True

        def run_test():
            # Two barriers: one to synchronise start, one to synchronise end
            start_barrier = threading.Barrier(n_threads + 1)
            end_barrier = threading.Barrier(n_threads + 1)

            def worker():
                start_barrier.wait()
                speed_bump.spin_delay_ns(delay_ns)
                end_barrier.wait()

            threads = [threading.Thread(target=worker) for _ in range(n_threads)]
            for t in threads:
                t.start()

            # Disable GC during timing-sensitive measurement
            gc_was_enabled = gc.isenabled()
            gc.disable()
            try:
                start_barrier.wait()
                wall_start = time.perf_counter_ns()
                end_barrier.wait()
                total = time.perf_counter_ns() - wall_start
            finally:
                if gc_was_enabled:
                    gc.enable()

            for t in threads:
                t.join()

            # In FTP: total should be ~1xdelay (parallel)
            # In GIL: total would be ~Nxdelay (serialised)
            assert total < max_expected, (
                f"Delays appear serialised on FTP: total={total}ns, "
                f"serialised would be {serialised_would_be}ns. "
                f"Parallel should complete in ~{delay_ns}ns"
            )

        with_deflake(run_test, is_overshoot)

    @requires_gil
    def test_gil_delays_are_serialised(self):
        """Control test: On GIL Python, delays SHOULD serialise.

        This proves our parallelism detector works - if this passes on GIL,
        and test_ftp_delays_are_parallel passes on FTP, we know we're
        correctly detecting the difference.

        Uses two-barrier synchronisation and GC disable for measurement accuracy.
        No deflake needed: GC would make time appear longer, not shorter,
        so cannot cause false negatives on a minimum-bound check.
        """
        delay_ns = 100_000  # 100μs per thread
        n_threads = 4
        min_expected = delay_ns * n_threads * 0.5  # At least half of serialised

        # Two barriers: one to synchronise start, one to synchronise end
        start_barrier = threading.Barrier(n_threads + 1)
        end_barrier = threading.Barrier(n_threads + 1)

        def worker():
            start_barrier.wait()
            speed_bump.spin_delay_ns(delay_ns)
            end_barrier.wait()

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()

        # Disable GC during timing-sensitive measurement
        gc_was_enabled = gc.isenabled()
        gc.disable()
        try:
            start_barrier.wait()
            wall_start = time.perf_counter_ns()
            end_barrier.wait()
            total = time.perf_counter_ns() - wall_start
        finally:
            if gc_was_enabled:
                gc.enable()

        for t in threads:
            t.join()

        # On GIL: total should be ~Nxdelay (serialised)
        assert total >= min_expected, (
            f"Delays appear parallel on GIL Python: total={total}ns, "
            f"expected at least {min_expected}ns for {n_threads} serialised delays"
        )


class TestMatchCacheThreadSafety:
    """Tests for thread-safety of the match cache under concurrent access."""

    def test_concurrent_cache_access_no_crash(self):
        """Claim: Match cache handles concurrent access safely.
        Falsification: Race condition would cause crash or exception.
        """
        pattern = parse_pattern("test.*:*", 1)
        config = speed_bump.Config(
            enabled=True,
            targets=(pattern,),
            delay_ns=100,  # Very small delay
            frequency=1,
            start_ns=0,
            end_ns=None,
        )

        speed_bump.clear_cache()
        speed_bump.install(config)

        errors = []
        n_threads = 8
        n_iterations = 100

        def worker():
            try:
                for _ in range(n_iterations):
                    # Force cache access by calling a function
                    def dummy():
                        pass

                    dummy()
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        speed_bump.uninstall()

        assert len(errors) == 0, f"Thread safety errors: {errors}"
