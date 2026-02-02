# Plan: speed-bump

**Created**: 2026-02-01
**Terminal Goal**: Identify which pieces of Python machinery are performance-critical for complex GPU-accelerated async systems by artificially slowing code and measuring throughput impact.

---

## Current State

- **Code**: Working. PEP 669 monitoring + C spin delay. 28/28 tests pass.
- **Docs**: Methodology and patterns documented. README complete except limitations.
- **Epistemic Status**: NBS recovery in progress.

---

## Prioritised Work

### Immediate (This Session)
- [x] Verify build and tests pass
- [x] Document known limitations
- [x] Establish NBS structure (this plan, progress log)

### Next Session
- [x] Run `/nbs-investigation` on "Statistics collection" to determine requirements → **Deferred** (annotated in README)
- [x] Test behaviour with free-threaded Python → **Complete** (see FTP progress log)

### Future (Deferred)
- [ ] Consider alternative approaches for C extension coverage (eBPF - speculative)
- [ ] Decide on statistics collection feature

**Plan complete. Core objectives achieved. FTP verification complete. Future items are exploratory/deferred.**

---

## Known Limitations (to document)

1. **Free-threaded Python**: Behaviour unknown/untested with PEP 703
2. **C extensions**: Cannot slow C extension code, only interpreted Python
3. **GIL**: Spin delay holds the GIL, blocking other threads

---

## Open Questions (Resolved)

1. ~~What should "Statistics collection" actually collect?~~ **Deferred** - annotated in README with uncertainty note
2. ~~Is there a path to slowing C extension code?~~ **No** - documented as fundamental limitation
3. ~~How does spin delay behave without GIL?~~ **Parallel execution** - verified with FTP tests

---

## Falsification Criteria

| Claim | How to falsify |
|-------|----------------|
| Spin delay is accurate | Measure delay vs requested; should be within 2x |
| Pattern matching works | Test with known module/function; verify callback fires |
| Timing windows work | Set start/end times; verify delay only in window |
| Clock calibration is stable | Run calibration multiple times; values should be consistent |

All criteria verified by test suite (28/28 pass).
