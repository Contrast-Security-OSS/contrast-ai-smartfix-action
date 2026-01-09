"""Test helpers package for SmartFix test suite.

This package provides reusable patch lists and utilities for testing
across all functional domains.
"""

from .agent_patches import (
    AGENT_EXECUTION_PATCHES,
    EVENT_LOOP_PATCHES,
    SUB_AGENT_PATCHES,
    MCP_PATCHES,
    AGENT_ORCHESTRATION_PATCHES,
)

from .build_patches import (
    SUBPROCESS_PATCHES,
    BUILD_RUNNER_PATCHES,
    FORMATTER_PATCHES,
    COMMAND_VALIDATION_PATCHES,
    BUILD_WORKFLOW_PATCHES,
)

from .api_patches import (
    HTTP_PATCHES,
    CONTRAST_API_PATCHES,
    GITHUB_API_PATCHES,
    HANDLER_PATCHES,
    API_INTEGRATION_PATCHES,
)

from .common_patches import (
    GIT_OPERATIONS_PATCHES,
    FILE_IO_PATCHES,
    TELEMETRY_PATCHES,
    ENV_PATCHES,
    COMMON_PATCHES,
    setup_patch_list,
    teardown_patch_list,
    setup_git_patches_with_defaults,
)

__all__ = [
    # Agent patches
    'AGENT_EXECUTION_PATCHES',
    'EVENT_LOOP_PATCHES',
    'SUB_AGENT_PATCHES',
    'MCP_PATCHES',
    'AGENT_ORCHESTRATION_PATCHES',
    # Build patches
    'SUBPROCESS_PATCHES',
    'BUILD_RUNNER_PATCHES',
    'FORMATTER_PATCHES',
    'COMMAND_VALIDATION_PATCHES',
    'BUILD_WORKFLOW_PATCHES',
    # API patches
    'HTTP_PATCHES',
    'CONTRAST_API_PATCHES',
    'GITHUB_API_PATCHES',
    'HANDLER_PATCHES',
    'API_INTEGRATION_PATCHES',
    # Common patches
    'GIT_OPERATIONS_PATCHES',
    'FILE_IO_PATCHES',
    'TELEMETRY_PATCHES',
    'ENV_PATCHES',
    'COMMON_PATCHES',
    # Utilities
    'setup_patch_list',
    'teardown_patch_list',
    'setup_git_patches_with_defaults',
]
