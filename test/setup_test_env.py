"""Standard test environment setup helper.

This module provides consistent test environment setup across all test files
to prevent missing environment variables and ensure reliable test execution.
"""

import os
from unittest.mock import patch
from pathlib import Path


def get_standard_test_env_vars():
    """
    Get standard environment variables for testing.

    Returns:
        dict: Dictionary of environment variables needed for testing
    """
    return {
        # Contrast API configuration
        'CONTRAST_HOST': 'test.contrastsecurity.com',
        'CONTRAST_ORG_ID': 'test-org-id',
        'CONTRAST_APP_ID': 'test-app-id',
        'CONTRAST_AUTHORIZATION_KEY': 'test-auth-key',
        'CONTRAST_API_KEY': 'test-api-key',

        # GitHub configuration
        'GITHUB_TOKEN': 'mock-github-token',
        'GITHUB_REPOSITORY': 'mock/repo',
        'GITHUB_EVENT_PATH': '/tmp/github_event.json',
        'GITHUB_WORKSPACE': '/tmp',

        # Repository configuration
        'REPO_ROOT': '/tmp/test_repo',
        'BASE_BRANCH': 'main',

        # Build configuration
        'BUILD_COMMAND': 'echo "test build command"',
        'FORMATTING_COMMAND': 'echo "test format command"',

        # Debug and testing flags
        'DEBUG_MODE': 'true',
        'TESTING': 'true'
    }


def setup_test_environment():
    """
    Set up standard test environment with all required variables.

    Returns:
        unittest.mock._patch: Environment patch that should be started/stopped by caller
    """
    return patch.dict(os.environ, get_standard_test_env_vars(), clear=True)


class TestEnvironmentMixin:
    """
    Mixin class to provide standard test environment setup.

    Usage:
        class TestMyClass(unittest.TestCase, TestEnvironmentMixin):
            def setUp(self):
                self.setup_standard_test_env()

            def tearDown(self):
                self.cleanup_standard_test_env()
    """

    def setup_standard_test_env(self):
        """Set up standard test environment."""
        self._env_patcher = setup_test_environment()
        self._env_patcher.start()

    def cleanup_standard_test_env(self):
        """Clean up standard test environment."""
        if hasattr(self, '_env_patcher'):
            self._env_patcher.stop()


def create_temp_repo_dir():
    """
    Create a temporary directory for repository testing.

    Returns:
        pathlib.Path: Path to temporary directory
    """
    import tempfile
    return Path(tempfile.mkdtemp())


def cleanup_temp_dir(temp_dir):
    """
    Clean up temporary directory.

    Args:
        temp_dir: Path to temporary directory to clean up
    """
    import shutil
    if temp_dir and temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)
