# Recovery Plan: speed-bump

**Based on**: `.nbs/discovery-report.md`
**Date**: 2026-02-01
**Mode**: Supervisor-led with workers

---

## Steps

### Step 1: Create plan file
- **What**: Create `01-02-2026-speed-bump-plan.md` with terminal goal and prioritised work
- **Why**: NBS compliance requires explicit plan file
- **Reversible**: Delete file
- **Status**: Complete

### Step 2: Create progress log
- **What**: Create `01-02-2026-speed-bump-progress.md` documenting this recovery session
- **Why**: NBS compliance requires progress tracking
- **Reversible**: Delete file
- **Status**: Complete

### Step 3: Document limitations in README
- **What**: Add "Limitations" section to README.md covering:
  - Free-threaded Python (unknown/untested)
  - C extension code (cannot be slowed)
  - GIL implications (spin delay holds GIL)
- **Why**: Discovery identified these as undocumented known limitations
- **Reversible**: Revert git change
- **Status**: Complete

### Step 4: Annotate Statistics collection uncertainty
- **What**: Keep the TODO, add comments explaining we don't know what this means, suggest /nbs-investigation
- **Why**: Honest about uncertainty; defers decision to investigation rather than guessing
- **Reversible**: Revert git change
- **Status**: Complete
- **Decision**: Human chose to keep with uncertainty annotation

### Step 5: Add manual build instructions
- **What**: Add section to README for building without pip (direct gcc)
- **Why**: Worker-001 had to figure this out; should be documented
- **Reversible**: Revert git change
- **Status**: Complete

### Step 6: Commit recovery changes
- **What**: Git commit all changes with clear message
- **Why**: Preserve recovery state in version control
- **Reversible**: Git revert
- **Status**: Complete (commit 133b703)

### Step 7: Verify final state
- **What**: Confirm all artefacts preserved, tests still pass, structure complete
- **Why**: Final check before declaring recovery complete
- **Reversible**: N/A (read-only)
- **Status**: Complete

---

## Decision Required

**Step 4 requires your input**: The README shows "Statistics collection" as an unchecked TODO. Options:

1. **Remove** - Delete the TODO line (we're not doing it)
2. **Keep with context** - Add a note explaining what it would collect
3. **Defer** - Leave as-is, address later

Which do you prefer?
