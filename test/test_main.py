import unittest
import sys
import os
import io
import tempfile
import contextlib
from unittest.mock import patch, MagicMock

# Add src directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import test setup helper
sys.path.insert(0, os.path.dirname(__file__))
from setup_test_env import TestEnvironmentMixin, create_temp_repo_dir, cleanup_temp_dir

# Initialize config with testing flag first
from src.config import reset_config, get_config  # noqa: E402
_ = get_config(testing=True)
# Import modules to be tested AFTER config initialization
from src.main import main  # noqa: E402


class TestMain(unittest.TestCase, TestEnvironmentMixin):
    """Test the main functionality of the application."""

    def setUp(self):
        """Set up test environment before each test."""
        # Use helper for temp directory creation
        self.temp_dir = str(create_temp_repo_dir())

        # Setup standard env vars using mixin, then override paths for this test
        self.setup_standard_test_env()

        # Override paths specific to this test
        import os
        self.env_vars = {
            'HOME': self.temp_dir,
            'GITHUB_WORKSPACE': self.temp_dir,
            'BUILD_COMMAND': 'echo "Mock build"',
            'FORMATTING_COMMAND': 'echo "Mock format"',
            'GITHUB_TOKEN': 'mock-token',
            'GITHUB_REPOSITORY': 'mock/repo',
            'CONTRAST_HOST': 'mock.contrastsecurity.com',  # No https:// prefix
            'CONTRAST_ORG_ID': 'mock-org',
            'CONTRAST_APP_ID': 'mock-app',
            'CONTRAST_AUTHORIZATION_KEY': 'mock-auth',
            'CONTRAST_API_KEY': 'mock-api',
            'BASE_BRANCH': 'main',
            'DEBUG_MODE': 'true',
            'RUN_TASK': 'generate_fix'
        }

        # Apply additional environment variables to what the mixin already set up
        os.environ.update(self.env_vars)

        # Reset config for clean test state
        reset_config()

        # Mock subprocess calls
        self.subproc_patcher = patch('subprocess.run')
        self.mock_subprocess = self.subproc_patcher.start()
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = "Mock output"
        mock_process.communicate.return_value = (b"Mock stdout", b"Mock stderr")
        self.mock_subprocess.return_value = mock_process

        # Mock git configuration
        self.git_patcher = patch('src.git_handler.configure_git_user')
        self.mock_git = self.git_patcher.start()

        # Mock API calls
        self.api_patcher = patch('src.contrast_api.get_vulnerability_with_prompts')
        self.mock_api = self.api_patcher.start()
        self.mock_api.return_value = None

        # Mock requests for version checking
        self.requests_patcher = patch('src.version_check.requests.get')
        self.mock_requests_get = self.requests_patcher.start()
        mock_response = MagicMock()
        mock_response.json.return_value = [{'name': 'v1.0.0'}]
        mock_response.raise_for_status.return_value = None
        self.mock_requests_get.return_value = mock_response

        # Mock sys.exit to prevent test termination
        self.exit_patcher = patch('sys.exit')
        self.mock_exit = self.exit_patcher.start()

    def tearDown(self):
        """Clean up after each test."""
        # Stop all patches
        self.cleanup_standard_test_env()
        self.subproc_patcher.stop()
        self.git_patcher.stop()
        self.api_patcher.stop()
        self.requests_patcher.stop()
        self.exit_patcher.stop()
        reset_config()

        # Clean up temp directory
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            import shutil
            shutil.rmtree(self.temp_dir)

    def test_main_with_version_check(self):
        """Test main function with version check."""
        # Add version ref to environment
        updated_env = self.env_vars.copy()
        updated_env['GITHUB_ACTION_REF'] = 'refs/tags/v1.0.0'

        # Create a proper patch for the function as imported in main.py
        # Note: main.py imports from version_check directly, not src.version_check
        with patch('src.version_check.get_latest_repo_version') as mock_get_latest:
            # Setup version check mocks
            mock_get_latest.return_value = "v1.0.0"

            with patch.dict('os.environ', updated_env, clear=True):
                # Run main and capture output
                with io.StringIO() as buf, contextlib.redirect_stdout(buf):
                    main()
                    output = buf.getvalue()

                # Verify main function and version check ran
                self.assertIn("--- Starting Contrast AI SmartFix Script ---", output)
                self.assertIn("Current action version", output)
                mock_get_latest.assert_called_once()

    def test_main_without_action_ref(self):
        """Test main function without GITHUB_ACTION_REF."""
        # Ensure no GITHUB_ACTION_REF is set
        test_env = self.env_vars.copy()
        if 'GITHUB_ACTION_REF' in test_env:
            del test_env['GITHUB_ACTION_REF']
        if 'GITHUB_REF' in test_env:
            del test_env['GITHUB_REF']

        with patch.dict('os.environ', test_env, clear=True):
            # Run main and capture output
            with io.StringIO() as buf, contextlib.redirect_stdout(buf):
                main()
                output = buf.getvalue()

        # Verify warning about missing environment variables is present (updated for new message format)
        self.assertIn("Warning: Neither GITHUB_ACTION_REF nor GITHUB_REF environment variables are set", output)


if __name__ == '__main__':
    unittest.main()
