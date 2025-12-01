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

    # Create virtual environment if it doesn't exist
    VENV_DIR="$PROJECT_ROOT/.venv"
    if [[ ! -d "$VENV_DIR" ]]; then
        echo "Creating virtual environment..."
        if ! uv venv "$VENV_DIR"; then
            echo "Error creating virtual environment" >&2
            exit 1
        fi
    fi

    # Install dependencies in virtual environment
    if ! uv pip install -r "$REQUIREMENTS_LOCK"; then
        echo "Error installing dependencies" >&2
        exit 1
    fi
fi

# Set essential environment variables before running tests
export BASE_BRANCH="main"
export CONTRAST_HOST="test.contrastsecurity.com"
export CONTRAST_ORG_ID="test-org-id"
export CONTRAST_APP_ID="test-app-id"
export CONTRAST_AUTHORIZATION_KEY="test-auth-key"
export CONTRAST_API_KEY="test-api-key"
export GITHUB_TOKEN="mock-github-token"
export GITHUB_REPOSITORY="mock/repo"
export GITHUB_SERVER_URL="https://mockhub.com"
export GITHUB_EVENT_PATH="/tmp/github_event.json"
export GITHUB_WORKSPACE="/tmp"
export REPO_ROOT="/tmp/test_repo"
export BUILD_COMMAND="echo 'test build command'"
export FORMATTING_COMMAND="echo 'test format command'"
export DEBUG_MODE="true"
export TESTING="true"
export ENABLE_ANTHROPIC_PROMPT_CACHING="true"

# Run tests
VENV_DIR="$PROJECT_ROOT/.venv"
PYTHON_CMD="python"
if [[ -d "$VENV_DIR" ]]; then
    PYTHON_CMD="$VENV_DIR/bin/python"
fi

if [[ ${#TEST_FILES[@]} -eq 0 ]]; then
    echo "Running all tests..."
    "$PYTHON_CMD" -m unittest discover -s test
else
    echo "Running specific tests: ${TEST_FILES[*]}"
    "$PYTHON_CMD" -m unittest "${TEST_FILES[@]}"
fi
