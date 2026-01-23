"""
Tests for build_runner.py module.

Tests build execution, output capture, exit code handling, and telemetry integration.
"""

import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.smartfix.domains.workflow.build_runner import run_build_command


class TestBuildRunner(unittest.TestCase):
    """Tests for build command execution."""

    def setUp(self):
        """Set up mocks for each test."""
        # Mock telemetry to prevent actual telemetry calls
        self.telemetry_patcher = patch('src.telemetry_handler.update_telemetry')
        self.mock_telemetry = self.telemetry_patcher.start()

        # Mock subprocess.run
        self.subprocess_patcher = patch('subprocess.run')
        self.mock_subprocess = self.subprocess_patcher.start()

    def tearDown(self):
        """Clean up mocks after each test."""
        self.telemetry_patcher.stop()
        self.subprocess_patcher.stop()

    def test_build_succeeds_exit_code_0(self):
        """Test successful build with exit code 0."""
        # Setup mock
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "BUILD SUCCESS\n"
        mock_result.stderr = ""
        self.mock_subprocess.return_value = mock_result

        # Execute
        success, output = run_build_command(
            "mvn clean install",
            Path("/tmp/repo"),
            "test-remediation-id"
        )

        # Verify
        self.assertTrue(success)
        self.assertEqual(output, "BUILD SUCCESS\n")
        self.mock_subprocess.assert_called_once()
        self.mock_telemetry.assert_called_with("configInfo.buildCommandRunTestsIncluded", True)

    def test_build_fails_exit_code_1(self):
        """Test failed build with exit code 1."""
        # Setup mock
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "COMPILATION FAILED\n"
        self.mock_subprocess.return_value = mock_result

        # Execute
        success, output = run_build_command(
            "mvn clean install",
            Path("/tmp/repo"),
            "test-remediation-id"
        )

        # Verify
        self.assertFalse(success)
        self.assertEqual(output, "COMPILATION FAILED\n")
        self.mock_telemetry.assert_called_with("configInfo.buildCommandRunTestsIncluded", True)

    def test_build_different_exit_codes(self):
        """Test handling of various exit codes (2, 124, 137)."""
        test_cases = [
            (2, "Error: Invalid arguments\n"),
            (124, "Error: Timeout\n"),
            (137, "Error: Process killed\n"),
        ]

        for exit_code, error_msg in test_cases:
            with self.subTest(exit_code=exit_code):
                # Setup mock
                mock_result = MagicMock()
                mock_result.returncode = exit_code
                mock_result.stdout = ""
                mock_result.stderr = error_msg
                self.mock_subprocess.return_value = mock_result

                # Execute
                success, output = run_build_command(
                    "npm test",
                    Path("/tmp/repo"),
                    "test-remediation-id"
                )

                # Verify
                self.assertFalse(success)
                self.assertEqual(output, error_msg)

    def test_build_output_parsing_stdout_and_stderr(self):
        """Test that both stdout and stderr are captured and combined."""
        # Setup mock
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Standard output\n"
        mock_result.stderr = "Warning messages\n"
        self.mock_subprocess.return_value = mock_result

        # Execute
        success, output = run_build_command(
            "gradle build",
            Path("/tmp/repo"),
            "test-remediation-id"
        )

        # Verify
        self.assertTrue(success)
        self.assertEqual(output, "Standard output\nWarning messages\n")

    def test_build_command_not_found(self):
        """Test handling of FileNotFoundError when command doesn't exist."""
        # Setup mock to raise FileNotFoundError
        self.mock_subprocess.side_effect = FileNotFoundError("Command not found")

        # Mock error_exit to prevent actual exit
        with patch('src.smartfix.domains.workflow.build_runner.error_exit') as mock_error_exit:
            # Execute
            run_build_command(
                "nonexistent-command",
                Path("/tmp/repo"),
                "test-remediation-id"
            )

            # Verify error_exit was called
            mock_error_exit.assert_called_once_with("test-remediation-id")

    def test_build_unexpected_exception(self):
        """Test handling of unexpected exceptions during build."""
        # Setup mock to raise unexpected exception
        self.mock_subprocess.side_effect = RuntimeError("Unexpected error")

        # Mock error_exit to prevent actual exit
        with patch('src.smartfix.domains.workflow.build_runner.error_exit') as mock_error_exit:
            # Execute
            run_build_command(
                "mvn clean install",
                Path("/tmp/repo"),
                "test-remediation-id"
            )

            # Verify error_exit was called
            mock_error_exit.assert_called_once_with("test-remediation-id")

    def test_build_subprocess_call_parameters(self):
        """Test that subprocess.run is called with correct parameters."""
        # Setup mock
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Success"
        mock_result.stderr = ""
        self.mock_subprocess.return_value = mock_result

        # Execute
        command = "npm run build"
        repo_root = Path("/tmp/test-repo")
        run_build_command(command, repo_root, "test-remediation-id")

        # Verify subprocess.run was called with correct parameters
        self.mock_subprocess.assert_called_once_with(
            command,
            cwd=repo_root,
            shell=True,
            check=False,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )

    def test_build_telemetry_always_recorded(self):
        """Test that telemetry is recorded regardless of build outcome."""
        # Test successful build
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Success"
        mock_result.stderr = ""
        self.mock_subprocess.return_value = mock_result

        run_build_command("npm test", Path("/tmp/repo"), "test-remediation-id")
        self.mock_telemetry.assert_called_with("configInfo.buildCommandRunTestsIncluded", True)

        # Reset mock
        self.mock_telemetry.reset_mock()

        # Test failed build
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Failed"

        run_build_command("npm test", Path("/tmp/repo"), "test-remediation-id")
        self.mock_telemetry.assert_called_with("configInfo.buildCommandRunTestsIncluded", True)

    def test_build_encoding_handling(self):
        """Test that encoding errors are handled gracefully."""
        # Setup mock with unicode characters
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Test output with unicode: \u2713\n"
        mock_result.stderr = "Warning with emoji: \U0001F4A9\n"
        self.mock_subprocess.return_value = mock_result

        # Execute
        success, output = run_build_command(
            "npm test",
            Path("/tmp/repo"),
            "test-remediation-id"
        )

        # Verify
        self.assertTrue(success)
        self.assertIn("\u2713", output)
        self.assertIn("\U0001F4A9", output)


if __name__ == '__main__':
    unittest.main()
