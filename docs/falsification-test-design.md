# Falsification Test Design: Free-Threaded Python

**Date**: 2026-02-01
**Purpose**: Design tests that PROVE behaviour, not just confirm it.

---

## Falsification Philosophy

A test that passes tells you nothing unless it would FAIL if the code was broken.

For each test, we must define:
1. **Claim**: What behaviour we're asserting
2. **Falsification**: How we'd detect if broken
3. **Control**: A test that SHOULD fail to prove our detector works

---

## Test Categories

### Category 1: Runtime Detection

**Claim**: speed-bump correctly detects GIL vs FTP runtime.

**Tests**:

```python
# test_free_threaded.py

import sys
import pytest

def is_free_threaded():
    """Return True if running on free-threaded Python."""
    return hasattr(sys, '_is_gil_enabled') and not sys._is_gil_enabled()

def is_gil_python():
    """Return True if running on GIL Python."""
    return not hasattr(sys, '_is_gil_enabled') or sys._is_gil_enabled()


class TestRuntimeDetection:
    """Tests for FTP/GIL detection."""

    def test_detection_function_exists(self):
        """Claim: sys._is_gil_enabled exists on Python 3.13+.
        Falsification: Would fail on Python 3.12 or earlier.
        """
        assert hasattr(sys, '_is_gil_enabled'), "Requires Python 3.13+"

    @pytest.mark.skipif(is_gil_python(), reason="Requires FTP")
    def test_ftp_detected_correctly(self):
        """Claim: On FTP, sys._is_gil_enabled() returns False.
        Falsification: Would fail if detection was inverted.
        """
        assert sys._is_gil_enabled() is False

    @pytest.mark.skipif(is_free_threaded(), reason="Requires GIL Python")
    def test_gil_detected_correctly(self):
        """Claim: On GIL Python, sys._is_gil_enabled() returns True.
        Falsification: Would fail if detection was inverted.
        """
        assert sys._is_gil_enabled() is True
```

---

### Category 2: Delay Accuracy Per-Thread

**Claim**: Spin delay works correctly in each thread independently.

**Falsification**: If delays didn't work per-thread, measured delay would be wrong.

```python
# test_threading_scaling.py

import time
import threading
from concurrent.futures import ThreadPoolExecutor
import speed_bump

class TestDelayAccuracyPerThread:
    """Tests that delay works in each thread."""

    def measure_delay(self, target_ns: int) -> int:
        """Measure actual delay vs requested."""
        start = time.perf_counter_ns()
        speed_bump.spin_delay_ns(target_ns)
        return time.perf_counter_ns() - start

    def test_delay_works_in_main_thread(self):
        """Claim: Delay works in main thread.
        Falsification: Measured time would be << requested.
        """
        target = 100_000  # 100μs
        elapsed = self.measure_delay(target)
        # Allow 0.5x to 3x tolerance (spin delay isn't perfect)
        assert 0.5 * target <= elapsed <= 3 * target, f"Delay inaccurate: {elapsed}ns vs {target}ns"

    def test_delay_works_in_worker_thread(self):
        """Claim: Delay works in spawned thread.
        Falsification: Measured time would be << requested if delay broken in threads.
        """
        target = 100_000  # 100μs
        result = [0]

        def worker():
            result[0] = self.measure_delay(target)

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        assert 0.5 * target <= result[0] <= 3 * target, f"Delay inaccurate in thread: {result[0]}ns"

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
            assert 0.5 * target <= elapsed <= 3 * target, f"Worker {i} delay wrong: {elapsed}ns"
```

---

### Category 3: FTP Parallelism Verification

**Claim**: In FTP, delays in parallel threads don't block each other.

**Falsification**: If delays were serialised (like with GIL), total time would be N×delay.

**Control**: On GIL Python, total time SHOULD be ~N×delay (serialised).

```python
class TestFTPParallelism:
    """Tests specific to free-threaded Python behaviour."""

    @pytest.mark.skipif(is_gil_python(), reason="Requires FTP")
    def test_ftp_delays_are_parallel(self):
        """Claim: In FTP, N threads delaying in parallel complete in ~1×delay time.
        Falsification: If delays serialised, would take N×delay.

        This is the KEY FTP test - proves delays don't hold a global lock.
        """
        delay_ns = 100_000  # 100μs per thread
        n_threads = 4

        barrier = threading.Barrier(n_threads)

        def worker():
            barrier.wait()  # Synchronise start
            speed_bump.spin_delay_ns(delay_ns)

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]

        start = time.perf_counter_ns()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        total = time.perf_counter_ns() - start

        # In FTP: total should be ~1×delay (parallel)
        # In GIL: total would be ~N×delay (serialised)
        # Allow 2× tolerance for scheduling overhead
        max_expected = delay_ns * 2  # Parallel
        serialised_would_be = delay_ns * n_threads

        assert total < serialised_would_be * 0.6, (
            f"Delays appear serialised: total={total}ns, "
            f"serialised would be {serialised_would_be}ns. "
            f"FTP should complete in ~{delay_ns}ns"
        )

    @pytest.mark.skipif(is_free_threaded(), reason="Requires GIL Python")
    def test_gil_delays_are_serialised(self):
        """Control test: On GIL Python, delays SHOULD serialise.

        This proves our parallelism detector works - if this passes on GIL,
        and test_ftp_delays_are_parallel passes on FTP, we know we're
        correctly detecting the difference.
        """
        delay_ns = 100_000  # 100μs per thread
        n_threads = 4

        barrier = threading.Barrier(n_threads)

        def worker():
            barrier.wait()
            speed_bump.spin_delay_ns(delay_ns)

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]

        start = time.perf_counter_ns()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        total = time.perf_counter_ns() - start

        # On GIL: total should be ~N×delay (serialised)
        min_expected = delay_ns * n_threads * 0.5  # At least half of serialised

        assert total >= min_expected, (
            f"Delays appear parallel on GIL Python: total={total}ns, "
            f"expected at least {min_expected}ns for {n_threads} serialised delays"
        )
```

---

### Category 4: Scaling Verification

**Claim**: Slowdown scales correctly with thread count.

```python
class TestThreadScaling:
    """Tests for 1, 2, 4, 8 thread scaling."""

    @pytest.fixture
    def delay_ns(self):
        return 50_000  # 50μs

    def run_parallel_delays(self, n_threads: int, delay_ns: int) -> tuple[int, list[int]]:
        """Run delays in parallel, return (total_time, per_thread_times)."""
        barrier = threading.Barrier(n_threads)
        per_thread = [0] * n_threads

        def worker(idx):
            barrier.wait()
            start = time.perf_counter_ns()
            speed_bump.spin_delay_ns(delay_ns)
            per_thread[idx] = time.perf_counter_ns() - start

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]

        start = time.perf_counter_ns()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        total = time.perf_counter_ns() - start

        return total, per_thread

    @pytest.mark.parametrize("n_threads", [1, 2, 4, 8])
    def test_per_thread_delay_accuracy(self, n_threads: int, delay_ns: int):
        """Claim: Each thread gets accurate delay regardless of thread count.
        Falsification: Per-thread delay would be wrong if delay mechanism broken.
        """
        _, per_thread = self.run_parallel_delays(n_threads, delay_ns)

        for i, elapsed in enumerate(per_thread):
            ratio = elapsed / delay_ns
            assert 0.5 <= ratio <= 3.0, (
                f"Thread {i}/{n_threads} delay wrong: {elapsed}ns vs {delay_ns}ns (ratio={ratio:.2f})"
            )

    @pytest.mark.skipif(is_gil_python(), reason="Requires FTP")
    @pytest.mark.parametrize("n_threads", [1, 2, 4, 8])
    def test_ftp_total_time_is_constant(self, n_threads: int, delay_ns: int):
        """Claim: In FTP, total time is ~constant regardless of thread count.
        Falsification: Total time would scale with N if serialised.
        """
        total, _ = self.run_parallel_delays(n_threads, delay_ns)

        # In FTP, total should be ~1×delay regardless of N
        # Allow 3× tolerance for scheduling
        max_expected = delay_ns * 3

        assert total <= max_expected, (
            f"With {n_threads} threads, total={total}ns but expected <={max_expected}ns (parallel)"
        )

    @pytest.mark.skipif(is_free_threaded(), reason="Requires GIL Python")
    @pytest.mark.parametrize("n_threads", [1, 2, 4, 8])
    def test_gil_total_time_scales_with_n(self, n_threads: int, delay_ns: int):
        """Control: In GIL Python, total time scales with thread count.
        Falsification: Would not scale if GIL was somehow bypassed.
        """
        total, _ = self.run_parallel_delays(n_threads, delay_ns)

        # On GIL, total should be ~N×delay
        min_expected = delay_ns * n_threads * 0.5

        assert total >= min_expected, (
            f"With {n_threads} threads, total={total}ns but expected >={min_expected}ns (serialised)"
        )
```

---

### Category 5: Match Cache Thread Safety

**Claim**: The match cache in _monitoring.py is thread-safe.

**Falsification**: Race conditions would cause cache corruption or crashes.

```python
class TestMatchCacheThreadSafety:
    """Tests for thread-safety of the match cache."""

    def test_concurrent_cache_access(self):
        """Claim: Match cache handles concurrent access safely.
        Falsification: Race condition would cause crash or wrong results.
        """
        import speed_bump
        from speed_bump._patterns import parse_pattern

        # Create a config
        pattern = parse_pattern("test.*:*", 1)
        config = speed_bump.Config(
            enabled=True,
            targets=(pattern,),
            delay_ns=1000,
            frequency=1,
            start_ns=0,
            end_ns=None,
        )

        speed_bump.clear_cache()
        speed_bump.install(config)

        errors = []
        n_threads = 8
        n_iterations = 1000

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
```

---

## Test File Structure

```
tests/
├── conftest.py                # Updated with is_free_threaded(), is_gil_python()
├── test_free_threaded.py      # Category 1, 5 tests
├── test_threading_scaling.py  # Category 2, 3, 4 tests
└── existing tests...
```

---

## Execution Plan

1. Run tests with GIL Python: GIL-specific tests pass, FTP-specific skip
2. Run tests with FTP Python: FTP-specific tests pass, GIL-specific skip
3. Compare results to verify detection works correctly

---

## Open Questions

1. Does the spin delay in _core.c release GIL? (Check implementation)
2. Does the match cache lock work correctly in FTP?
3. What's the actual thread safety model of PEP 669 monitoring?
