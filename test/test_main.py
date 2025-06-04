#-
# #%L
# Contrast AI SmartFix
# %%
# Copyright (C) 2025 Contrast Security, Inc.
# %%
# Contact: support@contrastsecurity.com
# License: Commercial
# NOTICE: This Software and the patented inventions embodied within may only be
# used as part of Contrast Security’s commercial offerings. Even though it is
# made available through public repositories, use of this Software is subject to
# the applicable End User Licensing Agreement found at
# https://www.contrastsecurity.com/enduser-terms-0317a or as otherwise agreed
# between Contrast Security and the End User. The Software may not be reverse
# engineered, modified, repackaged, sold, redistributed or otherwise used in a
# way not consistent with the End User License Agreement.
# #L%
#

import io
import contextlib
import unittest
from unittest.mock import patch, MagicMock
import os
from src.main import main
from src.message_prefixes import MessagePrefix

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
    @patch('src.version_check.get_latest_repo_version')
    @patch('src.version_check.check_for_newer_version')
    def test_main_newer_version_available(self, mock_check_newer, mock_get_latest):
        self._set_base_config_env_vars() # Ensure config is set
        os.environ['GITHUB_ACTION_REF'] = 'refs/tags/v1.0.0' # Override for this test

        mock_get_latest.return_value = "v1.1.0"
        mock_check_newer.return_value = "v1.1.0"
        current_version_for_test = "v1.0.0"
        
        with io.StringIO() as stdout, contextlib.redirect_stdout(stdout):
            main() 
            output = stdout.getvalue()

        # Check for the correct, new output format from do_version_check()
        expected_info_messages = [
            f"{MessagePrefix.INFO.value}Current action version (from GITHUB_ACTION_REF 'refs/tags/{current_version_for_test}'): {current_version_for_test}",
            f"{MessagePrefix.INFO.value}Latest version available in repo: v1.1.0",
            f"{MessagePrefix.INFO.value}A newer version of this action is available (v1.1.0).",
            f"{MessagePrefix.INFO.value}You are running version {current_version_for_test}.",
            f"{MessagePrefix.INFO.value}Please update your workflow to use the latest version of the action like this: Contrast-Security-OSS/contrast-ai-smartfix-action@v1.1.0"
        ]
        for msg in expected_info_messages:
            self.assertIn(msg, output)
        
        from src.version_check import ACTION_REPO_URL 
        mock_get_latest.assert_called_once_with(ACTION_REPO_URL)
        mock_check_newer.assert_called_once_with(current_version_for_test, "v1.1.0")

    @patch.dict(os.environ, {'GITHUB_ACTION_REF': 'v1.1.0'}) 
    @patch('src.version_check.get_latest_repo_version')
    @patch('src.version_check.check_for_newer_version')
    def test_main_already_latest_version(self, mock_check_newer, mock_get_latest):
        self._set_base_config_env_vars()
        os.environ['GITHUB_ACTION_REF'] = 'v1.1.0'

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
        self._set_base_config_env_vars()
        os.environ['GITHUB_ACTION_REF'] = 'refs/tags/v1.0.0'

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
        self._set_base_config_env_vars() # Set base config
        if 'GITHUB_ACTION_REF' in os.environ: # Specifically remove GITHUB_ACTION_REF for this test
            del os.environ['GITHUB_ACTION_REF']

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
        self._set_base_config_env_vars()
        os.environ['GITHUB_ACTION_REF'] = 'abcdef1234567890abcdef1234567890abcdef12'
        
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
        self._set_base_config_env_vars()
        os.environ['GITHUB_ACTION_REF'] = 'refs/heads/main'

        with io.StringIO() as stdout, contextlib.redirect_stdout(stdout):
            main()
            output = stdout.getvalue()
        self.assertIn("Warning: Could not parse current action version 'refs/heads/main' from GITHUB_ACTION_REF 'refs/heads/main'. Skipping version check.", output)
        mock_get_latest.assert_not_called()
        mock_check_newer.assert_not_called()

if __name__ == '__main__':
    unittest.main()