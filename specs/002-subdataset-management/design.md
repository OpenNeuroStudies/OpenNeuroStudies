# Design: Temporary Subdataset Installation for Metadata Extraction

## Context

**Problem**: Studies have all `n/a` values in `studies.tsv` (except study-ds000001, ds005256, ds006131-ds006192) because their `sourcedata/` subdatasets are not initialized.

**Root Cause**: The organization process creates gitlinks (git submodule references) without initializing subdatasets. This is intentional and correct for performance — creating 1000+ gitlinks without cloning is fast. However, metadata extraction requires access to the git tree (commits, file lists) of sourcedata subdatasets.

**What Extraction Needs**:
- Git tree available in `sourcedata/*/` subdatasets (for `git ls-tree`, `git describe --tags`, reading `dataset_description.json`)
- Does NOT need annexed file content downloaded (sparse access via `SparseDataset` uses symlink parsing and git commands)
- Does NOT need derivatives initialized (confirmed: no extraction code reads from `derivatives/`)

**User Requirements**:
- Install sourcedata subdatasets "temporarily only" for extraction
- Preserve state: if subdataset already installed, don't uninstall after
- Avoid duplication between Python code layer and Snakemake layer
- Make process efficient and observable
- **Use DataLad's existing functionality** - don't reinvent subdataset management

## Key Facts from Research

### DataLad Dataset API

**`Dataset.is_installed()`** - Check if dataset is installed:
```python
from datalad.distribution.dataset import Dataset

ds = Dataset('study-ds000001/sourcedata/ds000001')
if ds.is_installed():
    # Git repository exists, can use sparse access
```

**`Dataset.subdatasets()`** - List subdatasets with state:
```python
subdatasets = list(parent_ds.subdatasets(result_renderer='disabled'))
for sd in subdatasets:
    path = sd['path']
    state = sd['state']  # 'absent' or 'present'
```

**`parent_ds.get(path)`** - Install subdataset (only git tree, no content):
```python
# DataLad accepts absolute paths - no need to compute relative paths
parent_ds = Dataset('study-ds000001')
subdataset_path = Path('study-ds000001/sourcedata/ds000001')

# Install using absolute path directly
parent_ds.get(str(subdataset_path), get_data=False)
```

**`parent_ds.drop(path, what='datasets')`** - Uninstall subdataset:
```python
# Drop subdataset (removes git tree, keeps gitlink)
# DataLad accepts absolute paths directly
parent_ds.drop(str(subdataset_path), what='datasets')
```

### Existing Patterns in Codebase
- **No datalad install calls** in current workflow — only one test uses `datalad install -r`
- **Gitlink creation without cloning** via `link_gitmodule()` (organization/submodule_linker.py)
- **Thread-safe locking** via `parent_repo_lock` and `study_lock()` (lib/locks.py)
- **SHA-based dependency tracking** via Snakemake params + `--rerun-triggers params`

## Solution Architecture: Two-Layer Design with DataLad API

### Layer 1: bids_studies.subdatasets (Generic BIDS Toolkit)
**File**: `code/src/bids_studies/subdatasets/__init__.py` (new module)

**Purpose**: Generic utilities for managing subdatasets during BIDS metadata extraction. Not OpenNeuro-specific.

**Error Handling Strategy**:
- **Transient errors** (network issues, file locks): Retry with exponential backoff
- **Permanent errors** (missing subdataset, invalid git repo): Fail immediately with clear error
- **No silent failures**: All errors either retry or raise exceptions
- **Observability**: Log all operations (install/drop) and errors

**Module Structure**:

```python
# code/src/bids_studies/subdatasets/__init__.py
"""Subdataset management utilities for BIDS study datasets."""

import logging
import time
from pathlib import Path
from typing import Iterator

from datalad.distribution.dataset import Dataset
from datalad.support.exceptions import IncompleteResultsError
import datalad.api as dl

logger = logging.getLogger(__name__)


# ============================================================================
# Low-level utilities
# ============================================================================

def iter_sourcedata_subdatasets(study_path: Path) -> Iterator[Path]:
    """Iterate over sourcedata subdataset paths in a study.

    Yields absolute paths to all subdatasets under study_path/sourcedata/,
    regardless of whether they are installed.

    Args:
        study_path: Path to study directory

    Yields:
        Absolute paths to sourcedata subdatasets
    """
    parent_ds = Dataset(str(study_path))
    if not parent_ds.is_installed():
        return

    subdatasets = list(parent_ds.subdatasets(result_renderer='disabled'))
    for sd in subdatasets:
        sd_path = Path(sd['path'])
        # Filter for sourcedata subdatasets
        if 'sourcedata' in sd_path.parts:
            yield sd_path


def get_subdataset_states(study_path: Path) -> dict[Path, str]:
    """Get installation state of all sourcedata subdatasets.

    Args:
        study_path: Path to study directory

    Returns:
        Dict mapping subdataset path to state ('absent' or 'present')
    """
    states = {}
    for sd_path in iter_sourcedata_subdatasets(study_path):
        ds = Dataset(str(sd_path))
        states[sd_path] = 'present' if ds.is_installed() else 'absent'
    return states


def ensure_subdatasets_installed(
    study_path: Path,
    get_data: bool = False,
    max_retries: int = 3
) -> tuple[set[Path], set[Path]]:
    """Install sourcedata subdatasets if not already installed.

    Args:
        study_path: Path to study directory
        get_data: If True, also get file content (not just git tree)
        max_retries: Maximum retry attempts for transient errors

    Returns:
        Tuple of (newly_installed, already_installed) path sets

    Raises:
        Exception: If installation fails after retries or on non-transient errors
    """
    newly_installed = set()
    already_installed = set()

    parent_ds = Dataset(str(study_path))

    for sd_path in iter_sourcedata_subdatasets(study_path):
        ds = Dataset(str(sd_path))

        if ds.is_installed():
            already_installed.add(sd_path)
        else:
            # Install using parent dataset's get method with retries
            # DataLad accepts absolute paths directly - no need for relative_to()
            last_error = None
            for attempt in range(max_retries):
                try:
                    parent_ds.get(str(sd_path), get_data=get_data,
                                 result_renderer='disabled')
                    newly_installed.add(sd_path)
                    logger.info(f"Installed subdataset: {sd_path}")
                    break
                except (IncompleteResultsError, OSError, IOError) as e:
                    # Transient errors: network issues, file locks, etc.
                    last_error = e
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt  # Exponential backoff
                        logger.warning(
                            f"Transient error installing {sd_path} "
                            f"(attempt {attempt + 1}/{max_retries}): {e}. "
                            f"Retrying in {wait_time}s..."
                        )
                        time.sleep(wait_time)
                    else:
                        logger.error(
                            f"Failed to install {sd_path} after {max_retries} attempts"
                        )
                        raise RuntimeError(
                            f"Installation failed after {max_retries} retries: {e}"
                        ) from e
                except Exception as e:
                    # Non-transient error: fail immediately
                    logger.error(f"Fatal error installing {sd_path}: {e}")
                    raise RuntimeError(
                        f"Installation of {sd_path} failed with unexpected error: {e}"
                    ) from e

    return newly_installed, already_installed


def drop_subdatasets(
    subdataset_paths: set[Path],
    study_path: Path,
    reckless: bool = False,
    max_retries: int = 3
) -> set[Path]:
    """Drop (uninstall) subdatasets.

    Args:
        subdataset_paths: Set of subdataset paths to drop
        study_path: Parent study path
        reckless: Skip safety checks for faster operation (default: False)
                 TODO: Consider enabling after verifying correct operation.
                 Using reckless='kill' skips DataLad's availability checks,
                 which is appropriate for local-only datasets but bypasses
                 safety mechanisms during development.
        max_retries: Maximum retry attempts for transient errors

    Returns:
        Set of successfully dropped paths

    Raises:
        Exception: If drop fails after retries or on non-transient errors
    """
    dropped = set()
    parent_ds = Dataset(str(study_path))

    for sd_path in subdataset_paths:
        # DataLad accepts absolute paths directly - no need for relative_to()
        last_error = None
        for attempt in range(max_retries):
            try:
                # Use safe mode by default; reckless='kill' can be enabled later
                # for performance after verifying correctness
                parent_ds.drop(str(sd_path),
                              what='datasets',
                              reckless='kill' if reckless else None,
                              result_renderer='disabled')
                dropped.add(sd_path)
                logger.info(f"Dropped subdataset: {sd_path}")
                break
            except (IncompleteResultsError, OSError, IOError) as e:
                # Transient errors: file locks, network issues, etc.
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(
                        f"Transient error dropping {sd_path} "
                        f"(attempt {attempt + 1}/{max_retries}): {e}. "
                        f"Retrying in {wait_time}s..."
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(
                        f"Failed to drop {sd_path} after {max_retries} attempts"
                    )
                    raise RuntimeError(
                        f"Drop failed after {max_retries} retries: {e}"
                    ) from e
            except Exception as e:
                # Non-transient error: fail immediately
                logger.error(f"Fatal error dropping {sd_path}: {e}")
                raise RuntimeError(
                    f"Drop of {sd_path} failed with unexpected error: {e}"
                ) from e

    return dropped


class TemporarySubdatasetInstall:
    """Context manager for temporary subdataset installation.

    Installs sourcedata subdatasets on entry, drops newly-installed ones on exit.
    Preserves the installation state of subdatasets that were already installed.

    Example:
        with TemporarySubdatasetInstall(study_path) as (newly, existing):
            # All sourcedata subdatasets are now installed
            # Extract metadata here
            pass
        # Newly installed subdatasets are dropped, existing ones preserved
    """

    def __init__(self, study_path: Path, get_data: bool = False,
                 reckless_drop: bool = False):
        self.study_path = study_path
        self.get_data = get_data
        self.reckless_drop = reckless_drop
        self.newly_installed = set()
        self.already_installed = set()

    def __enter__(self):
        self.newly_installed, self.already_installed = \
            ensure_subdatasets_installed(self.study_path, self.get_data)
        return self.newly_installed, self.already_installed

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Only drop subdatasets we installed
        if self.newly_installed:
            drop_subdatasets(self.newly_installed, self.study_path,
                           reckless=self.reckless_drop)
        return False  # Don't suppress exceptions


# ============================================================================
# High-level interface for extraction with managed subdatasets
# ============================================================================

def extract_study_with_subdatasets(
    study_path: Path,
    stage: str = "basic",
    get_data: bool = False,
    reckless_drop: bool = False
) -> dict:
    """Extract study metadata with automatic subdataset management.

    High-level function that:
    1. Installs sourcedata subdatasets if needed
    2. Extracts metadata at specified stage
    3. Drops newly-installed subdatasets (preserves existing ones)

    This is the main entry point for both CLI and Snakemake workflows.

    Args:
        study_path: Path to study directory
        stage: Extraction stage ("basic", "counts", "sizes", "imaging")
        get_data: If True, also get file content (not just git tree)
        reckless_drop: Skip safety checks when dropping subdatasets

    Returns:
        Dictionary with extracted metadata (all studies.tsv columns)

    Raises:
        Exception: If subdataset installation/drop or extraction fails

    Example:
        # Use from CLI or Snakemake
        from bids_studies.subdatasets import extract_study_with_subdatasets

        result = extract_study_with_subdatasets(
            Path('study-ds000001'),
            stage='imaging'
        )
        # result contains: study_id, subjects_num, bold_num, etc.
    """
    # Import here to avoid circular dependencies
    # NOTE: This assumes bids_studies.extraction module exists with this function
    # or we import from openneuro_studies if extraction lives there
    from bids_studies.extraction import extract_metadata

    with TemporarySubdatasetInstall(study_path, get_data, reckless_drop) as (newly, existing):
        if newly:
            logger.info(f"Installed {len(newly)} sourcedata subdatasets for {study_path.name}")
        if existing:
            logger.info(f"Using {len(existing)} already-installed subdatasets")

        # Extract metadata with subdatasets now available
        result = extract_metadata(study_path, stage=stage)
        logger.info(f"Extracted metadata for {study_path.name}")

    # Subdatasets automatically dropped on context exit
    return result
```

**Design Notes**:
- **Module-level imports and logger** - proper Python style, not inside functions
- **High-level interface** - `extract_study_with_subdatasets()` does everything
- **CLI-ready** - can be called directly without Snakemake
- **Snakemake-friendly** - Snakemake just calls this one function

**Design Notes**:
- **Module-level imports and logger** - proper Python style, not inside functions
- **Pure DataLad API** - no raw git submodule commands
- **Generic BIDS utilities** - works with any BIDS study dataset, not OpenNeuro-specific
- **State preservation** - tracks what was already installed vs newly installed
- **Context manager pattern** - automatic cleanup via `__exit__`
- **High-level interface** - `extract_study_with_subdatasets()` for CLI and Snakemake
- **Thread-safe** - DataLad handles locking internally
- **Robust error handling** - retries transient errors, fails on unexpected errors
- **No relative path computation** - DataLad accepts absolute paths directly
- **Guaranteed operation** - failures raise exceptions, not just logged

### Layer 2: bids_studies.extraction Integration
**File**: `code/src/bids_studies/extraction/study.py` (or similar)

**Purpose**: Wrap existing extraction logic to use subdataset management.

**Note**: This assumes `bids_studies.extraction` module exists or will be created. If extraction logic currently lives in `openneuro_studies.metadata`, it should be moved to `bids_studies` for reusability.

```python
# code/src/bids_studies/extraction/study.py (or appropriate location)
"""Study-level metadata extraction."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_metadata(study_path: Path, stage: str = "basic") -> dict:
    """Extract all metadata for a study.

    This function performs the actual extraction logic that currently lives in
    openneuro_studies.metadata.studies_tsv.collect_study_metadata().

    Args:
        study_path: Path to study directory
        stage: Extraction stage ("basic", "counts", "sizes", "imaging")

    Returns:
        Dictionary with all studies.tsv columns
    """
    # TODO: Move extraction logic from openneuro_studies to here
    # For now, delegate to existing implementation
    from openneuro_studies.metadata.studies_tsv import collect_study_metadata
    return collect_study_metadata(study_path, stage=stage)
```

### Layer 3: Snakemake Workflow Integration
**File**: `code/workflow/Snakefile` (minimal modification)

**Approach**: Just call the high-level `extract_study_with_subdatasets()` function.

**Modified Rule**:

```python
rule extract_study:
    """Extract metadata from study with automatic subdataset management."""
    output:
        json_file = ".snakemake/extracted/{study}.json"
    params:
        deps = lambda wc: get_study_deps(wc.study)
    run:
        from pathlib import Path
        import json
        from bids_studies.subdatasets import extract_study_with_subdatasets

        study_path = Path(wildcards.study)

        # Single function call - all logic in bids_studies
        result = extract_study_with_subdatasets(study_path, stage="imaging")

        # Save result
        Path(output.json_file).parent.mkdir(parents=True, exist_ok=True)
        with open(output.json_file, "w") as f:
            json.dump(result, f, indent=2)

        prov_manager.record(output.json_file, "extract_study", params.deps)
```

**Why This Design**:
- ✅ **Ultra-minimal Snakemake code** - just one function call
- ✅ **All logic in bids_studies** - reusable from CLI
- ✅ **No low-level calls** - Snakemake doesn't manage subdatasets directly
- ✅ **Testable** - can test `extract_study_with_subdatasets()` independently
- ✅ **CLI-ready** - same function works outside Snakemake

### Layer 4: CLI Integration
**File**: `code/src/openneuro_studies/cli/main.py`

**Approach**: Use the same high-level function, making subdataset management the default.

```python
@click.command()
@click.option("--stage", type=click.Choice(["basic", "counts", "sizes", "imaging"]),
              default="sizes", help="Extraction stage")
@click.option("--ensure-subdatasets/--no-ensure-subdatasets", default=True,
              help="Temporarily install sourcedata subdatasets (default: enabled)")
@click.argument("studies", nargs=-1)
def metadata_generate(stage: str, ensure_subdatasets: bool, studies: tuple[str, ...]):
    """Generate metadata for studies.

    By default, automatically manages subdataset installation/uninstallation.
    Use --no-ensure-subdatasets to skip (useful if subdatasets already installed).
    """
    from pathlib import Path
    from bids_studies.subdatasets import extract_study_with_subdatasets
    from openneuro_studies.metadata.studies_tsv import collect_study_metadata

    for study in studies:
        study_path = Path(study)

        if ensure_subdatasets:
            # Use high-level function with subdataset management
            result = extract_study_with_subdatasets(study_path, stage=stage)
        else:
            # Direct extraction (assumes subdatasets already available)
            result = collect_study_metadata(study_path, stage=stage)

        # Save or process result...
```

**Why This Design**:
- ✅ **Subdataset management by default** - users don't need to think about it
- ✅ **Can disable if needed** - via `--no-ensure-subdatasets`
- ✅ **Same function as Snakemake** - consistent behavior
- ✅ **Works standalone** - no Snakemake required

## Implementation Steps

### 1. Create bids_studies.subdatasets Module

**File**: `code/src/bids_studies/subdatasets/__init__.py`

Implement:
- **Module-level setup**: imports, logger at top
- `iter_sourcedata_subdatasets()` - iterate sourcedata paths using `Dataset.subdatasets()`
- `get_subdataset_states()` - get current installation states
- `ensure_subdatasets_installed()` - install using `parent_ds.get(path, get_data=False)` with retry
- `drop_subdatasets()` - uninstall using `parent_ds.drop(path, what='datasets')` with retry
- `TemporarySubdatasetInstall` - context manager combining install + drop
- **`extract_study_with_subdatasets()`** - high-level function for CLI and Snakemake

**Error Handling**:
- Retry transient errors with exponential backoff
- Raise exceptions on failures (no silent failures)
- Log all operations for observability

### 2. Create/Update bids_studies.extraction Module (Optional)

**File**: `code/src/bids_studies/extraction/study.py`

If extraction logic should move from `openneuro_studies.metadata` to `bids_studies`:
- Create `extract_metadata(study_path, stage)` function
- Move study-level extraction logic from openneuro_studies
- Make it generic (not OpenNeuro-specific)

Otherwise, `extract_study_with_subdatasets()` can delegate to existing `openneuro_studies` code.

### 3. Modify Snakemake Workflow

**File**: `code/workflow/Snakefile`

- Import `extract_study_with_subdatasets` from `bids_studies.subdatasets`
- **Single function call** - no direct subdataset management
- Let bids_studies handle all the complexity

### 4. Update CLI

**File**: `code/src/openneuro_studies/cli/main.py`

- Import `extract_study_with_subdatasets` from `bids_studies.subdatasets`
- Make `--ensure-subdatasets` default to True
- Use same high-level function as Snakemake

### 5. Update Automation Script

**File**: `.openneuro-studies/process_openneuro_todo`

No changes needed — the script calls Snakemake, which now handles subdataset management automatically.

### 6. Add Tests

**File**: `code/tests/unit/test_bids_subdatasets.py` (new)

Test cases:
- `test_iter_sourcedata_subdatasets` - finds correct subdataset paths
- `test_get_subdataset_states` - correctly identifies absent/present states
- `test_ensure_subdatasets_installed` - actually installs via DataLad
- `test_drop_subdatasets` - successfully drops subdatasets
- `test_temporary_install_context_manager` - preserves original state

**File**: `code/tests/integration/test_extraction_with_subdatasets.py` (new)

Integration test:
- Start with uninitialized study (gitlink only, state='absent')
- Run metadata extraction with context manager
- Verify sourcedata was temporarily installed
- Verify sourcedata is dropped after extraction (state='absent' again)
- Verify extracted metadata is NOT all n/a

### 7. Update pyproject.toml

Ensure `bids_studies.subdatasets` (and optionally `bids_studies.extraction`) are included in package discovery.

## Critical Files

### New Files
- `code/src/bids_studies/subdatasets/__init__.py` - subdataset management using DataLad API
- `code/tests/unit/test_bids_subdatasets.py` - unit tests
- `code/tests/integration/test_extraction_with_subdatasets.py` - integration test

### Modified Files
- `code/workflow/Snakefile` - add context manager to `extract_study` rule
- `code/pyproject.toml` - ensure bids_studies.subdatasets is included

### Unchanged Files (Context Only)
- `code/workflow/lib/git_utils.py` - provides `get_study_deps()` for SHA tracking
- `code/src/openneuro_studies/metadata/summary_extractor.py` - extraction logic
- `code/src/bids_studies/sparse/access.py` - `SparseDataset` (calls `git ls-tree`)

## Advantages of DataLad API Approach

### vs. Raw Git Submodule Commands

| Aspect | DataLad API | Raw Git Commands |
|--------|-------------|------------------|
| **State checking** | `ds.is_installed()` | Parse `git submodule status` output |
| **Installation** | `parent_ds.get(abs_path)` | `git submodule update --init {rel_path}` |
| **Uninstallation** | `parent_ds.drop(abs_path)` | `git submodule deinit -f {rel_path}` |
| **Path handling** | Accepts absolute paths | Requires relative path computation |
| **Listing subdatasets** | `parent_ds.subdatasets()` | Parse `.gitmodules` + check filesystem |
| **Error handling** | Pythonic exceptions + retry | Parse stderr, check exit codes |
| **Locking** | Built-in (DataLad handles) | Manual lock management needed |
| **Provenance** | Automatic (if using `dl.run`) | Manual tracking |

### Benefits

1. **Less code** - DataLad provides high-level API, no subprocess or relative path management
2. **More robust** - DataLad handles edge cases + retry logic for transient errors
3. **Better errors** - Pythonic exceptions with retry/fail logic, not stderr parsing
4. **Guaranteed operation** - Failures raise exceptions, ensuring correctness
5. **Future-proof** - DataLad API is stable, git submodule internals may change
6. **Consistent** - Uses same API as rest of OpenNeuroStudies (already uses DataLad for dataset creation)

## Risks & Mitigations

### Risk: DataLad drop() May Fail for Subdatasets with Annexed Content
**Scenario**: If sourcedata subdataset has annexed content present locally, `drop()` may refuse to drop.

**Mitigation**:
- **Initial approach**: Use safe mode (no reckless) to verify correct operation and catch edge cases
- **Future optimization**: After confirming correct behavior, can enable `reckless='kill'` mode via parameter for faster operation
- This skips DataLad's availability checks (appropriate for local-only datasets) but is disabled by default for safety during development

### Risk: Parallel Snakemake Jobs Race on Same Subdataset
**Scenario**: Two studies share a sourcedata subdataset (unlikely but possible for multi-source derivatives).

**Mitigation**: DataLad handles locking internally. Multiple `get()` calls on same path are safe.

### Risk: Extraction Fails Mid-Process, State Not Restored
**Scenario**: Extraction crashes, `__exit__` doesn't run.

**Mitigation**: Context manager `__exit__` is called even on exceptions (Python guarantee).

### Risk: User Interrupts Snakemake (Ctrl+C)
**Scenario**: SIGINT during extraction, subdatasets left installed.

**Mitigation**: Acceptable — next run will snapshot current state and work correctly. User can manually run `dl.drop()` if needed.

### Risk: Subdataset Installation Takes Long Time
**Scenario**: 1000+ studies × multiple sourcedata each = many git operations.

**Mitigation**:
- Only install uninitialized subdatasets (skip if already `state='present'`)
- DataLad `get()` is already optimized for batch operations
- Snakemake parallelization spreads load across studies

## Verification

### Unit Tests
```bash
cd code
pytest tests/unit/test_bids_subdatasets.py -v
```

### Integration Test
```bash
cd code
pytest tests/integration/test_extraction_with_subdatasets.py -v
```

### End-to-End Workflow
```bash
# 1. Check initial state (should be 'absent')
python3 << 'EOF'
from datalad.distribution.dataset import Dataset
ds = Dataset('study-ds002685/sourcedata/ds002685')
print(f"Before: is_installed = {ds.is_installed()}")
EOF

# 2. Run Snakemake extraction
snakemake -s code/workflow/Snakefile --cores 1 \
  --forcerun extract_study .snakemake/extracted/study-ds002685.json

# 3. Verify extraction succeeded (not all n/a)
python3 -c "
import json
with open('.snakemake/extracted/study-ds002685.json') as f:
    data = json.load(f)
    print(f\"subjects_num: {data['subjects_num']}\")
    print(f\"bold_num: {data['bold_num']}\")
    assert data['subjects_num'] != 'n/a', 'Extraction failed'
"

# 4. Verify subdataset was dropped (state restored)
python3 << 'EOF'
from datalad.distribution.dataset import Dataset
ds = Dataset('study-ds002685/sourcedata/ds002685')
print(f"After: is_installed = {ds.is_installed()}")
assert not ds.is_installed(), "Subdataset should be dropped"
EOF

# 5. Run full workflow to update studies.tsv
snakemake -s code/workflow/Snakefile --cores 4 --rerun-triggers params

# 6. Verify studies.tsv has real values
python3 -c "
import csv
with open('studies.tsv') as f:
    rows = list(csv.DictReader(f, delimiter='\t'))
    for r in rows:
        if r['study_id'] == 'study-ds002685':
            print(f\"subjects_num: {r['subjects_num']}\")
            assert r['subjects_num'] != 'n/a', 'studies.tsv not updated'
"
```

### Manual Verification of State Preservation
```bash
# 1. Manually install a sourcedata subdataset
python3 << 'EOF'
import datalad.api as dl
from datalad.distribution.dataset import Dataset

ds = Dataset('study-ds000030')
ds.get('sourcedata/ds000030', get_data=False)
print("Manually installed sourcedata/ds000030")
EOF

# 2. Run extraction
snakemake -s code/workflow/Snakefile --cores 1 \
  --forcerun extract_study .snakemake/extracted/study-ds000030.json

# 3. Verify subdataset is STILL installed (not dropped)
python3 << 'EOF'
from datalad.distribution.dataset import Dataset
ds = Dataset('study-ds000030/sourcedata/ds000030')
assert ds.is_installed(), "Should still be installed (state preserved)"
print("✓ State preserved: subdataset still installed")
EOF
```

## Future Enhancements

### Reckless Drop Mode (After Verification)
**Status**: Disabled by default, can enable after confirming correct operation

Once the implementation is verified to work correctly, enable `reckless_drop=True` for performance:

```python
# In Snakemake or CLI
with TemporarySubdatasetInstall(study_path, reckless_drop=True):
    # Faster drop operation, skips safety checks
```

**Benefits**:
- Faster drop operations (skips availability checks)
- Appropriate for local-only datasets without remotes
- Reduces network checks

**Trade-off**: Initially slower but safer operation to catch edge cases during development.

### Parallel Installation (Optional)
DataLad's `get()` supports `jobs` parameter for parallel operations:

```python
parent_ds.get(sourcedata_paths, get_data=False, jobs=4)
```

Could be added if installation becomes a bottleneck.

### Provenance Recording (Optional)
Wrap installations in `datalad run` for full provenance:

```python
dl.run(
    cmd=['python', '-c', 'from bids_studies...'],
    message="Extract metadata with temporary subdataset install",
    inputs=['sourcedata/'],
    outputs=['.snakemake/extracted/{study}.json']
)
```

### CLI --ensure-subdatasets (Optional)
Add flag to `metadata generate` command for manual runs outside Snakemake.

## Open Questions

None — design is complete based on DataLad API research.
