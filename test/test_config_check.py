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

import unittest
from unittest.mock import patch, call
import os
import sys
from io import StringIO
import importlib # Added for reloading the config module

# Import the module that will be tested and reloaded
# from src import config_check # Comment out initial import, will be imported in tests
# Import MessagePrefix from its actual location
from src.message_prefixes import MessagePrefix

class TestConfigCheck(unittest.TestCase):

    def setUp(self):
        # Backup original environ and stderr
        self.original_environ = os.environ.copy()
        self.original_stderr = sys.stderr
        sys.stderr = StringIO() # Redirect stderr for capturing output
        
        # Clear all potentially relevant environment variables before each test
        # to ensure a clean slate and avoid interference between tests.
        vars_to_clear = [
            "DEBUG_MODE", "BASE_BRANCH", "BUILD_COMMAND", "MAX_BUILD_ATTEMPTS", 
            "FORMATTING_COMMAND", "MAX_OPEN_PRS", "GITHUB_TOKEN", "GITHUB_REPOSITORY",
            "CONTRAST_HOST", "CONTRAST_ORG_ID", "CONTRAST_APP_ID", 
            "CONTRAST_AUTHORIZATION_KEY", "CONTRAST_API_KEY", "AWS_REGION", 
            "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", 
            "AGENT_MODEL", "ATTEMPT_WRITING_SECURITY_TEST", "SKIP_QA_REVIEW", 
            "SKIP_COMMENTS", "VULNERABILITY_SEVERITIES"
        ]
        for key in vars_to_clear:
            if key in os.environ: # Use direct key, not INPUT_ prefixed
                del os.environ[key]
        
        # Import or re-import config_check module here to ensure it's fresh for each test
        # This is important because it might have been modified by previous tests or failed to load.
        if 'src.config_check' in sys.modules:
            del sys.modules['src.config_check']
        if 'src.utils' in sys.modules: # utils imports config_check, so reload it too if present
            del sys.modules['src.utils']
            
        from src import config_check
        self.config_check_module = config_check
        # We also need to ensure utils is reloaded if it was cached and depends on an old config_check
        # This can be done by reloading it after config_check or ensuring it's also removed from sys.modules
        # For now, removing from sys.modules is handled above.

    def tearDown(self):
        # Restore original environ and stderr
        os.environ.clear()
        os.environ.update(self.original_environ)
        sys.stderr = self.original_stderr
        
        # Remove config_check and utils from sys.modules to ensure they are fully reloaded next time
        if 'src.config_check' in sys.modules:
            del sys.modules['src.config_check']
        if 'src.utils' in sys.modules:
            del sys.modules['src.utils']
        self.config_check_module = None

    def set_env_vars(self, env_vars):
        for key, value in env_vars.items():
            # Set directly, no INPUT_ prefix needed as per user's config_check.py
            os.environ[key] = str(value)

    def get_minimal_required_env_for_load(self):
        """Returns minimal env vars for load_and_validate_config to pass basic checks."""
        return {
            "GITHUB_REPOSITORY": "test/repo",
            "GITHUB_TOKEN": "test_token",
            "CONTRAST_HOST": "test_host",
            "CONTRAST_ORG_ID": "test_org_id",
            "CONTRAST_APP_ID": "test_app_id",
            "CONTRAST_AUTHORIZATION_KEY": "test_auth_key",
            "CONTRAST_API_KEY": "test_api_key",
            # AGENT_MODEL defaults, so not strictly required unless it's bedrock and AWS vars are missing
        }

    def get_aws_config_for_bedrock(self):
        return {
            "AWS_ACCESS_KEY_ID": "test_aws_key_id",
            "AWS_SECRET_ACCESS_KEY": "test_aws_secret_key",
            "AWS_REGION": "test_aws_region",
        }

    def test_get_env_var_required_present(self):
        os.environ["TEST_VAR"] = "test_value"
        # Directly test the function from the imported module
        val = self.config_check_module.get_env_var("TEST_VAR")
        self.assertEqual(val, "test_value")
        self.assertEqual(sys.stderr.getvalue(), "") # No error output

    def test_get_env_var_required_missing_exits(self):
        with patch('sys.exit') as mock_exit:
            mock_exit.side_effect = SystemExit # Ensure SystemExit is raised
            with self.assertRaises(SystemExit): # Expect SystemExit
                self.config_check_module.get_env_var("MISSING_REQUIRED_VAR")
            mock_exit.assert_called_once_with(1)
            self.assertIn(f"{MessagePrefix.ERROR.value}Required environment variable MISSING_REQUIRED_VAR is not set.", sys.stderr.getvalue())

    def test_get_env_var_optional_missing_returns_default(self):
        val = self.config_check_module.get_env_var("OPTIONAL_MISSING", required=False, default="default_val")
        self.assertEqual(val, "default_val")
        self.assertEqual(sys.stderr.getvalue(), "")

    def test_get_env_var_optional_present_overrides_default(self):
        os.environ["OPTIONAL_PRESENT"] = "actual_value"
        val = self.config_check_module.get_env_var("OPTIONAL_PRESENT", required=False, default="default_val")
        self.assertEqual(val, "actual_value")
        self.assertEqual(sys.stderr.getvalue(), "")

    def test_get_env_var_optional_missing_no_default_returns_none(self):
        val = self.config_check_module.get_env_var("OPTIONAL_MISSING_NO_DEFAULT", required=False)
        self.assertIsNone(val)
        self.assertEqual(sys.stderr.getvalue(), "")

    def test_parse_and_validate_severities_valid_json(self):
        severities_json = '["CRITICAL", "high", "MeDiUm"]'
        expected = ["CRITICAL", "HIGH", "MEDIUM"]
        result = self.config_check_module._parse_and_validate_severities(severities_json)
        self.assertEqual(result, expected)
        self.assertEqual(sys.stderr.getvalue(), "")

    def test_parse_and_validate_severities_invalid_json_string_uses_default(self):
        severities_json = '["CRITICAL", "high"' # Malformed
        expected_default = ["CRITICAL", "HIGH"]
        result = self.config_check_module._parse_and_validate_severities(severities_json)
        self.assertEqual(result, expected_default)
        self.assertIn(f"{MessagePrefix.ERROR.value}Parsing vulnerability_severities JSON:", sys.stderr.getvalue())

    def test_parse_and_validate_severities_not_a_list_uses_default(self):
        severities_json = '{"sev": "critical"}'
        expected_default = ["CRITICAL", "HIGH"]
        result = self.config_check_module._parse_and_validate_severities(severities_json)
        self.assertEqual(result, expected_default)
        self.assertIn(f"{MessagePrefix.WARNING.value}vulnerability_severities must be a list, got <class 'dict'>. Using default.", sys.stderr.getvalue())

    def test_parse_and_validate_severities_empty_string_uses_default(self):
        severities_json = ''
        expected_default = ["CRITICAL", "HIGH"]
        result = self.config_check_module._parse_and_validate_severities(severities_json)
        self.assertEqual(result, expected_default)
        self.assertEqual(sys.stderr.getvalue(), "") # No error/warning for empty string, uses default silently

    def test_parse_and_validate_severities_none_input_uses_default(self):
        expected_default = ["CRITICAL", "HIGH"]
        result = self.config_check_module._parse_and_validate_severities(None)
        self.assertEqual(result, expected_default)
        self.assertEqual(sys.stderr.getvalue(), "") # No error/warning for None, uses default silently

    def test_parse_and_validate_severities_mixed_valid_invalid(self):
        severities_json = '["HIGH", "INVALID_SEV", "low"]'
        expected = ["HIGH", "LOW"]
        result = self.config_check_module._parse_and_validate_severities(severities_json)
        self.assertEqual(result, expected)
        self.assertIn(f"{MessagePrefix.WARNING.value}'INVALID_SEV' is not a valid severity level.", sys.stderr.getvalue())

    def test_parse_and_validate_severities_all_invalid_uses_default(self):
        severities_json = '["GARBAGE", "TRASH"]'
        expected_default = ["CRITICAL", "HIGH"]
        result = self.config_check_module._parse_and_validate_severities(severities_json)
        self.assertEqual(result, expected_default)
        self.assertIn(f"{MessagePrefix.WARNING.value}'GARBAGE' is not a valid severity level.", sys.stderr.getvalue())
        self.assertIn(f"{MessagePrefix.WARNING.value}'TRASH' is not a valid severity level.", sys.stderr.getvalue())
        self.assertIn(f"{MessagePrefix.WARNING.value}No valid severity levels provided. Using default:", sys.stderr.getvalue())

    # --- Tests for load_and_validate_config() ---
    def test_load_config_all_required_present_and_defaults(self):
        env_vars = self.get_minimal_required_env_for_load()
        # For bedrock model (default AGENT_MODEL), AWS creds are needed by load_and_validate_config
        env_vars.update(self.get_aws_config_for_bedrock())
        self.set_env_vars(env_vars)
        
        with patch('src.utils.debug_print') as mock_debug_print:
            self.config_check_module.load_and_validate_config()

        # Check that module level variables are set correctly
        self.assertEqual(self.config_check_module.GITHUB_TOKEN, "test_token")
        self.assertEqual(self.config_check_module.CONTRAST_HOST, "test_host")
        self.assertEqual(self.config_check_module.CONTRAST_ORG_ID, "test_org_id")
        self.assertEqual(self.config_check_module.CONTRAST_APP_ID, "test_app_id")
        self.assertEqual(self.config_check_module.CONTRAST_AUTHORIZATION_KEY, "test_auth_key")
        self.assertEqual(self.config_check_module.CONTRAST_API_KEY, "test_api_key")
        self.assertEqual(self.config_check_module.AGENT_MODEL, "bedrock/anthropic.claude-3-7-sonnet-20250219-v1:0")
        self.assertEqual(self.config_check_module.AWS_ACCESS_KEY_ID, "test_aws_key_id")
        self.assertEqual(self.config_check_module.AWS_SECRET_ACCESS_KEY, "test_aws_secret_key")
        self.assertEqual(self.config_check_module.AWS_REGION, "test_aws_region")
        
        # Check default values
        self.assertEqual(self.config_check_module.BASE_BRANCH, "main")
        self.assertEqual(self.config_check_module.MAX_BUILD_ATTEMPTS, 6) # Now an int
        self.assertEqual(self.config_check_module.MAX_OPEN_PRS, 5)       # Now an int
        self.assertFalse(self.config_check_module.DEBUG_MODE)
        self.assertEqual(self.config_check_module.BUILD_COMMAND, "mvn clean install")
        self.assertEqual(self.config_check_module.FORMATTING_COMMAND, "mvn spotless:apply")
        self.assertFalse(self.config_check_module.ATTEMPT_WRITING_SECURITY_TEST)
        self.assertTrue(self.config_check_module.SKIP_QA_REVIEW)
        self.assertFalse(self.config_check_module.SKIP_COMMENTS)
        self.assertEqual(self.config_check_module.VULNERABILITY_SEVERITIES, ["CRITICAL", "HIGH"])
        self.assertEqual(self.config_check_module.GITHUB_REPOSITORY, "test/repo")


    def test_load_config_missing_core_required_var_exits(self):
        env_vars = self.get_minimal_required_env_for_load()
        del env_vars["CONTRAST_HOST"] # Remove one core required var
        self.set_env_vars(env_vars)

        with patch('sys.exit') as mock_exit, \
             patch('src.utils.debug_print'):
            mock_exit.side_effect = SystemExit # Ensure SystemExit is raised
            with self.assertRaises(SystemExit):
                self.config_check_module.load_and_validate_config()
            mock_exit.assert_called_once_with(1)
            self.assertIn(f"{MessagePrefix.ERROR.value}Required environment variable CONTRAST_HOST is not set.", sys.stderr.getvalue())

    def test_load_config_missing_github_repository_exits(self):
        env_vars = self.get_minimal_required_env_for_load()
        del env_vars["GITHUB_REPOSITORY"]
        self.set_env_vars(env_vars)
        with patch('sys.exit') as mock_exit, \
             patch('src.utils.debug_print'):
            mock_exit.side_effect = SystemExit # Ensure SystemExit is raised
            with self.assertRaises(SystemExit):
                self.config_check_module.load_and_validate_config()
            mock_exit.assert_called_once_with(1)
            self.assertIn(f"{MessagePrefix.ERROR.value}Required environment variable GITHUB_REPOSITORY is not set.", sys.stderr.getvalue())


    def test_load_config_override_default_values(self):
        env_vars = self.get_minimal_required_env_for_load()
        env_vars.update(self.get_aws_config_for_bedrock()) # For bedrock model
        env_vars.update({
            "MAX_BUILD_ATTEMPTS": "10",
            "MAX_OPEN_PRS": "3",
            "DEBUG_MODE": "true",
            "BUILD_COMMAND": "npm run build",
            "BASE_BRANCH": "develop",
            "AGENT_MODEL": "bedrock/custom-model",
            "ATTEMPT_WRITING_SECURITY_TEST": "TrUe",
            "SKIP_QA_REVIEW": "FALSE",
            "SKIP_COMMENTS": "true",
            "VULNERABILITY_SEVERITIES": '["LOW", "NOTE"]',
            "AWS_SESSION_TOKEN": "test_session_token",
        })
        self.set_env_vars(env_vars)

        with patch('src.utils.debug_print'):
            self.config_check_module.load_and_validate_config()

        self.assertEqual(self.config_check_module.MAX_BUILD_ATTEMPTS, 10)
        self.assertEqual(self.config_check_module.MAX_OPEN_PRS, 3)
        self.assertTrue(self.config_check_module.DEBUG_MODE)
        self.assertEqual(self.config_check_module.BUILD_COMMAND, "npm run build")
        self.assertEqual(self.config_check_module.BASE_BRANCH, "develop")
        self.assertEqual(self.config_check_module.AGENT_MODEL, "bedrock/custom-model")
        self.assertTrue(self.config_check_module.ATTEMPT_WRITING_SECURITY_TEST)
        self.assertFalse(self.config_check_module.SKIP_QA_REVIEW)
        self.assertTrue(self.config_check_module.SKIP_COMMENTS)
        self.assertEqual(self.config_check_module.VULNERABILITY_SEVERITIES, ["LOW", "NOTE"])
        self.assertEqual(self.config_check_module.AWS_SESSION_TOKEN, "test_session_token")

    def test_load_config_invalid_max_build_attempts_exits(self):
        env_vars = self.get_minimal_required_env_for_load()
        env_vars["MAX_BUILD_ATTEMPTS"] = "not-an-integer"
        env_vars.update(self.get_aws_config_for_bedrock()) # Add AWS creds for default bedrock model
        self.set_env_vars(env_vars)

        with patch('sys.exit') as mock_exit, \
             patch('src.utils.debug_print'):
            mock_exit.side_effect = SystemExit # Ensure SystemExit is raised
            with self.assertRaises(SystemExit):
                self.config_check_module.load_and_validate_config()
            mock_exit.assert_called_once_with(1)
            self.assertIn(f"{MessagePrefix.ERROR.value}Invalid value for MAX_BUILD_ATTEMPTS: 'not-an-integer'. Must be an integer.", sys.stderr.getvalue())

    def test_load_config_invalid_max_open_prs_exits(self):
        env_vars = self.get_minimal_required_env_for_load()
        env_vars["MAX_OPEN_PRS"] = "abc"
        env_vars.update(self.get_aws_config_for_bedrock()) # Add AWS creds for default bedrock model
        self.set_env_vars(env_vars)

        with patch('sys.exit') as mock_exit, \
             patch('src.utils.debug_print'):
            mock_exit.side_effect = SystemExit # Ensure SystemExit is raised
            with self.assertRaises(SystemExit):
                self.config_check_module.load_and_validate_config()
            mock_exit.assert_called_once_with(1)
            self.assertIn(f"{MessagePrefix.ERROR.value}Invalid value for MAX_OPEN_PRS: 'abc'. Must be an integer.", sys.stderr.getvalue())
            
    def test_load_config_debug_mode_true_string(self):
        env_vars = self.get_minimal_required_env_for_load()
        env_vars["DEBUG_MODE"] = "True"
        env_vars.update(self.get_aws_config_for_bedrock()) # Added AWS creds
        self.set_env_vars(env_vars)
        with patch('src.utils.debug_print'):
            self.config_check_module.load_and_validate_config()
        self.assertTrue(self.config_check_module.DEBUG_MODE)

    def test_load_config_debug_mode_false_string(self):
        env_vars = self.get_minimal_required_env_for_load()
        env_vars["DEBUG_MODE"] = "False"
        env_vars.update(self.get_aws_config_for_bedrock()) # Added AWS creds
        self.set_env_vars(env_vars)
        with patch('src.utils.debug_print'):
            self.config_check_module.load_and_validate_config()
        self.assertFalse(self.config_check_module.DEBUG_MODE)
        
    def test_load_config_debug_mode_output(self):
        env_vars = self.get_minimal_required_env_for_load()
        env_vars.update(self.get_aws_config_for_bedrock()) # For bedrock model
        env_vars.update({
            "DEBUG_MODE": "true",
            "BASE_BRANCH": "feature/debug",
            "AGENT_MODEL": "bedrock/debug-model"
        })
        self.set_env_vars(env_vars)

        # Patch debug_print on the utils instance used by the reloaded config_check_module
        with patch.object(self.config_check_module.utils, 'debug_print') as mock_utils_debug_print:
            self.config_check_module.load_and_validate_config()
            
            # Check specific debug print calls made by load_and_validate_config
            mock_utils_debug_print.assert_any_call(f"{MessagePrefix.DEBUG.value}Debug Mode: True")
            mock_utils_debug_print.assert_any_call(f"{MessagePrefix.DEBUG.value}Base Branch: feature/debug")
            mock_utils_debug_print.assert_any_call(f"{MessagePrefix.DEBUG.value}Agent Model: bedrock/debug-model")
            # Add more checks as needed for other debug prints

    def test_load_config_bedrock_model_missing_aws_creds_exits(self):
        env_vars = self.get_minimal_required_env_for_load()
        env_vars["AGENT_MODEL"] = "bedrock/some-model"
        # DO NOT set AWS credentials (AWS_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
        # Ensure they are not in env_vars from get_minimal_required_env_for_load either
        aws_keys_to_remove = ["AWS_REGION", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]
        for k in aws_keys_to_remove:
            if k in env_vars: del env_vars[k]

        self.set_env_vars(env_vars)

        with patch('sys.exit') as mock_exit, \
             patch('src.utils.debug_print'):
            mock_exit.side_effect = SystemExit # Ensure SystemExit is raised
            with self.assertRaises(SystemExit):
                self.config_check_module.load_and_validate_config()
            mock_exit.assert_called_once_with(1)
            self.assertIn(f"{MessagePrefix.ERROR.value}Bedrock agent model ('bedrock/some-model') requires AWS_REGION, AWS_ACCESS_KEY_ID, and AWS_SECRET_ACCESS_KEY to be set.", sys.stderr.getvalue())

    def test_load_config_non_bedrock_model_does_not_require_aws_creds(self):
        env_vars = self.get_minimal_required_env_for_load()
        env_vars["AGENT_MODEL"] = "openai/gpt-4" # Non-bedrock model
        # Ensure no AWS creds are set
        aws_keys_to_remove = ["AWS_REGION", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]
        for k in aws_keys_to_remove:
            if k in env_vars: del env_vars[k]
        self.set_env_vars(env_vars)

        with patch('sys.exit') as mock_exit, patch('src.utils.debug_print'):
            self.config_check_module.load_and_validate_config()
            mock_exit.assert_not_called() # Should not exit
            self.assertEqual(self.config_check_module.AGENT_MODEL, "openai/gpt-4")
            self.assertIsNone(self.config_check_module.AWS_REGION)

    # Tests for VULNERABILITY_SEVERITIES parsing within load_and_validate_config context
    def test_load_config_vulnerability_severities_default(self):
        env_vars = self.get_minimal_required_env_for_load()
        # Ensure VULNERABILITY_SEVERITIES is not set to test default logic in load_and_validate_config
        if "VULNERABILITY_SEVERITIES" in env_vars: del env_vars["VULNERABILITY_SEVERITIES"]
        if "VULNERABILITY_SEVERITIES" in os.environ: del os.environ["VULNERABILITY_SEVERITIES"]
        env_vars.update(self.get_aws_config_for_bedrock()) # Added AWS creds
        self.set_env_vars(env_vars)

        with patch('src.utils.debug_print'):
            self.config_check_module.load_and_validate_config()
        self.assertEqual(self.config_check_module.VULNERABILITY_SEVERITIES, ["CRITICAL", "HIGH"])
        self.assertEqual(sys.stderr.getvalue(), "") # Default case should not print to stderr

    def test_load_config_vulnerability_severities_custom_valid(self):
        env_vars = self.get_minimal_required_env_for_load()
        env_vars["VULNERABILITY_SEVERITIES"] = '["MEDIUM", "LOW", "note"]' # Corrected JSON string
        env_vars.update(self.get_aws_config_for_bedrock()) # Added AWS creds
        self.set_env_vars(env_vars)
        with patch('src.utils.debug_print'): 
            self.config_check_module.load_and_validate_config()
            self.assertEqual(self.config_check_module.VULNERABILITY_SEVERITIES, ["MEDIUM", "LOW", "NOTE"])
            self.assertEqual(sys.stderr.getvalue(), "")

    def test_load_config_vulnerability_severities_custom_mixed_valid_invalid(self):
        env_vars = self.get_minimal_required_env_for_load()
        env_vars["VULNERABILITY_SEVERITIES"] = '["HIGH", "INVALID", "LOW", "CRITICAL", "BAD"]' # Corrected JSON string
        env_vars.update(self.get_aws_config_for_bedrock()) # Added AWS creds
        self.set_env_vars(env_vars)
        # sys.stderr is already redirected in setUp
        with patch('src.utils.debug_print'):
            self.config_check_module.load_and_validate_config() # Call the loading function

            self.assertEqual(self.config_check_module.VULNERABILITY_SEVERITIES, ["HIGH", "LOW", "CRITICAL"])
            output = sys.stderr.getvalue() # Get output from stderr redirected in setUp
            self.assertIn(f"{MessagePrefix.WARNING.value}'INVALID' is not a valid severity level. Must be one of {self.config_check_module.VALID_SEVERITIES}.", output)
            self.assertIn(f"{MessagePrefix.WARNING.value}'BAD' is not a valid severity level. Must be one of {self.config_check_module.VALID_SEVERITIES}.", output)

    def test_load_config_vulnerability_severities_custom_all_invalid_reverts_to_default(self):
        env_vars = self.get_minimal_required_env_for_load()
        env_vars["VULNERABILITY_SEVERITIES"] = '["INVALID1", "INVALID2"]' # Corrected JSON string
        env_vars.update(self.get_aws_config_for_bedrock()) # Added AWS creds
        self.set_env_vars(env_vars)
        with patch('src.utils.debug_print'):
            self.config_check_module.load_and_validate_config() # Call the loading function

            self.assertEqual(self.config_check_module.VULNERABILITY_SEVERITIES, ["CRITICAL", "HIGH"]) 
            output = sys.stderr.getvalue()
            self.assertIn(f"{MessagePrefix.WARNING.value}'INVALID1' is not a valid severity level. Must be one of {self.config_check_module.VALID_SEVERITIES}.", output)
            self.assertIn(f"{MessagePrefix.WARNING.value}'INVALID2' is not a valid severity level. Must be one of {self.config_check_module.VALID_SEVERITIES}.", output)
            self.assertIn(f"{MessagePrefix.WARNING.value}No valid severity levels provided. Using default: {self.config_check_module.VULNERABILITY_SEVERITIES_DEFAULT}", output)
    
    def test_load_config_vulnerability_severities_malformed_json_reverts_to_default(self):
        env_vars = self.get_minimal_required_env_for_load()
        env_vars["VULNERABILITY_SEVERITIES"] = '["HIGH", "LOW"' # Corrected JSON string (malformed)
        env_vars.update(self.get_aws_config_for_bedrock()) # Added AWS creds
        self.set_env_vars(env_vars)
        with patch('src.utils.debug_print'):
            self.config_check_module.load_and_validate_config() # Call the loading function

            self.assertEqual(self.config_check_module.VULNERABILITY_SEVERITIES, ["CRITICAL", "HIGH"])
            self.assertIn(f"{MessagePrefix.ERROR.value}Parsing vulnerability_severities JSON:", sys.stderr.getvalue())

    def test_load_config_vulnerability_severities_not_a_list_reverts_to_default(self):
        env_vars = self.get_minimal_required_env_for_load()
        env_vars["VULNERABILITY_SEVERITIES"] = '{"severity": "HIGH"}' # Corrected JSON string (dict)
        env_vars.update(self.get_aws_config_for_bedrock()) # Added AWS creds
        self.set_env_vars(env_vars)
        with patch('src.utils.debug_print'):
            self.config_check_module.load_and_validate_config() # Call the loading function

            self.assertEqual(self.config_check_module.VULNERABILITY_SEVERITIES, ["CRITICAL", "HIGH"])
            self.assertIn(f"{MessagePrefix.WARNING.value}vulnerability_severities must be a list, got <class 'dict'>. Using default: {self.config_check_module.VULNERABILITY_SEVERITIES_DEFAULT}", sys.stderr.getvalue())
            
    def test_skip_comments_true(self):
        env_vars = self.get_minimal_required_env_for_load()
        env_vars["SKIP_COMMENTS"] = "true"
        env_vars.update(self.get_aws_config_for_bedrock()) # Added AWS creds
        self.set_env_vars(env_vars)
        with patch('src.utils.debug_print'):
            self.config_check_module.load_and_validate_config()
        self.assertTrue(self.config_check_module.SKIP_COMMENTS)

    def test_skip_comments_false(self):
        env_vars = self.get_minimal_required_env_for_load()
        env_vars["SKIP_COMMENTS"] = "false"
        env_vars.update(self.get_aws_config_for_bedrock()) # Added AWS creds
        self.set_env_vars(env_vars)
        with patch('src.utils.debug_print'):
            self.config_check_module.load_and_validate_config()
        self.assertFalse(self.config_check_module.SKIP_COMMENTS)

    def test_skip_comments_invalid_string_is_false(self):
        env_vars = self.get_minimal_required_env_for_load()
        env_vars["SKIP_COMMENTS"] = "not-true-or-false"
        env_vars.update(self.get_aws_config_for_bedrock()) # Added AWS creds
        self.set_env_vars(env_vars)
        with patch('src.utils.debug_print'):
            self.config_check_module.load_and_validate_config()
        self.assertFalse(self.config_check_module.SKIP_COMMENTS)

if __name__ == '__main__':
    unittest.main()
