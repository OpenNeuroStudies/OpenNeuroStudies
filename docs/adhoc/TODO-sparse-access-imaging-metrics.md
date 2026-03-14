# TODO: Fix Sparse Access for Imaging Metrics Extraction

**Priority**: HIGH  
**Status**: NOT STARTED  
**Created**: 2026-03-14  
**Related**: FR-042 Hierarchical Statistics

---

## Problem Statement

Imaging metrics (bold_duration_total, bold_voxels_total, bold_voxels_mean, bold_duration_mean) are extracted as "n/a" even when BOLD files exist and are countable.

**Example** (study-ds002766/sourcedata/sourcedata+subjects+sessions.tsv):
```tsv
source_id  subject_id  session_id  bold_num  bold_size    bold_duration_total  bold_voxels_total
ds002766   sub-cast1   ses-01      3         149937128    n/a                  n/a
```

**Expected**: Real values for imaging metrics  
**Actual**: "n/a" across all sessions

---

## Root Cause Analysis

### Current State
1. ✅ Subdatasets initialized (git tree present)
2. ❌ Annexed files NOT fetched (broken symlinks)
   ```bash
   $ file study-ds002766/sourcedata/ds002766/.../bold.nii.gz
   broken symbolic link to ../../../.git/annex/objects/.../MD5E-s15235034...nii.gz
   ```
3. ✅ Web URLs available via git-annex:
   ```bash
   $ git annex whereis ...
   s3-PUBLIC: https://s3.amazonaws.com/openneuro.org/ds002766/.../bold.nii.gz?versionId=...
   ```
4. ❌ **BUG**: `SparseDataset` NOT using web URLs for file access

### Code Flow
```python
# code/src/bids_studies/extraction/subject.py:127-128
if include_imaging and bold_files:
    _extract_imaging_metrics(ds, bold_files, result)

# code/src/bids_studies/extraction/subject.py:226-252
def _extract_imaging_metrics(ds, bold_files, result):
    for bold_file in bold_files:
        try:
            with ds.open_file(bold_file) as f:  # <-- FAILS HERE
                header_info = _extract_nifti_header_from_gzip_stream(f)
                # ...
        except NetworkError:
            raise  # Propagate network errors
        except Exception as e:
            logger.debug(f"Failed to read BOLD header: {e}")  # <-- SILENTLY CONTINUES
            continue
```

**Problem**: When `ds.open_file()` fails (can't access broken symlink), exception is caught and logged as DEBUG (not visible), extraction continues, result stays as "n/a".

---

## Tasks

### Task 1: Fix SparseDataset Web URL Access

**File**: `code/src/bids_studies/sparse/...` (find actual location)

**Investigation needed**:
- [ ] Locate `SparseDataset` implementation
- [ ] Check how `open_file()` is implemented
- [ ] Verify if it uses git-annex whereis to get web URLs
- [ ] Test if it can stream from HTTPS URLs
- [ ] Fix or implement web URL streaming

**Expected behavior**:
```python
with SparseDataset(path) as ds:
    # When file is a broken symlink (annexed, not fetched):
    # 1. Run git annex whereis <file>
    # 2. Extract web URL (s3-PUBLIC or similar)
    # 3. Stream file content from URL
    # 4. Return file-like object for header parsing
    with ds.open_file("sub-01/func/sub-01_bold.nii.gz") as f:
        data = f.read(1024*1024)  # Read first 1MB for header
```

### Task 2: Improve Error Visibility

**File**: `code/src/bids_studies/extraction/subject.py:226-252`

**Current behavior** (WRONG):
```python
except Exception as e:
    logger.debug(f"Failed to read BOLD header: {e}")  # DEBUG level - hidden!
    continue  # Silently continue, leave metrics as n/a
```

**Required behavior**:
```python
except Exception as e:
    logger.warning(f"Failed to extract imaging metrics from {bold_file}: {e}")
    # Option 1: Continue but log at WARNING level (visible)
    # Option 2: Raise exception after N failures
    # Option 3: Add to error summary, report at end
    continue
```

**Rationale**: Critical extraction failures must be visible, not hidden at DEBUG level.

### Task 3: Add Error Handling to Workflow

**File**: `code/workflow/Snakefile`

**Current** (extract_study rule):
```python
try:
    extract_study_stats(study_path, include_imaging=True, write_files=True)
except Exception as e:
    logger.warning(f"Failed to extract: {e}")  # Continues silently?
```

**Required**:
- [ ] Capture extraction warnings/errors
- [ ] Report summary at end of run
- [ ] Fail workflow if critical errors exceed threshold
- [ ] Write error log to `.snakemake/errors.tsv` or similar

### Task 4: Update Constitution

**File**: `.specify/memory/constitution.md`

**Add new requirement** to Principle V (Observability & Monitoring):

```markdown
### Error Visibility

Critical errors during metadata extraction MUST be visible and NOT hidden:

- Extraction failures MUST log at WARNING or ERROR level (not DEBUG)
- Silent failures are FORBIDDEN - exceptions must propagate or be reported
- Workflows MUST provide error summaries (e.g., "15/40 studies failed imaging metrics")
- Error logs MUST be written to accessible locations (logs/, .snakemake/errors.tsv)
- **Rationale**: Hidden errors lead to incomplete metadata that appears valid but contains "n/a" values. Users must know when extraction fails so they can investigate and fix root causes.
```

---

## Acceptance Criteria

### For Task 1 (SparseDataset Fix):
- [ ] Can extract imaging metrics from annexed files without downloading
- [ ] Streams NIfTI headers from git-annex web URLs
- [ ] Unit test: Mock git-annex whereis, verify HTTP streaming works
- [ ] Integration test: Extract from ds002766 session, verify metrics != "n/a"

### For Task 2 (Error Visibility):
- [ ] Extraction failures log at WARNING level (visible in console)
- [ ] Can see errors in Snakemake output
- [ ] Error messages include file path and exception details

### For Task 3 (Workflow Error Handling):
- [ ] `make metadata` shows summary: "40 studies processed, 5 warnings"
- [ ] Failed extractions don't silently produce "n/a" values
- [ ] Error log file created with details

### For Task 4 (Constitution):
- [ ] Constitution updated with Error Visibility requirement
- [ ] Version bumped (1.20251218.1 → 1.20251218.2)
- [ ] SYNC IMPACT REPORT updated

---

## Testing Plan

### Test 1: Sparse Access with Annexed Files
```bash
# Start with initialized subdataset, no content fetched
cd study-ds002766/sourcedata/ds002766
git annex drop sub-cast1/ses-01/func/*_bold.nii.gz  # Ensure not present
cd ../../..

# Run extraction
python3 << 'PYEOF'
from pathlib import Path
from bids_studies.extraction.subject import extract_subjects_stats

result = extract_subjects_stats(
    Path("study-ds002766/sourcedata/ds002766"),
    "ds002766",
    include_imaging=True
)

# Check first session
session1 = [r for r in result if r["session_id"] == "ses-01"][0]
print(f"bold_duration_total: {session1['bold_duration_total']}")
print(f"bold_voxels_total: {session1['bold_voxels_total']}")

# EXPECTED: Real numbers, not "n/a"
assert session1["bold_duration_total"] != "n/a", "Duration extraction failed!"
assert session1["bold_voxels_total"] != "n/a", "Voxels extraction failed!"
PYEOF
```

### Test 2: Error Visibility
```bash
# Force extraction to fail (corrupt file, network error, etc.)
# Verify error appears in output

make metadata 2>&1 | grep -i "warning\|error" | head -20

# EXPECTED: See warnings about failed extractions
# NOT EXPECTED: Silent success with n/a values
```

### Test 3: End-to-End Workflow
```bash
# Full workflow with error reporting
make extract 2>&1 | tee /tmp/extract.log

# Check for error summary
grep -i "summary\|failed\|warning" /tmp/extract.log

# Verify error log exists
test -f .snakemake/errors.tsv && echo "Error log created" || echo "No error log"
```

---

## Related Issues

- FR-042: Hierarchical statistics extraction (completed but has this bug)
- Subdataset management: Initialization without content fetching
- SparseDataset design: Should work without fetching annexed content
- Constitution Principle V: Observability requirements

---

## Implementation Priority

**CRITICAL**: This bug affects ALL multi-session studies with annexed data:
- Imaging metrics are core metadata (bold_duration, bold_voxels)
- Users expect these values, not "n/a"
- Silent failures violate observability principles
- Affects scientific reproducibility (missing metadata)

**Recommendation**: Fix before next metadata generation run.

---

## Temporary Workaround

Until fixed, users can fetch content before extraction:

```bash
# Option A: Fetch specific BOLD files (faster)
datalad get -n study-ds*/sourcedata/*/sub-*/ses-*/func/*_bold.nii.gz

# Option B: Disable imaging metrics (lose data quality)
# In Snakefile, change include_imaging=True to False
```

**NOT RECOMMENDED**: Both workarounds are suboptimal - proper sparse access should work.
