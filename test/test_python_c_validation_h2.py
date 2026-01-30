"""Test H2 finding: Verify python -c flag is blocked"""
import unittest
from src.smartfix.config.command_validator import (
    validate_command,
    CommandValidationError,
)


class TestPythonCValidation(unittest.TestCase):
    """Test that python -c and other dangerous interpreter flags are blocked."""

    def test_python_c_flag_blocked(self):
        """Test that python -c is blocked."""
        with self.assertRaises(CommandValidationError) as cm:
            validate_command("BUILD_COMMAND", 'python -c "print(1)"')

        self.assertIn("dangerous interpreter flag", str(cm.exception).lower())

    def test_python3_c_flag_blocked(self):
        """Test that python3 -c is blocked."""
        with self.assertRaises(CommandValidationError) as cm:
            validate_command("BUILD_COMMAND", 'python3 -c "print(1)"')

        error_msg = str(cm.exception).lower()
        # Should be blocked for dangerous interpreter flag
        self.assertIn("dangerous interpreter flag", error_msg)

    def test_node_e_flag_blocked(self):
        """Test that node -e is blocked."""
        with self.assertRaises(CommandValidationError) as cm:
            validate_command("BUILD_COMMAND", 'node -e "console.log(1)"')

        self.assertIn("dangerous interpreter flag", str(cm.exception).lower())

    def test_node_eval_flag_blocked(self):
        """Test that node --eval is blocked."""
        with self.assertRaises(CommandValidationError):
            validate_command("BUILD_COMMAND", 'node --eval "console.log(1)"')
        # Blocked (may be for eval pattern or interpreter flag)

    def test_ruby_e_flag_blocked(self):
        """Test that ruby -e is blocked."""
        with self.assertRaises(CommandValidationError):
            validate_command("BUILD_COMMAND", 'ruby -e "puts 1"')
        # Blocked (may be for disallowed command or interpreter flag)

    def test_perl_e_flag_blocked(self):
        """Test that perl -e is blocked."""
        with self.assertRaises(CommandValidationError):
            validate_command("BUILD_COMMAND", 'perl -e "print 1"')
        # Blocked (may be for disallowed command or interpreter flag)

    def test_python_m_allowed(self):
        """Test that python -m with allowed modules works."""
        # Should not raise
        validate_command("BUILD_COMMAND", "python -m pytest")
        validate_command("BUILD_COMMAND", "python3 -m unittest")
        validate_command("BUILD_COMMAND", "python -m coverage run")


if __name__ == '__main__':
    unittest.main()
