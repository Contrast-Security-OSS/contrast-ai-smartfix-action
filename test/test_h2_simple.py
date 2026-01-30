"""Simple test to verify H2 finding about python -c validation"""
import unittest
from src.smartfix.config.command_validator import (
    validate_command,
    CommandValidationError,
)


class TestH2PythonCSimple(unittest.TestCase):
    """Test python -c with benign code (no other dangerous patterns)."""

    def test_python_c_simple_blocked(self):
        """python -c with benign code should be blocked."""
        with self.assertRaises(CommandValidationError) as cm:
            validate_command("BUILD_COMMAND", 'python -c "print(1)"')

        error_msg = str(cm.exception).lower()
        print(f"\nError for 'python -c': {error_msg[:200]}")
        self.assertIn("dangerous interpreter flag", error_msg)

    def test_python3_c_simple_blocked(self):
        """python3 -c with benign code should be blocked."""
        with self.assertRaises(CommandValidationError) as cm:
            validate_command("BUILD_COMMAND", 'python3 -c "print(1)"')

        error_msg = str(cm.exception).lower()
        print(f"\nError for 'python3 -c': {error_msg[:200]}")
        # This is the KEY test - does it block python3 -c specifically?
        self.assertIn("dangerous interpreter flag", error_msg)

    def test_python3_c_with_imports_blocked(self):
        """python3 -c with imports but no dangerous patterns should be blocked."""
        with self.assertRaises(CommandValidationError) as cm:
            validate_command("BUILD_COMMAND", 'python3 -c "import sys; print(sys.version)"')

        error_msg = str(cm.exception).lower()
        print(f"\nError for 'python3 -c with imports': {error_msg[:200]}")
        self.assertIn("dangerous interpreter flag", error_msg)


if __name__ == '__main__':
    unittest.main(verbosity=2)
