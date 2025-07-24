#!/bin/bash
#
# run_tests.sh - Install dependencies with UV and run tests
#
# Usage:
#   ./run_tests.sh [--skip-install] [test_files...]
#
# Examples:
#   ./run_tests.sh                    # Install deps and run all tests
#   ./run_tests.sh test_main.py       # Install deps and run specific test
#   ./run_tests.sh --skip-install     # Skip installation, run all tests
#

set -e  # Exit on error

# Get the project root directory
PROJECT_ROOT=$(cd "$(dirname "$0")/.." && pwd)
REQUIREMENTS_LOCK="$PROJECT_ROOT/src/requirements.lock"
SKIP_INSTALL=0

# Process arguments
TEST_FILES=()
for arg in "$@"; do
    if [[ "$arg" == "--skip-install" ]]; then
        SKIP_INSTALL=1
    else
        TEST_FILES+=("$arg")
    fi
done

# Change to project root for proper imports
cd "$PROJECT_ROOT"

# Install dependencies if not skipped
if [[ $SKIP_INSTALL -eq 0 ]]; then
    if [[ ! -f "$REQUIREMENTS_LOCK" ]]; then
        echo "Error: Requirements lock file not found at $REQUIREMENTS_LOCK" >&2
        exit 1
    fi

    echo "Installing dependencies from $REQUIREMENTS_LOCK..."
    
    # Check if UV is installed
    if ! command -v uv &> /dev/null; then
        echo "Error: UV is not installed. Please install it first:"
        echo "  pip install uv"
        echo "or"
        echo "  curl -sSf https://install.uv.dev | python3 -"
        exit 1
    fi
    
    # Install dependencies (with --system flag to install outside of venv)
    if ! uv pip install --system -r "$REQUIREMENTS_LOCK"; then
        echo "Error installing dependencies" >&2
        exit 1
    fi
fi

# Run tests
if [[ ${#TEST_FILES[@]} -eq 0 ]]; then
    echo "Running all tests..."
    python -m unittest discover -s test
else
    echo "Running specific tests: ${TEST_FILES[*]}"
    python -m unittest "${TEST_FILES[@]}"
fi
