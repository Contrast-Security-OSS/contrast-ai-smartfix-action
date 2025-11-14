#!/bin/bash

# Setup script for installing git hooks
# Run this once after cloning the repository to enable automatic linting

set -e

echo "🔧 Setting up git hooks for SmartFix development..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Check if we're in the right directory
if [ ! -f "action.yml" ] || [ ! -d "src" ] || [ ! -d "hooks" ]; then
    print_error "This doesn't appear to be the contrast-ai-smartfix-action repository root"
    print_error "Please run this script from the repository root directory"
    exit 1
fi

# Check if .git directory exists
if [ ! -d ".git" ]; then
    print_error "No .git directory found. Are you in a git repository?"
    exit 1
fi

echo ""
print_info "Installing git hooks..."

# Install pre-commit hook
if [ -f "hooks/pre-commit" ]; then
    ln -sf ../../hooks/pre-commit .git/hooks/pre-commit
    chmod +x .git/hooks/pre-commit
    print_success "Pre-commit hook installed (whitespace cleanup)"
else
    print_warning "hooks/pre-commit not found, skipping"
fi

# Install pre-push hook
if [ -f "hooks/pre-push" ]; then
    ln -sf ../../hooks/pre-push .git/hooks/pre-push
    chmod +x .git/hooks/pre-push
    print_success "Pre-push hook installed (Python linting)"
else
    print_warning "hooks/pre-push not found, skipping"
fi

echo ""
print_info "Checking Python linting dependencies..."

# Check if flake8 is available
if command -v flake8 &> /dev/null; then
    print_success "flake8 is already installed"
else
    print_warning "flake8 not found. Installing..."
    if command -v pip &> /dev/null; then
        pip install flake8
        print_success "flake8 installed successfully"
    elif command -v pip3 &> /dev/null; then
        pip3 install flake8
        print_success "flake8 installed successfully"
    else
        print_error "Neither pip nor pip3 found. Please install flake8 manually:"
        print_error "pip install flake8"
        exit 1
    fi
fi

echo ""
print_success "Git hooks setup completed successfully!"
echo ""
print_info "What happens now:"
echo "  🧹 Pre-commit: Automatically cleans trailing whitespace"
echo "  🔍 Pre-push: Runs Python linting before pushing"
echo ""
print_info "To bypass hooks temporarily (not recommended):"
echo "  git commit --no-verify"
echo "  git push --no-verify"
echo ""
print_success "Happy coding! 🚀"