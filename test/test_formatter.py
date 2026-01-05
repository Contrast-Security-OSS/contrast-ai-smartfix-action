"""
Tests for formatter.py module.

Tests formatter execution, graceful degradation, and error handling.
"""

import unittest
import os
from pathlib import Path
from unittest.mock import patch

from src.smartfix.domains.workflow.formatter import run_formatting_command


class TestFormatter(unittest.TestCase):
    """Tests for formatting command execution."""

    def setUp(self):
        """Set up mocks for each test."""
        # Store original cwd to restore later
        self.original_cwd = os.getcwd()

        # Mock run_command from utils
        self.run_command_patcher = patch('src.smartfix.domains.workflow.formatter.run_command')
        self.mock_run_command = self.run_command_patcher.start()

        # Mock os.chdir to prevent actual directory changes
        self.chdir_patcher = patch('os.chdir')
        self.mock_chdir = self.chdir_patcher.start()

    def tearDown(self):
        """Clean up mocks after each test."""
        self.run_command_patcher.stop()
        self.chdir_patcher.stop()
        # Ensure we're back in original directory
        os.chdir(self.original_cwd)

    def test_formatter_succeeds(self):
        """Test successful formatter execution."""
        # Setup mock
        self.mock_run_command.return_value = "Formatted 3 files\n"

        # Execute
        result = run_formatting_command(
            "black .",
            Path("/tmp/repo"),
            "test-remediation-id"
        )

        # Verify
        self.assertEqual(result, [])  # Returns empty list (no files tracked)
        self.mock_run_command.assert_called_once_with(
            ["black", "."],
            check=False
        )
        # Verify directory changes
        self.assertEqual(self.mock_chdir.call_count, 2)  # chdir to repo_root and back

    def test_formatter_no_command_provided(self):
        """Test behavior when no formatting command is provided."""
        # Execute with None
        result = run_formatting_command(
            None,
            Path("/tmp/repo"),
            "test-remediation-id"
        )

        # Verify
        self.assertEqual(result, [])
        self.mock_run_command.assert_not_called()
        self.mock_chdir.assert_not_called()

    def test_formatter_empty_string(self):
        """Test behavior when empty string is provided."""
        # Execute with empty string
        result = run_formatting_command(
            "",
            Path("/tmp/repo"),
            "test-remediation-id"
        )

        # Verify
        self.assertEqual(result, [])
        self.mock_run_command.assert_not_called()
        self.mock_chdir.assert_not_called()

    def test_formatter_fails_error_exit_called(self):
        """Test that error_exit is called when formatter fails."""
        # Setup mock to raise exception
        self.mock_run_command.side_effect = Exception("Formatter error")

        # Mock error_exit to prevent actual exit
        with patch('src.smartfix.domains.workflow.formatter.error_exit') as mock_error_exit:
            # Execute
            run_formatting_command(
                "prettier --write .",
                Path("/tmp/repo"),
                "test-remediation-id"
            )

            # Verify error_exit was called
            mock_error_exit.assert_called_once_with("test-remediation-id")

    def test_formatter_directory_change_and_restore(self):
        """Test that directory is changed to repo_root and restored."""
        # Setup mock
        self.mock_run_command.return_value = "Success"

        # Execute
        repo_root = Path("/tmp/test-repo")
        run_formatting_command(
            "black .",
            repo_root,
            "test-remediation-id"
        )

        # Verify directory changes
        calls = self.mock_chdir.call_args_list
        self.assertEqual(len(calls), 2)
        # First call should change to repo_root
        self.assertEqual(calls[0][0][0], str(repo_root))
        # Second call should restore original directory
        self.assertEqual(calls[1][0][0], self.original_cwd)

    def test_formatter_directory_restored_on_exception(self):
        """Test that directory is restored even if formatter raises exception."""
        # Setup mock to raise exception
        self.mock_run_command.side_effect = RuntimeError("Formatter crashed")

        # Mock error_exit to prevent actual exit
        with patch('src.smartfix.domains.workflow.formatter.error_exit'):
            # Execute
            repo_root = Path("/tmp/test-repo")
            run_formatting_command(
                "black .",
                repo_root,
                "test-remediation-id"
            )

            # Verify directory was restored (chdir called twice)
            self.assertEqual(self.mock_chdir.call_count, 2)
            calls = self.mock_chdir.call_args_list
            # First call: change to repo_root
            self.assertEqual(calls[0][0][0], str(repo_root))
            # Second call: restore original
            self.assertEqual(calls[1][0][0], self.original_cwd)

    def test_formatter_command_parsing(self):
        """Test that formatter command is correctly split into arguments."""
        # Setup mock
        self.mock_run_command.return_value = "Success"

        # Execute with multi-word command
        run_formatting_command(
            "prettier --write --config .prettierrc .",
            Path("/tmp/repo"),
            "test-remediation-id"
        )

        # Verify command was split correctly
        self.mock_run_command.assert_called_once_with(
            ["prettier", "--write", "--config", ".prettierrc", "."],
            check=False
        )

    def test_formatter_file_not_found_error(self):
        """Test handling of FileNotFoundError when formatter binary doesn't exist."""
        # Setup mock to raise FileNotFoundError
        self.mock_run_command.side_effect = FileNotFoundError("black: command not found")

        # Mock error_exit to prevent actual exit
        with patch('src.smartfix.domains.workflow.formatter.error_exit') as mock_error_exit:
            # Execute
            run_formatting_command(
                "black .",
                Path("/tmp/repo"),
                "test-remediation-id"
            )

            # Verify error_exit was called
            mock_error_exit.assert_called_once_with("test-remediation-id")

    def test_formatter_timeout_error(self):
        """Test handling of timeout during formatter execution."""
        # Setup mock to raise TimeoutError
        import subprocess
        self.mock_run_command.side_effect = subprocess.TimeoutExpired("black", 30)

        # Mock error_exit to prevent actual exit
        with patch('src.smartfix.domains.workflow.formatter.error_exit') as mock_error_exit:
            # Execute
            run_formatting_command(
                "black .",
                Path("/tmp/repo"),
                "test-remediation-id"
            )

            # Verify error_exit was called
            mock_error_exit.assert_called_once_with("test-remediation-id")

    def test_formatter_permission_error(self):
        """Test handling of permission errors during formatter execution."""
        # Setup mock to raise PermissionError
        self.mock_run_command.side_effect = PermissionError("Permission denied")

        # Mock error_exit to prevent actual exit
        with patch('src.smartfix.domains.workflow.formatter.error_exit') as mock_error_exit:
            # Execute
            run_formatting_command(
                "black .",
                Path("/tmp/repo"),
                "test-remediation-id"
            )

            # Verify error_exit was called
            mock_error_exit.assert_called_once_with("test-remediation-id")

    def test_formatter_multiple_sequential_calls(self):
        """Test multiple sequential formatter calls."""
        # Setup mock
        self.mock_run_command.return_value = "Success"

        # Execute multiple times
        formatters = ["black .", "prettier --write .", "isort ."]
        for formatter in formatters:
            result = run_formatting_command(
                formatter,
                Path("/tmp/repo"),
                "test-remediation-id"
            )
            self.assertEqual(result, [])

        # Verify all were called
        self.assertEqual(self.mock_run_command.call_count, 3)

    def test_formatter_returns_empty_list(self):
        """Test that formatter always returns empty list (changed files not tracked)."""
        # Setup mock
        self.mock_run_command.return_value = "Formatted: file1.py, file2.py"

        # Execute
        result = run_formatting_command(
            "black .",
            Path("/tmp/repo"),
            "test-remediation-id"
        )

        # Verify returns empty list (note in code says git operations handled by main.py)
        self.assertEqual(result, [])
        self.assertIsInstance(result, list)


if __name__ == '__main__':
    unittest.main()
