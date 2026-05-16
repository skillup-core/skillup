#!/bin/bash
# Skillbot Debugger Transform Test Runner
# Usage: ./test.sh

cd "$(dirname "$0")"
python3 test.py testcase.txt
