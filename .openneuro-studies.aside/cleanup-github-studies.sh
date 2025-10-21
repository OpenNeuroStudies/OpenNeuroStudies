#!/bin/bash
# Cleanup script to remove study repositories from GitHub organization
# Usage: .openneuro-studies/cleanup-github-studies.sh [--org ORGANIZATION] [--dry-run]
#
# This script is useful for:
# - Cleaning up after integration tests
# - Removing test study repositories
# - Resetting the GitHub organization
#
# WARNING: This is DESTRUCTIVE! Use with caution.

set -e

# Default values
ORG="OpenNeuroStudies"
DRY_RUN=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --org)
            ORG="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --help)
            echo "Usage: $0 [--org ORGANIZATION] [--dry-run]"
            echo ""
            echo "Remove all study-* repositories from GitHub organization"
            echo ""
            echo "Options:"
            echo "  --org ORGANIZATION    GitHub organization name (default: OpenNeuroStudies)"
            echo "  --dry-run            Show what would be deleted without deleting"
            echo "  --help               Show this help message"
            echo ""
            echo "Environment:"
            echo "  GITHUB_TOKEN         Required: GitHub personal access token with repo:delete scope"
            echo ""
            echo "Examples:"
            echo "  # Dry run to see what would be deleted"
            echo "  $0 --dry-run"
            echo ""
            echo "  # Delete from specific organization"
            echo "  $0 --org MyTestOrg"
            echo ""
            echo "  # Delete for real"
            echo "  $0"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Check for GITHUB_TOKEN
if [ -z "$GITHUB_TOKEN" ]; then
    echo "Error: GITHUB_TOKEN environment variable is not set"
    echo "Please set your GitHub personal access token with repo:delete scope:"
    echo "  export GITHUB_TOKEN='your_token_here'"
    exit 1
fi

# Check for gh CLI
if ! command -v gh &> /dev/null; then
    echo "Error: GitHub CLI (gh) is not installed"
    echo "Install from: https://cli.github.com/"
    exit 1
fi

echo "================================================"
echo "GitHub Study Repository Cleanup"
echo "================================================"
echo "Organization: $ORG"
echo "Dry run: $DRY_RUN"
echo ""

# Authenticate gh CLI with token
export GH_TOKEN="$GITHUB_TOKEN"

# List all repositories in the organization
echo "Fetching repositories from $ORG..."
REPOS=$(gh repo list "$ORG" --limit 1000 --json name --jq '.[].name')

# Filter to study-* repositories
STUDY_REPOS=$(echo "$REPOS" | grep -E '^study-ds[0-9]+$' || true)

if [ -z "$STUDY_REPOS" ]; then
    echo "No study repositories found in $ORG"
    exit 0
fi

# Count repositories
REPO_COUNT=$(echo "$STUDY_REPOS" | wc -l)
echo "Found $REPO_COUNT study repositories:"
echo "$STUDY_REPOS" | sed 's/^/  - /'
echo ""

if [ "$DRY_RUN" = true ]; then
    echo "DRY RUN: Would delete the above repositories"
    echo "Run without --dry-run to actually delete them"
    exit 0
fi

# Confirm deletion
echo "WARNING: This will permanently delete $REPO_COUNT repositories!"
echo "This action CANNOT be undone."
echo ""
read -p "Are you sure you want to continue? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Aborted."
    exit 0
fi

echo ""
echo "Deleting repositories..."

# Delete each repository
DELETED=0
FAILED=0

for REPO in $STUDY_REPOS; do
    echo -n "Deleting $ORG/$REPO... "
    if gh repo delete "$ORG/$REPO" --yes 2>/dev/null; then
        echo "✓"
        ((DELETED++))
    else
        echo "✗ (failed)"
        ((FAILED++))
    fi
done

echo ""
echo "================================================"
echo "Cleanup complete"
echo "================================================"
echo "Deleted: $DELETED repositories"
if [ $FAILED -gt 0 ]; then
    echo "Failed:  $FAILED repositories"
fi
echo ""
echo "Next steps:"
echo "  1. Remove local study-* directories if needed"
echo "  2. Re-run: openneuro-studies organize"
