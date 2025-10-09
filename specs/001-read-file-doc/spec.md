# Feature Specification: OpenNeuroStudies Infrastructure Refactoring

**Feature Branch**: `001-read-file-doc`
**Created**: 2025-10-09
**Status**: Draft
**Input**: User description: "Read file doc/designs/1-initial-rf.md which provides details for what should be done, which doc/project_summary.md being an old project summary describing what was achieved under sourcedata/proto1/ - the initial prototype"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Dataset Discovery and Organization (Priority: P1)

As a neuroscience researcher, I need to navigate a unified collection of OpenNeuro raw and derivative datasets organized as BIDS study structures, so that I can quickly find and access both original data and processed derivatives for my research without manually traversing multiple repositories.

**Why this priority**: This is the foundation for the entire system. Without proper dataset discovery and organization, no other features can function. This directly addresses the core mission of making 1000+ datasets navigable and accessible.

**Independent Test**: Can be fully tested by verifying that the system discovers datasets from configured sources (OpenNeuroDatasets, OpenNeuroDerivatives, etc.), organizes them into study-{id} folders with proper sourcedata/ and derivatives/ structure, and generates a complete studies.tsv index file. All linked repositories should be associated with public URLs and tested to (still) exist.

**Acceptance Scenarios**:

1. **Given** multiple source repositories configured in sourcedata/ (openneuro, openneuro-derivatives, openfmri), **When** the discovery script runs, **Then** all datasets are identified with their URLs and current commit states extracted from .gitmodules and Git
2. **Given** a discovered raw dataset (e.g., ds000001), **When** the organization process runs, **Then** a study-ds000001 folder is created as a DataLad dataset without annex using `datalad create --no-annex -d . study-ds000001`, with sourcedata/raw/ linked as a git submodule to the original dataset, and the study dataset is linked as a git submodule in the top-level repository's .gitmodules with URL pointing to the configured GitHub organization (e.g., https://github.com/OpenNeuroStudies/study-ds000001)
3. **Given** derivative datasets (e.g. ds006185) matching a single raw dataset (e.g. ds006131), **When** organization process runs, **Then** derivatives are linked under derivatives/{toolname-version}/ as git submodules within the raw dataset (i.e ds006131).
4. **Given** a derivative dataset (e.g. ds006185) from OpenNeuroDatasets has a single raw source dataset, **When** organization process runs, **Then** we do NOT create a `study-{id}` for that dataset.
5. **Given** a derivative dataset with multiple SourceDatasets (e.g., ds006190) from OpenNeuroDatasets, **When** organization process runs, **Then** we do create a `study-{id}` for that dataset and all source datasets are linked under sourcedata/{original_id}/ without creating a single sourcedata/raw folder, and the entire `study-{id}` is linked under `derivatives/study-{id}` of each original raw dataset (e.g. ds006189, ds006185, ds006131 for ds006185)

---

### User Story 2 - Metadata Generation and Synchronization (Priority: P2)

As a dataset curator, I need automatically generated and synchronized metadata files (dataset_description.json, studies.tsv, studies_derivatives.tsv) for each study and the overall collection, so that I can track dataset provenance, licensing, versioning, and available derivatives without manual maintenance.

**Why this priority**: Metadata provides essential context for researchers and enables dashboard generation. It builds upon the organized structure from P1 but can be implemented and tested independently once the structure exists.

**Independent Test**: Can be tested by verifying that running the metadata generation script on an existing study produces correct and reproducible dataset_description.json with BIDS 1.10.1 study format, populates studies.tsv with accurate summary data, and creates studies_derivatives.tsv listing all available derivatives with versions.

**Acceptance Scenarios**:

1. **Given** a study folder with sourcedata/raw/, **When** metadata generation runs, **Then** dataset_description.json is created with DatasetType="study", Authors from git shortlog of the study dataset, Title prefixed with "Study dataset for ", and SourceDatasets referencing all sourcedata entries
2. **Given** multiple studies with varying metadata, **When** studies.tsv generation runs, **Then** the file contains study_id (e.g. study-ds000001), name, version, raw_version, bids_version, hed_version, license, authors, subjects_num, sessions_num, sessions_min, sessions_max, bold_num, t1w_num, t2w_num, bold_size, t1w_size, bold_size_max, bold_voxels, datatypes, derivative_ids (list of derivative identifiers), and bids_valid (where version is study dataset version, raw_version is version/tag of raw dataset if single source and released or "n/a" if multiple sources or no release)
2a. **Given** imaging metrics extraction is triggered (separate stage), **When** sparse data access via datalad-fuse or fsspec is established, **Then** bold_size, t1w_size, bold_size_max, and bold_voxels are populated in studies.tsv without full cloning
3. **Given** a study with 3 derivatives (e.g., fmriprep-21.0.1, mriqc-23.0.0, bids-validator), **When** studies_derivatives.tsv generation runs, **Then** 3 rows are created with study_id, derivative_id pairs, each listing tool name, version, size statistics from git annex info, execution metrics if available, and outdatedness (number of commits the processed raw dataset is behind current raw dataset version)
4. **Given** a raw dataset with version 1.0.5 and a derivative processed from version 1.0.3, **When** outdatedness calculation runs for studies_derivatives.tsv, **Then** the derivative's outdatedness column shows the commit count between 1.0.3 and 1.0.5 in the raw dataset
5. **Given** updates to source datasets or derivatives, **When** metadata sync runs, **Then** only affected studies are updated (incremental updates supported)

---

### User Story 3 - BIDS Validation Integration (Priority: P3)

As a data quality manager, I need automated BIDS validation results stored for each study dataset, so that I can quickly identify and address BIDS compliance issues across the entire collection without manually running validators.

**Why this priority**: Validation ensures data quality but depends on the organized structure and metadata from P1 and P2. It adds value by surfacing compliance issues but is not required for basic dataset access.

**Independent Test**: Can be tested by running BIDS validator on study datasets and verifying that both JSON and text outputs are stored under derivatives/bids-validator.{json,txt}, with validation status reflected in studies.tsv.

**Acceptance Scenarios**:

1. **Given** a newly created or modified study dataset, **When** validation is triggered, **Then** bids-validator-deno runs and outputs are saved to derivatives/bids-validator.json and derivatives/bids-validator.txt
2. **Given** validation results for multiple studies, **When** studies.tsv is updated, **Then** a bids-valid column reflects pass/fail/warning status for each study
3. **Given** a non-BIDS compliant dataset, **When** validation runs, **Then** errors are captured in the validation output files and the study is marked accordingly in studies.tsv

---

### Edge Cases

- What happens when a source repository is unreachable during discovery? System should cache last known state and log the error without blocking processing of other datasets. A logs/errors.tsv file at the top level should aggregate information about all errors with columns study_id, error_type, message.
- What happens when a dataset has malformed dataset_description.json? System should mark metadata fields as "n/a" and log validation warnings.
- What happens when two derivatives have the same tool and version? System should disambiguate using the first 8 letters of DataLad UUID from .datalad/config.
- What happens when SourceDatasets contains non-OpenNeuro references (DOIs, local paths)? System should preserve them in metadata but only process OpenNeuro datasets for linking.
- What happens when a derivative dataset points to a source dataset that doesn't exist in the collection? System should log the missing dependency and mark it in metadata as unavailable.
- What happens when versioning produces a date-based release (e.g., 0.20251009.0) on the same day? Subsequent releases increment the PATCH number (0.20251009.1, 0.20251009.2).
- What happens when a raw dataset has no git tags/releases? System should mark raw_version as "n/a" and fetch CHANGES file if available to determine version information without cloning.
- What happens when calculating outdatedness requires cloning? This operation should be performed sparingly as a separate batch process, with results cached to avoid repeated cloning.
- What happens when imaging metrics extraction (bold_size, bold_voxels) is needed? This requires sparse data access via datalad-fuse or fsspec as a separate operation stage, avoiding full clones while accessing NIfTI headers for size/dimension information.

## Requirements *(mandatory)*

### Functional Requirements

**Note on Naming Conventions**: All TSV column names MUST follow BIDS tabular file conventions (https://bids-specification.readthedocs.io/en/stable/common-principles.html#tabular-files) using snake_case (e.g., study_id, subject_count, session_min). Exception: When copying fields directly from JSON files that use CamelCase (e.g., BIDSVersion, SourceDatasets in dataset_description.json), preserve the original CamelCase naming in the TSV columns.

- **FR-001**: System MUST discover datasets from configured sources (OpenNeuroDatasets, OpenNeuroDerivatives, openfmri) without requiring full clones
- **FR-002**: System MUST extract dataset metadata (URLs, commit SHAs, dataset_description.json) using GitHub/Forgejo tree APIs
- **FR-003**: System MUST create study-{id} folder structures with sourcedata/ and derivatives/ subfolders
- **FR-004**: System MUST link datasets as git submodules using git config and git update-index without cloning
- **FR-005**: System MUST generate dataset_description.json for each study following BIDS 1.10.1 study dataset specification
- **FR-006**: System MUST populate SourceDatasets field referencing all sourcedata entries
- **FR-007**: System MUST generate GeneratedBy field with code provenance information
- **FR-008**: System MUST copy or collate ReferencesAndLinks, License, Keywords, Acknowledgements, and Funding from source datasets
- **FR-009**: System MUST generate studies.tsv with study_id, name, version, raw_version, bids_version, hed_version, license, authors, subjects_num, sessions_num, sessions_min, sessions_max, bold_num, t1w_num, t2w_num, bold_size, t1w_size, bold_size_max, bold_voxels, datatypes, derivative_ids, and bids_valid columns
- **FR-010**: System MUST generate studies_derivatives.tsv (tall format) at top level with study_id, derivative_id as lead columns, followed by tool name, version, UUID disambiguation, size statistics, execution metrics, outdatedness, and other status columns
- **FR-011**: System MUST generate studies.json and studies_derivatives.json describing TSV column purposes following BIDS sidecar conventions
- **FR-012**: System MUST support incremental updates (process specific studies, not all at once)
- **FR-013**: System MUST handle derivative datasets with multiple SourceDatasets by linking all sources under sourcedata/{original_id}/
- **FR-014**: System MUST identify derivative datasets from OpenNeuro with DatasetType=derivative and parse OpenNeuro dataset IDs from SourceDatasets URLs/DOIs
- **FR-015**: System MUST run bids-validator-deno on study datasets and store JSON and text outputs under derivatives/
- **FR-016**: System MUST be idempotent (running multiple times produces the same result)
- **FR-017**: System MUST cache API responses to avoid GitHub rate limits
- **FR-018**: System MUST support versioned releases using 0.YYYYMMDD.PATCH format
- **FR-019**: System MUST generate CHANGES file entries following CPAN::Changes::Spec format
- **FR-020**: System MUST operate on YAML specifications for sources rather than requiring hardcoded submodules
- **FR-021**: System MUST create each study-{id} as a DataLad dataset without annex using `datalad create --no-annex -d . study-{id}`
- **FR-022**: System MUST link each study-{id} repository as a git submodule in the top-level repository's .gitmodules
- **FR-023**: System MUST configure study submodule URLs to point to a configured GitHub organization (e.g., https://github.com/OpenNeuroStudies/study-ds000001)
- **FR-024**: System MUST publish study repositories to the configured GitHub organization for public access
- **FR-025**: System MUST extract raw dataset version from git tags without cloning when available
- **FR-026**: System MUST fetch CHANGES file to determine version when git tags are unavailable, avoiding full clone
- **FR-027**: System MUST populate studies.tsv version and raw_version columns (version for study dataset version, raw_version for source dataset version/tag or "n/a" if multiple sources or no release)
- **FR-028**: System MUST calculate derivative outdatedness as commit count between processed raw version and current raw version
- **FR-029**: System MUST populate studies_derivatives.tsv with outdatedness metric for each study-derivative pair
- **FR-030**: System MUST perform outdatedness calculations as a separate batch operation with caching to minimize cloning requirements
- **FR-031**: System MUST extract imaging modality file counts from raw datasets (bold_num, t1w_num, t2w_num) and populate studies.tsv
- **FR-032**: System MUST extract imaging data characteristics (bold_size, t1w_size, bold_size_max, bold_voxels) requiring sparse data access via datalad-fuse or fsspec
- **FR-033**: System MUST implement imaging metrics extraction as a separate operation stage with sparse access to avoid full dataset cloning
- **FR-034**: System MUST maintain top-level CHANGES file following CPAN::Changes::Spec format with UTF-8 encoding for repository version history, as required by BIDS specification for datasets

### Key Entities

- **Study Dataset**: A BIDS study folder (study-{id}) initialized as a git repository, containing sourcedata/ and derivatives/ with generated metadata following BIDS 1.10.1 study specification. Published to GitHub organization and linked as git submodule in top-level repository. Key attributes: study ID, title, authors, BIDS version, source datasets, derivative datasets, GitHub URL, raw dataset version.

- **Source Dataset**: A raw BIDS dataset from OpenNeuroDatasets, openfmri, or other configured sources. Linked as git submodule under sourcedata/raw/ or sourcedata/{id}/. Key attributes: dataset ID, URL, commit SHA, BIDS version, license, authors.

- **Derivative Dataset**: A processed dataset from OpenNeuroDerivatives or OpenNeuro derivatives. Linked as git submodule under derivatives/{toolname-version}/. Key attributes: tool name, version, DataLad UUID, size statistics, execution metrics, source datasets, processed raw version, outdatedness metric.

- **Source Specification**: YAML configuration defining dataset sources (GitHub organizations, regex patterns, DataLad collections). Key attributes: organization/URL, inclusion patterns, access credentials.

- **Metadata Index**: TSV files with JSON sidecars providing tabular overviews. studies.tsv (wide format) lists studies with derivative_ids column. studies_derivatives.tsv (tall format) has one row per study-derivative pair with study_id and derivative_id as lead columns, enabling detailed derivative tracking. Key attributes: column names, data types, descriptions, relationships. Dashboards can join or compose wide versions as needed.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: System successfully discovers and organizes 1000+ OpenNeuro datasets into BIDS study structures without manual intervention
- **SC-002**: Metadata generation completes for the full dataset collection in under 2 hours using cached API responses
- **SC-003**: 100% of organized studies have valid dataset_description.json files conforming to BIDS 1.10.1 study specification
- **SC-004**: studies.tsv provides complete overview with all required columns populated (or marked "n/a" where data unavailable)
- **SC-005**: Incremental updates process individual studies in under 30 seconds per study
- **SC-006**: Git submodule linking completes without cloning, reducing disk space and performance
- **SC-007**: Researchers can locate any dataset and its derivatives within 3 clicks/commands using studies.tsv index
- **SC-008**: BIDS validation results are available for all study datasets within 24 hours of organization
- **SC-009**: System handles API failures gracefully with less than 1% data loss using cached state
- **SC-010**: Release generation produces changelog entries that accurately summarize changes since previous release

## Assumptions

- GitHub API tokens are available via GITHUB_TOKEN environment variable with sufficient rate limits for batch operations
- DataLad is installed and functional for git-annex operations and provenance capture
- DataLad command-line commands have Python API counterparts in `datalad.api` package (e.g., `datalad.api.create`); convention is to import as `import datalad.api as dl`
- bids-validator-deno version 2.1.0 or later is available for BIDS validation
- Source datasets maintain stable commit histories (no force pushes that invalidate cached SHAs)
- BIDS specification 1.10.1 study dataset conventions are followed
- Most datasets have single source dataset; multi-source derivatives are minority cases
- Derivative naming follows {toolname-version} convention; UUID disambiguation needed only for same-version conflicts
- Execution metrics are available only for derivatives processed with con-duct/duct monitoring
- Calendar-based versioning (0.YYYYMMDD.PATCH) is acceptable for project releases
- GitHub organization (e.g., OpenNeuroStudies) is configured and accessible for publishing study repositories
- Study repositories can be published to GitHub using automation (push access configured)
- Outdatedness calculations may require temporary cloning in some cases where git log/tag APIs are insufficient
- Imaging metrics extraction (bold_size, t1w_size, max_bold_size, bold_voxels) requires sparse data access tools (datalad-fuse or fsspec) to avoid full cloning
- Sparse access operations are separate stages run less frequently than basic metadata generation

## Out of Scope

- Actual data processing or derivative generation (only linking existing derivatives)
- Real-time synchronization with OpenNeuro (batch updates on schedule or manual trigger)
- Web dashboard implementation (metadata enables dashboards but UI is separate feature)
- Modification of source datasets or derivatives (read-only linking)
- Support for non-git dataset sources (only git/DataLad repositories)
- Initial implementation will focus on local git repository creation; GitHub publishing automation is in scope but may be phased
- Deep analysis of derivative processing history requiring extensive cloning (will be batched and cached)
