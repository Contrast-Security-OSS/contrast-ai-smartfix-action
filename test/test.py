import io
import os
import contextlib
import unittest
import sys
import tempfile
from unittest.mock import patch, Mock, MagicMock

# Add src directory to Python path for proper imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.main import main

class TestSmartFixAction(unittest.TestCase):

    def setUp(self):
        # Create a temporary directory for HOME to fix git config issues
        self.temp_home = tempfile.mkdtemp()
        
        # Set up mock environment variables for testing
        self.env_patcher = patch.dict('os.environ', {
            'HOME': self.temp_home,  # Set HOME for git config
            'GITHUB_WORKSPACE': self.temp_home,  # Required by config.py
            'BUILD_COMMAND': 'echo "Mock build command"',
            'FORMATTING_COMMAND': 'echo "Mock formatting command"',
            'GITHUB_TOKEN': 'mock-github-token',
            'GITHUB_REPOSITORY': 'mock/repository',
            'CONTRAST_HOST': 'mock.contrastsecurity.com',  # Removed https:// prefix
            'CONTRAST_ORG_ID': 'mock-org-id',
            'CONTRAST_APP_ID': 'mock-app-id',
            'CONTRAST_AUTHORIZATION_KEY': 'mock-auth-key',
            'CONTRAST_API_KEY': 'mock-api-key',
            'BASE_BRANCH': 'main',
            'DEBUG_MODE': 'true',
            'RUN_TASK': 'generate_fix'  # Add RUN_TASK to prevent missing env var errors
        })
        self.env_patcher.start()
        
        # Mock subprocess to prevent actual command execution
        self.subprocess_patcher = patch('subprocess.run')
        self.mock_subprocess_run = self.subprocess_patcher.start()
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = "Mock process output"
        mock_process.stderr = ""
        mock_process.communicate.return_value = (b"Mock stdout", b"Mock stderr")
        self.mock_subprocess_run.return_value = mock_process
        
        # Mock git_handler's configure_git_user to prevent git config errors
        self.git_config_patcher = patch('src.git_handler.configure_git_user')
        self.mock_git_config = self.git_config_patcher.start()
        
        # Mock API calls to prevent network issues
        self.api_patcher = patch('src.contrast_api.get_vulnerability_with_prompts')
        self.mock_api = self.api_patcher.start()
        self.mock_api.return_value = None  # No vulnerabilities by default

        # Mock requests to prevent actual HTTP calls
        self.requests_patcher = patch('requests.get')
        self.mock_requests = self.requests_patcher.start()
        mock_response = MagicMock()
        mock_response.json.return_value = []
        self.mock_requests.return_value = mock_response

        # Mock sys.exit to prevent test termination
        self.exit_patcher = patch('sys.exit')
        self.mock_exit = self.exit_patcher.start()
        
    def tearDown(self):
        # Clean up all patches
        self.env_patcher.stop()
        self.subprocess_patcher.stop()
        self.git_config_patcher.stop()
        self.api_patcher.stop()
        self.requests_patcher.stop()
        self.exit_patcher.stop()
        
        # Clean up temp directory if it exists
        if hasattr(self, 'temp_home') and os.path.exists(self.temp_home):
            import shutil
            try:
                shutil.rmtree(self.temp_home)
            except:
                pass

    def test_main_output(self):
        # Test main function output
        with io.StringIO() as stdout, contextlib.redirect_stdout(stdout):
            main()
            output = stdout.getvalue().strip()
        self.assertIn("--- Starting Contrast AI SmartFix Script ---", output)

if __name__ == '__main__':
    unittest.main()