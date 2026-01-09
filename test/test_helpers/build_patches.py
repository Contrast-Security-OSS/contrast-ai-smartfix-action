"""Shared patches for build and test workflow tests.

This module provides reusable patch lists for testing build execution,
formatting, and command validation functionality.
"""

# Subprocess patches - prevent actual command execution
SUBPROCESS_PATCHES = [
    'subprocess.run',
    'subprocess.Popen',
    'subprocess.check_output',
]

# Build runner patches - prevent actual builds
BUILD_RUNNER_PATCHES = [
    'src.smartfix.domains.workflow.build_runner.run_build_command',
    'src.smartfix.domains.workflow.build_runner.capture_build_output',
]

# Formatter patches - prevent actual formatting
FORMATTER_PATCHES = [
    'src.smartfix.domains.workflow.formatter.run_formatting_command',
    'src.smartfix.domains.workflow.formatter.format_files',
]

# Command validation patches - for testing validation logic
COMMAND_VALIDATION_PATCHES = [
    'src.smartfix.config.command_validator.validate_command',
    'src.smartfix.config.command_validator.validate_shell_command',
]

# Combined build workflow patches (all of the above)
BUILD_WORKFLOW_PATCHES = (
    SUBPROCESS_PATCHES
    + BUILD_RUNNER_PATCHES
    + FORMATTER_PATCHES
    + COMMAND_VALIDATION_PATCHES
)
