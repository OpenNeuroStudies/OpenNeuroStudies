# Subdataset Initialization Bug Analysis

**Date**: 2026-03-10
**Status**: Critical bug identified, fix required

## Executive Summary

✅ **Fixed**: False positive detection bug in `is_subdataset_initialized()`
❌ **New Critical Bug**: Subdataset initialization command runs from wrong repository context

**Impact**: 72.5% of studies (29/40) have no metadata because subdatasets failed to initialize.

## Current State

### Extraction Results
- **Total studies**: 40
- **Studies with real metadata**: 11 (27.5%)
- **Studies with n/a metadata**: 29 (72.5%)
- **Subdatasets fully initialized**: 15/49 (30.6%)

### Which Studies Have Real Metadata
The 11 studies that succeeded were **already initialized before this extraction run**:
- study-ds002766
- study-ds002843
- study-ds004044
- study-ds004078
- study-ds004496
- study-ds004636
- study-ds004746
- study-ds005237
- study-ds005256
- study-ds006131
- study-ds006191 (has 3 sourcedata subdatasets)

These were manually initialized during earlier development/testing.

## Root Cause Analysis

### The Bug
`subdataset_manager.py:120` runs:
```python
["git", "-C", str(parent_path), "submodule", "update", "--init", str(subdataset_path)]
```

Where:
- `parent_path` = `/home/yoh/proj/openneuro/OpenNeuroStudies` (parent repo root)
- `subdataset_path` = `study-ds000030/sourcedata/ds000030` (relative path)

### Why It Fails
Git submodules are hierarchical:
- **Parent repo** `.gitmodules` contains: `study-ds000030`, `study-ds000001`, etc. (top-level studies)
- **Study repo** `.gitmodules` contains: `sourcedata/ds000030`, `derivatives/...`, etc. (nested subdatasets)

The command runs from the **parent repo** but tries to initialize a subdataset registered in the **study repo**.

Result: `error: pathspec 'study-ds000030/sourcedata/ds000030' did not match any file(s) known to git`

### Verification

Manual test from correct context succeeds:
```bash
cd study-ds000030
git submodule update --init sourcedata/ds000030
# ✓ Success: Cloning into '.../study-ds000030/sourcedata/ds000030'...
```

## The Fix

### Required Changes

**File**: `code/src/openneuro_studies/lib/subdataset_manager.py`

Update `_initialize_single_subdataset()` to:

1. **Detect immediate parent repository**:
   - For `study-ds000030/sourcedata/ds000030` → parent is `study-ds000030`
   - For nested derivatives: `study-ds000030/derivatives/fMRIPrep-21.0.1` → parent is `study-ds000030`

2. **Make path relative to immediate parent**:
   - Absolute: `/path/to/study-ds000030/sourcedata/ds000030`
   - Relative to study: `sourcedata/ds000030`

3. **Run git from immediate parent**:
   ```python
   ["git", "-C", str(study_path), "submodule", "update", "--init", "sourcedata/ds000030"]
   ```

### Implementation Sketch

```python
def _initialize_single_subdataset(subdataset_path: Path, parent_path: Path) -> tuple[Path, bool]:
    """Initialize a single subdataset from its immediate parent repository."""

    # Find immediate parent repo (the study directory)
    # For study-ds000030/sourcedata/ds000030 -> study-ds000030
    study_path = subdataset_path.parent.parent

    # Make path relative to study repo
    # From: parent_path/study-ds000030/sourcedata/ds000030
    # To: sourcedata/ds000030
    relative_to_study = subdataset_path.relative_to(study_path)

    result = subprocess.run(
        ["git", "-C", str(study_path), "submodule", "update", "--init", str(relative_to_study)],
        capture_output=True,
        timeout=300,
        check=False,
        text=True,
    )

    # ... rest of error handling
```

### Edge Cases to Handle

1. **Multi-level nesting**: What if we have `study-ds/sourcedata/ds/sub-01`?
   → Need to walk up the directory tree looking for `.gitmodules` containing the subdataset

2. **Derivative subdatasets**: `study-ds000030/derivatives/fMRIPrep-21.0.1`
   → Same logic applies (parent is still `study-ds000030`)

3. **Top-level subdatasets**: `study-ds000030` itself
   → Already works (registered in parent repo .gitmodules)

### Robust Solution

```python
def find_immediate_parent_repo(subdataset_path: Path, repo_root: Path) -> Path | None:
    """Find the immediate parent repository that registers this subdataset.

    Walks up directory tree from subdataset, checking each level's .gitmodules
    for an entry matching this subdataset.

    Args:
        subdataset_path: Path to subdataset (e.g., study-ds000030/sourcedata/ds000030)
        repo_root: Root of top-level repository

    Returns:
        Path to immediate parent repo, or None if not found
    """
    current = subdataset_path.parent

    while current >= repo_root:
        gitmodules = current / ".gitmodules"
        if not gitmodules.exists():
            current = current.parent
            continue

        # Check if this .gitmodules contains subdataset_path
        relative_path = subdataset_path.relative_to(current)

        # Read .gitmodules and look for path = {relative_path}
        with open(gitmodules) as f:
            content = f.read()
            if f"path = {relative_path}" in content:
                return current

        current = current.parent

    return None
```

## Testing Plan

### Unit Tests

Add to `code/tests/unit/test_subdataset_manager.py`:

```python
def test_find_immediate_parent_repo():
    """Test finding immediate parent repo for nested subdatasets."""
    # Create mock structure:
    # parent/
    #   .gitmodules (has study-ds000030)
    #   study-ds000030/
    #     .gitmodules (has sourcedata/ds000030)
    #     sourcedata/
    #       ds000030/

    # Test: sourcedata/ds000030 -> should return study-ds000030
    # Test: study-ds000030 -> should return parent
```

### Integration Test

Use study-ds000030 (which failed in the extraction):

```bash
# 1. Deinitialize subdataset
cd study-ds000030 && git submodule deinit -f sourcedata/ds000030 && cd ..

# 2. Verify it's uninitialized
python3 code/tests-adhoc/analyze_extraction_state.py | grep "ds000030"
# Should show NOT initialized

# 3. Run extraction for just this study
snakemake -s code/workflow/Snakefile --cores 1 \
  --forcerun extract_study .snakemake/extracted/study-ds000030.json

# 4. Verify subdataset was initialized and extracted
cat .snakemake/extracted/study-ds000030.json | jq '.subjects_num'
# Should show real number, not "n/a"

# 5. Verify it was deinitialized (state restored)
python3 code/tests-adhoc/analyze_extraction_state.py | grep "ds000030"
# Should show NOT initialized again
```

## Secondary Bug Fixed

**File**: `code/tests-adhoc/analyze_extraction_state.py:50`

**Bug**: Path comparison without resolving
```python
# Before (incorrect)
result["is_own_repo"] = (git_root == subdataset_path)

# After (correct)
git_root = Path(proc.stdout.strip()).resolve()
subdataset_resolved = subdataset_path.resolve()
result["is_own_repo"] = (git_root == subdataset_resolved)
```

**Impact**: Analysis script incorrectly reported "Is own repo: 0" for all subdatasets, even initialized ones. Now correctly detects 15/49 initialized.

## Next Steps

1. ✅ Document bug analysis (this file)
2. ⏳ Implement `find_immediate_parent_repo()` function
3. ⏳ Update `_initialize_single_subdataset()` to use correct parent context
4. ⏳ Add unit tests
5. ⏳ Run integration test with single study
6. ⏳ Run full extraction workflow
7. ⏳ Verify `make analyze-state` shows >90% metadata completion

## References

- Plan: `/home/yoh/.claude/plans/async-nibbling-marshmallow.md`
- Snakemake workflow: `code/workflow/Snakefile`
- Subdataset manager: `code/src/openneuro_studies/lib/subdataset_manager.py`
- Extraction logs: `.duct/logs/2026.03.10T08.56.14-315315_stdout`
