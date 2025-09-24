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
from unittest.mock import patch, MagicMock

# Test setup imports (path is set up by conftest.py)
from src.config import get_config, reset_config
from src.github.external_coding_agent import ExternalCodingAgent
from src.smartfix.domains.vulnerability import Vulnerability
from src.smartfix.domains.vulnerability.context import RemediationContext


class TestExternalCodingAgent(unittest.TestCase):
    """Tests for the ExternalCodingAgent class"""

    def setUp(self):
        """Set up test environment before each test"""
        reset_config()  # Reset the config singleton
        self.config = get_config(testing=True)

    def tearDown(self):
        """Clean up after each test"""
        reset_config()

    def _create_test_context(self, remediation_id="REM-789", vuln_uuid="1234-FAKE-ABCD", vuln_title="Fake Vulnerability Title"):
        """Helper method to create a proper test RemediationContext"""
        from src.smartfix.domains.vulnerability import VulnerabilitySeverity

        # Create a mock vulnerability with correct parameters
        vulnerability = Vulnerability(
            uuid=vuln_uuid,
            title=vuln_title,
            rule_name="TestRule",
            severity=VulnerabilitySeverity.HIGH
        )

        # Create remediation context
        context = RemediationContext.create(remediation_id, vulnerability, self.config)
        # Add issue_body for external agent compatibility
        context.issue_body = "Test issue body"
        return context

    @patch('src.github.external_coding_agent.log')
    def test_constructor(self, mock_log):
        """Test that we can construct an ExternalCodingAgent object"""
        # Create an ExternalCodingAgent object
        agent = ExternalCodingAgent(self.config)

        # Assert that the config was set correctly
        self.assertEqual(agent.config, self.config)

    @patch('src.github.external_coding_agent.debug_log')
    def test_remediate_with_smartfix(self, mock_debug_log):
        """Test remediate returns error result when CODING_AGENT is SMARTFIX"""
        # Set CODING_AGENT to SMARTFIX
        self.config.CODING_AGENT = "SMARTFIX"

        # Create an ExternalCodingAgent object
        agent = ExternalCodingAgent(self.config)

        # Create proper test context
        context = self._create_test_context()        # Call remediate
        result = agent.remediate(context)

        # Assert that result is False
        self.assertFalse(result.success)

        # Assert that debug_log was called with the expected message
        mock_debug_log.assert_called_with("SMARTFIX agent detected, ExternalCodingAgent should not be used")

    @patch('src.github.external_coding_agent.error_exit')
    @patch('src.git_handler.find_issue_with_label')
    @patch('src.git_handler.create_issue')
    @patch('src.git_handler.add_labels_to_pr')
    @patch('src.git_handler.find_open_pr_for_issue')
    @patch('src.contrast_api.notify_remediation_pr_opened')
    @patch('src.github.external_coding_agent.time.sleep')  # Mock sleep to speed up tests
    @patch('src.telemetry_handler.update_telemetry')
    @patch('src.github.external_coding_agent.debug_log')
    @patch('src.github.external_coding_agent.log')
    def test_remediate_with_external_agent_pr_created(self, mock_log, mock_debug_log, mock_update_telemetry,
                                                      mock_sleep, mock_notify, mock_find_pr, mock_add_labels, mock_create_issue,
                                                      mock_find_issue, mock_error_exit):
        """Test remediate when PR is created successfully"""
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

        # Create proper test context
        context = self._create_test_context(remediation_id='1REM-FAKE-ABCD')
        # Add issue_body for external agent compatibility
        context.issue_body = 'Fake issue body.'

        # Call remediate
        result = agent.remediate(context)

        # Assert that result is successful
        self.assertTrue(result.success)

        # Verify log calls
        mock_log.assert_any_call("Waiting for external agent to create a PR for issue #42")
        mock_log.assert_any_call("External agent created PR #123 at https://github.com/owner/repo/pull/123")

        # Verify telemetry updates
        mock_update_telemetry.assert_any_call("additionalAttributes.codingAgent", "EXTERNAL-COPILOT")
        mock_update_telemetry.assert_any_call("resultInfo.prCreated", True)
        mock_update_telemetry.assert_any_call("additionalAttributes.prStatus", "OPEN")
        mock_update_telemetry.assert_any_call("additionalAttributes.prNumber", 123)
        mock_update_telemetry.assert_any_call("additionalAttributes.prUrl", "https://github.com/owner/repo/pull/123")

    @patch('src.github.external_coding_agent.error_exit')
    @patch('src.git_handler.find_issue_with_label')
    @patch('src.git_handler.create_issue')
    @patch('src.git_handler.find_open_pr_for_issue')
    @patch('src.github.external_coding_agent.time.sleep')
    @patch('src.telemetry_handler.update_telemetry')
    @patch('src.github.external_coding_agent.debug_log')
    @patch('src.github.external_coding_agent.log')
    def test_remediate_with_external_agent_pr_timeout(self, mock_log, mock_debug_log, mock_update_telemetry,
                                                      mock_sleep, mock_find_pr, mock_create_issue, mock_find_issue, mock_error_exit):
        """Test remediate when PR creation times out"""
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

        # Create proper test context
        context = self._create_test_context(remediation_id='1REM-FAKE-ABCD')
        # Add issue_body for external agent compatibility
        context.issue_body = 'Fake issue body.'

        try:
            # Call remediate
            result = agent.remediate(context)

            # Assert that result is False when PR is not created
            self.assertFalse(result.success)

            # Verify _poll_for_pr was called with the right parameters
            mock_poll_for_pr.assert_called_once_with(42, "1REM-FAKE-ABCD", 'contrast-vuln-id:VULN-1234-FAKE-ABCD', 'smartfix-id:1REM-FAKE-ABCD', max_attempts=100, sleep_seconds=5)
        finally:
            # Restore original method
            agent._poll_for_pr = original_poll_for_pr

        # Verify log calls
        mock_log.assert_any_call("Waiting for external agent to create a PR for issue #42")
        mock_log.assert_any_call("External agent failed to create a PR within the timeout period", is_error=True)

        # Verify telemetry updates
        mock_update_telemetry.assert_any_call("additionalAttributes.codingAgent", "EXTERNAL-COPILOT")
        mock_update_telemetry.assert_any_call("resultInfo.prCreated", False)
        mock_update_telemetry.assert_any_call("resultInfo.failureReason", "PR creation timeout")
        mock_update_telemetry.assert_any_call("resultInfo.failureCategory", "AGENT_FAILURE")

    @patch('src.git_handler.find_issue_with_label')
    @patch('src.git_handler.reset_issue')
    @patch('src.git_handler.find_open_pr_for_issue')
    @patch('src.contrast_api.notify_remediation_pr_opened')
    @patch('src.github.external_coding_agent.time.sleep')
    @patch('src.telemetry_handler.update_telemetry')
    @patch('src.github.external_coding_agent.debug_log')
    @patch('src.github.external_coding_agent.log')
    def test_remediate_with_existing_issue(self, mock_log, mock_debug_log, mock_update_telemetry,
                                           mock_sleep, mock_notify, mock_find_pr, mock_reset_issue,
                                           mock_find_issue):
        """Test remediate when an existing GitHub issue is found"""
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

        # Create proper test context
        context = self._create_test_context(remediation_id='1REM-FAKE-ABCD')
        # Add issue_body for external agent compatibility
        context.issue_body = 'Fake issue body.'

        try:
            # Call remediate
            result = agent.remediate(context)

            # Assert that result is successful
            self.assertTrue(result.success)

            # Verify poll was called correctly
            mock_poll_for_pr.assert_called_once_with(42, "1REM-FAKE-ABCD", 'contrast-vuln-id:VULN-1234-FAKE-ABCD', 'smartfix-id:1REM-FAKE-ABCD', max_attempts=100, sleep_seconds=5)
        finally:
            # Restore original method
            agent._poll_for_pr = original_poll_for_pr

        # Verify there's a call about finding an existing issue
        mock_debug_log.assert_any_call("Found existing GitHub issue #42 with label contrast-vuln-id:VULN-1234-FAKE-ABCD")

        # Verify reset_issue was called
        mock_reset_issue.assert_called_once_with(42, "smartfix-id:1REM-FAKE-ABCD")

    @patch('src.git_handler.check_issues_enabled')
    @patch('src.git_handler.find_issue_with_label')
    @patch('src.git_handler.create_issue')
    @patch('src.github.external_coding_agent.time.sleep')  # Mock sleep to prevent actual sleeping
    @patch('src.github.external_coding_agent.error_exit')
    @patch('src.github.external_coding_agent.log')
    @patch('src.github.external_coding_agent.debug_log')
    def test_remediate_with_issues_disabled(self, mock_debug_log, mock_log, mock_error_exit, mock_sleep, mock_create_issue, mock_find_issue, mock_check_issues):
        """Test remediate when GitHub Issues are disabled"""
        from src.contrast_api import FailureCategory

        # Configure mock data
        vuln_uuid = 'vuln-uuid-123'
        remediation_id = '1REM-FAKE-ABCD'
        vuln_title = "Test SQL Injection Vulnerability"
        issue_body = "Test issue body for vulnerability"

        # Configure mocks - Issues are disabled
        mock_check_issues.return_value = False
        mock_find_issue.return_value = None  # This should trigger the check

        # Make error_exit raise an exception to stop execution (simulating sys.exit behavior)
        mock_error_exit.side_effect = SystemExit("Mocked exit for Issues disabled")

        # Create agent instance and set CODING_AGENT to external agent
        agent = ExternalCodingAgent(self.config)
        agent.config.CODING_AGENT = "GITHUB_COPILOT"  # Set to external agent to avoid early return

        # Create proper test context
        context = self._create_test_context(remediation_id=remediation_id, vuln_uuid=vuln_uuid, vuln_title=vuln_title)
        # Add issue_body for external agent compatibility
        context.issue_body = issue_body

        # Execute and expect SystemExit due to Issues being disabled
        with self.assertRaises(SystemExit):
            agent.remediate(context)

        # Verify Issues disabled check was called and error_exit was triggered
        mock_find_issue.assert_called_once_with("contrast-vuln-id:VULN-vuln-uuid-123")
        mock_check_issues.assert_called_once()
        mock_error_exit.assert_called_once_with("1REM-FAKE-ABCD", FailureCategory.GIT_COMMAND_FAILURE.value)
        mock_log.assert_any_call("GitHub Issues are disabled for this repository. External coding agent requires Issues to be enabled.", is_error=True)

        # Verify create_issue was not called since Issues are disabled
        mock_create_issue.assert_not_called()

        # Verify sleep was not called since execution should stop at error_exit
        mock_sleep.assert_not_called()

    @patch('src.git_handler.add_labels_to_pr')
    @patch('src.git_handler.find_open_pr_for_issue')
    @patch('src.github.external_coding_agent.notify_remediation_pr_opened')
    @patch('src.github.external_coding_agent.time.sleep')  # Mock sleep to speed up tests
    @patch('src.github.external_coding_agent.log')
    @patch('src.github.external_coding_agent.debug_log')
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
        result = agent._poll_for_pr(
            issue_number=456,
            remediation_id="REM-789",
            vulnerability_label="contrast-vuln-id:VULN-1234-FAKE-ABCD",
            remediation_label="smartfix-id:1REM-FAKE-ABCD",
            max_attempts=3,
            sleep_seconds=0.01
        )

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
    @patch('src.github.external_coding_agent.notify_remediation_pr_opened')
    @patch('src.github.external_coding_agent.time.sleep')
    @patch('src.github.external_coding_agent.log')
    @patch('src.github.external_coding_agent.debug_log')
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
        result = agent._poll_for_pr(
            issue_number=456,
            remediation_id="REM-789",
            vulnerability_label="contrast-vuln-id:VULN-12345",
            remediation_label="smartfix-id:remediation-67890",
            max_attempts=3,
            sleep_seconds=0.01
        )

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
    @patch('src.contrast_api.notify_remediation_pr_opened')
    @patch('src.github.external_coding_agent.time.sleep')
    @patch('src.github.external_coding_agent.log')
    @patch('src.github.external_coding_agent.debug_log')
    def test_poll_for_pr_not_found(self, mock_debug_log, mock_log, mock_sleep, mock_notify, mock_find_pr):
        """Test _poll_for_pr when PR is never found"""
        # Configure mocks
        mock_find_pr.return_value = None

        agent = ExternalCodingAgent(self.config)
        # Use very small max_attempts and sleep_seconds to speed up tests
        result = agent._poll_for_pr(
            issue_number=456,
            remediation_id="REM-789",
            vulnerability_label="contrast-vuln-id:VULN-12345",
            remediation_label="smartfix-id:remediation-67890",
            max_attempts=3,
            sleep_seconds=0.01
        )

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
    @patch('src.github.external_coding_agent.notify_remediation_pr_opened')
    @patch('src.github.external_coding_agent.time.sleep')
    @patch('src.github.external_coding_agent.log')
    @patch('src.github.external_coding_agent.debug_log')
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
        result = agent._poll_for_pr(
            issue_number=456,
            remediation_id="REM-789",
            vulnerability_label="contrast-vuln-id:VULN-12345",
            remediation_label="smartfix-id:remediation-67890",
            max_attempts=3,
            sleep_seconds=0.01
        )

        # Verify results
        self.assertEqual(result, pr_info)  # Still returns PR info even if notification fails
        mock_notify.assert_called_once()
        mock_add_labels.assert_called_once_with(123, ["contrast-vuln-id:VULN-12345", "smartfix-id:remediation-67890"])
        mock_find_pr.assert_called_once()
        # No sleep calls needed
        mock_sleep.assert_not_called()

    def test_assemble_issue_body_with_all_data(self):
        """Test assemble_issue_body with all vulnerability data present"""
        agent = ExternalCodingAgent(self.config)

        vulnerability_details = {
            'vulnerabilityTitle': 'SQL Injection Vulnerability',
            'vulnerabilityUuid': '12345-abcde-67890',
            'vulnerabilityRuleName': 'SQL-INJECTION',
            'vulnerabilitySeverity': 'HIGH',
            'vulnerabilityStatus': 'OPEN',
            'vulnerabilityOverviewStory': 'This is a detailed overview of the SQL injection vulnerability',
            'vulnerabilityEventsSummary': 'Event 1: User input detected\nEvent 2: SQL query executed\nEvent 3: Database accessed',
            'vulnerabilityHttpRequestDetails': 'POST /api/users HTTP/1.1\nHost: example.com\nContent-Type: application/json\n\n{"username": "admin\' OR 1=1--"}'
        }

        result = agent.assemble_issue_body(vulnerability_details)

        # Verify all sections are present
        self.assertIn('# Contrast AI SmartFix Issue Report', result)
        self.assertIn('# Security Vulnerability: SQL Injection Vulnerability', result)
        self.assertIn('**Rule:** SQL-INJECTION', result)
        self.assertIn('**Severity:** HIGH', result)
        self.assertIn('**Status:** OPEN', result)
        self.assertIn('## Overview', result)
        self.assertIn('This is a detailed overview of the SQL injection vulnerability', result)
        self.assertIn('## Technical Details', result)
        self.assertIn('### Event Summary', result)
        self.assertIn('Event 1: User input detected', result)
        self.assertIn('### HTTP Request Details', result)
        self.assertIn('POST /api/users HTTP/1.1', result)
        self.assertIn('## Action Required', result)

    def test_assemble_issue_body_with_empty_overview(self):
        """Test assemble_issue_body when overview is empty"""
        agent = ExternalCodingAgent(self.config)

        vulnerability_details = {
            'vulnerabilityTitle': 'XSS Vulnerability',
            'vulnerabilityUuid': '12345-abcde-67890',
            'vulnerabilityRuleName': 'XSS',
            'vulnerabilitySeverity': 'MEDIUM',
            'vulnerabilityStatus': 'OPEN',
            'vulnerabilityOverviewStory': '',  # Empty overview
            'vulnerabilityEventsSummary': 'Event 1: Script injection detected',
            'vulnerabilityHttpRequestDetails': 'GET /search?q=<script>alert(1)</script> HTTP/1.1'
        }

        result = agent.assemble_issue_body(vulnerability_details)

        # Verify overview section is not present
        self.assertNotIn('## Overview', result)
        self.assertIn('## Technical Details', result)
        self.assertIn('### Event Summary', result)
        self.assertIn('### HTTP Request Details', result)

    def test_assemble_issue_body_with_empty_events_and_http(self):
        """Test assemble_issue_body when events and HTTP details are empty"""
        agent = ExternalCodingAgent(self.config)

        vulnerability_details = {
            'vulnerabilityTitle': 'Path Traversal',
            'vulnerabilityUuid': '12345-abcde-67890',
            'vulnerabilityRuleName': 'PATH-TRAVERSAL',
            'vulnerabilitySeverity': 'LOW',
            'vulnerabilityStatus': 'CONFIRMED',
            'vulnerabilityOverviewStory': 'This vulnerability allows directory traversal attacks',
            'vulnerabilityEventsSummary': '',  # Empty events
            'vulnerabilityHttpRequestDetails': ''  # Empty HTTP details
        }

        result = agent.assemble_issue_body(vulnerability_details)

        # Verify overview section is present but technical details section is not
        self.assertIn('## Overview', result)
        self.assertIn('This vulnerability allows directory traversal attacks', result)
        self.assertNotIn('## Technical Details', result)
        self.assertNotIn('### Event Summary', result)
        self.assertNotIn('### HTTP Request Details', result)

    def test_assemble_issue_body_with_all_empty_optional_fields(self):
        """Test assemble_issue_body when all optional fields are empty"""
        agent = ExternalCodingAgent(self.config)

        vulnerability_details = {
            'vulnerabilityTitle': 'Buffer Overflow',
            'vulnerabilityUuid': '12345-abcde-67890',
            'vulnerabilityRuleName': 'BUFFER-OVERFLOW',
            'vulnerabilitySeverity': 'CRITICAL',
            'vulnerabilityStatus': 'NEW',
            'vulnerabilityOverviewStory': '',  # Empty
            'vulnerabilityEventsSummary': '',  # Empty
            'vulnerabilityHttpRequestDetails': ''  # Empty
        }

        result = agent.assemble_issue_body(vulnerability_details)

        # Verify only basic sections are present
        self.assertIn('# Security Vulnerability: Buffer Overflow', result)
        self.assertIn('**Rule:** BUFFER-OVERFLOW', result)
        self.assertIn('**Severity:** CRITICAL', result)
        self.assertIn('**Status:** NEW', result)
        self.assertNotIn('## Overview', result)
        self.assertNotIn('## Technical Details', result)
        self.assertNotIn('### Event Summary', result)
        self.assertNotIn('### HTTP Request Details', result)
        self.assertIn('## Action Required', result)

    def test_assemble_issue_body_with_whitespace_only_fields(self):
        """Test assemble_issue_body when optional fields contain only whitespace"""
        agent = ExternalCodingAgent(self.config)

        vulnerability_details = {
            'vulnerabilityTitle': 'CSRF Vulnerability',
            'vulnerabilityUuid': '12345-abcde-67890',
            'vulnerabilityRuleName': 'CSRF',
            'vulnerabilitySeverity': 'MEDIUM',
            'vulnerabilityStatus': 'OPEN',
            'vulnerabilityOverviewStory': '   \n   \t   ',  # Whitespace only
            'vulnerabilityEventsSummary': '\n\n\n',  # Newlines only
            'vulnerabilityHttpRequestDetails': '    '  # Spaces only
        }

        result = agent.assemble_issue_body(vulnerability_details)

        # Verify sections with whitespace-only content are not included
        self.assertNotIn('## Overview', result)
        self.assertNotIn('## Technical Details', result)
        self.assertNotIn('### Event Summary', result)
        self.assertNotIn('### HTTP Request Details', result)

    @patch('src.github.external_coding_agent.tail_string')
    def test_assemble_issue_body_with_very_long_data(self, mock_tail_string):
        """Test assemble_issue_body with very long vulnerability data that needs truncation"""
        agent = ExternalCodingAgent(self.config)

        # Create very long strings
        long_overview = 'A' * 10000  # 10k characters
        long_events = 'B' * 25000    # 25k characters
        long_http = 'C' * 5000       # 5k characters

        vulnerability_details = {
            'vulnerabilityTitle': 'Large Data Vulnerability',
            'vulnerabilityUuid': '12345-abcde-67890',
            'vulnerabilityRuleName': 'LARGE-DATA',
            'vulnerabilitySeverity': 'HIGH',
            'vulnerabilityStatus': 'OPEN',
            'vulnerabilityOverviewStory': long_overview,
            'vulnerabilityEventsSummary': long_events,
            'vulnerabilityHttpRequestDetails': long_http
        }

        # Configure mock to return truncated versions
        mock_tail_string.side_effect = lambda text, max_len, prefix="...[Content truncated]...\n": f"TRUNCATED_{text[:10]}_{max_len}"

        result = agent.assemble_issue_body(vulnerability_details)

        # Verify tail_string was called with correct parameters
        expected_calls = [
            unittest.mock.call(long_overview, 8000),
            unittest.mock.call(long_events, 20000),
            unittest.mock.call(long_http, 4000)
        ]
        mock_tail_string.assert_has_calls(expected_calls, any_order=False)

        # Verify truncated content appears in result
        self.assertIn('TRUNCATED_AAAAAAAAAA_8000', result)
        self.assertIn('TRUNCATED_BBBBBBBBBB_20000', result)
        self.assertIn('TRUNCATED_CCCCCCCCCC_4000', result)

    def test_assemble_issue_body_with_missing_fields(self):
        """Test assemble_issue_body when some fields are missing from the dictionary"""
        agent = ExternalCodingAgent(self.config)

        vulnerability_details = {
            'vulnerabilityTitle': 'Incomplete Data Vulnerability',
            'vulnerabilityUuid': '12345-abcde-67890',
            # Missing some fields intentionally
            'vulnerabilityOverviewStory': 'This vulnerability has incomplete data',
            # Missing vulnerabilityEventsSummary and vulnerabilityHttpRequestDetails
        }

        result = agent.assemble_issue_body(vulnerability_details)

        # Verify default values are used for missing fields
        self.assertIn('**Rule:** Unknown Rule', result)
        self.assertIn('**Severity:** Unknown Severity', result)
        self.assertIn('**Status:** Unknown Status', result)
        self.assertIn('## Overview', result)
        self.assertIn('This vulnerability has incomplete data', result)
        # Technical details section should not be present since events and HTTP are missing
        self.assertNotIn('## Technical Details', result)

    def test_assemble_issue_body_character_count_logging(self):
        """Test that assemble_issue_body logs the character count"""
        with patch('src.github.external_coding_agent.debug_log') as mock_debug_log:
            agent = ExternalCodingAgent(self.config)

            vulnerability_details = {
                'vulnerabilityTitle': 'Test Vulnerability',
                'vulnerabilityUuid': '12345-abcde-67890',
                'vulnerabilityRuleName': 'TEST',
                'vulnerabilitySeverity': 'LOW',
                'vulnerabilityStatus': 'OPEN',
                'vulnerabilityOverviewStory': 'Short overview',
                'vulnerabilityEventsSummary': 'Short events',
                'vulnerabilityHttpRequestDetails': 'Short HTTP details'
            }

            result = agent.assemble_issue_body(vulnerability_details)

            # Verify debug_log was called with character count
            expected_length = len(result)
            mock_debug_log.assert_called_with(f"Assembled issue body with {expected_length} characters")


if __name__ == '__main__':
    unittest.main()
