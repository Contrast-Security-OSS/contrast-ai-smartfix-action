#!/usr/bin/env python3
"""Tests for test environment setup helper."""

import unittest

# Test setup imports (path is set up by conftest.py)
from setup_test_env import (
    create_temp_repo_dir,
    cleanup_temp_dir
)


class TestSetupTestEnv(unittest.TestCase):
    """Test cases for test environment setup helper."""

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
