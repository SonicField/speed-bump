# Supervisor State: speed-bump NBS Recovery

## Terminal Goal

Get speed-bump NBS-compliant before applying it to real AI training work. This means:
1. All claims verified (no bullshit)
2. Tests pass
3. Known limitations documented
4. Epistemic structure established (plan, progress files)

## Current Phase

Gap analysis - identifying what needs verification before declaring NBS compliance.

## Context From Discovery

**Project purpose**: Identify which Python code is actually on the critical path in GPU-accelerated async systems by artificially slowing code and measuring throughput impact.

**Key insight**: Time spent ≠ time that matters. Traditional profilers miss this.

**Implementation**: PEP 669 monitoring hooks + C extension spin delay.

**Known limitations flagged by human**:
- Behaviour in free-threaded Python (PEP 703) is uncertain
- Can only slow interpreted Python, not C extensions
- (Speculation): eBPF might be alternative approach

## Active Workers

None.

## Workers Since Last Self-Check

1

## Gap Analysis Questions

1. ~~Do the tests actually pass?~~ **VERIFIED**: Yes - 28/28 tests pass. C extension compiles cleanly.
2. Are claims in docs/README verified by tests? (partially verified by worker-001)
3. Free-threaded Python behaviour - documented or tested?
4. "Only Python interpreter code" limitation - documented?
5. Statistics collection (unchecked in README) - what's the status?

## 3Ws + Self-Check Log

### Worker: worker-001 (Build/Test Verification) - 2026-02-01

**What went well:**
- Worker adapted to environment constraints (no pip, no pytest) without getting stuck
- Direct gcc compilation worked cleanly
- Created comprehensive manual test runner covering all major functionality
- Clear, evidence-based answers to success criteria

**What didn't work:**
- Initial task assumed pip/pytest would be available - environment constraints should be in task brief
- Required multiple permission approvals mid-task (could have used broader permission grant)

**What we can do better:**
- Include environment constraints in worker task descriptions (e.g., "no pip access, may need manual build")
- Consider passing --dangerouslyAllowAllBashCommands or similar for trusted workers

**Key findings:**
- Clock overhead: 25 ns (plausible for modern x86)
- C extension: compiles without warnings
- All functionality verified: calibration, spin delay, patterns, config, monitoring lifecycle
