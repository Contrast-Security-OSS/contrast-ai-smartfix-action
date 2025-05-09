import unittest
from unittest.mock import patch, mock_open
import os
import requests # Import requests here
from packaging.version import parse as parse_version

# Add project root to sys.path to allow importing version_check
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

import version_check

class TestVersionCheck(unittest.TestCase):

    @patch('version_check.open', new_callable=mock_open, read_data="v1.0.0")
    def test_get_current_version_from_file(self, mock_file):
        self.assertEqual(version_check.get_current_version_from_file(), "v1.0.0")
        # Use os.path.join for cross-platform compatibility in assertion
        expected_path = os.path.join(os.path.dirname(version_check.__file__), "VERSION")
        mock_file.assert_called_once_with(expected_path, "r")

    @patch('version_check.open', side_effect=FileNotFoundError)
    def test_get_current_version_file_not_found(self, mock_file):
        with patch('builtins.print') as mock_print:
            self.assertEqual(version_check.get_current_version_from_file(), "0.0.0")
            expected_path = os.path.join(os.path.dirname(version_check.__file__), "VERSION")
            mock_print.assert_any_call(f"Warning: {expected_path} not found. Defaulting to 0.0.0")

    @patch.dict(os.environ, {"GITHUB_REPOSITORY": "owner/repo"}) # This GITHUB_REPOSITORY is for the mock, version_check.py uses hardcoded
    @patch('version_check.requests.get')
    @patch('version_check.get_current_version_from_file', return_value="v1.0.0")
    def test_new_version_available(self, mock_get_current_version, mock_requests_get):
        mock_response = unittest.mock.Mock()
        mock_response.json.return_value = [{'name': 'v1.1.0'}]
        mock_response.raise_for_status = unittest.mock.Mock()
        mock_requests_get.return_value = mock_response

        with patch('builtins.print') as mock_print:
            version_check.check_for_new_action_version()
            # Use the hardcoded repo name in the expected message
            mock_print.assert_any_call("INFO: A new version (v1.1.0) of the 'Contrast-Security-OSS/contrast-resolve-action-dev' action is available.")
            mock_print.assert_any_call("INFO: You are currently using version v1.0.0.")
            mock_print.assert_any_call("INFO: Please consider updating your workflow to use 'Contrast-Security-OSS/contrast-resolve-action-dev@v1.1.0'.")

    @patch.dict(os.environ, {"GITHUB_REPOSITORY": "owner/repo"}) # This GITHUB_REPOSITORY is for the mock
    @patch('version_check.requests.get')
    @patch('version_check.get_current_version_from_file', return_value="v1.1.0") # Current is latest
    def test_no_new_version(self, mock_get_current_version, mock_requests_get):
        mock_response = unittest.mock.Mock()
        mock_response.json.return_value = [{'name': 'v1.1.0'}] 
        mock_response.raise_for_status = unittest.mock.Mock()
        mock_requests_get.return_value = mock_response

        with patch('builtins.print') as mock_print:
            version_check.check_for_new_action_version()
            for call_args in mock_print.call_args_list:
                self.assertNotIn("INFO: A new version", call_args[0][0])

    @patch.dict(os.environ, {"GITHUB_REPOSITORY": "owner/repo"}) # This GITHUB_REPOSITORY is for the mock
    @patch('version_check.requests.get')
    @patch('version_check.get_current_version_from_file', return_value="v1.0.0")
    def test_no_tags_found(self, mock_get_current_version, mock_requests_get):
        mock_response = unittest.mock.Mock()
        mock_response.json.return_value = [] # No tags
        mock_response.raise_for_status = unittest.mock.Mock()
        mock_requests_get.return_value = mock_response

        with patch('builtins.print') as mock_print:
            version_check.check_for_new_action_version()
            for call_args in mock_print.call_args_list:
                self.assertNotIn("INFO: A new version", call_args[0][0])
    
    @patch.dict(os.environ, {}, clear=True) # GITHUB_REPOSITORY is not set, but should not affect the hardcoded repo in version_check.py
    @patch('version_check.requests.get')
    @patch('version_check.get_current_version_from_file', return_value="v1.0.0")
    def test_hardcoded_repo_used_when_env_missing(self, mock_get_current_version, mock_requests_get): # Renamed test
        # Mock the response for requests.get to simulate no tags found
        mock_response = unittest.mock.Mock()
        mock_response.json.return_value = [] 
        mock_response.raise_for_status = unittest.mock.Mock()
        mock_requests_get.return_value = mock_response

        with patch('builtins.print') as mock_print:
            version_check.check_for_new_action_version()
            
            # Assert that requests.get was called with the hardcoded repo URL
            expected_url = "https://api.github.com/repos/Contrast-Security-OSS/contrast-resolve-action-dev/tags"
            mock_requests_get.assert_called_once_with(
                expected_url,
                headers={"Accept": "application/vnd.github.v3+json", "X-GitHub-Api-Version": "2022-11-28"},
                timeout=10
            )
            # Check that no "new version" print messages were called (because we simulated no tags)
            for call_args in mock_print.call_args_list:
                self.assertNotIn("INFO: A new version", call_args[0][0])

    @patch.dict(os.environ, {"GITHUB_REPOSITORY": "owner/repo"}) # This GITHUB_REPOSITORY is for the mock
    @patch('version_check.requests.get', side_effect=requests.exceptions.Timeout)
    @patch('version_check.get_current_version_from_file', return_value="v1.0.0")
    def test_requests_timeout(self, mock_get_current_version, mock_requests_get):
        with patch('builtins.print') as mock_print:
            version_check.check_for_new_action_version()
            # Use the hardcoded repo name in the expected message
            mock_print.assert_any_call("Warning: Timeout while checking for new action version for 'Contrast-Security-OSS/contrast-resolve-action-dev'.")

    @patch.dict(os.environ, {"GITHUB_REPOSITORY": "owner/repo"}) # This GITHUB_REPOSITORY is for the mock
    @patch('version_check.requests.get')
    @patch('version_check.get_current_version_from_file', return_value="v1.0.0")
    def test_requests_http_error(self, mock_get_current_version, mock_requests_get):
        mock_http_error_response = unittest.mock.Mock()
        mock_http_error_response.status_code = 403
        mock_response = unittest.mock.Mock()
        # Configure the mock to simulate an HTTPError
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_http_error_response)
        mock_requests_get.return_value = mock_response
        
        with patch('builtins.print') as mock_print:
            version_check.check_for_new_action_version()
            # Use the hardcoded repo name in the expected message
            mock_print.assert_any_call("Warning: Could not check for new action version for 'Contrast-Security-OSS/contrast-resolve-action-dev'. Status: 403")

if __name__ == '__main__': # pragma: no cover
    unittest.main()
