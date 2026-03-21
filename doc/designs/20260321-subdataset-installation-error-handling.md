# Subdataset Installation and Error Handling Analysis

**Date**: 2026-03-21
**Status**: Analysis Complete → Implementation Needed
**Authors**: Claude Sonnet 4.5

## Summary

Analysis of subdataset installation requirements for metadata extraction and proper error threshold handling. Current implementation has a 50% error tolerance which is inappropriate for operational errors. Subdatasets must be installed before extraction, and the system should fail fast on operational errors.

## Problem Statement

**Current Behavior (WRONG)**:
1. Extract_study rule temporarily installs subdatasets, extracts metadata, then deinitializes them
2. Imaging metrics extraction tolerates up to 50% error rate before failing
3. Missing git-annex URLs (operational errors) counted toward tolerance threshold
4. study-ds001506 failed with 772.7% error rate due to uninitialized subdataset

**What Should Happen**:
1. Subdatasets should be installed and **kept installed** (no deinitialization)
2. Operational errors (missing subdatasets, git failures) should fail **immediately**
3. Expected failures (optional metrics, edge cases) can be tolerated with logging
4. Clear distinction between operational errors vs expected failures

## Current Implementation Review

### 1. Subdataset Installation (✅ Implemented)

**File**: `code/src/openneuro_studies/lib/subdataset_manager.py`

**Plan**: Implemented from `.claude/plans/async-nibbling-marshmallow.md`

**Functions**:
- `is_subdataset_initialized()` - Checks if subdataset has git tree and files
- `get_uninitialized_sourcedata()` - Finds sourcedata subdatasets needing init
- `initialize_subdatasets()` - Runs `git submodule update --init` (parallel capable)
- `snapshot_initialization_state()` - Records currently initialized subdatasets
- `restore_initialization_state()` - **Deinitializes temporary subdatasets** ⚠️

**Workflow Integration**: `code/workflow/Snakefile` lines 144-232

```python
rule extract_study:
    """Extract metadata for a single study."""
    run:
        # 1. Snapshot current state
        original_state = snapshot_initialization_state([study_path])

        # 2. Find uninitialized sourcedata
        to_init = get_uninitialized_sourcedata(study_path)

        # 3. Initialize if needed
        if to_init:
            init_results = initialize_subdatasets(to_init)
            # ⚠️ Logs warnings but continues even if some fail

        # 4. Extract metadata
        try:
            result = collect_study_metadata(study_path)
        finally:
            # 5. Restore state (deinitialize)
            restore_initialization_state(current_state, original_state)
            # ⚠️ This undoes the installation!
```

**Issues**:
- ❌ Step 5 deinitializes subdatasets after extraction (user wants to keep installed)
- ❌ Step 3 continues even if initialization fails (should fail fast)
- ❌ No verification that subdatasets are actually initialized before extraction

### 2. Error Threshold (❌ WRONG)

**File**: `code/src/bids_studies/extraction/subject.py` lines 339-359

```python
# Check if extraction errors exceed threshold
if all_errors and results:
    total_subjects = len(results)
    error_rate = len(all_errors) / total_subjects if total_subjects > 0 else 0

    # Fail if error rate exceeds 50% (indicates systemic problem)
    if error_rate > 0.5:  # ⚠️ WRONG - tolerates operational errors!
        raise RuntimeError(
            f"Extraction failed: {len(all_errors)} errors across {total_subjects} subjects "
            f"(error rate: {error_rate:.1%} exceeds 50% threshold)."
        )
```

**What This Does**:
- Allows up to 50% of extractions to fail before raising error
- Counts **all errors equally** (operational + expected)
- Example: ds001506 had 1190 errors / 154 subjects = 772.7% rate → failed
- If it was 77 errors / 154 subjects = 50% rate → **would have passed silently!**

**Why This Is Wrong**:
1. **Operational errors** (missing subdatasets, git failures) should fail immediately
2. **50% tolerance masks real problems** (partial extractions appear successful)
3. **No distinction** between "file not found" (expected) vs "git not initialized" (operational)
4. **Silent failures** when error rate < 50% → incomplete studies.tsv

### 3. Error Types Classification

We need to distinguish between two error categories:

#### Operational Errors (MUST fail immediately):
- Subdataset not initialized (missing .git tree)
- Git commands fail (git ls-tree, git describe)
- Git-annex not available when required
- Malformed BIDS structure (no dataset_description.json)
- I/O errors (permissions, disk full)
- Network failures (git clone timeout)

**Current handling**: Logged as warnings, counted toward 50% threshold ❌

**Should be**: Raise exception immediately, fail the entire extraction ✅

#### Expected Failures (Can tolerate with logging):
- Optional imaging metrics unavailable (file without remote URL for specific scan)
- Subject missing specific modality (no T1w, no BOLD)
- Empty sessions or subjects (valid BIDS but no data)
- Derivative-specific files not in source dataset

**Current handling**: Logged as warnings, counted toward 50% threshold ❌

**Should be**: Log at INFO level, don't count toward threshold, continue extraction ✅

### 4. Root Cause: ds001506 Failure

**Actual error**: Subdataset `study-ds001506/sourcedata/ds001506` not initialized

**Evidence**:
```bash
$ cd study-ds001506 && git submodule status
-0bd43a59def10a921cab51500b03122d1defc0aa sourcedata/ds001506
# ^ minus sign means uninitialized

$ cd sourcedata/ds001506 && ls -la
total 0  # Empty directory, no .git, no files

$ git annex whereis sub-01/.../bold.nii.gz
git-annex: First run: git-annex init
# git-annex not available because subdataset not initialized
```

**Failure chain**:
1. extract_study rule runs
2. `get_uninitialized_sourcedata()` finds sourcedata/ds001506 uninitialized
3. `initialize_subdatasets()` is called BUT FAILS SILENTLY (only logs warning)
4. Extraction proceeds with uninitialized subdataset
5. Imaging metrics extraction tries to get remote URLs
6. SparseDataset → git-annex → fails (not initialized)
7. 1190 "No remote URL found" errors logged (one per BOLD file)
8. Error rate 1190/154 = 772.7% > 50% → extraction fails
9. Snakemake job fails with RuntimeError

**Why it wasn't caught earlier**:
- `initialize_subdatasets()` failed but only logged warning (line 186)
- Extraction proceeded without verifying initialization succeeded
- 50% threshold allowed system to continue with broken state

## Required Changes

### Change 1: Keep Subdatasets Installed (Simplify)

**Rationale**: User wants subdatasets to remain installed for future operations.

**File**: `code/workflow/Snakefile` extract_study rule

**Current** (lines 174-231):
```python
# 1. Snapshot state
original_state = snapshot_initialization_state([study_path])

# 2-3. Find and initialize
to_init = get_uninitialized_sourcedata(study_path)
if to_init:
    init_results = initialize_subdatasets(to_init)

# 4. Extract
try:
    result = collect_study_metadata(study_path)
finally:
    # 5. Restore state (REMOVE THIS)
    restore_initialization_state(current_state, original_state)
```

**New**:
```python
# 1. Find uninitialized sourcedata
to_init = get_uninitialized_sourcedata(study_path)

# 2. Initialize if needed (FAIL FAST)
if to_init:
    logger.info(f"Initializing {len(to_init)} sourcedata subdatasets for {wildcards.study}")
    init_results = initialize_subdatasets(to_init, parent_path=Path("."))

    # FAIL IMMEDIATELY if any initialization fails
    failed = [p for p, success in init_results.items() if not success]
    if failed:
        raise RuntimeError(
            f"Failed to initialize required subdatasets for {wildcards.study}: {failed}. "
            "This is an operational error - extraction cannot proceed."
        )

# 3. Extract metadata (subdatasets now guaranteed initialized)
result = collect_study_metadata(study_path)

# 4. No restore step - keep subdatasets installed
```

**Benefits**:
- ✅ Simpler code (no snapshot/restore logic)
- ✅ Fails fast on initialization errors
- ✅ Subdatasets remain available for future operations
- ✅ No risk of partial state (all-or-nothing initialization)

**Functions to remove/deprecate**:
- `snapshot_initialization_state()` - no longer needed
- `restore_initialization_state()` - no longer needed

### Change 2: Remove Error Threshold Tolerance

**Rationale**: Operational errors should fail immediately, not be tolerated.

**File**: `code/src/bids_studies/extraction/subject.py` lines 339-366

**Current**:
```python
# Check if extraction errors exceed threshold
if all_errors and results:
    total_subjects = len(results)
    error_rate = len(all_errors) / total_subjects if total_subjects > 0 else 0

    logger.warning(f"Extraction completed with {len(all_errors)} errors ...")

    # Fail if error rate exceeds 50%
    if error_rate > 0.5:
        raise RuntimeError(...)
elif all_errors and not results:
    # All extractions failed - critical error
    raise RuntimeError(...)
```

**New**:
```python
# Report any extraction errors (no tolerance)
if all_errors:
    # Distinguish operational errors from expected failures
    # For now, treat ALL errors from extraction as operational
    # (imaging metrics errors should be caught earlier in workflow)

    error_summary = "\n".join(all_errors[:10])
    error_msg = (
        f"Extraction errors detected for {len(all_errors)} operations "
        f"across {len(results)} subjects/sessions.\n"
        f"First errors:\n{error_summary}"
    )

    if not results:
        # No successful extractions - critical failure
        raise RuntimeError(f"Extraction completely failed: {error_msg}")
    else:
        # Some errors occurred - log as WARNING but continue
        # This allows expected failures (missing optional modalities)
        logger.warning(error_msg)

        # TODO: Classify errors into operational vs expected
        # For operational errors, should raise exception here

return results, all_errors
```

**Alternative (stricter)**:
```python
# Zero tolerance for any errors
if all_errors:
    error_summary = "\n".join(all_errors[:10])
    raise RuntimeError(
        f"Extraction failed with {len(all_errors)} errors. "
        f"No tolerance for operational errors.\n"
        f"First errors:\n{error_summary}"
    )
```

**Decision needed**:
- **Option A**: Zero tolerance (fail on any error)
- **Option B**: Classify errors, fail only on operational errors

### Change 3: Add Imaging Metrics Validation

**Rationale**: Catch missing git-annex earlier, before attempting extraction.

**File**: `code/src/openneuro_studies/metadata/summary_extractor.py`

**Add validation before imaging metrics extraction**:

```python
def extract_imaging_metrics(study_path: Path) -> dict[str, Any]:
    """Extract imaging metrics from sourcedata.

    Validates that sourcedata is initialized and git-annex is available
    before attempting to extract metrics.
    """
    result = {...}

    sourcedata_path = study_path / "sourcedata"
    if not sourcedata_path.exists():
        return result

    for source_dir in sourcedata_path.iterdir():
        if not source_dir.is_dir():
            continue

        # VALIDATE: Check subdataset is initialized
        if not is_subdataset_initialized(source_dir):
            raise RuntimeError(
                f"Sourcedata subdataset not initialized: {source_dir}. "
                "This is an operational error - run initialization first."
            )

        # VALIDATE: Check git-annex is available
        try:
            result = subprocess.run(
                ["git", "-C", str(source_dir), "annex", "version"],
                capture_output=True,
                timeout=5,
                check=True
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            raise RuntimeError(
                f"Git-annex not initialized in {source_dir}. "
                "This is an operational error - cannot extract imaging metrics."
            )

        # Now proceed with extraction (failures here are expected)
        try:
            with SparseDataset(source_dir) as ds:
                # Extract metrics...
                pass
        except Exception as e:
            # Log but don't fail - this might be expected (missing files)
            logger.info(f"Could not extract imaging metrics from {source_dir}: {e}")
```

### Change 4: Implement logs/errors.tsv (Per Spec)

**Rationale**: Centralized error tracking as specified in spec/002-error-recovery.

**File**: `code/workflow/Snakefile`

**Add to extract_study rule**:
```python
# After extraction
if errors:
    # Append to logs/errors.tsv
    errors_log = Path("logs/errors.tsv")
    errors_log.parent.mkdir(exist_ok=True)

    # Create if doesn't exist
    if not errors_log.exists():
        with open(errors_log, "w") as f:
            f.write("study_id\terror_type\tcount\tdetails\ttimestamp\n")

    # Append errors
    import datetime
    timestamp = datetime.datetime.now().isoformat()
    with open(errors_log, "a") as f:
        for error in errors[:10]:  # Limit to first 10
            # Classify error type
            error_type = "imaging" if "imaging metrics" in error else "extraction"
            f.write(f"{wildcards.study}\t{error_type}\t1\t{error}\t{timestamp}\n")
```

## Edge Cases Analysis

### Case 1: Subdataset Already Partially Initialized

**Scenario**: Subdataset has .git but working tree is empty

**Current behavior**: `is_subdataset_initialized()` returns False (checks for files)

**Action needed**: ✅ Already handled - will reinitialize

### Case 2: Git-annex Not Initialized in Sourcedata

**Scenario**: Subdataset initialized but `git annex init` never run

**Current behavior**: Imaging metrics fail with "git-annex: First run: git-annex init"

**Action needed**: Add pre-flight check (Change 3 above)

### Case 3: Network Failure During Initialization

**Scenario**: `git submodule update --init` times out

**Current behavior**: `_initialize_single_subdataset()` catches timeout, returns False

**Action needed**: ✅ Will now fail fast with RuntimeError (Change 1)

### Case 4: Sourcedata Missing from GitHub

**Scenario**: .gitmodules references non-existent repository

**Current behavior**: Git submodule init fails, logged as warning

**Action needed**: ✅ Will now fail fast with RuntimeError (Change 1)

### Case 5: Study Has No Sourcedata

**Scenario**: Derivative-only study (no sourcedata/ directory)

**Current behavior**: `get_uninitialized_sourcedata()` returns empty list

**Action needed**: ✅ Already handled - skips initialization

### Case 6: Imaging Metrics Optional

**Scenario**: Study organized but imaging metrics not needed yet

**Current behavior**: Always tries to extract imaging metrics (include_imaging=True)

**Potential issue**: If subdataset not initialized, will fail hard (Change 3)

**Action needed**: Either:
- Keep subdatasets always initialized (recommended)
- Add `--no-imaging` flag to skip metrics extraction
- Make imaging metrics extraction conditional on subdataset state

**Recommendation**: Keep all sourcedata initialized (simplest)

## Implementation Plan

### Phase 1: Simplify Workflow (Keep Installed)

1. **Modify** `code/workflow/Snakefile` extract_study rule:
   - Remove `snapshot_initialization_state()` call
   - Remove `restore_initialization_state()` call in finally block
   - Add fail-fast check after `initialize_subdatasets()`

2. **Deprecate** functions in `subdataset_manager.py`:
   - Mark `snapshot_initialization_state()` as deprecated
   - Mark `restore_initialization_state()` as deprecated
   - Add docstring notes: "No longer used - subdatasets kept installed"

3. **Update** plan document `.claude/plans/async-nibbling-marshmallow.md`:
   - Mark as "Superseded" status
   - Note: "Implementation simplified - subdatasets now kept installed"

### Phase 2: Fix Error Handling

1. **Modify** `code/src/bids_studies/extraction/subject.py`:
   - Remove 50% threshold check (lines 352-359)
   - Change to zero-tolerance or classification-based approach
   - Update docstring to remove "50% threshold" reference

2. **Add** validation in `summary_extractor.py`:
   - Pre-flight check for subdataset initialization
   - Pre-flight check for git-annex availability
   - Fail fast with clear error messages

3. **Implement** `logs/errors.tsv`:
   - Add error logging to extract_study rule
   - TSV format with columns: study_id, error_type, count, details, timestamp

### Phase 3: Fix ds001506 Immediately

```bash
cd /home/yoh/proj/openneuro/OpenNeuroStudies
cd study-ds001506
git submodule update --init sourcedata/ds001506
# Verify
git submodule status sourcedata/ds001506
# Should show space (initialized) instead of minus
```

### Phase 4: Testing

1. **Rerun extraction** for ds001506:
   ```bash
   make extract-one STUDY=study-ds001506
   ```

2. **Test edge cases**:
   - Uninitialized subdataset (should fail fast now)
   - Partially initialized (should reinitialize)
   - Missing git-annex (should fail with clear message)

3. **Verify** all studies can extract:
   ```bash
   make extract CORES=4
   ```

## Success Criteria

1. ✅ ds001506 extraction succeeds after subdataset initialization
2. ✅ Extract_study rule no longer deinitializes subdatasets
3. ✅ Initialization failures cause immediate failure (no 50% tolerance)
4. ✅ Clear error messages distinguish operational vs expected failures
5. ✅ logs/errors.tsv exists and records extraction errors
6. ✅ All studies in sample set extract successfully

## Open Questions

### Q1: Should we remove snapshot/restore functions entirely?

**Options**:
- A. Keep but mark deprecated (backward compatibility)
- B. Remove entirely (cleaner codebase)

**Recommendation**: Mark deprecated for now, remove in future version.

### Q2: Zero tolerance or error classification?

**Options**:
- A. Zero tolerance - fail on any error (strict)
- B. Classify errors - fail only on operational errors (flexible)

**Recommendation**: Start with zero tolerance (simpler), add classification later if needed.

### Q3: Should imaging metrics be optional?

**Options**:
- A. Always require (current behavior)
- B. Make optional with --no-imaging flag
- C. Conditional based on subdataset state

**Recommendation**: Always require (subdatasets always initialized now).

## References

- Plan: `.claude/plans/async-nibbling-marshmallow.md`
- Spec: `specs/002-error-recovery/` (if exists)
- Implementation:
  - `code/src/openneuro_studies/lib/subdataset_manager.py`
  - `code/workflow/Snakefile` (lines 144-232)
  - `code/src/bids_studies/extraction/subject.py` (lines 339-366)
