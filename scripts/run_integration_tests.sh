#!/bin/bash
set -e

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
echo "=== Verifying block registry ==="
python3 scripts/generate_block_registry.py

echo ""
echo "=== All integration tests passed ==="
