# Studies.tsv Summary Columns Implementation Plan

Date: 2025-12-18
Status: Planning
Approach: **datalad-fuse sparse access** (generalizable, works with any git forge)

## Summary

This document plans the implementation of missing summary columns in studies.tsv per FR-009, FR-031, FR-032, FR-033.

**Key Decision**: Use datalad-fuse to mount the entire repository hierarchy with sparse access. This approach:
- Is generalizable (works with any git forge, not just GitHub)
- Avoids full cloning (git-annex fetches content on-demand)
- Provides a filesystem interface for metadata extraction
- Works uniformly across all data sources

## Current State

studies.tsv has these columns with `n/a` values that need implementation:

| Column | Description | Data Source | Extraction Method |
|--------|-------------|-------------|-------------------|
| `subjects_num` | Number of subjects | sub-* directories | Count via fuse mount |
| `sessions_num` | Total sessions | ses-* directories | Count via fuse mount |
| `sessions_min` | Min sessions/subject | ses-* per subject | Count via fuse mount |
| `sessions_max` | Max sessions/subject | ses-* per subject | Count via fuse mount |
| `bold_num` | BOLD file count | *_bold.nii* files | Count via fuse mount |
| `t1w_num` | T1w file count | *_T1w.nii* files | Count via fuse mount |
| `t2w_num` | T2w file count | *_T2w.nii* files | Count via fuse mount |
| `datatypes` | Present datatypes | Datatype directories | List via fuse mount |
| `raw_version` | Source dataset version | Git tags | Already in metadata cache |
| `author_lead_raw` | First author from raw | dataset_description.json | Already in metadata cache |
| `author_senior_raw` | Last author from raw | dataset_description.json | Already in metadata cache |
| `bold_size` | Total BOLD size | File sizes | stat() via fuse mount |
| `t1w_size` | Total T1w size | File sizes | stat() via fuse mount |
| `bold_size_max` | Max BOLD size | File sizes | stat() via fuse mount |
| `bold_voxels` | Total BOLD voxels | NIfTI headers | Read first 1KB via fuse mount |

## datalad-fuse Background

**What is datalad-fuse?**
- FUSE filesystem that mounts DataLad datasets
- Provides lazy access to git-annex content (fetched on-demand)
- No full clone required - only accessed files are retrieved
- Works as a normal filesystem mount point

**How it works:**
```bash
# Mount a study dataset hierarchy
datalad-fuse /path/to/OpenNeuroStudies /tmp/fuse-mount

# Access appears as normal filesystem
ls /tmp/fuse-mount/study-ds000001/sourcedata/ds000001/
# → Fetches directory listing without downloading files

stat /tmp/fuse-mount/study-ds000001/sourcedata/ds000001/sub-01/anat/sub-01_T1w.nii.gz
# → Returns file size from git-annex key (no download)

head -c 1024 /tmp/fuse-mount/.../sub-01_T1w.nii.gz
# → Downloads only first 1KB from git-annex remote
```

## Implementation Phases

### Phase 0: datalad-fuse Infrastructure

**Goal:** Provide utilities for managing datalad-fuse mounts

**Components:**
1. `code/src/openneuro_studies/lib/fuse_mount.py`:
   - `FuseMount` context manager class
   - `mount_repository()` - mount entire repo hierarchy
   - `unmount()` - clean unmount
   - Error handling for mount failures

2. Integration tests:
   - `code/tests/integration/test_fuse_mount.py`
   - Test mounting/unmounting
   - Test directory listing through mount
   - Test file stat() without download

**Example API:**
```python
from openneuro_studies.lib.fuse_mount import FuseMount

# Context manager auto-mounts and unmounts
with FuseMount(repo_path, mount_point="/tmp/fuse") as mount:
    # Access files through mount point
    subjects = list((mount.path / "study-ds000001/sourcedata/ds000001").glob("sub-*"))
    print(f"Found {len(subjects)} subjects")
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

### Phase 2: Directory-Based Counts (Fuse Mount)

**Target columns:** `subjects_num`, `sessions_num`, `sessions_min`, `sessions_max`, `datatypes`

**Approach:** Mount via datalad-fuse, traverse directory structure

**Implementation:**
1. Create `code/src/openneuro_studies/metadata/summary_extractor.py`
2. Function `extract_directory_summary(study_path: Path, fuse_mount: FuseMount) -> dict`:
   ```python
   def extract_directory_summary(study_path: Path, fuse_mount: FuseMount) -> dict:
       """Extract summary from directory structure via fuse mount."""
       source_path = fuse_mount.path / study_path / "sourcedata"

       # Find all sub-* directories
       subjects = list(source_path.glob("*/sub-*"))
       subjects_num = len(subjects)

       # Count sessions per subject
       session_counts = []
       for sub_dir in subjects:
           sessions = list(sub_dir.glob("ses-*"))
           if sessions:
               session_counts.append(len(sessions))

       sessions_num = sum(session_counts) if session_counts else 0
       sessions_min = min(session_counts) if session_counts else "n/a"
       sessions_max = max(session_counts) if session_counts else "n/a"

       # Identify datatypes (anat/, func/, dwi/, etc.)
       datatypes = set()
       for datatype_dir in source_path.glob("*/sub-*/*/"):
           if datatype_dir.name in ["anat", "func", "dwi", "fmap", "perf", "meg", "eeg", "ieeg"]:
               datatypes.add(datatype_dir.name)

       return {
           "subjects_num": subjects_num,
           "sessions_num": sessions_num,
           "sessions_min": sessions_min,
           "sessions_max": sessions_max,
           "datatypes": ",".join(sorted(datatypes)) if datatypes else "n/a",
       }
   ```

### Phase 3: File Counts (Fuse Mount)

**Target columns:** `bold_num`, `t1w_num`, `t2w_num`

**Approach:** Mount via datalad-fuse, glob for file patterns

**Implementation:**
1. Extend `summary_extractor.py`
2. Function `extract_file_counts(study_path: Path, fuse_mount: FuseMount) -> dict`:
   ```python
   def extract_file_counts(study_path: Path, fuse_mount: FuseMount) -> dict:
       """Count imaging files by modality via fuse mount."""
       source_path = fuse_mount.path / study_path / "sourcedata"

       # Use glob patterns for BIDS imaging files
       bold_files = list(source_path.glob("**/func/*_bold.nii*"))
       t1w_files = list(source_path.glob("**/anat/*_T1w.nii*"))
       t2w_files = list(source_path.glob("**/anat/*_T2w.nii*"))

       return {
           "bold_num": len(bold_files),
           "t1w_num": len(t1w_files),
           "t2w_num": len(t2w_files),
       }
   ```

### Phase 4: File Sizes (Fuse Mount with stat)

**Target columns:** `bold_size`, `t1w_size`, `bold_size_max`

**Approach:** Use stat() on fuse mount - git-annex keys encode sizes

**Implementation:**
1. Extend `summary_extractor.py`
2. Function `extract_file_sizes(study_path: Path, fuse_mount: FuseMount) -> dict`:
   ```python
   def extract_file_sizes(study_path: Path, fuse_mount: FuseMount) -> dict:
       """Extract file sizes via stat() without downloading."""
       source_path = fuse_mount.path / study_path / "sourcedata"

       # Get BOLD files and their sizes
       bold_files = list(source_path.glob("**/func/*_bold.nii*"))
       bold_sizes = [f.stat().st_size for f in bold_files]

       # Get T1w sizes
       t1w_files = list(source_path.glob("**/anat/*_T1w.nii*"))
       t1w_sizes = [f.stat().st_size for f in t1w_files]

       return {
           "bold_size": sum(bold_sizes) if bold_sizes else 0,
           "t1w_size": sum(t1w_sizes) if t1w_sizes else 0,
           "bold_size_max": max(bold_sizes) if bold_sizes else 0,
       }
   ```

**Note:** stat() on annex files returns size without download - encoded in symlink target.

### Phase 5: Voxel Counts (Fuse Mount with NIfTI Headers)

**Target columns:** `bold_voxels`

**Approach:** Read first 352 bytes of NIfTI files (header) via fuse mount

**Implementation:**
1. Create `code/src/openneuro_studies/metadata/imaging_metrics.py`
2. Function `extract_nifti_voxels(nifti_path: Path) -> int`:
   ```python
   import nibabel as nib

   def extract_nifti_voxels(nifti_path: Path) -> int:
       """Extract voxel count from NIfTI header (reads ~1KB only)."""
       # nibabel reads header first, no full download
       img = nib.load(str(nifti_path))
       shape = img.shape
       return int(np.prod(shape[:3]))  # X * Y * Z dimensions
   ```
3. Function `extract_voxel_counts(study_path: Path, fuse_mount: FuseMount) -> dict`:
   ```python
   def extract_voxel_counts(study_path: Path, fuse_mount: FuseMount) -> dict:
       """Extract total voxel counts across BOLD files."""
       source_path = fuse_mount.path / study_path / "sourcedata"

       bold_files = list(source_path.glob("**/func/*_bold.nii*"))
       total_voxels = 0

       for bold_file in bold_files:
           try:
               voxels = extract_nifti_voxels(bold_file)
               # For 4D files, multiply by time dimension
               img = nib.load(str(bold_file))
               if len(img.shape) > 3:
                   voxels *= img.shape[3]  # Include time dimension
               total_voxels += voxels
           except Exception as e:
               logger.warning(f"Failed to read {bold_file}: {e}")
               continue

       return {"bold_voxels": total_voxels if total_voxels > 0 else "n/a"}
   ```

## Implementation Order

```
Phase 0: datalad-fuse Infrastructure
  ├── lib/fuse_mount.py (mount utilities)
  └── tests/integration/test_fuse_mount.py

Phase 1: Raw Dataset Metadata (no mount)
  └── author_lead_raw, author_senior_raw, raw_version

Phase 2: Directory Counts (fuse mount)
  └── subjects_num, sessions_*, datatypes

Phase 3: File Counts (fuse mount)
  └── bold_num, t1w_num, t2w_num

Phase 4: File Sizes (fuse mount + stat)
  └── bold_size, t1w_size, bold_size_max

Phase 5: Voxel Counts (fuse mount + NIfTI headers)
  └── bold_voxels
```

## CLI Integration

Use `--stage` option to control extraction depth:

```bash
# Basic metadata only (no mount required)
openneuro-studies metadata generate --stage basic

# Include directory/file counts (fuse mount, no downloads)
openneuro-studies metadata generate --stage counts

# Include file sizes (fuse mount + stat)
openneuro-studies metadata generate --stage sizes

# Full extraction with NIfTI headers (fuse mount + partial downloads)
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
datalad-fuse mount → /tmp/fuse-mount/
    ↓
metadata --stage=counts → studies.tsv (+ directory/file counts via mount)
    ↓
metadata --stage=sizes → studies.tsv (+ file sizes via stat)
    ↓
metadata --stage=imaging → studies.tsv (+ NIfTI headers, ~1KB per file)
    ↓
datalad-fuse unmount
```

## Testing Strategy

**Unit Tests:**
- Parse subject/session patterns from paths
- Extract file counts from lists
- Parse NIfTI headers

**Integration Tests:**
1. Mount sample study via datalad-fuse
2. Extract directory summary without errors
3. Verify counts match expected values
4. Verify no full downloads occurred (check disk usage)

**Test Datasets:**
- Use existing study-ds000001, study-ds005256, etc.
- Small datasets to minimize test time

## Dependencies

```python
# Add to pyproject.toml
[project.optional-dependencies]
imaging = [
    "datalad-fuse>=0.4.0",
    "nibabel>=5.0.0",  # For NIfTI header reading
]
```

## Open Questions

1. Should we mount once for all studies or per-study?
   - **Recommendation:** Mount once at repo root, process all studies
2. How to handle mount failures?
   - **Recommendation:** Fall back to "n/a" for affected columns, log error
3. Cache fuse mount results?
   - **Recommendation:** Yes, cache summary extractions with timestamp
4. Multi-source studies: aggregate or report per-source?
   - **Recommendation:** Aggregate (sum counts, max sizes)
5. What if datalad-fuse not installed?
   - **Recommendation:** Gracefully skip imaging stages, populate "n/a"

## Next Steps

1. Implement Phase 0 (fuse mount utilities)
2. Write integration tests for fuse mounting
3. Implement Phase 1 (raw metadata from cache)
4. Implement Phases 2-3 (counts via fuse)
5. Test on sample studies
6. Implement Phases 4-5 (sizes and voxels)
