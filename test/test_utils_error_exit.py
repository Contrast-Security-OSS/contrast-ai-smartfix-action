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
from unittest.mock import patch, MagicMock, call
from contextlib import contextmanager

# Import the function we want to test
sys.path.append('src')  # Add src directory to path
import utils
import config
from contrast_api import FailureCategory

class TestErrorExit(unittest.TestCase):
    """Tests for the error_exit function in utils.py"""

    @contextmanager
    def assert_system_exit(self, expected_code=1):
        """Context manager to assert that sys.exit was called with the expected code"""
        with self.assertRaises(SystemExit) as cm:
            yield
        self.assertEqual(cm.exception.code, expected_code)

    @patch('utils.log')
    @patch('utils.cleanup_branch')
    @patch('utils.get_branch_name')
    @patch('utils.send_telemetry_data')
    @patch('utils.notify_remediation_failed')
    def test_error_exit_with_failure_code(self, mock_notify, mock_send_telemetry, mock_get_branch, 
                                         mock_cleanup, mock_log):
        """Test error_exit when a specific failure code is provided"""
        # Setup
        remediation_id = "test-remediation-id"
        failure_code = FailureCategory.AGENT_FAILURE.value
        mock_notify.return_value = True  # Notification succeeds
        mock_get_branch.return_value = f"smartfix/remediation-{remediation_id}"
        
        # Configure config module
        config.CONTRAST_HOST = "test-host"
        config.CONTRAST_ORG_ID = "test-org"
        config.CONTRAST_APP_ID = "test-app"
        config.CONTRAST_AUTHORIZATION_KEY = "test-auth"
        config.CONTRAST_API_KEY = "test-api"

        # Execute the function and verify it calls sys.exit(1)
        with self.assert_system_exit():
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
        
        # Verify success log message
        mock_log.assert_any_call(
            f"Successfully notified Remediation service about {failure_code} for remediation {remediation_id}."
        )
        
        # Verify other function calls
        mock_get_branch.assert_called_once_with(remediation_id)
        mock_cleanup.assert_called_once_with(f"smartfix/remediation-{remediation_id}")
        mock_send_telemetry.assert_called_once()

    @patch('utils.log')
    @patch('utils.cleanup_branch')
    @patch('utils.get_branch_name')
    @patch('utils.send_telemetry_data')
    @patch('utils.notify_remediation_failed')
    def test_error_exit_default_failure_code(self, mock_notify, mock_send_telemetry, mock_get_branch, 
                                            mock_cleanup, mock_log):
        """Test error_exit when no failure code is provided (uses default)"""
        # Setup
        remediation_id = "test-remediation-id"
        default_failure_code = FailureCategory.GENERAL_FAILURE.value
        mock_notify.return_value = True
        mock_get_branch.return_value = f"smartfix/remediation-{remediation_id}"

        # Execute
        with self.assert_system_exit():
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
        
        mock_log.assert_any_call(
            f"Successfully notified Remediation service about {default_failure_code} for remediation {remediation_id}."
        )

    @patch('utils.log')
    @patch('utils.cleanup_branch')
    @patch('utils.get_branch_name')
    @patch('utils.send_telemetry_data')
    @patch('utils.notify_remediation_failed')
    def test_error_exit_notification_failure(self, mock_notify, mock_send_telemetry, mock_get_branch, 
                                           mock_cleanup, mock_log):
        """Test error_exit when notification to remediation service fails"""
        # Setup
        remediation_id = "test-remediation-id"
        failure_code = FailureCategory.INITIAL_BUILD_FAILURE.value
        mock_notify.return_value = False  # Notification fails
        mock_get_branch.return_value = f"smartfix/remediation-{remediation_id}"

        # Execute
        with self.assert_system_exit():
            utils.error_exit(remediation_id, failure_code)

        # Assert
        mock_notify.assert_called_once()
        
        # Verify failure log message with is_warning flag
        mock_log.assert_any_call(
            f"Failed to notify Remediation service about {failure_code} for remediation {remediation_id}.",
            is_warning=True
        )
        
        # Still calls cleanup and telemetry
        mock_cleanup.assert_called_once()
        mock_send_telemetry.assert_called_once()

    @patch('utils.log')
    @patch('utils.cleanup_branch')
    @patch('utils.get_branch_name')
    @patch('utils.send_telemetry_data')
    @patch('utils.notify_remediation_failed')
    def test_error_exit_exception_during_notify(self, mock_notify, mock_send_telemetry, mock_get_branch, 
                                              mock_cleanup, mock_log):
        """Test error_exit when notification raises an exception"""
        # Setup
        remediation_id = "test-remediation-id"
        mock_notify.side_effect = Exception("API connection error")  # Simulate exception
        mock_get_branch.return_value = f"smartfix/remediation-{remediation_id}"

        # Execute
        with self.assert_system_exit():
            utils.error_exit(remediation_id)

        # Even on exception, should continue with cleanup and telemetry
        mock_cleanup.assert_called_once()
        mock_send_telemetry.assert_called_once()

    @patch('utils.log')
    @patch('utils.cleanup_branch')
    @patch('utils.get_branch_name')
    @patch('utils.send_telemetry_data')
    @patch('utils.notify_remediation_failed')
    def test_error_exit_branch_cleanup_exception(self, mock_notify, mock_send_telemetry, mock_get_branch, 
                                               mock_cleanup, mock_log):
        """Test error_exit when branch cleanup raises an exception"""
        # Setup
        remediation_id = "test-remediation-id"
        failure_code = FailureCategory.GIT_COMMAND_FAILURE.value
        mock_notify.return_value = True
        mock_get_branch.return_value = f"smartfix/remediation-{remediation_id}"
        mock_cleanup.side_effect = Exception("Git error during cleanup")  # Simulate git error

        # Execute
        with self.assert_system_exit():
            utils.error_exit(remediation_id, failure_code)

        # Assert notifications were sent despite branch cleanup failure
        mock_notify.assert_called_once()
        # Should still attempt to send telemetry
        mock_send_telemetry.assert_called_once()
        # Verify cleanup was attempted
        mock_cleanup.assert_called_once_with(f"smartfix/remediation-{remediation_id}")

if __name__ == '__main__':
    unittest.main()
