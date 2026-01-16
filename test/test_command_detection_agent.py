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

    def test_detect_raises_max_attempts_exceeded(self):
        """Test detect() raises MaxAttemptsExceededError after max attempts."""
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

    def test_detect_error_includes_build_files(self):
        """Test error message includes build files context."""
        agent = CommandDetectionAgent(self.repo_root, max_attempts=1)

        build_files = ["pom.xml", "build.gradle"]
        failed_attempts = []
        remediation_id = "test-remediation-123"

        with self.assertRaises(MaxAttemptsExceededError) as context:
            agent.detect(build_files, failed_attempts, remediation_id)

        error_msg = str(context.exception)
        self.assertIn("pom.xml", error_msg)
        self.assertIn("build.gradle", error_msg)

    def test_detect_error_includes_last_attempt(self):
        """Test error message includes last failed attempt details."""
        agent = CommandDetectionAgent(self.repo_root, max_attempts=1)

        build_files = ["pom.xml"]
        failed_attempts = [
            {"command": "mvn test", "error": "mvn: command not found"}
        ]
        remediation_id = "test-remediation-123"

        with self.assertRaises(MaxAttemptsExceededError) as context:
            agent.detect(build_files, failed_attempts, remediation_id)

        error_msg = str(context.exception)
        self.assertIn("Last attempt: mvn test", error_msg)
        self.assertIn("Last error: mvn: command not found", error_msg)


if __name__ == '__main__':
    unittest.main()
