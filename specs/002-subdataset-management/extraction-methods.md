# Derivatives Metadata Extraction Methods

## Scope

This document analyzes practical extraction methods for derivatives metadata that can be implemented using **git tree access only** (no annexed content download required).

**Immediate Priority**:
- tasks_processed / tasks_missing
- anat_processed / func_processed / processing_complete
- template_spaces / transform_spaces

**Future TODO** (deferred):
- pipeline_config → config registry system
- quality metrics (mean_fd, mean_dvars, tsnr_mean)
- defaced_input detection

## Core Extraction Principle

All metadata should be extractable using **git ls-files** or **git ls-tree** to list files in the repository WITHOUT:
- Cloning annexed content
- Downloading large files
- Permanent subdataset installation

This works because:
1. BIDS entities (_task-, _space-, etc.) are in **filenames**
2. Directory structure (anat/, func/) is in **git tree**
3. Git stores file paths even for annexed files

## Extraction Methods

### 1. tasks_processed

**What**: Comma-separated list of task names found in derivative's func/ data

**Method**: Parse _task- entities from func/ filenames

**Implementation**:
```python
def extract_tasks_processed(derivative_path: Path) -> str:
    """Extract task names from derivative func/ directory.

    Returns:
        Comma-separated sorted task names, or 'n/a' if none found
    """
    import subprocess
    import re

    try:
        # List all files in func/ directory using git
        result = subprocess.run(
            ['git', '-C', str(derivative_path), 'ls-files', 'func/'],
            capture_output=True, text=True, check=True
        )

        if not result.stdout.strip():
            return 'n/a'

        files = result.stdout.strip().split('\n')

        # Extract task entities: _task-{label}_
        task_pattern = re.compile(r'_task-([a-zA-Z0-9]+)_')
        tasks = set()

        for filepath in files:
            # Only consider data files (not transforms, not events.tsv, etc.)
            if any(filepath.endswith(ext) for ext in [
                '_bold.nii.gz', '_bold.json',
                '_cbv.nii.gz', '_cbv.json',
                '_sbref.nii.gz', '_sbref.json'
            ]):
                match = task_pattern.search(filepath)
                if match:
                    tasks.add(match.group(1))

        if tasks:
            return ','.join(sorted(tasks))
        return 'n/a'

    except subprocess.CalledProcessError:
        return 'n/a'
```

**Example Output**: `"rest,finger,nback"` or `"n/a"`

**Edge Cases**:
- No func/ directory → 'n/a'
- func/ has only events.tsv or confounds → 'n/a' (no actual data processed)
- Task-free designs (rest state without task entity) → Check for any _bold.nii.gz, mark as 'rest' or 'n/a'

---

### 2. tasks_missing

**What**: Tasks present in raw sourcedata but NOT in derivative

**Method**: Compare raw func/ tasks with derivative func/ tasks

**Implementation**:
```python
def extract_tasks_missing(
    derivative_path: Path,
    raw_path: Path,
    tasks_processed: str
) -> str:
    """Extract tasks that exist in raw but not in derivative.

    Args:
        derivative_path: Path to derivative subdataset
        raw_path: Path to raw sourcedata subdataset
        tasks_processed: Already-extracted tasks from derivative

    Returns:
        Comma-separated missing task names, or empty string if none missing
    """
    import subprocess
    import re

    # Parse tasks_processed
    if tasks_processed == 'n/a':
        deriv_tasks = set()
    else:
        deriv_tasks = set(tasks_processed.split(','))

    # Extract tasks from raw sourcedata
    try:
        result = subprocess.run(
            ['git', '-C', str(raw_path), 'ls-files', 'func/'],
            capture_output=True, text=True, check=True
        )

        if not result.stdout.strip():
            return ''  # No raw func data

        files = result.stdout.strip().split('\n')
        task_pattern = re.compile(r'_task-([a-zA-Z0-9]+)_')
        raw_tasks = set()

        for filepath in files:
            if filepath.endswith('_bold.nii.gz'):
                match = task_pattern.search(filepath)
                if match:
                    raw_tasks.add(match.group(1))

        # Calculate missing
        missing = raw_tasks - deriv_tasks

        if missing:
            return ','.join(sorted(missing))
        return ''  # All tasks processed

    except subprocess.CalledProcessError:
        return 'n/a'  # Cannot determine
```

**Example Output**:
- `""` (empty) if all tasks processed
- `"memory,motor"` if these tasks missing
- `"n/a"` if cannot determine (error accessing raw)

**Edge Cases**:
- Raw has no tasks but derivative does (synthetic derivative?) → empty string
- Raw has tasks, derivative empty → all tasks listed as missing
- Both have no task entities (resting state) → empty string

---

### 3. anat_processed

**What**: Boolean indicating if anatomical data was processed

**Method**: Check for preprocessed anatomical outputs in anat/ directory

**Implementation**:
```python
def extract_anat_processed(derivative_path: Path) -> bool:
    """Check if anatomical processing outputs exist.

    Looks for typical fMRIPrep anatomical outputs:
    - *_desc-preproc_T1w.nii.gz
    - *_space-*_T1w.nii.gz
    - *_dseg.nii.gz (segmentation)
    - *_desc-brain_mask.nii.gz

    Returns:
        True if anatomical outputs found, False otherwise
    """
    import subprocess

    try:
        result = subprocess.run(
            ['git', '-C', str(derivative_path), 'ls-files', 'anat/'],
            capture_output=True, text=True, check=True
        )

        if not result.stdout.strip():
            return False

        files = result.stdout.strip().split('\n')

        # Check for typical preprocessed anatomical outputs
        anat_indicators = [
            '_desc-preproc_T1w.nii.gz',
            '_desc-preproc_T2w.nii.gz',
            '_space-',  # Any space-normalized anatomy
            '_dseg.nii.gz',  # Segmentation
            '_desc-brain_mask.nii.gz',
        ]

        for filepath in files:
            if any(indicator in filepath for indicator in anat_indicators):
                return True

        return False

    except subprocess.CalledProcessError:
        return False
```

**Example Output**: `true` or `false`

**Edge Cases**:
- anat/ exists but only has native space (no preprocessing) → Could check for desc-preproc specifically
- Only transformations in anat/ (no actual images) → false
- Derivative is func-only (no anat processing needed) → false (expected)

---

### 4. func_processed

**What**: Boolean indicating if functional data was processed

**Method**: Check for preprocessed functional outputs in func/ directory

**Implementation**:
```python
def extract_func_processed(derivative_path: Path) -> bool:
    """Check if functional processing outputs exist.

    Looks for typical fMRIPrep functional outputs:
    - *_desc-preproc_bold.nii.gz
    - *_space-*_bold.nii.gz
    - *_boldref.nii.gz (reference volumes)

    Returns:
        True if functional outputs found, False otherwise
    """
    import subprocess

    try:
        result = subprocess.run(
            ['git', '-C', str(derivative_path), 'ls-files', 'func/'],
            capture_output=True, text=True, check=True
        )

        if not result.stdout.strip():
            return False

        files = result.stdout.strip().split('\n')

        # Check for preprocessed functional outputs
        func_indicators = [
            '_desc-preproc_bold.nii.gz',
            '_space-',  # Any space-normalized functional
            '_boldref.nii.gz',
        ]

        for filepath in files:
            if any(indicator in filepath for indicator in func_indicators):
                return True

        return False

    except subprocess.CalledProcessError:
        return False
```

**Example Output**: `true` or `false`

**Edge Cases**:
- func/ has only confounds TSV (no images) → false
- func/ has only native space (no preprocessing) → Check for desc-preproc
- Derivative is anat-only → false (expected)

---

### 5. processing_complete

**What**: Boolean indicating if ALL raw data modalities were fully processed

**Method**: Combine tasks_missing, anat_processed, func_processed checks

**Implementation**:
```python
def extract_processing_complete(
    tasks_missing: str,
    anat_processed: bool,
    func_processed: bool,
    raw_path: Path
) -> bool:
    """Determine if processing is complete.

    Complete means:
    - All tasks from raw are in derivative (tasks_missing is empty)
    - If raw has anat, derivative has anat_processed=true
    - If raw has func, derivative has func_processed=true

    Args:
        tasks_missing: Already-extracted missing tasks
        anat_processed: Already-extracted anat flag
        func_processed: Already-extracted func flag
        raw_path: Path to raw sourcedata (to check what modalities exist)

    Returns:
        True if processing complete, False if partial
    """
    import subprocess

    # Check tasks completeness
    if tasks_missing and tasks_missing != 'n/a':
        return False  # Missing tasks means incomplete

    # Check if raw has anat/func
    try:
        result = subprocess.run(
            ['git', '-C', str(raw_path), 'ls-tree', '-d', 'HEAD'],
            capture_output=True, text=True, check=True
        )

        raw_dirs = result.stdout.strip().split('\n')
        raw_has_anat = any('anat' in line for line in raw_dirs)
        raw_has_func = any('func' in line for line in raw_dirs)

        # If raw has modality, derivative must have processed it
        if raw_has_anat and not anat_processed:
            return False

        if raw_has_func and not func_processed:
            return False

        # All checks passed
        return True

    except subprocess.CalledProcessError:
        return False  # Cannot determine, mark as incomplete
```

**Example Output**: `true` or `false`

**Logic**:
- `true`: All tasks processed AND all modalities processed
- `false`: Any tasks missing OR any expected modality not processed

**Edge Cases**:
- Raw is anat-only, derivative has anat → true
- Raw is func-only, derivative has func, all tasks → true
- Raw has anat+func, derivative only has func → false
- Cannot access raw dataset → false (conservative)

---

### 6. template_spaces

**What**: Comma-separated list of template spaces with actual volumetric/surface data (not just transforms)

**Method**: Parse _space- entities from derivative filenames, exclude transform-only files

**Implementation**:
```python
def extract_template_spaces(derivative_path: Path) -> str:
    """Extract template spaces with actual data.

    Identifies spaces from _space- entity in filenames.
    Excludes files that are only transforms (_xfm, _to-*_from-*).

    Returns:
        Comma-separated sorted space names, or 'n/a' if none
    """
    import subprocess
    import re

    try:
        # List all files in derivative
        result = subprocess.run(
            ['git', '-C', str(derivative_path), 'ls-files'],
            capture_output=True, text=True, check=True
        )

        if not result.stdout.strip():
            return 'n/a'

        files = result.stdout.strip().split('\n')

        # Extract space entities: _space-{label}_
        space_pattern = re.compile(r'_space-([a-zA-Z0-9]+)_')
        data_spaces = set()

        for filepath in files:
            # Exclude transform files
            if any(x in filepath for x in ['_xfm.', '_from-', '_to-']):
                continue

            # Only consider data files
            if any(filepath.endswith(ext) for ext in [
                '_bold.nii.gz', '_T1w.nii.gz', '_T2w.nii.gz',
                '_cbv.nii.gz', '_mask.nii.gz', '_dseg.nii.gz',
                '_probseg.nii.gz', '_dtissue.nii.gz',
                '.func.gii', '.surf.gii', '.shape.gii'  # Surface files
            ]):
                match = space_pattern.search(filepath)
                if match:
                    data_spaces.add(match.group(1))

        if data_spaces:
            return ','.join(sorted(data_spaces))
        return 'n/a'

    except subprocess.CalledProcessError:
        return 'n/a'
```

**Example Output**: `"MNI152NLin2009cAsym,T1w,fsaverage5"` or `"n/a"`

**Space Types**:
- Volumetric: MNI152NLin2009cAsym, MNI152NLin6Asym, MNIPediatricAsym
- Native: T1w, T2w
- Surface: fsaverage, fsaverage5, fsaverage6, fsnative

**Edge Cases**:
- No space entity (native space without label) → 'n/a'
- Only transforms → 'n/a'
- Mix of data and transforms in same space → Space appears in data_spaces

---

### 7. transform_spaces

**What**: Comma-separated list of spaces that have ONLY transformations (no volumetric/surface data)

**Method**: Parse _space- from transform files, exclude spaces that also have data

**Implementation**:
```python
def extract_transform_spaces(
    derivative_path: Path,
    template_spaces: str
) -> str:
    """Extract spaces with only transformations.

    Identifies spaces from transform files (_xfm, _to-*_from-*).
    Excludes spaces that also appear in template_spaces.

    Args:
        derivative_path: Path to derivative subdataset
        template_spaces: Already-extracted data spaces

    Returns:
        Comma-separated sorted space names, or empty string if none
    """
    import subprocess
    import re

    # Parse template_spaces
    if template_spaces == 'n/a':
        data_spaces = set()
    else:
        data_spaces = set(template_spaces.split(','))

    try:
        result = subprocess.run(
            ['git', '-C', str(derivative_path), 'ls-files'],
            capture_output=True, text=True, check=True
        )

        if not result.stdout.strip():
            return ''

        files = result.stdout.strip().split('\n')

        # Extract spaces from transforms
        # Formats: _to-{space}_from-*, _from-{space}_to-*, _space-{space}_*xfm
        to_pattern = re.compile(r'_to-([a-zA-Z0-9]+)_')
        from_pattern = re.compile(r'_from-([a-zA-Z0-9]+)_')
        space_pattern = re.compile(r'_space-([a-zA-Z0-9]+)_')

        transform_spaces_all = set()

        for filepath in files:
            # Only consider transform files
            if '_xfm.' in filepath or '_from-' in filepath or '_to-' in filepath:
                # Extract all space references
                for pattern in [to_pattern, from_pattern, space_pattern]:
                    matches = pattern.findall(filepath)
                    transform_spaces_all.update(matches)

        # Exclude spaces that have data
        transform_only = transform_spaces_all - data_spaces

        if transform_only:
            return ','.join(sorted(transform_only))
        return ''

    except subprocess.CalledProcessError:
        return ''
```

**Example Output**:
- `"MNI152NLin6Asym,fsnative"` if these have only transforms
- `""` (empty) if no transform-only spaces
- `""` if all transforms are for spaces with data

**Edge Cases**:
- Space has both data and transforms → Appears in template_spaces, NOT in transform_spaces
- Space referenced in _from- or _to- but has data → Excluded from transform_spaces
- Transform between two data spaces → Neither appears in transform_spaces

---

## Extraction Order

Due to dependencies, extraction should follow this order:

1. **tasks_processed** (independent)
2. **template_spaces** (independent)
3. **tasks_missing** (depends on tasks_processed + raw access)
4. **transform_spaces** (depends on template_spaces)
5. **anat_processed** (independent)
6. **func_processed** (independent)
7. **processing_complete** (depends on tasks_missing, anat_processed, func_processed, raw access)

## Implementation Pattern

```python
def extract_derivative_completeness_metadata(
    derivative_path: Path,
    raw_path: Path
) -> dict[str, Any]:
    """Extract all completeness metadata for a derivative.

    Args:
        derivative_path: Path to derivative subdataset (must be installed)
        raw_path: Path to raw sourcedata subdataset (must be installed)

    Returns:
        Dictionary with all completeness fields
    """
    # Extract independent metrics
    tasks_processed = extract_tasks_processed(derivative_path)
    template_spaces = extract_template_spaces(derivative_path)
    anat_processed = extract_anat_processed(derivative_path)
    func_processed = extract_func_processed(derivative_path)

    # Extract dependent metrics
    tasks_missing = extract_tasks_missing(derivative_path, raw_path, tasks_processed)
    transform_spaces = extract_transform_spaces(derivative_path, template_spaces)
    processing_complete = extract_processing_complete(
        tasks_missing, anat_processed, func_processed, raw_path
    )

    return {
        'tasks_processed': tasks_processed,
        'tasks_missing': tasks_missing,
        'anat_processed': anat_processed,
        'func_processed': func_processed,
        'processing_complete': processing_complete,
        'template_spaces': template_spaces,
        'transform_spaces': transform_spaces,
    }
```

## Testing Strategy

### Unit Tests

Test each extraction function with:
- Complete fMRIPrep output (all tasks, all modalities)
- Partial fMRIPrep output (missing tasks)
- Anat-only derivative
- Func-only derivative
- Empty derivative (error case)

### Integration Tests

Test with real derivatives:
- `ds000001-fmriprep` (complete processing)
- `ds006131-fmriprep` (check multi-space)
- MRIQC derivatives (different structure)

### Edge Case Tests

- No func/ directory
- No anat/ directory
- Resting state (no task entity)
- Multi-echo BOLD
- Surface-only processing
- Native space only (no templates)

## Performance Considerations

All extractions use `git ls-files` which:
- ✅ Works on git tree only (no annexed content)
- ✅ Fast (milliseconds for typical datasets)
- ✅ Works with temporary subdataset installation
- ✅ No network access needed
- ⚠️ Requires git repository initialized (temporary installation handles this)

**Parallel Execution**: Extractions for different derivatives can run in parallel safely.

## Future Enhancements (TODO)

**Deferred to later**:
- **pipeline_config registry system** - Create hash/ID system for config fingerprinting
- **Quality metrics** - Requires parsing TSV files (confounds), needs sparse access
- **defaced_input** - Requires checking raw dataset for defacing indicators
- **Per-subject processing status** - Requires deeper analysis of subject directories
- **Processing time** - Requires parsing logs (if available)
