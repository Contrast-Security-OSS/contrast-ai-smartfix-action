# Contributing to SmartFix

Thank you for your interest in contributing to SmartFix! This guide will help you get set up for development.

## ⚖️ Contributor License Agreement

**External contributors must have a signed Contributor License Agreement (CLA) on file with Contrast Security before we can accept code contributions.**

If you or your company do not have a CLA on file with Contrast Security, please contact us before submitting pull requests. This requirement does not apply to Contrast Security employees.

## 🚀 Quick Start

### 1. Clone and Setup

```bash
git clone <repository-url>
cd contrast-ai-smartfix-action

# Install git hooks for automatic linting
./setup-hooks.sh
```

### 2. Install Dependencies

```bash
# Install Python dependencies (creates .venv and installs packages)
./test/run_tests.sh --skip-install  # Will prompt to install uv if needed

# Or install manually
pip install -r src/requirements.txt
pip install flake8  # For linting (if not already installed by setup-hooks.sh)
```

### 3. Verify Setup

```bash
# Run tests to ensure everything works
./test/run_tests.sh

# Run linting to check code quality
./.git/hooks/pre-push
```

## 🔧 Development Workflow

### Code Quality & Linting

We use automated linting to maintain code quality with **single source of truth** approach:

- **Local Development**: Git hooks automatically run linting checks
- **CI/CD**: Uses the same hook scripts to ensure consistency

#### Git Hooks (Automatic)
- **Pre-commit**: Cleans trailing whitespace
- **Pre-push**: Runs Python linting with flake8

#### Manual Linting
```bash
# Run the same linting that CI uses
./.git/hooks/pre-push

# Or run flake8 directly (but hook is preferred for consistency)
flake8 src/ test/
```

#### Bypassing Hooks (Not Recommended)
```bash
git commit --no-verify  # Skip pre-commit
git push --no-verify    # Skip pre-push
```

### Running Tests

```bash
# Run all tests (installs deps if needed)
./test/run_tests.sh

# Run tests without installing deps
./test/run_tests.sh --skip-install

# Run specific test file
./test/run_tests.sh test_main.py

# Run multiple specific tests
./test/run_tests.sh test_main.py test_config.py
```

### Code Style Guidelines

- **Linting**: Follows flake8 default configuration
- **Imports**: Group standard library, third-party, and local imports separately
- **Whitespace**: No trailing whitespace (automatically cleaned by pre-commit hook)
- **Comments**: Use clear, concise comments for complex logic

## 🧪 Testing Guidelines

- Write tests for new functionality
- Maintain existing test coverage
- Use descriptive test names
- Mock external dependencies (API calls, file system, etc.)

## 📋 Pull Request Process

1. **Create Feature Branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make Changes**
   - Write code following style guidelines
   - Add/update tests as needed
   - Run linting and tests locally:
     ```bash
     ./.git/hooks/pre-push  # Linting
     ./test/run_tests.sh    # Tests
     ```

3. **Commit Changes**
   ```bash
   git add .
   git commit -m "Add feature: description of changes"
   # Pre-commit hook automatically cleans whitespace
   ```

4. **Push and Create PR**
   ```bash
   git push origin your-feature-name
   # Pre-push hook automatically runs linting
   # Create pull request on GitHub
   ```

5. **PR Requirements**
   - ✅ All CI checks pass (uses same hook scripts)
   - ✅ Code review approval
   - ✅ Branch is up-to-date with main

## 🔍 Debugging & Development

### Local Development Commands

```bash
# Full development cycle
./setup-hooks.sh           # One-time setup
./test/run_tests.sh        # Run tests
./.git/hooks/pre-push      # Run linting

# During development
git commit                 # Triggers pre-commit (whitespace cleanup)
git push                   # Triggers pre-push (linting)
```

### Environment Variables

The test runner (`./test/run_tests.sh`) automatically sets up test environment variables. For manual testing, you'll need:

```bash
export BASE_BRANCH="main"
export BUILD_COMMAND="echo 'Mock build'"
export FORMATTING_COMMAND="echo 'Mock format'"
export GITHUB_TOKEN="your-github-token"
export CONTRAST_HOST="https://your.contrast.host"
export CONTRAST_ORG_ID="your-org-id"
export CONTRAST_APP_ID="your-app-id"
export CONTRAST_AUTHORIZATION_KEY="your-auth-key"
export CONTRAST_API_KEY="your-api-key"
export DEBUG_MODE="true"
```

### Debugging Tips

- Use `DEBUG_MODE=true` for verbose logging

## 🐛 Troubleshooting

#### Tests Not Working
```bash
# Use the test script which handles all setup
./test/run_tests.sh

# If UV is missing, install it:
pip install uv
```

Thank you for contributing to SmartFix! 🙏