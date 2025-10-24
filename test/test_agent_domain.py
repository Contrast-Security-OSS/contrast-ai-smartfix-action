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
from src.config import get_config, reset_config
from src.smartfix.domains.agents import (
    SmartFixAgent,
    CodingAgentStrategy,
    AgentSession,
)
from src.smartfix.shared.failure_categories import FailureCategory
from src.smartfix.domains.vulnerability import RemediationContext


# Global patches to prevent git operations during tests
GIT_HANDLER_PATCHES = [
    'src.git_handler.prepare_feature_branch',
    'src.git_handler.stage_changes',
    'src.git_handler.check_status',
    'src.git_handler.commit_changes',
    'src.git_handler.amend_commit',
    'src.git_handler.get_last_commit_changed_files',
    'src.git_handler.get_uncommitted_changed_files',
    'src.git_handler.push_branch',
    'src.git_handler.cleanup_branch'
]


class TestSmartFixAgent(unittest.TestCase):

    def setUp(self):
        """Set up mocks to prevent git operations in all tests"""
        # Reset and get test config
        reset_config()
        self.config = get_config(testing=True)

        # Start all git handler patches
        self.git_mocks = []
        for patch_target in GIT_HANDLER_PATCHES:
            patcher = patch(patch_target)
            mock = patcher.start()
            self.git_mocks.append((patcher, mock))

        # Set up common return values for git mocks
        # get_last_commit_changed_files and get_uncommitted_changed_files should return a list
        for patcher, mock in self.git_mocks:
            if 'get_last_commit_changed_files' in patcher.attribute:
                mock.return_value = ["src/file1.py", "src/file2.py"]
            elif 'get_uncommitted_changed_files' in patcher.attribute:
                mock.return_value = ["src/file1.py", "src/file2.py"]
            elif 'check_status' in patcher.attribute:
                mock.return_value = True  # Has changes

    def tearDown(self):
        """Stop all patches"""
        for patcher, mock in self.git_mocks:
            patcher.stop()
        reset_config()

    def test_smartfix_agent_is_a_coding_agent_strategy(self):
        """
        Tests that SmartFixAgent correctly implements the CodingAgentStrategy interface.
        """
        self.assertTrue(issubclass(SmartFixAgent, CodingAgentStrategy))

    @patch('src.smartfix.domains.agents.smartfix_agent.SmartFixAgent._run_ai_fix_agent')
    @patch('src.smartfix.domains.workflow.build_runner.run_build_command')
    @patch('src.build_output_analyzer.extract_build_errors')
    def test_remediate_method_exists(self, mock_extract_errors, mock_run_build, mock_run_ai_fix):
        """
        Tests that the remediate method is present on the SmartFixAgent and no longer raises NotImplementedError.
        """
        agent = SmartFixAgent()
        mock_context = MagicMock(spec=RemediationContext)

        # Mock the required attributes and methods
        mock_context.build_config = MagicMock()
        mock_context.build_config.has_build_command.return_value = False
        mock_context.vulnerability = MagicMock()
        mock_context.vulnerability.title = "Test Vulnerability"
        mock_context.remediation_id = "test-123"
        mock_context.repo_config = MagicMock()
        mock_context.repo_config.repo_path = "/tmp/test-repo"

        # Mock function returns
        mock_run_build.return_value = (True, "Build success")
        mock_run_ai_fix.return_value = "Fix applied successfully"

        # Should not raise NotImplementedError anymore
        result = agent.remediate(mock_context)
        self.assertIsInstance(result, AgentSession)
        # Just verify that the method returns a valid session object, don't check specific status
        # since the mock setup might result in different statuses

    @patch('src.smartfix.domains.agents.smartfix_agent.run_build_command')
    @patch('src.smartfix.domains.agents.smartfix_agent.extract_build_errors')
    def test_validate_initial_build_success(self, mock_extract_errors, mock_run_build):
        """
        Tests successful initial build validation.
        """
        agent = SmartFixAgent()
        mock_context = MagicMock(spec=RemediationContext)

        # Setup mocks with proper attribute structure
        mock_context.build_config = MagicMock()
        mock_context.build_config.has_build_command.return_value = True
        mock_context.build_config.build_command = "npm test"
        mock_context.repo_config = MagicMock()
        mock_context.repo_config.repo_path = "/repo"
        mock_context.remediation_id = "test-123"
        mock_run_build.return_value = (True, "build success output")

        session = AgentSession()
        result = agent._validate_initial_build(session, mock_context)

        self.assertTrue(result)

    @patch('src.smartfix.domains.agents.smartfix_agent.run_build_command')
    @patch('src.smartfix.domains.agents.smartfix_agent.extract_build_errors')
    def test_validate_initial_build_failure(self, mock_extract_errors, mock_run_build):
        """
        Tests failed initial build validation.
        """
        agent = SmartFixAgent()
        mock_context = MagicMock(spec=RemediationContext)

        # Setup mocks with proper attribute structure
        mock_context.build_config = MagicMock()
        mock_context.build_config.has_build_command.return_value = True
        mock_context.build_config.build_command = "npm test"
        mock_context.repo_config = MagicMock()
        mock_context.repo_config.repo_path = "/repo"
        mock_context.remediation_id = "test-123"
        mock_run_build.return_value = (False, "build failed output")
        mock_extract_errors.return_value = "Compilation errors found"

        session = AgentSession()
        result = agent._validate_initial_build(session, mock_context)

        self.assertFalse(result)

    @patch('src.smartfix.domains.agents.smartfix_agent.SmartFixAgent._run_ai_fix_agent')
    def test_run_fix_agent_success(self, mock_run_ai_fix):
        """
        Tests successful fix agent execution.
        """
        agent = SmartFixAgent()
        session = AgentSession()
        mock_context = MagicMock(spec=RemediationContext)

        # Setup mocks with proper attribute structure
        mock_context.vulnerability = MagicMock()
        mock_context.vulnerability.title = "SQL Injection"
        mock_context.prompts = MagicMock()  # Required by _run_fix_agent
        mock_context.repo_config = MagicMock()  # Required by _run_fix_agent

        mock_run_ai_fix.return_value = "Fix applied successfully"

        result = agent._run_fix_agent(session, mock_context)

        self.assertIsNotNone(result)
        self.assertEqual(result, "Fix applied successfully")
        self.assertIsNone(session.failure_category)  # No failure category should be set on success

    @patch('src.smartfix.domains.agents.smartfix_agent.SmartFixAgent._run_ai_fix_agent')
    def test_run_fix_agent_error(self, mock_run_ai_fix):
        """
        Tests fix agent execution with error.
        """
        agent = SmartFixAgent()
        session = AgentSession()
        mock_context = MagicMock(spec=RemediationContext)

        # Setup mocks with proper attribute structure
        mock_context.vulnerability = MagicMock()
        mock_context.vulnerability.title = "SQL Injection"

        mock_run_ai_fix.return_value = "Error during AI fix agent execution: Something went wrong"

        result = agent._run_fix_agent(session, mock_context)

        self.assertIsNone(result)
        # Verify failure reason is set
        from src.smartfix.shared.failure_categories import FailureCategory
        self.assertEqual(session.failure_category, FailureCategory.AGENT_FAILURE)

    @patch('src.smartfix.domains.agents.smartfix_agent.SmartFixAgent._run_qa_loop_internal')
    def test_run_qa_loop_success(self, mock_run_qa):
        """
        Tests successful QA loop execution.
        """
        agent = SmartFixAgent()
        session = AgentSession()
        mock_context = MagicMock(spec=RemediationContext)

        # Set up build config for QA loop to run
        mock_context.build_config = MagicMock()
        mock_context.build_config.has_build_command.return_value = True

        mock_run_qa.return_value = (True, ["src/file1.py"], "npm test", ["QA attempt 1"])

        result = agent._run_qa_loop(session, mock_context, "fix_result")

        self.assertTrue(result)
        self.assertEqual(session.qa_attempts, 1)
        self.assertIsNone(session.failure_category)  # No failure category should be set on success

    def test_complete_remediation_workflow_success(self):
        """
        Tests the complete remediation workflow with all steps successful.
        """
        agent = SmartFixAgent()
        mock_context = MagicMock(spec=RemediationContext)

        # Setup context
        mock_context.build_config = MagicMock()
        mock_context.build_config.has_build_command.return_value = False  # Skip QA

        # Set should_try_building to False so _validate_initial_build is not called
        with patch.object(agent, '_run_fix_agent', return_value="success") as mock_fix:
            result = agent.remediate(mock_context)

            self.assertIsInstance(result, AgentSession)
            self.assertTrue(result.success)
            self.assertIsNone(result.failure_category)  # No failure category should be set

            # Validate that run_fix_agent was called
            mock_fix.assert_called_once()

    def test_complete_remediation_workflow_with_qa(self):
        """
        Tests the complete remediation workflow including QA validation.
        """
        agent = SmartFixAgent()
        mock_context = MagicMock(spec=RemediationContext)

        # Setup context for QA
        with patch('src.config.get_config') as mock_config:
            config_mock = MagicMock()
            config_mock.SKIP_QA_REVIEW = False
            mock_config.return_value = config_mock
            mock_context.build_config = MagicMock()
            mock_context.build_config.has_build_command.return_value = True

            with patch.object(agent, '_validate_initial_build', return_value=True) as mock_validate, \
                 patch.object(agent, '_run_fix_agent', return_value="success") as mock_fix, \
                 patch.object(agent, '_run_qa_loop', return_value=True) as mock_qa:

                result = agent.remediate(mock_context)

                self.assertTrue(result.success)
                self.assertIsNone(result.failure_category)  # No failure category should be set

                mock_validate.assert_called_once()
                mock_fix.assert_called_once()
                mock_qa.assert_called_once()


class TestAgentSession(unittest.TestCase):

    def test_session_initialization(self):
        """
        Tests the default state of a new AgentSession.
        """
        session = AgentSession()
        self.assertFalse(session.is_complete)
        self.assertEqual(session.qa_attempts, 0)
        self.assertIsNone(session.failure_category)
        self.assertIsNone(session.final_pr_body)

    def test_complete_session(self):
        """
        Tests that the AgentSession status and failure reason can be updated correctly.
        """
        session = AgentSession()
        self.assertFalse(session.is_complete)
        self.assertIsNone(session.failure_category)

        # Test setting success status with PR body
        pr_body = "Test PR Body"
        session.complete_session(pr_body=pr_body)
        self.assertTrue(session.is_complete)
        self.assertEqual(session.final_pr_body, pr_body)
        self.assertIsNone(session.failure_category)
        self.assertTrue(session.success)

        # Create a new session for failure test
        session = AgentSession()
        failure_category = FailureCategory.AGENT_FAILURE

        # Test setting error status with failure category
        session.complete_session(failure_category=failure_category)
        self.assertTrue(session.is_complete)
        self.assertEqual(session.failure_category, failure_category)
        self.assertFalse(session.success)


class TestCodingAgentStrategy(unittest.TestCase):

    def test_cannot_instantiate_abstract_class(self):
        """
        Ensures the abstract CodingAgentStrategy cannot be instantiated directly.
        """
        with self.assertRaises(TypeError):
            CodingAgentStrategy()

    def test_concrete_class_must_implement_remediate(self):
        """
        Tests that a subclass of CodingAgentStrategy must implement the remediate method.
        """
        class IncompleteAgent(CodingAgentStrategy):
            pass

        with self.assertRaises(TypeError):
            IncompleteAgent()

        class CompleteAgent(CodingAgentStrategy):
            def remediate(self, context: RemediationContext) -> AgentSession:
                session = AgentSession()
                session.complete_session(pr_body="Test PR Body")
                return session

        # This should not raise an error
        agent = CompleteAgent()
        self.assertIsNotNone(agent)


if __name__ == "__main__":
    unittest.main()
