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
import unittest.mock
from unittest.mock import patch
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

    @patch('src.git_handler.run_command')
    @patch('src.git_handler.ensure_label')
    @patch('src.git_handler.log')
    def test_create_issue_success(self, mock_log, mock_ensure_label, mock_run_command):
        """Test creating a GitHub issue when successful"""
        # Setup
        title = "Test Issue Title"
        body = "Test issue body"
        vuln_label = "contrast-vuln-id:VULN-1234"
        remediation_label = "smartfix-id:5678"
        
        # Mock successful issue creation with URL returned
        mock_run_command.return_value = "https://github.com/mock/repo/issues/42"
        mock_ensure_label.return_value = True
        
        # Initialize config with testing=True
        _ = get_config(testing=True)
        
        # Execute
        result = git_handler.create_issue(title, body, vuln_label, remediation_label)
        
        # Assert
        mock_run_command.assert_called_once()
        self.assertEqual(42, result)  # Should extract issue number 42 from URL
        mock_log.assert_any_call("Successfully created issue: https://github.com/mock/repo/issues/42")
        mock_log.assert_any_call("Issue number extracted: 42")
        mock_log.assert_any_call("Issue assigned to @Copilot")

    @patch('src.git_handler.run_command')
    @patch('src.git_handler.ensure_label')
    @patch('src.git_handler.log')
    def test_create_issue_failure(self, mock_log, mock_ensure_label, mock_run_command):
        """Test creating a GitHub issue when it fails"""
        # Setup
        title = "Test Issue Title"
        body = "Test issue body"
        vuln_label = "contrast-vuln-id:VULN-1234"
        remediation_label = "smartfix-id:5678"
        
        # Mock failure during issue creation
        mock_run_command.side_effect = Exception("Mock error")
        mock_ensure_label.return_value = True
        
        # Initialize config with testing=True
        _ = get_config(testing=True)
        
        # Execute
        result = git_handler.create_issue(title, body, vuln_label, remediation_label)
        
        # Assert
        mock_run_command.assert_called_once()
        self.assertIsNone(result)
        mock_log.assert_any_call("Failed to create GitHub issue: Mock error", is_error=True)

    @patch('src.git_handler.run_command')
    @patch('src.git_handler.find_open_pr_for_issue')
    @patch('src.git_handler.ensure_label')
    @patch('src.git_handler.log')
    @patch('src.git_handler.debug_log')
    def test_reset_issue_success(self, mock_debug_log, mock_log, mock_ensure_label, mock_find_open_pr, mock_run_command):
        """Test resetting a GitHub issue when successful"""
        # Setup
        issue_number = 42
        remediation_label = "smartfix-id:5678"
        
        # Mock that no open PR exists
        mock_find_open_pr.return_value = None
        
        # Mock successful issue view with labels
        mock_run_command.side_effect = [
            # First call - issue view response
            json.dumps({"labels": [{"name": "contrast-vuln-id:VULN-1234"}, {"name": "smartfix-id:OLD-REM"}]}),
            # Second call - remove label response
            "",
            # Third call - add label response
            "",
            # Fourth call - unassign response
            "",
            # Fifth call - reassign response
            ""
        ]
        mock_ensure_label.return_value = True
        
        # Initialize config with testing=True
        _ = get_config(testing=True)
        
        # Execute
        result = git_handler.reset_issue(issue_number, remediation_label)
        
        # Assert
        self.assertEqual(mock_run_command.call_count, 5)  # Should call run_command 5 times
        self.assertTrue(result)
        mock_debug_log.assert_any_call("Removed existing remediation labels from issue #42")
        mock_log.assert_any_call("Added new remediation label to issue #42")
        mock_log.assert_any_call("Reassigned issue #42 to @Copilot")
        
    @patch('src.git_handler.find_open_pr_for_issue')
    @patch('src.git_handler.run_command')
    @patch('src.git_handler.log')
    def test_reset_issue_failure(self, mock_log, mock_run_command, mock_find_pr):
        """Test resetting a GitHub issue when it fails"""
        # Setup
        issue_number = 42
        remediation_label = "smartfix-id:5678"
        mock_run_command.side_effect = Exception("Mock error")
        mock_find_pr.return_value = None  # No open PR exists
        
        # Initialize config with testing=True
        _ = get_config(testing=True)
        
        # Execute
        result = git_handler.reset_issue(issue_number, remediation_label)
        
        # Assert
        mock_run_command.assert_called_once()
        self.assertFalse(result)
        mock_log.assert_any_call("Failed to reset issue #42: Mock error", is_error=True)

    @patch('src.git_handler.find_open_pr_for_issue')
    @patch('src.git_handler.log')
    def test_reset_issue_with_open_pr(self, mock_log, mock_find_open_pr):
        """Test resetting a GitHub issue when an open PR exists"""
        # Setup
        issue_number = 42
        remediation_label = "smartfix-id:5678"
        
        # Mock that an open PR exists
        mock_find_open_pr.return_value = {
            "number": 123,
            "url": "https://github.com/mock/repo/pull/123",
            "title": "Fix for issue #42"
        }
        
        # Initialize config with testing=True
        _ = get_config(testing=True)
        
        # Execute
        result = git_handler.reset_issue(issue_number, remediation_label)
        
        # Assert
        mock_find_open_pr.assert_called_once_with(issue_number)
        self.assertFalse(result)
        mock_log.assert_any_call(
            "Cannot reset issue #42 because it has an open PR #123: https://github.com/mock/repo/pull/123", 
            is_error=True
        )

    @patch('src.git_handler.run_command')
    @patch('src.git_handler.debug_log')
    @patch('src.git_handler.log')
    def test_find_open_pr_for_issue_found(self, mock_log, mock_debug_log, mock_run_command):
        """Test finding a PR for an issue when the PR exists"""
        # Setup
        issue_number = 42
        pr_data = [
            {
                "number": 123,
                "url": "https://github.com/mock/repo/pull/123",
                "title": "Fix bug for issue #42",
                "headRefName": "copilot/fix-42",
                "baseRefName": "main",
                "state": "OPEN"
            }
        ]
        mock_run_command.return_value = json.dumps(pr_data)
        
        # Initialize config with testing=True
        _ = get_config(testing=True)
        
        # Execute
        result = git_handler.find_open_pr_for_issue(issue_number)
        
        # Assert
        self.assertEqual(result, pr_data[0])
        mock_run_command.assert_called_once()
        mock_debug_log.assert_any_call("Searching for open PR related to issue #42")
        mock_log.assert_any_call("Found open PR #123 for issue #42: Fix bug for issue #42")

    @patch('src.git_handler.run_command')
    @patch('src.git_handler.debug_log')
    @patch('src.git_handler.log')
    def test_find_open_pr_for_issue_not_found(self, mock_log, mock_debug_log, mock_run_command):
        """Test finding a PR for an issue when no PR exists"""
        # Setup
        issue_number = 42
        mock_run_command.return_value = "[]"
        
        # Initialize config with testing=True
        _ = get_config(testing=True)
        
        # Execute
        result = git_handler.find_open_pr_for_issue(issue_number)
        
        # Assert
        self.assertIsNone(result)
        mock_run_command.assert_called_once()
        mock_debug_log.assert_any_call("Searching for open PR related to issue #42")
        mock_debug_log.assert_any_call("No open PRs found for issue #42")

    @patch('src.git_handler.debug_log')
    @patch('src.git_handler.run_command')
    @patch('src.git_handler.log')
    def test_find_open_pr_for_issue_error(self, mock_log, mock_run_command, mock_debug_log):
        """Test finding a PR for an issue when an error occurs"""
        # Setup
        issue_number = 42
        mock_run_command.side_effect = Exception("Mock error")
        
        # Initialize config with testing=True
        _ = get_config(testing=True)
        
        # Execute
        result = git_handler.find_open_pr_for_issue(issue_number)
        
        # Assert
        self.assertIsNone(result)
        mock_run_command.assert_called_once()
        mock_debug_log.assert_any_call("Searching for open PR related to issue #42")
        mock_log.assert_any_call("Error searching for PRs related to issue #42: Mock error", is_error=True)

    @patch('src.git_handler.config')
    @patch('src.git_handler.ensure_label')
    @patch('src.git_handler.run_command')
    @patch('src.git_handler.log')
    @patch('src.git_handler.debug_log')
    def test_add_labels_to_pr_success(self, mock_debug_log, mock_log, mock_run_command, mock_ensure_label, mock_config):
        """Test successfully adding labels to a PR"""
        # Setup
        pr_number = 123
        labels = ["contrast-vuln-id:VULN-12345", "smartfix-id:remediation-67890"]
        mock_ensure_label.return_value = True
        mock_run_command.return_value = ""  # Successful command returns empty string
        
        # Mock config to use test repository
        mock_config.GITHUB_REPOSITORY = "mock/repo"
        
        # Initialize config with testing=True
        _ = get_config(testing=True)
        
        # Execute
        result = git_handler.add_labels_to_pr(pr_number, labels)
        
        # Assert
        self.assertTrue(result)
        
        # Verify ensure_label was called for each label with correct parameters
        expected_ensure_calls = [
            unittest.mock.call("contrast-vuln-id:VULN-12345", "Vulnerability identified by Contrast", "ff0000"),
            unittest.mock.call("smartfix-id:remediation-67890", "Remediation ID for Contrast vulnerability", "0075ca")
        ]
        mock_ensure_label.assert_has_calls(expected_ensure_calls, any_order=True)
        
        # Verify run_command was called with correct gh pr edit command
        mock_run_command.assert_called_once()
        call_args = mock_run_command.call_args[0][0]  # First argument (command list)
        self.assertEqual(call_args[0:5], ["gh", "pr", "edit", "--repo", "mock/repo"])
        self.assertEqual(call_args[5], "123")
        self.assertEqual(call_args[6:8], ["--add-label", "contrast-vuln-id:VULN-12345,smartfix-id:remediation-67890"])
        
        mock_log.assert_any_call("Adding labels to PR #123: ['contrast-vuln-id:VULN-12345', 'smartfix-id:remediation-67890']")
        mock_log.assert_any_call("Successfully added labels to PR #123: ['contrast-vuln-id:VULN-12345', 'smartfix-id:remediation-67890']")

    @patch('src.git_handler.ensure_label')
    @patch('src.git_handler.run_command')
    @patch('src.git_handler.log')
    @patch('src.git_handler.debug_log')
    def test_add_labels_to_pr_empty_labels(self, mock_debug_log, mock_log, mock_run_command, mock_ensure_label):
        """Test adding empty labels list to a PR"""
        # Setup
        pr_number = 123
        labels = []
        
        # Initialize config with testing=True
        _ = get_config(testing=True)
        
        # Execute
        result = git_handler.add_labels_to_pr(pr_number, labels)
        
        # Assert
        self.assertTrue(result)
        mock_ensure_label.assert_not_called()
        mock_run_command.assert_not_called()
        mock_debug_log.assert_called_with("No labels provided to add to PR")

    @patch('src.git_handler.ensure_label')
    @patch('src.git_handler.run_command')
    @patch('src.git_handler.log')
    @patch('src.git_handler.debug_log')
    def test_add_labels_to_pr_with_custom_label(self, mock_debug_log, mock_log, mock_run_command, mock_ensure_label):
        """Test adding labels including a custom label type"""
        # Setup
        pr_number = 456
        labels = ["contrast-vuln-id:VULN-99999", "custom-label"]
        mock_ensure_label.return_value = True
        mock_run_command.return_value = ""
        
        # Initialize config with testing=True
        _ = get_config(testing=True)
        
        # Execute
        result = git_handler.add_labels_to_pr(pr_number, labels)
        
        # Assert
        self.assertTrue(result)
        
        # Verify ensure_label was called with correct parameters for different label types
        expected_ensure_calls = [
            unittest.mock.call("contrast-vuln-id:VULN-99999", "Vulnerability identified by Contrast", "ff0000"),
            unittest.mock.call("custom-label", "Label added by Contrast AI SmartFix", "cccccc")
        ]
        mock_ensure_label.assert_has_calls(expected_ensure_calls, any_order=True)

    @patch('src.git_handler.ensure_label')
    @patch('src.git_handler.run_command')
    @patch('src.git_handler.log')
    @patch('src.git_handler.debug_log')
    def test_add_labels_to_pr_command_failure(self, mock_debug_log, mock_log, mock_run_command, mock_ensure_label):
        """Test adding labels to a PR when the gh command fails"""
        # Setup
        pr_number = 789
        labels = ["test-label"]
        mock_ensure_label.return_value = True
        mock_run_command.side_effect = Exception("Command failed")
        
        # Initialize config with testing=True
        _ = get_config(testing=True)
        
        # Execute
        result = git_handler.add_labels_to_pr(pr_number, labels)
        
        # Assert
        self.assertFalse(result)
        mock_ensure_label.assert_called_once_with("test-label", "Label added by Contrast AI SmartFix", "cccccc")
        mock_run_command.assert_called_once()
        mock_log.assert_any_call("Adding labels to PR #789: ['test-label']")
        mock_log.assert_any_call("Failed to add labels to PR #789: Command failed", is_error=True)

if __name__ == '__main__':
    unittest.main()
