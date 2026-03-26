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

from src.smartfix.domains.workflow.session_handler import (
    SessionOutcome, handle_session_result, generate_qa_section
)
from src.smartfix.shared.failure_categories import FailureCategory


class TestSessionHandler(unittest.TestCase):
    """
    Unit tests for the structured session handling functions.

    These tests validate the core business logic that was causing the original bug
    where failed sessions could generate false positive success messages.
    """

    def create_mock_session(self, success=True, failure_category=None, pr_body="Test PR body"):
        """Helper to create a mock session object."""
        session = MagicMock()
        session.success = success
        session.failure_category = failure_category
        session.pr_body = pr_body
        return session

    def test_generate_qa_section_success_with_build_command(self):
        """Test QA section generation with a build command."""
        result = generate_qa_section("pytest")

        self.assertIn("Final Build Status:** Success", result)
        self.assertIn("Build Run:** Yes (`pytest`)", result)

    def test_generate_qa_section_no_build_command(self):
        """Test QA section when no build command is provided."""
        with patch('src.smartfix.domains.workflow.session_handler.log') as mock_log:
            result = generate_qa_section(None)

        self.assertEqual(result, "")  # Empty section when no build command
        mock_log.assert_called_with("Review section skipped: no BUILD_COMMAND was provided.")

    def test_generate_qa_section_empty_build_command(self):
        """Test QA section when empty string build command is provided."""
        with patch('src.smartfix.domains.workflow.session_handler.log') as mock_log:
            result = generate_qa_section("")

        self.assertEqual(result, "")
        mock_log.assert_called_with("Review section skipped: no BUILD_COMMAND was provided.")

    def test_handle_session_result_success(self):
        """Test session result handling for successful session."""
        session = self.create_mock_session(success=True, pr_body="Custom PR body")

        result = handle_session_result(session)

        self.assertIsInstance(result, SessionOutcome)
        self.assertTrue(result.should_continue)
        self.assertIsNone(result.failure_category)
        self.assertEqual(result.ai_fix_summary, "Custom PR body")

    def test_handle_session_result_success_no_pr_body(self):
        """Test session result handling for successful session without PR body."""
        session = self.create_mock_session(success=True, pr_body=None)

        result = handle_session_result(session)

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

        result = handle_session_result(session)

        self.assertFalse(result.should_continue)
        self.assertEqual(result.failure_category, "INITIAL_BUILD_FAILURE")
        self.assertIsNone(result.ai_fix_summary)

    def test_handle_session_result_failure_no_category(self):
        """Test session result handling for failed session without failure category."""
        session = self.create_mock_session(success=False, failure_category=None)

        result = handle_session_result(session)

        self.assertFalse(result.should_continue)
        self.assertEqual(result.failure_category, FailureCategory.AGENT_FAILURE.value)
        self.assertIsNone(result.ai_fix_summary)

    def test_bug_fix_validation(self):
        """
        Integration test validating the original bug is fixed.

        This test simulates the exact scenario that was causing false positive
        "Success (passed on first attempt)" messages.
        """
        # Bug scenario: session failed
        failed_session = self.create_mock_session(
            success=False,
            failure_category=MagicMock(value="INITIAL_BUILD_FAILURE")
        )

        result = handle_session_result(failed_session)

        self.assertFalse(result.should_continue)  # Should NOT continue to PR generation
        self.assertEqual(result.failure_category, "INITIAL_BUILD_FAILURE")

        # Legitimate success scenario should still work
        success_session = self.create_mock_session(success=True)
        result = handle_session_result(success_session)

        self.assertTrue(result.should_continue)  # Should continue to PR generation
        self.assertIsNone(result.failure_category)

        # Generate QA section for legitimate success
        qa_section = generate_qa_section("pytest")

        self.assertIn("Final Build Status:** Success", qa_section)

    def test_session_failure_with_category(self):
        """
        Test that session failure returns should_continue=False with a failure category.
        """
        mock_failure_category = MagicMock()
        mock_failure_category.value = "QA_BUILD_FAILURE"
        failed_session = self.create_mock_session(
            success=False,
            failure_category=mock_failure_category
        )

        result = handle_session_result(failed_session)

        self.assertFalse(result.should_continue)
        self.assertEqual(result.failure_category, "QA_BUILD_FAILURE")
        self.assertIsNone(result.ai_fix_summary)


if __name__ == '__main__':
    unittest.main()
