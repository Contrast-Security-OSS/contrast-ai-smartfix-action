"""Test edge cases for python -c validation in various contexts"""
import unittest
from src.smartfix.config.command_validator import (
    validate_command,
    CommandValidationError,
)


class TestPythonCEdgeCases(unittest.TestCase):
    """Test edge cases for python -c validation in chains, pipes, and redirects."""

    def test_python_c_in_chain(self):
        """python -c should be blocked even in command chain."""
        with self.assertRaises(CommandValidationError) as cm:
            validate_command("BUILD_COMMAND", 'npm install && python -c "print(1)"')
        self.assertIn("dangerous interpreter flag", str(cm.exception).lower())

    def test_python3_c_after_pipe(self):
        """python3 -c should be blocked after pipe."""
        with self.assertRaises(CommandValidationError) as cm:
            validate_command("BUILD_COMMAND", 'echo test | python3 -c "import sys; print(sys.stdin.read())"')
        self.assertIn("dangerous interpreter flag", str(cm.exception).lower())

    def test_python_c_with_redirect(self):
        """python -c with redirect should be blocked."""
        with self.assertRaises(CommandValidationError) as cm:
            validate_command("BUILD_COMMAND", 'python -c "print(1)" > output.txt')
        self.assertIn("dangerous interpreter flag", str(cm.exception).lower())

    def test_python_without_c_allowed(self):
        """python without -c should be allowed (running script files)."""
        # Should not raise
        validate_command("BUILD_COMMAND", "python script.py")
        validate_command("BUILD_COMMAND", "python3 test_runner.py")

    def test_python_m_not_confused_with_c(self):
        """python -m should not be confused with -c."""
        # Should not raise
        validate_command("BUILD_COMMAND", "python -m pytest")
        validate_command("BUILD_COMMAND", "python3 -m unittest")


if __name__ == '__main__':
    unittest.main(verbosity=2)
