import io
import contextlib
import unittest
from unittest.mock import patch, MagicMock
import os
# main.py now imports from version_check, so tests for main might need to mock those imported functions
from main import main 
# No longer directly testing get_latest_repo_version, check_for_newer_version from main
# Those are now in version_check.py and tested in test_version_check.py
from message_prefixes import MessagePrefix # Import MessagePrefix

class TestMainFunctionality(unittest.TestCase):

    def setUp(self):
        self.original_environ = os.environ.copy()
        # Clear potentially relevant env vars
        for key in list(os.environ.keys()):
            if key.startswith("INPUT_") or key == "GITHUB_ACTION_REF":
                del os.environ[key]
        self._set_base_config_env_vars()


    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_environ)

    def _set_base_config_env_vars(self):
        """Sets the minimum required environment variables for config_check to pass."""
        required_inputs = {
            "GITHUB_TOKEN": "test_token",
            "CONTRAST_HOST": "test_host",
            "CONTRAST_ORG_ID": "test_org_id",
            "CONTRAST_APP_ID": "test_app_id",
            "CONTRAST_AUTHORIZATION_KEY": "test_auth_key",
            "CONTRAST_API_KEY": "test_api_key",
            "AGENT_MODEL": "test_model",
            "AWS_ACCESS_KEY_ID": "test_aws_key_id",
            "AWS_SECRET_ACCESS_KEY": "test_aws_secret_key",
            "AWS_REGION": "test_aws_region",
            "BASE_BRANCH": "main" # Added BASE_BRANCH
        }
        for k, v in required_inputs.items():
            os.environ[f"INPUT_{k}"] = v

    @patch.dict(os.environ, {'GITHUB_ACTION_REF': 'refs/tags/v1.0.0'})
    @patch('version_check.get_latest_repo_version') 
    @patch('version_check.check_for_newer_version') 
    def test_main_newer_version_available(self, mock_check_newer, mock_get_latest):
        self._set_base_config_env_vars() # Ensure config is set
        os.environ['GITHUB_ACTION_REF'] = 'refs/tags/v1.0.0' # Override for this test

        mock_get_latest.return_value = "v1.1.0"
        mock_check_newer.return_value = "v1.1.0"
        current_version_for_test = "v1.0.0"
        
        with io.StringIO() as stdout, contextlib.redirect_stdout(stdout):
            main() 
            output = stdout.getvalue()

        self.assertIn("Hello, World!", output)
        # Check for the correct, new output format from do_version_check()
        expected_info_messages = [
            f"{MessagePrefix.INFO.value}Current action version (from GITHUB_ACTION_REF 'refs/tags/{current_version_for_test}'): {current_version_for_test}",
            f"{MessagePrefix.INFO.value}Latest version available in repo: v1.1.0",
            f"{MessagePrefix.INFO.value}A newer version of this action is available (v1.1.0).",
            f"{MessagePrefix.INFO.value}You are running version {current_version_for_test}.",
            f"{MessagePrefix.INFO.value}Please update your workflow to use the latest version of the action like this: Contrast-Security-OSS/contrast-resolve-action-dev@v1.1.0"
        ]
        for msg in expected_info_messages:
            self.assertIn(msg, output)
        
        from version_check import ACTION_REPO_URL 
        mock_get_latest.assert_called_once_with(ACTION_REPO_URL)
        mock_check_newer.assert_called_once_with(current_version_for_test, "v1.1.0")

    @patch.dict(os.environ, {'GITHUB_ACTION_REF': 'v1.1.0'}) 
    @patch('version_check.get_latest_repo_version') 
    @patch('version_check.check_for_newer_version') 
    def test_main_already_latest_version(self, mock_check_newer, mock_get_latest):
        self._set_base_config_env_vars()
        os.environ['GITHUB_ACTION_REF'] = 'v1.1.0'

        mock_get_latest.return_value = "v1.1.0"
        mock_check_newer.return_value = None

        with io.StringIO() as stdout, contextlib.redirect_stdout(stdout):
            main()
            output = stdout.getvalue()
        self.assertIn("Hello, World!", output)
        self.assertIn(f"{MessagePrefix.INFO.value}Current action version (from GITHUB_ACTION_REF 'v1.1.0'): v1.1.0", output)
        self.assertIn(f"{MessagePrefix.INFO.value}Latest version available in repo: v1.1.0", output)
        self.assertNotIn(f"{MessagePrefix.INFO.value}A newer version of this action is available", output)
        from version_check import ACTION_REPO_URL
        mock_get_latest.assert_called_once_with(ACTION_REPO_URL)
        mock_check_newer.assert_called_once_with("v1.1.0", "v1.1.0")

    @patch.dict(os.environ, {'GITHUB_ACTION_REF': 'refs/tags/v1.0.0'})
    @patch('version_check.get_latest_repo_version') 
    @patch('version_check.check_for_newer_version') 
    def test_main_no_latest_version_found(self, mock_check_newer, mock_get_latest):
        self._set_base_config_env_vars()
        os.environ['GITHUB_ACTION_REF'] = 'refs/tags/v1.0.0'

        mock_get_latest.return_value = None

        with io.StringIO() as stdout, contextlib.redirect_stdout(stdout):
            main()
            output = stdout.getvalue()
        self.assertIn("Hello, World!", output)
        self.assertIn(f"{MessagePrefix.INFO.value}Current action version (from GITHUB_ACTION_REF 'refs/tags/v1.0.0'): v1.0.0", output)
        self.assertIn(f"{MessagePrefix.WARNING.value}Could not determine the latest version from the repository.", output)
        mock_check_newer.assert_not_called()
        self.assertNotIn(f"{MessagePrefix.INFO.value}A newer version of this action is available", output)
        from version_check import ACTION_REPO_URL
        mock_get_latest.assert_called_once_with(ACTION_REPO_URL)

    @patch.dict(os.environ, {}, clear=True) 
    @patch('version_check.get_latest_repo_version') 
    @patch('version_check.check_for_newer_version') 
    def test_main_no_action_ref_env(self, mock_check_newer, mock_get_latest):
        self._set_base_config_env_vars() # Set base config
        if 'GITHUB_ACTION_REF' in os.environ: # Specifically remove GITHUB_ACTION_REF for this test
            del os.environ['GITHUB_ACTION_REF']

        with io.StringIO() as stdout, contextlib.redirect_stdout(stdout):
            main()
            output = stdout.getvalue()
        self.assertIn("Hello, World!", output)
        self.assertIn(f"{MessagePrefix.WARNING.value}GITHUB_ACTION_REF is not set. Skipping version check.", output)
        mock_get_latest.assert_not_called()
        mock_check_newer.assert_not_called()

    @patch.dict(os.environ, {'GITHUB_ACTION_REF': 'abcdef1234567890abcdef1234567890abcdef12'}) 
    @patch('version_check.get_latest_repo_version') 
    @patch('version_check.check_for_newer_version') 
    def test_main_with_sha_ref(self, mock_check_newer, mock_get_latest):
        self._set_base_config_env_vars()
        os.environ['GITHUB_ACTION_REF'] = 'abcdef1234567890abcdef1234567890abcdef12'
        
        with io.StringIO() as stdout, contextlib.redirect_stdout(stdout):
            main()
            output = stdout.getvalue()
        self.assertIn("Hello, World!", output)
        self.assertIn(f"{MessagePrefix.INFO.value}Running action from SHA: abcdef1234567890abcdef1234567890abcdef12. Skipping version comparison against tags.", output)
        mock_get_latest.assert_not_called()
        mock_check_newer.assert_not_called()

    @patch.dict(os.environ, {'GITHUB_ACTION_REF': 'refs/heads/main'}) 
    @patch('version_check.get_latest_repo_version') 
    @patch('version_check.check_for_newer_version') 
    def test_main_with_branch_ref_unparsable_version(self, mock_check_newer, mock_get_latest):
        self._set_base_config_env_vars()
        os.environ['GITHUB_ACTION_REF'] = 'refs/heads/main'

        with io.StringIO() as stdout, contextlib.redirect_stdout(stdout):
            main()
            output = stdout.getvalue()
        self.assertIn("Hello, World!", output)
        self.assertIn(f"{MessagePrefix.WARNING.value}Could not parse current action version 'refs/heads/main' from GITHUB_ACTION_REF 'refs/heads/main'. Skipping version check.", output)
        mock_get_latest.assert_not_called()
        mock_check_newer.assert_not_called()

    # Original test, ensuring Hello World still works if version check is skipped for any reason
    def test_hello_world_output_if_version_check_skipped(self):
        self._set_base_config_env_vars() # Set base config
        if 'GITHUB_ACTION_REF' in os.environ: # Specifically remove GITHUB_ACTION_REF for this test
            del os.environ['GITHUB_ACTION_REF']
            
        with io.StringIO() as stdout, contextlib.redirect_stdout(stdout):
            main()
            output = stdout.getvalue()
        self.assertIn("Hello, World!", output)
        self.assertIn(f"{MessagePrefix.WARNING.value}GITHUB_ACTION_REF is not set. Skipping version check.", output)
        self.assertNotIn("Current action version", output) 
        self.assertNotIn("Latest version available", output) 

if __name__ == '__main__':
    unittest.main()