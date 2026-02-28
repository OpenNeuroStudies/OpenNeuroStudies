# Makefile for OpenNeuroStudies common operations
#
# Prerequisites: openneuro-studies and snakemake must be in PATH
# (activate venv before running make, or install globally)

.PHONY: help discover organize extract metadata full-refresh refresh studies-init clean

# Default number of cores for parallel operations
CORES ?= 8

help:
	@echo "OpenNeuroStudies common commands:"
	@echo ""
	@echo "Fresh Clone Workflow:"
	@echo "  make studies-init    - Initialize study-* subdatasets (required after clone)"
	@echo "  make refresh         - Refresh existing studies only (no discovery)"
	@echo ""
	@echo "Discovery Workflow:"
	@echo "  make discover        - Discover datasets from GitHub"
	@echo "  make organize        - Organize discovered datasets into studies"
	@echo "  make full-refresh    - Complete workflow (discover → organize → extract)"
	@echo ""
	@echo "Metadata Extraction:"
	@echo "  make extract         - Extract metadata via Snakemake (with subdataset mgmt)"
	@echo "  make studies-tsv     - Update studies.tsv only"
	@echo "  make derivatives-tsv - Update studies+derivatives.tsv only"
	@echo "  make metadata        - Generate all metadata files"
	@echo ""
	@echo "Utilities:"
	@echo "  make extract-one STUDY=<name>  - Extract single study"
	@echo "  make clean           - Remove Snakemake cache and lock"
	@echo ""
	@echo "Options:"
	@echo "  CORES=N              - Number of parallel cores (default: 8)"
	@echo ""
	@echo "Examples:"
	@echo "  # After fresh clone:"
	@echo "  make studies-init && make refresh"
	@echo ""
	@echo "  # Discover new datasets:"
	@echo "  make full-refresh"
	@echo ""
	@echo "  # Update existing studies:"
	@echo "  make refresh CORES=4"
	@echo "  make extract-one STUDY=study-ds002685"

# Initialize study subdatasets (required after fresh clone)
studies-init:
	@echo "Initializing study-* subdatasets..."
	git submodule update --init study-*
	@echo "✓ Study subdatasets initialized"

# Refresh existing studies only (no discovery)
# This organizes only existing study-* directories (incremental update)
refresh:
	@echo "Refreshing existing studies..."
	openneuro-studies organize study-*
	$(MAKE) extract metadata
	@echo "✓ Refresh complete"

# Discovery workflow
discover:
	openneuro-studies discover

organize:
	openneuro-studies organize

# Extraction workflow
extract:
	snakemake -s code/workflow/Snakefile --cores $(CORES) --rerun-triggers params

studies-tsv:
	snakemake -s code/workflow/Snakefile --cores $(CORES) studies.tsv

derivatives-tsv:
	openneuro-studies metadata generate --derivatives-tsv study-*

metadata: extract derivatives-tsv

# Complete workflow (discover new + organize + extract)
full-refresh: studies-init discover organize extract metadata
	@echo "✓ Full refresh complete"

# Extract single study (usage: make extract-one STUDY=study-ds000001)
extract-one:
ifndef STUDY
	@echo "Error: STUDY parameter required"
	@echo "Usage: make extract-one STUDY=study-ds000001"
	@exit 1
endif
	snakemake -s code/workflow/Snakefile --cores 1 \
		.snakemake/extracted/$(STUDY).json

# Clean Snakemake artifacts
clean:
	snakemake -s code/workflow/Snakefile --unlock || true
	@echo "✓ Snakemake lock removed"
