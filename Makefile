# Blueprint — Development Makefile

.PHONY: test-contracts test-blocks test-all test-install help

# Use python3 by default; override with: make PYTHON=python test-all
PYTHON ?= python3

# Prevent GPU/network access during tests
export CUDA_VISIBLE_DEVICES  ?=
export TRANSFORMERS_OFFLINE  ?= 1
export HF_HUB_OFFLINE        ?= 1

# Install test dependencies
test-install:
	$(PYTHON) -m pip install -r backend/requirements.txt
	$(PYTHON) -m pip install -r backend/requirements-test.txt

# Run all contract tests (validate, execute, compile)
test-contracts:
	$(PYTHON) -m pytest backend/tests/test_contract_validate.py \
		backend/tests/test_contract_execute.py \
		backend/tests/test_contract_compile.py \
		-v --timeout=60

# Run block I/O and coverage tests
test-blocks:
	$(PYTHON) -m pytest backend/tests/test_block_io.py \
		backend/tests/test_block_coverage.py \
		-v --timeout=120

# Run all contract + block tests together
test-all: test-contracts test-blocks

help:
	@echo "Available targets:"
	@echo "  test-install    Install test dependencies"
	@echo "  test-contracts  Run contract validation, execution, and compile tests"
	@echo "  test-blocks     Run block I/O verification and block coverage tests"
	@echo "  test-all        Run all contract and block tests"
	@echo ""
	@echo "Override Python: make PYTHON=python3.11 test-all"
