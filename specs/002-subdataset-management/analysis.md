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

## Extended Analysis: Derivatives Metadata Requirements

### Current Derivative Columns (studies+derivatives.tsv)

**Existing columns** (per FR-010):
- `study_id` - Study identifier
- `derivative_id` - Derivative directory name (e.g., fMRIPrep-21.0.1)
- `tool_name` - Processing tool name
- `tool_version` - Tool version
- `datalad_uuid` - DataLad UUID for disambiguation
- `url` - Git URL of derivative dataset
- `size_total` - Total size (bytes) ❌ Currently n/a
- `size_annexed` - Annexed file size (bytes) ❌ Currently n/a
- `file_count` - Number of files ❌ Currently n/a
- `outdatedness` - Commits behind current raw version ❌ Currently n/a
- `processed_raw_version` - Raw version that was processed ❌ Currently n/a

### Required Additions from User + Notes

Based on user request and `doc/note-todos/20260209-1.md`:

#### 1. Version Tracking (User Request)

**processed_raw_version** (already in spec, not implemented):
- Extract from derivative's `dataset_description.json` → `SourceDatasets` field
- OR from git describe --always on the raw dataset at time of processing
- Format: git tag or commit SHA

**current_raw_version**:
- Current git describe --always of the raw sourcedata
- Format: git tag or commit SHA

**uptodate** (boolean):
- `true` if processed_raw_version == current_raw_version
- `false` if versions differ
- `n/a` if either version unknown

**outdatedness** (count):
- Number of commits between processed_raw_version and current_raw_version
- `0` if uptodate
- `n/a` if versions unknown

#### 2. Processing Completeness (from notes)

**tasks_processed**:
- Comma-separated list of task names found in derivative func/ data
- Example: "rest,finger,nback"
- Compare with raw dataset tasks to determine if complete

**tasks_missing**:
- Tasks present in raw but NOT in derivative
- Empty string if all tasks processed
- Example: "foot,memory" if these tasks weren't processed

**anat_processed** (boolean):
- `true` if anatomical processing present (anat/ directory with outputs)
- `false` if no anatomical outputs

**func_processed** (boolean):
- `true` if functional processing present (func/ directory with outputs)
- `false` if no functional outputs

**processing_complete** (boolean):
- `true` if all raw data modalities processed (no missing tasks, all anat/func done)
- `false` if partial processing detected

#### 3. fMRIPrep-Specific Metadata

**template_spaces**:
- Comma-separated list of template spaces with actual data (not just transformations)
- Extract from space-* entities in derivative filenames
- Example: "MNI152NLin2009cAsym,fsaverage5,T1w"
- Distinguish data vs transforms: check for _bold.nii.gz vs _from-*_to-*_xfm.h5

**transform_spaces**:
- Spaces with only transformations (no volumetric/surface data)
- Example: "MNI152NLin6Asym,fsnative"

**pipeline_config**:
- Extract from dataset_description.json → GeneratedBy → Container/Version/CodeURL
- Or from .fmriprep/config.toml if available
- Key options: --output-spaces, --bold2t1w-dof, --use-aroma, --skull-strip-template

**defaced_input** (boolean):
- Whether input data was defaced before processing
- Check raw dataset for defacing indicators:
  - _defacemask.nii.gz files in anat/
  - "defaced" in dataset_description.json notes
  - Face voxels zeroed in T1w (heuristic check)

**subject_processing_status**:
- JSON object mapping subject → status
- Example: `{"sub-01": "complete", "sub-02": "failed", "sub-03": "partial"}`
- Extract from derivatives presence + error logs

#### 4. Quality Metrics (fMRIPrep/MRIQC)

**For fMRIPrep derivatives**:

**mean_fd** (framewise displacement):
- Average FD across all runs
- Extract from desc-confounds_timeseries.tsv files

**mean_dvars**:
- Average DVARS across all runs
- Extract from confounds files

**tsnr_mean**:
- Average tSNR across all BOLD runs
- Can be computed from preprocessed BOLD data or extracted if stored

**registration_quality**:
- Summary of registration quality metrics
- Check figures/reports for QC flags

**For MRIQC derivatives**:

**qa_rating_mean**:
- Average quality rating across subjects
- Extract from MRIQC JSON outputs

**failed_subjects**:
- Count or list of subjects that failed MRIQC
- Parse from MRIQC reports

#### 5. Computational Metadata

**processing_time_hours**:
- Total processing time if logged
- Extract from fmriprep logs or .fmriprep/CITATION.md timestamps

**container_version**:
- Docker/Singularity container version used
- Extract from dataset_description.json → GeneratedBy

**compute_environment**:
- HPC cluster, cloud, local
- Parse from logs if available

## Proposed Derivatives Extraction Architecture

### Two-Tier Extraction

**Tier 1: Basic Stats (All Derivatives)**
- Size stats (git-annex info)
- Version tracking (processed_raw_version, current_raw_version, uptodate, outdatedness)
- File counts
- Processing completeness (tasks, modalities)

**Tier 2: Tool-Specific Stats (fMRIPrep, MRIQC, etc.)**
- Template spaces
- Quality metrics
- Configuration details
- Per-subject status

### Implementation Strategy

```python
def extract_derivative_metadata(
    derivative_path: Path,
    raw_path: Path,
    tool_name: str
) -> dict[str, Any]:
    """Extract comprehensive derivative metadata.
    
    Args:
        derivative_path: Path to derivative subdataset
        raw_path: Path to raw sourcedata subdataset
        tool_name: Derivative tool name (fMRIPrep, MRIQC, etc.)
    
    Returns:
        Dictionary with all derivative metadata
    """
    result = {}
    
    # Tier 1: Universal metadata
    result.update(extract_basic_derivative_stats(derivative_path))
    result.update(extract_version_tracking(derivative_path, raw_path))
    result.update(extract_processing_completeness(derivative_path, raw_path))
    
    # Tier 2: Tool-specific metadata
    if tool_name.lower() == 'fmriprep':
        result.update(extract_fmriprep_metadata(derivative_path))
    elif tool_name.lower() == 'mriqc':
        result.update(extract_mriqc_metadata(derivative_path))
    
    return result


def extract_version_tracking(
    derivative_path: Path,
    raw_path: Path
) -> dict[str, Any]:
    """Extract version tracking metadata.
    
    Returns dict with:
    - processed_raw_version: Version of raw used for processing
    - current_raw_version: Current version of raw
    - uptodate: Boolean if versions match
    - outdatedness: Commit count between versions
    """
    import subprocess
    
    # Get processed version from derivative's dataset_description.json
    dd_path = derivative_path / 'dataset_description.json'
    processed_version = 'n/a'
    if dd_path.exists():
        with open(dd_path) as f:
            dd = json.load(f)
            # Parse SourceDatasets for version info
            sources = dd.get('SourceDatasets', [])
            if sources:
                # Extract version from first source
                # Could be in Version field or URL
                processed_version = sources[0].get('Version', 'n/a')
    
    # Get current version from raw dataset
    try:
        result = subprocess.run(
            ['git', '-C', str(raw_path), 'describe', '--always'],
            capture_output=True, text=True, check=True
        )
        current_version = result.stdout.strip()
    except subprocess.CalledProcessError:
        current_version = 'n/a'
    
    # Calculate outdatedness
    uptodate = False
    outdatedness = 'n/a'
    if processed_version != 'n/a' and current_version != 'n/a':
        if processed_version == current_version:
            uptodate = True
            outdatedness = 0
        else:
            # Count commits between versions
            try:
                result = subprocess.run(
                    ['git', '-C', str(raw_path), 'rev-list', '--count',
                     f'{processed_version}..{current_version}'],
                    capture_output=True, text=True, check=True
                )
                outdatedness = int(result.stdout.strip())
                uptodate = (outdatedness == 0)
            except (subprocess.CalledProcessError, ValueError):
                outdatedness = 'n/a'
    
    return {
        'processed_raw_version': processed_version,
        'current_raw_version': current_version,
        'uptodate': uptodate,
        'outdatedness': outdatedness
    }


def extract_fmriprep_metadata(derivative_path: Path) -> dict[str, Any]:
    """Extract fMRIPrep-specific metadata.
    
    Returns dict with:
    - template_spaces: Spaces with data
    - transform_spaces: Spaces with only transforms
    - pipeline_config: Key configuration options
    - defaced_input: Whether input was defaced
    - quality_metrics: Mean FD, DVARS, tSNR
    """
    from collections import defaultdict
    import re
    
    result = {
        'template_spaces': 'n/a',
        'transform_spaces': 'n/a',
        'pipeline_config': 'n/a',
        'defaced_input': 'n/a',
        'mean_fd': 'n/a',
        'mean_dvars': 'n/a',
        'tsnr_mean': 'n/a',
    }
    
    # Extract template spaces from filenames
    data_spaces = set()
    transform_spaces = set()
    
    # Use git ls-files to list all files without cloning
    try:
        import subprocess
        result_files = subprocess.run(
            ['git', '-C', str(derivative_path), 'ls-files'],
            capture_output=True, text=True, check=True
        )
        files = result_files.stdout.strip().split('\n')
        
        space_pattern = re.compile(r'_space-(\w+)_')
        
        for file in files:
            if '_space-' in file:
                match = space_pattern.search(file)
                if match:
                    space = match.group(1)
                    if '_xfm.' in file:
                        transform_spaces.add(space)
                    else:
                        data_spaces.add(space)
        
        if data_spaces:
            result['template_spaces'] = ','.join(sorted(data_spaces))
        if transform_spaces:
            result['transform_spaces'] = ','.join(sorted(transform_spaces))
    
    except subprocess.CalledProcessError:
        pass
    
    # Extract pipeline config from dataset_description.json
    dd_path = derivative_path / 'dataset_description.json'
    if dd_path.exists():
        try:
            with open(dd_path) as f:
                dd = json.load(f)
                gen_by = dd.get('GeneratedBy', [])
                if gen_by:
                    config_items = []
                    container = gen_by[0].get('Container', {})
                    if 'Tag' in container:
                        config_items.append(f"container:{container['Tag']}")
                    # Parse command-line args if stored
                    # This would require looking at logs or CITATION
                    result['pipeline_config'] = ','.join(config_items) if config_items else 'n/a'
        except (json.JSONDecodeError, IOError):
            pass
    
    # Check for defaced input
    # Look for defacemask or defaced mentions in raw sourcedata
    # This would need raw_path parameter
    
    # Extract quality metrics from confounds files
    # This would require sparse access to TSV files
    # For now, mark as future enhancement
    
    return result


def extract_processing_completeness(
    derivative_path: Path,
    raw_path: Path
) -> dict[str, Any]:
    """Extract processing completeness metadata.
    
    Returns dict with:
    - tasks_processed: Tasks found in derivative
    - tasks_missing: Tasks in raw but not in derivative
    - anat_processed: Boolean
    - func_processed: Boolean
    - processing_complete: Boolean
    """
    import subprocess
    
    # Get tasks from derivative
    try:
        result = subprocess.run(
            ['git', '-C', str(derivative_path), 'ls-files', 'func/'],
            capture_output=True, text=True
        )
        deriv_files = result.stdout.strip().split('\n')
        
        # Extract task entities
        task_pattern = re.compile(r'_task-(\w+)_')
        deriv_tasks = set()
        for file in deriv_files:
            match = task_pattern.search(file)
            if match:
                deriv_tasks.add(match.group(1))
    except subprocess.CalledProcessError:
        deriv_tasks = set()
    
    # Get tasks from raw
    try:
        result = subprocess.run(
            ['git', '-C', str(raw_path), 'ls-files', 'func/'],
            capture_output=True, text=True
        )
        raw_files = result.stdout.strip().split('\n')
        
        raw_tasks = set()
        for file in raw_files:
            match = task_pattern.search(file)
            if match:
                raw_tasks.add(match.group(1))
    except subprocess.CalledProcessError:
        raw_tasks = set()
    
    # Calculate completeness
    missing_tasks = raw_tasks - deriv_tasks
    
    # Check modalities
    anat_processed = any('anat/' in f for f in deriv_files) if deriv_files else False
    func_processed = bool(deriv_tasks)
    
    processing_complete = (len(missing_tasks) == 0 and anat_processed and func_processed)
    
    return {
        'tasks_processed': ','.join(sorted(deriv_tasks)) if deriv_tasks else 'n/a',
        'tasks_missing': ','.join(sorted(missing_tasks)) if missing_tasks else '',
        'anat_processed': anat_processed,
        'func_processed': func_processed,
        'processing_complete': processing_complete,
    }
```

## Proposed studies+derivatives.tsv Schema

### Updated Column List

**Core Identification** (existing):
- study_id
- derivative_id
- tool_name
- tool_version
- datalad_uuid
- url

**Size/File Stats** (implement):
- size_total
- size_annexed
- file_count

**Version Tracking** (new):
- processed_raw_version
- current_raw_version
- uptodate (boolean)
- outdatedness (integer count)

**Processing Completeness** (new):
- tasks_processed
- tasks_missing
- anat_processed (boolean - ANY desc- in anat/)
- func_processed (boolean - ANY desc- in func/)
- processing_complete (boolean)
- descriptions (JSON dict with desc- entity counts)

**fMRIPrep-Specific** (new):
- template_spaces
- transform_spaces
- pipeline_config
- defaced_input (boolean)

**Quality Metrics** (future):
- mean_fd
- mean_dvars
- tsnr_mean

**Computational** (future):
- processing_time_hours
- container_version
- compute_environment

## Revised Implementation Plan

### Phase 1: Core Derivatives Stats (Highest Priority)

1. Implement `extract_basic_derivative_stats()` using git-annex info
2. Implement `extract_version_tracking()` for version comparison
3. Update `collect_derivatives_for_study()` with temporary installation
4. Test with fMRIPrep derivatives

### Phase 2: Processing Completeness (High Priority)

1. Implement `extract_processing_completeness()` 
2. Add task comparison logic
3. Add modality detection (anat/func)
4. Test with partial processing cases

### Phase 3: fMRIPrep-Specific Metadata (Medium Priority)

1. Implement `extract_fmriprep_metadata()`
2. Extract template spaces from filenames
3. Parse pipeline configuration
4. Test with various fMRIPrep versions

### Phase 4: Quality Metrics (Lower Priority)

1. Implement confounds parsing (requires sparse access)
2. Extract FD, DVARS, tSNR
3. Aggregate across subjects/runs
4. Consider MRIQC integration

## Updated Success Criteria

✅ All derivative basic stats populated (size, file count)
✅ Version tracking working (processed vs current, uptodate, outdatedness)
✅ Processing completeness accurate (tasks, modalities)
✅ fMRIPrep spaces and config extracted
✅ No permanent subdataset installation required
✅ Extraction works via temporary installation only
