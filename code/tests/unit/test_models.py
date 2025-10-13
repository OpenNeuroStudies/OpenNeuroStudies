"""Unit tests for Pydantic models."""

import pytest
from pydantic import ValidationError

from openneuro_studies.models import (
    DerivativeDataset,
    SourceDataset,
    StudyDataset,
    StudyState,
    generate_derivative_id,
    transition_state,
)


@pytest.mark.unit
@pytest.mark.ai_generated
class TestSourceDataset:
    """Tests for SourceDataset model."""

    def test_valid_source_dataset(self) -> None:
        """Test creating a valid source dataset."""
        source = SourceDataset(
            dataset_id="ds000001",
            url="https://github.com/OpenNeuroDatasets/ds000001",
            commit_sha="a" * 40,
            bids_version="1.10.1",
            license="CC0",
            authors=["John Doe", "Jane Smith"],
            subjects_num=16,
        )
        assert source.dataset_id == "ds000001"
        assert source.bids_version == "1.10.1"
        assert len(source.authors) == 2

    def test_invalid_dataset_id_pattern(self) -> None:
        """Test that invalid dataset ID pattern raises error."""
        with pytest.raises(ValidationError):
            SourceDataset(
                dataset_id="invalid",
                url="https://github.com/test/repo",
                commit_sha="a" * 40,
                bids_version="1.10.1",
            )

    def test_invalid_commit_sha_length(self) -> None:
        """Test that invalid commit SHA length raises error."""
        with pytest.raises(ValidationError):
            SourceDataset(
                dataset_id="ds000001",
                url="https://github.com/test/repo",
                commit_sha="abc123",
                bids_version="1.10.1",
            )

    def test_invalid_commit_sha_chars(self) -> None:
        """Test that non-hex commit SHA raises error."""
        with pytest.raises(ValidationError):
            SourceDataset(
                dataset_id="ds000001",
                url="https://github.com/test/repo",
                commit_sha="g" * 40,
                bids_version="1.10.1",
            )


@pytest.mark.unit
@pytest.mark.ai_generated
class TestDerivativeDataset:
    """Tests for DerivativeDataset model."""

    def test_valid_derivative_dataset(self) -> None:
        """Test creating a valid derivative dataset."""
        derivative = DerivativeDataset(
            dataset_id="ds006185",
            derivative_id="fmriprep-21.0.1",
            tool_name="fmriprep",
            version="21.0.1",
            url="https://github.com/OpenNeuroDerivatives/ds006185-fmriprep",
            commit_sha="abc123def456abc123def456abc123def456abc1",
            datalad_uuid="12345678-1234-5678-1234-567812345678",
            source_datasets=["ds006131"],
        )
        assert derivative.dataset_id == "ds006185"
        assert derivative.derivative_id == "fmriprep-21.0.1"
        assert derivative.uuid_prefix == "12345678"

    def test_uuid_prefix_extraction(self) -> None:
        """Test automatic UUID prefix extraction."""
        derivative = DerivativeDataset(
            dataset_id="ds000001",
            derivative_id="mriqc-23.0.0",
            tool_name="mriqc",
            version="23.0.0",
            url="https://github.com/OpenNeuroDerivatives/ds000001-mriqc",
            commit_sha="def456abc123def456abc123def456abc123def4",
            datalad_uuid="abcdefgh-1234-5678-1234-567812345678",
            source_datasets=["ds000001"],
        )
        assert derivative.uuid_prefix == "abcdefgh"

    def test_invalid_uuid_length(self) -> None:
        """Test that invalid UUID length raises error."""
        with pytest.raises(ValidationError):
            DerivativeDataset(
                dataset_id="ds000001",
                derivative_id="test-1.0",
                tool_name="test",
                version="1.0",
                url="https://github.com/test/test",
                commit_sha="abc123def456abc123def456abc123def456abc1",
                datalad_uuid="short-uuid",
                source_datasets=["ds000001"],
            )

    def test_requires_source_datasets(self) -> None:
        """Test that at least one source dataset is required."""
        with pytest.raises(ValidationError):
            DerivativeDataset(
                dataset_id="ds000001",
                derivative_id="test-1.0",
                tool_name="test",
                version="1.0",
                url="https://github.com/test/test",
                commit_sha="abc123def456abc123def456abc123def456abc1",
                datalad_uuid="12345678-1234-5678-1234-567812345678",
                source_datasets=[],
            )


@pytest.mark.unit
@pytest.mark.ai_generated
class TestGenerateDerivativeId:
    """Tests for generate_derivative_id function."""

    def test_unique_base_id(self) -> None:
        """Test generation with unique tool-version combination."""
        result = generate_derivative_id(
            tool_name="fmriprep",
            version="21.0.1",
            datalad_uuid="12345678-1234-5678-1234-567812345678",
            existing_ids=["mriqc-23.0.0"],
        )
        assert result == "fmriprep-21.0.1"

    def test_conflicting_id_adds_uuid(self) -> None:
        """Test UUID prefix is added when base ID conflicts."""
        result = generate_derivative_id(
            tool_name="fmriprep",
            version="21.0.1",
            datalad_uuid="abcdefgh-1234-5678-1234-567812345678",
            existing_ids=["fmriprep-21.0.1"],
        )
        assert result == "fmriprep-21.0.1-abcdefgh"


@pytest.mark.unit
@pytest.mark.ai_generated
class TestStudyDataset:
    """Tests for StudyDataset model."""

    def test_valid_study_dataset(self) -> None:
        """Test creating a valid study dataset."""
        source = SourceDataset(
            dataset_id="ds000001",
            url="https://github.com/OpenNeuroDatasets/ds000001",
            commit_sha="a" * 40,
            bids_version="1.10.1",
        )

        study = StudyDataset(
            study_id="study-ds000001",
            name="Balloon Analog Risk-taking Task",
            title="Study dataset for Balloon Analog Risk-taking Task",
            authors=["Yaroslav O. Halchenko"],
            bids_version="1.10.1",
            source_datasets=[source],
            github_url="https://github.com/OpenNeuroStudies/study-ds000001",
            state=StudyState.DISCOVERED,
        )
        assert study.study_id == "study-ds000001"
        assert study.state == StudyState.DISCOVERED
        assert len(study.source_datasets) == 1

    def test_requires_source_datasets(self) -> None:
        """Test that at least one source dataset is required."""
        with pytest.raises(ValidationError):
            StudyDataset(
                study_id="study-ds000001",
                name="Test",
                title="Test Study",
                authors=["Test Author"],
                bids_version="1.10.1",
                source_datasets=[],
                github_url="https://github.com/OpenNeuroStudies/study-ds000001",
                state=StudyState.DISCOVERED,
            )

    def test_invalid_study_id_pattern(self) -> None:
        """Test that invalid study ID pattern raises error."""
        source = SourceDataset(
            dataset_id="ds000001",
            url="https://github.com/OpenNeuroDatasets/ds000001",
            commit_sha="a" * 40,
            bids_version="1.10.1",
        )

        with pytest.raises(ValidationError):
            StudyDataset(
                study_id="invalid-id",
                name="Test",
                title="Test Study",
                authors=["Test"],
                bids_version="1.10.1",
                source_datasets=[source],
                github_url="https://github.com/OpenNeuroStudies/study-invalid-id",
                state=StudyState.DISCOVERED,
            )


@pytest.mark.unit
@pytest.mark.ai_generated
class TestStateTransition:
    """Tests for study state transition function."""

    def test_valid_transition(self) -> None:
        """Test valid state transition."""
        source = SourceDataset(
            dataset_id="ds000001",
            url="https://github.com/OpenNeuroDatasets/ds000001",
            commit_sha="a" * 40,
            bids_version="1.10.1",
        )

        study = StudyDataset(
            study_id="study-ds000001",
            name="Test",
            title="Test Study",
            authors=["Test"],
            bids_version="1.10.1",
            source_datasets=[source],
            github_url="https://github.com/OpenNeuroStudies/study-ds000001",
            state=StudyState.DISCOVERED,
        )

        updated = transition_state(study, StudyState.ORGANIZED)
        assert updated.state == StudyState.ORGANIZED

    def test_invalid_transition(self) -> None:
        """Test invalid state transition raises error."""
        source = SourceDataset(
            dataset_id="ds000001",
            url="https://github.com/OpenNeuroDatasets/ds000001",
            commit_sha="a" * 40,
            bids_version="1.10.1",
        )

        study = StudyDataset(
            study_id="study-ds000001",
            name="Test",
            title="Test Study",
            authors=["Test"],
            bids_version="1.10.1",
            source_datasets=[source],
            github_url="https://github.com/OpenNeuroStudies/study-ds000001",
            state=StudyState.DISCOVERED,
        )

        with pytest.raises(ValueError, match="Invalid transition"):
            transition_state(study, StudyState.VALIDATED)
