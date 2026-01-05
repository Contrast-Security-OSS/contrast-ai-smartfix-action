"""Shared patches and utilities for all tests.

This module provides reusable patch lists for common operations like git, file I/O,
and telemetry that are used across all test domains.
"""

from unittest.mock import patch

# Git operations patches - CRITICAL: prevents accidental branch switching/cleanup
GIT_OPERATIONS_PATCHES = [
    'src.smartfix.domains.scm.git_operations.GitOperations.prepare_feature_branch',
    'src.smartfix.domains.scm.git_operations.GitOperations.stage_changes',
    'src.smartfix.domains.scm.git_operations.GitOperations.check_status',
    'src.smartfix.domains.scm.git_operations.GitOperations.commit_changes',
    'src.smartfix.domains.scm.git_operations.GitOperations.amend_commit',
    'src.smartfix.domains.scm.git_operations.GitOperations.get_last_commit_changed_files',
    'src.smartfix.domains.scm.git_operations.GitOperations.get_uncommitted_changed_files',
    'src.smartfix.domains.scm.git_operations.GitOperations.push_branch',
    'src.smartfix.domains.scm.git_operations.GitOperations.cleanup_branch',
]

# File I/O patches - prevent actual file system operations
FILE_IO_PATCHES = [
    'builtins.open',
    'os.path.exists',
    'os.makedirs',
    'os.remove',
    'pathlib.Path.read_text',
    'pathlib.Path.write_text',
]

# Telemetry patches - prevent actual telemetry updates
TELEMETRY_PATCHES = [
    'src.telemetry.update_telemetry',
    'src.telemetry.record_event',
    'src.telemetry.record_error',
]

# Environment variable patches - for testing config
ENV_PATCHES = [
    'os.getenv',
    'os.environ.get',
]

# Combined common patches (all of the above)
COMMON_PATCHES = (
    GIT_OPERATIONS_PATCHES
    + FILE_IO_PATCHES
    + TELEMETRY_PATCHES
    + ENV_PATCHES
)


def setup_patch_list(test_case, patch_list):
    """Helper function to set up a list of patches in a test case.

    Args:
        test_case: The unittest.TestCase instance
        patch_list: List of patch target strings

    Returns:
        List of (patcher, mock) tuples

    Example:
        class TestMyClass(unittest.TestCase):
            def setUp(self):
                self.mocks = setup_patch_list(self, GIT_OPERATIONS_PATCHES)

            def tearDown(self):
                teardown_patch_list(self.mocks)
    """
    mocks = []
    for patch_target in patch_list:
        patcher = patch(patch_target)
        mock = patcher.start()
        mocks.append((patcher, mock))
    return mocks


def teardown_patch_list(mocks):
    """Helper function to tear down a list of patches.

    Args:
        mocks: List of (patcher, mock) tuples from setup_patch_list
    """
    for patcher, mock in mocks:
        patcher.stop()


def setup_git_patches_with_defaults(test_case):
    """Set up git operation patches with common default return values.

    This is a convenience function that sets up git patches and configures
    common defaults like file change lists and status checks.

    Args:
        test_case: The unittest.TestCase instance

    Returns:
        List of (patcher, mock) tuples
    """
    mocks = setup_patch_list(test_case, GIT_OPERATIONS_PATCHES)

    # Set default return values for common git operations
    for patcher, mock in mocks:
        if 'get_last_commit_changed_files' in patcher.attribute:
            mock.return_value = ["src/file1.py", "src/file2.py"]
        elif 'get_uncommitted_changed_files' in patcher.attribute:
            mock.return_value = ["src/file1.py", "src/file2.py"]
        elif 'check_status' in patcher.attribute:
            mock.return_value = True  # Has changes

    return mocks
