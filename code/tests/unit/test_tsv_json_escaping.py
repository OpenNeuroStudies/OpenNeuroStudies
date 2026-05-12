"""Unit tests for TSV JSON escaping in studies+derivatives.tsv.

Verifies that JSON fields in TSV files are properly handled by csv.DictWriter
(tab-delimited) without escape-bombing, and round-trip correctly through
csv.DictReader.
"""

import csv
import json
import tempfile
from pathlib import Path


class TestTSVJSONEscaping:
    """Test that JSON in TSV round-trips correctly via csv module."""

    def test_json_roundtrip_via_csv_module(self):
        """JSON strings written with csv.DictWriter should round-trip via DictReader."""
        sample_data = {
            "MELODIC": 48,
            "about": 16,
            "aparcaseg": 112,
            "aroma": 48,
            "aseg": 112,
        }

        json_string = json.dumps(sample_data, separators=(",", ":"))
        expected = '{"MELODIC":48,"about":16,"aparcaseg":112,"aroma":48,"aseg":112}'
        assert json_string == expected

        # Write using csv.DictWriter (the current approach)
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tsv', newline="") as f:
            temp_path = Path(f.name)
            writer = csv.DictWriter(
                f,
                fieldnames=["study_id", "derivative_id", "descriptions"],
                delimiter="\t",
            )
            writer.writeheader()
            writer.writerow({
                "study_id": "study-ds000001",
                "derivative_id": "fMRIPrep-21.0.1",
                "descriptions": json_string,
            })

        # Read back with csv.DictReader — should get original JSON
        with open(temp_path, newline="") as f:
            reader = csv.DictReader(f, delimiter="\t")
            rows = list(reader)

        temp_path.unlink()

        assert len(rows) == 1
        assert rows[0]["study_id"] == "study-ds000001"
        assert rows[0]["descriptions"] == expected

        # Should be parseable as JSON
        parsed = json.loads(rows[0]["descriptions"])
        assert parsed == sample_data

    def test_json_with_escapechar_causes_bombing(self):
        """Demonstrate that escapechar='\\' causes escape bombing."""
        sample_data = {"test": "value"}
        json_string = json.dumps(sample_data, separators=(",", ":"))

        # Write with escapechar='\\' (the OLD broken way)
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tsv') as f:
            temp_path = Path(f.name)
            writer = csv.DictWriter(
                f,
                fieldnames=["data"],
                delimiter="\t",
                quoting=csv.QUOTE_NONE,
                escapechar="\\"  # THIS CAUSES ESCAPE BOMBING
            )
            writer.writeheader()
            writer.writerow({"data": json_string})

        # Read back
        with open(temp_path, 'r') as f:
            content = f.read()

        temp_path.unlink()

        lines = content.strip().split('\n')
        data_line = lines[1]

        # With escapechar='\\', the JSON gets escaped
        # This demonstrates the bug we fixed
        assert "\\" in data_line  # Escaping occurred

    def test_complex_json_roundtrip(self):
        """Complex JSON with nested structures round-trips correctly."""
        complex_data = {
            "about": 11,
            "basil": 506,
            "basilByTissueType": 22,
            "basilGM": 264,
            "preproc": 311,
            "summary": 22,
        }

        json_string = json.dumps(complex_data, separators=(",", ":"))

        # Write using csv.DictWriter
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tsv', newline="") as f:
            temp_path = Path(f.name)
            writer = csv.DictWriter(f, fieldnames=["descriptions"], delimiter="\t")
            writer.writeheader()
            writer.writerow({"descriptions": json_string})

        # Read back via csv.DictReader
        with open(temp_path, newline="") as f:
            reader = csv.DictReader(f, delimiter="\t")
            rows = list(reader)

        temp_path.unlink()

        descriptions_field = rows[0]["descriptions"]

        # Verify clean JSON roundtrip (no escape bombing)
        parsed = json.loads(descriptions_field)
        assert parsed == complex_data

        # No backslashes — csv module uses "" for quote escaping, not \"
        assert descriptions_field.count("\\") == 0

    def test_no_escape_bombing_on_repeated_writes(self):
        """Repeatedly writing and reading should not grow backslashes."""
        data = {"key": "value"}
        json_string = json.dumps(data, separators=(",", ":"))

        # Write → read → write → read ... should stay stable
        current = json_string
        for _ in range(5):
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tsv', newline="") as f:
                temp_path = Path(f.name)
                writer = csv.DictWriter(f, fieldnames=["data"], delimiter="\t")
                writer.writeheader()
                writer.writerow({"data": current})

            with open(temp_path, newline="") as f:
                reader = csv.DictReader(f, delimiter="\t")
                rows = list(reader)

            temp_path.unlink()
            current = rows[0]["data"]

        # After 5 round-trips, should still be the original
        assert current == json_string
        assert json.loads(current) == data

    def test_field_with_tab_is_properly_escaped(self):
        """A field value containing a tab character should be quoted."""
        # This shouldn't normally happen but is the safety net
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tsv', newline="") as f:
            temp_path = Path(f.name)
            writer = csv.DictWriter(
                f, fieldnames=["id", "value"], delimiter="\t"
            )
            writer.writeheader()
            writer.writerow({"id": "test", "value": "has\ttab"})

        # Read back — should correctly parse despite embedded tab
        with open(temp_path, newline="") as f:
            reader = csv.DictReader(f, delimiter="\t")
            rows = list(reader)

        temp_path.unlink()

        assert len(rows) == 1
        assert rows[0]["id"] == "test"
        assert rows[0]["value"] == "has\ttab"
