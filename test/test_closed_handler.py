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
from unittest.mock import patch, mock_open
import os
import json

# Add project root to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Now import project modules (after path modification)
from src.config import reset_config, get_config  # noqa: E402
from src import closed_handler  # noqa: E402


class TestClosedHandler(unittest.TestCase):
    """Tests for the closed_handler module"""

    def setUp(self):
        """Set up test environment before each test"""
        # Mock sys.exit first to prevent any initialization issues
        self.exit_patcher = patch('sys.exit')
        self.mock_exit = self.exit_patcher.start()

        reset_config()

        # Mock environment variables
        self.env_patcher = patch.dict(os.environ, {
            'CONTRAST_HOST': 'test.contrastsecurity.com',
            'CONTRAST_ORG_ID': 'test-org-id',
            'CONTRAST_APP_ID': 'test-app-id',
            'CONTRAST_AUTHORIZATION_KEY': 'test-auth-key',
            'CONTRAST_API_KEY': 'test-api-key',
            'GITHUB_EVENT_PATH': '/tmp/github_event.json',
            'REPO_ROOT': '/tmp/test_repo',
        })
        self.env_patcher.start()

        self.config = get_config()

    def tearDown(self):
        """Clean up after each test"""
        self.env_patcher.stop()
        self.exit_patcher.stop()
        reset_config()

    def test_get_pr_changed_files_count_success(self):
        """Test get_pr_changed_files_count when gh command succeeds"""
        with patch('src.git_handler.run_command') as mock_run_command:
            mock_run_command.return_value = "3"

            from src.git_handler import get_pr_changed_files_count
            result = get_pr_changed_files_count(123)

            self.assertEqual(result, 3)
            mock_run_command.assert_called_once_with(
                ['gh', 'pr', 'view', '123', '--json', 'changedFiles', '--jq', '.changedFiles'],
                env=unittest.mock.ANY,
                check=False
            )

    def test_get_pr_changed_files_count_zero_files(self):
        """Test get_pr_changed_files_count when PR has zero changed files"""
        with patch('src.git_handler.run_command') as mock_run_command:
            mock_run_command.return_value = "0"

            from src.git_handler import get_pr_changed_files_count
            result = get_pr_changed_files_count(123)

            self.assertEqual(result, 0)

    def test_get_pr_changed_files_count_command_failure(self):
        """Test get_pr_changed_files_count when gh command fails"""
        with patch('src.git_handler.run_command') as mock_run_command:
            mock_run_command.return_value = None

            from src.git_handler import get_pr_changed_files_count
            result = get_pr_changed_files_count(123)

            self.assertEqual(result, -1)

    def test_get_pr_changed_files_count_invalid_response(self):
        """Test get_pr_changed_files_count when gh returns invalid data"""
        with patch('src.git_handler.run_command') as mock_run_command:
            mock_run_command.return_value = "invalid_number"

            from src.git_handler import get_pr_changed_files_count
            result = get_pr_changed_files_count(123)

            self.assertEqual(result, -1)

    @patch('src.closed_handler.contrast_api.notify_remediation_failed')
    @patch('src.closed_handler.get_pr_changed_files_count')
    def test_notify_remediation_service_zero_changes(self, mock_get_count, mock_notify_failed):
        """Test _notify_remediation_service when PR has zero changed files"""
        mock_get_count.return_value = 0
        mock_notify_failed.return_value = True

        closed_handler._notify_remediation_service("test-remediation-id", pr_number=123)

        mock_get_count.assert_called_once_with(123)
        mock_notify_failed.assert_called_once_with(
            remediation_id="test-remediation-id",
            failure_category="GENERATE_PR_FAILURE",
            contrast_host=self.config.CONTRAST_HOST,
            contrast_org_id=self.config.CONTRAST_ORG_ID,
            contrast_app_id=self.config.CONTRAST_APP_ID,
            contrast_auth_key=self.config.CONTRAST_AUTHORIZATION_KEY,
            contrast_api_key=self.config.CONTRAST_API_KEY
        )

    @patch('src.closed_handler.contrast_api.notify_remediation_pr_closed')
    @patch('src.closed_handler.get_pr_changed_files_count')
    def test_notify_remediation_service_with_changes(self, mock_get_count, mock_notify_closed):
        """Test _notify_remediation_service when PR has changed files"""
        mock_get_count.return_value = 3
        mock_notify_closed.return_value = True

        closed_handler._notify_remediation_service("test-remediation-id", pr_number=123)

        mock_get_count.assert_called_once_with(123)
        mock_notify_closed.assert_called_once_with(
            remediation_id="test-remediation-id",
            contrast_host=self.config.CONTRAST_HOST,
            contrast_org_id=self.config.CONTRAST_ORG_ID,
            contrast_app_id=self.config.CONTRAST_APP_ID,
            contrast_auth_key=self.config.CONTRAST_AUTHORIZATION_KEY,
            contrast_api_key=self.config.CONTRAST_API_KEY
        )

    @patch('src.closed_handler.contrast_api.notify_remediation_pr_closed')
    def test_notify_remediation_service_no_pr_number(self, mock_notify_closed):
        """Test _notify_remediation_service when no PR number provided (legacy behavior)"""
        mock_notify_closed.return_value = True

        closed_handler._notify_remediation_service("test-remediation-id", pr_number=None)

        mock_notify_closed.assert_called_once_with(
            remediation_id="test-remediation-id",
            contrast_host=self.config.CONTRAST_HOST,
            contrast_org_id=self.config.CONTRAST_ORG_ID,
            contrast_app_id=self.config.CONTRAST_APP_ID,
            contrast_auth_key=self.config.CONTRAST_AUTHORIZATION_KEY,
            contrast_api_key=self.config.CONTRAST_API_KEY
        )

    @patch('src.closed_handler.contrast_api.notify_remediation_failed')
    @patch('src.closed_handler.get_pr_changed_files_count')
    def test_notify_remediation_service_get_count_error(self, mock_get_count, mock_notify_failed):
        """Test _notify_remediation_service when getting changed files count fails"""
        mock_get_count.return_value = -1  # Error case
        mock_notify_failed.return_value = True

        with patch('src.closed_handler.contrast_api.notify_remediation_pr_closed') as mock_notify_closed:
            mock_notify_closed.return_value = True

            closed_handler._notify_remediation_service("test-remediation-id", pr_number=123)

            mock_get_count.assert_called_once_with(123)
            # Should fall back to standard closed notification since count failed
            mock_notify_closed.assert_called_once()
            mock_notify_failed.assert_not_called()

    def test_load_github_event_missing_path(self):
        """Test _load_github_event when GITHUB_EVENT_PATH is not set"""
        # Reset the mock to clear any previous calls
        self.mock_exit.reset_mock()

        # Patch sys.exit specifically in the closed_handler module and make it raise SystemExit
        with patch('src.closed_handler.sys.exit', side_effect=SystemExit) as mock_module_exit:
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(SystemExit):
                    closed_handler._load_github_event()
                mock_module_exit.assert_called_once_with(1)

    def test_load_github_event_file_not_found(self):
        """Test _load_github_event when event file doesn't exist"""
        # Reset the mock to clear any previous calls
        self.mock_exit.reset_mock()

        # Patch sys.exit specifically in the closed_handler module and make it raise SystemExit
        with patch('src.closed_handler.sys.exit', side_effect=SystemExit) as mock_module_exit:
            with patch('builtins.open', side_effect=FileNotFoundError):
                with self.assertRaises(SystemExit):
                    closed_handler._load_github_event()
                mock_module_exit.assert_called_once_with(1)

    def test_load_github_event_success(self):
        """Test _load_github_event when event file loads successfully"""
        event_data = {"action": "closed", "pull_request": {"merged": False}}
        with patch('builtins.open', mock_open(read_data=json.dumps(event_data))):
            result = closed_handler._load_github_event()
            self.assertEqual(result, event_data)

    def test_validate_pr_event_not_closed(self):
        """Test _validate_pr_event when action is not 'closed'"""
        # Reset the mock to clear any previous calls
        self.mock_exit.reset_mock()

        # Patch sys.exit specifically in the closed_handler module and make it raise SystemExit
        with patch('src.closed_handler.sys.exit', side_effect=SystemExit) as mock_module_exit:
            event_data = {"action": "opened"}
            with self.assertRaises(SystemExit):
                closed_handler._validate_pr_event(event_data)
            mock_module_exit.assert_called_once_with(0)

    def test_validate_pr_event_merged(self):
        """Test _validate_pr_event when PR was merged"""
        # Reset the mock to clear any previous calls
        self.mock_exit.reset_mock()

        # Patch sys.exit specifically in the closed_handler module and make it raise SystemExit
        with patch('src.closed_handler.sys.exit', side_effect=SystemExit) as mock_module_exit:
            event_data = {"action": "closed", "pull_request": {"merged": True}}
            with self.assertRaises(SystemExit):
                closed_handler._validate_pr_event(event_data)
            mock_module_exit.assert_called_once_with(0)

    def test_validate_pr_event_success(self):
        """Test _validate_pr_event when PR was closed without merging"""
        event_data = {"action": "closed", "pull_request": {"merged": False, "number": 123}}
        result = closed_handler._validate_pr_event(event_data)
        self.assertEqual(result, {"merged": False, "number": 123})

    @patch('src.closed_handler.contrast_api.send_telemetry_data')
    @patch('src.closed_handler._notify_remediation_service')
    @patch('src.closed_handler._extract_vulnerability_info')
    @patch('src.closed_handler._extract_remediation_info')
    @patch('src.closed_handler._validate_pr_event')
    @patch('src.closed_handler._load_github_event')
    @patch('src.telemetry_handler.initialize_telemetry')
    def test_handle_closed_pr_integration(self, mock_init_telemetry, mock_load_event,
                                          mock_validate, mock_extract_remediation,
                                          mock_extract_vuln, mock_notify, mock_send_telemetry):
        """Test handle_closed_pr integration flow"""
        # Mock data
        event_data = {"action": "closed", "pull_request": {"merged": False, "number": 123}}
        pull_request = {"merged": False, "number": 123, "head": {"ref": "smartfix/REM-123"}}

        mock_load_event.return_value = event_data
        mock_validate.return_value = pull_request
        mock_extract_remediation.return_value = ("REM-123", [])
        mock_extract_vuln.return_value = "VULN-456"

        # Call the function
        closed_handler.handle_closed_pr()

        # Verify calls
        mock_init_telemetry.assert_called_once()
        mock_load_event.assert_called_once()
        mock_validate.assert_called_once_with(event_data)
        mock_extract_remediation.assert_called_once_with(pull_request)
        mock_extract_vuln.assert_called_once_with([])
        mock_notify.assert_called_once_with("REM-123", 123)
        mock_send_telemetry.assert_called_once()


if __name__ == '__main__':
    unittest.main()
