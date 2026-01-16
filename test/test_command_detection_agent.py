# -
# #%L
# Contrast AI SmartFix
# %%
# Copyright (C) 2025 Contrast Security, Inc.
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
from src.smartfix.domains.agents.command_detection_agent import (
    CommandDetectionAgent,
    MaxAttemptsExceededError
)


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
        self.assertIn("Previous attempts", prompt)
        self.assertIn("mvn test", prompt)
        self.assertIn("mvn: command not found", prompt)
        self.assertIn("maven test", prompt)

    @patch('src.smartfix.domains.agents.command_detection_agent.SubAgentExecutor')
    def test_detect_raises_max_attempts_exceeded(self, mock_executor_class):
        """Test detect() raises MaxAttemptsExceededError after max attempts."""
        # Mock executor to return invalid command that fails validation
        mock_executor = Mock()
        mock_executor_class.return_value = mock_executor
        mock_executor.execute_detection.return_value = "invalid"

        agent = CommandDetectionAgent(self.repo_root, max_attempts=2)

        build_files = ["pom.xml"]
        failed_attempts = []
        remediation_id = "test-remediation-123"

        with self.assertRaises(MaxAttemptsExceededError) as context:
            agent.detect(
                build_files=build_files,
                failed_attempts=failed_attempts,
                remediation_id=remediation_id
            )

        # Error message should mention attempts
        self.assertIn("Could not detect valid build command", str(context.exception))
        self.assertIn("2 attempts", str(context.exception))

    @patch('src.smartfix.domains.agents.command_detection_agent.SubAgentExecutor')
    def test_detect_error_includes_build_files(self, mock_executor_class):
        """Test error message includes build files context."""
        # Mock executor to return invalid command
        mock_executor = Mock()
        mock_executor_class.return_value = mock_executor
        mock_executor.execute_detection.return_value = "invalid"

        agent = CommandDetectionAgent(self.repo_root, max_attempts=1)

        build_files = ["pom.xml", "build.gradle"]
        failed_attempts = []
        remediation_id = "test-remediation-123"

        with self.assertRaises(MaxAttemptsExceededError) as context:
            agent.detect(build_files, failed_attempts, remediation_id)

        error_msg = str(context.exception)
        self.assertIn("pom.xml", error_msg)
        self.assertIn("build.gradle", error_msg)

    @patch('src.smartfix.domains.agents.command_detection_agent.SubAgentExecutor')
    def test_detect_error_includes_last_attempt(self, mock_executor_class):
        """Test error message includes last failed attempt details."""
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

        with self.assertRaises(MaxAttemptsExceededError) as context:
            agent.detect(build_files, failed_attempts, remediation_id)

        error_msg = str(context.exception)
        self.assertIn("Last attempt:", error_msg)
        self.assertIn("Last error:", error_msg)

    @patch('src.smartfix.domains.agents.command_detection_agent.run_build_command')
    @patch('src.smartfix.domains.agents.command_detection_agent.validate_command')
    @patch('src.smartfix.domains.agents.command_detection_agent.SubAgentExecutor')
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
    @patch('src.smartfix.domains.agents.command_detection_agent.SubAgentExecutor')
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
        second_call_prompt = mock_executor.execute_detection.call_args_list[1][0][0]
        self.assertIn("rm -rf /", second_call_prompt)
        self.assertIn("Dangerous command", second_call_prompt)

    @patch('src.smartfix.domains.agents.command_detection_agent.extract_build_errors')
    @patch('src.smartfix.domains.agents.command_detection_agent.run_build_command')
    @patch('src.smartfix.domains.agents.command_detection_agent.validate_command')
    @patch('src.smartfix.domains.agents.command_detection_agent.SubAgentExecutor')
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
        second_call_prompt = mock_executor.execute_detection.call_args_list[1][0][0]
        self.assertIn("mvn clean", second_call_prompt)
        self.assertIn("No tests found", second_call_prompt)

    @patch('src.smartfix.domains.agents.command_detection_agent.run_build_command')
    @patch('src.smartfix.domains.agents.command_detection_agent.validate_command')
    @patch('src.smartfix.domains.agents.command_detection_agent.SubAgentExecutor')
    def test_detect_exhausts_max_attempts(self, mock_executor_class, mock_validate, mock_run_build):
        """Test agent raises error after exhausting max attempts."""
        # Setup mocks - all attempts fail validation
        mock_executor = Mock()
        mock_executor_class.return_value = mock_executor
        mock_executor.execute_detection.return_value = "invalid command"

        from src.smartfix.config.command_validator import CommandValidationError
        mock_validate.side_effect = CommandValidationError("Invalid")

        # Execute
        agent = CommandDetectionAgent(self.repo_root, max_attempts=2)

        with self.assertRaises(MaxAttemptsExceededError) as context:
            agent.detect(
                build_files=["pom.xml"],
                failed_attempts=[],
                remediation_id="test-123"
            )

        # Verify - should have tried exactly max_attempts times
        self.assertEqual(mock_executor.execute_detection.call_count, 2)
        error_msg = str(context.exception)
        self.assertIn("2 attempts", error_msg)
        self.assertIn("invalid command", error_msg)


if __name__ == '__main__':
    unittest.main()
