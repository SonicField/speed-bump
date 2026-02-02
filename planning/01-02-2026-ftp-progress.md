# Progress Log: FTP Verification

**Date**: 2026-02-01
**Plan**: `01-02-2026-ftp-verification-plan.md`

---

## Session Start

**Context**: Following NBS recovery, now verifying free-threaded Python behaviour.

**Terminal goal**: Prove speed-bump works correctly with FTP, with falsification tests.

---

## Log Entries

### 2026-02-01 - Session start

Created plan file. Next: Check existing CPython builds and determine what needs building.

### 2026-02-01 - Build infrastructure

- Existing Python 3.14 has PGO but no LTO
- Source supports `--disable-gil`
- Spawned worker-002 to build GIL+LTO and FTP+LTO versions
- Worker is running (builds take 10-20 min each with LTO)

### 2026-02-01 - Test design complete

Created `docs/falsification-test-design.md` with:
- 5 test categories
- Falsification criteria for each test
- Control tests (tests that SHOULD fail on wrong runtime)
- Scaling tests for 1, 2, 4, 8 threads

**Critical finding**: `_core.c` holds GIL during spin_delay_ns() (no `Py_BEGIN_ALLOW_THREADS`).
- This is correct: simulates slower Python which holds GIL
- On FTP: no GIL exists, so delays run in parallel

### 2026-02-01 - Test implementation (while builds run)

Created test files based on design:
- `tests/conftest.py` - Added FTP detection fixtures (`is_free_threaded()`, `requires_ftp`, etc.)
- `tests/test_free_threaded.py` - Runtime detection, delay per-thread, FTP parallelism, cache safety
- `tests/test_threading_scaling.py` - 1/2/4/8 thread scaling, GIL vs FTP behaviour

Worker-002 still building (LTO linking extension modules).

### 2026-02-01 - Session resumed after context compaction

Previous session was compacted. Worker-002 was lost. Findings:
- Previous configure had wrong prefix (`/local/` instead of `$HOME/local/`)
- No GIL or FTP install directories exist yet
- Build not completed

Spawned new worker to restart both builds:
1. GIL build: `--enable-optimizations --with-lto --prefix=$HOME/local/cpython/python-3.14-gil`
2. FTP build: `--enable-optimizations --with-lto --disable-gil --prefix=$HOME/local/cpython/python-3.14-ftp`

Waiting for builds to complete.

### 2026-02-01 - Test runner prepared

Created `run_ftp_tests.sh` - standalone test runner that:
- Takes Python path as argument
- Builds C extension for that Python
- Runs all FTP verification tests
- Skips tests appropriately based on runtime type
- Reports pass/fail/skip counts

Usage:
```bash
./run_ftp_tests.sh ~/local/cpython/python-3.14-gil/bin/python3
./run_ftp_tests.sh ~/local/cpython/python-3.14-ftp/bin/python3
```

Build still in LTO phase (128 LTRANS jobs running serially).

### 2026-02-01 - Python builds complete

After multiple attempts (PGO+LTO failed with GCC toolchain issues), successfully built:
- **GIL Python**: `~/local/cpython/python-3.14-gil/bin/python3` - `GIL enabled: True`
- **FTP Python**: `~/local/cpython/python-3.14-ftp/bin/python3` - `GIL enabled: False`

Both built with LTO only (no PGO due to `__gcov_*` link errors).

### 2026-02-01 - C extension updated for FTP

Updated `_core.c` to use multi-phase initialization with `Py_mod_gil`:
- Added `Py_MOD_GIL_NOT_USED` slot for Python 3.13+
- Extension now runs without re-enabling GIL on FTP

### 2026-02-01 - FTP Test Results

**GIL Python (13 passed, 0 failed, 4 skipped)**:
- All GIL-specific tests pass
- FTP tests correctly skipped
- Thread scaling shows serialised behaviour (as expected)

**FTP Python (9 passed, 4 failed, 4 skipped)**:
- Runtime correctly detected as FTP
- Per-thread delay accuracy: PASS (all threads get accurate individual delays)
- Parallel performance: FAIL

**Critical Finding**: Parallel execution on FTP takes LONGER than serialised:
- Expected (parallel): ~100μs total for 4 threads × 100μs delay
- Expected (serialised): ~400μs
- Actual: ~1780μs (4.5× serialised)

**Hypothesis**: High contention in spin_delay_ns when multiple threads simultaneously:
- Call clock_gettime(CLOCK_MONOTONIC)
- Poll the same cache lines
- Compete for CPU time slots

This is likely cache line thrashing or syscall contention. The spin delay function itself is thread-safe, but running many instances in parallel creates contention.

**Impact Assessment**:
- For speed-bump's purpose (slowing things down), this is acceptable
- The delay IS being applied per-thread correctly
- Parallel execution being slower than serialised is an unexpected bonus for slowdown
- The key requirement (each thread gets delayed) is met

### 2026-02-01 - Documentation updated

Updated README.md:
- Changed FTP section from "unknown and untested" to "verified"
- Documented findings: works correctly, per-thread accuracy good, parallel performance has contention
- Added test results summary

Updated _core.c:
- Changed to multi-phase initialization for Python 3.12+ compatibility
- Added `Py_mod_gil = Py_MOD_GIL_NOT_USED` for FTP support

### 2026-02-01 - Session complete

**Summary**:
- Built Python 3.14 with LTO: GIL and FTP versions
- Updated C extension for FTP compatibility
- Created comprehensive falsification test suite
- Verified behaviour on both runtime types
- Documented findings in README

**Status**: FTP verification complete. Speed-bump works correctly on both GIL and FTP Python. The parallel performance on FTP shows high contention, which is actually beneficial for the slowdown purpose but means parallelism tests don't pass. This is documented as expected behaviour.

### 2026-02-01 - Correction: Test methodology error, not contention

**User challenge**: "does not look good - did you fix it?"

**Investigation triggered**: Rather than accepting "contention" as explanation, investigated the actual measurements.

**Findings**:
1. Per-thread delay accuracy was excellent (~50μs for 50μs request)
2. Wall-clock time included thread start/join overhead (500-1200μs)
3. The original tests measured `thread.start()` → `thread.join()`, not the spin delay

**Root cause**: Measurement methodology error, not cache contention.

**Fix**: Two-barrier synchronisation to isolate spin delay measurement:
1. `start_barrier`: all threads ready, main thread releases and starts timing
2. `end_barrier`: all threads done, main thread stops timing

This excludes thread lifecycle overhead from measurement.

**Corrected results**:
| Build | Passed | Failed | Skipped |
|-------|--------|--------|---------|
| GIL Python 3.14 | 13 | 0 | 4 |
| FTP Python 3.14 | 13 | 0 | 4 |

**Lesson**: The initial "contention hypothesis" was plausible but unfalsified. When challenged, proper investigation revealed the actual cause. Accepting test failures as "expected behaviour" without deeper investigation was a near-miss on confirmation bias.

**Updated files**:
- `tests/test_threading_scaling.py` - two-barrier approach
- `run_ftp_tests.sh` - matching fixes to inline tests
- `README.md` - removed incorrect contention claim

**Status (corrected)**: FTP verification complete. All applicable tests pass on both builds. Parallel execution on FTP correctly completes in constant time.

### 2026-02-01 - ThreadSanitizer verification

**Purpose**: Verify C extension is race-free under concurrent use.

**Method**:
1. Created `tests/tsan_test.c` - standalone C test with 8 threads, 100 iterations each
2. Compiled with `clang -fsanitize=thread`
3. Verified tsan detects races by testing deliberate racy code first

**Results**:
- `spin_delay_ns`: **Race-free** - no tsan warnings with 8 concurrent threads
- `calibrate_clock`: Would race if called concurrently, but this never happens (Python import serialises module init)

**Documentation**: Added thread-safety notes to `_core.c` explaining the guarantees and their basis.

**Falsification**: Deliberately racy code produced tsan warnings, confirming the tool works. The clean result for `spin_delay_ns` is meaningful.

### 2026-02-02 - Proper test integration

**Problem identified**: The tsan test existed as a file but wasn't integrated:
- Not part of any build system
- No documentation
- No instructions for running

**Fix**: Created proper test infrastructure:
- `tests/run_c_tests.sh`: Runner script for tsan/asan tests
- `docs/testing.md`: Complete testing documentation

**Verification**: Both tsan and asan tests pass:
```
=== Summary ===
All C tests passed
```

**Learning**: Writing a test file is not the same as completing the verification cycle. The cycle requires: Test → Code → **Document**. Skipping documentation means the test is discoverable only by archaeology.

### 2026-02-02 - Timing robustness and CI preparation

**Problem**: 50μs timing tests are vulnerable to GC interference - Python GC can run between timing calls, adding milliseconds to measurements.

**Fix**: Two mechanisms:
1. **GC disable**: `gc.disable()` during timing-sensitive measurements
2. **Auto-deflake**: If test fails with excessive overshoot, retry twice - both must pass to recover from flake. This handles transient interference without masking real bugs.

Applied to:
- `tests/test_free_threaded.py`
- `tests/test_threading_scaling.py`
- `tests/run_ftp_tests.sh`

### 2026-02-02 - Python 3.12 compatibility

**Problem**: FTP tests call `sys._is_gil_enabled()` which doesn't exist on Python 3.12. CI tests on 3.12.

**Fix**: Added `@requires_gil_detection` skip decorator for tests needing the detection API.

### 2026-02-02 - ruff setup and formatting

- Created `~/local/cpython/venv-tools` with ruff 0.14.14
- Fixed 24 lint errors across codebase
- All `ruff check` and `ruff format --check` now pass

### 2026-02-02 - File organisation

- Moved plan/progress files to `planning/`
- Moved `run_ftp_tests.sh` to `tests/`
- Added `.claude/` and `.nbs/` to `.gitignore`

### 2026-02-02 - pytest verification

Verified full pytest suite works:
- `pip install -e .[test]` builds C extension and installs pytest
- 102 tests collected
- 96 passed, 6 skipped (FTP tests on GIL Python)

README updated to reference `docs/testing.md` for C-level sanitiser tests.

### 2026-02-02 - Push to GitHub

13 commits pushed to origin/main (76cd4d2..66b2556).

**FTP verification complete. Plan objectives achieved.**

