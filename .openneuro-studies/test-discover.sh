#!/bin/bash
# Helper script to discover the 6 MVP test datasets
# Usage: .openneuro-studies/test-discover.sh

set -e

# Ensure GITHUB_TOKEN is set
if [ -z "$GITHUB_TOKEN" ]; then
    echo "Error: GITHUB_TOKEN environment variable is not set"
    echo "Please set your GitHub personal access token:"
    echo "  export GITHUB_TOKEN='your_token_here'"
    exit 1
fi

# Run discovery with test filter
echo "Discovering 6 MVP test datasets..."
echo ""

openneuro-studies discover \
    --test-filter ds000001 \
    --test-filter ds000010 \
    --test-filter ds006131 \
    --test-filter ds006185 \
    --test-filter ds006189 \
    --test-filter ds006190 \
    --output .openneuro-studies/discovered-datasets.json

echo ""
echo "Discovery complete! Results saved to .openneuro-studies/discovered-datasets.json"
echo ""
echo "Test datasets:"
echo "  Raw datasets: ds000001, ds000010, ds006131"
echo "  Derivatives:  ds006185, ds006189, ds006190"
echo ""
echo "To view results:"
echo "  cat .openneuro-studies/discovered-datasets.json | jq"
