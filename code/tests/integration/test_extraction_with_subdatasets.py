"""Integration tests for extraction with subdataset management."""

import pytest
from pathlib import Path
from datalad.distribution.dataset import Dataset

from bids_studies.subdatasets import (
    extract_study_with_subdatasets,
    get_subdataset_states,
    TemporarySubdatasetInstall,
)


@pytest.mark.integration
def test_extraction_with_temporary_subdataset_install(tmp_path):
    """Test full extraction workflow with temporary subdataset installation.

    This test verifies:
    1. Starting with uninitialized subdataset
    2. Running extraction with subdataset management
    3. Subdataset is temporarily installed
    4. Subdataset is dropped after extraction
    5. Extracted metadata is correct (not all n/a)
    """
    # Skip if DataLad not available
    pytest.importorskip('datalad')

    # Create study structure
    study_path = tmp_path / "study-ds-test"
    sourcedata_path = study_path / "sourcedata" / "ds-test"

    # Create parent study dataset
    study_ds = Dataset(str(study_path))
    study_ds.create(force=True, annex=False)

    # Create sourcedata subdataset with minimal BIDS structure
    sourcedata_ds = Dataset(str(sourcedata_path))
    sourcedata_ds.create(force=True, annex=False)

    # Add minimal BIDS content to sourcedata
    desc_file = sourcedata_path / "dataset_description.json"
    desc_file.write_text('''{
        "Name": "Test Dataset",
        "BIDSVersion": "1.6.0",
        "Authors": ["Test Author"]
    }''')

    # Add a subject directory
    sub_dir = sourcedata_path / "sub-01"
    sub_dir.mkdir()

    # Save subdataset
    sourcedata_ds.save(message="Add minimal BIDS structure")

    # Install subdataset in parent (creates gitlink)
    study_ds.install(str(sourcedata_path), source=str(sourcedata_path))
    study_ds.save(message="Add sourcedata subdataset")

    # Create study dataset_description.json
    study_desc = study_path / "dataset_description.json"
    study_desc.write_text('''{
        "Name": "Study dataset for ds-test",
        "BIDSVersion": "1.6.0",
        "DatasetType": "study"
    }''')
    study_ds.save(message="Add study description")

    # Now uninstall the subdataset to simulate uninitialized state
    study_ds.drop(str(sourcedata_path), what='datasets', reckless='kill',
                  result_renderer='disabled')

    # Verify subdataset is not installed
    assert not Dataset(str(sourcedata_path)).is_installed()
    states_before = get_subdataset_states(study_path)
    assert states_before[sourcedata_path] == 'absent'

    # Run extraction with subdataset management
    result = extract_study_with_subdatasets(study_path, stage='basic')

    # Verify subdataset was dropped after extraction
    assert not Dataset(str(sourcedata_path)).is_installed()
    states_after = get_subdataset_states(study_path)
    assert states_after[sourcedata_path] == 'absent'

    # Verify extraction succeeded (got metadata from subdataset)
    assert result['study_id'] == 'study-ds-test'
    assert result['subjects_num'] == 1  # We created sub-01


@pytest.mark.integration
def test_preserves_already_installed_subdatasets(tmp_path):
    """Test that already-installed subdatasets are preserved."""
    pytest.importorskip('datalad')

    # Create study with installed subdataset
    study_path = tmp_path / "study-ds-preserve"
    sourcedata_path = study_path / "sourcedata" / "ds-preserve"

    study_ds = Dataset(str(study_path))
    study_ds.create(force=True, annex=False)

    sourcedata_ds = Dataset(str(sourcedata_path))
    sourcedata_ds.create(force=True, annex=False)

    # Add content
    desc_file = sourcedata_path / "dataset_description.json"
    desc_file.write_text('{"Name": "Test", "BIDSVersion": "1.6.0"}')
    sourcedata_ds.save(message="Add description")

    # Install subdataset
    study_ds.install(str(sourcedata_path), source=str(sourcedata_path))
    study_ds.save(message="Add sourcedata")

    # Verify subdataset IS installed before
    assert Dataset(str(sourcedata_path)).is_installed()

    # Use context manager
    with TemporarySubdatasetInstall(study_path) as (newly, existing):
        # Should recognize it's already installed
        assert len(newly) == 0
        assert len(existing) == 1
        assert sourcedata_path in existing

    # Verify subdataset is STILL installed after (preserved)
    assert Dataset(str(sourcedata_path)).is_installed()


@pytest.mark.integration
@pytest.mark.slow
def test_extraction_stages(tmp_path):
    """Test extraction at different stages with subdataset management."""
    pytest.importorskip('datalad')

    # Create study
    study_path = tmp_path / "study-ds-stages"
    sourcedata_path = study_path / "sourcedata" / "ds-stages"

    study_ds = Dataset(str(study_path))
    study_ds.create(force=True, annex=False)

    sourcedata_ds = Dataset(str(sourcedata_path))
    sourcedata_ds.create(force=True, annex=False)

    # Add BIDS structure
    desc_file = sourcedata_path / "dataset_description.json"
    desc_file.write_text('''{
        "Name": "Test Dataset",
        "BIDSVersion": "1.6.0",
        "Authors": ["Author One", "Author Two"]
    }''')

    # Add subject with session
    sub_ses_dir = sourcedata_path / "sub-01" / "ses-01"
    sub_ses_dir.mkdir(parents=True)

    sourcedata_ds.save(message="Add BIDS structure")

    study_ds.install(str(sourcedata_path), source=str(sourcedata_path))
    study_ds.save(message="Add sourcedata")

    # Uninstall for testing
    study_ds.drop(str(sourcedata_path), what='datasets', reckless='kill',
                  result_renderer='disabled')

    # Test basic stage
    result_basic = extract_study_with_subdatasets(study_path, stage='basic')
    assert result_basic['author_lead_raw'] == 'Author One'
    assert result_basic['author_senior_raw'] == 'Author Two'

    # Verify dropped after each extraction
    assert not Dataset(str(sourcedata_path)).is_installed()
