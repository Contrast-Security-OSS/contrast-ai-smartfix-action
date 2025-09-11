import unittest
import os
import sys
from unittest.mock import patch, MagicMock
from packaging.version import Version

# Add project root to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import test setup helper
sys.path.insert(0, os.path.dirname(__file__))
from setup_test_env import TestEnvironmentMixin

# Import modules
from src.config import reset_config, get_config  # noqa: E402
from src.version_check import get_latest_repo_version, check_for_newer_version, do_version_check, normalize_version, safe_parse_version  # noqa: E402

# Initialize config with testing=True for tests
_ = get_config(testing=True)


class TestVersionCheck(unittest.TestCase, TestEnvironmentMixin):
    """Test the version checking functionality."""

    def setUp(self):
        # Common setup for all tests using mixin
        self.setup_standard_test_env()
        reset_config()  # Reset config before each test

        self.requests_patcher = patch('src.version_check.requests')
        self.mock_requests = self.requests_patcher.start()

        # Set up mock exceptions
        self.mock_requests.exceptions = MagicMock()
        self.mock_requests.exceptions.RequestException = Exception

        # Set up a default mock response
        self.mock_response = MagicMock()
        self.mock_response.json.return_value = [
            {'name': 'v1.0.0'},
            {'name': 'v1.1.0'},
            {'name': '2.0.0'}
        ]
        self.mock_response.raise_for_status.return_value = None
        self.mock_requests.get.return_value = self.mock_response

        # Reset debug_log and log mocks before each test
        self.log_patcher = patch('src.version_check.log')
        self.mock_log = self.log_patcher.start()

        self.debug_log_patcher = patch('src.version_check.debug_log')
        self.mock_debug_log = self.debug_log_patcher.start()

    def tearDown(self):
        # Clean up all patches
        self.cleanup_standard_test_env()
        self.requests_patcher.stop()
        self.log_patcher.stop()
        self.debug_log_patcher.stop()
        reset_config()  # Reset config after each test

    def test_normalize_version(self):
        """Test the normalize_version function."""
        self.assertEqual(normalize_version("v1.0.0"), "1.0.0")
        self.assertEqual(normalize_version("1.0.0"), "1.0.0")
        self.assertEqual(normalize_version(""), "")
        self.assertEqual(normalize_version(None), None)

    def test_safe_parse_version(self):
        """Test the safe_parse_version function."""
        self.assertIsInstance(safe_parse_version("1.0.0"), Version)
        self.assertIsInstance(safe_parse_version("v1.0.0"), Version)
        self.assertIsNone(safe_parse_version("invalid"))
        self.assertIsNone(safe_parse_version(""))
        self.assertIsNone(safe_parse_version(None))

    def test_get_latest_repo_version_success(self):
        """Test getting the latest version from a repo with valid tags."""
        result = get_latest_repo_version("https://github.com/user/repo")
        self.assertEqual(result, "2.0.0")
        self.mock_requests.get.assert_called_once_with("https://api.github.com/repos/user/repo/tags")

    def test_get_latest_repo_version_with_v_prefix(self):
        """Test that versions with 'v' prefix are handled correctly."""
        # Change mock response to only have v-prefixed tags
        self.mock_response.json.return_value = [
            {'name': 'v1.0.0'},
            {'name': 'v2.0.0'},
            {'name': 'v1.5.2'}
        ]
        result = get_latest_repo_version("https://github.com/user/repo")
        self.assertEqual(result, "v2.0.0")

    def test_get_latest_repo_version_no_tags(self):
        """Test behavior when no tags are found."""
        self.mock_response.json.return_value = []
        result = get_latest_repo_version("https://github.com/user/repo")
        self.assertIsNone(result)

    def test_get_latest_repo_version_request_error(self):
        """Test handling of request exceptions."""
        # Create a proper RequestException instance
        request_exception = self.mock_requests.exceptions.RequestException("Connection error")
        self.mock_requests.get.side_effect = request_exception
        result = get_latest_repo_version("https://github.com/user/repo")
        self.assertIsNone(result)

    def test_check_for_newer_version_newer_available(self):
        """Test when a newer version is available."""
        result = check_for_newer_version("v1.0.0", "v1.1.0")
        self.assertEqual(result, "v1.1.0")

    def test_check_for_newer_version_same_version(self):
        """Test when versions are the same."""
        result = check_for_newer_version("v1.0.0", "v1.0.0")
        self.assertIsNone(result)

    def test_check_for_newer_version_older_version(self):
        """Test when the latest version is older."""
        result = check_for_newer_version("v2.0.0", "v1.9.0")
        self.assertIsNone(result)

    def test_check_for_newer_version_mixed_formats(self):
        """Test version comparison with mixed format (with/without v prefix)."""
        result = check_for_newer_version("1.0.0", "v1.1.0")
        self.assertEqual(result, "v1.1.0")

    def test_check_for_newer_version_with_version_object(self):
        """Test check_for_newer_version with a Version object as first parameter."""
        from packaging.version import parse
        version_obj = parse("1.0.0")
        result = check_for_newer_version(version_obj, "v1.1.0")
        self.assertEqual(result, "v1.1.0")

    @patch.dict('os.environ', {}, clear=True)
    def test_do_version_check_no_refs(self):
        """Test do_version_check when no reference environment variables are set."""
        # Using patch.dict to ensure environment variables are cleared
        do_version_check()
        # Check that the appropriate debug_log message was called
        self.mock_debug_log.assert_any_call("Warning: Neither GITHUB_ACTION_REF nor GITHUB_REF environment variables are set. Version checking is skipped.")

    @patch.dict('os.environ', {'GITHUB_SHA': 'abcdef1234567890abcdef1234567890abcdef12'}, clear=True)
    def test_do_version_check_with_sha_only(self):
        """Test do_version_check when only GITHUB_SHA is available."""
        # Using patch.dict to mock only GITHUB_SHA
        do_version_check()
        # Check that the appropriate debug_log message was called
        self.mock_debug_log.assert_any_call("Running from SHA: abcdef1234567890abcdef1234567890abcdef12. No ref found for version check, using SHA.")

    @patch('src.version_check.get_latest_repo_version')
    def test_do_version_check_with_github_ref(self, mock_get_latest):
        """Test when GITHUB_REF is set but not GITHUB_ACTION_REF."""
        # Setup environment and mocks
        os.environ["GITHUB_REF"] = "refs/tags/v1.0.0"
        mock_get_latest.return_value = "v2.0.0"

        # Reset mocks before test
        self.mock_log.reset_mock()

        do_version_check()

        # Check debug print calls for messages that use debug_log
        self.mock_debug_log.assert_any_call("Current action version: v1.0.0")
        self.mock_debug_log.assert_any_call("Latest version available in repo: v2.0.0")

        # Check that the log function was called with the newer version message
        self.mock_log.assert_any_call("INFO: A newer version of this action is available (v2.0.0).")

    @patch('src.version_check.get_latest_repo_version')
    def test_do_version_check_prefers_action_ref(self, mock_get_latest):
        """Test that GITHUB_ACTION_REF is preferred over GITHUB_REF."""
        # Setup environment with both variables
        os.environ["GITHUB_ACTION_REF"] = "refs/tags/v2.0.0"
        os.environ["GITHUB_REF"] = "refs/tags/v1.0.0"  # This should be ignored
        mock_get_latest.return_value = "v2.0.0"

        do_version_check()

        # Check that the debug_log was called with the correct version from GITHUB_ACTION_REF
        self.mock_debug_log.assert_any_call("Current action version: v2.0.0")

    @patch('src.version_check.get_latest_repo_version')
    def test_do_version_check_sha_ref(self, mock_get_latest):
        """Test with a SHA reference instead of a version tag."""
        os.environ["GITHUB_ACTION_REF"] = "abcdef1234567890abcdef1234567890abcdef12"

        do_version_check()

        # Check debug_log calls
        self.mock_debug_log.assert_any_call("Running action from SHA: abcdef1234567890abcdef1234567890abcdef12. Skipping version comparison against tags.")
        mock_get_latest.assert_not_called()

    @patch('src.version_check.get_latest_repo_version')
    def test_do_version_check_unparseable_version(self, mock_get_latest):
        """Test with a reference that can't be parsed as a version."""
        os.environ["GITHUB_REF"] = "refs/heads/main"

        do_version_check()

        # Check debug_log calls
        self.mock_debug_log.assert_any_call("Running from branch 'main'. Version checking is only meaningful when using release tags.")
        mock_get_latest.assert_not_called()


if __name__ == '__main__':
    unittest.main()
