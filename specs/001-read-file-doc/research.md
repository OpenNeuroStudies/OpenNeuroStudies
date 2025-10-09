# Research: DataLad Python API, Git Submodules, and GitHub API Patterns

**Research Date**: 2025-10-09
**Project**: OpenNeuroStudies Infrastructure Refactoring
**Purpose**: Document best practices for DataLad Python API, git submodule operations, and GitHub API usage for discovering and organizing 1000+ OpenNeuro datasets

---

## 1. DataLad Python API (`datalad.api`)

### 1.1 Creating Datasets Without Annex

#### Decision
Use `datalad.api.create()` with `annex=False` parameter to create plain Git repositories for study datasets, as they only contain metadata and submodule links (no large files requiring git-annex).

#### Rationale
- Study datasets contain only metadata files (JSON, TSV) and git submodule references, not large data files
- Plain Git repositories are simpler to manage and publish to GitHub
- No git-annex overhead for datasets that don't need large file management
- According to DataLad docs: "Plain Git repositories can be created via `annex=False`"
- Study datasets are organizational structures, not data storage; derivatives and raw data remain in their own annexes

#### Code Example

```python
import datalad.api as dl

# Create a study dataset without git-annex
study_path = 'study-ds000001'
result = dl.create(path=study_path, annex=False)

# Create within a superdataset (automatically registers as submodule)
result = dl.create(
    path='study-ds000002',
    dataset='.',  # Current directory as superdataset
    annex=False,
    description='Study dataset for ds000002'
)

# Using Dataset object for more control
from datalad.api import Dataset

superdataset = Dataset('.')
result = superdataset.create(path='study-ds000003', annex=False)
```

#### Function Signature
```python
datalad.api.create(
    path=None,
    initopts=None,
    *,
    force=False,
    description=None,
    dataset=None,
    annex=True,  # Set to False for plain Git
    fake_dates=False,
    cfg_proc=None
)
```

#### Key Parameters
- **`path`**: Where the dataset should be created; directories created as necessary
- **`annex`**: If `False`, creates plain Git repository without git-annex
- **`dataset`**: Path to parent dataset for automatic submodule registration
- **`force`**: Enforce creation in non-empty directory
- **`description`**: Brief label for the dataset's nature and location

#### Alternatives Considered
1. **Using git-annex for all datasets**: Rejected due to unnecessary complexity for metadata-only repos
2. **Command-line `datalad create`**: Rejected due to startup overhead when processing 1000+ datasets
3. **Plain git init**: Rejected as it loses DataLad metadata and integration benefits

---

### 1.2 Error Handling Patterns

#### Decision
Use structured exception handling with the `on_failure` parameter set to `'continue'` for batch operations, allowing collection of all errors before raising `IncompleteResultsError`.

#### Rationale
- Processing 1000+ datasets requires resilience; one failure shouldn't stop all processing
- `IncompleteResultsError.failed` attribute provides detailed failure information for logging
- `on_failure='continue'` allows capturing all failures in a single batch run
- Structured error handling enables systematic error reporting in `logs/errors.tsv`

#### Code Example

```python
import datalad.api as dl
from datalad.support.exceptions import IncompleteResultsError, CommandError

def create_study_dataset(study_id: str, base_path: str) -> dict:
    """
    Create a study dataset with proper error handling.

    Returns result dict with status information.
    """
    try:
        result = dl.create(
            path=f'{base_path}/study-{study_id}',
            dataset=base_path,
            annex=False,
            on_failure='continue'  # Collect errors, don't stop immediately
        )
        return {'status': 'ok', 'study_id': study_id, 'result': result}

    except IncompleteResultsError as e:
        # Access detailed failure information
        failed_results = e.failed
        return {
            'status': 'error',
            'study_id': study_id,
            'error_type': 'IncompleteResultsError',
            'failures': failed_results,
            'message': str(e)
        }

    except CommandError as e:
        # Handle direct command failures
        return {
            'status': 'error',
            'study_id': study_id,
            'error_type': 'CommandError',
            'message': str(e),
            'stdout': getattr(e, 'stdout', None),
            'stderr': getattr(e, 'stderr', None)
        }

    except Exception as e:
        # Catch-all for unexpected errors
        return {
            'status': 'error',
            'study_id': study_id,
            'error_type': type(e).__name__,
            'message': str(e)
        }

# Batch processing with error collection
def process_multiple_studies(study_ids: list, base_path: str) -> tuple[list, list]:
    """Process multiple studies, collecting successes and failures."""
    successes = []
    failures = []

    for study_id in study_ids:
        result = create_study_dataset(study_id, base_path)
        if result['status'] == 'ok':
            successes.append(result)
        else:
            failures.append(result)

    return successes, failures
```

#### Exception Types

**`IncompleteResultsError`**:
- Raised when `on_failure='continue'` or `on_failure='stop'` and operations fail
- Contains `failed` attribute with list of result dictionaries
- Result records have status 'impossible' or 'error'

**`CommandError`**:
- Raised by underlying git/git-annex commands on non-zero exit
- Contains `stdout_json` with captured JSON records (if available)
- Original exception preserved in `IncompleteResultsError.failed[n]['exception']`

#### on_failure Parameter Options
- `'ignore'`: Report failures but don't raise exception (silent continuation)
- `'continue'`: Raise `IncompleteResultsError` at end, but process all items (default for batch operations)
- `'stop'`: Stop on first failure and raise exception immediately

#### Alternatives Considered
1. **`on_failure='ignore'`**: Rejected as it silently swallows errors, making debugging difficult
2. **`on_failure='stop'`**: Rejected for batch operations as it prevents processing remaining datasets
3. **Try-except around each command**: Too verbose; DataLad's built-in error handling is more robust

---

### 1.3 Saving Changes and Commit Messages

#### Decision
Use `Dataset.save()` method or `dl.save()` with explicit `message` parameter for all commits, following BIDS provenance standards.

#### Rationale
- Provides structured commit messages for provenance tracking
- Integrates with DataLad's metadata system
- More efficient than command-line for batch operations (no startup overhead)
- Enables programmatic commit message generation from templates

#### Code Example

```python
import datalad.api as dl
from datalad.api import Dataset

# Using datalad.api directly
dl.save(
    path='dataset_description.json',
    message='Generate study dataset metadata for ds000001',
    dataset='study-ds000001'
)

# Using Dataset object (preferred for multiple operations)
ds = Dataset('study-ds000001')

# Save specific file
ds.save(
    path='dataset_description.json',
    message='Add BIDS study metadata'
)

# Save multiple files
ds.save(
    path=['dataset_description.json', '.gitmodules'],
    message='Add study metadata and sourcedata submodules'
)

# Save all changes in dataset
ds.save(message='Configure study dataset structure')

# Save with multi-line commit message
commit_msg = """Add derivative submodules for fmriprep and mriqc

Links to OpenNeuroDerivatives repositories:
- fmriprep-21.0.1 (eb586851-1a79-4671-aded-31384b3d5d7f)
- mriqc-0.16.1 (3a3af661-2cf7-4eec-8e31-38d0c75652b5)

Generated automatically by OpenNeuroStudies infrastructure."""

ds.save(
    path='sourcedata/',
    message=commit_msg,
    recursive=True  # Recurse into subdatasets if needed
)
```

#### Structured Commit Message Template

```python
def generate_commit_message(
    action: str,
    study_id: str,
    details: dict = None
) -> str:
    """Generate standardized commit messages."""

    templates = {
        'create_study': 'Initialize study dataset for {study_id}',
        'add_sourcedata': 'Link sourcedata for {study_id}: {datasets}',
        'add_derivatives': 'Link derivative datasets: {tools}',
        'update_metadata': 'Update study metadata for {study_id}',
    }

    msg = templates[action].format(study_id=study_id, **(details or {}))

    # Add provenance footer
    msg += '\n\nGenerated by OpenNeuroStudies infrastructure'

    return msg

# Usage
ds = Dataset('study-ds000001')
ds.save(
    message=generate_commit_message(
        'add_derivatives',
        'ds000001',
        {'tools': 'fmriprep-21.0.1, mriqc-0.16.1'}
    )
)
```

#### Alternatives Considered
1. **Automatic commit messages**: Rejected as they lack context for provenance tracking
2. **Command-line `datalad save`**: Rejected due to startup overhead for batch operations
3. **Direct git commands**: Rejected as they bypass DataLad's metadata tracking

---

### 1.4 Import Convention

#### Decision
**Always** import DataLad API as: `import datalad.api as dl`

#### Rationale
- Official convention from DataLad Handbook and documentation
- Provides consistent, recognizable pattern across codebase
- Shorter than `datalad.api` for repeated use
- All user-oriented commands exposed via `datalad.api`
- Clear distinction from Dataset class: `from datalad.api import Dataset`

#### Code Example

```python
# Standard import convention
import datalad.api as dl
from datalad.api import Dataset

# Create dataset using module
result = dl.create(path='my_dataset', annex=False)

# Get dataset info
info = dl.status(dataset='my_dataset')

# Using Dataset class for persistent operations
ds = Dataset('my_dataset')
ds.save(message='Initial commit')
ds.create(path='subdataset', annex=False)

# All datalad.api commands available via dl.* pattern
dl.get(path='data.txt', dataset='my_dataset')
dl.clone(source='https://example.com/repo.git', path='cloned')
```

#### Benefits of Python API vs CLI
1. **No startup overhead**: Significant speedup for 1000+ operations
2. **Persistent Dataset objects**: Reuse instances across multiple operations
3. **Structured results**: Native Python dictionaries instead of parsing output
4. **Exception handling**: Proper Python exceptions vs exit codes
5. **Integration**: Easy to use in analysis scripts and Jupyter notebooks

---

## 2. Git Submodule Operations

### 2.1 Adding Submodules Without Cloning

#### Decision
Use manual `.gitmodules` configuration plus `git update-index --cacheinfo 160000` to link submodules without cloning, avoiding unnecessary disk I/O and network traffic for 1000+ datasets.

#### Rationale
- Dramatically reduces time and disk space for creating 1000+ submodule links
- Only metadata (URL, path, commit SHA) needed for structural organization
- Actual data retrieval deferred until needed (lazy loading principle)
- Standard git mechanism; documented in git-submodule sources
- OpenNeuroStudies organizes datasets, doesn't require their content immediately

#### Code Example

```python
import subprocess
import os
from pathlib import Path

def add_submodule_without_cloning(
    repo_path: str,
    submodule_url: str,
    submodule_path: str,
    commit_sha: str,
    submodule_name: str = None,
    datalad_id: str = None
) -> None:
    """
    Add a git submodule without cloning it.

    Args:
        repo_path: Path to parent repository
        submodule_url: URL of submodule repository
        submodule_path: Relative path where submodule should appear
        commit_sha: Specific commit SHA to reference
        submodule_name: Name for submodule (defaults to path)
        datalad_id: DataLad UUID (optional, for DataLad datasets)
    """
    if submodule_name is None:
        # Use path as name, removing slashes
        submodule_name = submodule_path.replace('/', '-')

    os.chdir(repo_path)

    # 1. Create directory structure (git expects it for update-index)
    submodule_dir = Path(submodule_path)
    submodule_dir.mkdir(parents=True, exist_ok=True)

    # 2. Configure .gitmodules
    subprocess.run([
        'git', 'config', '-f', '.gitmodules',
        f'submodule.{submodule_name}.path',
        submodule_path
    ], check=True)

    subprocess.run([
        'git', 'config', '-f', '.gitmodules',
        f'submodule.{submodule_name}.url',
        submodule_url
    ], check=True)

    # Add DataLad-specific fields if provided
    if datalad_id:
        subprocess.run([
            'git', 'config', '-f', '.gitmodules',
            f'submodule.{submodule_name}.datalad-id',
            datalad_id
        ], check=True)

        subprocess.run([
            'git', 'config', '-f', '.gitmodules',
            f'submodule.{submodule_name}.datalad-url',
            submodule_url
        ], check=True)

    # 3. Stage .gitmodules
    subprocess.run(['git', 'add', '.gitmodules'], check=True)

    # 4. Add gitlink with specific commit SHA
    # Mode 160000 = gitlink (submodule reference)
    subprocess.run([
        'git', 'update-index', '--add', '--cacheinfo',
        f'160000,{commit_sha},{submodule_path}'
    ], check=True)

    print(f"Added submodule {submodule_name} at {submodule_path} -> {commit_sha}")

# Example usage for OpenNeuro datasets
add_submodule_without_cloning(
    repo_path='study-ds000001',
    submodule_url='https://github.com/OpenNeuroDatasets/ds000001',
    submodule_path='sourcedata/raw',
    commit_sha='f8e27ac909e50b5b5e311f6be271f0b1757ebb7b',
    submodule_name='ds000001-raw',
    datalad_id='9850e7d6-100e-11e5-96f6-002590c1b0b6'
)

add_submodule_without_cloning(
    repo_path='study-ds000001',
    submodule_url='https://github.com/OpenNeuroDerivatives/ds000001-fmriprep',
    submodule_path='derivatives/fmriprep-21.0.1',
    commit_sha='a1b2c3d4e5f6789012345678901234567890abcd',
    submodule_name='ds000001-fmriprep',
    datalad_id='eb586851-1a79-4671-aded-31384b3d5d7f'
)
```

#### Understanding Mode 160000

**What is 160000?**
- Git file mode indicating a "gitlink" (submodule reference)
- Not a regular file (100644), directory (040000), or executable (100755)
- Records a commit SHA as a directory entry
- Special handling by git to recognize submodule

**Git Object Types:**
- `100644` = regular file
- `100755` = executable file
- `040000` = directory/tree
- `120000` = symbolic link
- `160000` = gitlink (submodule)

#### Workflow Steps

```bash
# Manual equivalent (what the Python code does):

# 1. Configure .gitmodules
git config -f .gitmodules submodule."name".path "path/to/submodule"
git config -f .gitmodules submodule."name".url "https://example.com/repo.git"
git config -f .gitmodules submodule."name".datalad-id "uuid-here"

# 2. Stage .gitmodules
git add .gitmodules

# 3. Add gitlink pointing to specific commit
mkdir -p path/to/submodule
git update-index --add --cacheinfo 160000,<commit-sha>,path/to/submodule

# 4. Commit
git commit -m "Add submodule without cloning"

# Later, if you need to actually use the submodule:
git submodule update --init path/to/submodule
```

#### Alternatives Considered

1. **`git submodule add <url> <path>`**: Rejected as it requires full clone
   - Pros: Official command, automatic setup
   - Cons: Clones entire repository, slow for 1000+ datasets, requires ~TB disk space

2. **`datalad clone -d . <url> <path>`**: Rejected due to cloning overhead
   - Pros: DataLad-native, preserves metadata
   - Cons: Same cloning issue, even slower startup

3. **Sparse checkout**: Rejected as still requires clone operation
   - Pros: Reduces disk usage after clone
   - Cons: Still needs initial clone, complex setup

4. **GitHub API only (no submodules)**: Rejected as loses git benefits
   - Pros: No git overhead
   - Cons: Loses version tracking, submodule structure benefits, git-based workflows

---

### 2.2 .gitmodules Format and DataLad Conventions

#### Decision
Follow DataLad's extended `.gitmodules` format with `datalad-id` and `datalad-url` fields in addition to standard git `path` and `url` fields.

#### Rationale
- Preserves DataLad dataset identity across locations and renames
- `datalad-id` enables dataset tracking across entire history
- `datalad-url` supports special URL schemes (ria+http, ria+ssh)
- Compatible with standard git (extra fields ignored by git)
- Maintains provenance for BIDS dataset requirements

#### Format Specification

```ini
[submodule "descriptive-name"]
    path = relative/path/in/parent
    url = https://github.com/org/repo.git
    datalad-id = uuid-v4-here
    datalad-url = https://github.com/org/repo.git
```

#### Code Example

```python
def format_gitmodules_entry(
    name: str,
    path: str,
    url: str,
    datalad_id: str = None,
    extra_fields: dict = None
) -> str:
    """
    Generate .gitmodules entry in DataLad format.

    Args:
        name: Submodule name
        path: Relative path in parent repo
        url: Clone URL for submodule
        datalad_id: DataLad UUID (optional)
        extra_fields: Additional key-value pairs

    Returns:
        Formatted .gitmodules section
    """
    lines = [f'[submodule "{name}"]']
    lines.append(f'\tpath = {path}')
    lines.append(f'\turl = {url}')

    if datalad_id:
        lines.append(f'\tdatalad-id = {datalad_id}')
        lines.append(f'\tdatalad-url = {url}')

    if extra_fields:
        for key, value in extra_fields.items():
            lines.append(f'\t{key} = {value}')

    return '\n'.join(lines)

# Example: OpenNeuro raw dataset
raw_entry = format_gitmodules_entry(
    name='ds000001-raw',
    path='sourcedata/raw',
    url='https://github.com/OpenNeuroDatasets/ds000001',
    datalad_id='9850e7d6-100e-11e5-96f6-002590c1b0b6'
)

# Example: Derivative dataset
derivative_entry = format_gitmodules_entry(
    name='ds000001-fmriprep',
    path='derivatives/fmriprep-21.0.1',
    url='https://github.com/OpenNeuroDerivatives/ds000001-fmriprep',
    datalad_id='eb586851-1a79-4671-aded-31384b3d5d7f'
)

print(raw_entry)
print()
print(derivative_entry)
```

#### Output

```ini
[submodule "ds000001-raw"]
	path = sourcedata/raw
	url = https://github.com/OpenNeuroDatasets/ds000001
	datalad-id = 9850e7d6-100e-11e5-96f6-002590c1b0b6
	datalad-url = https://github.com/OpenNeuroDatasets/ds000001

[submodule "ds000001-fmriprep"]
	path = derivatives/fmriprep-21.0.1
	url = https://github.com/OpenNeuroDerivatives/ds000001-fmriprep
	datalad-id = eb586851-1a79-4671-aded-31384b3d5d7f
	datalad-url = https://github.com/OpenNeuroDerivatives/ds000001-fmriprep
```

#### Reading .gitmodules Programmatically

```python
import configparser
from pathlib import Path

def read_gitmodules(repo_path: str) -> dict:
    """
    Parse .gitmodules file into structured dictionary.

    Returns:
        Dict mapping submodule names to their properties
    """
    gitmodules_path = Path(repo_path) / '.gitmodules'

    if not gitmodules_path.exists():
        return {}

    config = configparser.ConfigParser()
    config.read(gitmodules_path)

    submodules = {}
    for section in config.sections():
        if section.startswith('submodule '):
            name = section.replace('submodule ', '').strip('"')
            submodules[name] = dict(config[section])

    return submodules

# Example usage
submodules = read_gitmodules('study-ds000001')
for name, props in submodules.items():
    print(f"{name}:")
    print(f"  Path: {props['path']}")
    print(f"  URL: {props['url']}")
    print(f"  DataLad ID: {props.get('datalad-id', 'N/A')}")
```

#### Extracting DataLad ID from Dataset

```python
import configparser
from pathlib import Path

def get_datalad_id(dataset_path: str) -> str:
    """
    Extract DataLad UUID from dataset's .datalad/config file.

    Returns:
        DataLad UUID or None if not found
    """
    config_path = Path(dataset_path) / '.datalad' / 'config'

    if not config_path.exists():
        return None

    config = configparser.ConfigParser()
    config.read(config_path)

    try:
        return config['datalad.dataset']['id']
    except KeyError:
        return None

# For remote datasets, get from .gitmodules in source superdataset
def get_datalad_id_from_remote(
    source_repo: str,
    submodule_path: str,
    gitmodules_content: str
) -> str:
    """Extract datalad-id for a submodule from .gitmodules content."""
    config = configparser.ConfigParser()
    config.read_string(gitmodules_content)

    for section in config.sections():
        if section.startswith('submodule '):
            if config[section].get('path') == submodule_path:
                return config[section].get('datalad-id')

    return None
```

#### Best Practices

1. **Submodule naming**: Use descriptive names (e.g., `ds000001-fmriprep`) not just paths
2. **Path structure**: Organize by type (`sourcedata/`, `derivatives/`)
3. **URL stability**: Prefer https URLs over ssh for public datasets
4. **DataLad ID**: Always include for DataLad datasets (enables provenance tracking)
5. **Comments**: .gitmodules doesn't support comments; document in README instead

---

### 2.3 DataLad vs Direct Git for Submodules

#### Decision
Use **direct git commands** for submodule manipulation when not cloning, use **DataLad** when working with actual dataset content.

#### Rationale
- Direct git: Faster for structural operations (no DataLad overhead)
- Direct git: More control over submodule references without content
- DataLad: Better for content operations (get, save, update with data)
- Hybrid approach: Structure with git, content with DataLad

#### Decision Matrix

| Operation | Use | Reason |
|-----------|-----|--------|
| Add submodule without cloning | **Git** | DataLad requires clone |
| Add submodule with cloning | **DataLad** | Preserves metadata |
| Update submodule reference | **Git** | Direct SHA manipulation |
| Fetch submodule content | **DataLad** | Handles annex content |
| Remove submodule | **Git** | Simple reference removal |
| Query submodule status | **DataLad** | Richer status info |

#### Code Examples

```python
# Use Git for: Adding submodule link without cloning
import subprocess

subprocess.run([
    'git', 'config', '-f', '.gitmodules',
    'submodule.name.path', 'path'
], check=True)
subprocess.run([
    'git', 'update-index', '--cacheinfo',
    '160000,<sha>,path'
], check=True)

# Use DataLad for: Cloning and getting content
import datalad.api as dl

ds = dl.clone(
    source='https://github.com/OpenNeuroDatasets/ds000001',
    path='sourcedata/raw',
    dataset='.'  # Register in parent
)

# Get specific files
dl.get(path='sourcedata/raw/dataset_description.json')

# Use Git for: Updating submodule reference
subprocess.run([
    'git', 'update-index', '--cacheinfo',
    f'160000,{new_sha},sourcedata/raw'
], check=True)

# Use DataLad for: Checking what's available
from datalad.api import Dataset
ds = Dataset('.')
status = ds.subdatasets()
```

#### Alternatives Considered
1. **Always use DataLad**: Rejected due to overhead for non-content operations
2. **Always use git**: Rejected as it loses DataLad benefits for content operations
3. **GitPython library**: Rejected as it's another dependency; subprocess is sufficient

---

## 3. GitHub API for Discovery

### 3.1 Reading Files Without Cloning

#### Decision
Use GitHub Contents API (`GET /repos/{owner}/{repo}/contents/{path}`) with `Accept: application/vnd.github.v3.raw` header to fetch file content directly without cloning.

#### Rationale
- No cloning overhead: Fetch only needed files (dataset_description.json)
- Rate limit efficient: Single request per file
- Direct access: Get raw content or base64 encoded
- Supports specific refs: Can fetch from any branch/tag/commit
- Essential for scaling to 1000+ datasets

#### Code Example

```python
import requests
import json
import base64
from typing import Optional, Dict, Any

class GitHubFileReader:
    """Read files from GitHub repositories without cloning."""

    def __init__(self, token: Optional[str] = None):
        """
        Initialize with optional GitHub token.

        Args:
            token: GitHub personal access token (increases rate limits)
        """
        self.base_url = 'https://api.github.com'
        self.session = requests.Session()

        if token:
            self.session.headers['Authorization'] = f'token {token}'

        # Default to API v3
        self.session.headers['Accept'] = 'application/vnd.github.v3+json'

    def read_file_raw(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: str = None
    ) -> str:
        """
        Read file content as raw text.

        Args:
            owner: Repository owner
            repo: Repository name
            path: Path to file in repository
            ref: Branch, tag, or commit SHA (default: default branch)

        Returns:
            Raw file content as string

        Raises:
            requests.HTTPError: If file not found or API error
        """
        url = f'{self.base_url}/repos/{owner}/{repo}/contents/{path}'

        # Request raw content directly
        headers = {'Accept': 'application/vnd.github.v3.raw'}
        params = {}
        if ref:
            params['ref'] = ref

        response = self.session.get(url, headers=headers, params=params)
        response.raise_for_status()

        return response.text

    def read_file_json(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: str = None
    ) -> Dict[str, Any]:
        """
        Read JSON file and parse it.

        Args:
            owner: Repository owner
            repo: Repository name
            path: Path to JSON file
            ref: Branch, tag, or commit SHA

        Returns:
            Parsed JSON as dictionary
        """
        content = self.read_file_raw(owner, repo, path, ref)
        return json.loads(content)

    def read_file_base64(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: str = None
    ) -> tuple[str, Dict[str, Any]]:
        """
        Read file with metadata (includes SHA, size, etc.).

        Returns:
            Tuple of (decoded_content, metadata_dict)
        """
        url = f'{self.base_url}/repos/{owner}/{repo}/contents/{path}'

        params = {}
        if ref:
            params['ref'] = ref

        response = self.session.get(url, params=params)
        response.raise_for_status()

        data = response.json()

        # Decode base64 content
        if data.get('encoding') == 'base64':
            content = base64.b64decode(data['content']).decode('utf-8')
        else:
            content = data['content']

        metadata = {
            'sha': data['sha'],
            'size': data['size'],
            'name': data['name'],
            'path': data['path'],
            'download_url': data.get('download_url')
        }

        return content, metadata

# Example usage for OpenNeuro datasets
reader = GitHubFileReader(token='your_github_token')

# Read dataset_description.json from OpenNeuro dataset
dataset_desc = reader.read_file_json(
    owner='OpenNeuroDatasets',
    repo='ds000001',
    path='dataset_description.json'
)

print(f"Dataset Name: {dataset_desc.get('Name')}")
print(f"BIDS Version: {dataset_desc.get('BIDSVersion')}")
print(f"License: {dataset_desc.get('License')}")

# Read from specific commit
dataset_desc_v1 = reader.read_file_json(
    owner='OpenNeuroDatasets',
    repo='ds000001',
    path='dataset_description.json',
    ref='f8e27ac909e50b5b5e311f6be271f0b1757ebb7b'
)

# Read with metadata
content, metadata = reader.read_file_base64(
    owner='OpenNeuroDatasets',
    repo='ds000001',
    path='dataset_description.json'
)
print(f"File SHA: {metadata['sha']}")
print(f"File size: {metadata['size']} bytes")
```

#### API Response Format

**With `Accept: application/vnd.github.v3.raw`:**
```
HTTP/1.1 200 OK
Content-Type: text/plain; charset=utf-8

{
  "Name": "Balloon Analog Risk-taking Task",
  "BIDSVersion": "1.0.2",
  ...
}
```

**With default Accept header:**
```json
{
  "name": "dataset_description.json",
  "path": "dataset_description.json",
  "sha": "a1b2c3d4e5...",
  "size": 532,
  "encoding": "base64",
  "content": "ewogICJOYW1lIjogIkJhbGxvb24g...",
  "download_url": "https://raw.githubusercontent.com/..."
}
```

#### File Size Limits

- **Up to 1 MB**: Fully supported by Contents API
- **1-100 MB**: Limited support; use `download_url` or Git Blob API
- **Over 100 MB**: Use Git Blob API or git-lfs

For OpenNeuro datasets, `dataset_description.json` is typically < 10 KB.

#### Alternatives Considered

1. **Git Tree API**: More complex; better for batch operations (see section 3.4)
2. **Raw GitHub content**: No rate limit info in response headers
3. **`download_url` from API response**: Extra HTTP request; no auth benefits
4. **Cloning sparse**: Still requires clone operation; slower

---

### 3.2 Efficient Pagination for 1000+ Repositories

#### Decision
Use Link header-based pagination with `per_page=100` for listing organization repositories, avoiding the 1000-result Search API limit.

#### Rationale
- List repositories endpoint: No 1000-result limit (unlike Search API)
- Link headers: Official pagination mechanism
- `per_page=100`: Maximum allowed, minimizes requests
- Authenticated: 5,000 requests/hour vs 60 unauthenticated

#### Code Example

```python
import requests
from typing import Iterator, Dict, Any, Optional
import re

class GitHubOrgExplorer:
    """Discover repositories in GitHub organizations."""

    def __init__(self, token: Optional[str] = None):
        self.base_url = 'https://api.github.com'
        self.session = requests.Session()

        if token:
            self.session.headers['Authorization'] = f'token {token}'

        self.session.headers['Accept'] = 'application/vnd.github.v3+json'

    def list_repos(
        self,
        org: str,
        repo_type: str = 'all'
    ) -> Iterator[Dict[str, Any]]:
        """
        List all repositories in an organization with pagination.

        Args:
            org: Organization name (e.g., 'OpenNeuroDatasets')
            repo_type: 'all', 'public', 'private', 'forks', 'sources', 'member'

        Yields:
            Repository dictionaries with metadata
        """
        url = f'{self.base_url}/orgs/{org}/repos'
        params = {
            'per_page': 100,  # Maximum allowed
            'type': repo_type,
            'page': 1
        }

        while True:
            response = self.session.get(url, params=params)
            response.raise_for_status()

            repos = response.json()

            # Yield each repository
            for repo in repos:
                yield repo

            # Check for next page in Link header
            link_header = response.headers.get('Link', '')
            if not self._has_next_page(link_header):
                break

            # Increment page for next iteration
            params['page'] += 1

    def _has_next_page(self, link_header: str) -> bool:
        """Check if Link header indicates more pages."""
        return 'rel="next"' in link_header

    def _extract_page_count(self, link_header: str) -> Optional[int]:
        """Extract total page count from Link header."""
        # Link header format: <...&page=10>; rel="last"
        match = re.search(r'&page=(\d+)>; rel="last"', link_header)
        return int(match.group(1)) if match else None

    def get_repo_metadata(
        self,
        owner: str,
        repo: str
    ) -> Dict[str, Any]:
        """
        Get detailed metadata for a specific repository.

        Returns:
            Repository metadata including default_branch, created_at, etc.
        """
        url = f'{self.base_url}/repos/{owner}/{repo}'
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()

    def list_repo_refs(
        self,
        owner: str,
        repo: str,
        ref_type: str = 'heads'
    ) -> Iterator[Dict[str, Any]]:
        """
        List references (branches, tags) in a repository.

        Args:
            owner: Repository owner
            repo: Repository name
            ref_type: 'heads' (branches) or 'tags'

        Yields:
            Reference dictionaries with name and SHA
        """
        url = f'{self.base_url}/repos/{owner}/{repo}/git/refs/{ref_type}'
        params = {'per_page': 100, 'page': 1}

        while True:
            response = self.session.get(url, params=params)
            response.raise_for_status()

            refs = response.json()
            for ref in refs:
                yield ref

            if not self._has_next_page(response.headers.get('Link', '')):
                break

            params['page'] += 1

# Example: Discover all OpenNeuro datasets
explorer = GitHubOrgExplorer(token='your_github_token')

print("OpenNeuroDatasets repositories:")
for i, repo in enumerate(explorer.list_repos('OpenNeuroDatasets'), 1):
    print(f"{i}. {repo['name']} - {repo['default_branch']} "
          f"({repo['updated_at']})")

    if i >= 10:  # Limit output for example
        print("... (continuing)")
        break

# Get full count
all_repos = list(explorer.list_repos('OpenNeuroDatasets'))
print(f"\nTotal repositories: {len(all_repos)}")

# Example: Get specific dataset metadata
ds_metadata = explorer.get_repo_metadata('OpenNeuroDatasets', 'ds000001')
print(f"\nds000001 metadata:")
print(f"  Default branch: {ds_metadata['default_branch']}")
print(f"  Clone URL: {ds_metadata['clone_url']}")
print(f"  Size: {ds_metadata['size']} KB")

# Example: List all tags (releases) for a dataset
print(f"\nds000001 tags:")
for tag in explorer.list_repo_refs('OpenNeuroDatasets', 'ds000001', 'tags'):
    tag_name = tag['ref'].replace('refs/tags/', '')
    print(f"  {tag_name}: {tag['object']['sha']}")
```

#### Link Header Format

```
Link: <https://api.github.com/organizations/123/repos?page=2&per_page=100>; rel="next",
      <https://api.github.com/organizations/123/repos?page=15&per_page=100>; rel="last"
```

Possible `rel` values:
- `next`: URL for next page
- `last`: URL for last page
- `first`: URL for first page
- `prev`: URL for previous page

#### Pagination Best Practices

1. **Check rate limits** before starting large batch operations
2. **Use per_page=100** to minimize request count
3. **Follow Link headers** instead of manually constructing URLs
4. **Handle empty results** gracefully (end of pagination)
5. **Monitor X-RateLimit-Remaining** header during iteration

#### Alternatives Considered

1. **Search API**: Limited to 1000 results; rejected
2. **Manual page counting**: Fragile if results change; rejected
3. **GraphQL API**: More complex; consider for future optimization
4. **PyGithub library**: Hides details; prefer explicit control for now

---

### 3.3 ETag-Based Caching for Rate Limit Management

#### Decision
Implement conditional requests using `If-None-Match` with ETag caching to reduce rate limit consumption and enable efficient incremental updates.

#### Rationale
- 304 responses: Don't count against rate limit
- Incremental updates: Only process changed datasets
- Disk-based cache: Persist across script runs
- Standard HTTP: Works with any API client
- Critical for 1000+ dataset updates

#### Code Example

```python
import requests
import json
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import time

class CachedGitHubClient:
    """GitHub API client with ETag-based caching."""

    def __init__(
        self,
        token: Optional[str] = None,
        cache_dir: str = 'scratch/cache'
    ):
        """
        Initialize client with caching support.

        Args:
            token: GitHub personal access token
            cache_dir: Directory for cache storage
        """
        self.base_url = 'https://api.github.com'
        self.session = requests.Session()

        if token:
            self.session.headers['Authorization'] = f'token {token}'

        self.session.headers['Accept'] = 'application/vnd.github.v3+json'

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.etag_file = self.cache_dir / 'etags.json'
        self.etags = self._load_etags()

    def _load_etags(self) -> Dict[str, str]:
        """Load ETags from cache file."""
        if self.etag_file.exists():
            with open(self.etag_file, 'r') as f:
                return json.load(f)
        return {}

    def _save_etags(self):
        """Save ETags to cache file."""
        with open(self.etag_file, 'w') as f:
            json.dump(self.etags, f, indent=2)

    def _cache_key(self, url: str, params: dict = None) -> str:
        """Generate cache key from URL and parameters."""
        key_input = url
        if params:
            # Sort params for consistent keys
            param_str = '&'.join(f"{k}={v}" for k, v in sorted(params.items()))
            key_input = f"{url}?{param_str}"

        return hashlib.sha256(key_input.encode()).hexdigest()

    def _get_cache_path(self, cache_key: str) -> Path:
        """Get file path for cached response."""
        return self.cache_dir / f"{cache_key}.json"

    def get(
        self,
        url: str,
        params: dict = None,
        use_cache: bool = True
    ) -> Tuple[Any, bool]:
        """
        Make GET request with ETag caching.

        Args:
            url: API endpoint URL
            params: Query parameters
            use_cache: Whether to use conditional requests

        Returns:
            Tuple of (response_data, from_cache)
            - response_data: Parsed JSON response
            - from_cache: True if 304 response (not modified)

        Raises:
            requests.HTTPError: On API errors
        """
        cache_key = self._cache_key(url, params)
        cache_path = self._get_cache_path(cache_key)

        # Prepare request headers
        headers = {}
        if use_cache and cache_key in self.etags:
            # Add If-None-Match header for conditional request
            headers['If-None-Match'] = self.etags[cache_key]

        # Make request
        response = self.session.get(url, params=params, headers=headers)

        # Handle 304 Not Modified
        if response.status_code == 304:
            # Load from cache
            if cache_path.exists():
                with open(cache_path, 'r') as f:
                    return json.load(f), True
            else:
                # Cache file missing; re-fetch without conditional
                return self.get(url, params, use_cache=False)

        # Handle other errors
        response.raise_for_status()

        # Store ETag for future requests
        if 'ETag' in response.headers:
            self.etags[cache_key] = response.headers['ETag']
            self._save_etags()

        # Parse and cache response
        data = response.json()
        with open(cache_path, 'w') as f:
            json.dump(data, f, indent=2)

        return data, False

    def check_rate_limit(self) -> Dict[str, Any]:
        """
        Check current rate limit status.

        Returns:
            Dict with limit, remaining, reset timestamp
        """
        url = f'{self.base_url}/rate_limit'
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()['resources']['core']

    def wait_for_rate_limit(self, min_remaining: int = 100):
        """
        Wait if rate limit is too low.

        Args:
            min_remaining: Minimum requests to keep available
        """
        rate_limit = self.check_rate_limit()
        remaining = rate_limit['remaining']

        if remaining < min_remaining:
            reset_time = rate_limit['reset']
            wait_seconds = reset_time - int(time.time()) + 60

            print(f"Rate limit low ({remaining} remaining). "
                  f"Waiting {wait_seconds}s until reset...")
            time.sleep(wait_seconds)

# Example usage
client = CachedGitHubClient(token='your_github_token')

# First request: Fetches from API, stores ETag
url = 'https://api.github.com/repos/OpenNeuroDatasets/ds000001/contents/dataset_description.json'
data, from_cache = client.get(url)
print(f"First request - from cache: {from_cache}")

# Second request: Returns 304 if unchanged, uses cache
data, from_cache = client.get(url)
print(f"Second request - from cache: {from_cache}")

# Check rate limit status
rate_limit = client.check_rate_limit()
print(f"\nRate limit status:")
print(f"  Limit: {rate_limit['limit']}")
print(f"  Remaining: {rate_limit['remaining']}")
print(f"  Resets at: {time.ctime(rate_limit['reset'])}")

# Batch processing with rate limit awareness
def process_datasets_cached(dataset_ids: list):
    """Process multiple datasets with caching."""
    client = CachedGitHubClient(token='your_token')

    results = []
    for ds_id in dataset_ids:
        # Check rate limit periodically
        if len(results) % 50 == 0:
            client.wait_for_rate_limit(min_remaining=100)

        url = f'https://api.github.com/repos/OpenNeuroDatasets/{ds_id}'
        try:
            data, cached = client.get(url)
            results.append({
                'id': ds_id,
                'name': data.get('name'),
                'cached': cached
            })
        except requests.HTTPError as e:
            print(f"Error fetching {ds_id}: {e}")

    return results
```

#### Cache Directory Structure

```
scratch/cache/
├── etags.json                           # ETag mapping
├── a1b2c3d4e5f6789...abcdef.json      # Cached response 1
├── fedcba987...123456789abc.json      # Cached response 2
└── ...
```

#### ETags File Format

```json
{
  "a1b2c3d4e5f6789abcdef123456789abcdef": "\"6d82cfc7b33c1c9a6e9e7f1e9c6e8d5b\"",
  "fedcba9876543210fedcba9876543210": "\"8d5b7a9c6e1f0e2d3c4b5a6e9f8d7c6b\""
}
```

#### HTTP Flow with ETags

```
# First request
GET /repos/OpenNeuroDatasets/ds000001/contents/dataset_description.json
-> 200 OK
   ETag: "abc123"
   { ... response data ... }

# Second request (file unchanged)
GET /repos/OpenNeuroDatasets/ds000001/contents/dataset_description.json
If-None-Match: "abc123"
-> 304 Not Modified
   (no body, uses cached data)

# Third request (file changed)
GET /repos/OpenNeuroDatasets/ds000001/contents/dataset_description.json
If-None-Match: "abc123"
-> 200 OK
   ETag: "def456"
   { ... new response data ... }
```

#### Rate Limit Headers

Every API response includes:
```
X-RateLimit-Limit: 5000
X-RateLimit-Remaining: 4995
X-RateLimit-Reset: 1372700873
X-RateLimit-Used: 5
X-RateLimit-Resource: core
```

#### Benefits

1. **Rate limit preservation**: 304 responses don't count
2. **Network efficiency**: No response body for 304
3. **Incremental updates**: Only fetch changed resources
4. **Persistent cache**: Survives script restarts
5. **Automatic invalidation**: New ETag = cache invalid

#### Alternatives Considered

1. **Time-based caching**: Less accurate; rejected
2. **No caching**: Wastes rate limit; rejected
3. **Database cache**: Overkill for this use case; rejected
4. **Redis/Memcached**: Additional dependency; file-based sufficient

---

## 4. Summary of Decisions

### DataLad Python API

| Topic | Decision | Key Benefit |
|-------|----------|-------------|
| Import convention | `import datalad.api as dl` | Standard, concise |
| Dataset creation | `dl.create(annex=False)` | Plain Git for metadata |
| Error handling | `on_failure='continue'` | Batch resilience |
| Commits | `Dataset.save(message=...)` | Provenance tracking |

### Git Submodules

| Topic | Decision | Key Benefit |
|-------|----------|-------------|
| Adding submodules | `git update-index --cacheinfo 160000` | No cloning needed |
| .gitmodules format | DataLad extended format | Preserves DataLad IDs |
| Tool choice | Git for structure, DataLad for content | Optimal performance |

### GitHub API

| Topic | Decision | Key Benefit |
|-------|----------|-------------|
| File reading | Contents API with raw Accept header | Direct access |
| Pagination | Link header-based | No 1000-result limit |
| Caching | ETag-based conditional requests | Rate limit savings |

---

## 5. References

### Official Documentation
- DataLad Python API: http://docs.datalad.org/en/stable/modref.html
- DataLad Handbook: https://handbook.datalad.org/
- GitHub REST API: https://docs.github.com/en/rest
- Git Submodules: https://git-scm.com/book/en/v2/Git-Tools-Submodules
- BIDS Specification: https://bids-specification.readthedocs.io/

### Key Resources
- DataLad create: http://docs.datalad.org/en/stable/generated/datalad.api.create.html
- GitHub Contents API: https://docs.github.com/en/rest/repos/contents
- GitHub Tree API: https://docs.github.com/en/rest/git/trees
- GitHub Best Practices: https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api

---

**End of Research Document**
