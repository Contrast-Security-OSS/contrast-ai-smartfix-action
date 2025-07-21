#!/usr/bin/env python
#-
# #%L
# Contrast AI SmartFix
# %%
# Copyright (C) 2025 Contrast Security, Inc.
# %%
# Contact: support@contrastsecurity.com
# License: Commercial
# NOTICE: This Software and the patented inventions embodied within may only be
# used as part of Contrast Security's commercial offerings. Even though it is
# made available through public repositories, use of this Software is subject to
# the applicable End User Licensing Agreement found at
# https://www.contrastsecurity.com/enduser-terms-0317a or as otherwise agreed
# between Contrast Security and the End User. The Software may not be reverse
# engineered, modified, repackaged, sold, redistributed or otherwise used in a
# way not consistent with the End User License Agreement.
# #L%
#

import sys
import unittest
from unittest.mock import patch, MagicMock
import os
import json

# Add project root to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# IDEA: Update Config to take a dict of config values for testing
# Define test environment variables used throughout the test file
TEST_ENV_VARS = {
    'GITHUB_REPOSITORY': 'mock/repo',
    'GITHUB_TOKEN': 'mock-token',
    'BASE_BRANCH': 'main',
    'CONTRAST_HOST': 'test-host',
    'CONTRAST_ORG_ID': 'test-org',
    'CONTRAST_APP_ID': 'test-app',
    'CONTRAST_AUTHORIZATION_KEY': 'test-auth',
    'CONTRAST_API_KEY': 'test-api',
    'GITHUB_WORKSPACE': '/tmp',
    'RUN_TASK': 'generate_fix',  # This triggers the requirement for BUILD_COMMAND
    'BUILD_COMMAND': 'echo "Test build command"'  # Required when RUN_TASK=generate_fix with SMARTFIX coding agent
}

# Set environment variables before importing modules to prevent initialization errors
os.environ.update(TEST_ENV_VARS)

# Import with testing=True
from src.config import get_config, reset_config
from src import git_handler

class TestGitHandler(unittest.TestCase):
    """Tests for functions in git_handler.py"""
    
    def setUp(self):
        """Set up test environment before each test"""
        # Use the shared TEST_ENV_VARS for consistent environment setup
        self.env_patcher = patch.dict('os.environ', TEST_ENV_VARS)
        self.env_patcher.start()
        reset_config()  # Reset the config singleton
        
    def tearDown(self):
        """Clean up after each test"""
        self.env_patcher.stop()
        reset_config()
    
    @patch('src.git_handler.run_command')
    @patch('src.git_handler.log')
    @patch('src.git_handler.debug_log')
    def test_find_issue_with_label_found(self, mock_debug_log, mock_log, mock_run_command):
        """Test finding an issue with a specific label when the issue exists"""
        # Setup
        label = "test-label"
        mock_response = json.dumps([{"number": 42, "createdAt": "2025-07-21T12:00:00Z"}])
        mock_run_command.return_value = mock_response
        
        # Initialize config with testing=True
        _ = get_config(testing=True)
        
        # Execute
        result = git_handler.find_issue_with_label(label)
        
        # Assert
        mock_run_command.assert_called_once()
        self.assertEqual(42, result)
        mock_debug_log.assert_any_call("Found issue #42 with label: test-label")
    
    @patch('src.git_handler.run_command')
    @patch('src.git_handler.log')
    @patch('src.git_handler.debug_log')
    def test_find_issue_with_label_not_found(self, mock_debug_log, mock_log, mock_run_command):
        """Test finding an issue with a specific label when no issue exists"""
        # Setup
        label = "test-label"
        mock_run_command.return_value = json.dumps([])
        
        # Initialize config with testing=True
        _ = get_config(testing=True)
        
        # Execute
        result = git_handler.find_issue_with_label(label)
        
        # Assert
        mock_run_command.assert_called_once()
        self.assertIsNone(result)
        mock_debug_log.assert_any_call("No issues found with label: test-label")
    
    @patch('src.git_handler.run_command')
    @patch('src.git_handler.log')
    def test_find_issue_with_label_error(self, mock_log, mock_run_command):
        """Test finding an issue with a specific label when an error occurs"""
        # Setup
        label = "test-label"
        mock_run_command.side_effect = Exception("Mock error")
        
        # Initialize config with testing=True
        _ = get_config(testing=True)
        
        # Execute
        result = git_handler.find_issue_with_label(label)
        
        # Assert
        mock_run_command.assert_called_once()
        self.assertIsNone(result)
        mock_log.assert_any_call("Error searching for GitHub issue with label: Mock error", is_error=True)

if __name__ == '__main__':
    unittest.main()
