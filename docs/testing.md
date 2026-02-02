# Testing

Speed-bump has two test layers: Python integration tests and C-level sanitiser tests.

## Python Tests

### With pytest (if available)

```bash
pytest tests/
```

### Standalone runner (no pytest required)

```bash
# Test with GIL Python
./tests/run_ftp_tests.sh /path/to/python3.14/bin/python3

# Test with FTP Python
./tests/run_ftp_tests.sh /path/to/python3.14t/bin/python3
```

The standalone runner:
- Builds the C extension for the specified Python
- Runs all tests with appropriate skips based on runtime type
- Reports pass/fail/skip counts

### Test categories

| Category | GIL Python | FTP Python |
|----------|------------|------------|
| Runtime detection | ✓ | ✓ |
| Delay accuracy (main thread) | ✓ | ✓ |
| Delay accuracy (worker thread) | ✓ | ✓ |
| Per-thread accuracy (1,2,4,8 threads) | ✓ | ✓ |
| Cache thread safety | ✓ | ✓ |
| GIL serialisation tests | ✓ | skip |
| FTP parallelism tests | skip | ✓ |

GIL-specific and FTP-specific tests are skipped on the wrong runtime by design - they test mutually exclusive behaviours.

## C-Level Tests

The C tests exercise the core spin delay code with sanitisers, independently of Python. This avoids false positives from uninstrumented Python runtime code.

### Running C tests

```bash
# All sanitiser tests
./tests/run_c_tests.sh

# ThreadSanitizer only
./tests/run_c_tests.sh tsan

# AddressSanitizer only
./tests/run_c_tests.sh asan

# Clean build artifacts
./tests/run_c_tests.sh clean
```

### What the C tests verify

**ThreadSanitizer (tsan)**:
- `spin_delay_ns` is race-free under concurrent execution
- 8 threads, 100 iterations each, no shared mutable state

**AddressSanitizer (asan)**:
- No buffer overflows, use-after-free, or memory leaks
- Same test harness as tsan

### Why standalone C tests?

1. **Isolation**: Tests the actual functions that run in parallel, without Python overhead
2. **No false positives**: Uninstrumented Python code would trigger spurious warnings
3. **Speed**: Faster iteration than full Python integration tests
4. **Precision**: If tsan finds a race, it's definitely in our code

### Thread-safety guarantees

Verified by tsan (documented in `src/speed_bump/_core.c`):

| Function | Thread-safe? | Notes |
|----------|--------------|-------|
| `spin_delay_ns` | Yes | Uses only local variables |
| `calibrate_clock` | No* | Called once at module init; Python import serialises this |
| `g_clock_overhead_ns` | Read-only after init | Safe to read from any thread |
| `g_calibrated` | Read-only after init | Safe to read from any thread |

*Would race if called concurrently, but this never happens due to Python's import machinery.

## Falsification

All tests are designed with falsification criteria:

1. **Test validity**: Deliberately racy code confirms tsan detects races
2. **Measurement accuracy**: Two-barrier synchronisation isolates spin delay from thread overhead
3. **Control tests**: GIL tests fail on FTP, FTP tests fail on GIL (verified by design)

See `docs/falsification-test-design.md` for detailed test design rationale.
