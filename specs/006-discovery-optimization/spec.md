# Feature Specification: Discovery Scanning Optimization

**Feature Branch**: `006-discovery-optimization`
**Created**: 2026-05-12
**Status**: Implemented
**Input**: User description: "Optimize discovery scanning to eliminate redundant GitHub API calls. `make refresh-existing` with `--include-related all` took 4 hours 11 minutes to scan 2826 repos when listing 10,000 repos should be much faster."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Fast Repeat Discovery Scans (Priority: P1)

As a dataset curator running `make refresh-existing` daily to keep the collection current, I need repeat discovery scans to complete in minutes rather than hours, so that I can maintain the collection without blocking my workflow for half a day.

**Why this priority**: This is the primary pain point. The 4+ hour scan time makes routine maintenance impractical. Most repeat runs process the same derivative graph that hasn't changed since the last scan.

**Independent Test**: Run `make refresh-existing` twice within 24 hours. First run creates a derivative graph cache. Second run should complete in under 5 minutes by loading the cached graph instead of re-scanning all 2826 repositories. Output (studies+derivatives.tsv) should be identical between runs.

**Acceptance Scenarios**:

1. **Given** a previous discovery run completed within 24 hours, **When** discovery runs again with `--include-related all`, **Then** the derivative graph is loaded from `.openneuro-studies/cache/derivative_graph.json` and the scan phase is skipped entirely
2. **Given** a cached derivative graph exists, **When** discovery loads it, **Then** a progress message reports "Loaded N derivatives from cache" and the expansion phase proceeds immediately
3. **Given** a cached derivative graph older than 24 hours, **When** discovery runs, **Then** the cache is considered expired and a full scan is performed, producing a fresh cache file

---

### User Story 2 - Faster Cold Discovery Scans (Priority: P2)

As a dataset curator running a first-time or cache-expired discovery, I need the full scan to complete in under 30 minutes rather than 4+ hours, so that even cold scans are feasible within a working session.

**Why this priority**: Cold scans still happen (first run, cache expired, force rescan). Eliminating redundant API calls within a single scan dramatically reduces wall time. This is the foundation that makes US1's cache worthwhile.

**Independent Test**: Run `openneuro-studies discover --include-related all --force-rescan` and measure elapsed time. Should complete in under 30 minutes for ~2826 repos (compared to 4h11m before optimization).

**Acceptance Scenarios**:

1. **Given** 2826 repositories across configured sources, **When** a full discovery scan runs, **Then** each repository requires at most 2 API calls (commit SHA + dataset_description.json), not 3 (the default_branch lookup is eliminated by using the listing response's default_branch field)
2. **Given** `--include-related all` is specified, **When** the bidirectional filter expansion runs, **Then** the derivative graph scan (`_discover_all_derivatives`) executes exactly once per session, regardless of how many expansion iterations are needed
3. **Given** HTTP response cache (`requests_cache`) is active, **When** a scan runs for longer than 1 hour, **Then** cached responses remain valid for the entire session (24-hour TTL prevents mid-scan cache expiration)

---

### User Story 3 - Cache Bypass for Forced Refresh (Priority: P3)

As a dataset curator who knows new datasets were recently added to OpenNeuro, I need a way to force a fresh scan that bypasses all caches, so that I can ensure newly published datasets are discovered immediately without waiting for cache expiration.

**Why this priority**: Cache bypass is an escape hatch needed occasionally. Most runs benefit from caching, but users must be able to override it when they know the data has changed.

**Independent Test**: Run `openneuro-studies discover --include-related all --force-rescan --test-filter ds000001` and verify it performs a full API scan even when a valid cache exists.

**Acceptance Scenarios**:

1. **Given** a valid derivative graph cache exists, **When** `--force-rescan` flag is provided, **Then** the cache is ignored and a full scan is performed
2. **Given** `--force-rescan` is used, **When** the scan completes, **Then** the cache file is updated with the fresh results

---

### Edge Cases

- What happens when the cache file is corrupted (invalid JSON)? System logs a warning and falls back to a full scan without crashing.
- What happens when the cache file has a version mismatch (schema change)? System ignores the cache and performs a full scan, then writes a new cache with the current version.
- What happens when the persistent cache directory doesn't exist? System creates `.openneuro-studies/cache/` automatically before writing the cache file.
- What happens when the bidirectional closure loop encounters circular derivative relationships (A sources B, B sources A)? The set-based closure algorithm terminates naturally when no new datasets are added, regardless of cycles.
- What happens when the session-level memoization returns stale data after a long-running session with interleaved operations? The session cache is only valid within a single `DatasetFinder` instance lifetime. New instances start with empty caches.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST cache the result of `_discover_all_derivatives()` in a session-level instance variable (`_cached_all_derivatives`) so that repeated calls within the same `DatasetFinder` instance return the cached result without re-scanning
- **FR-002**: System MUST persist the derivative graph (list of `DerivativeDataset` objects with their source_datasets relationships) to `.openneuro-studies/cache/derivative_graph.json` after each successful full scan
- **FR-003**: System MUST load the persistent derivative graph cache on subsequent runs, skipping the full scan if the cache is valid (not expired, correct schema version)
- **FR-004**: System MUST expire the persistent cache after 24 hours (configurable via class constant `_CACHE_TTL_SECONDS`)
- **FR-005**: System MUST invalidate the persistent cache when the cache file has a version mismatch (schema version stored in `"version"` field)
- **FR-006**: System MUST use the `default_branch` field from the GitHub listing API response when fetching commit SHAs, eliminating the separate `/repos/{owner}/{repo}` API call per repository
- **FR-007**: System MUST provide a `get_branch_sha(owner, repo, branch)` method on `GitHubClient` that fetches commit SHA for a known branch name, trying fallback branches (main, master) if the specified branch fails
- **FR-008**: System MUST set `requests_cache` TTL to 24 hours (86400 seconds) to prevent cache expiration during long-running scans
- **FR-009**: System MUST provide a `--force-rescan` CLI flag on the `discover` command that bypasses both session-level and persistent caches, forcing a full API scan
- **FR-010**: System MUST implement the bidirectional filter expansion (`--include-related all`) as a single closure algorithm that: (a) calls `_discover_all_derivatives()` exactly once, (b) iterates a while loop adding forward (raw→derivative) and backward (derivative→source) edges until no new datasets are added, (c) does NOT mutate `self.test_dataset_filter` during expansion
- **FR-011**: System MUST serialize `DerivativeDataset` objects to JSON for the persistent cache using Pydantic's `model_dump(mode="json")` and deserialize via `DerivativeDataset(**d)` constructor
- **FR-012**: System MUST log cache operations at INFO level (load/save success) and WARNING level (load failures, corrupt files)

### Key Entities

- **Derivative Graph Cache**: A JSON file at `.openneuro-studies/cache/derivative_graph.json` containing the serialized list of all `DerivativeDataset` objects discovered from configured sources. Schema: `{"version": int, "timestamp": ISO8601, "derivatives_count": int, "derivatives": [serialized DerivativeDataset]}`. This file is the primary mechanism for avoiding redundant full scans.

- **Session Cache**: An in-memory instance variable (`_cached_all_derivatives`) on `DatasetFinder` that stores the derivative list for the lifetime of one discovery session. Prevents redundant scans when the expansion algorithm or other code paths call `_discover_all_derivatives()` multiple times.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Repeat discovery scans (within 24 hours) complete in under 5 minutes by loading the cached derivative graph
- **SC-002**: Cold discovery scans (no cache or expired cache) complete in under 30 minutes for ~2826 repositories, reduced from 4+ hours
- **SC-003**: The number of GitHub API calls per cold scan is reduced from ~8,500+ (3 per repo) to ~5,652 (2 per repo: commit SHA + dataset_description.json)
- **SC-004**: `_discover_all_derivatives()` scanning logic executes at most once per session, regardless of how many times the method is called
- **SC-005**: All existing unit tests pass unchanged (mocking `_discover_all_derivatives` continues to work as before)
- **SC-006**: The `studies+derivatives.tsv` output is identical whether produced from cache or from a fresh scan
