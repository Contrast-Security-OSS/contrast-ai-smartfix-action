#!/usr/bin/env python3
"""Tests for test environment setup helper."""

import unittest

# Test setup imports (path is set up by conftest.py)
from setup_test_env import (
    get_standard_test_env_vars,
    create_temp_repo_dir,
    cleanup_temp_dir
)


class TestSetupTestEnv(unittest.TestCase):
    """Test cases for test environment setup helper."""

    def test_get_standard_test_env_vars(self):
        """Test that standard environment variables are returned."""
        env_vars = get_standard_test_env_vars()

        # Check that all required variables are present
        required_vars = [
            'CONTRAST_HOST', 'CONTRAST_ORG_ID', 'CONTRAST_APP_ID',
            'CONTRAST_AUTHORIZATION_KEY', 'CONTRAST_API_KEY',
            'GITHUB_TOKEN', 'GITHUB_REPOSITORY', 'BASE_BRANCH',
            'REPO_ROOT', 'BUILD_COMMAND', 'TESTING'
        ]

        for var in required_vars:
            self.assertIn(var, env_vars, f"Missing required environment variable: {var}")

        # Check specific values
        self.assertEqual(env_vars['BASE_BRANCH'], 'main')
        self.assertEqual(env_vars['TESTING'], 'true')

    def test_create_and_cleanup_temp_dir(self):
        """Test temporary directory creation and cleanup."""
        # Create temp directory
        temp_dir = create_temp_repo_dir()

        # Should exist and be a directory
        self.assertTrue(temp_dir.exists())
        self.assertTrue(temp_dir.is_dir())

        # Clean up
        cleanup_temp_dir(temp_dir)

        # Should no longer exist
        self.assertFalse(temp_dir.exists())


if __name__ == '__main__':
    unittest.main()
