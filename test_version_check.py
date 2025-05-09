import os
import unittest
from unittest.mock import patch, MagicMock
import requests # Import requests for requests.exceptions.HTTPError
from packaging.version import parse as parse_version # Import for type hinting if needed, or direct use

# Assuming version_check.py is in the same directory or accessible via PYTHONPATH
from version_check import get_latest_repo_version, check_for_newer_version, do_version_check, ACTION_REPO_URL

class TestVersionCheckFunctions(unittest.TestCase): # Renamed for clarity

    @patch('version_check.requests.get')
    def test_get_latest_repo_version_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = [{'name': 'v1.0.0'}, {'name': 'v1.1.0'}, {'name': '0.9.0'}]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        self.assertEqual(get_latest_repo_version("https://github.com/user/repo"), "v1.1.0")

    @patch('version_check.requests.get')
    def test_get_latest_repo_version_handles_non_v_prefix(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = [{'name': '1.0.0'}, {'name': '1.1.0'}, {'name': '0.9.0'}]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        self.assertEqual(get_latest_repo_version("https://github.com/user/repo"), "1.1.0")

    @patch('version_check.requests.get')
    def test_get_latest_repo_version_mixed_tags(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {'name': 'v1.0.0'}, {'name': '1.1.0'}, {'name': 'v0.9.0'},
            {'name': 'latest'}, {'name': 'v2.0.0-alpha'}, {'name': '2.0.1'}
        ]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        self.assertEqual(get_latest_repo_version("https://github.com/user/repo"), "2.0.1")


    @patch('version_check.requests.get')
    def test_get_latest_repo_version_only_invalid_tags(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = [{'name': 'latest'}, {'name': 'beta-feature'}]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        self.assertIsNone(get_latest_repo_version("https://github.com/user/repo"))

    @patch('version_check.requests.get')
    def test_get_latest_repo_version_no_tags(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        self.assertIsNone(get_latest_repo_version("https://github.com/user/repo"))

    @patch('version_check.requests.get')
    def test_get_latest_repo_version_http_error(self, mock_get):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("Test HTTP Error")
        mock_get.return_value = mock_response
        self.assertIsNone(get_latest_repo_version("https://github.com/user/repo"))

    @patch('version_check.requests.get')
    def test_get_latest_repo_version_unexpected_error(self, mock_get):
        mock_get.side_effect = Exception("Unexpected error")
        self.assertIsNone(get_latest_repo_version("https://github.com/user/repo"))
        
    def test_check_for_newer_version_newer_is_found(self):
        self.assertEqual(check_for_newer_version("v1.0.0", "v1.1.0"), "v1.1.0")
        self.assertEqual(check_for_newer_version("1.0.0", "v1.1.0"), "v1.1.0")
        self.assertEqual(check_for_newer_version("v1.0.0", "1.1.0"), "1.1.0")
        self.assertEqual(check_for_newer_version("1.0.0", "1.1.0"), "1.1.0")

    def test_check_for_newer_version_no_newer_found(self):
        self.assertIsNone(check_for_newer_version("v1.1.0", "v1.0.0"))
        self.assertIsNone(check_for_newer_version("1.1.0", "v1.0.0"))
        self.assertIsNone(check_for_newer_version("v1.1.0", "1.0.0"))
        self.assertIsNone(check_for_newer_version("1.1.0", "1.0.0"))

    def test_check_for_newer_version_same_version(self):
        self.assertIsNone(check_for_newer_version("v1.0.0", "v1.0.0"))
        self.assertIsNone(check_for_newer_version("1.0.0", "v1.0.0"))
        self.assertIsNone(check_for_newer_version("v1.0.0", "1.0.0"))
        self.assertIsNone(check_for_newer_version("1.0.0", "1.0.0"))

    def test_check_for_newer_version_prerelease(self):
        self.assertEqual(check_for_newer_version("1.0.0", "1.0.1-alpha"), "1.0.1-alpha")
        self.assertIsNone(check_for_newer_version("1.0.1", "1.0.1-alpha"))
        self.assertEqual(check_for_newer_version("1.0.1-alpha", "1.0.1-beta"), "1.0.1-beta")
        self.assertEqual(check_for_newer_version("v1.0.0", "v1.0.1-alpha"), "v1.0.1-alpha")


    def test_check_for_newer_version_invalid_current_version(self):
        self.assertIsNone(check_for_newer_version("invalid-version", "v1.0.0"))

    def test_check_for_newer_version_invalid_latest_version(self):
        self.assertIsNone(check_for_newer_version("v1.0.0", "invalid-version"))

    def test_check_for_newer_version_both_invalid(self):
        self.assertIsNone(check_for_newer_version("invalid-1", "invalid-2"))

class TestDoVersionCheck(unittest.TestCase):
    # ACTION_REPO_URL is imported from version_check, so it will be the correct one.

    @patch.dict(os.environ, {'GITHUB_ACTION_REF': 'refs/tags/v1.0.0'})
    @patch('version_check.get_latest_repo_version')
    @patch('version_check.check_for_newer_version')
    @patch('builtins.print')
    def test_do_version_check_newer_available(self, mock_print, mock_check_newer, mock_get_latest):
        mock_get_latest.return_value = "v1.1.0"
        mock_check_newer.return_value = "v1.1.0"
        current_version_for_test = "v1.0.0"
        
        # Simulate GITHUB_ACTION_REF for this test case
        with patch.dict(os.environ, {'GITHUB_ACTION_REF': f'refs/tags/{current_version_for_test}'}):
            do_version_check()

        mock_get_latest.assert_called_once_with(ACTION_REPO_URL)
        mock_check_newer.assert_called_once_with(current_version_for_test, "v1.1.0")
        
        # Check for the specific print calls in the new format
        expected_calls = [
            unittest.mock.call(f"Current action version (from GITHUB_ACTION_REF 'refs/tags/{current_version_for_test}'): {current_version_for_test}"),
            unittest.mock.call(f"Latest version available in repo: v1.1.0"),
            unittest.mock.call(f"INFO: A newer version of this action is available (v1.1.0)."),
            unittest.mock.call(f"INFO: You are running version {current_version_for_test}."),
            unittest.mock.call(f"INFO: Please update your workflow to use the latest version of the action like this: Contrast-Security-OSS/contrast-resolve-action-dev@v1.1.0")
        ]
        # Check that all expected calls are present in the mock_print calls
        for expected_call in expected_calls:
            self.assertIn(expected_call, mock_print.call_args_list)

    @patch.dict(os.environ, {'GITHUB_ACTION_REF': 'v1.1.0'})
    @patch('version_check.get_latest_repo_version')
    @patch('version_check.check_for_newer_version')
    @patch('builtins.print')
    def test_do_version_check_already_latest(self, mock_print, mock_check_newer, mock_get_latest):
        mock_get_latest.return_value = "v1.1.0"
        mock_check_newer.return_value = None

        do_version_check()

        mock_get_latest.assert_called_once_with(ACTION_REPO_URL)
        mock_check_newer.assert_called_once_with("v1.1.0", "v1.1.0")
        printed_messages = ' '.join([call_args[0][0] for call_args in mock_print.call_args_list if call_args[0]])
        self.assertIn("Current action version (from GITHUB_ACTION_REF 'v1.1.0'): v1.1.0", printed_messages)
        self.assertIn("Latest version available in repo: v1.1.0", printed_messages)
        self.assertNotIn("INFO: A newer version of this action is available", printed_messages)

    @patch.dict(os.environ, {'GITHUB_ACTION_REF': 'refs/tags/v1.0.0'})
    @patch('version_check.get_latest_repo_version')
    @patch('version_check.check_for_newer_version')
    @patch('builtins.print')
    def test_do_version_check_no_latest_found(self, mock_print, mock_check_newer, mock_get_latest):
        mock_get_latest.return_value = None
        do_version_check()
        mock_get_latest.assert_called_once_with(ACTION_REPO_URL)
        mock_check_newer.assert_not_called()
        printed_messages = ' '.join([call_args[0][0] for call_args in mock_print.call_args_list if call_args[0]])
        self.assertIn("Current action version (from GITHUB_ACTION_REF 'refs/tags/v1.0.0'): v1.0.0", printed_messages)
        self.assertIn("Could not determine the latest version from the repository.", printed_messages)

    @patch.dict(os.environ, {}, clear=True)
    @patch('version_check.get_latest_repo_version')
    @patch('version_check.check_for_newer_version')
    @patch('builtins.print')
    def test_do_version_check_no_action_ref(self, mock_print, mock_check_newer, mock_get_latest):
        do_version_check()
        mock_get_latest.assert_not_called()
        mock_check_newer.assert_not_called()
        self.assertIn(unittest.mock.call("Warning: GITHUB_ACTION_REF is not set. Skipping version check."), mock_print.call_args_list)

    @patch.dict(os.environ, {'GITHUB_ACTION_REF': 'abcdef1234567890abcdef1234567890abcdef12'})
    @patch('version_check.get_latest_repo_version')
    @patch('version_check.check_for_newer_version')
    @patch('builtins.print')
    def test_do_version_check_sha_ref(self, mock_print, mock_check_newer, mock_get_latest):
        do_version_check()
        mock_get_latest.assert_not_called()
        mock_check_newer.assert_not_called()
        self.assertIn(unittest.mock.call("Running action from SHA: abcdef1234567890abcdef1234567890abcdef12. Skipping version comparison against tags."), mock_print.call_args_list)

    @patch.dict(os.environ, {'GITHUB_ACTION_REF': 'refs/heads/main'})
    @patch('version_check.get_latest_repo_version')
    @patch('version_check.check_for_newer_version')
    @patch('builtins.print')
    def test_do_version_check_unparsable_ref(self, mock_print, mock_check_newer, mock_get_latest):
        do_version_check()
        mock_get_latest.assert_not_called()
        mock_check_newer.assert_not_called()
        self.assertIn(unittest.mock.call("Warning: Could not parse current action version 'refs/heads/main' from GITHUB_ACTION_REF 'refs/heads/main'. Skipping version check."), mock_print.call_args_list)

if __name__ == '__main__':
    unittest.main()
