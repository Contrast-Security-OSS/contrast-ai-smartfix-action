# Makefile for contrast-ai-smartfix-action
#
# Available targets:
#   make test     - Run all tests using the test runner
#   make coverage - Run tests with coverage report
#   make lint     - Run linting via pre-push hook
#   make help     - Show this help message

.PHONY: test coverage lint help

# Run tests using the test runner script
test:
	@echo "Running tests..."
	./test/run_tests.sh

# Run tests with coverage report
coverage:
	@echo "Running tests with coverage..."
	./test/run_tests.sh --coverage

# Run linting via the pre-push hook
lint:
	@echo "Running linter..."
	./.git/hooks/pre-push

# Show help message
help:
	@echo "Available make targets:"
	@echo "  test     - Run all tests using ./test/run_tests.sh"
	@echo "  coverage - Run tests with coverage report"
	@echo "  lint     - Run linting via ./.git/hooks/pre-push"
	@echo "  help     - Show this help message"

# Default target
.DEFAULT_GOAL := help