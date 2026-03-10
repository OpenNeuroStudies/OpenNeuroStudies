# Extraction Failure Diagnosis and Fix Plan

**Date**: 2026-03-10
**Issue**: After implementing subdataset management, only one study changed; all studies still have "n/a" metadata

## Root Cause Analysis

### Problem Discovery

1. **Extracted JSON files have extraction_version="1.1.0"** ✓
   - This confirms Snakemake detected the param change
   - Re-extraction DID run

2. **But all metadata fields are "n/a"** ✗
   - `subjects_num`: "n/a"
   - `bold_num`: 0
   - `datatypes`: "n/a"
   - This indicates extraction is failing silently

3. **Subdatasets appear "initialized" but are EMPTY** ✗
   ```bash
   $ ls -la study-ds000001/sourcedata/ds000001/
   total 4
   drwxrwxr-x 1 yoh yoh   0 Mar  9 23:08 .
   drwx------ 1 yoh yoh 168 Mar  9 23:08 ..
   # NO FILES!

   $ cd study-ds000001/sourcedata/ds000001 && git status
   On branch master
   nothing to commit, working tree clean
   # But which repository?

   $ git rev-parse --show-toplevel
   /home/yoh/proj/openneuro/OpenNeuroStudies/study-ds000001
   # It's the PARENT repository, not the subdataset!
   ```

### Critical Bug

**Bug in `lib/subdataset_manager.py::is_subdataset_initialized()`**:

```python
def is_subdataset_initialized(subdataset_path: Path) -> bool:
    # ...
    # Verify git status works (git tree accessible)
    try:
        result = subprocess.run(
            ["git", "-C", str(subdataset_path), "status"],
            capture_output=True,
            timeout=5,
            check=False,
        )
        return result.returncode == 0  # ← FALSE POSITIVE!
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
```

**Why it fails**:
- `git -C study-ds000001/sourcedata/ds000001 status` succeeds even when the directory is empty
- Git searches upward and finds the parent repository (`study-ds000001`)
- Function returns `True` (initialized) when it should return `False`
- Snakemake thinks subdataset is available, skips initialization
- Extraction runs but finds no files → all "n/a"

### Correct Detection Method

A subdataset is initialized if:
1. `.git` exists in the subdataset directory (file or directory), AND
2. It's either:
   - A gitlink file containing `gitdir: ...` pointing to parent's `.git/modules/`
   - A regular `.git` directory (older submodule style)
3. AND the working tree has files (not just empty)

## Fix Strategy

### Fix 1: Correct `is_subdataset_initialized()` Function

```python
def is_subdataset_initialized(subdataset_path: Path) -> bool:
    """Check if subdataset has git tree available.

    A subdataset is initialized if:
    - .git exists (file or directory)
    - It points to a valid git repository
    - The working tree is not empty
    """
    if not subdataset_path.exists():
        return False

    git_path = subdataset_path / ".git"
    if not git_path.exists():
        return False

    # Check if this is actually a submodule with its own repository
    # (not just a directory inside a parent repository)
    try:
        # Get the repository root for this path
        result = subprocess.run(
            ["git", "-C", str(subdataset_path), "rev-parse", "--show-toplevel"],
            capture_output=True,
            timeout=5,
            check=True,
            text=True,
        )

        # The git root should BE this subdataset path, not a parent
        git_root = Path(result.stdout.strip())
        if git_root != subdataset_path:
            return False  # This is inside a parent repository

        # Verify the working tree has files (not empty except for .git)
        has_files = any(
            item.name != ".git"
            for item in subdataset_path.iterdir()
            if not item.name.startswith(".")
        )

        return has_files

    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return False
```

### Fix 2: Enhanced Diagnostic Logging

Add logging to see what's happening:

```python
def initialize_subdatasets(
    subdataset_paths: list[Path],
    parent_path: Path = Path("."),
    jobs: int = 1,
) -> dict[Path, bool]:
    """Initialize subdatasets using git submodule update."""
    if not subdataset_paths:
        logger.info("No subdatasets to initialize")
        return {}

    logger.info(f"Initializing {len(subdataset_paths)} subdatasets:")
    for path in subdataset_paths:
        logger.info(f"  - {path}")

    # ... rest of function
```

### Fix 3: Verify Initialization Worked

After `git submodule update --init`, verify files were actually checked out:

```python
def _initialize_single_subdataset(subdataset_path: Path, parent_path: Path) -> tuple[Path, bool]:
    """Initialize a single subdataset."""
    try:
        result = subprocess.run(
            ["git", "-C", str(parent_path), "submodule", "update", "--init", str(subdataset_path)],
            capture_output=True,
            timeout=300,
            check=False,
            text=True,
        )

        if result.returncode == 0:
            # VERIFY: Check that files were actually checked out
            has_files = any(
                item.name not in {".git", ".gitignore"}
                for item in subdataset_path.iterdir()
                if not item.name.startswith(".")
            )

            if has_files:
                logger.info(f"✓ Initialized and verified: {subdataset_path}")
                return (subdataset_path, True)
            else:
                logger.warning(f"⚠ Initialized but no files: {subdataset_path}")
                return (subdataset_path, False)
        else:
            logger.warning(f"✗ Failed: {subdataset_path}: {result.stderr}")
            return (subdataset_path, False)
    except Exception as e:
        logger.warning(f"✗ Exception: {subdataset_path}: {e}")
        return (subdataset_path, False)
```

## Implementation Plan

### Phase 1: Enhanced Diagnostics (IMMEDIATE)

1. **Create `full-clean` Makefile target**:
   ```makefile
   full-clean: unlock
       @echo "Removing all Snakemake intermediate files..."
       rm -rf .snakemake/extracted/*.json
       rm -rf .snakemake/prov/
       @echo "✓ Clean complete"
   ```

2. **Create `analyze-state` Makefile target**:
   ```makefile
   analyze-state:
       @echo "Analyzing extraction state..."
       @python3 code/tests-adhoc/analyze_extraction_state.py
   ```

3. **Create `code/tests-adhoc/analyze_extraction_state.py`**:
   - Check how many studies have "n/a" vs real values
   - Check how many subdatasets are actually initialized (with files)
   - Report statistics on extraction success rate

### Phase 2: Fix Subdataset Manager (HIGH PRIORITY)

1. **Fix `is_subdataset_initialized()`** - Use `rev-parse --show-toplevel` check
2. **Add file existence verification** - Ensure working tree has files
3. **Add diagnostic logging** - Show what's being initialized
4. **Add post-init verification** - Confirm files were checked out

### Phase 3: Testing (HIGH PRIORITY)

1. **Test with duct logging**:
   ```bash
   make full-clean
   duct make metadata analyze-state CORES=6
   ```

2. **Review duct logs** to see:
   - Which subdatasets were detected as needing initialization
   - Whether `git submodule update --init` succeeded
   - Whether files were actually checked out
   - Whether extraction found data

3. **Compare results**:
   - Before: ~all studies with "n/a"
   - After fix: studies should have real metadata

## Expected Outcomes

### Before Fix
- `is_subdataset_initialized()` returns `True` for empty directories
- No initialization happens
- Extraction finds no files → "n/a"
- Only studies with pre-existing initialized subdatasets work (e.g., ds000001, ds005256, ds006131-ds006192)

### After Fix
- `is_subdataset_initialized()` correctly detects empty directories
- Initialization runs for ~1000 studies
- `git submodule update --init` checks out files
- Extraction finds files → real metadata
- studies.tsv populated with subjects_num, bold_num, etc.

## Verification Checklist

- [ ] Fix `is_subdataset_initialized()` to check `rev-parse --show-toplevel`
- [ ] Add file existence check (working tree not empty)
- [ ] Add diagnostic logging to initialization
- [ ] Add post-init verification
- [ ] Update unit tests to catch this bug
- [ ] Add integration test for initialization detection
- [ ] Run `make full-clean`
- [ ] Run `duct make metadata analyze-state CORES=6`
- [ ] Review duct logs for initialization messages
- [ ] Check studies.tsv for real values (not all "n/a")
- [ ] Verify ~1000 studies extracted successfully

## Timeline

- **Phase 1 (Diagnostics)**: 1 hour - Create Makefile targets and analysis script
- **Phase 2 (Fix)**: 2 hours - Fix subdataset_manager.py, update tests
- **Phase 3 (Testing)**: 4-6 hours - Full re-extraction with logging review

**Total**: ~8 hours (1 day)

## Risk Assessment

**LOW RISK** - The bug is isolated to subdataset detection:
- Fix is straightforward (better git command)
- No changes to extraction logic needed
- Unit tests will prevent regression
- Can verify fix incrementally with single study

**HIGH IMPACT** - Fixing this unblocks all 1000+ studies:
- Will eliminate "n/a" values across repository
- Enables full metadata extraction
- Closes critical gap from specification analysis
