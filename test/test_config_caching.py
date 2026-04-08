"""Test config caching - verify detection only runs once per process"""
import unittest
from unittest.mock import patch


class TestConfigCaching(unittest.TestCase):
    """Test that command detection uses singleton pattern and only runs once."""

    def setUp(self):
        """Reset config before each test."""
        # Reset the singleton
        from src.config import reset_config
        reset_config()

    def test_detection_runs_once_per_process(self):
        """Verify detection only runs once despite multiple get_config() calls."""
        env = {
            'GITHUB_WORKSPACE': '/tmp',
            'BASE_BRANCH': 'main',
            'GITHUB_TOKEN': 'test',
            'GITHUB_REPOSITORY': 'test/repo',
            'GITHUB_SERVER_URL': 'https://github.com',
            'CONTRAST_HOST': 'test.com',
            'CONTRAST_ORG_ID': 'org',
            'CONTRAST_APP_ID': 'app',
            'CONTRAST_AUTHORIZATION_KEY': 'auth',
            'CONTRAST_API_KEY': 'key',
            # No BUILD_COMMAND - force detection
        }

        with patch.dict('os.environ', env, clear=True):
            with patch('src.config.Config._auto_detect_build_command') as mock_detect:
                mock_detect.return_value = "npm test"

                # Call get_config() multiple times
                from src.config import get_config

                config1 = get_config(testing=False)
                config2 = get_config(testing=False)
                config3 = get_config(testing=False)

                # Verify it's the same instance
                self.assertIs(config1, config2)
                self.assertIs(config2, config3)

                # Detection should only be called ONCE despite 3 get_config() calls
                self.assertEqual(
                    mock_detect.call_count, 1,
                    f"Detection was called {mock_detect.call_count} times, expected 1. "
                    "Singleton pattern ensures detection only runs once per process."
                )

    def test_singleton_returns_same_instance(self):
        """Verify get_config() returns the same instance every time."""
        env = {
            'GITHUB_WORKSPACE': '/tmp',
            'BASE_BRANCH': 'main',
            'BUILD_COMMAND': 'npm test',  # Provide command to skip detection
            'GITHUB_TOKEN': 'test',
            'GITHUB_REPOSITORY': 'test/repo',
            'GITHUB_SERVER_URL': 'https://github.com',
            'CONTRAST_HOST': 'test.com',
            'CONTRAST_ORG_ID': 'org',
            'CONTRAST_APP_ID': 'app',
            'CONTRAST_AUTHORIZATION_KEY': 'auth',
            'CONTRAST_API_KEY': 'key',
        }

        with patch.dict('os.environ', env, clear=True):
            from src.config import get_config

            # Call get_config() 10 times (typical usage in workflow)
            instances = [get_config(testing=False) for _ in range(10)]

            # All instances should be the exact same object
            for instance in instances[1:]:
                self.assertIs(
                    instances[0], instance,
                    "get_config() should return the same singleton instance every time."
                )


if __name__ == '__main__':
    unittest.main(verbosity=2)
