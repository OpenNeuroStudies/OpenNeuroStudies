# Makefile for OpenNeuroStudies common operations
#
# Prerequisites: openneuro-studies and snakemake must be in PATH
# (activate venv before running make, or install globally)

.PHONY: help discover organize extract metadata full-refresh clean

# Default number of cores for parallel operations
CORES ?= 8

help:
	@echo "OpenNeuroStudies common commands:"
	@echo ""
	@echo "  make discover        - Discover datasets from GitHub"
	@echo "  make organize        - Organize discovered datasets into studies"
	@echo "  make extract         - Extract metadata via Snakemake (with subdataset mgmt)"
	@echo "  make studies-tsv     - Update studies.tsv only"
	@echo "  make derivatives-tsv - Update studies+derivatives.tsv only"
	@echo "  make metadata        - Generate all metadata files"
	@echo "  make full-refresh    - Complete workflow (discover → organize → extract)"
	@echo ""
	@echo "  make extract-one STUDY=<name>  - Extract single study"
	@echo "  make clean           - Remove Snakemake cache and lock"
	@echo ""
	@echo "Options:"
	@echo "  CORES=N              - Number of parallel cores (default: 8)"
	@echo ""
	@echo "Examples:"
	@echo "  make full-refresh"
	@echo "  make extract CORES=4"
	@echo "  make extract-one STUDY=study-ds002685"

discover:
	openneuro-studies discover

organize:
	openneuro-studies organize

extract:
	snakemake -s code/workflow/Snakefile --cores $(CORES) --rerun-triggers params

studies-tsv:
	snakemake -s code/workflow/Snakefile --cores $(CORES) studies.tsv

derivatives-tsv:
	openneuro-studies metadata generate --derivatives-tsv study-*

metadata: extract derivatives-tsv

full-refresh: discover organize extract metadata
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
