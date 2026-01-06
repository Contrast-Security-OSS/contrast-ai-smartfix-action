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

"""
Tests for smartfix_agent.py module.

Tests the SmartFixAgent remediation workflow state machine including:
- Initial build validation
- Fix agent execution
- QA loop validation
- Session completion with various failure categories
"""

import unittest
from unittest.mock import patch, Mock
from pathlib import Path

from src.smartfix.domains.agents.smartfix_agent import SmartFixAgent
from src.smartfix.domains.vulnerability import RemediationContext
from src.smartfix.shared.failure_categories import FailureCategory


class TestSmartFixAgentInitialBuildFailure(unittest.TestCase):
    """Test initial build validation failure scenarios"""

    def test_build_fails_before_fix_returns_initial_build_failure(self):
        """
        When initial build fails before any fix attempt,
        should return session with INITIAL_BUILD_FAILURE.
        """
        # Arrange
        agent = SmartFixAgent()
        context = Mock(spec=RemediationContext)

        # Setup build configuration
        context.build_config = Mock()
        context.build_config.has_build_command.return_value = True
        context.build_config.build_command = "npm test"

        context.repo_config = Mock()
        context.repo_config.repo_path = Path("/tmp/test")

        context.remediation_id = "test-remediation-123"

        # Mock build failure
        with patch('src.smartfix.domains.agents.smartfix_agent.run_build_command') as mock_build:
            mock_build.return_value = (False, "Build failed: compilation errors")

            with patch('src.smartfix.domains.agents.smartfix_agent.extract_build_errors') as mock_extract:
                mock_extract.return_value = "Compilation error on line 42"

                # Act
                session = agent.remediate(context)

        # Assert
        self.assertEqual(session.failure_category, FailureCategory.INITIAL_BUILD_FAILURE)
        self.assertEqual(session.pr_body, "Build failed before fix attempt")
        self.assertTrue(session.is_complete)


class TestSmartFixAgentSuccessScenarios(unittest.TestCase):
    """Test successful remediation scenarios"""

    def test_fix_succeeds_without_build_command_returns_success(self):
        """
        When fix agent succeeds and no build command is configured,
        should return successful session immediately.
        """
        # Arrange
        agent = SmartFixAgent()
        context = Mock(spec=RemediationContext)

        # No build configuration
        context.build_config = None

        # Properly configure prompts and repo_config mocks
        context.prompts = Mock()
        context.prompts.fix_system_prompt = "You are a security expert"
        context.prompts.fix_user_prompt = "Fix this vulnerability"

        context.repo_config = Mock()
        context.repo_config.repo_path = Path("/tmp/test")

        context.remediation_id = "test-fix-123"
        context.session_id = "session-456"
        context.skip_writing_security_test = False

        # Mock the internal execution methods to avoid actual agent execution
        with patch.object(agent, '_run_fix_agent_execution', return_value="Agent completed successfully"):
            with patch.object(agent, '_extract_analytics_data'):
                with patch.object(agent, '_extract_pr_body', return_value="## Fix Applied\n\nFixed the vulnerability"):
                    # Act
                    session = agent.remediate(context)

        # Assert
        self.assertTrue(session.is_complete)
        self.assertIsNone(session.failure_category)
        self.assertIn("Fix Applied", session.pr_body)

    def test_fix_succeeds_with_build_passing_returns_success(self):
        """
        When fix agent succeeds and build passes,
        should run QA loop and return success if QA passes.
        """
        # Arrange
        agent = SmartFixAgent()
        context = Mock(spec=RemediationContext)

        # Setup build configuration
        context.build_config = Mock()
        context.build_config.has_build_command.return_value = True
        context.build_config.build_command = "npm test"

        context.repo_config = Mock()
        context.repo_config.repo_path = Path("/tmp/test")

        context.prompts = Mock()
        context.prompts.fix_system_prompt = "Fix system"
        context.prompts.fix_user_prompt = "Fix user"

        context.remediation_id = "test-remediation-456"
        context.session_id = "session-789"
        context.skip_writing_security_test = False
        context.max_qa_attempts = 3
        context.changed_files = []

        # Mock initial build success
        with patch('src.smartfix.domains.agents.smartfix_agent.run_build_command') as mock_build:
            mock_build.return_value = (True, "Build passed")

            # Mock fix agent execution
            with patch.object(agent, '_run_fix_agent_execution', return_value="Success"):
                with patch.object(agent, '_extract_analytics_data'):
                    with patch.object(agent, '_extract_pr_body', return_value="## Fix Applied"):
                        # Mock QA loop success
                        with patch.object(agent, '_run_qa_loop_internal', return_value=(True, [], None, [])):
                            # Act
                            session = agent.remediate(context)

        # Assert
        self.assertTrue(session.is_complete)
        self.assertIsNone(session.failure_category)
        self.assertIn("Fix Applied", session.pr_body)


class TestSmartFixAgentFixAgentFailures(unittest.TestCase):
    """Test fix agent failure scenarios"""

    def test_fix_agent_throws_exception_returns_agent_failure(self):
        """
        When fix agent throws an exception,
        should return session with AGENT_FAILURE.
        """
        # Arrange
        agent = SmartFixAgent()
        context = Mock(spec=RemediationContext)
        context.build_config = None
        context.prompts = Mock()
        context.repo_config = Mock()

        # Mock fix agent exception
        with patch.object(agent, '_run_ai_fix_agent', side_effect=Exception("Agent crashed")):
            # Act
            session = agent.remediate(context)

        # Assert
        self.assertEqual(session.failure_category, FailureCategory.AGENT_FAILURE)
        self.assertIn("Exception during fix agent execution", session.pr_body)
        self.assertTrue(session.is_complete)

    def test_fix_agent_returns_none_returns_agent_failure(self):
        """
        When fix agent returns None (failed to generate fix),
        should return session with AGENT_FAILURE.
        """
        # Arrange
        agent = SmartFixAgent()
        context = Mock(spec=RemediationContext)
        context.build_config = None
        context.prompts = Mock()
        context.repo_config = Mock()

        # Mock fix agent failure (returns None)
        with patch.object(agent, '_run_ai_fix_agent', return_value=None):
            # Act
            session = agent.remediate(context)

        # Assert
        self.assertEqual(session.failure_category, FailureCategory.AGENT_FAILURE)
        self.assertIn("Fix agent failed", session.pr_body)
        self.assertTrue(session.is_complete)

    def test_fix_agent_returns_error_message_returns_agent_failure(self):
        """
        When fix agent returns error message,
        should return session with AGENT_FAILURE.
        """
        # Arrange
        agent = SmartFixAgent()
        context = Mock(spec=RemediationContext)
        context.build_config = None
        context.prompts = Mock()
        context.repo_config = Mock()

        # Mock fix agent error
        with patch.object(agent, '_run_ai_fix_agent', return_value="Error: Failed to apply fix"):
            # Act
            session = agent.remediate(context)

        # Assert
        self.assertEqual(session.failure_category, FailureCategory.AGENT_FAILURE)
        self.assertIn("Fix agent failed", session.pr_body)
        self.assertTrue(session.is_complete)


class TestSmartFixAgentQALoopFailures(unittest.TestCase):
    """Test QA loop failure scenarios"""

    def test_qa_loop_exhausts_retries_returns_exceeded_qa_attempts(self):
        """
        When QA loop fails after max attempts,
        should return session with EXCEEDED_QA_ATTEMPTS.
        """
        # Arrange
        agent = SmartFixAgent()
        context = Mock(spec=RemediationContext)

        context.build_config = Mock()
        context.build_config.has_build_command.return_value = True
        context.build_config.build_command = "npm test"

        context.repo_config = Mock()
        context.repo_config.repo_path = Path("/tmp/test")

        context.prompts = Mock()
        context.prompts.fix_system_prompt = "Fix"
        context.prompts.fix_user_prompt = "Fix"

        context.remediation_id = "test-remediation-789"
        context.session_id = "session-qa-1"
        context.skip_writing_security_test = False
        context.max_qa_attempts = 3
        context.changed_files = []

        # Mock initial build success
        with patch('src.smartfix.domains.agents.smartfix_agent.run_build_command') as mock_build:
            mock_build.return_value = (True, "Build passed")

            # Mock fix agent execution
            with patch.object(agent, '_run_fix_agent_execution', return_value="Success"):
                with patch.object(agent, '_extract_analytics_data'):
                    with patch.object(agent, '_extract_pr_body', return_value="## Fix Applied"):
                        # Mock QA loop failure after 3 attempts
                        with patch.object(agent, '_run_qa_loop_internal', return_value=(False, [], "Build failed", ["attempt1", "attempt2", "attempt3"])):
                            # Act
                            session = agent.remediate(context)

        # Assert
        self.assertEqual(session.failure_category, FailureCategory.EXCEEDED_QA_ATTEMPTS)
        self.assertEqual(session.qa_attempts, 3)
        self.assertIn("QA loop failed", session.pr_body)
        self.assertTrue(session.is_complete)

    def test_qa_loop_throws_exception_returns_qa_agent_failure(self):
        """
        When QA loop throws an exception,
        should return session with QA_AGENT_FAILURE.
        """
        # Arrange
        agent = SmartFixAgent()
        context = Mock(spec=RemediationContext)

        context.build_config = Mock()
        context.build_config.has_build_command.return_value = True
        context.build_config.build_command = "npm test"

        context.repo_config = Mock()
        context.repo_config.repo_path = Path("/tmp/test")

        context.prompts = Mock()
        context.prompts.fix_system_prompt = "Fix"
        context.prompts.fix_user_prompt = "Fix"

        context.remediation_id = "test-remediation-999"
        context.session_id = "session-qa-exception"
        context.skip_writing_security_test = False
        context.max_qa_attempts = 3
        context.changed_files = []

        # Mock initial build success
        with patch('src.smartfix.domains.agents.smartfix_agent.run_build_command') as mock_build:
            mock_build.return_value = (True, "Build passed")

            # Mock fix agent execution
            with patch.object(agent, '_run_fix_agent_execution', return_value="Success"):
                with patch.object(agent, '_extract_analytics_data'):
                    with patch.object(agent, '_extract_pr_body', return_value="## Fix Applied"):
                        # Mock QA loop exception
                        with patch.object(agent, '_run_qa_loop_internal', side_effect=Exception("QA crashed")):
                            # Act
                            session = agent.remediate(context)

        # Assert
        self.assertEqual(session.failure_category, FailureCategory.QA_AGENT_FAILURE)
        self.assertIn("QA loop failed", session.pr_body)
        self.assertTrue(session.is_complete)


class TestSmartFixAgentInternalMethods(unittest.TestCase):
    """Test internal helper methods"""

    def test_extract_pr_body_from_agent_summary(self):
        """
        When agent summary contains <pr_body> tags,
        should extract just the PR body content.
        """
        # Arrange
        agent = SmartFixAgent()
        agent_summary = """
Some agent output here.

<pr_body>
# Fix Applied

This PR fixes the security vulnerability.

## Changes
- Updated input validation
- Added security tests
</pr_body>

More agent output after.
"""

        # Act
        pr_body = agent._extract_pr_body(agent_summary)

        # Assert
        self.assertIn("Fix Applied", pr_body)
        self.assertIn("Updated input validation", pr_body)
        self.assertNotIn("Some agent output here", pr_body)
        self.assertNotIn("More agent output after", pr_body)

    def test_extract_pr_body_without_markers_returns_full_summary(self):
        """
        When agent summary has no PR body markers,
        should return the full summary.
        """
        # Arrange
        agent = SmartFixAgent()
        agent_summary = "Fixed the issue by updating validation."

        # Act
        pr_body = agent._extract_pr_body(agent_summary)

        # Assert
        self.assertEqual(pr_body, agent_summary)

    def test_extract_analytics_data_parses_all_fields(self):
        """
        When agent summary contains analytics tags with all fields,
        should extract and update telemetry with correct values.
        """
        # Arrange
        agent = SmartFixAgent()
        agent_summary = """
<analytics>
Confidence_Score: High (85%)
Programming_Language: Python
Technical_Stack: FastAPI, PostgreSQL
Frameworks: FastAPI, SQLAlchemy, Pydantic
</analytics>
"""

        # Mock telemetry handler
        with patch('src.smartfix.domains.agents.smartfix_agent.telemetry_handler') as mock_telemetry:
            # Act
            agent._extract_analytics_data(agent_summary)

            # Assert
            mock_telemetry.update_telemetry.assert_any_call("resultInfo.confidence", "High (85%)")
            mock_telemetry.update_telemetry.assert_any_call("appInfo.programmingLanguage", "Python")
            mock_telemetry.update_telemetry.assert_any_call("appInfo.technicalStackInfo", "FastAPI, PostgreSQL")
            mock_telemetry.update_telemetry.assert_any_call("appInfo.frameworksAndLibraries", ["FastAPI", "SQLAlchemy", "Pydantic"])

    def test_extract_analytics_data_handles_missing_tags(self):
        """
        When agent summary has no analytics tags,
        should not update telemetry and return early.
        """
        # Arrange
        agent = SmartFixAgent()
        agent_summary = "No analytics here."

        # Mock telemetry handler
        with patch('src.smartfix.domains.agents.smartfix_agent.telemetry_handler') as mock_telemetry:
            # Act
            agent._extract_analytics_data(agent_summary)

            # Assert
            mock_telemetry.update_telemetry.assert_not_called()


if __name__ == '__main__':
    unittest.main()
