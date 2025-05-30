import io
import contextlib
import unittest
from unittest.mock import patch, MagicMock
import os
from src.main import main

class TestMainFunctionality(unittest.TestCase):

    @patch.dict(os.environ, {'GITHUB_ACTION_REF': 'refs/tags/v1.0.0'})
    @patch('src.version_check.get_latest_repo_version') # Corrected target
    @patch('src.version_check.check_for_newer_version') # Corrected target
    def test_main_newer_version_available(self, mock_check_newer, mock_get_latest):
        mock_get_latest.return_value = "v1.1.0"
        mock_check_newer.return_value = "v1.1.0"
        current_version_for_test = "v1.0.0"
        
        with io.StringIO() as stdout, contextlib.redirect_stdout(stdout):
            main() 
            output = stdout.getvalue()

        # Check for the correct, new output format from do_version_check()
        expected_info_messages = [
            f"Current action version (from GITHUB_ACTION_REF 'refs/tags/{current_version_for_test}'): {current_version_for_test}",
            f"Latest version available in repo: v1.1.0",
            f"INFO: A newer version of this action is available (v1.1.0).",
            f"INFO: You are running version {current_version_for_test}.",
            f"INFO: Please update your workflow to use the latest version of the action like this: Contrast-Security-OSS/contrast-resolve-action-dev@v1.1.0"
        ]
        for msg in expected_info_messages:
            self.assertIn(msg, output)
        
        from src.version_check import ACTION_REPO_URL 
        mock_get_latest.assert_called_once_with(ACTION_REPO_URL)
        mock_check_newer.assert_called_once_with(current_version_for_test, "v1.1.0")

    @patch.dict(os.environ, {'GITHUB_ACTION_REF': 'v1.1.0'}) 
    @patch('src.version_check.get_latest_repo_version') # Corrected target
    @patch('src.version_check.check_for_newer_version') # Corrected target
    def test_main_already_latest_version(self, mock_check_newer, mock_get_latest):
        mock_get_latest.return_value = "v1.1.0"
        mock_check_newer.return_value = None

        with io.StringIO() as stdout, contextlib.redirect_stdout(stdout):
            main()
            output = stdout.getvalue()

        self.assertIn("Current action version (from GITHUB_ACTION_REF 'v1.1.0'): v1.1.0", output)
        self.assertIn("Latest version available in repo: v1.1.0", output)
        self.assertNotIn("INFO: A newer version of this action is available", output)
        from src.version_check import ACTION_REPO_URL
        mock_get_latest.assert_called_once_with(ACTION_REPO_URL)
        mock_check_newer.assert_called_once_with("v1.1.0", "v1.1.0")

    @patch.dict(os.environ, {'GITHUB_ACTION_REF': 'refs/tags/v1.0.0'})
    @patch('src.version_check.get_latest_repo_version') # Corrected target
    @patch('src.version_check.check_for_newer_version') # Corrected target
    def test_main_no_latest_version_found(self, mock_check_newer, mock_get_latest):
        mock_get_latest.return_value = None

        with io.StringIO() as stdout, contextlib.redirect_stdout(stdout):
            main()
            output = stdout.getvalue()

        self.assertIn("Current action version (from GITHUB_ACTION_REF 'refs/tags/v1.0.0'): v1.0.0", output)
        self.assertIn("Could not determine the latest version from the repository.", output)
        mock_check_newer.assert_not_called()
        self.assertNotIn("INFO: A newer version of this action is available", output)
        from src.version_check import ACTION_REPO_URL
        mock_get_latest.assert_called_once_with(ACTION_REPO_URL)

    @patch.dict(os.environ, {}, clear=True) 
    @patch('src.version_check.get_latest_repo_version') # Corrected target
    @patch('src.version_check.check_for_newer_version') # Corrected target
    def test_main_no_action_ref_env(self, mock_check_newer, mock_get_latest):
        with io.StringIO() as stdout, contextlib.redirect_stdout(stdout):
            main()
            output = stdout.getvalue()

        self.assertIn("Warning: GITHUB_ACTION_REF environment variable is not set. Version checking is skipped. This variable is automatically set by GitHub Actions. To enable version checking, ensure this script is running as part of a GitHub Action workflow.", output)
        mock_get_latest.assert_not_called()
        mock_check_newer.assert_not_called()

    @patch.dict(os.environ, {'GITHUB_ACTION_REF': 'abcdef1234567890abcdef1234567890abcdef12'}) 
    @patch('src.version_check.get_latest_repo_version') # Corrected target
    @patch('src.version_check.check_for_newer_version') # Corrected target
    def test_main_with_sha_ref(self, mock_check_newer, mock_get_latest):
        with io.StringIO() as stdout, contextlib.redirect_stdout(stdout):
            main()
            output = stdout.getvalue()
        self.assertIn("Running action from SHA: abcdef1234567890abcdef1234567890abcdef12. Skipping version comparison against tags.", output)
        mock_get_latest.assert_not_called()
        mock_check_newer.assert_not_called()

    @patch.dict(os.environ, {'GITHUB_ACTION_REF': 'refs/heads/main'}) 
    @patch('src.version_check.get_latest_repo_version') # Corrected target
    @patch('src.version_check.check_for_newer_version') # Corrected target
    def test_main_with_branch_ref_unparsable_version(self, mock_check_newer, mock_get_latest):
        with io.StringIO() as stdout, contextlib.redirect_stdout(stdout):
            main()
            output = stdout.getvalue()
        self.assertIn("Warning: Could not parse current action version 'refs/heads/main' from GITHUB_ACTION_REF 'refs/heads/main'. Skipping version check.", output)
        mock_get_latest.assert_not_called()
        mock_check_newer.assert_not_called()

if __name__ == '__main__':
    unittest.main()