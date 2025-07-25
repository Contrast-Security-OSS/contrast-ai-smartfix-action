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

# Add project root to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

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
from src.external_coding_agent import ExternalCodingAgent

class TestExternalCodingAgent(unittest.TestCase):
    """Tests for the ExternalCodingAgent class"""
    
    def setUp(self):
        """Set up test environment before each test"""
        # Use the shared TEST_ENV_VARS for consistent environment setup
        self.env_patcher = patch.dict('os.environ', TEST_ENV_VARS)
        self.env_patcher.start()
        reset_config()  # Reset the config singleton
        self.config = get_config(testing=True)
        
    def tearDown(self):
        """Clean up after each test"""
        self.env_patcher.stop()
        reset_config()
    
    @patch('src.external_coding_agent.log')
    def test_constructor(self, mock_log):
        """Test that we can construct an ExternalCodingAgent object"""
        # Create an ExternalCodingAgent object
        agent = ExternalCodingAgent(self.config)
        
        # Assert that the config was set correctly
        self.assertEqual(agent.config, self.config)
        
        # Assert that log was called with the expected message
        mock_log.assert_called_once_with(f"Initialized ExternalCodingAgent")
        
    @patch('src.external_coding_agent.debug_log')
    def test_generate_fixes_with_smartfix(self, mock_debug_log):
        """Test generate_fixes returns False when CODING_AGENT is SMARTFIX"""
        # Set CODING_AGENT to SMARTFIX
        self.config.CODING_AGENT = "SMARTFIX"
        
        # Create an ExternalCodingAgent object
        agent = ExternalCodingAgent(self.config)
        
        # Call generate_fixes
        result = agent.generate_fixes("1234-FAKE-ABCD", "1REM-FAKE-ABCD", "Fake Vulnerability Title")
        
        # Assert that result is False
        self.assertFalse(result)
        
        # Assert that debug_log was called with the expected message
        mock_debug_log.assert_called_once_with("SMARTFIX agent detected, ExternalCodingAgent.generate_fixes returning False")
        
    @patch('src.external_coding_agent.error_exit')
    @patch('src.git_handler.find_issue_with_label')
    @patch('src.git_handler.create_issue')
    @patch('src.git_handler.add_labels_to_pr')
    @patch('src.git_handler.find_open_pr_for_issue')
    @patch('src.external_coding_agent.notify_remediation_pr_opened')
    @patch('src.external_coding_agent.time.sleep')  # Mock sleep to speed up tests
    @patch('src.telemetry_handler.update_telemetry')
    @patch('src.external_coding_agent.debug_log')
    @patch('src.external_coding_agent.log')
    def test_generate_fixes_with_external_agent_pr_created(self, mock_log, mock_debug_log, mock_update_telemetry, 
                                                         mock_sleep, mock_notify, mock_find_pr, mock_add_labels, mock_create_issue, 
                                                         mock_find_issue, mock_error_exit):
        """Test generate_fixes when PR is created successfully"""
        # Set CODING_AGENT to GITHUB_COPILOT
        self.config.CODING_AGENT = "GITHUB_COPILOT"
        
        # Configure mocks
        mock_find_issue.return_value = 42
        
        # Mock the find_open_pr_for_issue to return PR info on first call
        pr_info = {
            "number": 123,
            "url": "https://github.com/owner/repo/pull/123",
            "title": "Fix test issue"
        }
        mock_find_pr.return_value = pr_info
        mock_notify.return_value = True
        mock_add_labels.return_value = True
        
        # Create an ExternalCodingAgent object
        agent = ExternalCodingAgent(self.config)
        
        # Call generate_fixes
        result = agent.generate_fixes("1234-FAKE-ABCD", "1REM-FAKE-ABCD", "Fake Vulnerability Title")

        # Assert that result is True
        self.assertTrue(result)
        
        # Verify log calls
        mock_log.assert_any_call("--- Generating fix with external coding agent ---")
        mock_log.assert_any_call(f"Waiting for external agent to create a PR for issue #42")
        mock_log.assert_any_call(f"External agent created PR #123 at https://github.com/owner/repo/pull/123")
        
        # Verify telemetry updates
        mock_update_telemetry.assert_any_call("additionalAttributes.codingAgent", "EXTERNAL")
        mock_update_telemetry.assert_any_call("resultInfo.prCreated", True)
        mock_update_telemetry.assert_any_call("additionalAttributes.prStatus", "OPEN")
        mock_update_telemetry.assert_any_call("additionalAttributes.prNumber", 123)
        mock_update_telemetry.assert_any_call("additionalAttributes.prUrl", "https://github.com/owner/repo/pull/123")

    @patch('src.external_coding_agent.error_exit')
    @patch('src.git_handler.find_issue_with_label')
    @patch('src.git_handler.create_issue')
    @patch('src.git_handler.find_open_pr_for_issue')
    @patch('src.external_coding_agent.time.sleep')
    @patch('src.telemetry_handler.update_telemetry')
    @patch('src.external_coding_agent.debug_log')
    @patch('src.external_coding_agent.log')
    def test_generate_fixes_with_external_agent_pr_timeout(self, mock_log, mock_debug_log, mock_update_telemetry, 
                                                         mock_sleep, mock_find_pr, mock_create_issue, mock_find_issue, mock_error_exit):
        """Test generate_fixes when PR creation times out"""
        # Set CODING_AGENT to GITHUB_COPILOT
        self.config.CODING_AGENT = "GITHUB_COPILOT"
        
        # Configure mock
        mock_find_issue.return_value = 42
        
        # Mock the find_open_pr_for_issue to always return None (no PR found)
        mock_find_pr.return_value = None
        
        # Create an ExternalCodingAgent object with a small max_attempts to speed up the test
        agent = ExternalCodingAgent(self.config)
        
        # Mock _poll_for_pr instead of patching it
        mock_poll_for_pr = MagicMock(return_value=None)
        original_poll_for_pr = agent._poll_for_pr
        agent._poll_for_pr = mock_poll_for_pr
        
        try:
            # Call generate_fixes
            result = agent.generate_fixes("1234-FAKE-ABCD", "1REM-FAKE-ABCD", "Fake Vulnerability Title")

            # Assert that result is False when PR is not created
            self.assertFalse(result)
            
            # Verify _poll_for_pr was called with the right parameters
            mock_poll_for_pr.assert_called_once_with(42, "1REM-FAKE-ABCD", 'contrast-vuln-id:VULN-1234-FAKE-ABCD', 'smartfix-id:1REM-FAKE-ABCD', max_attempts=100, sleep_seconds=5)
        finally:
            # Restore original method
            agent._poll_for_pr = original_poll_for_pr
        
        # Verify log calls
        mock_log.assert_any_call("--- Generating fix with external coding agent ---")
        mock_log.assert_any_call(f"Waiting for external agent to create a PR for issue #42")
        mock_log.assert_any_call("External agent failed to create a PR within the timeout period", is_error=True)
        
        # Verify telemetry updates
        mock_update_telemetry.assert_any_call("additionalAttributes.codingAgent", "EXTERNAL")
        mock_update_telemetry.assert_any_call("resultInfo.prCreated", False)
        mock_update_telemetry.assert_any_call("resultInfo.failureReason", "PR creation timeout")
        mock_update_telemetry.assert_any_call("resultInfo.failureCategory", "AGENT_FAILURE")
    
    @patch('src.git_handler.find_issue_with_label')
    @patch('src.git_handler.reset_issue')
    @patch('src.git_handler.find_open_pr_for_issue')
    @patch('src.external_coding_agent.notify_remediation_pr_opened')
    @patch('src.external_coding_agent.time.sleep')
    @patch('src.telemetry_handler.update_telemetry')
    @patch('src.external_coding_agent.debug_log')
    @patch('src.external_coding_agent.log')
    def test_generate_fixes_with_existing_issue(self, mock_log, mock_debug_log, mock_update_telemetry, 
                                               mock_sleep, mock_notify, mock_find_pr, mock_reset_issue, 
                                               mock_find_issue):
        """Test generate_fixes when an existing GitHub issue is found"""
        # Set CODING_AGENT to GITHUB_COPILOT
        self.config.CODING_AGENT = "GITHUB_COPILOT"
        
        # Mock the find_issue_with_label to return an issue number
        mock_find_issue.return_value = 42
        
        # Mock PR info to be returned
        pr_info = {
            "number": 123,
            "url": "https://github.com/owner/repo/pull/123",
            "title": "Fix test issue"
        }
        mock_find_pr.return_value = pr_info
        mock_notify.return_value = True
        
        # Create an ExternalCodingAgent object
        agent = ExternalCodingAgent(self.config)
        
        # Mock _poll_for_pr instead of patching it
        mock_poll_for_pr = MagicMock(return_value=pr_info)
        original_poll_for_pr = agent._poll_for_pr
        agent._poll_for_pr = mock_poll_for_pr
        
        try:
            # Call generate_fixes
            result = agent.generate_fixes("1234-FAKE-ABCD", "1REM-FAKE-ABCD", "Fake Vulnerability Title")

            # Assert that result is True
            self.assertTrue(result)
            
            # Verify poll was called correctly
            mock_poll_for_pr.assert_called_once_with(42, "1REM-FAKE-ABCD", 'contrast-vuln-id:VULN-1234-FAKE-ABCD', 'smartfix-id:1REM-FAKE-ABCD', max_attempts=100, sleep_seconds=5)
        finally:
            # Restore original method
            agent._poll_for_pr = original_poll_for_pr
        
        # Verify that log was called with the expected message
        mock_log.assert_any_call("--- Generating fix with external coding agent ---")
        
        # Verify there's a call about finding an existing issue
        mock_debug_log.assert_any_call("Found existing GitHub issue #42 with label contrast-vuln-id:VULN-1234-FAKE-ABCD")
        
        # Verify reset_issue was called
        mock_reset_issue.assert_called_once_with(42, "smartfix-id:1REM-FAKE-ABCD")

    @patch('src.git_handler.add_labels_to_pr')
    @patch('src.git_handler.find_open_pr_for_issue')
    @patch('src.external_coding_agent.notify_remediation_pr_opened')
    @patch('src.external_coding_agent.time.sleep')  # Mock sleep to speed up tests
    @patch('src.external_coding_agent.log')
    @patch('src.external_coding_agent.debug_log')
    def test_poll_for_pr_found_immediately(self, mock_debug_log, mock_log, mock_sleep, mock_notify, mock_find_pr, mock_add_labels):
        """Test _poll_for_pr when PR is found on first attempt"""
        # Configure mocks
        pr_info = {
            "number": 123,
            "url": "https://github.com/owner/repo/pull/123",
            "title": "Fix test issue"
        }
        mock_find_pr.return_value = pr_info
        mock_notify.return_value = True
        mock_add_labels.return_value = True
        
        agent = ExternalCodingAgent(self.config)
        # Use very small max_attempts and sleep_seconds to speed up tests
        result = agent._poll_for_pr(issue_number=456, remediation_id="REM-789", vulnerability_label="contrast-vuln-id:VULN-1234-FAKE-ABCD", remediation_label="smartfix-id:1REM-FAKE-ABCD", max_attempts=3, sleep_seconds=0.01)

        # Verify results
        self.assertEqual(result, pr_info)
        mock_find_pr.assert_called_once_with(456)
        mock_notify.assert_called_once_with(
            remediation_id="REM-789",
            pr_number=123,
            pr_url="https://github.com/owner/repo/pull/123",
            contrast_host=self.config.CONTRAST_HOST,
            contrast_org_id=self.config.CONTRAST_ORG_ID,
            contrast_app_id=self.config.CONTRAST_APP_ID,
            contrast_auth_key=self.config.CONTRAST_AUTHORIZATION_KEY,
            contrast_api_key=self.config.CONTRAST_API_KEY
        )
        # Sleep should not be called since we found the PR on first attempt
        mock_sleep.assert_not_called()
    
    @patch('src.git_handler.add_labels_to_pr')
    @patch('src.git_handler.find_open_pr_for_issue')
    @patch('src.external_coding_agent.notify_remediation_pr_opened')
    @patch('src.external_coding_agent.time.sleep')
    @patch('src.external_coding_agent.log')
    @patch('src.external_coding_agent.debug_log')
    def test_poll_for_pr_found_after_retries(self, mock_debug_log, mock_log, mock_sleep, mock_notify, mock_find_pr, mock_add_labels):
        """Test _poll_for_pr when PR is found after several attempts"""
        # Configure mocks
        pr_info = {
            "number": 123,
            "url": "https://github.com/owner/repo/pull/123",
            "title": "Fix test issue"
        }
        # Return None twice, then return PR info
        mock_find_pr.side_effect = [None, None, pr_info]
        mock_notify.return_value = True
        mock_add_labels.return_value = True
        
        agent = ExternalCodingAgent(self.config)
        # Use very small max_attempts and sleep_seconds to speed up tests
        result = agent._poll_for_pr(issue_number=456, remediation_id="REM-789", vulnerability_label="contrast-vuln-id:VULN-12345", remediation_label="smartfix-id:remediation-67890", max_attempts=3, sleep_seconds=0.01)
        
        # Verify results
        self.assertEqual(result, pr_info)
        self.assertEqual(mock_find_pr.call_count, 3)
        mock_notify.assert_called_once()
        mock_add_labels.assert_called_once_with(123, ["contrast-vuln-id:VULN-12345", "smartfix-id:remediation-67890"])
        # Sleep should be called twice (after first and second attempts)
        self.assertEqual(mock_sleep.call_count, 2)
        for call in mock_sleep.call_args_list:
            self.assertEqual(call[0][0], 0.01)  # Verify sleep called with 0.01 seconds
        
    @patch('src.git_handler.find_open_pr_for_issue')
    @patch('src.external_coding_agent.notify_remediation_pr_opened')
    @patch('src.external_coding_agent.time.sleep')
    @patch('src.external_coding_agent.log')
    @patch('src.external_coding_agent.debug_log')
    def test_poll_for_pr_not_found(self, mock_debug_log, mock_log, mock_sleep, mock_notify, mock_find_pr):
        """Test _poll_for_pr when PR is never found"""
        # Configure mocks
        mock_find_pr.return_value = None
        
        agent = ExternalCodingAgent(self.config)
        # Use very small max_attempts and sleep_seconds to speed up tests
        result = agent._poll_for_pr(issue_number=456, remediation_id="REM-789", vulnerability_label="contrast-vuln-id:VULN-12345", remediation_label="smartfix-id:remediation-67890", max_attempts=3, sleep_seconds=0.01)
        
        # Verify results
        self.assertIsNone(result)
        self.assertEqual(mock_find_pr.call_count, 3)
        mock_notify.assert_not_called()
        # Sleep should be called twice (after first and second attempts)
        self.assertEqual(mock_sleep.call_count, 2)
        for call in mock_sleep.call_args_list:
            self.assertEqual(call[0][0], 0.01)  # Verify sleep called with 0.01 seconds
    
    @patch('src.git_handler.add_labels_to_pr')
    @patch('src.git_handler.find_open_pr_for_issue')
    @patch('src.external_coding_agent.notify_remediation_pr_opened')
    @patch('src.external_coding_agent.time.sleep')
    @patch('src.external_coding_agent.log')
    @patch('src.external_coding_agent.debug_log')
    def test_poll_for_pr_notification_failure(self, mock_debug_log, mock_log, mock_sleep, mock_notify, mock_find_pr, mock_add_labels):
        """Test _poll_for_pr when PR is found but notification fails"""
        # Configure mocks
        pr_info = {
            "number": 123,
            "url": "https://github.com/owner/repo/pull/123",
            "title": "Fix test issue"
        }
        mock_find_pr.return_value = pr_info
        mock_notify.return_value = False  # Notification fails
        mock_add_labels.return_value = True
        
        agent = ExternalCodingAgent(self.config)
        # Use very small max_attempts and sleep_seconds to speed up tests
        result = agent._poll_for_pr(issue_number=456, remediation_id="REM-789", vulnerability_label="contrast-vuln-id:VULN-12345", remediation_label="smartfix-id:remediation-67890", max_attempts=3, sleep_seconds=0.01)
        
        # Verify results
        self.assertEqual(result, pr_info)  # Still returns PR info even if notification fails
        mock_notify.assert_called_once()
        mock_add_labels.assert_called_once_with(123, ["contrast-vuln-id:VULN-12345", "smartfix-id:remediation-67890"])
        mock_find_pr.assert_called_once()
        # No sleep calls needed
        mock_sleep.assert_not_called()

if __name__ == '__main__':
    unittest.main()
