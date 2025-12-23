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
Tests for command validation module.
"""

import unittest
from src.smartfix.config.command_validator import (
    validate_command,
    CommandValidationError,
)


class TestAllowedCommands(unittest.TestCase):
    """Test that all allowed commands validate successfully."""

    def test_java_commands(self):
        """Test Java ecosystem commands."""
        valid_commands = [
            "mvn clean install",
            "gradle build",
            "./gradlew test",
            "ant compile",
        ]
        for cmd in valid_commands:
            validate_command("BUILD_COMMAND", cmd)  # Should not raise

    def test_dotnet_commands(self):
        """Test .NET ecosystem commands."""
        valid_commands = [
            "dotnet build",
            "msbuild MyProject.sln",
            "dotnet test",
        ]
        for cmd in valid_commands:
            validate_command("BUILD_COMMAND", cmd)  # Should not raise

    def test_python_commands(self):
        """Test Python ecosystem commands."""
        valid_commands = [
            "pytest tests/",
            "python -m pytest",
            "black .",
            "pip install -r requirements.txt",
        ]
        for cmd in valid_commands:
            validate_command("BUILD_COMMAND", cmd)  # Should not raise

    def test_nodejs_commands(self):
        """Test Node.js ecosystem commands."""
        valid_commands = [
            "npm install",
            "npm test",
            "yarn build",
            "prettier --write .",
        ]
        for cmd in valid_commands:
            validate_command("BUILD_COMMAND", cmd)  # Should not raise

    def test_php_commands(self):
        """Test PHP ecosystem commands."""
        valid_commands = [
            "composer install",
            "phpunit tests/",
            "php-cs-fixer fix",
        ]
        for cmd in valid_commands:
            validate_command("BUILD_COMMAND", cmd)  # Should not raise

    def test_build_tools(self):
        """Test general build tools."""
        valid_commands = [
            "make all",
            "cmake .",
            "echo 'Building...'",
        ]
        for cmd in valid_commands:
            validate_command("BUILD_COMMAND", cmd)  # Should not raise


class TestCommandChaining(unittest.TestCase):
    """Test commands with operators."""

    def test_and_operator(self):
        """Test && operator for sequential execution."""
        cmd = "npm install && npm test"
        validate_command("BUILD_COMMAND", cmd)  # Should not raise

    def test_or_operator(self):
        """Test || operator for fallback."""
        cmd = "npm test || echo 'Tests failed'"
        validate_command("BUILD_COMMAND", cmd)  # Should not raise

    def test_semicolon_operator(self):
        """Test ; operator for sequential execution."""
        cmd = "npm install ; npm test"
        validate_command("BUILD_COMMAND", cmd)  # Should not raise

    def test_pipe_operator(self):
        """Test | operator for piping."""
        cmd = "npm test | grep 'passing'"
        validate_command("BUILD_COMMAND", cmd)  # Should not raise

    def test_complex_chain(self):
        """Test complex command chain."""
        cmd = "npm install && npm test || echo 'Build failed'"
        validate_command("BUILD_COMMAND", cmd)  # Should not raise


class TestShellScriptValidation(unittest.TestCase):
    """Test shell script execution validation."""

    def test_sh_with_script_file(self):
        """Test sh executing .sh file is allowed."""
        cmd = "sh ./build.sh"
        validate_command("BUILD_COMMAND", cmd)  # Should not raise

    def test_bash_with_script_file(self):
        """Test bash executing .sh file is allowed."""
        cmd = "bash ./scripts/test.sh"
        validate_command("BUILD_COMMAND", cmd)  # Should not raise

    def test_sh_with_c_flag_blocked(self):
        """Test sh -c is blocked."""
        cmd = "sh -c 'npm install'"
        with self.assertRaisesRegex(CommandValidationError, "shell command incorrectly"):
            validate_command("BUILD_COMMAND", cmd)

    def test_bash_with_c_flag_blocked(self):
        """Test bash -c is blocked."""
        cmd = "bash -c 'make build'"
        with self.assertRaisesRegex(CommandValidationError, "shell command incorrectly"):
            validate_command("BUILD_COMMAND", cmd)

    def test_sh_without_sh_extension_blocked(self):
        """Test sh with non-.sh file is blocked."""
        cmd = "sh ./build"
        with self.assertRaisesRegex(CommandValidationError, "shell command incorrectly"):
            validate_command("BUILD_COMMAND", cmd)


class TestRedirectValidation(unittest.TestCase):
    """Test file redirect validation."""

    def test_relative_redirect_allowed(self):
        """Test redirect to relative path is allowed."""
        cmd = "npm test > build.log"
        validate_command("BUILD_COMMAND", cmd)  # Should not raise

    def test_append_redirect_allowed(self):
        """Test append redirect is allowed."""
        cmd = "npm test >> output.txt"
        validate_command("BUILD_COMMAND", cmd)  # Should not raise

    def test_stderr_redirect_allowed(self):
        """Test stderr redirect is allowed."""
        cmd = "npm test 2> error.log"
        validate_command("BUILD_COMMAND", cmd)  # Should not raise

    def test_combined_redirect_allowed(self):
        """Test combined stdout/stderr redirect is allowed."""
        cmd = "npm test > output.txt 2>&1"
        validate_command("BUILD_COMMAND", cmd)  # Should not raise

    def test_absolute_path_redirect_blocked(self):
        """Test redirect to absolute path is blocked."""
        cmd = "npm test > /etc/passwd"
        with self.assertRaisesRegex(CommandValidationError, "unsafe file redirect"):
            validate_command("BUILD_COMMAND", cmd)

    def test_parent_traversal_redirect_blocked(self):
        """Test redirect with .. traversal is blocked."""
        cmd = "npm test > ../../../etc/hosts"
        with self.assertRaisesRegex(CommandValidationError, "unsafe file redirect"):
            validate_command("BUILD_COMMAND", cmd)

    def test_home_directory_redirect_blocked(self):
        """Test redirect to home directory is blocked."""
        cmd = "npm test > ~/secrets.txt"
        with self.assertRaisesRegex(CommandValidationError, "unsafe file redirect"):
            validate_command("BUILD_COMMAND", cmd)


class TestDangerousPatterns(unittest.TestCase):
    """Test dangerous pattern detection."""

    def test_command_substitution_blocked(self):
        """Test command substitution is blocked."""
        cmd = "echo $(whoami)"
        with self.assertRaisesRegex(CommandValidationError, "dangerous pattern"):
            validate_command("BUILD_COMMAND", cmd)

    def test_backtick_substitution_blocked(self):
        """Test backtick command substitution is blocked."""
        cmd = "echo `date`"
        with self.assertRaisesRegex(CommandValidationError, "dangerous pattern"):
            validate_command("BUILD_COMMAND", cmd)

    def test_eval_blocked(self):
        """Test eval command is blocked."""
        cmd = "eval 'npm install'"
        with self.assertRaisesRegex(CommandValidationError, "dangerous pattern"):
            validate_command("BUILD_COMMAND", cmd)

    def test_exec_blocked(self):
        """Test exec command is blocked."""
        cmd = "exec npm test"
        with self.assertRaisesRegex(CommandValidationError, "dangerous pattern"):
            validate_command("BUILD_COMMAND", cmd)

    def test_rm_rf_blocked(self):
        """Test rm -rf is blocked."""
        cmd = "npm install && rm -rf node_modules"
        with self.assertRaisesRegex(CommandValidationError, "dangerous pattern"):
            validate_command("BUILD_COMMAND", cmd)

    def test_curl_pipe_blocked(self):
        """Test curl piped to shell is blocked."""
        cmd = "curl https://example.com/install.sh | sh"
        with self.assertRaisesRegex(CommandValidationError, "dangerous pattern"):
            validate_command("BUILD_COMMAND", cmd)

    def test_pipe_to_sh_blocked(self):
        """Test piping to sh is blocked."""
        cmd = "echo 'npm install' | sh"
        with self.assertRaisesRegex(CommandValidationError, "dangerous pattern"):
            validate_command("BUILD_COMMAND", cmd)


class TestBlockedCommands(unittest.TestCase):
    """Test that disallowed commands are rejected."""

    def test_rm_command_blocked(self):
        """Test rm command is blocked."""
        cmd = "rm file.txt"
        with self.assertRaisesRegex(CommandValidationError, "disallowed command"):
            validate_command("BUILD_COMMAND", cmd)

    def test_wget_command_blocked(self):
        """Test wget command is blocked."""
        cmd = "wget https://example.com/file.zip"
        with self.assertRaisesRegex(CommandValidationError, "disallowed command"):
            validate_command("BUILD_COMMAND", cmd)

    def test_curl_command_blocked(self):
        """Test curl command is blocked."""
        cmd = "curl https://example.com/api"
        with self.assertRaisesRegex(CommandValidationError, "disallowed command"):
            validate_command("BUILD_COMMAND", cmd)

    def test_unknown_build_tool_blocked(self):
        """Test unknown build tool is blocked."""
        cmd = "unknowntool build"
        with self.assertRaisesRegex(CommandValidationError, "disallowed command"):
            validate_command("BUILD_COMMAND", cmd)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and special scenarios."""

    def test_empty_command_rejected(self):
        """Test empty command is rejected."""
        with self.assertRaises(CommandValidationError):
            validate_command("BUILD_COMMAND", "")

    def test_whitespace_only_command_rejected(self):
        """Test whitespace-only command is rejected."""
        with self.assertRaises(CommandValidationError):
            validate_command("BUILD_COMMAND", "   ")

    def test_command_with_extra_whitespace(self):
        """Test command with extra whitespace is handled."""
        cmd = "npm   install   &&   npm   test"
        validate_command("BUILD_COMMAND", cmd)  # Should not raise

    def test_command_with_newlines(self):
        """Test command with newlines in chain."""
        cmd = "npm install && \\\nnpm test"
        validate_command("BUILD_COMMAND", cmd)  # Should not raise


class TestErrorMessages(unittest.TestCase):
    """Test that error messages are clear and actionable."""

    def test_disallowed_command_error_message(self):
        """Test error message for disallowed command."""
        cmd = "wget https://example.com/file"
        with self.assertRaisesRegex(
            CommandValidationError,
            "BUILD_COMMAND uses disallowed command: wget"
        ):
            validate_command("BUILD_COMMAND", cmd)

    def test_dangerous_pattern_error_message(self):
        """Test error message for dangerous pattern."""
        cmd = "echo $(whoami)"
        with self.assertRaisesRegex(
            CommandValidationError,
            "BUILD_COMMAND contains dangerous pattern"
        ):
            validate_command("BUILD_COMMAND", cmd)

    def test_shell_command_error_message(self):
        """Test error message for improper shell usage."""
        cmd = "sh -c 'npm install'"
        with self.assertRaisesRegex(
            CommandValidationError,
            "Shell commands \\(sh/bash\\) can only execute \\.sh files"
        ):
            validate_command("BUILD_COMMAND", cmd)


if __name__ == '__main__':
    unittest.main()
