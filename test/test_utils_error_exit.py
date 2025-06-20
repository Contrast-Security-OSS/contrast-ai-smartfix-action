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
        for actual_call in mock_log.call_args_list:
            # For simplicity, just check if the message string is in the call args
            args, kwargs = actual_call
            if args and message in args[0]:
                # If we need to verify warning/error flags
                if is_warning and kwargs.get('is_warning', False):
                    return True
                elif is_error and kwargs.get('is_error', False):
                    return True
                elif not is_warning and not is_error and not kwargs.get('is_warning', False) and not kwargs.get('is_error', False):
                    return True
                
        # If not found, print all calls for debugging
        print(f"All mock_log calls: {mock_log.call_args_list}")
        print(f"Failed to find message: {message}")
        return False

    @patch('sys.exit')
    @patch('utils.log')  # Directly patch the module function
    @patch('git_handler.cleanup_branch')
    @patch('git_handler.get_branch_name')
    @patch('contrast_api.send_telemetry_data')
    @patch('contrast_api.notify_remediation_failed')
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
        
        # Check each log message using our helper
        success_message = f"Successfully notified Remediation service about {failure_code} for remediation {remediation_id}."
        self.assertTrue(self.find_log_call(mock_log, success_message), f"Expected log message not found: {success_message}")
        
        # Verify other function calls
        mock_get_branch.assert_called_once_with(remediation_id)
        mock_cleanup.assert_called_once_with(f"smartfix/remediation-{remediation_id}")
        mock_send_telemetry.assert_called_once()
        # Verify sys.exit was called with code 1
        mock_exit.assert_called_once_with(1)

    @patch('sys.exit')
    @patch('utils.log')
    @patch('git_handler.cleanup_branch')
    @patch('git_handler.get_branch_name')
    @patch('contrast_api.send_telemetry_data')
    @patch('contrast_api.notify_remediation_failed')
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
        
        # Check the log message using our helper
        success_message = f"Successfully notified Remediation service about {default_failure_code} for remediation {remediation_id}."
        self.assertTrue(self.find_log_call(mock_log, success_message), f"Expected log message not found: {success_message}")
        
        # Verify other functions were called
        mock_get_branch.assert_called_once_with(remediation_id)
        mock_cleanup.assert_called_once()
        mock_send_telemetry.assert_called_once()
        # Verify sys.exit was called with code 1
        mock_exit.assert_called_once_with(1)

if __name__ == '__main__':
    unittest.main()
