#!/bin/bash
# Skillup Test Runner
# This script runs all unit tests for the SKILL code analyzer

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================="
echo "  Skillup Unit Test Suite"
echo "========================================="

# Run the tests
python3 src/test_skillup.py

EXIT_CODE=$?

exit $EXIT_CODE
