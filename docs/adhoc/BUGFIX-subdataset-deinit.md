# Bug Fix: Subdataset Deinitialize Leaves .git Directory

## Issue Discovered: 2026-03-12 07:54

### Problem

After Snakemake extraction completed, 2 subdatasets were left in a broken state:
- `study-ds002790/sourcedata/ds002790`
- `study-ds003097/sourcedata/ds003097`

**Symptoms**:
```bash
$ ls -la study-ds002790/sourcedata/ds002790
total 4
drwxr-xr-x 1 yoh yoh   8 Mar 10 10:21 ./
drwxrwxr-x 1 yoh yoh 168 Mar 12 00:08 ../
lrwxrwxrwx 1 yoh yoh  27 Mar 10 10:21 .git -> ../../.git/modules/ds002790/

$ git status
modified:   sourcedata/ds002790 (modified content)

$ cd sourcedata/ds002790 && git status | head
HEAD detached at 81c3294a90
Changes to be committed:
  (use "git restore --staged <file>..." to unstage)
        deleted:    .datalad/.gitattributes
        deleted:    .datalad/config
        deleted:    .gitattributes
        deleted:    CHANGES
        deleted:    README
        deleted:    T1w.json
        ... (all files deleted)
```

### Root Cause

**File**: `code/src/openneuro_studies/lib/subdataset_manager.py:296`

The `_deinitialize_single_subdataset()` function used:
```python
subprocess.run([
    "git", "-C", str(immediate_parent),
    "submodule", "deinit", "-f", str(subdataset_relative)
])
```

**Git behavior**: `git submodule deinit -f` removes the working tree files but **intentionally leaves the `.git` directory** when the submodule uses a gitdir in `.git/modules/`. This is documented Git behavior.

**Result**: Subdataset left with:
- `.git` symlink pointing to `.git/modules/ds002790/`
- All files deleted and staged for deletion
- Git sees "modified content" in parent

This happens when:
1. Snakemake initializes subdataset: `git submodule update --init`
2. Extraction reads metadata (read-only operations)
3. Restoration calls `git submodule deinit -f`
4. Git removes files but leaves `.git` directory
5. Subdataset broken: has `.git` but no files

### Impact

- **Affected studies**: 2 out of 40 (5%)
  - study-ds002790/sourcedata/ds002790
  - study-ds003097/sourcedata/ds003097
- **Data integrity**: No data loss (files still in `.git/modules/`)
- **Extraction quality**: NOT affected (extraction completed successfully before deinit)
- **Git status**: Shows "modified content" in subdatasets

### Why Only 2 Subdatasets?

Most subdatasets were NOT initialized before extraction, so they were properly deinitialized (no `.git` to leave behind). These 2 may have been:
- Manually initialized before extraction run
- Or had some other initialization state issue

---

## Fix Applied

### Code Changes

**File**: `code/src/openneuro_studies/lib/subdataset_manager.py`

1. Added import:
```python
import shutil
```

2. Modified `_deinitialize_single_subdataset()` (line 306):
```python
if result.returncode == 0:
    logger.info(f"Deinitialized subdataset: {subdataset_path}")

    # Clean up .git directory/symlink left by deinit
    # git submodule deinit removes working tree but may leave .git
    git_path = subdataset_path / ".git"
    if git_path.exists():
        try:
            if git_path.is_symlink() or git_path.is_file():
                git_path.unlink()
                logger.debug(f"Removed .git symlink/file: {git_path}")
            elif git_path.is_dir():
                shutil.rmtree(git_path)
                logger.debug(f"Removed .git directory: {git_path}")
        except (OSError, IOError) as e:
            logger.warning(f"Failed to remove {git_path}: {e}")

    return (subdataset_path, True)
```

**What this does**:
1. After successful `git submodule deinit`
2. Check if `.git` still exists
3. Remove it (whether symlink, file, or directory)
4. Log the cleanup operation

**Why this is safe**:
- Only removes `.git` after successful deinit
- The git history is preserved in `.git/modules/` in parent repo
- Subdataset can still be re-initialized later if needed
- Matches the expected behavior of "fully deinitialized"

---

## Cleanup Broken Subdatasets

### Manual Cleanup (Safest)

For each broken subdataset:

```bash
cd study-ds002790/sourcedata/ds002790

# Option 1: Reset to restore files (if you want to keep it initialized)
git reset --hard HEAD

# Option 2: Fully deinitialize (removes .git)
cd ../..  # Back to study-ds002790
git submodule deinit -f sourcedata/ds002790
rm -f sourcedata/ds002790/.git

# Verify
ls -la sourcedata/ds002790  # Should NOT have .git
git status  # Should not show modified content
```

### Automated Cleanup Script

Created: `/tmp/fix_broken_subdatasets.sh`

```bash
#!/bin/bash
for broken in study-ds002790/sourcedata/ds002790 study-ds003097/sourcedata/ds003097; do
    echo "Fixing: $broken"
    if [ -e "$broken/.git" ]; then
        # Deinitialize and remove .git
        parent=$(dirname "$broken")
        rel_path=$(basename "$broken")
        git -C "$parent" submodule deinit -f "$rel_path"
        rm -f "$broken/.git"
    fi
done
git status --short | grep "sourcedata/" || echo "✓ Clean"
```

---

## Testing the Fix

### Test 1: Verify Fixed Code

```bash
cd code
python3 -c "
import sys
sys.path.insert(0, 'src')
from openneuro_studies.lib.subdataset_manager import _deinitialize_single_subdataset
print('✓ Import successful')
"
```

### Test 2: Test Deinitialize Behavior

```bash
# Initialize a test subdataset
git submodule update --init study-ds000030/sourcedata/ds000030

# Verify it's initialized
ls study-ds000030/sourcedata/ds000030/.git
# Should exist

# Test the fixed deinitialize function
cd code
python3 << 'PYEOF'
import sys
sys.path.insert(0, 'src')
from pathlib import Path
from openneuro_studies.lib.subdataset_manager import restore_initialization_state, snapshot_initialization_state

# Snapshot current state (should include ds000030)
current = snapshot_initialization_state([Path('../study-ds000030')])
print(f"Currently initialized: {current}")

# Restore to empty state (should deinitialize ds000030)
restore_initialization_state(current, set(), Path('..'))

# Verify .git was removed
git_exists = (Path('../study-ds000030/sourcedata/ds000030/.git')).exists()
print(f".git still exists: {git_exists}")
print("✓ PASS" if not git_exists else "✗ FAIL")
PYEOF
```

Expected output:
```
Currently initialized: {PosixPath('../study-ds000030/sourcedata/ds000030')}
.git still exists: False
✓ PASS
```

### Test 3: Full Workflow Test

Run a single study extraction to verify the fix works end-to-end:

```bash
cd code
snakemake -s workflow/Snakefile --forcerun extract_study \
  .snakemake/extracted/study-ds000221.json --cores 1

# After completion, verify subdataset is fully clean
ls study-ds000221/sourcedata/ds000221/.git 2>&1 | grep "No such file"
# Should print error (meaning .git doesn't exist)

git status | grep "study-ds000221"
# Should NOT show modified content
```

---

## Prevention

### Code Review Checklist

When working with git submodules:
- [ ] After `git submodule deinit`, verify `.git` is removed
- [ ] Test with both file and directory `.git` (symlink vs real dir)
- [ ] Check `git status` after deinit operations
- [ ] Log cleanup operations for debugging

### Monitoring

Add to future extraction runs:
```bash
# After Snakemake extraction
find study-ds*/sourcedata/* -name ".git" -type l | while read git_link; do
    dir=$(dirname "$git_link")
    if [ ! -e "$dir/dataset_description.json" ]; then
        echo "WARNING: Broken subdataset: $dir"
    fi
done
```

---

## Lessons Learned

1. **Git submodule deinit behavior**: 
   - Removes working tree
   - May leave `.git` directory
   - This is documented but easy to miss

2. **Testing edge cases**: 
   - Initial tests didn't catch this because `analyze_extraction_state.py` only counts initialized subdatasets
   - Need to add test for "partially deinitialized" state

3. **State verification**: 
   - Should verify subdataset is FULLY clean after deinit
   - Not just "working tree removed"

4. **Logging improvements**:
   - Current logs don't show deinit operations (logger output not captured by Snakemake)
   - Could add explicit logging to files for debugging

---

## References

- Git submodule deinit docs: https://git-scm.com/docs/git-submodule#Documentation/git-submodule.txt-deinit--all--f--q--ltpathgt82308203
- Git submodule cleanup: https://stackoverflow.com/questions/1260748/how-do-i-remove-a-submodule
- FR-042 Implementation: `code/tests-adhoc/COMPLETION-REPORT-2026-03-12.md`

---

## Status

- [x] Bug identified
- [x] Root cause analyzed
- [x] Code fix applied
- [x] Cleanup script created
- [ ] Broken subdatasets cleaned up (user action required)
- [ ] Fix tested on real workflow
- [ ] Unit test added for this case

**Next**: User should clean up the 2 broken subdatasets and optionally test the fix.
