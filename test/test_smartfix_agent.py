# -
# #%L
# Contrast AI SmartFix
# %%
# Copyright (C) 2026 Contrast Security, Inc.
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

Tests the SmartFixAgent remediation workflow including:
- Fix agent execution
- BuildTool integration
- PR gate validation
- Session completion with various failure categories
"""

import unittest
from unittest.mock import patch, Mock
from pathlib import Path

from src.smartfix.domains.agents.smartfix_agent import SmartFixAgent
from src.smartfix.domains.agents.build_tool import reset_storage, get_successful_build_command
from src.smartfix.domains.vulnerability import RemediationContext
from src.smartfix.shared.failure_categories import FailureCategory


class TestSmartFixAgentSuccessScenarios(unittest.TestCase):
    """Test successful remediation scenarios"""

    def setUp(self):
        reset_storage()

    def tearDown(self):
        reset_storage()

    def test_fix_succeeds_without_build_command_returns_success(self):
        """When fix agent succeeds and no build command is configured,
        should return successful session (PR gate skipped)."""
        agent = SmartFixAgent()
        context = Mock(spec=RemediationContext)
        context.build_config = None
        context.prompts = Mock()
        context.prompts.fix_system_prompt = "You are a security expert"
        context.prompts.fix_user_prompt = "Fix this vulnerability"
        context.repo_config = Mock()
        context.repo_config.repo_path = Path("/tmp/test")
        context.remediation_id = "test-fix-123"
        context.session_id = "session-456"
        context.skip_writing_security_test = False

        with patch.object(agent, '_run_fix_agent_execution', return_value="Agent completed"):
            with patch.object(agent, '_extract_analytics_data'):
                with patch.object(agent, '_extract_pr_body', return_value="## Fix Applied"):
                    session = agent.remediate(context)

        self.assertTrue(session.is_complete)
        self.assertIsNone(session.failure_category)
        self.assertIn("Fix Applied", session.pr_body)

    @patch('src.smartfix.domains.agents.smartfix_agent.get_successful_build_command')
    def test_fix_succeeds_with_verified_build_returns_success(self, mock_get_cmd):
        """When fix agent succeeds and BuildTool recorded a successful build,
        PR gate passes and session succeeds."""
        mock_get_cmd.return_value = "mvn test"

        agent = SmartFixAgent()
        context = Mock(spec=RemediationContext)
        context.build_config = Mock()
        context.build_config.has_build_command.return_value = True
        context.build_config.build_command = "mvn test"
        context.build_config.user_build_command = "mvn test"
        context.build_config.user_format_command = None
        context.repo_config = Mock()
        context.repo_config.repo_path = Path("/tmp/test")
        context.prompts = Mock()
        context.prompts.fix_system_prompt = "Fix system"
        context.prompts.fix_user_prompt = "Fix user"
        context.remediation_id = "test-456"
        context.session_id = "session-789"
        context.skip_writing_security_test = False

        with patch.object(agent, '_run_fix_agent_execution', return_value="Success"):
            with patch.object(agent, '_extract_analytics_data'):
                with patch.object(agent, '_extract_pr_body', return_value="## Fix Applied"):
                    session = agent.remediate(context)

        self.assertTrue(session.is_complete)
        self.assertIsNone(session.failure_category)


class TestSmartFixAgentFixAgentFailures(unittest.TestCase):
    """Test fix agent failure scenarios"""

    def setUp(self):
        reset_storage()

    def tearDown(self):
        reset_storage()

    def test_fix_agent_throws_exception_returns_agent_failure(self):
        """When fix agent throws an exception,
        should return session with AGENT_FAILURE."""
        agent = SmartFixAgent()
        context = Mock(spec=RemediationContext)
        context.build_config = None
        context.prompts = Mock()
        context.repo_config = Mock()

        with patch.object(agent, '_run_ai_fix_agent', side_effect=Exception("Agent crashed")):
            session = agent.remediate(context)

        self.assertEqual(session.failure_category, FailureCategory.AGENT_FAILURE)
        self.assertIn("Exception during fix agent execution", session.pr_body)

    def test_fix_agent_returns_none_returns_agent_failure(self):
        """When fix agent returns None,
        should return session with AGENT_FAILURE."""
        agent = SmartFixAgent()
        context = Mock(spec=RemediationContext)
        context.build_config = None
        context.prompts = Mock()
        context.repo_config = Mock()

        with patch.object(agent, '_run_ai_fix_agent', return_value=None):
            session = agent.remediate(context)

        self.assertEqual(session.failure_category, FailureCategory.AGENT_FAILURE)
        self.assertIn("Fix agent failed", session.pr_body)

    def test_fix_agent_returns_error_message_returns_agent_failure(self):
        """When fix agent returns error message,
        should return session with AGENT_FAILURE."""
        agent = SmartFixAgent()
        context = Mock(spec=RemediationContext)
        context.build_config = None
        context.prompts = Mock()
        context.repo_config = Mock()

        with patch.object(agent, '_run_ai_fix_agent', return_value="Error: Failed to apply fix"):
            session = agent.remediate(context)

        self.assertEqual(session.failure_category, FailureCategory.AGENT_FAILURE)
        self.assertIn("Fix agent failed", session.pr_body)


class TestSmartFixAgentPRGate(unittest.TestCase):
    """Test PR gate (build verification) scenarios"""

    def setUp(self):
        reset_storage()

    def tearDown(self):
        reset_storage()

    @patch('src.smartfix.domains.agents.smartfix_agent.get_successful_build_command')
    def test_pr_gate_fails_when_no_build_verified(self, mock_get_cmd):
        """When build command is configured but agent never verified a build,
        PR gate fails with BUILD_VERIFICATION_FAILED."""
        mock_get_cmd.return_value = None

        agent = SmartFixAgent()
        context = Mock(spec=RemediationContext)
        context.build_config = Mock()
        context.build_config.has_build_command.return_value = True
        context.build_config.build_command = "mvn test"
        context.build_config.user_build_command = "mvn test"
        context.build_config.user_format_command = None
        context.repo_config = Mock()
        context.repo_config.repo_path = Path("/tmp/test")
        context.prompts = Mock()
        context.prompts.fix_system_prompt = "Fix"
        context.prompts.fix_user_prompt = "Fix"
        context.remediation_id = "test-gate-fail"
        context.session_id = "session-gate"
        context.skip_writing_security_test = False

        with patch.object(agent, '_run_fix_agent_execution', return_value="Success"):
            with patch.object(agent, '_extract_analytics_data'):
                with patch.object(agent, '_extract_pr_body', return_value="## Fix Applied"):
                    session = agent.remediate(context)

        self.assertEqual(session.failure_category, FailureCategory.BUILD_VERIFICATION_FAILED)
        self.assertIn("did not verify", session.pr_body)

    def test_pr_gate_skipped_when_no_build_config(self):
        """When no build command is configured, PR gate is skipped."""
        agent = SmartFixAgent()
        context = Mock(spec=RemediationContext)
        context.build_config = Mock()
        context.build_config.has_build_command.return_value = False
        context.prompts = Mock()
        context.prompts.fix_system_prompt = "Fix"
        context.prompts.fix_user_prompt = "Fix"
        context.repo_config = Mock()
        context.repo_config.repo_path = Path("/tmp/test")
        context.remediation_id = "test-no-build"
        context.session_id = "session-no-build"
        context.skip_writing_security_test = False

        with patch.object(agent, '_run_fix_agent_execution', return_value="Success"):
            with patch.object(agent, '_extract_analytics_data'):
                with patch.object(agent, '_extract_pr_body', return_value="## Fix Applied"):
                    session = agent.remediate(context)

        # Should succeed since gate is skipped
        self.assertTrue(session.is_complete)
        self.assertIsNone(session.failure_category)


class TestSmartFixAgentBuildToolIntegration(unittest.TestCase):
    """Test BuildTool is properly created and passed to the agent."""

    def setUp(self):
        reset_storage()

    def tearDown(self):
        reset_storage()

    @patch('src.smartfix.domains.agents.smartfix_agent._run_agent_in_event_loop')
    def test_build_tool_passed_as_additional_tool(self, mock_event_loop):
        """BuildTool should be passed as additional_tools to the agent."""
        mock_event_loop.return_value = "<pr_body>Fix applied</pr_body>"

        agent = SmartFixAgent()
        context = Mock(spec=RemediationContext)
        context.build_config = Mock()
        context.build_config.has_build_command.return_value = False
        context.build_config.user_build_command = "mvn test"
        context.build_config.user_format_command = None
        context.repo_config = Mock()
        context.repo_config.repo_path = Path("/tmp/test")
        context.prompts = Mock()
        context.prompts.fix_system_prompt = "Fix"
        context.prompts.fix_user_prompt = "Fix"
        context.remediation_id = "test-build-tool"
        context.session_id = "session-bt"
        context.skip_writing_security_test = False

        with patch.object(agent, '_extract_analytics_data'):
            agent.remediate(context)

        # Verify _run_agent_in_event_loop was called with additional_tools
        mock_event_loop.assert_called_once()
        call_kwargs = mock_event_loop.call_args
        # additional_tools is passed as a keyword argument
        self.assertIn('additional_tools', call_kwargs.kwargs)
        additional_tools = call_kwargs.kwargs['additional_tools']
        self.assertEqual(len(additional_tools), 1)
        self.assertTrue(callable(additional_tools[0]))

    def test_reset_storage_called_per_remediation(self):
        """Storage should be reset at the start of each remediation."""
        # Simulate leftover state from a previous run
        from src.smartfix.domains.agents import build_tool
        build_tool._successful_build_command = "leftover"

        agent = SmartFixAgent()
        context = Mock(spec=RemediationContext)
        context.build_config = None
        context.prompts = Mock()
        context.repo_config = Mock()

        with patch.object(agent, '_run_ai_fix_agent', return_value="<pr_body>Fixed</pr_body>"):
            agent.remediate(context)

        # Storage should have been reset
        self.assertIsNone(get_successful_build_command())


class TestSmartFixAgentInternalMethods(unittest.TestCase):
    """Test internal helper methods"""

    def test_extract_pr_body_from_agent_summary(self):
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
        pr_body = agent._extract_pr_body(agent_summary)

        self.assertIn("Fix Applied", pr_body)
        self.assertIn("Updated input validation", pr_body)
        self.assertNotIn("Some agent output here", pr_body)

    def test_extract_pr_body_without_markers_returns_full_summary(self):
        agent = SmartFixAgent()
        agent_summary = "Fixed the issue by updating validation."

        pr_body = agent._extract_pr_body(agent_summary)

        self.assertEqual(pr_body, agent_summary)

    def test_extract_analytics_data_parses_all_fields(self):
        agent = SmartFixAgent()
        agent_summary = """
<analytics>
Confidence_Score: High (85%)
Programming_Language: Python
Technical_Stack: FastAPI, PostgreSQL
Frameworks: FastAPI, SQLAlchemy, Pydantic
</analytics>
"""
        with patch('src.smartfix.domains.agents.smartfix_agent.telemetry_handler') as mock_telemetry:
            agent._extract_analytics_data(agent_summary)

            mock_telemetry.update_telemetry.assert_any_call("resultInfo.confidence", "High (85%)")
            mock_telemetry.update_telemetry.assert_any_call("appInfo.programmingLanguage", "Python")
            mock_telemetry.update_telemetry.assert_any_call("appInfo.technicalStackInfo", "FastAPI, PostgreSQL")
            mock_telemetry.update_telemetry.assert_any_call("appInfo.frameworksAndLibraries", ["FastAPI", "SQLAlchemy", "Pydantic"])

    def test_extract_analytics_data_handles_missing_tags(self):
        agent = SmartFixAgent()
        agent_summary = "No analytics here."

        with patch('src.smartfix.domains.agents.smartfix_agent.telemetry_handler') as mock_telemetry:
            agent._extract_analytics_data(agent_summary)
            mock_telemetry.update_telemetry.assert_not_called()


if __name__ == '__main__':
    unittest.main()
