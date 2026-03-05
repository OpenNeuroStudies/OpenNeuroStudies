#!/bin/bash
# Test expectations for metadata extraction
# Validates that known datasets have expected metadata values

set -e

FAILED=0

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "Testing metadata extraction expectations..."
echo ""

# Helper functions
check_value() {
    local file=$1
    local study=$2
    local column=$3
    local expected=$4
    local description=$5

    # Get column number
    local col_num=$(head -1 "$file" | tr '\t' '\n' | grep -n "^${column}$" | cut -d: -f1)

    if [ -z "$col_num" ]; then
        echo -e "${RED}✗${NC} Column '$column' not found in $file"
        ((FAILED++))
        return
    fi

    # Get value
    local actual=$(grep "^${study}" "$file" | cut -f"$col_num")

    if [ "$actual" == "$expected" ]; then
        echo -e "${GREEN}✓${NC} $description"
    elif [ "$actual" == "n/a" ]; then
        echo -e "${RED}✗${NC} $description - got 'n/a' (expected: $expected)"
        ((FAILED++))
    else
        echo -e "${YELLOW}⚠${NC} $description - got '$actual' (expected: $expected)"
    fi
}

check_not_na() {
    local file=$1
    local study=$2
    local column=$3
    local description=$4

    local col_num=$(head -1 "$file" | tr '\t' '\n' | grep -n "^${column}$" | cut -d: -f1)

    if [ -z "$col_num" ]; then
        echo -e "${RED}✗${NC} Column '$column' not found in $file"
        ((FAILED++))
        return
    fi

    local actual=$(grep "^${study}" "$file" | cut -f"$col_num")

    if [ "$actual" != "n/a" ] && [ "$actual" != "" ]; then
        echo -e "${GREEN}✓${NC} $description (value: $actual)"
    else
        echo -e "${RED}✗${NC} $description - is 'n/a' or empty"
        ((FAILED++))
    fi
}

check_numeric() {
    local file=$1
    local study=$2
    local column=$3
    local description=$4

    local col_num=$(head -1 "$file" | tr '\t' '\n' | grep -n "^${column}$" | cut -d: -f1)

    if [ -z "$col_num" ]; then
        echo -e "${RED}✗${NC} Column '$column' not found in $file"
        ((FAILED++))
        return
    fi

    local actual=$(grep "^${study}" "$file" | cut -f"$col_num")

    # Check if it's a number (including decimals and scientific notation)
    if [[ "$actual" =~ ^[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]+)?$ ]]; then
        echo -e "${GREEN}✓${NC} $description (value: $actual)"
    else
        echo -e "${RED}✗${NC} $description - not numeric (got: '$actual')"
        ((FAILED++))
    fi
}

# Test studies.tsv expectations
echo "=== Testing studies.tsv ==="

if [ ! -f "studies.tsv" ]; then
    echo -e "${RED}✗${NC} studies.tsv not found"
    exit 1
fi

# study-ds000001 expectations (well-known dataset)
check_value "studies.tsv" "study-ds000001" "subjects_num" "16" "ds000001 has 16 subjects"
check_value "studies.tsv" "study-ds000001" "bold_num" "48" "ds000001 has 48 BOLD files"
check_value "studies.tsv" "study-ds000001" "bold_tasks" "balloonanalogrisktask" "ds000001 task is balloonanalogrisktask"
check_numeric "studies.tsv" "study-ds000001" "bold_voxels" "ds000001 bold_voxels is numeric"
check_numeric "studies.tsv" "study-ds000001" "bold_timepoints" "ds000001 bold_timepoints is numeric"

# study-ds006131 expectations (session-based dataset)
check_value "studies.tsv" "study-ds006131" "subjects_num" "18" "ds006131 has 18 subjects"
check_value "studies.tsv" "study-ds006131" "sessions_num" "106" "ds006131 has 106 sessions"
check_value "studies.tsv" "study-ds006131" "bold_num" "480" "ds006131 has 480 BOLD files"
check_value "studies.tsv" "study-ds006131" "bold_tasks" "bao,rat,rest" "ds006131 tasks are bao,rat,rest"
check_numeric "studies.tsv" "study-ds006131" "bold_voxels" "ds006131 bold_voxels is numeric"

echo ""
echo "=== Testing studies+derivatives.tsv ==="

if [ ! -f "studies+derivatives.tsv" ]; then
    echo -e "${RED}✗${NC} studies+derivatives.tsv not found"
    exit 1
fi

# Check that derivatives have real metadata, not all n/a
check_not_na "studies+derivatives.tsv" "study-ds000001\tMRIQC" "file_count" "ds000001 MRIQC has file_count"
check_not_na "studies+derivatives.tsv" "study-ds000001\tfMRIPrep" "file_count" "ds000001 fMRIPrep has file_count"
check_not_na "studies+derivatives.tsv" "study-ds000001\tfMRIPrep" "tasks_processed" "ds000001 fMRIPrep has tasks_processed"
check_not_na "studies+derivatives.tsv" "study-ds000001\tfMRIPrep" "template_spaces" "ds000001 fMRIPrep has template_spaces"

# Check numeric sizes (not humanized strings)
check_numeric "studies+derivatives.tsv" "study-ds000001\tfMRIPrep" "size_annexed" "ds000001 fMRIPrep size_annexed is numeric"
check_numeric "studies+derivatives.tsv" "study-ds000001\tfMRIPrep" "file_count" "ds000001 fMRIPrep file_count is numeric"

# Check JSON formatting (no Python repr artifacts)
echo ""
echo "=== Checking JSON formatting ==="
if grep -q '""' studies+derivatives.tsv 2>/dev/null; then
    echo -e "${RED}✗${NC} Found Python repr artifacts (doubled quotes) in studies+derivatives.tsv"
    ((FAILED++))
else
    echo -e "${GREEN}✓${NC} No Python repr artifacts in JSON columns"
fi

echo ""
echo "=========================================="
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All expectations passed!${NC}"
    exit 0
else
    echo -e "${RED}✗ $FAILED expectation(s) failed${NC}"
    exit 1
fi
