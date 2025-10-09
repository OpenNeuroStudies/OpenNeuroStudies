# OpenNeuroStudies Project Summary

## Overview

The **OpenNeuroStudies** project is a DataLad super-dataset that reorganizes OpenNeuro datasets into [BIDS "study"](https://bids-specification.readthedocs.io/en/stable/common-principles.html#study-dataset) folder structures.
It transforms flat OpenNeuro dataset collections into hierarchical BIDS study datasets that group raw BIDS data from OpenNeuroDatasets with their corresponding derivative datasets from OpenNeuroDerivatives.

## Purpose

The project creates a unified, hierarchical view of the entire OpenNeuro ecosystem, making it easier to navigate and work with both raw and derivative datasets in a standardized BIDS study format.

## Script Functionality ([code/layout_as_studies.sh]())

The main script performs the following operations:

### 1. Dataset Reorganization
- Transforms `ds0XXXXX` folders into `study-ds0XXXXX` structures
- Processes datasets individually or in batch

### 2. Directory Structure
Creates for each study:
- `sourcedata/raw/` - Contains the original raw BIDS dataset
- `derivatives/` - Contains derivative datasets (e.g., fmriprep, mriqc outputs)

### 3. Metadata Generation
- **dataset_description.json**: Updates with `DatasetType: "study"` and BIDS 1.10.1 compliance
  - Preserves original metadata as `BIDSRawVersion` and `BIDSRawAuthors`
- **derivatives.tsv**: Lists all derivatives with their versions for each study
- **studies.tsv**: Master file with overview of all studies including:
  - Study ID, Name, BIDS version, License, Authors, and available derivatives

### 4. GitHub Integration
Fetches metadata from:
- OpenNeuroDatasets repositories for raw data
- OpenNeuroDerivatives repositories for processed data
- Uses GitHub API with caching mechanism to avoid rate limits

## Current Structure

- **~1000+ study folders** (`study-ds000001` through `study-ds005242`)
- Each study folder contains standardized BIDS study structure
- Git submodules link to derivative repositories (499KB `.gitmodules` file)
- Master `studies.tsv` (316KB) provides tabular overview of all studies

## Key Features

### Caching
- Uses `scratch/cache/` directory for GitHub API responses
- Reduces API calls and improves performance

### Error Handling
- Gracefully handles non-BIDS datasets
- Marks incomplete datasets with "n/a" in studies.tsv

### Version Tracking
- Derivative folders named with tool versions (e.g., `fmriprep-21.0.1`)
- Supports multiple versions of the same derivative tool

### DataLad Integration
- Maintains DataLad metadata in submodules
- Preserves dataset IDs and URLs for reproducibility

## Technical Details

### Dependencies
- Bash shell
- Git and git submodules
- curl for API requests
- jq for JSON processing
- Python for JSON manipulation
- GitHub token (via `$GITHUB_TOKEN` environment variable)

### Workflow
1. Fetches dataset metadata from GitHub repositories
2. Reorganizes directory structure using git mv
3. Updates metadata files to BIDS study format
4. Links derivatives as git submodules
5. Generates summary tables for easy navigation

## Benefits

- **Standardization**: Uniform BIDS study structure across all datasets
- **Integration**: Raw and derivative data co-located in logical hierarchy
- **Discovery**: Easy navigation through studies.tsv index
- **Reproducibility**: Git submodules maintain exact versions and sources
- **Efficiency**: Cached API calls reduce processing time
