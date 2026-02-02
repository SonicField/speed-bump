#!/bin/bash
# Run FTP verification tests with specified Python build
# Usage: ./run_ftp_tests.sh <python-path>
#
# Example:
#   ./run_ftp_tests.sh ~/local/cpython/python-3.14-gil/bin/python3
#   ./run_ftp_tests.sh ~/local/cpython/python-3.14-ftp/bin/python3

set -e

PYTHON="${1:-python3}"

echo "=== FTP Verification Tests ==="
echo "Python: $PYTHON"
echo ""

# Verify Python is accessible
if ! "$PYTHON" --version 2>/dev/null; then
    echo "ERROR: Cannot run $PYTHON"
    exit 1
fi

# Check GIL status
echo "=== Runtime Detection ==="
"$PYTHON" -c "
import sys
if hasattr(sys, '_is_gil_enabled'):
    gil_enabled = sys._is_gil_enabled()
    print(f'Python {sys.version}')
    print(f'GIL enabled: {gil_enabled}')
    print(f'Runtime type: {\"GIL Python\" if gil_enabled else \"Free-Threaded Python (FTP)\"}')
else:
    print(f'Python {sys.version}')
    print('GIL detection not available (Python < 3.13)')
"
echo ""

# Build C extension if needed
echo "=== Building C Extension ==="
cd "$(dirname "$0")/.."

# Get Python include and library paths
PYTHON_INCLUDE=$("$PYTHON" -c "import sysconfig; print(sysconfig.get_path('include'))")
PYTHON_LIBDIR=$("$PYTHON" -c "import sysconfig; print(sysconfig.get_config_var('LIBDIR'))")
EXT_SUFFIX=$("$PYTHON" -c "import sysconfig; print(sysconfig.get_config_var('EXT_SUFFIX'))")

echo "Include: $PYTHON_INCLUDE"
echo "Extension suffix: $EXT_SUFFIX"

# Compile the C extension
gcc -shared -fPIC -O2 \
    -I"$PYTHON_INCLUDE" \
    -o "src/speed_bump/_core$EXT_SUFFIX" \
    src/speed_bump/_core.c

echo "C extension built: src/speed_bump/_core$EXT_SUFFIX"
echo ""

# Run tests using manual test runner (pytest may not be available)
echo "=== Running Tests ==="
PYTHONPATH="src:tests" "$PYTHON" -c "
import gc
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor

# Define detection functions inline (to avoid importing conftest which requires pytest)
def is_free_threaded():
    return hasattr(sys, '_is_gil_enabled') and not sys._is_gil_enabled()

def is_gil_python():
    return not hasattr(sys, '_is_gil_enabled') or sys._is_gil_enabled()

# Import speed_bump
import speed_bump
from speed_bump._patterns import parse_pattern

print('=' * 60)
print('Runtime:', 'FTP' if is_free_threaded() else 'GIL')
print('=' * 60)

passed = 0
failed = 0
skipped = 0

def with_deflake(test_fn, is_overshoot, retries=2):
    '''Run a timing test with auto-deflake on overshoot failures.
    If test_fn raises AssertionError and is_overshoot returns True,
    retry up to retries times. All retries must pass to recover.'''
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

def run_test(name, test_fn, skip_condition=None, skip_reason=''):
    global passed, failed, skipped
    if skip_condition:
        print(f'SKIP: {name} ({skip_reason})')
        skipped += 1
        return
    try:
        test_fn()
        print(f'PASS: {name}')
        passed += 1
    except AssertionError as e:
        print(f'FAIL: {name}')
        print(f'      {e}')
        failed += 1
    except Exception as e:
        print(f'ERROR: {name}')
        print(f'       {type(e).__name__}: {e}')
        failed += 1

# Test 1: Runtime detection
def test_detection_api():
    assert hasattr(sys, '_is_gil_enabled'), 'sys._is_gil_enabled not found'
run_test('Detection API exists', test_detection_api)

# Test 2: Helper consistency
def test_helper_consistency():
    ftp = is_free_threaded()
    gil = is_gil_python()
    assert ftp != gil, f'Inconsistent: FTP={ftp}, GIL={gil}'
run_test('Helper functions consistent', test_helper_consistency)

# Test 3: Delay in main thread
def test_delay_main_thread():
    target = 100_000  # 100μs
    start = time.perf_counter_ns()
    speed_bump.spin_delay_ns(target)
    elapsed = time.perf_counter_ns() - start
    ratio = elapsed / target
    assert 0.5 <= ratio <= 3.0, f'Delay inaccurate: {elapsed}ns vs {target}ns (ratio={ratio:.2f})'
run_test('Delay works in main thread', test_delay_main_thread)

# Test 4: Delay in worker thread
def test_delay_worker_thread():
    target = 100_000
    result = [0]
    def worker():
        start = time.perf_counter_ns()
        speed_bump.spin_delay_ns(target)
        result[0] = time.perf_counter_ns() - start
    t = threading.Thread(target=worker)
    t.start()
    t.join()
    ratio = result[0] / target
    assert 0.5 <= ratio <= 3.0, f'Thread delay inaccurate: {result[0]}ns (ratio={ratio:.2f})'
run_test('Delay works in worker thread', test_delay_worker_thread)

# Test 5: FTP parallelism (FTP only) - with GC disable and deflake
def test_ftp_parallelism():
    delay_ns = 100_000
    n_threads = 4
    max_expected = delay_ns * 3

    def is_overshoot(e):
        return True  # Any failure is an overshoot

    def run_test():
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
            start = time.perf_counter_ns()
            end_barrier.wait()
            total = time.perf_counter_ns() - start
        finally:
            if gc_was_enabled:
                gc.enable()

        for t in threads:
            t.join()

        assert total <= max_expected, f'Delays not parallel: total={total}ns, expected < {max_expected}ns'

    with_deflake(run_test, is_overshoot)
run_test('FTP delays are parallel', test_ftp_parallelism,
         skip_condition=is_gil_python(), skip_reason='Requires FTP')

# Test 6: GIL serialisation (GIL only) - with GC disable
def test_gil_serialisation():
    delay_ns = 100_000
    n_threads = 4
    min_expected = delay_ns * n_threads * 0.5

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
        start = time.perf_counter_ns()
        end_barrier.wait()
        total = time.perf_counter_ns() - start
    finally:
        if gc_was_enabled:
            gc.enable()

    for t in threads:
        t.join()

    # On GIL, delays should be serialised: total >= N * delay * 0.5
    # No deflake: GC makes time longer, not shorter, so can't cause false negatives
    assert total >= min_expected, f'Delays parallel on GIL: total={total}ns, expected >= {min_expected}ns'
run_test('GIL delays are serialised', test_gil_serialisation,
         skip_condition=is_free_threaded(), skip_reason='Requires GIL')

# Test 7-10: Thread scaling (1, 2, 4, 8 threads)
def run_parallel_delays(n_threads, delay_ns):
    '''Two-barrier approach: measures only spin delay time. GC disabled during timing.'''
    start_barrier = threading.Barrier(n_threads + 1)
    end_barrier = threading.Barrier(n_threads + 1)
    per_thread = [0] * n_threads

    def worker(idx):
        start_barrier.wait()
        t0 = time.perf_counter_ns()
        speed_bump.spin_delay_ns(delay_ns)
        per_thread[idx] = time.perf_counter_ns() - t0
        end_barrier.wait()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
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

    return total, per_thread

for n_threads in [1, 2, 4, 8]:
    def test_per_thread_accuracy(n=n_threads):
        delay_ns = 50_000
        _, per_thread = run_parallel_delays(n, delay_ns)
        for i, elapsed in enumerate(per_thread):
            ratio = elapsed / delay_ns
            assert 0.5 <= ratio <= 3.0, f'Thread {i}/{n} delay wrong: ratio={ratio:.2f}'
    run_test(f'Per-thread delay accuracy ({n_threads} threads)',
             lambda n=n_threads: test_per_thread_accuracy(n))

# FTP-specific: constant total time
for n_threads in [2, 4, 8]:
    def test_ftp_constant_time(n=n_threads):
        delay_ns = 50_000
        total, _ = run_parallel_delays(n, delay_ns)
        max_expected = delay_ns * 3
        assert total <= max_expected, f'{n} threads: total={total}ns > {max_expected}ns'
    run_test(f'FTP total time constant ({n_threads} threads)',
             lambda n=n_threads: test_ftp_constant_time(n),
             skip_condition=is_gil_python(), skip_reason='Requires FTP')

# GIL-specific: scaling total time
for n_threads in [2, 4, 8]:
    def test_gil_scaling_time(n=n_threads):
        delay_ns = 50_000
        total, _ = run_parallel_delays(n, delay_ns)
        min_expected = delay_ns * n * 0.5
        assert total >= min_expected, f'{n} threads: total={total}ns < {min_expected}ns'
    run_test(f'GIL total time scales ({n_threads} threads)',
             lambda n=n_threads: test_gil_scaling_time(n),
             skip_condition=is_free_threaded(), skip_reason='Requires GIL')

# Test: Cache thread safety
def test_cache_safety():
    pattern = parse_pattern('test.*:*', 1)
    config = speed_bump.Config(
        enabled=True,
        targets=(pattern,),
        delay_ns=100,
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
                def dummy(): pass
                dummy()
        except Exception as e:
            errors.append(str(e))

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    speed_bump.uninstall()
    assert len(errors) == 0, f'Thread safety errors: {errors}'
run_test('Cache thread safety', test_cache_safety)

print('')
print('=' * 60)
print(f'Results: {passed} passed, {failed} failed, {skipped} skipped')
print('=' * 60)

sys.exit(1 if failed > 0 else 0)
"
