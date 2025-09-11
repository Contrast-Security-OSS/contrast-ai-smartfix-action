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

import unittest
from unittest.mock import patch
from contextlib import contextmanager

# Test setup imports (path is set up by conftest.py)
from setup_test_env import TestEnvironmentMixin
from src import utils
from src.config import get_config, reset_config
from src.contrast_api import FailureCategory


class TestErrorExit(unittest.TestCase, TestEnvironmentMixin):
    """Tests for the error_exit function in utils.py"""

    def setUp(self):
        """Set up test environment before each test"""
        self.setup_standard_test_env()
        reset_config()  # Reset the config singleton

    def tearDown(self):
        """Clean up after each test"""
        self.cleanup_standard_test_env()
        reset_config()

    @contextmanager
    def assert_system_exit(self, expected_code=1):
        """Context manager to assert that sys.exit was called with the expected code"""
        with self.assertRaises(SystemExit) as cm:
            yield
        self.assertEqual(cm.exception.code, expected_code)

    @patch('sys.exit')
    @patch('src.utils.log')  # Directly patch the module function
    @patch('src.git_handler.cleanup_branch')
    @patch('src.git_handler.get_branch_name')
    @patch('src.contrast_api.send_telemetry_data')
    @patch('src.contrast_api.notify_remediation_failed')
    def test_error_exit_with_failure_code(self, mock_notify, mock_send_telemetry, mock_get_branch,
                                          mock_cleanup, mock_log, mock_exit):
        """Test error_exit when a specific failure code is provided"""
        # Setup
        remediation_id = "test-remediation-id"
        failure_code = FailureCategory.AGENT_FAILURE.value
        mock_notify.return_value = True  # Notification succeeds
        mock_get_branch.return_value = f"smartfix/remediation-{remediation_id}"
        config = get_config(testing=True)

        # Execute the function
        utils.error_exit(remediation_id, failure_code)

        # Assert
        mock_notify.assert_called_once_with(
            remediation_id=remediation_id,
            failure_category=failure_code,
            contrast_host=config.CONTRAST_HOST,
            contrast_org_id=config.CONTRAST_ORG_ID,
            contrast_app_id=config.CONTRAST_APP_ID,
            contrast_auth_key=config.CONTRAST_AUTHORIZATION_KEY,
            contrast_api_key=config.CONTRAST_API_KEY
        )

        # Verify other function calls
        mock_get_branch.assert_called_once_with(remediation_id)
        mock_cleanup.assert_called_once_with(f"smartfix/remediation-{remediation_id}")
        mock_send_telemetry.assert_called_once()
        # Verify sys.exit was called with code 1
        mock_exit.assert_called_once_with(1)

    @patch('sys.exit')
    @patch('src.utils.log')
    @patch('src.git_handler.cleanup_branch')
    @patch('src.git_handler.get_branch_name')
    @patch('src.contrast_api.send_telemetry_data')
    @patch('src.contrast_api.notify_remediation_failed')
    def test_error_exit_default_failure_code(self, mock_notify, mock_send_telemetry, mock_get_branch,
                                             mock_cleanup, mock_log, mock_exit):
        """Test error_exit when no failure code is provided (uses default)"""
        # Setup
        remediation_id = "test-remediation-id"
        default_failure_code = FailureCategory.GENERAL_FAILURE.value
        mock_notify.return_value = True
        mock_get_branch.return_value = f"smartfix/remediation-{remediation_id}"
        config = get_config(testing=True)

        # Execute
        utils.error_exit(remediation_id)

        # Assert
        mock_notify.assert_called_once_with(
            remediation_id=remediation_id,
            failure_category=default_failure_code,
            contrast_host=config.CONTRAST_HOST,
            contrast_org_id=config.CONTRAST_ORG_ID,
            contrast_app_id=config.CONTRAST_APP_ID,
            contrast_auth_key=config.CONTRAST_AUTHORIZATION_KEY,
            contrast_api_key=config.CONTRAST_API_KEY
        )

        # Verify other functions were called
        mock_get_branch.assert_called_once_with(remediation_id)
        mock_cleanup.assert_called_once()
        mock_send_telemetry.assert_called_once()
        # Verify sys.exit was called with code 1
        mock_exit.assert_called_once_with(1)


if __name__ == '__main__':
    unittest.main()
