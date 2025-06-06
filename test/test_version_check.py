import unittest
import os
import sys
import io
from unittest.mock import patch, MagicMock
from packaging.version import Version

# Add src directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# Mock the config and utils modules before importing version_check
mock_config = MagicMock()
mock_config.DEBUG_MODE = True
sys.modules['config'] = mock_config
# Mock utils.debug_print to capture output for testing
mock_utils = MagicMock()
mock_debug_print = MagicMock()
mock_utils.debug_print = mock_debug_print
sys.modules['utils'] = mock_utils

from src.version_check import get_latest_repo_version, check_for_newer_version, do_version_check, normalize_version, safe_parse_version

class TestVersionCheck(unittest.TestCase):
    """Test the version checking functionality."""

    def setUp(self):
        # Common setup for all tests
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

        # Mock the environment
        self.env_patcher = patch.dict('os.environ', clear=True)
        self.env_patcher.start()
        
        # Reset debug_print mock before each test
        mock_debug_print.reset_mock()
    
    def tearDown(self):
        # Clean up after each test
        self.requests_patcher.stop()
        self.env_patcher.stop()

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

    def test_do_version_check_no_refs(self):
        """Test do_version_check when no reference environment variables are set."""
        # No environment variables set
        do_version_check()
        # Check that the appropriate debug_print message was called
        mock_debug_print.assert_any_call("Warning: Neither GITHUB_ACTION_REF nor GITHUB_REF environment variables are set. Version checking is skipped.")

    def test_do_version_check_with_sha_only(self):
        """Test do_version_check when only GITHUB_SHA is available."""
        os.environ["GITHUB_SHA"] = "abcdef1234567890abcdef1234567890abcdef12"
        do_version_check()
        # Check that the appropriate debug_print message was called
        mock_debug_print.assert_any_call("Running from SHA: abcdef1234567890abcdef1234567890abcdef12. No ref found for version check, using SHA.")

    @patch('sys.stdout', new_callable=io.StringIO)
    @patch('src.version_check.get_latest_repo_version')
    def test_do_version_check_with_github_ref(self, mock_get_latest, mock_stdout):
        """Test when GITHUB_REF is set but not GITHUB_ACTION_REF."""
        # Setup environment and mocks
        os.environ["GITHUB_REF"] = "refs/tags/v1.0.0"
        mock_get_latest.return_value = "v2.0.0"
        
        do_version_check()
        
        # Check debug print calls for messages that use debug_print
        mock_debug_print.assert_any_call("Current action version: v1.0.0")
        mock_debug_print.assert_any_call("Latest version available in repo: v2.0.0")
        
        # Check stdout for regular print calls (newer version messages)
        output = mock_stdout.getvalue()
        self.assertIn("INFO: A newer version of this action is available", output)

    @patch('src.version_check.get_latest_repo_version')
    def test_do_version_check_prefers_action_ref(self, mock_get_latest):
        """Test that GITHUB_ACTION_REF is preferred over GITHUB_REF."""
        # Setup environment with both variables
        os.environ["GITHUB_ACTION_REF"] = "refs/tags/v2.0.0"
        os.environ["GITHUB_REF"] = "refs/tags/v1.0.0"  # This should be ignored
        mock_get_latest.return_value = "v2.0.0"
        
        do_version_check()
        
        # Check that the debug_print was called with the correct version from GITHUB_ACTION_REF
        mock_debug_print.assert_any_call("Current action version: v2.0.0")

    @patch('src.version_check.get_latest_repo_version')
    def test_do_version_check_sha_ref(self, mock_get_latest):
        """Test with a SHA reference instead of a version tag."""
        os.environ["GITHUB_ACTION_REF"] = "abcdef1234567890abcdef1234567890abcdef12"
        
        do_version_check()
        
        # Check debug_print calls
        mock_debug_print.assert_any_call("Running action from SHA: abcdef1234567890abcdef1234567890abcdef12. Skipping version comparison against tags.")
        mock_get_latest.assert_not_called()

    @patch('src.version_check.get_latest_repo_version')
    def test_do_version_check_unparseable_version(self, mock_get_latest):
        """Test with a reference that can't be parsed as a version."""
        os.environ["GITHUB_REF"] = "refs/heads/main"
        
        do_version_check()
        
        # Check debug_print calls
        mock_debug_print.assert_any_call("Running from branch 'main'. Version checking is only meaningful when using release tags.")
        mock_get_latest.assert_not_called()

if __name__ == '__main__':
    unittest.main()
