import unittest
import sys
import os
import io
import tempfile
import contextlib
from unittest.mock import patch, MagicMock

# Add src directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.main import main

class TestMain(unittest.TestCase):
    """Test the main functionality of the application."""

    def setUp(self):
        """Set up test environment before each test."""
        # Create a temporary directory
        self.temp_dir = tempfile.mkdtemp()
        
        # Setup standard env vars needed for testing
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
        
        # Apply environment variables
        self.env_patcher = patch.dict('os.environ', self.env_vars, clear=True)
        self.env_patcher.start()
        
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
        self.env_patcher.stop()
        self.subproc_patcher.stop()
        self.git_patcher.stop()
        self.api_patcher.stop()
        self.requests_patcher.stop() 
        self.exit_patcher.stop()
        
        # Clean up temp directory
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            import shutil
            shutil.rmtree(self.temp_dir)
    
    @patch('src.version_check.get_latest_repo_version')
    def test_main_with_version_check(self, mock_get_latest):
        """Test main function with version check."""
        # Setup version check mocks
        mock_get_latest.return_value = "v1.0.0"  
        
        # Add version ref to environment
        updated_env = self.env_vars.copy()
        updated_env['GITHUB_ACTION_REF'] = 'refs/tags/v1.0.0'
        
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
        if 'GITHUB_ACTION_REF' in os.environ:
            del os.environ['GITHUB_ACTION_REF']
            
        # Run main and capture output
        with io.StringIO() as buf, contextlib.redirect_stdout(buf):
            main()
            output = buf.getvalue()
        
        # Verify warning is present
        self.assertIn("Warning: GITHUB_ACTION_REF environment variable is not set", output)

if __name__ == '__main__':
    unittest.main()