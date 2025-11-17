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
from unittest.mock import MagicMock, patch

from src.smartfix.domains.workflow.session_handler import SessionHandler, QASectionConfig
from src.smartfix.shared.failure_categories import FailureCategory


class TestSessionHandler(unittest.TestCase):
    """
    Unit tests for the object-oriented session handling logic.

    These tests validate the core business logic that was causing the original bug
    where failed sessions could generate false positive success messages.
    """

    def setUp(self):
        """Set up test fixtures."""
        self.session_handler = SessionHandler()

    def create_mock_session(self, success=True, qa_attempts=0, failure_category=None, pr_body="Test PR body"):
        """Helper to create a mock session object."""
        session = MagicMock()
        session.success = success
        session.qa_attempts = qa_attempts
        session.failure_category = failure_category
        session.pr_body = pr_body
        return session

    def test_generate_qa_section_success_no_attempts(self):
        """Test QA section generation for successful session with no QA attempts."""
        session = self.create_mock_session(success=True, qa_attempts=0)
        config = QASectionConfig(skip_qa_review=False, has_build_command=True, build_command="pytest")

        result = self.session_handler.generate_qa_section(session, config)

        self.assertIn("Success (passed on first attempt)", result)
        self.assertIn("Build Run:** Yes (`pytest`)", result)

    def test_generate_qa_section_success_with_attempts(self):
        """Test QA section generation for successful session with QA attempts."""
        session = self.create_mock_session(success=True, qa_attempts=2)
        config = QASectionConfig(skip_qa_review=False, has_build_command=True, build_command="npm test")

        result = self.session_handler.generate_qa_section(session, config)

        self.assertIn("Final Build Status:** Success", result)
        self.assertNotIn("passed on first attempt", result)
        self.assertIn("Build Run:** Yes (`npm test`)", result)

    def test_generate_qa_section_qa_skipped_no_build_command(self):
        """Test QA section when QA is skipped due to no build command."""
        session = self.create_mock_session(success=True, qa_attempts=0)
        config = QASectionConfig(skip_qa_review=False, has_build_command=False, build_command="")

        with patch('src.smartfix.domains.workflow.session_handler.log') as mock_log:
            result = self.session_handler.generate_qa_section(session, config)

        self.assertEqual(result, "")  # Empty section when QA skipped
        mock_log.assert_called_with("QA Review was skipped as no BUILD_COMMAND was provided.")

    def test_generate_qa_section_qa_skipped_by_config(self):
        """Test QA section when QA is skipped by configuration."""
        session = self.create_mock_session(success=True, qa_attempts=0)
        config = QASectionConfig(skip_qa_review=True, has_build_command=True, build_command="make test")

        with patch('src.smartfix.domains.workflow.session_handler.log') as mock_log:
            result = self.session_handler.generate_qa_section(session, config)

        self.assertEqual(result, "")  # Empty section when QA skipped
        mock_log.assert_called_with("QA Review was skipped based on SKIP_QA_REVIEW setting.")

    def test_handle_session_result_success(self):
        """Test session result handling for successful session."""
        session = self.create_mock_session(success=True, pr_body="Custom PR body")

        result = self.session_handler.handle_session_result(session)

        self.assertTrue(result.should_continue)
        self.assertIsNone(result.failure_category)
        self.assertEqual(result.ai_fix_summary, "Custom PR body")

    def test_handle_session_result_success_no_pr_body(self):
        """Test session result handling for successful session without PR body."""
        session = self.create_mock_session(success=True, pr_body=None)

        result = self.session_handler.handle_session_result(session)

        self.assertTrue(result.should_continue)
        self.assertIsNone(result.failure_category)
        self.assertEqual(result.ai_fix_summary, "Fix completed successfully")

    def test_handle_session_result_failure_with_category(self):
        """Test session result handling for failed session with failure category."""
        mock_failure_category = MagicMock()
        mock_failure_category.value = "INITIAL_BUILD_FAILURE"
        session = self.create_mock_session(
            success=False,
            failure_category=mock_failure_category
        )

        result = self.session_handler.handle_session_result(session)

        self.assertFalse(result.should_continue)
        self.assertEqual(result.failure_category, "INITIAL_BUILD_FAILURE")
        self.assertIsNone(result.ai_fix_summary)

    def test_handle_session_result_failure_no_category(self):
        """Test session result handling for failed session without failure category."""
        session = self.create_mock_session(success=False, failure_category=None)

        result = self.session_handler.handle_session_result(session)

        self.assertFalse(result.should_continue)
        self.assertEqual(result.failure_category, FailureCategory.AGENT_FAILURE.value)
        self.assertIsNone(result.ai_fix_summary)

    def test_bug_fix_validation(self):
        """
        Integration test validating the original bug is fixed.

        This test simulates the exact scenario that was causing false positive
        "Success (passed on first attempt)" messages.
        """
        # Bug scenario: qa_attempts == 0 AND session failed
        failed_session = self.create_mock_session(
            success=False,
            qa_attempts=0,
            failure_category=MagicMock(value="INITIAL_BUILD_FAILURE")
        )

        # This should result in error_exit, not PR generation
        result = self.session_handler.handle_session_result(failed_session)

        self.assertFalse(result.should_continue)  # Should NOT continue to PR generation
        self.assertEqual(result.failure_category, "INITIAL_BUILD_FAILURE")

        # Legitimate success scenario should still work
        success_session = self.create_mock_session(success=True, qa_attempts=0)
        result = self.session_handler.handle_session_result(success_session)

        self.assertTrue(result.should_continue)  # Should continue to PR generation
        self.assertIsNone(result.failure_category)

        # Generate QA section for legitimate success
        config = QASectionConfig(skip_qa_review=False, has_build_command=True, build_command="pytest")
        qa_section = self.session_handler.generate_qa_section(success_session, config)

        self.assertIn("Success (passed on first attempt)", qa_section)

    def test_session_failure_with_qa_attempts(self):
        """
        Test that session failure returns should_continue=False even when qa_attempts > 0.

        This specifically tests the scenario where session success is false
        but qa_attempts is greater than 0, ensuring proper failure handling.
        """
        # Failure scenario: session failed but QA attempts were made
        mock_failure_category = MagicMock()
        mock_failure_category.value = "QA_BUILD_FAILURE"
        failed_session_with_qa = self.create_mock_session(
            success=False,
            qa_attempts=3,  # QA was attempted multiple times
            failure_category=mock_failure_category
        )

        result = self.session_handler.handle_session_result(failed_session_with_qa)

        # Should NOT continue regardless of qa_attempts when session failed
        self.assertFalse(result.should_continue)
        self.assertEqual(result.failure_category, "QA_BUILD_FAILURE")
        self.assertIsNone(result.ai_fix_summary)


if __name__ == '__main__':
    unittest.main()
