import io
import os
import contextlib
import unittest
import tempfile
from unittest.mock import patch, MagicMock

# Test setup imports (path is set up by conftest.py)
from src.config import reset_config
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
            'GITHUB_SERVER_URL': 'https://mockhub.com',
            'CONTRAST_HOST': 'mock.contrastsecurity.com',
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

        # Mock all HTTP requests
        self.requests_patcher = patch('requests.post')
        self.mock_requests_post = self.requests_patcher.start()
        mock_post_response = MagicMock()
        mock_post_response.status_code = 404  # Not found, to avoid further processing
        self.mock_requests_post.return_value = mock_post_response

        # Mock version check requests
        self.version_requests_patcher = patch('src.version_check.requests.get')
        self.mock_requests_get = self.version_requests_patcher.start()
        mock_response = MagicMock()
        mock_response.json.return_value = [{'name': 'v1.0.0'}]
        mock_response.raise_for_status.return_value = None
        self.mock_requests_get.return_value = mock_response

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
        self.version_requests_patcher.stop()
        self.exit_patcher.stop()
        reset_config()

        # Clean up temp directory if it exists
        if hasattr(self, 'temp_home') and os.path.exists(self.temp_home):
            import shutil
            try:
                shutil.rmtree(self.temp_home)
            except Exception:
                pass

    def test_main_output(self):
        # Test main function output
        with io.StringIO() as stdout, contextlib.redirect_stdout(stdout):
            main()
            output = stdout.getvalue().strip()
        self.assertIn("--- Starting Contrast AI SmartFix Script ---", output)


if __name__ == '__main__':
    unittest.main()
