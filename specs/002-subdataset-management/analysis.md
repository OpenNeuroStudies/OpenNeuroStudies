# Analysis: Subdataset Management and Metadata Extraction Issues

## Current Problems

### 1. Derivatives Stats Not Computed
**Symptom**: `studies+derivatives.tsv` shows all `n/a` for size_total, size_annexed, file_count
**Root Cause**: Code in `studies_plus_derivatives_tsv.py` lines 141-145 hardcodes these to `n/a` with TODO comments
**Specification**: FR-010 requires "size statistics from git annex info"

### 2. Bold Voxels Shows n/a
**Symptom**: `bold_voxels` column in `studies.tsv` shows `n/a` even after extraction
**Root Cause**: TBD - needs investigation of sparse access and fsspec functionality
**Specification**: FR-032 requires bold_voxels extraction via sparse access

### 3. Permanent Installation Required
**Symptom**: Makefile `studies-init` target permanently installs sourcedata/derivatives subdatasets
**Root Cause**: Current workflow requires manual `make studies-init` before extraction
**Specification Violation**: Design doc states "Install sourcedata subdatasets 'temporarily only' for extraction" and "Preserve state: if subdataset already installed, don't uninstall after"

### 4. Missing Columns
**Requested**:
- `raw_bids_version` - BIDS version from raw sourcedata
- `raw_hed_version` - HED version from raw sourcedata (rename from `hed_version`)
- `bold_timepoints` - Sum of timepoints across all BOLD runs
- `bold_tasks` - Sorted comma-separated set of tasks from BOLD files

## Specification Gaps

### Current Design Doc (002-subdataset-management/design.md)

**Line 12 states**: "Does NOT need derivatives initialized (confirmed: no extraction code reads from derivatives/)"

**This is incorrect**. The spec (FR-010) requires derivative stats extraction, which DOES need derivatives initialized to run git-annex info.

**Line 14-16 correctly states**:
- "Install sourcedata subdatasets 'temporarily only' for extraction"
- "Preserve state: if subdataset already installed, don't uninstall after"

But this is only implemented for sourcedata during study metadata extraction, NOT for derivatives during derivatives metadata extraction.

### Required Updates to Specification

1. **Clarify temporary installation applies to BOTH sourcedata AND derivatives**
2. **Document that derivatives need temporary installation for git-annex info stats**
3. **Remove the incorrect statement that derivatives don't need initialization**
4. **Add FR for new columns: raw_bids_version, raw_hed_version, bold_timepoints, bold_tasks**

## Implementation Analysis

### What Works

✅ **Sourcedata temporary installation during study extraction**
- `extract_study_with_subdatasets()` uses `TemporarySubdatasetInstall` context manager
- Installs sourcedata subdatasets, extracts metadata, drops after
- Preserves already-installed subdatasets

✅ **Study metadata extraction**
- Subjects_num, bold_num, t1w_num, bold_size, t1w_size all working
- Git tree access working via initialized subdatasets

### What Doesn't Work

❌ **Derivatives stats extraction**
- `collect_derivatives_for_study()` hardcodes all stats to n/a
- No temporary installation of derivative subdatasets
- No git-annex info call to get sizes

❌ **Bold voxels extraction**
- Returns n/a even though sparse access code exists
- Need to investigate why `extract_voxel_counts()` isn't working

❌ **Makefile forces permanent installation**
- `studies-init` target runs `datalad get -n -r -R1` on sourcedata/derivatives
- This makes subdatasets permanently installed
- Violates temporary installation requirement

❌ **Missing column extractions**
- No code to extract BIDSVersion from sourcedata (always extracted from study dataset_description.json)
- HEDVersion extraction exists but not renamed
- No bold_timepoints extraction
- No bold_tasks extraction

## Root Cause Summary

The core issue is **incomplete implementation of temporary subdataset management**:

1. **For study metadata extraction**: Temporary installation works ✅
2. **For derivatives metadata extraction**: NO temporary installation - stats hardcoded to n/a ❌
3. **Makefile workaround**: Forces permanent installation to make things work, but violates spec ❌

## Solution Architecture

### 1. Extend Temporary Installation to Derivatives

Create `extract_derivative_with_subdatasets()` function similar to `extract_study_with_subdatasets()`:

```python
def extract_derivative_with_subdatasets(
    derivative_path: Path,
    study_path: Path
) -> dict[str, Any]:
    """Extract derivative metadata with automatic subdataset management.

    Temporarily installs derivative subdataset if needed, extracts stats
    via git-annex info, then drops if it wasn't installed before.
    """
    with TemporarySubdatasetInstall(study_path, subdataset_paths=[derivative_path]):
        # Extract git-annex stats
        result = extract_derivative_stats(derivative_path)
    return result
```

### 2. Implement Derivative Stats Extraction

Replace hardcoded n/a values with actual git-annex info extraction:

```python
def extract_derivative_stats(derivative_path: Path) -> dict[str, Any]:
    """Extract derivative stats using git-annex info.

    Returns:
        Dict with size_total, size_annexed, file_count
    """
    # Run: git -C derivative_path annex info --json
    # Parse output for size stats
```

### 3. Remove Permanent Installation from Makefile

**Current**:
```makefile
studies-init:
    datalad get -s origin study-ds00*
    datalad get -n -r -R1 sourcedata derivatives
```

**Updated**:
```makefile
studies-init:
    datalad get -s origin study-ds00*
    # Removed: sourcedata/derivatives initialization
    # Extraction handles temporary installation automatically
```

### 4. Implement Missing Column Extractions

**raw_bids_version**: Extract from `sourcedata/*/dataset_description.json` (first sourcedata if multiple)
**raw_hed_version**: Rename existing `hed_version` extraction, extract from sourcedata
**bold_timepoints**: Sum timepoints from NIfTI headers via sparse access
**bold_tasks**: Parse _task- entities from func/*.nii.gz filenames

### 5. Debug Bold Voxels Extraction

Investigate why `extract_voxel_counts()` returns n/a:
- Check if sparse access is available (fsspec installed?)
- Check if sourcedata subdatasets are installed when extraction runs
- Check if NIfTI headers are accessible via sparse access

## Implementation Plan

### Phase 1: Fix Derivatives Stats (High Priority)

1. **Update design spec** to clarify derivatives need temporary installation
2. **Implement `extract_derivative_stats()`** using git-annex info
3. **Update `collect_derivatives_for_study()`** to use temporary installation
4. **Test** that derivatives stats are populated

### Phase 2: Remove Permanent Installation (High Priority)

1. **Update Makefile** to remove sourcedata/derivatives from studies-init
2. **Update documentation** to clarify extraction handles installation
3. **Test** that extraction works without pre-initialized subdatasets

### Phase 3: Add New Columns (Medium Priority)

1. **Add raw_bids_version extraction** from sourcedata
2. **Rename hed_version to raw_hed_version** and extract from sourcedata
3. **Implement bold_timepoints extraction** via sparse NIfTI access
4. **Implement bold_tasks extraction** from filenames
5. **Update STUDIES_COLUMNS** with new columns

### Phase 4: Debug Bold Voxels (Medium Priority)

1. **Add debug logging** to extract_voxel_counts()
2. **Verify sparse access** is working
3. **Test with known dataset** that has BOLD data
4. **Fix root cause** based on findings

## Testing Strategy

### Unit Tests
- Test derivative stats extraction with git-annex info
- Test temporary installation preserves state
- Test new column extractions

### Integration Tests
- Test full workflow in fresh clone WITHOUT studies-init
- Verify sourcedata subdatasets are temporarily installed during extraction
- Verify derivative subdatasets are temporarily installed during derivatives-tsv generation
- Verify all stats populated correctly

### Regression Tests
- Verify existing working extractions still work (subjects_num, bold_num, etc.)
- Verify temporary installation doesn't break parallel execution

## Success Criteria

✅ studies+derivatives.tsv shows real values for size_total, size_annexed, file_count
✅ bold_voxels shows real values (not n/a)
✅ New columns populated: raw_bids_version, raw_hed_version, bold_timepoints, bold_tasks
✅ Extraction works in fresh clone WITHOUT running make studies-init
✅ Subdatasets are NOT permanently installed after extraction
✅ Makefile simplified - studies-init only installs study-* subdatasets
