# Plan: Free-Threaded Python Verification for speed-bump

**Created**: 2026-02-01
**Terminal Goal**: Verify speed-bump works correctly with free-threaded Python, with falsification tests proving both correctness and failure detection.

---

## Scope

1. **Build infrastructure**: Optimised GIL and FTP builds in `~/local/cpython`
2. **Falsification test suite**: Tests that WOULD FAIL if behaviour was wrong
3. **Multi-threaded scaling**: Verify slowdown across 1, 2, 4, 8 threads
4. **Documentation**: Full docs for FTP behaviour and test methodology

---

## Phases

### Phase 1: Build Infrastructure

**Goal**: Two optimised CPython builds in `~/local/cpython`

| Build | Location | Configure flags |
|-------|----------|-----------------|
| GIL (3.14) | `~/local/cpython/python-3.14-gil` | `--enable-optimizations --with-lto` |
| FTP (3.14) | `~/local/cpython/python-3.14-ftp` | `--enable-optimizations --with-lto --disable-gil` |

**Acceptance criteria**:
- Both builds complete without error
- Both can import speed_bump
- `python -c "import sys; print(sys._is_gil_enabled())"` returns expected value

### Phase 2: Baseline Verification

**Goal**: Confirm existing tests pass on both builds

| Build | Expected |
|-------|----------|
| GIL | All 28 tests pass (already verified) |
| FTP | Unknown - this is what we're investigating |

### Phase 3: Falsification Test Design

**Goal**: Design tests that PROVE behaviour, not just confirm it

**Key insight**: A test that passes doesn't prove correctness. We need tests that:
1. Would FAIL if the feature was broken
2. Demonstrate the failure mode we're testing against

**Test categories**:

| Category | What it proves | How to falsify |
|----------|----------------|----------------|
| FTP detection | Code correctly detects GIL vs FTP | Mock `sys._is_gil_enabled()`, verify different paths taken |
| Delay accuracy | Spin delay works per-thread | Measure delay on each thread, compare to requested |
| Scaling behaviour | N threads get N × delay total | Run 1,2,4,8 threads, measure total slowdown |
| No cross-thread interference | One thread's delay doesn't block others | In FTP: slow one thread, verify others continue |

### Phase 4: Implementation

**Test file structure**:
```
tests/
├── test_free_threaded.py      # FTP-specific tests
├── test_threading_scaling.py  # Multi-thread scaling tests
├── conftest.py                # Updated with FTP detection fixtures
```

**Skip logic**:
- Tests requiring FTP: `@pytest.mark.skipif(sys._is_gil_enabled(), reason="Requires free-threaded Python")`
- Tests requiring GIL: `@pytest.mark.skipif(not sys._is_gil_enabled(), reason="Requires GIL Python")`

### Phase 5: Documentation

**Files to create/update**:
- `docs/free-threaded.md` - FTP behaviour and limitations
- `README.md` - Update limitations section
- Test docstrings - Explain what each test falsifies

---

## Falsification Contract

For each test, document:
1. **Claim being tested**: What behaviour we're asserting
2. **Falsification method**: How we'd detect if it was broken
3. **Expected failure mode**: What would happen if broken

Example:
```python
def test_delay_per_thread():
    """
    Claim: Each thread receives its own delay independently.
    Falsification: If delays were serialised (GIL-like), total time would be N×delay.
                   In FTP, total time should be ~1×delay (parallel execution).
    Expected failure: test_ftp_delays_are_parallel would fail if delays serialise.
    """
```

---

## Worker Strategy

To manage context, use workers for:
- Build tasks (long-running, isolated)
- Test implementation (can work from spec)
- Documentation (can work from test results)

Supervisor retains:
- Plan oversight
- Decision-making
- Progress tracking
- 3Ws after each worker

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| FTP build fails | Check Python 3.14 FTP support first |
| Tests are flaky | Use statistical methods, multiple runs |
| Context overflow | Aggressive worker delegation, summary-only results |
| Incorrect falsification | Review test logic before implementation |

---

## Progress Tracking

| Phase | Status | Worker | Notes |
|-------|--------|--------|-------|
| 1. Build GIL | Pending | | |
| 1. Build FTP | Pending | | |
| 2. Baseline GIL | Done | worker-001 | 28/28 pass |
| 2. Baseline FTP | Pending | | |
| 3. Test design | Pending | | Supervisor task |
| 4. Implementation | Pending | | |
| 5. Documentation | Pending | | |

---

## Open Questions

1. Does Python 3.14 source we have support `--disable-gil`?
2. What's the actual behaviour of spin delay without GIL?
3. Are there race conditions in the match cache under FTP?
