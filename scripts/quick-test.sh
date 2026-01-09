#!/bin/bash
# Quick database test - runs health check only
# Usage: ./scripts/quick-test.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Activate virtual environment
if [ -d "$PROJECT_ROOT/venv" ]; then
    source "$PROJECT_ROOT/venv/bin/activate"
else
    echo "❌ Virtual environment not found. Run: python3 -m venv venv"
    exit 1
fi

# Run health check
echo "🗄️  Running quick database health check..."
echo ""

python "$PROJECT_ROOT/tests/test_database.py" --health

EXIT_CODE=$?

deactivate

exit $EXIT_CODE
