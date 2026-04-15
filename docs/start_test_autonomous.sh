#!/usr/bin/env bash
# Start autonomous obstacle avoidance in test mode.
#
# Usage:
#   ./start_test_autonomous.sh          # single test cycle
#   ./start_test_autonomous.sh --loop   # continuous loop (Ctrl+C to stop)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Activate venv if present
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

if [ "${1:-}" = "--loop" ]; then
    echo "[autonomous] Starting CONTINUOUS mode (Ctrl+C to stop)..."
    python3 brain/test_autonomous.py
else
    echo "[autonomous] Starting SINGLE CYCLE test..."
    python3 brain/test_autonomous.py --single
fi
