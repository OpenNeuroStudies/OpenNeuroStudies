# Debug Guide: analyze-quality Test Failures

**Date**: 2026-03-26
**Status**: In Progress
**Issue**: analyze-quality CLI tests failing with exit code 2 (Click usage error)

## Summary

Refactored ad-hoc error analysis scripts into proper CLI commands under `openneuro-studies errors`. Created 16 comprehensive unit tests. All analyze-legacy tests pass (9/9), but analyze-quality tests fail (7/8) with exit code 2.

## Current Status

### Working ✅
- **analyze-legacy command**: Fully functional
- **analyze-legacy tests**: 9/9 passing
- **Direct CLI invocation**: `openneuro-studies errors analyze-quality` works correctly

### Failing ❌
- **analyze-quality tests**: 7/8 failing with exit code 2
- Exit code 2 = Click usage error (command not found or wrong arguments)

## Test Commands

### Run Tests
```bash
cd /home/yoh/proj/openneuro/OpenNeuroStudies/code

# All error CLI tests
.venv/bin/pytest tests/unit/test_errors_cli.py -v

# Only failing tests
.venv/bin/pytest tests/unit/test_errors_cli.py::TestAnalyzeQuality -v

# Single test with debugger
.venv/bin/pytest tests/unit/test_errors_cli.py::TestAnalyzeQuality::test_single_complete_study -xvs --pdb
```

### Manual Reproduction

#### Method 1: CliRunner (what tests use)
```python
cd /home/yoh/proj/openneuro/OpenNeuroStudies/code
.venv/bin/python3 << 'EOF'
import json, os
from pathlib import Path
from click.testing import CliRunner
from openneuro_studies.cli.errors import errors

# Create test data
tmp = Path('/tmp/test_manual')
tmp.mkdir(exist_ok=True)
(tmp / '.snakemake/extracted').mkdir(parents=True, exist_ok=True)

study = {
    'subjects_num': 16, 'bold_num': 10, 't1w_num': 16,
    'bold_voxels_total': 1000000, 'bold_voxels_mean': 100000,
    'bold_duration_total': 500.0, 'bold_duration_mean': 50.0
}
(tmp / '.snakemake/extracted/study-ds000001.json').write_text(json.dumps(study))

# Run via CliRunner
runner = CliRunner()
orig = os.getcwd()
os.chdir(tmp)
result = runner.invoke(errors, ['analyze-quality', '--format', 'table'])
os.chdir(orig)

print(f"Exit code: {result.exit_code}")
print(f"Output:\n{result.output}")

import shutil
shutil.rmtree(tmp)
EOF
```

#### Method 2: Direct CLI (should work)
```bash
# Create test data
mkdir -p /tmp/test_cli/.snakemake/extracted
cat > /tmp/test_cli/.snakemake/extracted/study-ds000001.json << 'JSON'
{
  "subjects_num": 16,
  "bold_num": 10,
  "t1w_num": 16,
  "bold_voxels_total": 1000000,
  "bold_voxels_mean": 100000,
  "bold_duration_total": 500.0,
  "bold_duration_mean": 50.0
}
JSON

# Run command
cd /tmp/test_cli
/home/yoh/proj/openneuro/OpenNeuroStudies/code/.venv/bin/openneuro-studies errors analyze-quality --format table

# Cleanup
rm -rf /tmp/test_cli
```

## Key Files

- **Command implementation**: `code/src/openneuro_studies/cli/errors.py`
  - Lines 315-477: `analyze_quality()` function
  - Lines 480-637: `analyze_legacy()` function (working)

- **Tests**: `code/tests/unit/test_errors_cli.py`
  - Lines 30-211: TestAnalyzeQuality class (7/8 failing)
  - Lines 213-372: TestAnalyzeLegacy class (9/9 passing)

- **Helper**: `run_in_dir()` function (lines 20-31)
  - Uses `os.chdir()` to change directory before invoking command
  - Both test classes use the same helper

## Debugging Observations

### From Extensive Debug Session

1. **Function executes correctly**:
   - analyze_quality is called
   - Finds JSON files
   - Processes results
   - Creates by_status dictionary

2. **Execution stops prematurely**:
   - Debug showed execution reaching result grouping
   - Never completes table output
   - Unexpected "No error logs found" message appears (from `list` command?)

3. **CliRunner vs pytest**:
   - Manual CliRunner: Exit code 0 (but wrong output)
   - Pytest CliRunner: Exit code 2 (usage error)

4. **Similarity to working tests**:
   - analyze-legacy uses identical test pattern
   - Same `run_in_dir()` helper
   - Same Click.testing.CliRunner approach
   - analyze-legacy tests all pass

## Hypotheses

### 1. CliRunner + os.chdir() Issue
- CliRunner might not respect `os.chdir()`
- Working directory might not be set correctly in command context
- **Test**: Run without os.chdir(), use absolute paths instead

### 2. Click Command Registration
- Command might not be properly registered to errors group
- Name resolution issue with hyphens in 'analyze-quality'
- **Test**: Check `errors.commands` dictionary

### 3. Pytest Environment
- Pytest doing something special with working directory
- Import/reload issue with module caching
- **Test**: Run CliRunner manually outside pytest

### 4. Output Buffering/Interference
- Click output handling in test vs production
- Debug statements interfering (now removed)
- **Test**: Compare with analyze-legacy command structure

## Next Steps for Debugging

1. **Verify command registration**:
   ```python
   from openneuro_studies.cli.errors import errors
   print(list(errors.commands.keys()))
   print(errors.commands.get('analyze-quality'))
   ```

2. **Test CliRunner manually** (Method 1 above):
   - If passes: Issue is pytest-specific
   - If fails: Issue is CliRunner + command

3. **Compare decorators**:
   - analyze-quality: `@errors.command(name="analyze-quality")`
   - analyze-legacy: `@errors.command(name="analyze-legacy")`
   - Check for any differences

4. **Test without run_in_dir**:
   - Create files in current directory
   - Invoke without os.chdir()
   - See if that isolates the problem

5. **Check Click version**:
   - Ensure compatible Click version
   - Check for known issues with hyphens in command names

## References

- Refactoring plan: `doc/designs/20260323-refactor-error-analysis-to-cli.md`
- Implementation commit: 3d59749
- Related issue: analyze-legacy tests passing, analyze-quality failing with same pattern
