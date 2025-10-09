# Research: OpenNeuroStudies Infrastructure Refactoring

**Feature**: [specs/001-read-file-doc](./spec.md)
**Date**: 2025-10-09

## 1. Concurrency Library Selection

**Decision**: `concurrent.futures.ThreadPoolExecutor`

**Rationale**:

For the OpenNeuroStudies infrastructure, which involves I/O-bound workloads (GitHub API calls, file reading, git operations), `ThreadPoolExecutor` is the optimal choice. The workload characteristics align perfectly with thread-based concurrency: DataLad operations involve git/git-annex commands that spend significant time waiting for disk I/O, network requests, and subprocess execution. Python's Global Interpreter Lock (GIL) does not negatively impact I/O-bound tasks because threads waiting on I/O release the GIL, allowing other threads to proceed.

ThreadPoolExecutor provides a simple, standard library solution with excellent error handling through futures and easy state synchronization using standard `threading.Lock()` objects. For synchronizing top-level operations (like updating `studies.tsv`), we can pass a shared lock to worker functions and use it to protect critical sections. The default max_workers calculation (`min(32, os.cpu_count() + 4)`) is well-suited for I/O workloads, providing reasonable parallelism without overwhelming the system.

DataLad compatibility is strong since DataLad operations are synchronous subprocess calls - ThreadPoolExecutor naturally handles this by running each DataLad operation in a separate thread without serialization complexity. Error collection is straightforward using `concurrent.futures.as_completed()` or by capturing exceptions from futures.

**Alternatives Considered**:

- **ProcessPoolExecutor**: Rejected because it's designed for CPU-bound tasks and introduces significant overhead. Each process requires separate memory space, making shared state synchronization complex. Passing DataLad dataset objects between processes requires pickling, which is problematic for git repositories with file handles and internal state. The IPC overhead would slow down our I/O-bound workload rather than speed it up.

- **joblib.Parallel**: Rejected despite being popular in data science. While it provides nice features like progress bars and efficient NumPy array sharing, these benefits don't apply to our use case. We're not working with NumPy arrays, and the added dependency isn't justified when ThreadPoolExecutor provides equivalent functionality for our needs. Joblib's batching heuristics could actually cause issues with our variable-duration tasks (some studies process quickly, others require extensive API calls).

- **multiprocessing.Pool**: Rejected for the same reasons as ProcessPoolExecutor - unnecessary complexity for I/O-bound work, state sharing difficulties, and no advantage over the higher-level ThreadPoolExecutor API.

**Code Example**:

```python
import concurrent.futures
import threading
from pathlib import Path
from typing import List, Dict, Any
import datalad.api as dl

class StudyProcessor:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.studies_lock = threading.Lock()
        self.errors: List[Dict[str, Any]] = []
        self.errors_lock = threading.Lock()

    def process_study(self, study_id: str, dataset_info: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single study dataset - runs in worker thread."""
        try:
            # Perform I/O-bound operations without locking
            study_dir = self.output_dir / f"study-{study_id}"

            # Create DataLad dataset without annex
            if not study_dir.exists():
                dl.create(path=str(study_dir), annex=False, dataset=str(self.output_dir))

            # Link source datasets as git submodules (I/O-bound, no locking needed)
            # ... git operations here ...

            # Generate metadata
            metadata = self._generate_study_metadata(study_id, dataset_info)

            # Update shared studies.tsv - requires synchronization
            with self.studies_lock:
                self._update_studies_tsv(study_id, metadata)

            return {"study_id": study_id, "status": "success", "metadata": metadata}

        except Exception as e:
            # Record error with synchronization
            with self.errors_lock:
                self.errors.append({
                    "study_id": study_id,
                    "error_type": type(e).__name__,
                    "message": str(e)
                })
            raise

    def _generate_study_metadata(self, study_id: str, dataset_info: Dict[str, Any]) -> Dict[str, Any]:
        """Generate metadata for a study - I/O-bound, no locking needed."""
        # Fetch dataset_description.json from GitHub API
        # Parse source datasets
        # Count imaging files
        return {}

    def _update_studies_tsv(self, study_id: str, metadata: Dict[str, Any]) -> None:
        """Update studies.tsv file - MUST be called with studies_lock held."""
        studies_file = self.output_dir / "studies.tsv"
        # Read, update, write - protected by lock
        pass

    def process_studies_parallel(self, studies: Dict[str, Dict[str, Any]], max_workers: int = None) -> List[Dict[str, Any]]:
        """Process multiple studies in parallel with error handling."""
        results = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_study = {
                executor.submit(self.process_study, study_id, info): study_id
                for study_id, info in studies.items()
            }

            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_study):
                study_id = future_to_study[future]
                try:
                    result = future.result()
                    results.append(result)
                    print(f"✓ Completed {study_id}")
                except Exception as e:
                    print(f"✗ Failed {study_id}: {e}")

        return results

# Usage example
if __name__ == "__main__":
    processor = StudyProcessor(Path("/path/to/OpenNeuroStudies"))

    studies_to_process = {
        "ds000001": {"url": "https://github.com/OpenNeuroDatasets/ds000001", "commit": "abc123"},
        "ds000002": {"url": "https://github.com/OpenNeuroDatasets/ds000002", "commit": "def456"},
        # ... more studies
    }

    # Process up to 10 studies concurrently (I/O-bound, can exceed CPU count)
    results = processor.process_studies_parallel(studies_to_process, max_workers=10)

    print(f"Processed {len(results)} studies with {len(processor.errors)} errors")
```

## 2. GitHub API Rate Limit Strategy

**Decision**: Use `requests-cache` with conditional requests and time-based expiration, combined with batch optimization patterns.

**Rationale**:

GitHub API provides 5000 requests per hour for authenticated users. For 1000+ datasets, we need intelligent caching to avoid exhausting this limit. The key insight is that GitHub's `304 Not Modified` responses from conditional requests do NOT count against the rate limit, making caching with conditional requests extremely effective.

The `requests-cache` library integrates cleanly with PyGithub using `install_cache()`, which monkey-patches the underlying requests library. While PyGithub doesn't natively support conditional requests (Issue #536), requests-cache automatically handles ETags and If-None-Match headers transparently. GitHub API responses include Cache-Control headers, which requests-cache can respect with `cache_control=True`.

For cache invalidation, we'll use a hybrid strategy: time-based expiration (24 hours for dataset metadata, 1 hour for releases/tags) combined with explicit cache clearing when we know data has changed (e.g., after creating a new study repository). This balances freshness with API efficiency.

Batch optimization involves batching multiple API calls into single requests where possible (e.g., using GraphQL for multiple datasets, though this requires more complex queries) and prioritizing cached data over real-time accuracy for non-critical operations.

**Caching Architecture Pattern**:

```
┌─────────────────────────────────────────────────────────────┐
│ Application Layer                                            │
│  - Study processor requests dataset metadata                │
│  - Release version checker requests tags                    │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ requests-cache Layer                                         │
│  - SQLite cache backend (persistent across runs)            │
│  - Automatic ETag handling (If-None-Match headers)          │
│  - Cache-Control header respect                             │
│  - Per-URL expiration policies                              │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ PyGithub → requests → GitHub API                            │
│  - Returns 304 Not Modified when content unchanged          │
│  - 304 responses don't count against rate limit             │
│  - Full responses cached with ETags for next request        │
└─────────────────────────────────────────────────────────────┘
```

**Cache Invalidation Strategy**:

1. **Time-based expiration**: Different TTLs for different resource types
   - Dataset metadata (dataset_description.json): 24 hours
   - Release/tag information: 1 hour
   - Repository tree listings: 6 hours
   - Commit information: 24 hours (immutable)

2. **Event-based invalidation**: Explicit cache clearing for known changes
   - After creating study repositories
   - After manual refresh commands
   - After batch processing completion

3. **Conditional requests**: Always send ETags for cache hits
   - Let GitHub tell us if content changed (304 = use cache, 200 = update cache)
   - Counts as cache hit for rate limit purposes even if sending request

**Code Example**:

```python
import requests_cache
from github import Github
from pathlib import Path
from typing import Dict, Any, Optional
import os
from datetime import timedelta

class GitHubAPIClient:
    """GitHub API client with intelligent caching to avoid rate limits."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Install global cache for all requests
        requests_cache.install_cache(
            cache_name=str(cache_dir / "github_cache"),
            backend='sqlite',
            expire_after=timedelta(hours=6),  # Default expiration
            cache_control=True,  # Respect Cache-Control headers from GitHub
            allowable_methods=['GET', 'HEAD'],  # Only cache safe methods
            urls_expire_after={
                # Fine-grained expiration by URL pattern
                '*/repos/*/git/commits/*': timedelta(days=7),  # Commits are immutable
                '*/repos/*/git/tags/*': timedelta(hours=1),     # Tags change rarely
                '*/repos/*/releases*': timedelta(hours=1),      # Releases need freshness
                '*/repos/*/contents/*': timedelta(hours=24),    # Dataset files change daily
                '*/repos/*/compare/*': timedelta(hours=6),      # Comparison results
            }
        )

        # Initialize PyGithub with token
        token = os.getenv('GITHUB_TOKEN')
        if not token:
            raise ValueError("GITHUB_TOKEN environment variable required")
        self.github = Github(token)

    def get_rate_limit_status(self) -> Dict[str, Any]:
        """Check current rate limit status."""
        rate_limit = self.github.get_rate_limit()
        return {
            "remaining": rate_limit.core.remaining,
            "limit": rate_limit.core.limit,
            "reset": rate_limit.core.reset,
        }

    def get_dataset_description(self, repo_name: str, ref: str = "HEAD") -> Optional[Dict[str, Any]]:
        """
        Fetch dataset_description.json from a repository.
        Uses cache automatically - 304 responses don't count against rate limit.
        """
        try:
            repo = self.github.get_repo(repo_name)
            # This API call is automatically cached by requests-cache
            content = repo.get_contents("dataset_description.json", ref=ref)

            import json
            return json.loads(content.decoded_content)
        except Exception as e:
            print(f"Error fetching dataset_description.json from {repo_name}: {e}")
            return None

    def get_latest_release_tag(self, repo_name: str) -> Optional[str]:
        """
        Get the latest release tag for a repository.
        Cached for 1 hour to balance freshness with rate limits.
        """
        try:
            repo = self.github.get_repo(repo_name)
            releases = repo.get_releases()

            # Get first release (most recent)
            latest_release = releases[0]
            return latest_release.tag_name
        except IndexError:
            # No releases
            return None
        except Exception as e:
            print(f"Error fetching releases from {repo_name}: {e}")
            return None

    def get_commit_count_between_tags(self, repo_name: str, base_tag: str, head_tag: str) -> Optional[int]:
        """
        Calculate number of commits between two tags using GitHub Compare API.
        Returns commit count without cloning repository.
        """
        try:
            repo = self.github.get_repo(repo_name)
            # Use compare API - automatically cached
            comparison = repo.compare(base_tag, head_tag)
            return comparison.ahead_by  # Number of commits ahead
        except Exception as e:
            print(f"Error comparing tags in {repo_name}: {e}")
            return None

    def clear_cache(self, pattern: Optional[str] = None) -> int:
        """
        Clear cache entries, optionally matching a pattern.
        Returns number of entries removed.
        """
        cache = requests_cache.get_cache()
        if pattern:
            # Clear specific URLs matching pattern
            removed = 0
            for key in list(cache.responses.keys()):
                if pattern in key:
                    del cache.responses[key]
                    removed += 1
            return removed
        else:
            # Clear entire cache
            count = len(cache.responses)
            cache.clear()
            return count

    def get_cache_info(self) -> Dict[str, Any]:
        """Get cache statistics."""
        cache = requests_cache.get_cache()
        return {
            "backend": cache.cache_name,
            "size": len(cache.responses),
        }

# Usage example
if __name__ == "__main__":
    client = GitHubAPIClient(Path.home() / ".cache" / "openneuro_studies")

    # Check rate limit before starting
    rate_info = client.get_rate_limit_status()
    print(f"Rate limit: {rate_info['remaining']}/{rate_info['limit']}")

    # Fetch dataset metadata - first call hits API, subsequent calls use cache
    for i in range(3):
        desc = client.get_dataset_description("OpenNeuroDatasets/ds000001")
        print(f"Call {i+1}: Got {desc.get('Name') if desc else 'None'}")

    # Cache info
    cache_info = client.get_cache_info()
    print(f"Cache: {cache_info['size']} entries")

    # Check rate limit after - should show minimal usage due to caching
    rate_info_after = client.get_rate_limit_status()
    requests_used = rate_info['remaining'] - rate_info_after['remaining']
    print(f"Requests used: {requests_used}")
```

## 3. Sparse Data Access Implementation

**Decision**: Use git-annex's HTTP range request capabilities with fsspec-git-annex as primary approach, with fallback to direct git-annex commands.

**Rationale**:

For accessing NIfTI headers without downloading full files, we need sparse read capabilities. After investigating datalad-fuse and fsspec options, the most reliable approach combines existing git-annex functionality with Python fsspec adapters.

The `fsspec-git-annex` package provides a filesystem interface to git-annex repositories that supports partial reads through HTTP range requests when the git-annex special remote supports it. This works well with OpenNeuro datasets since they typically use web-accessible special remotes. The datalad-fuse project has implemented fsspec integration with a `fsspec-head` command that includes a `--bytes` option for retrieving partial file content.

However, sparse access has limitations: not all git-annex remotes support range requests, and network reliability issues can cause failures. Therefore, we need a three-tier fallback strategy:

1. **Primary**: fsspec with range requests for NIfTI headers (first ~352 bytes for NIfTI-1, ~540 bytes for NIfTI-2)
2. **Secondary**: git-annex's built-in partial transfer support using `git annex get --bytes`
3. **Tertiary**: Cache results and mark datasets where sparse access failed for batch processing

NIfTI headers are fixed-size at the beginning of files, making them ideal for range requests. We only need the first ~1KB of each file to extract dimensions, voxel sizes, and data types.

**Recommended Approach**:

```
Sparse Access Strategy:
┌──────────────────────────────────────────────────────────┐
│ 1. Try fsspec-git-annex with HTTP range request         │
│    - Fast, no git-annex commands needed                 │
│    - Works with web special remotes                     │
│    - Read first 1KB of NIfTI file                       │
└────────┬─────────────────────────────────────────────────┘
         │ ✓ Success → Parse header → Done
         │ ✗ Fail
         ▼
┌──────────────────────────────────────────────────────────┐
│ 2. Try git-annex get --bytes=1024                       │
│    - Use DataLad/git-annex CLI                          │
│    - Download partial content                           │
│    - Slower but more reliable                           │
└────────┬─────────────────────────────────────────────────┘
         │ ✓ Success → Parse header → Done
         │ ✗ Fail
         ▼
┌──────────────────────────────────────────────────────────┐
│ 3. Mark for batch processing / Skip metrics            │
│    - Log dataset for later full-clone processing        │
│    - Mark imaging metrics as "unavailable"              │
│    - Continue without sparse data                       │
└──────────────────────────────────────────────────────────┘
```

**Fallback Strategy**:

- For datasets where sparse access consistently fails, maintain a "sparse_access_failed.txt" file
- These datasets can be processed in batch during off-hours with actual clones
- Populate imaging metrics incrementally as batch jobs complete
- Never block main workflow on sparse data access failures

**Code Example**:

```python
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import struct
import subprocess
import logging

logger = logging.getLogger(__name__)

class NIfTIHeaderReader:
    """
    Read NIfTI headers without downloading full files using sparse access.
    Implements fallback strategy for reliability.
    """

    NIFTI1_HEADER_SIZE = 348
    NIFTI2_HEADER_SIZE = 540

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.failed_cache = cache_dir / "sparse_access_failed.txt"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def is_known_failure(self, file_path: str) -> bool:
        """Check if this file previously failed sparse access."""
        if not self.failed_cache.exists():
            return False
        with open(self.failed_cache) as f:
            return file_path in f.read()

    def mark_failure(self, file_path: str) -> None:
        """Mark file as failed for sparse access."""
        with open(self.failed_cache, 'a') as f:
            f.write(f"{file_path}\n")

    def read_nifti_header_fsspec(self, file_path: str) -> Optional[bytes]:
        """
        Method 1: Try fsspec-git-annex with HTTP range request.
        This is the fastest method when it works.
        """
        try:
            # Attempt to import fsspec-git-annex
            # This is a conceptual example - actual API may differ
            import fsspec

            # Open with git-annex fsspec backend
            # The actual URL/path format depends on fsspec-git-annex implementation
            with fsspec.open(f"annexgit://{file_path}", mode='rb') as f:
                # Read first 1KB (enough for NIfTI-2 header)
                header = f.read(1024)
                return header if len(header) >= self.NIFTI1_HEADER_SIZE else None

        except ImportError:
            logger.debug("fsspec-git-annex not available")
            return None
        except Exception as e:
            logger.debug(f"fsspec read failed for {file_path}: {e}")
            return None

    def read_nifti_header_gitannex(self, dataset_path: Path, file_path: str) -> Optional[bytes]:
        """
        Method 2: Use git-annex get --bytes for partial download.
        More reliable but slower than fsspec.
        """
        try:
            # Use git-annex to download first 1KB
            result = subprocess.run(
                ['git', 'annex', 'get', '--bytes=1024', file_path],
                cwd=dataset_path,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                logger.debug(f"git-annex get failed: {result.stderr}")
                return None

            # Read the partial file
            full_path = dataset_path / file_path
            if full_path.exists():
                with open(full_path, 'rb') as f:
                    return f.read(1024)

            return None

        except subprocess.TimeoutExpired:
            logger.warning(f"git-annex get timed out for {file_path}")
            return None
        except Exception as e:
            logger.debug(f"git-annex read failed for {file_path}: {e}")
            return None

    def parse_nifti_header(self, header_bytes: bytes) -> Optional[Dict[str, Any]]:
        """
        Parse NIfTI header bytes to extract metadata.
        Returns dimensions, voxel sizes, and data type.
        """
        try:
            # Check magic number to determine NIfTI version
            # NIfTI-1: 'n+1\0' or 'ni1\0' at offset 344
            # Simplified parsing - production code should be more robust

            # Read header size (first 4 bytes, little-endian int)
            sizeof_hdr = struct.unpack('<i', header_bytes[0:4])[0]

            if sizeof_hdr == 348:
                # NIfTI-1 format
                dim = struct.unpack('<8h', header_bytes[40:56])  # Dimensions
                pixdim = struct.unpack('<8f', header_bytes[76:108])  # Voxel sizes
                datatype = struct.unpack('<h', header_bytes[70:72])[0]

                return {
                    "format": "NIfTI-1",
                    "dimensions": dim[1:dim[0]+1],  # First value is number of dimensions
                    "voxel_sizes": pixdim[1:dim[0]+1],
                    "datatype": datatype,
                }
            elif sizeof_hdr == 540:
                # NIfTI-2 format
                dim = struct.unpack('<8q', header_bytes[16:80])  # Dimensions (64-bit)
                pixdim = struct.unpack('<8d', header_bytes[104:168])  # Voxel sizes (double)
                datatype = struct.unpack('<h', header_bytes[12:14])[0]

                return {
                    "format": "NIfTI-2",
                    "dimensions": dim[1:dim[0]+1],
                    "voxel_sizes": pixdim[1:dim[0]+1],
                    "datatype": datatype,
                }
            else:
                logger.error(f"Unknown NIfTI format, sizeof_hdr={sizeof_hdr}")
                return None

        except Exception as e:
            logger.error(f"Failed to parse NIfTI header: {e}")
            return None

    def get_nifti_metadata(self, dataset_path: Path, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Get NIfTI metadata using sparse access with fallback strategy.

        Args:
            dataset_path: Path to DataLad dataset root
            file_path: Relative path to NIfTI file within dataset

        Returns:
            Dictionary with NIfTI metadata or None if all methods fail
        """
        # Skip if previously failed
        if self.is_known_failure(file_path):
            logger.debug(f"Skipping {file_path} (known failure)")
            return None

        # Try method 1: fsspec with range request
        header_bytes = self.read_nifti_header_fsspec(file_path)

        # Try method 2: git-annex get --bytes
        if header_bytes is None:
            header_bytes = self.read_nifti_header_gitannex(dataset_path, file_path)

        # Both methods failed
        if header_bytes is None:
            logger.warning(f"All sparse access methods failed for {file_path}")
            self.mark_failure(file_path)
            return None

        # Parse the header
        return self.parse_nifti_header(header_bytes)

# Usage example
if __name__ == "__main__":
    reader = NIfTIHeaderReader(Path.home() / ".cache" / "nifti_headers")

    # Example: Extract metadata from a NIfTI file in a DataLad dataset
    dataset_path = Path("/path/to/dataset")
    nifti_file = "sub-01/func/sub-01_task-rest_bold.nii.gz"

    metadata = reader.get_nifti_metadata(dataset_path, nifti_file)

    if metadata:
        print(f"Format: {metadata['format']}")
        print(f"Dimensions: {metadata['dimensions']}")
        print(f"Voxel sizes: {metadata['voxel_sizes']}")
        print(f"Data type: {metadata['datatype']}")
    else:
        print("Failed to extract metadata - will process in batch later")
```

## 4. DataLad API Patterns

**Decision**: Use `datalad.api` for all standard operations; use `datalad.support.annexrepo` only for low-level git operations not exposed in the high-level API.

**Rationale**:

DataLad's architecture clearly separates concerns: `datalad.api` provides user-facing, high-level operations with consistent error handling, provenance tracking, and state management. The `datalad.support.annexrepo` and `datalad.support.gitrepo` modules are internal, low-level interfaces to git and git-annex that lack the safety guarantees of the high-level API.

The DataLad documentation shows deprecation warnings for several `annexrepo` methods, explicitly recommending high-level alternatives. This indicates the project's direction: users should rely on `datalad.api`. The high-level API provides better abstraction, automatic result reporting, and integration with DataLad's configuration system.

For our use case, we need:
1. Creating datasets without annex: `datalad.api.create(annex=False)`
2. Adding git submodules: Use `datalad.api.install()` or direct git commands
3. Running commands with provenance: `datalad.api.run()`
4. State queries: `datalad.api.status()`, `datalad.api.diff()`

The pattern is: use `datalad.api` by default, drop to lower-level `Dataset.repo` methods only when the high-level API doesn't expose needed functionality (e.g., directly manipulating `.gitmodules` without cloning).

**Design Pattern Guide**:

```
Decision Tree for DataLad Operations:

┌─────────────────────────────────────────────────────────────┐
│ Is this a standard dataset operation?                       │
│ (create, save, get, push, install, run, status, diff)      │
└────┬─────────────────────────────────────────────────────┬──┘
     │ YES                                               NO│
     ▼                                                      ▼
┌─────────────────────────────────────┐  ┌────────────────────────────────────┐
│ Use datalad.api                     │  │ Is it a git operation?             │
│                                     │  │ (config, update-index, checkout)   │
│ import datalad.api as dl            │  └────┬────────────────────────────┬──┘
│ dl.create(...)                      │       │ YES                    NO  │
│ dl.save(...)                        │       ▼                            ▼
│ dl.run(...)                         │  ┌──────────────────────┐  ┌──────────────┐
│                                     │  │ Use subprocess       │  │ Use standard │
│ Benefits:                           │  │ with git commands    │  │ Python libs  │
│ - Provenance tracking               │  │                      │  │ (json, etc)  │
│ - Consistent error handling         │  │ subprocess.run([     │  └──────────────┘
│ - Result reporting                  │  │   'git', 'config',   │
│ - State management                  │  │   ...                │
└─────────────────────────────────────┘  │ ])                   │
                                          │                      │
                                          │ Avoid:               │
                                          │ - annexrepo methods  │
                                          │ - gitrepo methods    │
                                          │ (internal APIs)      │
                                          └──────────────────────┘
```

**Code Examples**:

```python
import datalad.api as dl
from pathlib import Path
import subprocess
import json
from typing import Optional, Dict, Any

class DatasetManager:
    """Manages DataLad dataset operations using recommended patterns."""

    def __init__(self, root_path: Path):
        self.root_path = root_path

    # Pattern 1: Creating DataLad dataset without annex
    def create_study_dataset(self, study_id: str) -> Path:
        """
        Create a study dataset without git-annex.
        Uses high-level API with annex=False parameter.
        """
        study_path = self.root_path / f"study-{study_id}"

        # Use datalad.api.create - high level, handles errors properly
        result = dl.create(
            path=str(study_path),
            annex=False,  # Plain git repository, no annex
            dataset=str(self.root_path),  # Register in parent dataset
            cfg_proc='text2git',  # All files to git (not annex)
            description=f"Study dataset for {study_id}"
        )

        return study_path

    # Pattern 2: Adding git submodules without cloning
    def add_submodule_without_clone(self,
                                     study_path: Path,
                                     submodule_url: str,
                                     submodule_path: str,
                                     commit_sha: str) -> bool:
        """
        Add git submodule without cloning - uses direct git commands.

        This is a case where datalad.api doesn't provide the needed functionality,
        so we use subprocess with git directly. We avoid datalad.support.annexrepo
        because it's an internal API.
        """
        try:
            # Create directory
            (study_path / submodule_path).mkdir(parents=True, exist_ok=True)

            # Configure submodule in .gitmodules
            submodule_name = submodule_path.replace('/', '-')
            subprocess.run(
                ['git', 'config', '-f', '.gitmodules',
                 f'submodule.{submodule_name}.path', submodule_path],
                cwd=study_path,
                check=True
            )
            subprocess.run(
                ['git', 'config', '-f', '.gitmodules',
                 f'submodule.{submodule_name}.url', submodule_url],
                cwd=study_path,
                check=True
            )

            # Add .gitmodules to git
            subprocess.run(
                ['git', 'add', '.gitmodules'],
                cwd=study_path,
                check=True
            )

            # Add gitlink pointing to specific commit
            subprocess.run(
                ['git', 'update-index', '--add', '--cacheinfo',
                 f'160000,{commit_sha},{submodule_path}'],
                cwd=study_path,
                check=True
            )

            # Commit using datalad.api.save for provenance
            dl.save(
                dataset=str(study_path),
                message=f"Add submodule {submodule_path} at {commit_sha[:8]}"
            )

            return True

        except subprocess.CalledProcessError as e:
            print(f"Failed to add submodule: {e}")
            return False

    # Pattern 3: Running commands with provenance capture
    def run_with_provenance(self,
                           dataset_path: Path,
                           command: str,
                           message: str,
                           inputs: Optional[list] = None,
                           outputs: Optional[list] = None) -> bool:
        """
        Run command with DataLad provenance tracking.
        Uses datalad.api.run - the recommended high-level API.
        """
        try:
            result = dl.run(
                cmd=command,
                dataset=str(dataset_path),
                message=message,
                inputs=inputs,  # Files that are inputs (will be retrieved if needed)
                outputs=outputs,  # Files that will be produced/modified
                explicit=True,  # Only track specified inputs/outputs
            )
            return result[0]['status'] == 'ok'

        except Exception as e:
            print(f"Command failed: {e}")
            return False

    # Pattern 4: Checking dataset status
    def get_dataset_status(self, dataset_path: Path) -> Dict[str, Any]:
        """
        Get dataset status using high-level API.
        Returns information about modified, untracked files.
        """
        try:
            # Use datalad.api.status - high level
            results = dl.status(
                dataset=str(dataset_path),
                annex='availability',  # Include annex availability info
                return_type='generator'
            )

            status = {
                'modified': [],
                'untracked': [],
                'deleted': [],
            }

            for result in results:
                if result['status'] == 'ok':
                    state = result.get('state', '')
                    path = result.get('path', '')

                    if state == 'modified':
                        status['modified'].append(path)
                    elif state == 'untracked':
                        status['untracked'].append(path)
                    elif state == 'deleted':
                        status['deleted'].append(path)

            return status

        except Exception as e:
            print(f"Status check failed: {e}")
            return {}

    # Pattern 5: Error handling with DataLad results
    def save_with_error_handling(self, dataset_path: Path, message: str, paths: Optional[list] = None) -> tuple[bool, str]:
        """
        Save changes with proper error handling.
        DataLad returns structured results - we should check them.
        """
        try:
            results = dl.save(
                dataset=str(dataset_path),
                path=paths,
                message=message,
                return_type='item-or-list',  # Get list of results
                on_failure='ignore',  # Don't raise, we'll check results
            )

            # Check if operation succeeded
            if isinstance(results, dict):
                results = [results]

            for result in results:
                if result['status'] != 'ok':
                    error_msg = result.get('message', 'Unknown error')
                    return False, error_msg

            return True, "Success"

        except Exception as e:
            return False, str(e)

    # Anti-pattern: Don't access Dataset.repo directly unless necessary
    def update_dataset_config_WRONG(self, dataset_path: Path):
        """
        WRONG: Using internal annexrepo methods.
        This is discouraged and may break in future DataLad versions.
        """
        # DON'T DO THIS:
        # from datalad.support.annexrepo import AnnexRepo
        # repo = AnnexRepo(dataset_path)
        # repo.set_metadata(...)  # Internal API, may change
        pass

    def update_dataset_config_RIGHT(self, dataset_path: Path, key: str, value: str):
        """
        RIGHT: Using subprocess with git config for configuration.
        """
        subprocess.run(
            ['git', 'config', key, value],
            cwd=dataset_path,
            check=True
        )

# Usage examples
if __name__ == "__main__":
    manager = DatasetManager(Path("/path/to/OpenNeuroStudies"))

    # Create study dataset
    study_path = manager.create_study_dataset("ds000001")
    print(f"Created study at {study_path}")

    # Add source dataset as submodule without cloning
    success = manager.add_submodule_without_clone(
        study_path=study_path,
        submodule_url="https://github.com/OpenNeuroDatasets/ds000001",
        submodule_path="sourcedata/raw",
        commit_sha="abc123def456..."
    )
    print(f"Submodule added: {success}")

    # Run validation with provenance
    success = manager.run_with_provenance(
        dataset_path=study_path,
        command="bids-validator-deno .",
        message="Run BIDS validation",
        outputs=["derivatives/bids-validator.json"]
    )
    print(f"Validation completed: {success}")

    # Check status
    status = manager.get_dataset_status(study_path)
    print(f"Modified files: {len(status['modified'])}")
```

## 5. GitHub Actions + act Compatibility

**Decision**: Design workflows for GitHub Actions first, add act-specific workarounds using conditional logic with `$ACT` environment variable.

**Rationale**:

The `act` tool provides valuable local testing capabilities for GitHub Actions workflows, but it has several limitations due to its Docker-based execution model. Rather than restricting our workflows to act's capabilities, we should design for full GitHub Actions functionality and add fallbacks for local testing.

Key compatibility insights: act supports basic workflow features like jobs, steps, strategy matrices (with limitations), and conditional execution. However, it lacks full support for: scheduled cron triggers (must be manually triggered), some GitHub context variables, the `vars` context, workflow concurrency controls, and services like databases.

The most practical approach is to use act's special `$ACT` environment variable (set to "true" when running in act) to conditionally skip or modify steps that won't work locally. For secrets, act supports loading from `.secrets` files or passing via `-s` flag. For testing scheduled workflows, we manually trigger them with `act -j job_name`.

Matrix strategies work in act but have limitations around dynamic matrices and exit code handling (fail-fast behavior). Our workflows should use simple, static matrices when possible.

**Compatible vs Incompatible Features**:

| Feature | GitHub Actions | act Support | Workaround |
|---------|---------------|-------------|------------|
| Basic jobs/steps | ✓ Full | ✓ Full | None needed |
| Matrix strategy (static) | ✓ Full | ✓ Full | None needed |
| Matrix strategy (dynamic) | ✓ Full | ✗ Limited | Use static matrices or test only on GitHub |
| Secrets | ✓ Automatic | ✓ Manual | Use `.secrets` file or `-s` flag |
| Scheduled cron | ✓ Automatic | ✗ Manual trigger | Use `act -j job_name` |
| GitHub context | ✓ Full | ⚠ Partial | Check `$ACT` and provide defaults |
| `vars` context | ✓ Full | ✗ None | Use env vars or skip with `if: !env.ACT` |
| Artifacts | ✓ Full | ⚠ Limited | Works but stays local |
| Services | ✓ Full | ✗ None | Skip tests requiring services in act |
| Concurrency control | ✓ Full | ✗ Ignored | Not testable locally |
| Workflow dispatch | ✓ Full | ⚠ Limited | Basic support only |
| Docker containers | ✓ Full | ✓ Full | Fully supported |
| Default images | Optimized | ⚠ Large | Use `act -P ubuntu-latest=catthehacker/ubuntu:act-latest` |

**Workarounds for Common Limitations**:

1. **Secrets Management**: Create `.secrets` file in project root (gitignored):
   ```
   GITHUB_TOKEN=ghp_your_token_here
   ```

2. **Cron Schedule Testing**: Can't test actual scheduling, but can test job logic:
   ```bash
   act schedule -j update-datasets
   ```

3. **Missing GitHub Context**: Provide defaults in workflow:
   ```yaml
   env:
     GITHUB_REPOSITORY: ${{ github.repository || 'OpenNeuroStudies/OpenNeuroStudies' }}
   ```

4. **Skip Incompatible Steps**: Use conditional execution:
   ```yaml
   - name: Upload artifacts
     if: ${{ !env.ACT }}  # Skip when running in act
     uses: actions/upload-artifact@v3
   ```

**Example Workflow YAML**:

```yaml
name: Update Studies Metadata

# Scheduled to run daily, but can be manually triggered
on:
  schedule:
    - cron: '0 2 * * *'  # 2 AM UTC daily
  workflow_dispatch:  # Allow manual trigger (works in act)
  push:
    branches: [master]  # Also run on push for testing

env:
  # Provide defaults for act compatibility
  GITHUB_REPOSITORY: ${{ github.repository || 'OpenNeuroStudies/OpenNeuroStudies' }}

jobs:
  update-metadata:
    runs-on: ubuntu-latest

    strategy:
      # Static matrix works in act; dynamic matrices may not
      matrix:
        batch: [1, 2, 3, 4]  # Process studies in batches
      fail-fast: false  # Continue even if one batch fails

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          # act may not populate github.token automatically
          token: ${{ secrets.GITHUB_TOKEN }}
          submodules: false  # Don't clone submodules

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt

      - name: Install DataLad (act-compatible)
        run: |
          if [ -n "$ACT" ]; then
            echo "Running in act - using simplified DataLad install"
            pip install datalad
          else
            echo "Running in GitHub Actions - full DataLad setup"
            pip install datalad
            git config --global user.name "GitHub Actions"
            git config --global user.email "actions@github.com"
          fi

      - name: Update metadata for batch ${{ matrix.batch }}
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          python -m openneuro_studies.update_metadata \
            --batch ${{ matrix.batch }} \
            --total-batches 4 \
            --cache-dir .cache

      - name: Run tests on updated metadata
        run: |
          pytest tests/test_metadata.py -v

      - name: Commit changes (skip in act)
        if: ${{ !env.ACT }}  # Only commit in real GitHub Actions
        run: |
          git config user.name "GitHub Actions"
          git config user.email "actions@github.com"
          git add studies.tsv studies_derivatives.tsv
          git commit -m "Update metadata [skip ci]" || echo "No changes"
          git push

      - name: Upload artifacts (GitHub only)
        if: ${{ !env.ACT }}  # Artifacts don't work well in act
        uses: actions/upload-artifact@v3
        with:
          name: metadata-batch-${{ matrix.batch }}
          path: |
            studies.tsv
            studies_derivatives.tsv
            logs/*.log

      - name: Display results (act-compatible)
        run: |
          if [ -n "$ACT" ]; then
            echo "Running in act - results in local files"
            ls -lh studies*.tsv
          else
            echo "Running in GitHub Actions - results uploaded as artifacts"
          fi

  # Job to test scheduled workflow logic locally with act
  validate-datasets:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Run validation
        run: |
          python -m openneuro_studies.validate --sample 10

      - name: Check rate limit (requires real GitHub token)
        if: ${{ !env.ACT }}
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          python -m openneuro_studies.check_rate_limit
```

**Testing Workflow Locally with act**:

```bash
# Install act (if not already installed)
# brew install act  # macOS
# or download from https://github.com/nektos/act/releases

# Create .secrets file with GitHub token
echo "GITHUB_TOKEN=ghp_your_token" > .secrets

# Test specific job
act -j update-metadata

# Test scheduled workflow (cron can't be tested, but job can)
act schedule -j update-metadata

# Test with specific matrix value
act -j update-metadata --matrix batch:1

# Use smaller Docker image for faster testing
act -j update-metadata -P ubuntu-latest=catthehacker/ubuntu:act-latest

# Verbose output for debugging
act -j update-metadata -v

# Dry run to see what would happen
act -j update-metadata -n
```

**Summary**: Design workflows for full GitHub Actions capabilities, use `$ACT` environment variable for conditional logic, keep matrices simple for act compatibility, and test critical paths locally while accepting that some features (scheduled triggers, full artifacts, services) only work in GitHub's environment.

## 6. Outdatedness Calculation Without Cloning

**Decision**: Use GitHub Compare API (`/repos/{owner}/{repo}/compare/{base}...{head}`) with PyGithub's `repo.compare()` method to calculate commit counts between versions without cloning.

**Rationale**:

The GitHub Compare API provides exactly what we need: given two commit SHAs, tags, or branch names, it returns comparison metadata including `ahead_by` and `behind_by` counts. PyGithub exposes this via `repo.compare(base, head)`, which returns a `Comparison` object with these attributes.

For calculating derivative outdatedness, we need to determine how many commits the raw dataset has received since the derivative was processed. This requires:
1. Identifying the raw dataset version used for derivative processing (from SourceDatasets)
2. Getting the current raw dataset version (latest tag or HEAD)
3. Comparing these two refs using the Compare API

The Compare API works with any two refs (tags, branches, commits), making it flexible. It returns the commit count without transferring file contents, making it efficient. The API response is cacheable (request counts against rate limit but can be cached with requests-cache).

When the API is insufficient (e.g., non-GitHub repositories like forgejo instances), we fall back to shallow cloning with depth limiting or marking the calculation as unavailable.

**Implementation Strategy**:

```
Outdatedness Calculation Flow:
┌────────────────────────────────────────────────────────────┐
│ 1. Extract derivative metadata                             │
│    - SourceDatasets from dataset_description.json          │
│    - Parse raw dataset ID (e.g., ds000001)                 │
│    - Parse version processed (e.g., "1.0.3" from DOI/URL)  │
└────────┬───────────────────────────────────────────────────┘
         ▼
┌────────────────────────────────────────────────────────────┐
│ 2. Get current raw dataset version                         │
│    - Fetch latest tag via GitHub API                       │
│    - Or use HEAD commit if no tags                         │
└────────┬───────────────────────────────────────────────────┘
         ▼
┌────────────────────────────────────────────────────────────┐
│ 3. Calculate commit count using Compare API                │
│    - repo.compare(base=processed_version, head=current)    │
│    - Extract ahead_by count from Comparison object         │
│    - Cache result for 6 hours                              │
└────────┬───────────────────────────────────────────────────┘
         │ ✓ Success → Return commit count
         │ ✗ Fail (non-GitHub, API error, etc.)
         ▼
┌────────────────────────────────────────────────────────────┐
│ 4. Fallback strategies                                     │
│    A. Try forgejo/gitea API if known instance             │
│    B. Shallow clone with depth limit (git clone --depth)  │
│    C. Mark as "unknown" and schedule for batch processing │
└────────────────────────────────────────────────────────────┘
```

**Fallback Approach**:

When GitHub API is unavailable or insufficient:

1. **Forgejo/Gitea instances**: Check if repository is on known forgejo instance (e.g., cerebra.fz-juelich.de), use their compare API (similar to GitHub)

2. **Shallow clone**: Use `git clone --depth=1` to get HEAD, then fetch specific tag and calculate:
   ```bash
   git clone --depth=1 --branch current_tag https://...
   git fetch --depth=50 origin old_tag
   git rev-list --count old_tag..current_tag
   ```

3. **Mark as unknown**: For difficult cases, store `outdatedness: "unknown"` in metadata and schedule for batch processing during off-hours

**Code Example**:

```python
from github import Github
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import re
import subprocess
import logging
from datetime import timedelta
import requests_cache

logger = logging.getLogger(__name__)

class OutdatednessCalculator:
    """
    Calculate how outdated derivatives are without cloning repositories.
    Uses GitHub Compare API as primary method.
    """

    def __init__(self, github_client: Github, cache_dir: Path):
        self.github = github_client
        self.cache_dir = cache_dir

        # Cache comparison results for 6 hours
        requests_cache.install_cache(
            cache_name=str(cache_dir / "outdatedness_cache"),
            expire_after=timedelta(hours=6),
        )

    def parse_openneuro_dataset_id(self, source_dataset: Dict[str, Any]) -> Optional[str]:
        """
        Extract OpenNeuro dataset ID from SourceDatasets entry.

        Examples:
            - URL: "https://openneuro.org/datasets/ds000001" → "ds000001"
            - DOI: "doi:10.18112/openneuro.ds000001.v1.0.3" → "ds000001"
            - DOI: "10.18112/openneuro.ds000001.v1.0.3" → "ds000001"
        """
        url = source_dataset.get('URL', '')
        doi = source_dataset.get('DOI', '')

        # Try to extract from URL
        url_match = re.search(r'datasets/(ds\d+)', url)
        if url_match:
            return url_match.group(1)

        # Try to extract from DOI
        doi_match = re.search(r'openneuro\.(ds\d+)', doi)
        if doi_match:
            return doi_match.group(1)

        return None

    def parse_version_from_source(self, source_dataset: Dict[str, Any]) -> Optional[str]:
        """
        Extract version from SourceDatasets entry.

        Examples:
            - Version: "1.0.3" → "1.0.3"
            - DOI: "doi:10.18112/openneuro.ds000001.v1.0.3" → "1.0.3"
            - URL: "https://openneuro.org/datasets/ds000001/versions/1.0.3" → "1.0.3"
        """
        version = source_dataset.get('Version', '')
        url = source_dataset.get('URL', '')
        doi = source_dataset.get('DOI', '')

        # Try explicit Version field first
        if version and re.match(r'\d+\.\d+\.\d+', version):
            return version

        # Try to extract from URL
        url_match = re.search(r'versions?/(\d+\.\d+\.\d+)', url)
        if url_match:
            return url_match.group(1)

        # Try to extract from DOI
        doi_match = re.search(r'\.v?(\d+\.\d+\.\d+)', doi)
        if doi_match:
            return doi_match.group(1)

        return None

    def get_latest_version(self, repo_name: str) -> Optional[str]:
        """
        Get latest version tag for a repository.
        Returns tag name or None if no tags exist.
        """
        try:
            repo = self.github.get_repo(repo_name)
            tags = repo.get_tags()

            # Get first tag (most recent)
            latest_tag = tags[0]
            return latest_tag.name

        except IndexError:
            # No tags
            logger.debug(f"No tags found for {repo_name}")
            return None
        except Exception as e:
            logger.error(f"Error fetching tags for {repo_name}: {e}")
            return None

    def calculate_commits_between(self, repo_name: str, base_ref: str, head_ref: str) -> Optional[int]:
        """
        Calculate number of commits between two refs using GitHub Compare API.

        Args:
            repo_name: Repository in format "owner/repo"
            base_ref: Base reference (tag, branch, commit)
            head_ref: Head reference (tag, branch, commit)

        Returns:
            Number of commits head is ahead of base, or None if comparison fails
        """
        try:
            repo = self.github.get_repo(repo_name)

            # Use GitHub Compare API
            # Returns Comparison object with ahead_by, behind_by attributes
            comparison = repo.compare(base_ref, head_ref)

            logger.info(f"Comparison {repo_name} {base_ref}...{head_ref}: "
                       f"ahead_by={comparison.ahead_by}, behind_by={comparison.behind_by}")

            # ahead_by is the number of commits head is ahead of base
            return comparison.ahead_by

        except Exception as e:
            logger.error(f"Comparison failed for {repo_name} {base_ref}...{head_ref}: {e}")
            return None

    def calculate_derivative_outdatedness(self,
                                          derivative_id: str,
                                          source_datasets: list,
                                          org_prefix: str = "OpenNeuroDatasets") -> Dict[str, Any]:
        """
        Calculate outdatedness for a derivative dataset.

        Args:
            derivative_id: Derivative dataset ID (e.g., "ds001234")
            source_datasets: List of SourceDatasets from dataset_description.json
            org_prefix: GitHub organization for raw datasets

        Returns:
            Dictionary with outdatedness info per source dataset
        """
        outdatedness_info = {}

        for source in source_datasets:
            # Extract dataset ID
            dataset_id = self.parse_openneuro_dataset_id(source)
            if not dataset_id:
                logger.warning(f"Could not parse dataset ID from {source}")
                outdatedness_info[str(source)] = {
                    "status": "error",
                    "message": "Could not parse dataset ID"
                }
                continue

            # Extract version derivative was processed from
            processed_version = self.parse_version_from_source(source)
            if not processed_version:
                logger.warning(f"Could not parse version from {source}")
                outdatedness_info[dataset_id] = {
                    "status": "error",
                    "message": "Could not parse processed version"
                }
                continue

            # Get current latest version
            repo_name = f"{org_prefix}/{dataset_id}"
            current_version = self.get_latest_version(repo_name)

            if not current_version:
                logger.warning(f"No tags found for {repo_name}")
                outdatedness_info[dataset_id] = {
                    "status": "error",
                    "message": "No version tags found",
                    "processed_version": processed_version
                }
                continue

            # Calculate commit difference
            commit_count = self.calculate_commits_between(
                repo_name=repo_name,
                base_ref=processed_version,
                head_ref=current_version
            )

            if commit_count is None:
                # Try fallback method
                commit_count = self._fallback_commit_count(
                    repo_name=repo_name,
                    base_ref=processed_version,
                    head_ref=current_version
                )

            outdatedness_info[dataset_id] = {
                "status": "ok" if commit_count is not None else "error",
                "processed_version": processed_version,
                "current_version": current_version,
                "commits_behind": commit_count if commit_count is not None else "unknown",
                "is_outdated": commit_count > 0 if commit_count is not None else None
            }

        return outdatedness_info

    def _fallback_commit_count(self, repo_name: str, base_ref: str, head_ref: str) -> Optional[int]:
        """
        Fallback method: shallow clone and calculate commits.
        Only used when GitHub API fails.
        """
        try:
            # Create temporary directory
            import tempfile
            with tempfile.TemporaryDirectory() as tmpdir:
                repo_url = f"https://github.com/{repo_name}"

                # Shallow clone at head ref
                subprocess.run(
                    ['git', 'clone', '--depth=1', '--branch', head_ref, repo_url, tmpdir],
                    check=True,
                    capture_output=True,
                    timeout=60
                )

                # Fetch base ref with limited depth
                subprocess.run(
                    ['git', 'fetch', '--depth=100', 'origin', f'refs/tags/{base_ref}:refs/tags/{base_ref}'],
                    cwd=tmpdir,
                    check=True,
                    capture_output=True,
                    timeout=60
                )

                # Count commits
                result = subprocess.run(
                    ['git', 'rev-list', '--count', f'{base_ref}..{head_ref}'],
                    cwd=tmpdir,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                count = int(result.stdout.strip())
                logger.info(f"Fallback method succeeded: {base_ref}..{head_ref} = {count} commits")
                return count

        except Exception as e:
            logger.error(f"Fallback method failed: {e}")
            return None

# Usage example
if __name__ == "__main__":
    from github import Github
    import os

    # Initialize
    github = Github(os.getenv('GITHUB_TOKEN'))
    calculator = OutdatednessCalculator(github, Path.home() / ".cache" / "outdatedness")

    # Example derivative with SourceDatasets
    derivative_id = "ds006185"
    source_datasets = [
        {
            "URL": "https://openneuro.org/datasets/ds006131",
            "DOI": "doi:10.18112/openneuro.ds006131.v1.0.3",
            "Version": "1.0.3"
        }
    ]

    # Calculate outdatedness
    outdatedness = calculator.calculate_derivative_outdatedness(
        derivative_id=derivative_id,
        source_datasets=source_datasets
    )

    # Display results
    for dataset_id, info in outdatedness.items():
        if info['status'] == 'ok':
            print(f"{dataset_id}: {info['commits_behind']} commits behind")
            print(f"  Processed version: {info['processed_version']}")
            print(f"  Current version: {info['current_version']}")
            print(f"  Is outdated: {info['is_outdated']}")
        else:
            print(f"{dataset_id}: ERROR - {info.get('message', 'Unknown error')}")
```

## Summary

This research has identified optimal technical approaches for the OpenNeuroStudies infrastructure refactoring:

**Concurrency**: `ThreadPoolExecutor` provides the right balance of simplicity, I/O-bound performance, and DataLad compatibility. Thread-based concurrency with explicit locks for shared state (studies.tsv) enables efficient parallel processing of 1000+ datasets without the complexity of process-based parallelism.

**GitHub API Caching**: The `requests-cache` library with conditional requests (ETags) offers transparent integration with PyGithub while keeping us within the 5000 req/hour rate limit. Time-based cache expiration combined with GitHub's 304 Not Modified responses (which don't count against rate limits) provides an effective caching strategy.

**Sparse Data Access**: A multi-tiered approach using fsspec-git-annex for HTTP range requests, falling back to `git annex get --bytes`, and ultimately marking failures for batch processing provides robust NIfTI header access without full dataset cloning. This enables imaging metrics extraction as a separate operation stage.

**DataLad API Usage**: The high-level `datalad.api` should be used for all standard operations (create, save, run, status), with direct git commands via subprocess for operations not exposed in the API (like submodule manipulation without cloning). The internal `datalad.support.annexrepo` should be avoided as it's designed for DataLad internal use and lacks stability guarantees.

**GitHub Actions + act**: Workflows should be designed for full GitHub Actions capabilities with conditional logic using the `$ACT` environment variable to handle act's limitations. Matrix strategies, basic jobs, and Docker containers work in both, while scheduled triggers, full artifact handling, and services require workarounds or GitHub-only execution.

**Outdatedness Calculation**: PyGithub's `repo.compare()` method provides efficient commit counting between versions without cloning, using GitHub's Compare API. The `Comparison` object's `ahead_by` attribute directly gives us the outdatedness metric. Fallback to shallow cloning handles edge cases.

These decisions collectively enable efficient processing of 1000+ datasets with minimal cloning, intelligent API usage staying within rate limits, and robust error handling for production reliability.
