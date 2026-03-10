# Makefile for OpenNeuroStudies common operations
#
# Prerequisites: openneuro-studies and snakemake must be in PATH
# (activate venv before running make, or install globally)

.PHONY: help discover organize extract metadata full-refresh refresh studies-init clean full-clean analyze-state test-expectations

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
	@echo "  make test-expectations          - Validate metadata for known datasets"
	@echo "  make clean                      - Remove Snakemake cache and lock"
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
	datalad get -s origin .openneuro-studies study-ds00*
	@echo "Initializing sourcedata and derivatives subdatasets within each study..."
	@for study in study-ds00*/; do \
		if [ -d "$$study" ]; then \
			echo "  $$study"; \
			datalad get -n -r -R1 -d "$$study" "$${study}sourcedata" "$${study}derivatives" || true; \
		fi; \
	done
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
	@snakemake -s code/workflow/Snakefile --cores $(CORES) --rerun-triggers params || \
		(echo ""; \
		 echo "ERROR: Snakemake failed. If directory is locked, run: make unlock"; \
		 exit 1)

studies-tsv:
	@snakemake -s code/workflow/Snakefile --cores $(CORES) studies.tsv || \
		(echo ""; \
		 echo "ERROR: Snakemake failed. If directory is locked, check:"; \
		 echo "  Lock files: .snakemake/locks/"; \
		 find .snakemake/locks -type f 2>/dev/null | sed 's/^/    /'; \
		 echo ""; \
		 echo "To unlock, run: make unlock"; \
		 exit 1)

derivatives-tsv:
	openneuro-studies metadata generate --derivatives-tsv study-*

metadata-tsv: studies-tsv derivatives-tsv

metadata: extract metadata-tsv

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

# Unlock Snakemake directory
unlock:
	@echo "Unlocking Snakemake directory..."
	@if [ -d .snakemake/locks ]; then \
		echo "Found lock files:"; \
		find .snakemake/locks -type f | sed 's/^/  /'; \
	fi
	@snakemake -s code/workflow/Snakefile --unlock
	@echo "✓ Unlocked"

# Clean Snakemake artifacts
clean: unlock
	@echo "✓ Snakemake lock removed"

# Full clean - remove all intermediate files
full-clean: unlock
	@echo "Removing all Snakemake intermediate files..."
	@if [ -d .snakemake/extracted ]; then \
		rm -rf .snakemake/extracted/*.json && echo "  ✓ Removed extracted/*.json"; \
	fi
	@if [ -d .snakemake/prov ]; then \
		rm -rf .snakemake/prov/ && echo "  ✓ Removed prov/"; \
	fi
	@echo "✓ Full clean complete"

# Analyze extraction state
analyze-state:
	@echo "Analyzing extraction state..."
	@python3 code/tests-adhoc/analyze_extraction_state.py

# Test that metadata meets expectations for known datasets
test-expectations:
	@echo "Running metadata extraction expectations tests..."
	@bash code/tests/test-expectations.sh
