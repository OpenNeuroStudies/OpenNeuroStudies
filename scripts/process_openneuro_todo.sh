#!/bin/bash
# Process OpenNeuro datasets from TODO list
#
# This script:
# 1. Discovers datasets from openneuro_datasets_todo.tsv
# 2. Organizes them into study-* directories
# 3. Extracts imaging metadata for studies missing it

set -e  # Exit on error
set -u  # Exit on undefined variable

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*"
}

# Configuration
TODO_FILE="${TODO_FILE:-scripts/openneuro_datasets_todo.tsv}"
STUDIES_TSV="studies.tsv"
JOBS="${JOBS:-4}"  # Parallel jobs for metadata extraction

# Check required files
if [ ! -f "$TODO_FILE" ]; then
    log_error "TODO file not found: $TODO_FILE"
    log_info "Create it with dataset IDs (one per line or TSV with 'dataset_id' column)"
    exit 1
fi

# Step 1: Discover datasets from TODO list
log_info "Step 1: Discovering datasets from $TODO_FILE"

# Read dataset IDs from TODO file (supports both plain list and TSV with header)
dataset_ids=()
if head -1 "$TODO_FILE" | grep -q "dataset_id"; then
    # TSV with header
    log_info "Detected TSV format with header"
    while IFS=$'\t' read -r dataset_id rest; do
        if [[ "$dataset_id" != "dataset_id" ]] && [[ -n "$dataset_id" ]]; then
            dataset_ids+=("$dataset_id")
        fi
    done < "$TODO_FILE"
else
    # Plain list (one ID per line)
    log_info "Detected plain list format"
    while read -r dataset_id; do
        # Skip empty lines and comments
        [[ -z "$dataset_id" || "$dataset_id" =~ ^[[:space:]]*# ]] && continue
        dataset_ids+=("$dataset_id")
    done < "$TODO_FILE"
fi

if [ ${#dataset_ids[@]} -eq 0 ]; then
    log_warn "No dataset IDs found in $TODO_FILE"
else
    log_info "Found ${#dataset_ids[@]} datasets to discover"

    # Discover each dataset
    for dataset_id in "${dataset_ids[@]}"; do
        log_info "Discovering $dataset_id..."
        if openneuro-studies discover --dataset-id "$dataset_id"; then
            log_info "  ✓ $dataset_id discovered"
        else
            log_warn "  ✗ $dataset_id discovery failed (may already exist)"
        fi
    done
fi

# Step 2: Organize all discovered datasets
log_info "Step 2: Organizing discovered datasets"

if openneuro-studies organize; then
    log_info "  ✓ Organization complete"
else
    log_error "  ✗ Organization failed"
    exit 1
fi

# Step 3: Extract imaging metadata for studies missing it
log_info "Step 3: Extracting imaging metadata for studies missing it"

if [ ! -f "$STUDIES_TSV" ]; then
    log_warn "studies.tsv not found, generating for all studies"
    openneuro-studies metadata generate --stage imaging --jobs "$JOBS"
    exit 0
fi

# Find studies missing imaging stats (bold_voxels is "n/a" or empty)
# Assumes bold_voxels is column 24 (adjust if needed)
log_info "Checking which studies need imaging extraction..."

studies_needing_imaging=()
while IFS=$'\t' read -r study_id rest; do
    # Skip header
    [[ "$study_id" == "study_id" ]] && continue

    # Check if this line has imaging stats
    # We'll check if bold_voxels (column 24) is n/a or empty
    bold_voxels=$(echo -e "$study_id\t$rest" | cut -f24)

    if [[ "$bold_voxels" == "n/a" || -z "$bold_voxels" ]]; then
        studies_needing_imaging+=("$study_id")
    fi
done < "$STUDIES_TSV"

if [ ${#studies_needing_imaging[@]} -eq 0 ]; then
    log_info "All studies already have imaging metadata ✓"
    exit 0
fi

log_info "Found ${#studies_needing_imaging[@]} studies needing imaging extraction:"
printf "  - %s\n" "${studies_needing_imaging[@]}"

# Extract imaging metadata in parallel
log_info "Extracting imaging metadata (parallel jobs: $JOBS)..."

if openneuro-studies metadata generate \
    --stage imaging \
    --jobs "$JOBS" \
    "${studies_needing_imaging[@]}"; then
    log_info "  ✓ Imaging metadata extraction complete"
else
    log_error "  ✗ Imaging metadata extraction failed"
    exit 1
fi

# Summary
log_info "="
log_info "Processing complete!"
log_info "  Discovered: ${#dataset_ids[@]} datasets"
log_info "  Updated imaging stats: ${#studies_needing_imaging[@]} studies"
log_info "="
