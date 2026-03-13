#!/usr/bin/env python3

import unittest
from pathlib import Path
from unittest.mock import patch

from src.smartfix.domains.agents.build_tool import (
    create_build_tool,
    get_successful_build_command,
    get_successful_format_command,
    reset_storage,
    _is_recordable_command,
    _truncate_tail,
)
from src.smartfix.config.command_validator import CommandValidationError


class TestBuildToolStorage(unittest.TestCase):
    """Test module-level storage functions."""

    def setUp(self):
        reset_storage()

    def tearDown(self):
        reset_storage()

    def test_initial_state_is_none(self):
        self.assertIsNone(get_successful_build_command())
        self.assertIsNone(get_successful_format_command())

    def test_reset_clears_storage(self):
        # Use create_build_tool to set storage via a successful build
        tool = create_build_tool(Path("/fake"), "rem-1")
        with patch('src.smartfix.domains.agents.build_tool.run_build_command', return_value=(True, "ok")):
            tool("make test")
        self.assertIsNotNone(get_successful_build_command())
        reset_storage()
        self.assertIsNone(get_successful_build_command())
        self.assertIsNone(get_successful_format_command())


class TestIsRecordableCommand(unittest.TestCase):
    """Test _is_recordable_command filtering."""

    def test_real_build_commands_are_recordable(self):
        self.assertTrue(_is_recordable_command("mvn test"))
        self.assertTrue(_is_recordable_command("npm run build"))
        self.assertTrue(_is_recordable_command("pytest"))
        self.assertTrue(_is_recordable_command("gradle build"))

    def test_version_commands_not_recordable(self):
        self.assertFalse(_is_recordable_command("mvn --version"))
        self.assertFalse(_is_recordable_command("node --version"))

    def test_help_commands_not_recordable(self):
        self.assertFalse(_is_recordable_command("mvn --help"))

    def test_shell_utilities_not_recordable(self):
        self.assertFalse(_is_recordable_command("echo hello"))
        self.assertFalse(_is_recordable_command("bash -c 'echo test'"))
        self.assertFalse(_is_recordable_command("cat file.txt"))

    def test_full_path_shell_utilities_not_recordable(self):
        self.assertFalse(_is_recordable_command("/usr/bin/echo hello"))

    def test_empty_command_not_recordable(self):
        self.assertFalse(_is_recordable_command(""))
        self.assertFalse(_is_recordable_command(None))


class TestTruncateTail(unittest.TestCase):
    """Test _truncate_tail output limiting."""

    def test_short_output_unchanged(self):
        self.assertEqual(_truncate_tail("hello\nworld", 100), "hello\nworld")

    def test_long_output_truncated_to_tail(self):
        lines = [f"line {i}" for i in range(200)]
        result = _truncate_tail("\n".join(lines), max_lines=50)
        result_lines = result.splitlines()
        self.assertEqual(len(result_lines), 50)
        self.assertIn("line 199", result_lines[-1])

    def test_empty_output(self):
        self.assertEqual(_truncate_tail("", 100), "")
        self.assertEqual(_truncate_tail(None, 100), "")


class TestBuildToolConfiguredMode(unittest.TestCase):
    """Test configured vs determined command validation."""

    def setUp(self):
        reset_storage()

    def tearDown(self):
        reset_storage()

    @patch('src.smartfix.domains.agents.build_tool.run_build_command', return_value=(True, "BUILD SUCCESS"))
    def test_configured_command_skips_validation(self, mock_build):
        """User-configured command (exact match) should skip allowlist validation."""
        tool = create_build_tool(
            Path("/repo"), "rem-1",
            user_build_command="mvn test",
        )
        with patch('src.smartfix.domains.agents.build_tool.validate_command') as mock_validate:
            result = tool("mvn test")
            mock_validate.assert_not_called()
            self.assertTrue(result["success"])

    @patch('src.smartfix.domains.agents.build_tool.run_build_command', return_value=(True, "BUILD SUCCESS"))
    def test_determined_command_validates_against_allowlist(self, mock_build):
        """Non-user-configured command must pass allowlist validation."""
        tool = create_build_tool(
            Path("/repo"), "rem-1",
            user_build_command="mvn test",
        )
        with patch('src.smartfix.domains.agents.build_tool.validate_command') as mock_validate:
            result = tool("gradle build")
            mock_validate.assert_called_once_with("BUILD_COMMAND", "gradle build")
            self.assertTrue(result["success"])

    def test_determined_command_fails_validation(self):
        """Determined command that fails allowlist should return error without running."""
        tool = create_build_tool(Path("/repo"), "rem-1")
        with patch('src.smartfix.domains.agents.build_tool.validate_command',
                   side_effect=CommandValidationError("blocked")):
            with patch('src.smartfix.domains.agents.build_tool.run_build_command') as mock_build:
                result = tool("rm -rf /")
                mock_build.assert_not_called()
                self.assertFalse(result["success"])
                self.assertIn("not allowed", result["output"])


class TestBuildToolFormatHandling(unittest.TestCase):
    """Test format command handling."""

    def setUp(self):
        reset_storage()

    def tearDown(self):
        reset_storage()

    @patch('src.smartfix.domains.agents.build_tool.run_build_command', return_value=(True, "ok"))
    @patch('src.smartfix.domains.agents.build_tool.run_formatting_command')
    def test_format_runs_before_build(self, mock_format, mock_build):
        """Format command should run before build command."""
        call_order = []
        mock_format.side_effect = lambda *a, **kw: call_order.append("format")
        mock_build.side_effect = lambda *a, **kw: (call_order.append("build"), (True, "ok"))[-1]

        tool = create_build_tool(Path("/repo"), "rem-1")
        tool("mvn test", "mvn spotless:apply")

        self.assertEqual(call_order, ["format", "build"])

    @patch('src.smartfix.domains.agents.build_tool.run_build_command', return_value=(True, "ok"))
    @patch('src.smartfix.domains.agents.build_tool.run_formatting_command',
           side_effect=Exception("format failed"))
    def test_format_failure_continues_to_build(self, mock_format, mock_build):
        """Format failure should log warning and continue to build."""
        tool = create_build_tool(Path("/repo"), "rem-1")
        result = tool("mvn test", "mvn spotless:apply")
        self.assertTrue(result["success"])
        mock_build.assert_called_once()

    @patch('src.smartfix.domains.agents.build_tool.run_build_command', return_value=(True, "ok"))
    @patch('src.smartfix.domains.agents.build_tool.run_formatting_command')
    def test_format_success_records_command(self, mock_format, mock_build):
        """Successful recordable format should be stored."""
        tool = create_build_tool(Path("/repo"), "rem-1")
        tool("mvn test", "mvn spotless:apply")
        self.assertEqual(get_successful_format_command(), "mvn spotless:apply")

    @patch('src.smartfix.domains.agents.build_tool.run_build_command', return_value=(True, "ok"))
    @patch('src.smartfix.domains.agents.build_tool.run_formatting_command')
    def test_configured_format_skips_validation(self, mock_format, mock_build):
        """User-configured format command should skip allowlist validation."""
        tool = create_build_tool(
            Path("/repo"), "rem-1",
            user_format_command="mvn spotless:apply",
        )
        with patch('src.smartfix.domains.agents.build_tool.validate_command') as mock_validate:
            tool("mvn test", "mvn spotless:apply")
            # validate_command should only be called for the build command (determined),
            # NOT for the format command (configured)
            for call in mock_validate.call_args_list:
                self.assertNotEqual(call[0][0], "FORMAT_COMMAND")

    def test_determined_format_fails_validation(self):
        """Determined format command that fails allowlist should return error."""
        tool = create_build_tool(Path("/repo"), "rem-1")
        with patch('src.smartfix.domains.agents.build_tool.validate_command',
                   side_effect=CommandValidationError("blocked")):
            result = tool("mvn test", "bad-format-cmd")
            self.assertFalse(result["success"])
            self.assertIn("not allowed", result["output"])


class TestBuildToolExecution(unittest.TestCase):
    """Test build execution and recording."""

    def setUp(self):
        reset_storage()

    def tearDown(self):
        reset_storage()

    @patch('src.smartfix.domains.agents.build_tool.run_build_command', return_value=(True, "BUILD SUCCESS"))
    def test_successful_build_records_command(self, mock_build):
        tool = create_build_tool(Path("/repo"), "rem-1")
        result = tool("mvn test")
        self.assertTrue(result["success"])
        self.assertTrue(result["recorded"])
        self.assertEqual(get_successful_build_command(), "mvn test")

    @patch('src.smartfix.domains.agents.build_tool.run_build_command', return_value=(True, "ok"))
    def test_non_recordable_success_not_recorded(self, mock_build):
        tool = create_build_tool(Path("/repo"), "rem-1")
        result = tool("mvn --version")
        self.assertTrue(result["success"])
        self.assertFalse(result["recorded"])
        self.assertIsNone(get_successful_build_command())

    @patch('src.smartfix.domains.agents.build_tool.run_build_command', return_value=(False, "COMPILATION ERROR\nfoo.java:10: error: cannot find symbol"))
    @patch('src.smartfix.domains.agents.build_tool.extract_build_errors', return_value="error: cannot find symbol")
    def test_failed_build_returns_errors(self, mock_extract, mock_build):
        tool = create_build_tool(Path("/repo"), "rem-1")
        result = tool("mvn test")
        self.assertFalse(result["success"])
        self.assertFalse(result["recorded"])
        self.assertIn("cannot find symbol", result["output"])
        self.assertIsNone(get_successful_build_command())

    @patch('src.smartfix.domains.agents.build_tool.run_build_command',
           side_effect=Exception("subprocess exploded"))
    def test_build_exception_returns_error(self, mock_build):
        tool = create_build_tool(Path("/repo"), "rem-1")
        result = tool("mvn test")
        self.assertFalse(result["success"])
        self.assertIn("exception", result["output"].lower())

    @patch('src.smartfix.domains.agents.build_tool.run_build_command', return_value=(True, "ok"))
    def test_no_format_command_skips_format(self, mock_build):
        """When no format command provided, only build runs."""
        tool = create_build_tool(Path("/repo"), "rem-1")
        with patch('src.smartfix.domains.agents.build_tool.run_formatting_command') as mock_format:
            result = tool("mvn test")
            mock_format.assert_not_called()
            self.assertTrue(result["success"])

    @patch('src.smartfix.domains.agents.build_tool.run_build_command', return_value=(True, "ok"))
    def test_none_format_command_skips_format(self, mock_build):
        tool = create_build_tool(Path("/repo"), "rem-1")
        with patch('src.smartfix.domains.agents.build_tool.run_formatting_command') as mock_format:
            tool("mvn test", None)
            mock_format.assert_not_called()


class TestBuildToolWhitespace(unittest.TestCase):
    """Test command normalization."""

    def setUp(self):
        reset_storage()

    def tearDown(self):
        reset_storage()

    @patch('src.smartfix.domains.agents.build_tool.run_build_command', return_value=(True, "ok"))
    def test_whitespace_stripped_for_comparison(self, mock_build):
        """Commands with extra whitespace should still match user config."""
        tool = create_build_tool(
            Path("/repo"), "rem-1",
            user_build_command="mvn test",
        )
        with patch('src.smartfix.domains.agents.build_tool.validate_command') as mock_validate:
            tool("  mvn test  ")
            mock_validate.assert_not_called()  # Should be configured mode


if __name__ == '__main__':
    unittest.main()
