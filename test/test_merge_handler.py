#!/usr/bin/env python
# -
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
from unittest.mock import patch, mock_open, MagicMock
import os
import json

# Add project root to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Define test environment variables used throughout the test file
TEST_ENV_VARS = {
    'GITHUB_REPOSITORY': 'mock/repo',
    'GITHUB_TOKEN': 'mock-token',
    'BASE_BRANCH': 'main',
    'CONTRAST_HOST': 'test.contrastsecurity.com',
    'CONTRAST_ORG_ID': 'test-org-id',
    'CONTRAST_APP_ID': 'test-app-id',
    'CONTRAST_AUTHORIZATION_KEY': 'test-auth-key',
    'CONTRAST_API_KEY': 'test-api-key',
    'GITHUB_WORKSPACE': '/tmp',
    'RUN_TASK': 'merge',
    'BUILD_COMMAND': 'echo "Test build command"',
    'GITHUB_EVENT_PATH': '/tmp/github_event.json',
    'REPO_ROOT': '/tmp/test_repo',
}

# Set environment variables before importing modules to prevent initialization errors
os.environ.update(TEST_ENV_VARS)

# Now import project modules (after path modification)
from src.config import reset_config, get_config  # noqa: E402
from src import merge_handler  # noqa: E402


class TestMergeHandler(unittest.TestCase):
    """Tests for the merge_handler module"""

    def setUp(self):
        """Set up test environment before each test"""
        # Mock sys.exit first to prevent any initialization issues
        self.exit_patcher = patch('sys.exit')
        self.mock_exit = self.exit_patcher.start()

        reset_config()

        # Mock environment variables with complete required vars
        self.env_patcher = patch.dict(os.environ, TEST_ENV_VARS)
        self.env_patcher.start()

        self.config = get_config()

    def tearDown(self):
        """Clean up after each test"""
        self.env_patcher.stop()
        self.exit_patcher.stop()
        reset_config()

    def test_load_github_event_success(self):
        """Test _load_github_event when event file loads successfully"""
        event_data = {"action": "closed", "pull_request": {"merged": True}}
        with patch('builtins.open', mock_open(read_data=json.dumps(event_data))):
            result = merge_handler._load_github_event()
            self.assertEqual(result, event_data)

    def test_validate_pr_event_merged(self):
        """Test _validate_pr_event when PR was merged"""
        event_data = {"action": "closed", "pull_request": {"merged": True, "number": 123}}
        result = merge_handler._validate_pr_event(event_data)
        self.assertEqual(result, {"merged": True, "number": 123})

    def test_validate_pr_event_not_merged(self):
        """Test _validate_pr_event when PR was closed without merging"""
        # Reset the mock to clear any previous calls
        self.mock_exit.reset_mock()

        # Patch sys.exit specifically in the merge_handler module and make it raise SystemExit
        with patch('src.merge_handler.sys.exit', side_effect=SystemExit) as mock_module_exit:
            event_data = {"action": "closed", "pull_request": {"merged": False}}
            with self.assertRaises(SystemExit):
                merge_handler._validate_pr_event(event_data)
            mock_module_exit.assert_called_once_with(0)

    def test_validate_pr_event_not_closed(self):
        """Test _validate_pr_event when action is not 'closed'"""
        # Reset the mock to clear any previous calls
        self.mock_exit.reset_mock()

        # Patch sys.exit specifically in the merge_handler module and make it raise SystemExit
        with patch('src.merge_handler.sys.exit', side_effect=SystemExit) as mock_module_exit:
            event_data = {"action": "opened"}
            with self.assertRaises(SystemExit):
                merge_handler._validate_pr_event(event_data)
            mock_module_exit.assert_called_once_with(0)

    @patch('src.merge_handler.contrast_api.send_telemetry_data')
    @patch('src.merge_handler._notify_remediation_service')
    @patch('src.merge_handler._extract_vulnerability_info')
    @patch('src.merge_handler._extract_remediation_info')
    @patch('src.merge_handler._validate_pr_event')
    @patch('src.merge_handler._load_github_event')
    @patch('src.telemetry_handler.initialize_telemetry')
    def test_handle_merged_pr_integration(self, mock_init_telemetry, mock_load_event,
                                          mock_validate, mock_extract_remediation,
                                          mock_extract_vuln, mock_notify, mock_send_telemetry):
        """Test handle_merged_pr integration flow"""
        # Mock data
        event_data = {"action": "closed", "pull_request": {"merged": True, "number": 123}}
        pull_request = {"merged": True, "number": 123, "head": {"ref": "smartfix/REM-123"}}

        mock_load_event.return_value = event_data
        mock_validate.return_value = pull_request
        mock_extract_remediation.return_value = ("REM-123", [])
        mock_extract_vuln.return_value = "VULN-456"

        # Call the function
        merge_handler.handle_merged_pr()

        # Verify calls
        mock_init_telemetry.assert_called_once()
        mock_load_event.assert_called_once()
        mock_validate.assert_called_once_with(event_data)
        mock_extract_remediation.assert_called_once_with(pull_request)
        mock_extract_vuln.assert_called_once_with([])
        mock_notify.assert_called_once_with("REM-123")
        mock_send_telemetry.assert_called_once()

    def test_extract_remediation_info_copilot_branch(self):
        """Test _extract_remediation_info with Copilot branch"""
        # Mock objects
        mock_extract_remediation_id = MagicMock(return_value="REM-456")
        git_ops_mock = MagicMock()
        git_ops_mock.extract_issue_number_from_branch.return_value = 42
        telemetry_mock = MagicMock()
        # Test data
        pull_request = {
            "head": {"ref": "copilot/fix-42"},
            "labels": [{"name": "smartfix-id:REM-456"}]
        }
        # Need to patch the GitOperations class and not just the constructor
        with patch('src.merge_handler.extract_remediation_id_from_labels', mock_extract_remediation_id):
            with patch('src.merge_handler.GitOperations') as mock_git_ops_class:
                # Return our mock instance when the class is instantiated
                mock_git_ops_class.return_value = git_ops_mock
                with patch('src.telemetry_handler.update_telemetry', telemetry_mock):
                    # Execute
                    result = merge_handler._extract_remediation_info(pull_request)
        # Assert - only check the result and that functions were called
        self.assertEqual(result, ("REM-456", [{"name": "smartfix-id:REM-456"}]))
        mock_extract_remediation_id.assert_called_once()
        git_ops_mock.extract_issue_number_from_branch.assert_called_once_with("copilot/fix-42")

    def test_extract_remediation_info_claude_branch(self):
        """Test _extract_remediation_info with Claude Code branch"""
        # Mock objects
        mock_extract_remediation_id = MagicMock(return_value="REM-789")
        git_ops_mock = MagicMock()
        git_ops_mock.extract_issue_number_from_branch.return_value = 75
        telemetry_mock = MagicMock()
        # Test data
        pull_request = {
            "head": {"ref": "claude/issue-75-20250908-1723"},
            "labels": [{"name": "smartfix-id:REM-789"}]
        }
        # Need to patch the GitOperations class and not just the constructor
        with patch('src.merge_handler.extract_remediation_id_from_labels', mock_extract_remediation_id):
            with patch('src.merge_handler.GitOperations') as mock_git_ops_class:
                # Return our mock instance when the class is instantiated
                mock_git_ops_class.return_value = git_ops_mock
                with patch('src.telemetry_handler.update_telemetry', telemetry_mock):
                    # Execute
                    result = merge_handler._extract_remediation_info(pull_request)
        # Assert - only check the result and that functions were called
        self.assertEqual(result, ("REM-789", [{"name": "smartfix-id:REM-789"}]))
        mock_extract_remediation_id.assert_called_once()
        git_ops_mock.extract_issue_number_from_branch.assert_called_once_with("claude/issue-75-20250908-1723")

    def test_extract_remediation_info_claude_branch_no_issue_number(self):
        """Test _extract_remediation_info with Claude Code branch without extractable issue number"""
        # Mock objects
        mock_extract_remediation_id = MagicMock(return_value="REM-789")
        git_ops_mock = MagicMock()
        git_ops_mock.extract_issue_number_from_branch.return_value = None
        telemetry_mock = MagicMock()
        # Test data
        pull_request = {
            "head": {"ref": "claude/issue-75-20250908-1723"},
            "labels": [{"name": "smartfix-id:REM-789"}]
        }
        # Need to patch the GitOperations class and not just the constructor
        with patch('src.merge_handler.extract_remediation_id_from_labels', mock_extract_remediation_id):
            with patch('src.merge_handler.GitOperations') as mock_git_ops_class:
                # Return our mock instance when the class is instantiated
                mock_git_ops_class.return_value = git_ops_mock
                with patch('src.telemetry_handler.update_telemetry', telemetry_mock):
                    # Execute
                    result = merge_handler._extract_remediation_info(pull_request)
        # Assert - only check the result and that functions were called
        self.assertEqual(result, ("REM-789", [{"name": "smartfix-id:REM-789"}]))
        mock_extract_remediation_id.assert_called_once()
        git_ops_mock.extract_issue_number_from_branch.assert_called_once_with("claude/issue-75-20250908-1723")


if __name__ == '__main__':
    unittest.main()
