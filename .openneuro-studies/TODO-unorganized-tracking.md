# Unorganized Datasets Tracking

## Overview

Some derivative datasets may be discovered but cannot be organized into study structures because their source raw datasets are not available in the current OpenNeuroStudies repository.

## Requirement

Create `.openneuro-studies/unorganized-datasets.json` to track derivatives that cannot be organized.

## File Structure

```json
{
  "derivatives_without_raw": [
    {
      "dataset_id": "ds000212-fmriprep",
      "derivative_id": "fmriprep-v20.2.0-abc123",
      "tool_name": "fmriprep",
      "version": "20.2.0",
      "source_datasets": ["ds000212"],
      "reason": "raw_dataset_not_found",
      "discovered_at": "2025-10-11T12:34:56Z",
      "notes": "Raw dataset ds000212 not in discovered-datasets.json"
    }
  ]
}
```

## Reason Codes

- `raw_dataset_not_found`: Source raw dataset(s) not in discovered datasets
- `invalid_source_reference`: SourceDatasets field cannot be parsed
- `multi_source_incomplete`: Multi-source derivative missing some source datasets

## Implementation

The `organize` command should:

1. Load `discovered-datasets.json`
2. For each derivative:
   - Check if all source datasets exist in discovered raw datasets
   - If yes: Organize into appropriate study
   - If no: Add to unorganized-datasets.json with reason
3. Save unorganized-datasets.json
4. Report counts of organized vs unorganized

## Example Output

```
Organizing 50 datasets:
  - 45 raw datasets
  - 3 derivative datasets (organized)
  - 2 derivative datasets (unorganized - see .openneuro-studies/unorganized-datasets.json)

✓ 48 datasets organized
⚠ 2 derivatives unorganized (missing source datasets)
```

## Testing

Integration test includes:
- `ds000001-mriqc`: Should organize into study-ds000001
- `ds000212-fmriprep`: Should be tracked as unorganized (ds000212 not in test set)

## Future Enhancements

- Periodic re-check of unorganized datasets when new raw datasets are discovered
- Command to manually organize specific unorganized derivatives
- Notification when unorganized derivatives can now be organized
