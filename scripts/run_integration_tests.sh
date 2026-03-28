#!/bin/bash
set -e

echo "=== Validating block metadata (MANIFEST.json freshness) ==="
python3 scripts/normalize_blocks.py --check

echo ""
echo "=== Validating port-compatibility codegen freshness ==="
python3 scripts/generate_port_compat.py --check

echo ""
echo "=== Validating block registry health ==="
python3 scripts/validate_blocks.py

echo ""
echo "=== Running registry service tests ==="
python3 -m pytest backend/tests/test_registry.py -v --tb=short

echo ""
echo "=== Running UX feature tests ==="
python3 -m pytest backend/tests/test_ux_features_integration.py -v --tb=short

echo ""
echo "=== Running block validation tests ==="
python3 -m pytest backend/tests/test_block_validation.py -v --tb=short

echo ""
echo "=== Running composite block tests ==="
python3 -m pytest backend/tests/test_composite.py -v --tb=short

echo ""
echo "=== Running system tests ==="
python3 -m pytest backend/tests/test_system.py -v --tb=short

echo ""
echo "=== Verifying block registry codegen ==="
python3 scripts/generate_block_registry.py

echo ""
echo "=== All integration tests passed ==="
