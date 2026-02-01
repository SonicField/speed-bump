# Discovery Report: speed-bump

**Date**: 2026-02-01
**Terminal Goal (Reconstructed)**: Identify which pieces of Python machinery are performance-critical for complex GPU-accelerated async systems by artificially slowing code and measuring throughput impact - because traditional profiling shows time spent, not time that matters.

---

## Artefacts Found

| Location | Files | Status |
|----------|-------|--------|
| `src/speed_bump/` | `__init__.py`, `_config.py`, `_core.c`, `_monitoring.py`, `_patterns.py` | Explored |
| `docs/` | `methodology.md`, `patterns.md` | Read |
| `tests/` | 6 test files (`test_calibration.py`, `test_config.py`, `test_delay.py`, `test_integration.py`, `test_monitoring.py`, `test_patterns.py`) | Verified via manual runner |
| Root | `README.md`, `pyproject.toml`, `setup.py`, `LICENSE`, etc. | Read |
| `.github/workflows/` | `ci.yml`, `release.yml` | Not explored |

---

## Triage Summary

| Artefact | Purpose | Verdict | Rationale |
|----------|---------|---------|-----------|
| `_core.c` | Clock calibration + spin delay | Keep | Core mechanism, C for performance |
| `_monitoring.py` | PEP 669 hooks for function call interception | Keep | Clean implementation, caches correctly |
| `_patterns.py` | Target pattern matching (glob-based) | Keep | Simple, correct |
| `_config.py` | Environment variable parsing + timing windows | Keep | Well-structured dataclass |
| `__init__.py` | Public API | Keep | Clean exports |
| `methodology.md` | Usage methodology for finding bottlenecks | Keep | Explains the "why" well |
| `patterns.md` | Pattern syntax reference | Keep | Useful reference for users |
| `tests/*` | Test suite | Keep | All 28 tests pass |
| `README.md` | Project overview | Keep | Clear, accurate (one TODO noted) |
| `pyproject.toml` | Build config | Keep | Standard, correct |

**No discards.** Project is coherent with no dead ends in current state.

---

## Valuable Outcomes Identified

1. **Working implementation**: PEP 669 monitoring + C spin delay, verified by 28 passing tests
2. **Methodology documentation**: Clear explanation of the slowdown approach vs traditional profiling
3. **Low clock overhead**: 25 ns measured, enabling microsecond-scale delays
4. **Pattern-based targeting**: Glob patterns allow selective slowdown of specific modules/functions

---

## Gap Analysis

### Instrumental Goals Summary

| Goal | Why Needed | Dependencies |
|------|------------|--------------|
| Document free-threaded Python behaviour | Human flagged this as uncertain | Research/testing |
| Document "only interpreter code" limitation | Known limitation, needs explicit docs | None |
| Clarify Statistics collection status | Marked as TODO in README | Decision on scope |
| Establish plan + progress files | NBS compliance | This discovery |
| Add build instructions for restricted environments | Worker needed manual gcc build | Document workaround |

### Confirmed Understanding (Full Detail)

#### Terminal Goal
**Question**: What was this project trying to achieve?
**Confirmed**: The terminal goal is to identify which pieces of Python machinery are performance-critical for complex systems - not by measuring raw time, but by understanding the dependency structure (non-linear, async) to find where improvements would actually propagate benefit through the system. The insight is that if slowing X doesn't hurt throughput, X isn't worth optimising regardless of how "hot" it looks.
*Human confirmed: "Yeh - exactly"*

#### Timeframe
**Question**: What timeframe did the work span?
**Confirmed**: Last couple of weeks. The motivation for NBS compliance is to get structure in place before doing real work on AI training next week.

#### Artefact Locations
**Question**: Is everything in `~/local/speed-bump`, or are there related artefacts elsewhere?
**Confirmed**: Self-contained. Everything is in the one directory.

#### Valuable Outcomes
**Question**: What are the valuable outcomes you want to preserve?
**Confirmed**: Most of it can be preserved. This is a tidy-up and verification pass ("making sure it has no bullshit"), not major triage.

#### Dead Ends / Known Issues
**Question**: What do you remember about dead ends or false starts?
**Confirmed**:
- Pure Python prototype existed but overhead was impractical (now gone, forgotten)
- Open question: behaviour in free-threaded Python (PEP 703/nogil) is uncertain
- Known limitation: can only slow interpreted Python, not C extensions
- Speculative: eBPF might be alternative approach (flagged as speculation, not verified)

---

## Open Questions

1. **Free-threaded Python**: How does speed-bump behave with PEP 703 (nogil)? The spin delay holds the GIL - what happens when there is no GIL?

2. **C extension coverage**: Can we ever slow C extension code? If not, should this be prominently documented as a fundamental limitation?

3. **Statistics collection**: README shows this as unchecked TODO. Is this planned? What would it collect?

4. **Build in restricted environments**: pip/setuptools not available in dev environment. Should alternative build instructions be documented?

---

## Recommended Next Steps

1. **Create plan file**: `01-02-2026-speed-bump-plan.md` with terminal goal and prioritised work
2. **Create progress log**: `01-02-2026-speed-bump-progress.md` documenting this session
3. **Document limitations**: Add section to README or separate doc covering:
   - Free-threaded Python (unknown/untested)
   - C extension code (cannot be slowed)
   - GIL implications (spin delay holds GIL)
4. **Decide on Statistics collection**: Keep TODO, remove, or implement?
5. **Add manual build instructions**: For environments without pip access

---

## Verification Status

| Criterion | Status |
|-----------|--------|
| C extension compiles | ✓ Verified (gcc, no warnings) |
| Tests pass | ✓ 28/28 pass |
| Clock overhead | ✓ 25 ns (plausible) |
| Code matches docs | Partially verified |
| Limitations documented | ✗ Gaps identified |
