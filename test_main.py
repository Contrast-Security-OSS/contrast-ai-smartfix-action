import io
import contextlib
import unittest
from unittest.mock import patch, MagicMock
import os
# main.py now imports from version_check, so tests for main might need to mock those imported functions
from main import main 
# No longer directly testing get_latest_repo_version, check_for_newer_version from main
# Those are now in version_check.py and tested in test_version_check.py

class TestMainFunctionality(unittest.TestCase):

    @patch.dict(os.environ, {'GITHUB_ACTION_REF': 'refs/tags/v1.0.0'})
    @patch('version_check.get_latest_repo_version') # Corrected target
    @patch('version_check.check_for_newer_version') # Corrected target
    def test_main_newer_version_available(self, mock_check_newer, mock_get_latest):
        mock_get_latest.return_value = "v1.1.0"
        mock_check_newer.return_value = "v1.1.0"
        current_version_for_test = "v1.0.0"
        
        with io.StringIO() as stdout, contextlib.redirect_stdout(stdout):
            main() 
            output = stdout.getvalue()

        self.assertIn("Hello, World!", output)
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
        
        from version_check import ACTION_REPO_URL 
        mock_get_latest.assert_called_once_with(ACTION_REPO_URL)
        mock_check_newer.assert_called_once_with(current_version_for_test, "v1.1.0")

    @patch.dict(os.environ, {'GITHUB_ACTION_REF': 'v1.1.0'}) 
    @patch('version_check.get_latest_repo_version') # Corrected target
    @patch('version_check.check_for_newer_version') # Corrected target
    def test_main_already_latest_version(self, mock_check_newer, mock_get_latest):
        mock_get_latest.return_value = "v1.1.0"
        mock_check_newer.return_value = None

        with io.StringIO() as stdout, contextlib.redirect_stdout(stdout):
            main()
            output = stdout.getvalue()
        self.assertIn("Hello, World!", output)
        self.assertIn("Current action version (from GITHUB_ACTION_REF 'v1.1.0'): v1.1.0", output)
        self.assertIn("Latest version available in repo: v1.1.0", output)
        self.assertNotIn("INFO: A newer version of this action is available", output)
        from version_check import ACTION_REPO_URL
        mock_get_latest.assert_called_once_with(ACTION_REPO_URL)
        mock_check_newer.assert_called_once_with("v1.1.0", "v1.1.0")

    @patch.dict(os.environ, {'GITHUB_ACTION_REF': 'refs/tags/v1.0.0'})
    @patch('version_check.get_latest_repo_version') # Corrected target
    @patch('version_check.check_for_newer_version') # Corrected target
    def test_main_no_latest_version_found(self, mock_check_newer, mock_get_latest):
        mock_get_latest.return_value = None

        with io.StringIO() as stdout, contextlib.redirect_stdout(stdout):
            main()
            output = stdout.getvalue()
        self.assertIn("Hello, World!", output)
        self.assertIn("Current action version (from GITHUB_ACTION_REF 'refs/tags/v1.0.0'): v1.0.0", output)
        self.assertIn("Could not determine the latest version from the repository.", output)
        mock_check_newer.assert_not_called()
        self.assertNotIn("INFO: A newer version of this action is available", output)
        from version_check import ACTION_REPO_URL
        mock_get_latest.assert_called_once_with(ACTION_REPO_URL)

    @patch.dict(os.environ, {}, clear=True) 
    @patch('version_check.get_latest_repo_version') # Corrected target
    @patch('version_check.check_for_newer_version') # Corrected target
    def test_main_no_action_ref_env(self, mock_check_newer, mock_get_latest):
        with io.StringIO() as stdout, contextlib.redirect_stdout(stdout):
            main()
            output = stdout.getvalue()
        self.assertIn("Hello, World!", output)
        self.assertIn("Warning: GITHUB_ACTION_REF is not set. Skipping version check.", output)
        mock_get_latest.assert_not_called()
        mock_check_newer.assert_not_called()

    @patch.dict(os.environ, {'GITHUB_ACTION_REF': 'abcdef1234567890abcdef1234567890abcdef12'}) 
    @patch('version_check.get_latest_repo_version') # Corrected target
    @patch('version_check.check_for_newer_version') # Corrected target
    def test_main_with_sha_ref(self, mock_check_newer, mock_get_latest):
        with io.StringIO() as stdout, contextlib.redirect_stdout(stdout):
            main()
            output = stdout.getvalue()
        self.assertIn("Hello, World!", output)
        self.assertIn("Running action from SHA: abcdef1234567890abcdef1234567890abcdef12. Skipping version comparison against tags.", output)
        mock_get_latest.assert_not_called()
        mock_check_newer.assert_not_called()

    @patch.dict(os.environ, {'GITHUB_ACTION_REF': 'refs/heads/main'}) 
    @patch('version_check.get_latest_repo_version') # Corrected target
    @patch('version_check.check_for_newer_version') # Corrected target
    def test_main_with_branch_ref_unparsable_version(self, mock_check_newer, mock_get_latest):
        with io.StringIO() as stdout, contextlib.redirect_stdout(stdout):
            main()
            output = stdout.getvalue()
        self.assertIn("Hello, World!", output)
        self.assertIn("Warning: Could not parse current action version 'refs/heads/main' from GITHUB_ACTION_REF 'refs/heads/main'. Skipping version check.", output)
        mock_get_latest.assert_not_called()
        mock_check_newer.assert_not_called()

    # Original test, ensuring Hello World still works if version check is skipped for any reason
    def test_hello_world_output_if_version_check_skipped(self):
        with patch.dict(os.environ, {}, clear=True):
            with io.StringIO() as stdout, contextlib.redirect_stdout(stdout):
                main()
                output = stdout.getvalue()
            self.assertIn("Hello, World!", output)
            self.assertIn("Warning: GITHUB_ACTION_REF is not set. Skipping version check.", output)
            self.assertNotIn("Current action version", output) 
            self.assertNotIn("Latest version available", output) 

if __name__ == '__main__':
    unittest.main()