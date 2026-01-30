# -
# #%L
# Contrast AI SmartFix
# %%
# Copyright (C) 2026 Contrast Security, Inc.
# %%
# Contact: support@contrastsecurity.com
# License: Commercial
# #L%
#

"""
Tests for CommandDetectionAgent.
"""

import unittest
from unittest.mock import Mock, patch
from pathlib import Path
from src.smartfix.domains.agents.command_detection_agent import CommandDetectionAgent


class TestCommandDetectionAgent(unittest.TestCase):
    """Test CommandDetectionAgent class."""

    def setUp(self):
        """Set up test fixtures."""
        self.repo_root = Path("/tmp/test_repo")
        self.max_attempts = 6

    def test_init(self):
        """Test agent initialization."""
        agent = CommandDetectionAgent(self.repo_root, max_attempts=self.max_attempts)

        self.assertEqual(agent.repo_root, self.repo_root)
        self.assertEqual(agent.max_attempts, self.max_attempts)
        self.assertIsNone(agent.project_dir)

    def test_init_with_project_dir(self):
        """Test agent initialization with project directory."""
        project_dir = Path("/tmp/test_repo/backend")
        agent = CommandDetectionAgent(self.repo_root, project_dir=project_dir, max_attempts=3)

        self.assertEqual(agent.project_dir, project_dir)
        self.assertEqual(agent.max_attempts, 3)

    def test_build_iteration_prompt_first_attempt(self):
        """Test building prompt for first iteration."""
        agent = CommandDetectionAgent(self.repo_root)

        build_files = ["pom.xml", "build.gradle"]
        failed_attempts = []

        prompt = agent._build_iteration_prompt(build_files, failed_attempts)

        # Should include build files
        self.assertIn("pom.xml", prompt)
        self.assertIn("build.gradle", prompt)
        # Should not mention previous attempts on first iteration
        self.assertNotIn("Previous attempts", prompt)

    def test_build_iteration_prompt_with_failures(self):
        """Test building prompt with failed attempt history."""
        agent = CommandDetectionAgent(self.repo_root)

        build_files = ["pom.xml"]
        failed_attempts = [
            {
                "command": "mvn test",
                "error": "mvn: command not found"
            },
            {
                "command": "maven test",
                "error": "maven: command not found"
            }
        ]

        prompt = agent._build_iteration_prompt(build_files, failed_attempts)

        # Should include failed attempt history
        self.assertIn("Failed Command Attempts", prompt)
        self.assertIn("mvn test", prompt)
        self.assertIn("mvn: command not found", prompt)
        self.assertIn("maven test", prompt)

    @patch('src.smartfix.domains.agents.sub_agent_executor.SubAgentExecutor')
    def test_detect_returns_none_after_max_attempts(self, mock_executor_class):
        """Test detect() returns None after max attempts exhausted."""
        # Mock executor to return invalid command that fails validation
        mock_executor = Mock()
        mock_executor_class.return_value = mock_executor
        mock_executor.execute_detection.return_value = "invalid"

        agent = CommandDetectionAgent(self.repo_root, max_attempts=2)

        build_files = ["pom.xml"]
        failed_attempts = []
        remediation_id = "test-remediation-123"

        # Should return None when max attempts exhausted
        result = agent.detect(
            build_files=build_files,
            failed_attempts=failed_attempts,
            remediation_id=remediation_id
        )

        # Should return None instead of raising exception
        self.assertIsNone(result)

    @patch('src.smartfix.domains.agents.command_detection_agent.log')
    @patch('src.smartfix.domains.agents.sub_agent_executor.SubAgentExecutor')
    def test_detect_logs_build_files_on_exhaustion(self, mock_executor_class, mock_log):
        """Test logging includes build files context when exhausted."""
        # Mock executor to return invalid command
        mock_executor = Mock()
        mock_executor_class.return_value = mock_executor
        mock_executor.execute_detection.return_value = "invalid"

        agent = CommandDetectionAgent(self.repo_root, max_attempts=1)

        build_files = ["pom.xml", "build.gradle"]
        failed_attempts = []
        remediation_id = "test-remediation-123"

        result = agent.detect(build_files, failed_attempts, remediation_id)

        # Should return None
        self.assertIsNone(result)
        # Should log warning with build files
        # Find the warning call (with is_warning=True)
        warning_calls = [call for call in mock_log.call_args_list
                         if len(call[0]) > 0 and "pom.xml" in call[0][0]]
        self.assertTrue(len(warning_calls) > 0)
        warning_msg = warning_calls[0][0][0]
        self.assertIn("pom.xml", warning_msg)
        self.assertIn("build.gradle", warning_msg)

    @patch('src.smartfix.domains.agents.command_detection_agent.log')
    @patch('src.smartfix.domains.agents.sub_agent_executor.SubAgentExecutor')
    def test_detect_logs_last_attempt_details(self, mock_executor_class, mock_log):
        """Test logging includes last failed attempt details when exhausted."""
        # Mock executor to return invalid command
        mock_executor = Mock()
        mock_executor_class.return_value = mock_executor
        mock_executor.execute_detection.return_value = "invalid"

        agent = CommandDetectionAgent(self.repo_root, max_attempts=1)

        build_files = ["pom.xml"]
        failed_attempts = [
            {"command": "mvn test", "error": "mvn: command not found"}
        ]
        remediation_id = "test-remediation-123"

        result = agent.detect(build_files, failed_attempts, remediation_id)

        # Should return None
        self.assertIsNone(result)
        # Should log warning with last attempt details
        # Find the warning call (with is_warning=True)
        warning_calls = [call for call in mock_log.call_args_list
                         if len(call[0]) > 0 and "Last attempt:" in call[0][0]]
        self.assertTrue(len(warning_calls) > 0)
        warning_msg = warning_calls[0][0][0]
        self.assertIn("Last attempt:", warning_msg)
        self.assertIn("Last error:", warning_msg)

    @patch('src.smartfix.domains.agents.command_detection_agent.run_build_command')
    @patch('src.smartfix.domains.agents.command_detection_agent.validate_command')
    @patch('src.smartfix.domains.agents.sub_agent_executor.SubAgentExecutor')
    def test_detect_successful_on_first_attempt(self, mock_executor_class, mock_validate, mock_run_build):
        """Test successful detection on first LLM attempt."""
        # Setup mocks
        mock_executor = Mock()
        mock_executor_class.return_value = mock_executor
        mock_executor.execute_detection.return_value = "mvn test"

        mock_validate.return_value = None  # No validation errors
        mock_run_build.return_value = (True, "Build successful")

        # Execute
        agent = CommandDetectionAgent(self.repo_root, max_attempts=3)
        result = agent.detect(
            build_files=["pom.xml"],
            failed_attempts=[],
            remediation_id="test-123"
        )

        # Verify
        self.assertEqual(result, "mvn test")
        mock_executor.execute_detection.assert_called_once()
        mock_validate.assert_called_once_with("BUILD_COMMAND", "mvn test")
        mock_run_build.assert_called_once()

    @patch('src.smartfix.domains.agents.command_detection_agent.run_build_command')
    @patch('src.smartfix.domains.agents.command_detection_agent.validate_command')
    @patch('src.smartfix.domains.agents.sub_agent_executor.SubAgentExecutor')
    def test_detect_retries_on_validation_failure(self, mock_executor_class, mock_validate, mock_run_build):
        """Test agent retries when validation fails."""
        # Setup mocks - first command fails validation, second succeeds
        mock_executor = Mock()
        mock_executor_class.return_value = mock_executor
        mock_executor.execute_detection.side_effect = [
            "rm -rf /",  # Invalid command
            "mvn test"   # Valid command
        ]

        from src.smartfix.config.command_validator import CommandValidationError
        mock_validate.side_effect = [
            CommandValidationError("Dangerous command"),  # First fails
            None  # Second passes
        ]
        mock_run_build.return_value = (True, "Build successful")

        # Execute
        agent = CommandDetectionAgent(self.repo_root, max_attempts=3)
        result = agent.detect(
            build_files=["pom.xml"],
            failed_attempts=[],
            remediation_id="test-123"
        )

        # Verify - should have called LLM twice
        self.assertEqual(result, "mvn test")
        self.assertEqual(mock_executor.execute_detection.call_count, 2)
        # Second call should include first failed attempt in prompt
        second_call_prompt = mock_executor.execute_detection.call_args_list[1][1]['prompt']
        self.assertIn("rm -rf /", second_call_prompt)
        self.assertIn("Dangerous command", second_call_prompt)

    @patch('src.smartfix.domains.agents.command_detection_agent.extract_build_errors')
    @patch('src.smartfix.domains.agents.command_detection_agent.run_build_command')
    @patch('src.smartfix.domains.agents.command_detection_agent.validate_command')
    @patch('src.smartfix.domains.agents.sub_agent_executor.SubAgentExecutor')
    def test_detect_retries_on_build_failure(self, mock_executor_class, mock_validate, mock_run_build, mock_extract_errors):
        """Test agent retries when build command fails."""
        # Setup mocks - first command fails build, second succeeds
        mock_executor = Mock()
        mock_executor_class.return_value = mock_executor
        mock_executor.execute_detection.side_effect = [
            "mvn clean",   # Wrong command
            "mvn test"     # Correct command
        ]

        mock_validate.return_value = None
        mock_run_build.side_effect = [
            (False, "Error: No tests found"),  # First fails
            (True, "Tests passed")             # Second succeeds
        ]
        mock_extract_errors.return_value = "No tests found"

        # Execute
        agent = CommandDetectionAgent(self.repo_root, max_attempts=3)
        result = agent.detect(
            build_files=["pom.xml"],
            failed_attempts=[],
            remediation_id="test-123"
        )

        # Verify - should have called LLM twice
        self.assertEqual(result, "mvn test")
        self.assertEqual(mock_executor.execute_detection.call_count, 2)
        # Second call should include first failed attempt with build error
        second_call_prompt = mock_executor.execute_detection.call_args_list[1][1]['prompt']
        self.assertIn("mvn clean", second_call_prompt)
        self.assertIn("No tests found", second_call_prompt)

    @patch('src.smartfix.domains.agents.command_detection_agent.log')
    @patch('src.smartfix.domains.agents.command_detection_agent.run_build_command')
    @patch('src.smartfix.domains.agents.command_detection_agent.validate_command')
    @patch('src.smartfix.domains.agents.sub_agent_executor.SubAgentExecutor')
    def test_detect_exhausts_max_attempts(self, mock_executor_class, mock_validate, mock_run_build, mock_log):
        """Test agent returns None and logs after exhausting max attempts."""
        # Setup mocks - all attempts fail validation
        mock_executor = Mock()
        mock_executor_class.return_value = mock_executor
        mock_executor.execute_detection.return_value = "invalid command"

        from src.smartfix.config.command_validator import CommandValidationError
        mock_validate.side_effect = CommandValidationError("Invalid")

        # Execute
        agent = CommandDetectionAgent(self.repo_root, max_attempts=2)

        result = agent.detect(
            build_files=["pom.xml"],
            failed_attempts=[],
            remediation_id="test-123"
        )

        # Verify - should have tried exactly max_attempts times
        self.assertEqual(mock_executor.execute_detection.call_count, 2)
        # Should return None
        self.assertIsNone(result)
        # Should log warning with attempt details
        # Find the warning call (with is_warning=True)
        warning_calls = [call for call in mock_log.call_args_list
                         if len(call[0]) > 0 and "2 attempts" in call[0][0]]
        self.assertTrue(len(warning_calls) > 0)
        warning_msg = warning_calls[0][0][0]
        self.assertIn("2 attempts", warning_msg)
        self.assertIn("invalid command", warning_msg)

    @patch('src.smartfix.domains.agents.sub_agent_executor.SubAgentExecutor')
    def test_phase1_failures_appear_in_first_prompt(self, mock_executor_class):
        """Test Phase 1 failure history is included in first LLM prompt."""
        # Setup mocks
        mock_executor = Mock()
        mock_executor_class.return_value = mock_executor
        mock_executor.execute_detection.return_value = "invalid"

        agent = CommandDetectionAgent(self.repo_root, max_attempts=1)

        # Phase 1 failures from detect_build_command
        phase1_failures = [
            {"command": "mvn test", "error": "mvn: command not found"},
            {"command": "gradle test", "error": "gradle: command not found"}
        ]

        agent.detect(
            build_files=["pom.xml", "build.gradle"],
            failed_attempts=phase1_failures,
            remediation_id="test-123"
        )

        # Verify Phase 1 failures are in first LLM prompt
        mock_executor.execute_detection.assert_called_once()
        # execute_detection now takes (prompt, target_folder, remediation_id)
        first_prompt = mock_executor.execute_detection.call_args[1]['prompt']
        self.assertIn("Failed Command Attempts", first_prompt)
        self.assertIn("mvn test", first_prompt)
        self.assertIn("mvn: command not found", first_prompt)
        self.assertIn("gradle test", first_prompt)
        self.assertIn("gradle: command not found", first_prompt)

    @patch('src.smartfix.domains.agents.command_detection_agent.run_build_command')
    @patch('src.smartfix.domains.agents.command_detection_agent.validate_command')
    @patch('src.smartfix.domains.agents.sub_agent_executor.SubAgentExecutor')
    def test_validation_failures_added_to_history(self, mock_executor_class, mock_validate, mock_run_build):
        """Test failures (both validation and build) are added to attempt_history for subsequent iterations.

        Scenario: validation fail -> build fail -> success (3 iterations total)
        """
        # Setup mocks - first fails validation, second passes validation but fails build, third succeeds
        mock_executor = Mock()
        mock_executor_class.return_value = mock_executor
        mock_executor.execute_detection.side_effect = [
            "rm -rf /",        # Invalid (validation fails)
            "mvn clean",       # Valid but wrong (build fails)
            "mvn test"         # Valid and correct
        ]

        from src.smartfix.config.command_validator import CommandValidationError
        mock_validate.side_effect = [
            CommandValidationError("Dangerous command"),  # First fails validation
            None,  # Second passes validation
            None   # Third passes validation
        ]
        mock_run_build.side_effect = [
            (False, "No tests found"),  # Second fails build
            (True, "Tests passed")      # Third succeeds
        ]

        # Execute
        agent = CommandDetectionAgent(self.repo_root, max_attempts=3)
        result = agent.detect(
            build_files=["pom.xml"],
            failed_attempts=[],
            remediation_id="test-123"
        )

        # Verify success
        self.assertEqual(result, "mvn test")

        # Verify validation failure was added to history
        # Check second prompt includes validation failure
        second_prompt = mock_executor.execute_detection.call_args_list[1][1]['prompt']
        self.assertIn("rm -rf /", second_prompt)
        self.assertIn("Command validation failed", second_prompt)
        self.assertIn("Dangerous command", second_prompt)

        # Verify build failure was also added to history
        # Check third prompt includes both failures with consistent formatting
        third_prompt = mock_executor.execute_detection.call_args_list[2][1]['prompt']
        self.assertIn("rm -rf /", third_prompt)
        self.assertIn("mvn clean", third_prompt)
        # Verify consistent error format for both types of failures
        self.assertIn("Attempt", third_prompt)
        self.assertIn("Command tried:", third_prompt)
        self.assertIn("Error encountered:", third_prompt)

    @patch('src.smartfix.domains.agents.command_detection_agent.run_build_command')
    @patch('src.smartfix.domains.agents.command_detection_agent.validate_command')
    @patch('src.smartfix.domains.agents.sub_agent_executor.SubAgentExecutor')
    def test_run_build_command_called_with_correct_parameters(self, mock_executor_class, mock_validate, mock_run_build):
        """Test run_build_command is called with correct parameters."""
        # Setup mocks
        mock_executor = Mock()
        mock_executor_class.return_value = mock_executor
        mock_executor.execute_detection.return_value = "mvn test"
        mock_validate.return_value = None
        mock_run_build.return_value = (True, "Build successful")

        # Execute with specific repo_root and remediation_id
        repo_root = Path("/test/repo/path")
        remediation_id = "test-remediation-456"
        agent = CommandDetectionAgent(repo_root, max_attempts=3)

        result = agent.detect(
            build_files=["pom.xml"],
            failed_attempts=[],
            remediation_id=remediation_id
        )

        # Verify run_build_command was called with correct parameters
        mock_run_build.assert_called_once_with("mvn test", repo_root, remediation_id)
        self.assertEqual(result, "mvn test")

    @patch('src.smartfix.domains.agents.sub_agent_executor.SubAgentExecutor')
    def test_empty_build_files_handled_correctly(self, mock_executor_class):
        """Test agent handles empty build_files list correctly.

        Empty build_files should still trigger detection (LLM may know what to do),
        but will return None after exhausting attempts with invalid command.
        """
        # Setup mocks
        mock_executor = Mock()
        mock_executor_class.return_value = mock_executor
        mock_executor.execute_detection.return_value = "invalid"

        agent = CommandDetectionAgent(self.repo_root, max_attempts=1)

        # Empty build_files list
        result = agent.detect(
            build_files=[],
            failed_attempts=[],
            remediation_id="test-123"
        )

        # Should still attempt detection (LLM might know what to do)
        mock_executor.execute_detection.assert_called_once()
        # Prompt should handle empty build_files gracefully
        first_prompt = mock_executor.execute_detection.call_args[1]['prompt']
        self.assertIn("Build System Detection", first_prompt)
        self.assertIn("Phase 1 did not find any standard build system files", first_prompt)
        # Should return None after exhausting attempts with invalid command
        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
