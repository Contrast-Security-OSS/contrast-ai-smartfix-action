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
GIT_OPERATIONS_PATCHES = [
    'src.smartfix.domains.scm.git_operations.GitOperations.prepare_feature_branch',
    'src.smartfix.domains.scm.git_operations.GitOperations.stage_changes',
    'src.smartfix.domains.scm.git_operations.GitOperations.check_status',
    'src.smartfix.domains.scm.git_operations.GitOperations.commit_changes',
    'src.smartfix.domains.scm.git_operations.GitOperations.amend_commit',
    'src.smartfix.domains.scm.git_operations.GitOperations.get_last_commit_changed_files',
    'src.smartfix.domains.scm.git_operations.GitOperations.get_uncommitted_changed_files',
    'src.smartfix.domains.scm.git_operations.GitOperations.push_branch',
    'src.smartfix.domains.scm.git_operations.GitOperations.cleanup_branch'
]


class TestSmartFixAgent(unittest.TestCase):

    def setUp(self):
        """Set up mocks to prevent git operations in all tests"""
        # Reset and get test config
        reset_config()
        self.config = get_config(testing=True)

        # Start all git operations patches
        self.git_mocks = []
        for patch_target in GIT_OPERATIONS_PATCHES:
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

    def test_complete_remediation_workflow_success(self):
        """
        Tests the complete remediation workflow with all steps successful.
        """
        agent = SmartFixAgent()
        mock_context = MagicMock(spec=RemediationContext)

        # Setup context — no build command so PR gate is skipped
        mock_context.build_config = MagicMock()
        mock_context.build_config.has_build_command.return_value = False

        with patch.object(agent, '_run_fix_agent', return_value="success") as mock_fix:
            result = agent.remediate(mock_context)

            self.assertIsInstance(result, AgentSession)
            self.assertTrue(result.success)
            self.assertIsNone(result.failure_category)

            mock_fix.assert_called_once()

    @patch('src.smartfix.domains.agents.smartfix_agent.get_successful_build_command')
    def test_complete_remediation_workflow_with_build_verification(self, mock_get_cmd):
        """
        Tests the complete remediation workflow with BuildTool verification (PR gate).
        """
        mock_get_cmd.return_value = "mvn test"

        agent = SmartFixAgent()
        mock_context = MagicMock(spec=RemediationContext)
        mock_context.build_config = MagicMock()
        mock_context.build_config.has_build_command.return_value = True

        with patch.object(agent, '_run_fix_agent', return_value="success") as mock_fix:
            result = agent.remediate(mock_context)

            self.assertTrue(result.success)
            self.assertIsNone(result.failure_category)
            mock_fix.assert_called_once()


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
