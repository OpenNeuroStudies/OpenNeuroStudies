# Refactoring: Use DataLad Commands for Subdataset Management

## Constitution Amendment: 2026-03-12

**Version**: 1.20251218.0 → 1.20251218.1

### Amendment Summary

Constitution Principle IV (Git/DataLad-First Workflow) has been updated to **REQUIRE** DataLad commands for subdataset management in Python code and Snakemake workflows.

**New Requirements**:
- ✅ MUST use `datalad install` (not `git submodule update --init`)
- ✅ MUST use `datalad uninstall` (not `git submodule deinit`)
- ✅ MUST use `datalad get`/`drop` for data access
- ❌ MUST NOT use direct `git submodule` commands

**Rationale**: DataLad provides more robust subdataset management, handles edge cases better, and ensures consistency with the project's DataLad-based architecture.

---

## Why DataLad Instead of Git Submodule?

### Problems with Current Implementation

The current `subdataset_manager.py` uses `git submodule` commands directly:

```python
# Current (PROBLEMATIC):
subprocess.run(["git", "submodule", "update", "--init", path])
subprocess.run(["git", "submodule", "deinit", "-f", path])
```

**Known Issues**:
1. **Bug**: `git submodule deinit` leaves `.git` symlink, causing broken state
   - Files deleted but `.git` remains
   - Git shows "modified content" 
   - Requires manual cleanup (see `BUGFIX-subdataset-deinit.md`)

2. **No Error Recovery**: Git commands don't handle partial failures well
   - Network interruptions leave incomplete state
   - No automatic retry logic
   - Manual intervention required

3. **Inconsistent with DataLad Architecture**: 
   - Project uses DataLad elsewhere (datalad run, datalad create)
   - Mixing git and DataLad commands increases complexity
   - Violates Constitution Principle VII (No Duplicate Implementations)

### Benefits of DataLad Commands

DataLad's `install`/`uninstall` provide:

1. **Robust State Management**:
   - Clean install/uninstall (no leftover `.git` files)
   - Atomic operations (either fully installed or not)
   - Better error messages

2. **Flexible Data Access**:
   - `--reckless ephemeral`: Install git tree without annexed data
   - `--reckless auto`: Automatic mode selection
   - Fine-grained control via `get`/`drop`

3. **Consistent Architecture**:
   - Single abstraction layer (DataLad) instead of mixing git/DataLad
   - Better integration with DataLad provenance tracking
   - Aligns with project's DataLad-first principle

---

## Files Requiring Changes

### 1. `code/src/openneuro_studies/lib/subdataset_manager.py`

**Current Implementation**:
```python
def _initialize_single_subdataset(subdataset_path: Path, parent_path: Path):
    result = subprocess.run(
        ["git", "-C", str(parent_path), "submodule", "update", "--init", str(subdataset_path)],
        ...
    )

def _deinitialize_single_subdataset(subdataset_path: Path, parent_path: Path):
    result = subprocess.run(
        ["git", "-C", str(immediate_parent), "submodule", "deinit", "-f", str(subdataset_relative)],
        ...
    )
    # Manually clean up .git (workaround for git submodule bug)
    git_path = subdataset_path / ".git"
    if git_path.exists():
        git_path.unlink()  # or shutil.rmtree()
```

**Proposed Refactoring**:
```python
import datalad.api as dl

def _initialize_single_subdataset(subdataset_path: Path, parent_path: Path):
    """Initialize subdataset using DataLad install."""
    try:
        # Install without fetching annexed data (metadata-only)
        # Note: Don't use reckless="ephemeral" - only for local clones
        # For remote repos, just install normally (git tree only, no annexed content)
        dl.install(
            path=str(subdataset_path),
            dataset=str(parent_path),
            get_data=False,  # Don't fetch annexed content
            result_renderer="disabled",  # Suppress DataLad output
            on_failure="ignore",  # Return result instead of raising
        )
        logger.info(f"Installed subdataset: {subdataset_path}")
        return (subdataset_path, True)
    except Exception as e:
        logger.warning(f"Failed to install {subdataset_path}: {e}")
        return (subdataset_path, False)

def _deinitialize_single_subdataset(subdataset_path: Path, parent_path: Path):
    """Deinitialize subdataset using DataLad uninstall."""
    try:
        # Uninstall subdataset (removes working tree AND .git)
        dl.uninstall(
            path=str(subdataset_path),
            dataset=str(parent_path),
            check=False,  # Equivalent to --nocheck in CLI
            result_renderer="disabled",
            on_failure="ignore",
        )
        logger.info(f"Uninstalled subdataset: {subdataset_path}")
        return (subdataset_path, True)
    except Exception as e:
        logger.warning(f"Failed to uninstall {subdataset_path}: {e}")
        return (subdataset_path, False)
```

**Benefits**:
- ✅ No manual `.git` cleanup needed (DataLad handles it)
- ✅ Cleaner error handling
- ✅ Consistent with DataLad architecture
- ✅ Better logging via DataLad's result system

### 2. `code/workflow/Snakefile`

**Current**: Relies on `subdataset_manager.py` functions (no direct changes needed if manager is refactored)

**Future Enhancement**: Could use DataLad directly in Snakemake rules:
```python
rule extract_study:
    run:
        import datalad.api as dl

        # Install subdatasets (remote repos, no annexed data)
        for subdataset in to_init:
            dl.install(path=str(subdataset), get_data=False)

        # Extract metadata
        result = collect_study_metadata(study_path, stage="imaging")

        # Uninstall subdatasets
        for subdataset in to_deinit:
            dl.uninstall(path=str(subdataset), check=False)
```

### 3. Dependencies

**Current** (`code/pyproject.toml`):
```toml
dependencies = [
    "click>=8.0",
    "pydantic>=2.0",
    # ... other deps
]
```

**Add DataLad** (if not already present):
```toml
dependencies = [
    "click>=8.0",
    "datalad>=1.0",  # For subdataset management
    "pydantic>=2.0",
    # ... other deps
]
```

**Check**: DataLad may already be in dependencies for `datalad run` usage.

---

## Implementation Plan

### Phase 1: Update Dependencies ✅
- [ ] Verify DataLad is in `code/pyproject.toml` dependencies
- [ ] If missing, add `datalad>=1.0` requirement
- [ ] Update dev environment: `uv pip install -e .`

### Phase 2: Refactor `subdataset_manager.py`
- [ ] Replace `_initialize_single_subdataset()` with `datalad.api.install()`
- [ ] Replace `_deinitialize_single_subdataset()` with `datalad.api.uninstall()`
- [ ] Remove manual `.git` cleanup code (no longer needed)
- [ ] Update imports: add `import datalad.api as dl`
- [ ] Remove subprocess imports for git submodule (cleanup)

### Phase 3: Testing
- [ ] Unit test: Test `initialize_subdatasets()` with DataLad
- [ ] Unit test: Test `restore_initialization_state()` with DataLad
- [ ] Integration test: Run Snakemake extraction on single study
- [ ] Verify: No `.git` files left after uninstall
- [ ] Verify: `git status` clean after extraction

### Phase 4: Validate on Real Workflow
- [ ] Run extraction on subset of studies (e.g., 5 studies)
- [ ] Check for any DataLad-specific errors
- [ ] Verify performance is similar to git submodule approach
- [ ] Monitor subdataset state during/after extraction

### Phase 5: Documentation
- [ ] Update `subdataset_manager.py` docstrings
- [ ] Add DataLad usage examples to CLAUDE.md (✅ DONE)
- [ ] Update constitution (✅ DONE)
- [ ] Document reckless options and when to use them

---

## DataLad Install Options

### Correct Options for Remote Repository Cloning

**Important**: `reckless` options (ephemeral, auto, etc.) are **only for local repository clones**. Since we're installing from remote GitHub URLs, we use different options.

```python
# Correct approach for remote repos: Use get_data=False
dl.install(
    path=subdataset_path,
    dataset=parent_path,
    get_data=False,  # Don't fetch annexed content (git tree only)
)
# - Clones git repository from remote
# - Does NOT fetch annexed data
# - Suitable for metadata extraction
# - SparseDataset can still read git-annex URLs

# For uninstall: Use check=False (equivalent to --nocheck)
dl.uninstall(
    path=subdataset_path,
    dataset=parent_path,
    check=False,  # Skip safety checks (like --nocheck in CLI)
)
# - Removes subdataset working tree and .git cleanly
# - No leftover files (unlike git submodule deinit)
```

### When to Use Each

| Use Case | Option | Reason |
|----------|--------|--------|
| Metadata extraction (remote) | `get_data=False` | Clone git tree only, no annexed content |
| Metadata extraction (local) | `reckless="ephemeral"` | Local clone, no data needed |
| Read dataset_description.json | `get_data=False` | File in git (not annexed) |
| Count subjects/sessions | `get_data=False` | Tree structure only |
| **Read imaging headers** | `get_data=False` | SparseDataset uses git-annex URLs |
| Full data access | Default (no flags) | Download annexed content |

**For our use case**: `get_data=False` is correct for remote repos - we install git tree without annexed content, and `SparseDataset` reads git-annex metadata directly.

---

## Testing Checklist

### Before Refactoring
- [x] Document current behavior
- [x] Identify bug in git submodule approach
- [x] Create test for broken subdataset state

### During Refactoring
- [ ] Write failing test for DataLad approach
- [ ] Implement DataLad-based functions
- [ ] Verify tests pass
- [ ] Check for regressions

### After Refactoring
- [ ] Test on single study (ds000001)
- [ ] Test on multi-session study (ds004488)
- [ ] Test on study with multiple sources (ds006191)
- [ ] Verify git status clean
- [ ] Verify no .git leftover files
- [ ] Performance comparison (should be similar)

---

## Migration Path

### Option 1: Direct Replacement (Recommended)
1. Update `subdataset_manager.py` to use DataLad
2. Test thoroughly
3. Deploy to production

**Pros**:
- Clean, single implementation
- No duplicate code
- Aligns with Constitution Principle VII (No Duplicate Implementations)

**Cons**:
- Requires thorough testing
- Potential for unexpected DataLad behavior

### Option 2: Gradual Migration (NOT RECOMMENDED)
1. Add DataLad functions alongside git submodule functions
2. Add flag to choose between implementations
3. Test both in parallel
4. Remove git submodule code after validation

**Cons**:
- Violates Constitution Principle VII (No Duplicate Implementations)
- Doubles maintenance burden
- Risk of divergence between implementations
- More complex codebase

**Recommendation**: Option 1 (Direct Replacement) following Constitution principles.

---

## Expected Outcomes

### After Refactoring

✅ **Bug Fixed**: No more broken subdataset states with leftover `.git` files

✅ **Cleaner Code**: Single abstraction layer (DataLad) instead of mixing git/DataLad

✅ **Better Error Handling**: DataLad provides structured error information

✅ **Constitution Compliant**: Aligns with Principle IV (Git/DataLad-First) and Principle VII (No Duplicate Implementations)

✅ **Maintainable**: DataLad team handles edge cases, we don't need workarounds

### Performance Impact

Expected: **Minimal to no performance difference**
- Both approaches clone git tree (same network operation)
- DataLad adds small Python overhead (~100ms per subdataset)
- For 40 studies: ~4 seconds total overhead (negligible vs 4 hour extraction)

### Risk Assessment

**Low Risk**:
- DataLad is mature, widely used in neuroscience
- API is stable (1.0+ release)
- Thoroughly tested in DataLad ecosystem
- Our use case (install/uninstall) is core functionality

**Mitigation**:
- Test on subset before full deployment
- Can roll back to git submodule if critical issues found
- Keep bug fix commit separate for easy revert

---

## References

- Constitution Principle IV: Git/DataLad-First Workflow
- Constitution Principle VII: No Duplicate Implementations (DRY)
- DataLad install docs: http://docs.datalad.org/en/stable/generated/man/datalad-install.html
- DataLad uninstall docs: http://docs.datalad.org/en/stable/generated/man/datalad-uninstall.html
- Bug report: `code/tests-adhoc/BUGFIX-subdataset-deinit.md`

---

## Status

- [x] Constitution amended (v1.20251218.1)
- [x] CLAUDE.md updated with DataLad examples
- [ ] Dependencies verified/updated
- [ ] Code refactored
- [ ] Tests updated
- [ ] Production deployment

**Next Steps**: Implement Phase 1 (verify dependencies) and Phase 2 (refactor subdataset_manager.py).
