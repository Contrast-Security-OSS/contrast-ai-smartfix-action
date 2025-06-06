import unittest
import os
import sys
import io
from unittest.mock import patch, MagicMock

# Add src directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.version_check import get_latest_repo_version, check_for_newer_version, do_version_check

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
    
    def tearDown(self):
        # Clean up after each test
        self.requests_patcher.stop()
        self.env_patcher.stop()

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

    @patch('sys.stdout', new_callable=io.StringIO)
    def test_do_version_check_no_ref(self, mock_stdout):
        """Test do_version_check when GITHUB_ACTION_REF is not set."""
        do_version_check()
        output = mock_stdout.getvalue()
        self.assertIn("Warning: GITHUB_ACTION_REF environment variable is not set", output)

    @patch('sys.stdout', new_callable=io.StringIO)
    @patch('src.version_check.get_latest_repo_version')
    def test_do_version_check_newer_available(self, mock_get_latest, mock_stdout):
        """Test when a newer version is available."""
        # Setup environment and mocks
        os.environ["GITHUB_ACTION_REF"] = "refs/tags/v1.0.0"
        mock_get_latest.return_value = "v2.0.0"
        
        do_version_check()
        
        output = mock_stdout.getvalue()
        self.assertIn("Current action version", output)
        self.assertIn("Latest version available in repo: v2.0.0", output)
        self.assertIn("INFO: A newer version of this action is available", output)

    @patch('sys.stdout', new_callable=io.StringIO)
    @patch('src.version_check.get_latest_repo_version')
    def test_do_version_check_sha_ref(self, mock_get_latest, mock_stdout):
        """Test with a SHA reference instead of a version tag."""
        os.environ["GITHUB_ACTION_REF"] = "abcdef1234567890abcdef1234567890abcdef12"
        
        do_version_check()
        
        output = mock_stdout.getvalue()
        self.assertIn("Running action from SHA", output)
        mock_get_latest.assert_not_called()

if __name__ == '__main__':
    unittest.main()
