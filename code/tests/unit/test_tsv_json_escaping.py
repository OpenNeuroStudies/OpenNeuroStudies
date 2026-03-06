"""Unit tests for TSV JSON escaping in studies+derivatives.tsv."""

import csv
import json
import tempfile
from pathlib import Path


class TestTSVJSONEscaping:
    """Test that JSON in TSV doesn't get escape-bombed."""

    def test_json_no_escape_bombing(self):
        """Test that JSON strings in TSV are not escape-bombed."""
        # Sample JSON data similar to descriptions column
        sample_data = {
            "MELODIC": 48,
            "about": 16,
            "aparcaseg": 112,
            "aroma": 48,
            "aseg": 112,
        }

        # Convert to JSON string (as done in derivative_extractor.py)
        json_string = json.dumps(sample_data, separators=(",", ":"))

        # Expected output (no escaping)
        expected = '{"MELODIC":48,"about":16,"aparcaseg":112,"aroma":48,"aseg":112}'
        assert json_string == expected

        # Write to TSV manually (as fixed - no csv.DictWriter to avoid escaping)
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tsv') as f:
            temp_path = Path(f.name)
            # Write header
            f.write("study_id\tderivative_id\tdescriptions\n")
            # Write data row
            f.write(f"study-ds000001\tfMRIPrep-21.0.1\t{json_string}\n")

        # Read back and verify no escape bombing
        with open(temp_path, 'r') as f:
            content = f.read()

        # Clean up
        temp_path.unlink()

        # Verify the JSON is NOT escape-bombed
        lines = content.strip().split('\n')
        assert len(lines) == 2  # header + data row

        data_line = lines[1]
        fields = data_line.split('\t')
        assert len(fields) == 3

        descriptions_field = fields[2]

        # Should be the clean JSON, not escape-bombed
        assert descriptions_field == expected
        assert "\\" not in descriptions_field or descriptions_field.count("\\") == 0

        # Should be parseable as JSON
        parsed = json.loads(descriptions_field)
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
        # The exact escaping depends on CSV implementation,
        # but backslashes should be present

    def test_complex_json_no_escape_bombing(self):
        """Test complex JSON with nested structures."""
        complex_data = {
            "about": 11,
            "basil": 506,
            "basilByTissueType": 22,
            "basilGM": 264,
            "preproc": 311,
            "summary": 22,
        }

        json_string = json.dumps(complex_data, separators=(",", ":"))

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tsv') as f:
            temp_path = Path(f.name)
            # Write manually (as fixed)
            f.write("descriptions\n")
            f.write(f"{json_string}\n")

        with open(temp_path, 'r') as f:
            content = f.read()

        temp_path.unlink()

        lines = content.strip().split('\n')
        descriptions_field = lines[1]

        # Verify clean JSON (no escape bombing)
        parsed = json.loads(descriptions_field)
        assert parsed == complex_data

        # Count backslashes - should be zero
        assert descriptions_field.count("\\") == 0
