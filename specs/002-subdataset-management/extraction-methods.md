# Derivatives Metadata Extraction Methods

## Scope

This document analyzes practical extraction methods for derivatives metadata that can be implemented using **git tree access only** (no annexed content download required).

**Immediate Priority**:
- tasks_processed / tasks_missing
- anat_processed / func_processed / processing_complete
- template_spaces / transform_spaces
- descriptions (JSON dict with desc- entity counts)

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

**Method**: Check for ANY desc- entity in anat/ directory NIfTI files

**Rationale**: Any desc- entity indicates processing occurred (preproc, brain, aseg, aparcaseg, etc.)

**Implementation**:
```python
def extract_anat_processed(derivative_path: Path) -> bool:
    """Check if anatomical processing outputs exist.

    Considers anatomical processed if ANY _desc- entity present in anat/ NIfTI files.
    This includes:
    - desc-preproc (preprocessed)
    - desc-brain (brain-extracted)
    - desc-aseg (FreeSurfer segmentation)
    - desc-aparcaseg (parcellation)
    - Any other desc- variant

    Also considers processed if:
    - Space-normalized outputs (_space-*)
    - Segmentation masks (_dseg, _probseg)

    Returns:
        True if anatomical outputs with processing indicators found, False otherwise
    """
    import subprocess
    import re

    try:
        result = subprocess.run(
            ['git', '-C', str(derivative_path), 'ls-files', 'anat/'],
            capture_output=True, text=True, check=True
        )

        if not result.stdout.strip():
            return False

        files = result.stdout.strip().split('\n')

        # Check for processing indicators
        for filepath in files:
            # NIfTI files only (exclude JSON sidecars)
            if not filepath.endswith('.nii.gz'):
                continue

            # Any desc- entity indicates processing
            if '_desc-' in filepath:
                return True

            # Space normalization indicates processing
            if '_space-' in filepath and '_from-' not in filepath:  # Exclude transforms
                return True

            # Segmentation outputs indicate processing
            if any(seg in filepath for seg in ['_dseg.nii.gz', '_probseg.nii.gz']):
                return True

        return False

    except subprocess.CalledProcessError:
        return False
```

**Example Output**: `true` or `false`

**Edge Cases**:
- anat/ has only raw data (no desc-, no space-) → false
- anat/ has only transformations → false (excluded by _from- check)
- Any desc- variant (not just preproc) → true
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

### 8. descriptions

**What**: JSON dict (as string) with counts of different desc- entity types in derivative outputs

**Purpose**: Track what types of processed outputs exist without listing every file

**Method**: Parse all _desc-{label}_ entities from derivative filenames and count occurrences

**Implementation**:
```python
def extract_descriptions(derivative_path: Path) -> str:
    """Extract description entity counts from derivative outputs.

    Counts occurrences of each _desc-{label}_ entity across all files.
    Returns JSON string for storage in TSV.

    Examples:
        {"preproc": 120, "brain": 40, "aseg": 40, "aparcaseg": 40}
        {"confounds": 60, "carpetplot": 20}

    Returns:
        JSON string of desc counts, or '{}' if none found
    """
    import subprocess
    import re
    import json
    from collections import Counter

    try:
        # List all files in derivative
        result = subprocess.run(
            ['git', '-C', str(derivative_path), 'ls-files'],
            capture_output=True, text=True, check=True
        )

        if not result.stdout.strip():
            return '{}'

        files = result.stdout.strip().split('\n')

        # Extract desc entities: _desc-{label}_
        desc_pattern = re.compile(r'_desc-([a-zA-Z0-9]+)_')
        desc_labels = []

        for filepath in files:
            # Only consider BIDS data files (not hidden, not in derivatives root)
            if filepath.startswith('.') or '/' not in filepath:
                continue

            matches = desc_pattern.findall(filepath)
            desc_labels.extend(matches)

        if not desc_labels:
            return '{}'

        # Count occurrences
        counts = Counter(desc_labels)

        # Convert to sorted dict for consistent output
        result_dict = dict(sorted(counts.items()))

        return json.dumps(result_dict, separators=(',', ':'))

    except subprocess.CalledProcessError:
        return '{}'
```

**Example Outputs**:

**fMRIPrep derivative**:
```json
{"aparcaseg":40,"aseg":40,"brain":40,"confounds":60,"preproc":180}
```
- `preproc`: 180 files (BOLD + T1w + T2w preprocessed)
- `brain`: 40 files (brain-extracted anatomicals)
- `aseg/aparcaseg`: 40 files (FreeSurfer segmentations)
- `confounds`: 60 files (confounds timeseries)

**MRIQC derivative**:
```json
{"carpetplot":20}
```
- `carpetplot`: 20 carpet plot images

**Minimal derivative**:
```json
{"preproc":10}
```

**No desc- entities**:
```json
{}
```

**Edge Cases**:
- Same desc- in multiple file types (NIfTI, JSON, TSV) → All counted
- Multiple desc- in same filename (rare) → Each counted separately
- desc- in transform filenames → Counted (intentional, shows transform types)
- Derivative has no desc- entities → Empty dict `{}`

**Usage**:
This column allows quick assessment of derivative content:
- High `preproc` count → Full preprocessing pipeline
- `confounds` present → Nuisance regressors available
- `brain` count → Brain extraction performed
- `aseg/aparcaseg` → FreeSurfer segmentation available

---

## Extraction Order

Due to dependencies, extraction should follow this order:

1. **tasks_processed** (independent)
2. **template_spaces** (independent)
3. **descriptions** (independent)
4. **anat_processed** (independent)
5. **func_processed** (independent)
6. **tasks_missing** (depends on tasks_processed + raw access)
7. **transform_spaces** (depends on template_spaces)
8. **processing_complete** (depends on tasks_missing, anat_processed, func_processed, raw access)

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
    descriptions = extract_descriptions(derivative_path)
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
        'descriptions': descriptions,
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
