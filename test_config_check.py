import unittest
from unittest.mock import patch, call
import os
import sys
from io import StringIO

# Assuming config_check.py is in the same directory or accessible via PYTHONPATH
from config_check import check_config

class TestConfigCheck(unittest.TestCase):

    def setUp(self):
        # Backup original environ
        self.original_environ = os.environ.copy()
        # Clear relevant INPUT_ variables before each test
        for key in list(os.environ.keys()):
            if key.startswith("INPUT_"):
                del os.environ[key]

    def tearDown(self):
        # Restore original environ
        os.environ.clear()
        os.environ.update(self.original_environ)

    def set_env_vars(self, env_vars):
        for key, value in env_vars.items():
            os.environ[f"INPUT_{key}"] = str(value)

    def get_base_required_config(self):
        return {
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
            "BASE_BRANCH": "main",
        }

    def test_all_required_vars_present(self):
        env_vars = self.get_base_required_config()
        self.set_env_vars(env_vars)
        
        config = check_config()

        self.assertEqual(config['GITHUB_TOKEN'], "test_token")
        self.assertEqual(config['CONTRAST_HOST'], "test_host")
        self.assertEqual(config['CONTRAST_ORG_ID'], "test_org_id")
        self.assertEqual(config['CONTRAST_APP_ID'], "test_app_id")
        self.assertEqual(config['CONTRAST_AUTHORIZATION_KEY'], "test_auth_key")
        self.assertEqual(config['CONTRAST_API_KEY'], "test_api_key")
        self.assertEqual(config['AGENT_MODEL'], "test_model")
        self.assertEqual(config['AWS_ACCESS_KEY_ID'], "test_aws_key_id")
        self.assertEqual(config['AWS_SECRET_ACCESS_KEY'], "test_aws_secret_key")
        self.assertEqual(config['AWS_REGION'], "test_aws_region")
        self.assertEqual(config['BASE_BRANCH'], "main")
        self.assertEqual(config['MAX_BUILD_ATTEMPTS'], 6) # Default
        self.assertEqual(config['MAX_OPEN_PRS'], 5) # Default
        self.assertFalse(config['VERBOSE_LOGGING']) # Default

    def test_missing_required_var(self):
        env_vars = self.get_base_required_config()
        del env_vars["CONTRAST_HOST"] # Remove one required var
        self.set_env_vars(env_vars)

        with patch('sys.exit') as mock_exit, \
             patch('sys.stdout', new_callable=StringIO) as mock_stdout, \
             patch('config_check.MessagePrefix') as mock_prefix: # Mock MessagePrefix
            mock_prefix.CONFIG_INVALID.value = "CONFIG_INVALID: " # Set mock value
            check_config()
            mock_exit.assert_called_once_with(1)
            self.assertIn("CONFIG_INVALID: Missing required configuration variables: CONTRAST_HOST", mock_stdout.getvalue())

    def test_multiple_missing_required_vars(self):
        env_vars = self.get_base_required_config()
        del env_vars["CONTRAST_HOST"]
        del env_vars["AGENT_MODEL"]
        del env_vars["BASE_BRANCH"] # Added missing BASE_BRANCH
        self.set_env_vars(env_vars)

        with patch('sys.exit') as mock_exit, \
             patch('sys.stdout', new_callable=StringIO) as mock_stdout, \
             patch('config_check.MessagePrefix') as mock_prefix: # Mock MessagePrefix
            mock_prefix.CONFIG_INVALID.value = "CONFIG_INVALID: " # Set mock value
            check_config()
            mock_exit.assert_called_once_with(1)
            output = mock_stdout.getvalue()
            self.assertIn("CONFIG_INVALID: Missing required configuration variables:", output)
            self.assertIn("CONTRAST_HOST", output)
            self.assertIn("AGENT_MODEL", output)
            self.assertIn("BASE_BRANCH", output) # Check for BASE_BRANCH in output


    def test_default_values_applied(self):
        env_vars = self.get_base_required_config()
        self.set_env_vars(env_vars)
        
        config = check_config()
        
        self.assertEqual(config['MAX_BUILD_ATTEMPTS'], 6)
        self.assertEqual(config['MAX_OPEN_PRS'], 5)
        self.assertFalse(config['VERBOSE_LOGGING'])
        self.assertIsNone(config['BUILD_COMMAND'])
        self.assertIsNone(config['FORMATTING_COMMAND'])
        self.assertEqual(config['BASE_BRANCH'], "main") # Check it has the value from get_base_required_config
        self.assertIsNone(config['AWS_SESSION_TOKEN'])

    @patch('builtins.print')  # Add print mock to prevent actual output
    def test_override_default_values(self, mock_print):
        env_vars = self.get_base_required_config()
        env_vars.update({
            "MAX_BUILD_ATTEMPTS": "10",
            "MAX_OPEN_PRS": "3",
            "VERBOSE_LOGGING": "true",
            "BUILD_COMMAND": "npm run build",
            "FORMATTING_COMMAND": "npm run lint",
            "BASE_BRANCH": "develop",
            "AWS_SESSION_TOKEN": "test_session_token"
        })
        self.set_env_vars(env_vars)

        config = check_config()

        self.assertEqual(config['MAX_BUILD_ATTEMPTS'], 10)
        self.assertEqual(config['MAX_OPEN_PRS'], 3)
        self.assertTrue(config['VERBOSE_LOGGING'])
        self.assertEqual(config['BUILD_COMMAND'], "npm run build")
        self.assertEqual(config['FORMATTING_COMMAND'], "npm run lint")
        self.assertEqual(config['BASE_BRANCH'], "develop")
        self.assertEqual(config['AWS_SESSION_TOKEN'], "test_session_token")

    def test_invalid_max_build_attempts(self):
        env_vars = self.get_base_required_config()
        env_vars["MAX_BUILD_ATTEMPTS"] = "not-an-integer"
        self.set_env_vars(env_vars)

        with patch('sys.exit') as mock_exit, \
             patch('sys.stdout', new_callable=StringIO) as mock_stdout, \
             patch('config_check.MessagePrefix') as mock_prefix: # Mock MessagePrefix
            mock_prefix.CONFIG_INVALID.value = "CONFIG_INVALID: " # Set mock value
            check_config()
            mock_exit.assert_called_once_with(1)
            self.assertIn("CONFIG_INVALID: Invalid value for MAX_BUILD_ATTEMPTS. Must be an integer.", mock_stdout.getvalue())

    def test_invalid_max_open_prs(self):
        env_vars = self.get_base_required_config()
        env_vars["MAX_OPEN_PRS"] = "abc"
        self.set_env_vars(env_vars)

        with patch('sys.exit') as mock_exit, \
             patch('sys.stdout', new_callable=StringIO) as mock_stdout, \
             patch('config_check.MessagePrefix') as mock_prefix: # Mock MessagePrefix
            mock_prefix.CONFIG_INVALID.value = "CONFIG_INVALID: " # Set mock value
            check_config()
            mock_exit.assert_called_once_with(1)
            self.assertIn("CONFIG_INVALID: Invalid value for MAX_OPEN_PRS. Must be an integer.", mock_stdout.getvalue())
            
    @patch('builtins.print')  # Add print mock to prevent actual output
    def test_verbose_logging_true_string(self, mock_print):
        env_vars = self.get_base_required_config()
        env_vars["VERBOSE_LOGGING"] = "True"
        self.set_env_vars(env_vars)
        config = check_config()
        self.assertTrue(config['VERBOSE_LOGGING'])

    @patch('builtins.print')  # Add print mock to prevent actual output
    def test_verbose_logging_false_string(self, mock_print):
        env_vars = self.get_base_required_config()
        env_vars["VERBOSE_LOGGING"] = "False" # Also test mixed case
        self.set_env_vars(env_vars)
        config = check_config()
        self.assertFalse(config['VERBOSE_LOGGING'])
        
    def test_verbose_logging_output(self):
        env_vars = self.get_base_required_config()
        env_vars.update({
            "VERBOSE_LOGGING": "true",
            "BUILD_COMMAND": "make build",
            "CONTRAST_API_KEY": "sensitive_api_key", # Test masking
            "GITHUB_TOKEN": "sensitive_github_token", # Test masking
            "BASE_BRANCH": "feature_branch" # Added to test output
        })
        self.set_env_vars(env_vars)

        with patch('builtins.print') as mock_print, \
             patch('config_check.MessagePrefix') as mock_prefix: # Mock MessagePrefix
            mock_prefix.INFO.value = "INFO: " # Set mock value
            config = check_config()
            
            self.assertTrue(config['VERBOSE_LOGGING'])
            
            # Check for general verbose logging messages
            mock_print.assert_any_call("INFO: Verbose logging enabled.")
            mock_print.assert_any_call("INFO: Configuration:")
            
            # Check specific config items, including masked ones
            # Order of items in dict is not guaranteed, so check for calls individually
            found_build_command = False
            found_api_key_masked = False
            found_github_token_masked = False
            found_contrast_host = False
            found_base_branch = False # Added for BASE_BRANCH

            for print_call in mock_print.call_args_list:
                arg = print_call.args[0] # print is called with a single string argument
                if "BUILD_COMMAND: make build" in arg:
                    found_build_command = True
                if "CONTRAST_API_KEY: ***" in arg:
                    found_api_key_masked = True
                if "GITHUB_TOKEN: ***" in arg:
                    found_github_token_masked = True
                if f"CONTRAST_HOST: {env_vars['CONTRAST_HOST']}" in arg:
                    found_contrast_host = True
                if f"BASE_BRANCH: {env_vars['BASE_BRANCH']}" in arg: # Check for BASE_BRANCH
                    found_base_branch = True
            
            self.assertTrue(found_build_command, "Build command not found in verbose output")
            self.assertTrue(found_api_key_masked, "API key not masked in verbose output")
            self.assertTrue(found_github_token_masked, "GitHub token not masked in verbose output")
            self.assertTrue(found_contrast_host, "Contrast host not found in verbose output")
            self.assertTrue(found_base_branch, "Base branch not found in verbose output") # Assert BASE_BRANCH

if __name__ == '__main__':
    unittest.main()
