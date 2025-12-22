# Studies.tsv Summary Columns Implementation Plan

Date: 2025-12-18
Status: Planning
Approach: **datalad-fuse FsspecAdapter** (no FUSE mount required)

## Summary

This document plans the implementation of missing summary columns in studies.tsv per FR-009, FR-031, FR-032, FR-033.

**Key Decision**: Use datalad-fuse's `FsspecAdapter` directly in Python without FUSE mounting:
- Is generalizable (works with any git forge, not just GitHub)
- Avoids full cloning (git-annex fetches content on-demand via URLs)
- Uses fsspec file-like objects passed to nibabel/other libraries
- No filesystem mounting required (pure Python solution)
- Works uniformly across all data sources

## Research Findings

### datalad-fuse Architecture

The [datalad-fuse](https://github.com/datalad/datalad-fuse) extension provides:
1. **FsspecAdapter** - Python class that wraps git-annex repositories
2. **URL Resolution** - Uses `git annex whereis` to get remote URLs for annexed files
3. **fsspec Integration** - Opens remote URLs via `HTTPFileSystem` with range request support
4. **Sparse Caching** - Downloads only requested bytes, caches under `.git/datalad/cache/fsspec`

See: [datalad-fuse issue #2](https://github.com/datalad/datalad-fuse/issues/2) for fsspec adapter design.

### fsspec + nibabel Integration

- [fsspec](https://filesystem-spec.readthedocs.io/) provides file-like objects for remote URLs
- [nibabel supports file-like objects](https://nipy.org/nibabel/reference/nibabel.filebasedimages.html) via `from_stream()` method
- HTTP range requests allow reading just NIfTI headers (~352 bytes) without full download
- [xibabel project](https://github.com/matthew-brett/xibabel) demonstrates fsspec+nibabel integration

### How it Works (No FUSE Mount)

```python
from datalad_fuse import FsspecAdapter

# Create adapter for dataset (no mount!)
adapter = FsspecAdapter("/path/to/study-ds000001/sourcedata/ds000001")

# Open annexed file - returns file-like object
with adapter.open("sub-01/anat/sub-01_T1w.nii.gz") as f:
    # f is an fsspec file-like object (HTTPFileSystem)
    # Only fetches bytes as needed via HTTP range requests
    import nibabel as nib
    img = nib.Nifti1Image.from_stream(f)
    shape = img.shape  # Reads header only (~352 bytes)
```

### Alternative: Direct git-annex whereis + fsspec

If datalad-fuse proves too heavy, we can implement minimal version:

```python
import subprocess
import json
import fsspec

def get_remote_url(repo_path: Path, file_path: str) -> str:
    """Get HTTP URL for annexed file via git-annex whereis."""
    result = subprocess.run(
        ["git", "-C", str(repo_path), "annex", "whereis", "--json", file_path],
        capture_output=True, text=True
    )
    data = json.loads(result.stdout)
    # Find web remote URL
    for remote in data.get("whereis", []):
        for url in remote.get("urls", []):
            if url.startswith("http"):
                return url
    return None

def open_remote_nifti(repo_path: Path, file_path: str):
    """Open remote NIfTI file without downloading."""
    url = get_remote_url(repo_path, file_path)
    fs = fsspec.filesystem("http")
    return fs.open(url)
```

## Current State

studies.tsv has these columns with `n/a` values that need implementation:

| Column | Description | Data Source | Extraction Method |
|--------|-------------|-------------|-------------------|
| `subjects_num` | Number of subjects | sub-* directories | git ls-tree (Phase 2) |
| `sessions_num` | Total sessions | ses-* directories | git ls-tree (Phase 2) |
| `sessions_min` | Min sessions/subject | ses-* per subject | git ls-tree (Phase 2) |
| `sessions_max` | Max sessions/subject | ses-* per subject | git ls-tree (Phase 2) |
| `bold_num` | BOLD file count | *_bold.nii* files | git ls-tree (Phase 3) |
| `t1w_num` | T1w file count | *_T1w.nii* files | git ls-tree (Phase 3) |
| `t2w_num` | T2w file count | *_T2w.nii* files | git ls-tree (Phase 3) |
| `datatypes` | Present datatypes | Datatype directories | git ls-tree (Phase 2) |
| `raw_version` | Source dataset version | Git tags | Cached metadata (Phase 1) |
| `author_lead_raw` | First author from raw | dataset_description.json | Cached metadata (Phase 1) |
| `author_senior_raw` | Last author from raw | dataset_description.json | Cached metadata (Phase 1) |
| `bold_size` | Total BOLD size | Annex key sizes | Symlink parsing (Phase 4) |
| `t1w_size` | Total T1w size | Annex key sizes | Symlink parsing (Phase 4) |
| `bold_size_max` | Max BOLD size | Annex key sizes | Symlink parsing (Phase 4) |
| `bold_voxels` | Total BOLD voxels | NIfTI headers | fsspec + nibabel (Phase 5) |

## datalad-fuse as Python Library (No Mount)

**What is datalad-fuse?**
- Python library with `FsspecAdapter` class for remote file access
- FUSE mounting is optional - we use the Python API directly
- Uses `git annex whereis` to resolve remote URLs
- fsspec handles HTTP range requests for sparse access

**How it works (Python API, no mount):**
```python
from datalad_fuse import FsspecAdapter

# Initialize adapter for a dataset
adapter = FsspecAdapter("/path/to/study-ds000001/sourcedata/ds000001")

# Get file state (annexed? local?)
is_local, annex_key = adapter.get_file_state("sub-01/anat/sub-01_T1w.nii.gz")
# annex_key contains size: SHA256E-s12345678--hash.nii.gz

# Open file - returns fsspec file-like object
with adapter.open("sub-01/anat/sub-01_T1w.nii.gz") as f:
    # f supports read(), seek() - fetches bytes via HTTP range requests
    header_bytes = f.read(352)  # Only downloads 352 bytes
```

**Why this approach?**
1. Pure Python - no FUSE kernel module needed
2. Works on any platform (including CI/containers)
3. Same code path for local and remote files
4. Integrates with nibabel via file-like objects

## Implementation Phases

### Phase 0: datalad-fuse Infrastructure

**Goal:** Provide utilities for sparse file access via datalad-fuse's FsspecAdapter (no FUSE mount)

**Components:**
1. `code/src/openneuro_studies/lib/sparse_access.py`:
   - `SparseDataset` class wrapping FsspecAdapter
   - `list_files(pattern)` - list files matching glob pattern (from git tree)
   - `get_file_size(path)` - get size from annex key (no download)
   - `open_file(path)` - return fsspec file-like object for remote access
   - Graceful fallback if datalad-fuse not installed

2. Integration tests:
   - `code/tests/integration/test_sparse_access.py`
   - Test file listing without clone
   - Test size extraction from annex keys
   - Test remote file open with fsspec
   - Test nibabel header reading via sparse access

**Example API:**
```python
from openneuro_studies.lib.sparse_access import SparseDataset

# Open dataset for sparse access (no clone, no mount)
with SparseDataset("/path/to/study-ds000001/sourcedata/ds000001") as ds:
    # List files from git tree
    subjects = ds.list_dirs("sub-*")
    print(f"Found {len(subjects)} subjects")

    # Get file size from annex key (no download)
    size = ds.get_file_size("sub-01/anat/sub-01_T1w.nii.gz")

    # Open for reading (fsspec handles HTTP range requests)
    with ds.open_file("sub-01/anat/sub-01_T1w.nii.gz") as f:
        import nibabel as nib
        img = nib.Nifti1Image.from_stream(f)
        shape = img.shape  # Only reads header
```

### Phase 1: Raw Dataset Metadata (No Mounting Required)

**Target columns:** `raw_version`, `author_lead_raw`, `author_senior_raw`

**Approach:** Use existing cached data from discovery phase

**Implementation:**
1. Extend `collect_study_metadata()` in `studies_tsv.py`
2. For single-source studies:
   - Read cached dataset_description.json from discovery
   - Extract `Authors[0]` → author_lead_raw
   - Extract `Authors[-1]` → author_senior_raw
   - If single author, duplicate for both fields
3. For multi-source studies:
   - If all sources have same lead/senior authors, use those
   - Otherwise use "n/a"
4. Get `raw_version` from git tags (already cached in metadata)

### Phase 2: Directory-Based Counts (Sparse Access)

**Target columns:** `subjects_num`, `sessions_num`, `sessions_min`, `sessions_max`, `datatypes`

**Approach:** Use SparseDataset to list directories from git tree (no download)

**Implementation:**
1. Create `code/src/openneuro_studies/metadata/summary_extractor.py`
2. Function `extract_directory_summary(study_path: Path) -> dict`:
   ```python
   from openneuro_studies.lib.sparse_access import SparseDataset

   def extract_directory_summary(study_path: Path) -> dict:
       """Extract summary from directory structure via sparse access."""
       # Find sourcedata subdataset
       source_paths = list((study_path / "sourcedata").iterdir())
       if not source_paths:
           return {"subjects_num": "n/a", ...}

       with SparseDataset(source_paths[0]) as ds:
           # List sub-* directories from git tree
           subjects = ds.list_dirs("sub-*")
           subjects_num = len(subjects)

           # Count sessions per subject
           session_counts = []
           for sub in subjects:
               sessions = ds.list_dirs(f"{sub}/ses-*")
               if sessions:
                   session_counts.append(len(sessions))

           sessions_num = sum(session_counts) if session_counts else 0
           sessions_min = min(session_counts) if session_counts else "n/a"
           sessions_max = max(session_counts) if session_counts else "n/a"

           # Identify datatypes
           datatypes = ds.list_bids_datatypes()

           return {
               "subjects_num": subjects_num,
               "sessions_num": sessions_num,
               "sessions_min": sessions_min,
               "sessions_max": sessions_max,
               "datatypes": ",".join(sorted(datatypes)) if datatypes else "n/a",
           }
   ```

### Phase 3: File Counts (Sparse Access)

**Target columns:** `bold_num`, `t1w_num`, `t2w_num`

**Approach:** Use SparseDataset to list files matching BIDS patterns

**Implementation:**
1. Extend `summary_extractor.py`
2. Function `extract_file_counts(study_path: Path) -> dict`:
   ```python
   def extract_file_counts(study_path: Path) -> dict:
       """Count imaging files by modality via sparse access."""
       source_paths = list((study_path / "sourcedata").iterdir())
       if not source_paths:
           return {"bold_num": "n/a", "t1w_num": "n/a", "t2w_num": "n/a"}

       with SparseDataset(source_paths[0]) as ds:
           # List files matching BIDS patterns
           bold_files = ds.list_files("**/func/*_bold.nii*")
           t1w_files = ds.list_files("**/anat/*_T1w.nii*")
           t2w_files = ds.list_files("**/anat/*_T2w.nii*")

           return {
               "bold_num": len(bold_files),
               "t1w_num": len(t1w_files),
               "t2w_num": len(t2w_files),
           }
   ```

### Phase 4: File Sizes (From Annex Keys)

**Target columns:** `bold_size`, `t1w_size`, `bold_size_max`

**Approach:** Parse sizes from git-annex keys (no download required)

**Implementation:**
1. Extend `summary_extractor.py`
2. Function `extract_file_sizes(study_path: Path) -> dict`:
   ```python
   def extract_file_sizes(study_path: Path) -> dict:
       """Extract file sizes from annex keys without downloading."""
       source_paths = list((study_path / "sourcedata").iterdir())
       if not source_paths:
           return {"bold_size": "n/a", "t1w_size": "n/a", "bold_size_max": "n/a"}

       with SparseDataset(source_paths[0]) as ds:
           # Get file sizes from annex keys
           bold_files = ds.list_files("**/func/*_bold.nii*")
           bold_sizes = [ds.get_file_size(f) for f in bold_files]
           bold_sizes = [s for s in bold_sizes if s is not None]

           t1w_files = ds.list_files("**/anat/*_T1w.nii*")
           t1w_sizes = [ds.get_file_size(f) for f in t1w_files]
           t1w_sizes = [s for s in t1w_sizes if s is not None]

           return {
               "bold_size": sum(bold_sizes) if bold_sizes else 0,
               "t1w_size": sum(t1w_sizes) if t1w_sizes else 0,
               "bold_size_max": max(bold_sizes) if bold_sizes else 0,
           }
   ```

**Note:** Git-annex keys encode sizes in the key name: `SHA256E-s12345678--hash.nii.gz` where `s12345678` is the size in bytes.

### Phase 5: Voxel Counts (fsspec + nibabel)

**Target columns:** `bold_voxels`

**Approach:** Open NIfTI headers via fsspec, read dimensions with nibabel

**Implementation:**
1. Create `code/src/openneuro_studies/metadata/imaging_metrics.py`
2. Function `extract_nifti_dimensions(fileobj) -> tuple`:
   ```python
   import nibabel as nib

   def extract_nifti_dimensions(fileobj) -> tuple:
       """Extract dimensions from NIfTI header (reads ~352 bytes only)."""
       # nibabel can read from file-like objects
       img = nib.Nifti1Image.from_stream(fileobj)
       return img.shape
   ```
3. Function `extract_voxel_counts(study_path: Path) -> dict`:
   ```python
   def extract_voxel_counts(study_path: Path) -> dict:
       """Extract total voxel counts across BOLD files via sparse access."""
       source_paths = list((study_path / "sourcedata").iterdir())
       if not source_paths:
           return {"bold_voxels": "n/a"}

       with SparseDataset(source_paths[0]) as ds:
           bold_files = ds.list_files("**/func/*_bold.nii*")
           total_voxels = 0

           for bold_file in bold_files:
               try:
                   with ds.open_file(bold_file) as f:
                       shape = extract_nifti_dimensions(f)
                       voxels = int(np.prod(shape[:3]))  # X * Y * Z
                       if len(shape) > 3:
                           voxels *= shape[3]  # Include time dimension
                       total_voxels += voxels
               except Exception as e:
                   logger.warning(f"Failed to read {bold_file}: {e}")
                   continue

           return {"bold_voxels": total_voxels if total_voxels > 0 else "n/a"}
   ```

## Implementation Order

```
Phase 0: datalad-fuse Infrastructure (Pure Python, no FUSE mount)
  ├── lib/sparse_access.py (SparseDataset wrapper)
  └── tests/integration/test_sparse_access.py

Phase 1: Raw Dataset Metadata (from cached data)
  └── author_lead_raw, author_senior_raw, raw_version

Phase 2: Directory Counts (sparse access - git tree listing)
  └── subjects_num, sessions_*, datatypes

Phase 3: File Counts (sparse access - git tree listing)
  └── bold_num, t1w_num, t2w_num

Phase 4: File Sizes (sparse access - annex key parsing)
  └── bold_size, t1w_size, bold_size_max

Phase 5: Voxel Counts (sparse access - fsspec + nibabel headers)
  └── bold_voxels
```

## CLI Integration

Use `--stage` option to control extraction depth:

```bash
# Basic metadata only (from cached data, no sparse access)
openneuro-studies metadata generate --stage basic

# Include directory/file counts (sparse access - git tree only)
openneuro-studies metadata generate --stage counts

# Include file sizes (sparse access - annex key parsing)
openneuro-studies metadata generate --stage sizes

# Full extraction with NIfTI headers (sparse access - fsspec + nibabel)
openneuro-studies metadata generate --stage imaging
```

## Data Flow

```
discover → discovered-datasets.json (includes cached dataset_description.json)
    ↓
organize → study-*/sourcedata/{id}/ (submodule links, no clone)
    ↓
metadata --stage=basic → studies.tsv (from cached data only)
    ↓
metadata --stage=counts → studies.tsv (+ counts via git tree listing)
    ↓
metadata --stage=sizes → studies.tsv (+ file sizes from annex keys)
    ↓
metadata --stage=imaging → studies.tsv (+ NIfTI headers via fsspec, ~352 bytes per file)
```

**Note:** No FUSE mounting required at any stage. All sparse access is done via:
1. `git ls-tree` for directory/file listings
2. Symlink target parsing for annex key sizes
3. `git annex whereis` + fsspec HTTPFileSystem for remote file content

## Testing Strategy

**Unit Tests:**
- Parse subject/session patterns from paths
- Parse annex key sizes from symlink targets
- Extract file counts from git tree output
- Parse NIfTI dimensions from headers

**Integration Tests:**
1. Open sample study via SparseDataset
2. List files/directories from git tree
3. Extract file sizes from annex keys
4. Open remote file via fsspec and read NIfTI header
5. Verify no full downloads occurred (check network traffic / cache)

**Test Datasets:**
- Use existing study-ds000001, study-ds005256, etc.
- Small datasets to minimize test time
- Test with both local content and remote-only content

## Dependencies

```python
# Add to pyproject.toml
[project.optional-dependencies]
imaging = [
    "datalad-fuse>=0.4.0",  # FsspecAdapter for sparse access
    "fsspec>=2023.1.0",     # Remote file access
    "aiohttp",              # For fsspec HTTP async
    "nibabel>=5.0.0",       # For NIfTI header reading
]
```

## Open Questions

1. Use datalad-fuse's FsspecAdapter or implement minimal version?
   - **Recommendation:** Start with datalad-fuse, fall back to minimal if issues
2. How to handle network failures during sparse access?
   - **Recommendation:** Fall back to "n/a" for affected columns, log error
3. Cache sparse access results?
   - **Recommendation:** Yes, cache summary extractions with timestamp in `.openneuro-studies/cache/`
4. Multi-source studies: aggregate or report per-source?
   - **Recommendation:** Aggregate (sum counts, max sizes)
5. What if datalad-fuse not installed?
   - **Recommendation:** Gracefully skip imaging stages, populate "n/a", warn user

## Next Steps

1. Implement Phase 0 (SparseDataset wrapper for datalad-fuse)
2. Write integration tests for sparse access
3. Implement Phase 1 (raw metadata from cache)
4. Implement Phases 2-3 (counts via git tree)
5. Test on sample studies
6. Implement Phases 4-5 (sizes from annex keys, voxels from nibabel)
