import os
import sys
import unittest
import io
import contextlib
from unittest.mock import patch, MagicMock, Mock

# Add src directory to Python path for proper imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the actual requests module for proper exception types
import requests

# Define a custom MockHTTPError for testing
class MockHTTPError(Exception):
    """Mock HTTP Error for testing exception handling."""
    def __init__(self, *args, **kwargs):
        self.response = Mock()
        self.response.status_code = 404
        self.response.text = "Not Found"
        super().__init__(*args, **kwargs)

# Import the functions to test after mocking
from src.version_check import get_latest_repo_version, check_for_newer_version, do_version_check, ACTION_REPO_URL

class TestVersionCheckFunctions(unittest.TestCase):

    def setUp(self):
        # Mock environment variables
        self.env_patcher = patch.dict('os.environ', {}, clear=True)
        self.env_patcher.start()
        
        # Mock sys.exit to prevent test termination
        self.exit_patcher = patch('sys.exit')
        self.mock_exit = self.exit_patcher.start()
        
    def tearDown(self):
        # Clean up patches
        self.env_patcher.stop()
        self.exit_patcher.stop()

    @patch('src.version_check.requests.get')
    def test_get_latest_repo_version_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = [{'name': 'v1.0.0'}, {'name': 'v1.1.0'}, {'name': '0.9.0'}]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        self.assertEqual(get_latest_repo_version("https://github.com/user/repo"), "v1.1.0")

    @patch('src.version_check.requests.get')
    def test_get_latest_repo_version_handles_non_v_prefix(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = [{'name': '1.0.0'}, {'name': '1.1.0'}, {'name': '0.9.0'}]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        self.assertEqual(get_latest_repo_version("https://github.com/user/repo"), "1.1.0")

    @patch('src.version_check.requests.get')
    def test_get_latest_repo_version_mixed_tags(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {'name': 'v1.0.0'}, {'name': '1.1.0'}, {'name': 'v0.9.0'},
            {'name': 'latest'}, {'name': 'v2.0.0-alpha'}, {'name': '2.0.1'}
        ]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        self.assertEqual(get_latest_repo_version("https://github.com/user/repo"), "2.0.1")

    @patch('src.version_check.requests.get')
    def test_get_latest_repo_version_only_invalid_tags(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = [{'name': 'latest'}, {'name': 'beta-feature'}]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        self.assertIsNone(get_latest_repo_version("https://github.com/user/repo"))

    @patch('src.version_check.requests.get')
    def test_get_latest_repo_version_no_tags(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        self.assertIsNone(get_latest_repo_version("https://github.com/user/repo"))

    @patch('src.version_check.requests.get')
    def test_get_latest_repo_version_http_error(self, mock_get):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = MockHTTPError("Test HTTP Error")
        mock_get.return_value = mock_response
        self.assertIsNone(get_latest_repo_version("https://github.com/user/repo"))

    @patch('src.version_check.requests.get')
    def test_get_latest_repo_version_unexpected_error(self, mock_get):
        mock_get.side_effect = Exception("Unexpected error")
        self.assertIsNone(get_latest_repo_version("https://github.com/user/repo"))
        
    def test_check_for_newer_version_newer_is_found(self):
        # Test with different version formats
        test_cases = [
            ("v1.0.0", "v1.1.0", "v1.1.0"),
            ("1.0.0", "v1.1.0", "v1.1.0"),
            ("v1.0.0", "1.1.0", "1.1.0"),
            ("1.0.0", "1.1.0", "1.1.0")
        ]
        for current, latest, expected in test_cases:
            with self.subTest(current=current, latest=latest):
                self.assertEqual(check_for_newer_version(current, latest), expected)

    def test_check_for_newer_version_no_newer_found(self):
        # Test with different version formats
        test_cases = [
            ("v1.1.0", "v1.0.0", None),
            ("1.1.0", "v1.0.0", None),
            ("v1.1.0", "1.0.0", None),
            ("1.1.0", "1.0.0", None)
        ]
        for current, latest, expected in test_cases:
            with self.subTest(current=current, latest=latest):
                self.assertEqual(check_for_newer_version(current, latest), expected)

    def test_check_for_newer_version_same_version(self):
        # Test with different version formats
        test_cases = [
            ("v1.0.0", "v1.0.0", None),
            ("1.0.0", "v1.0.0", None),
            ("v1.0.0", "1.0.0", None),
            ("1.0.0", "1.0.0", None)
        ]
        for current, latest, expected in test_cases:
            with self.subTest(current=current, latest=latest):
                self.assertEqual(check_for_newer_version(current, latest), expected)

    def test_check_for_newer_version_invalid_versions(self):
        # Test with invalid versions
        test_cases = [
            ("invalid-version", "v1.0.0", None),
            ("v1.0.0", "invalid-version", None),
            ("invalid-1", "invalid-2", None)
        ]
        for current, latest, expected in test_cases:
            with self.subTest(current=current, latest=latest):
                self.assertEqual(check_for_newer_version(current, latest), expected)

    @patch('sys.stdout', new_callable=io.StringIO)
    @patch('src.version_check.check_for_newer_version')
    @patch('src.version_check.get_latest_repo_version')
    def test_do_version_check_newer_available(self, mock_get_latest, mock_check_newer, mock_stdout):
        # Setup mocks
        mock_get_latest.return_value = "v1.1.0"
        mock_check_newer.return_value = "v1.1.0"
        
        # Set environment variables
        with patch.dict(os.environ, {'GITHUB_ACTION_REF': 'refs/tags/v1.0.0'}):
            do_version_check()
            
        output = mock_stdout.getvalue()
        self.assertIn("Current action version", output)
        self.assertIn("Latest version available in repo: v1.1.0", output)
        self.assertIn("A newer version of this action is available", output)
        
    @patch('sys.stdout', new_callable=io.StringIO)
    @patch('src.version_check.check_for_newer_version')
    @patch('src.version_check.get_latest_repo_version')
    def test_do_version_check_already_latest(self, mock_get_latest, mock_check_newer, mock_stdout):
        # Setup mocks
        mock_get_latest.return_value = "v1.0.0"
        mock_check_newer.return_value = None
        
        # Set environment variables
        with patch.dict(os.environ, {'GITHUB_ACTION_REF': 'refs/tags/v1.0.0'}):
            do_version_check()
            
        output = mock_stdout.getvalue()
        self.assertIn("Current action version", output)
        self.assertIn("Latest version available in repo: v1.0.0", output)
        self.assertNotIn("A newer version of this action is available", output)
        
    @patch('sys.stdout', new_callable=io.StringIO)
    @patch('src.version_check.check_for_newer_version')
    @patch('src.version_check.get_latest_repo_version')
    def test_do_version_check_no_latest_found(self, mock_get_latest, mock_check_newer, mock_stdout):
        # Setup mocks
        mock_get_latest.return_value = None
        
        # Set environment variables
        with patch.dict(os.environ, {'GITHUB_ACTION_REF': 'refs/tags/v1.0.0'}):
            do_version_check()
            
        output = mock_stdout.getvalue()
        self.assertIn("Current action version", output)
        self.assertIn("Could not determine the latest version from the repository", output)
        mock_check_newer.assert_not_called()
        
    @patch('sys.stdout', new_callable=io.StringIO)
    @patch('src.version_check.check_for_newer_version')
    @patch('src.version_check.get_latest_repo_version')
    def test_do_version_check_no_action_ref(self, mock_get_latest, mock_check_newer, mock_stdout):
        # No environment variables set (empty dict with clear=True)
        do_version_check()
            
        output = mock_stdout.getvalue()
        self.assertIn("Warning: GITHUB_ACTION_REF environment variable is not set", output)
        mock_get_latest.assert_not_called()
        mock_check_newer.assert_not_called()
        
    @patch('sys.stdout', new_callable=io.StringIO)
    @patch('src.version_check.check_for_newer_version')
    @patch('src.version_check.get_latest_repo_version')
    def test_do_version_check_sha_ref(self, mock_get_latest, mock_check_newer, mock_stdout):
        # Set environment variables with SHA
        with patch.dict(os.environ, {'GITHUB_ACTION_REF': 'abcdef1234567890abcdef1234567890abcdef12'}):
            do_version_check()
            
        output = mock_stdout.getvalue()
        self.assertIn("Running action from SHA", output)
        mock_get_latest.assert_not_called()
        mock_check_newer.assert_not_called()
        
    @patch('sys.stdout', new_callable=io.StringIO)
    @patch('src.version_check.check_for_newer_version')
    @patch('src.version_check.get_latest_repo_version')
    def test_do_version_check_unparsable_ref(self, mock_get_latest, mock_check_newer, mock_stdout):
        # Set environment variables with unparsable ref
        with patch.dict(os.environ, {'GITHUB_ACTION_REF': 'refs/heads/main'}):
            do_version_check()
            
        output = mock_stdout.getvalue()
        self.assertIn("Warning: Could not parse current action version", output)
        mock_get_latest.assert_not_called()
        mock_check_newer.assert_not_called()

if __name__ == '__main__':
    unittest.main()
