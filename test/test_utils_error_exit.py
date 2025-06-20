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
    
    def setUp(self):
        """Set up test environment before each test"""
        # Configure config module for all tests
        config.CONTRAST_HOST = "test-host"
        config.CONTRAST_ORG_ID = "test-org"
        config.CONTRAST_APP_ID = "test-app"
        config.CONTRAST_AUTHORIZATION_KEY = "test-auth"
        config.CONTRAST_API_KEY = "test-api"
        
    def tearDown(self):
        """Clean up after each test"""
        # Reset any changes to the config module
        pass
        
    @contextmanager
    def assert_system_exit(self, expected_code=1):
        """Context manager to assert that sys.exit was called with the expected code"""
        with self.assertRaises(SystemExit) as cm:
            yield
        self.assertEqual(cm.exception.code, expected_code)
        
    def find_log_call(self, mock_log, message, is_warning=False, is_error=False):
        """Helper method to find a specific log call in the mock's call list"""
        expected_call = call(message)
        if is_warning:
            expected_call = call(message, is_warning=True)
        elif is_error:
            expected_call = call(message, is_error=True)
            
        for actual_call in mock_log.call_args_list:
            # For debugging
            print(f"Checking actual call: {actual_call} against expected: {expected_call}")
            # Compare args and kwargs
            if actual_call == expected_call:
                return True
                
        # If not found, print all calls for debugging
        print(f"All mock_log calls: {mock_log.call_args_list}")
        return False

    @patch('sys.exit')
    @patch('src.utils.log')  # Make sure we're patching the correct import path
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
        
        # Check each log message directly
        mock_log.assert_any_call(
            f"Successfully notified Remediation service about {failure_code} for remediation {remediation_id}."
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
        
        # Check the log message directly
        mock_log.assert_any_call(
            f"Successfully notified Remediation service about {default_failure_code} for remediation {remediation_id}."
        )
        
        # Verify other functions were called
        mock_get_branch.assert_called_once_with(remediation_id)
        mock_cleanup.assert_called_once()
        mock_send_telemetry.assert_called_once()
        # Verify sys.exit was called with code 1
        mock_exit.assert_called_once_with(1)

    @patch('sys.exit')
    @patch('src.utils.log')
    @patch('src.git_handler.cleanup_branch')
    @patch('src.git_handler.get_branch_name')
    @patch('src.contrast_api.send_telemetry_data')
    @patch('src.contrast_api.notify_remediation_failed')
    def test_error_exit_notification_failure(self, mock_notify, mock_send_telemetry, mock_get_branch, 
                                           mock_cleanup, mock_log, mock_exit):
        """Test error_exit when notification to remediation service fails"""
        # Setup
        remediation_id = "test-remediation-id"
        failure_code = FailureCategory.INITIAL_BUILD_FAILURE.value
        mock_notify.return_value = False  # Notification fails
        mock_get_branch.return_value = f"smartfix/remediation-{remediation_id}"

        # Execute
        utils.error_exit(remediation_id, failure_code)

        # Assert
        mock_notify.assert_called_once()
        
        # Check the warning log message directly
        mock_log.assert_any_call(
            f"Failed to notify Remediation service about {failure_code} for remediation {remediation_id}.", 
            is_warning=True
        )
        
        # Still calls cleanup and telemetry
        mock_cleanup.assert_called_once()
        mock_send_telemetry.assert_called_once()
        # Verify sys.exit was called with code 1
        mock_exit.assert_called_once_with(1)

    @patch('sys.exit')
    @patch('src.utils.log')
    @patch('src.git_handler.cleanup_branch')
    @patch('src.git_handler.get_branch_name')
    @patch('src.contrast_api.send_telemetry_data')
    @patch('src.contrast_api.notify_remediation_failed')
    def test_error_exit_exception_during_notify(self, mock_notify, mock_send_telemetry, mock_get_branch, 
                                              mock_cleanup, mock_log, mock_exit):
        """Test error_exit when notification raises an exception"""
        # Setup
        remediation_id = "test-remediation-id"
        exception_msg = "API connection error"
        mock_notify.side_effect = Exception(exception_msg)  # Simulate exception
        mock_get_branch.return_value = f"smartfix/remediation-{remediation_id}"

        # Execute
        utils.error_exit(remediation_id)

        # Verify error was logged
        mock_log.assert_any_call(f"Error notifying Remediation service: {exception_msg}", is_error=True)
        
        # Even on exception, should continue with cleanup and telemetry
        mock_cleanup.assert_called_once()
        mock_send_telemetry.assert_called_once()
        mock_exit.assert_called_once_with(1)

    @patch('sys.exit')
    @patch('src.utils.log')
    @patch('src.git_handler.cleanup_branch')
    @patch('src.git_handler.get_branch_name')
    @patch('src.contrast_api.send_telemetry_data')
    @patch('src.contrast_api.notify_remediation_failed')
    def test_error_exit_branch_cleanup_exception(self, mock_notify, mock_send_telemetry, mock_get_branch, 
                                               mock_cleanup, mock_log, mock_exit):
        """Test error_exit when branch cleanup raises an exception"""
        # Setup
        remediation_id = "test-remediation-id"
        failure_code = FailureCategory.GIT_COMMAND_FAILURE.value
        mock_notify.return_value = True
        mock_get_branch.return_value = f"smartfix/remediation-{remediation_id}"
        error_msg = "Git error during cleanup"
        mock_cleanup.side_effect = Exception(error_msg)  # Simulate git error

        # Execute
        utils.error_exit(remediation_id, failure_code)

        # Verify success notification log
        mock_log.assert_any_call(
            f"Successfully notified Remediation service about {failure_code} for remediation {remediation_id}."
        )
        
        # Verify git error log
        mock_log.assert_any_call(
            f"Error cleaning up branch for remediation {remediation_id}: {error_msg}", 
            is_error=True
        )
        
        # Assert notifications were sent despite branch cleanup failure
        mock_notify.assert_called_once()
        # Should still attempt to send telemetry
        mock_send_telemetry.assert_called_once()
        # Verify cleanup was attempted
        mock_cleanup.assert_called_once_with(f"smartfix/remediation-{remediation_id}")
        mock_exit.assert_called_once_with(1)

if __name__ == '__main__':
    unittest.main()
