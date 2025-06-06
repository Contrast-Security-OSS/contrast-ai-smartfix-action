import io
import contextlib
import unittest
import sys
import os
import tempfile
from unittest.mock import patch, MagicMock

# Add src directory to Python path for proper imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.main import main

class TestMainFunctionality(unittest.TestCase):

    def setUp(self):
        # Create a temporary directory for HOME to fix git config issues
        self.temp_home = tempfile.mkdtemp()
        
        # Set up base environment variables needed for all tests
        self.base_env = {
            'HOME': self.temp_home,  # Set HOME for git config
            'GITHUB_WORKSPACE': self.temp_home,  # Required by config.py
            'BUILD_COMMAND': 'echo "Mock build command"',
            'FORMATTING_COMMAND': 'echo "Mock formatting command"',
            'GITHUB_TOKEN': 'mock-github-token',
            'GITHUB_REPOSITORY': 'mock/repository',
            'CONTRAST_HOST': 'mock.contrastsecurity.com',  # Without https:// prefix
            'CONTRAST_ORG_ID': 'mock-org-id',
            'CONTRAST_APP_ID': 'mock-app-id',
            'CONTRAST_AUTHORIZATION_KEY': 'mock-auth-key',
            'CONTRAST_API_KEY': 'mock-api-key',
            'BASE_BRANCH': 'main',
            'DEBUG_MODE': 'true',
            'RUN_TASK': 'generate_fix'
        }
        
        # Mock subprocess to prevent actual command execution
        self.subprocess_patcher = patch('subprocess.run')
        self.mock_subprocess_run = self.subprocess_patcher.start()
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = "Mock process output"
        mock_process.communicate.return_value = (b"Mock stdout", b"Mock stderr")
        self.mock_subprocess_run.return_value = mock_process
        
        # Mock git_handler's configure_git_user to prevent git config errors
        self.git_config_patcher = patch('src.git_handler.configure_git_user')
        self.mock_git_config = self.git_config_patcher.start()
        
        # Mock API calls to prevent network issues
        self.api_patcher = patch('src.contrast_api.get_vulnerability_with_prompts')
        self.mock_api = self.api_patcher.start()
        self.mock_api.return_value = None  # No vulnerabilities by default

        # Create a proper mock for requests
        self.requests_module_patcher = patch('src.version_check.requests')
        self.mock_requests_module = self.requests_module_patcher.start()
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status.return_value = None
        self.mock_requests_module.get.return_value = mock_response

        # Mock sys.exit to prevent test termination
        self.exit_patcher = patch('sys.exit')
        self.mock_exit = self.exit_patcher.start()
    
    def tearDown(self):
        # Clean up all patches
        self.subprocess_patcher.stop()
        self.git_config_patcher.stop()
        self.api_patcher.stop()
        self.requests_module_patcher.stop()
        self.exit_patcher.stop()
        
        # Clean up temp directory if it exists
        if hasattr(self, 'temp_home') and os.path.exists(self.temp_home):
            import shutil
            try:
                shutil.rmtree(self.temp_home)
            except:
                pass

    @patch('src.version_check.get_latest_repo_version')
    @patch('src.version_check.check_for_newer_version')
    def test_main_newer_version_available(self, mock_check_newer, mock_get_latest):
        test_env = self.base_env.copy()
        test_env['GITHUB_ACTION_REF'] = 'refs/tags/v1.0.0'
        with patch.dict(os.environ, test_env, clear=True):
            mock_get_latest.return_value = "v1.1.0"
            mock_check_newer.return_value = "v1.1.0"
            current_version_for_test = "v1.0.0"
            
            with io.StringIO() as stdout, contextlib.redirect_stdout(stdout):
                main() 
                output = stdout.getvalue()

            # Check for expected messages
            self.assertIn("Current action version", output)
            self.assertIn("Latest version available in repo", output)
            
            # Verify function calls
            mock_get_latest.assert_called_once()
            mock_check_newer.assert_called_once()

    @patch('src.version_check.get_latest_repo_version')
    @patch('src.version_check.check_for_newer_version')
    def test_main_already_latest_version(self, mock_check_newer, mock_get_latest):
        test_env = self.base_env.copy()
        test_env['GITHUB_ACTION_REF'] = 'v1.1.0'
        with patch.dict(os.environ, test_env, clear=True):
            mock_get_latest.return_value = "v1.1.0"
            mock_check_newer.return_value = None

            with io.StringIO() as stdout, contextlib.redirect_stdout(stdout):
                main()
                output = stdout.getvalue()

            # Check for expected messages
            self.assertIn("Current action version", output)
            self.assertIn("Latest version available in repo", output)
            
            # Verify function calls
            mock_get_latest.assert_called_once()
            mock_check_newer.assert_called_once()

    @patch('src.version_check.get_latest_repo_version')
    @patch('src.version_check.check_for_newer_version')
    def test_main_no_latest_version_found(self, mock_check_newer, mock_get_latest):
        test_env = self.base_env.copy()
        test_env['GITHUB_ACTION_REF'] = 'refs/tags/v1.0.0'
        with patch.dict(os.environ, test_env, clear=True):
            mock_get_latest.return_value = None

            with io.StringIO() as stdout, contextlib.redirect_stdout(stdout):
                main()
                output = stdout.getvalue()

            # Check for expected messages
            self.assertIn("Current action version", output)
            self.assertIn("Could not determine the latest version", output)
            
            # Verify function calls
            mock_get_latest.assert_called_once()
            mock_check_newer.assert_not_called()

    @patch('src.version_check.get_latest_repo_version')
    @patch('src.version_check.check_for_newer_version')
    def test_main_no_action_ref_env(self, mock_check_newer, mock_get_latest):
        # Don't add GITHUB_ACTION_REF to this test
        env_without_action_ref = self.base_env.copy()
        if 'GITHUB_ACTION_REF' in env_without_action_ref:
            del env_without_action_ref['GITHUB_ACTION_REF']
            
        with patch.dict(os.environ, env_without_action_ref, clear=True):
            with io.StringIO() as stdout, contextlib.redirect_stdout(stdout):
                main()
                output = stdout.getvalue()

            # Check for expected messages
            self.assertIn("Warning: GITHUB_ACTION_REF environment variable is not set", output)
            
            # Verify function calls
            mock_get_latest.assert_not_called()
            mock_check_newer.assert_not_called()

    @patch('src.version_check.get_latest_repo_version')
    @patch('src.version_check.check_for_newer_version')
    def test_main_with_sha_ref(self, mock_check_newer, mock_get_latest):
        test_env = self.base_env.copy()
        test_env['GITHUB_ACTION_REF'] = 'abcdef1234567890abcdef1234567890abcdef12'
        with patch.dict(os.environ, test_env, clear=True):
            with io.StringIO() as stdout, contextlib.redirect_stdout(stdout):
                main()
                output = stdout.getvalue()
                
            # Check for expected messages
            self.assertIn("Running action from SHA", output)
            
            # Verify function calls
            mock_get_latest.assert_not_called()
            mock_check_newer.assert_not_called()

    @patch('src.version_check.get_latest_repo_version')
    @patch('src.version_check.check_for_newer_version')
    def test_main_with_branch_ref_unparsable_version(self, mock_check_newer, mock_get_latest):
        test_env = self.base_env.copy()
        test_env['GITHUB_ACTION_REF'] = 'refs/heads/main'
        with patch.dict(os.environ, test_env, clear=True):
            with io.StringIO() as stdout, contextlib.redirect_stdout(stdout):
                main()
                output = stdout.getvalue()
                
            # Check for expected messages
            self.assertIn("Warning: Could not parse current action version", output)
            
            # Verify function calls
            mock_get_latest.assert_not_called()
            mock_check_newer.assert_not_called()

if __name__ == '__main__':
    unittest.main()