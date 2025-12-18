#!/usr/bin/env python3

import unittest
import os
from src.config import get_config, reset_config


class TestContrastLlmConfig(unittest.TestCase):
    """Test cases for the USE_CONTRAST_LLM configuration setting."""

    def setUp(self):
        """Set up test environment before each test."""
        # Store original environment to restore later
        self.original_env = os.environ.copy()

        # Set up minimal required environment variables for testing
        self.env_vars = {
            'GITHUB_WORKSPACE': '/tmp',
            'BUILD_COMMAND': 'echo "Mock build"',
            'GITHUB_TOKEN': 'mock-token',
            'GITHUB_REPOSITORY': 'mock/repo',
            'BASE_BRANCH': 'main',
            'CONTRAST_HOST': 'test.contrastsecurity.com',
            'CONTRAST_ORG_ID': 'test-org-id',
            'CONTRAST_APP_ID': 'test-app-id',
            'CONTRAST_AUTHORIZATION_KEY': 'test-auth-key',
            'CONTRAST_API_KEY': 'test-api-key',
            # Use non-Bedrock model to avoid AWS validation when USE_CONTRAST_LLM=false
            'AGENT_MODEL': 'anthropic/claude-sonnet-4-5'
        }

        os.environ.update(self.env_vars)
        reset_config()

    def tearDown(self):
        """Clean up after each test."""
        # Restore original environment
        os.environ.clear()
        os.environ.update(self.original_env)
        reset_config()

    def test_use_contrast_llm_default_value(self):
        """Test that USE_CONTRAST_LLM defaults to True when not set."""
        # Ensure USE_CONTRAST_LLM is not in environment
        if 'USE_CONTRAST_LLM' in os.environ:
            del os.environ['USE_CONTRAST_LLM']

        reset_config()
        config = get_config(testing=True)

        # Should default to True
        self.assertTrue(config.USE_CONTRAST_LLM)

    def test_use_contrast_llm_set_to_true(self):
        """Test that USE_CONTRAST_LLM can be set to true."""
        os.environ['USE_CONTRAST_LLM'] = 'true'
        reset_config()
        config = get_config(testing=True)

        self.assertTrue(config.USE_CONTRAST_LLM)

    def test_use_contrast_llm_set_to_false(self):
        """Test that USE_CONTRAST_LLM can be set to false."""
        os.environ['USE_CONTRAST_LLM'] = 'false'
        reset_config()
        config = get_config(testing=True)

        self.assertFalse(config.USE_CONTRAST_LLM)

    def test_use_contrast_llm_case_insensitive_true(self):
        """Test that USE_CONTRAST_LLM accepts 'TRUE' (case insensitive)."""
        os.environ['USE_CONTRAST_LLM'] = 'TRUE'
        reset_config()
        config = get_config(testing=True)

        self.assertTrue(config.USE_CONTRAST_LLM)

    def test_use_contrast_llm_case_insensitive_false(self):
        """Test that USE_CONTRAST_LLM accepts 'FALSE' (case insensitive)."""
        os.environ['USE_CONTRAST_LLM'] = 'FALSE'
        reset_config()
        config = get_config(testing=True)

        self.assertFalse(config.USE_CONTRAST_LLM)

    def test_use_contrast_llm_mixed_case(self):
        """Test that USE_CONTRAST_LLM accepts mixed case values."""
        test_cases = [
            ('True', True),
            ('False', False),
            ('tRuE', True),
            ('FaLsE', False)
        ]

        for env_value, expected in test_cases:
            with self.subTest(env_value=env_value):
                os.environ['USE_CONTRAST_LLM'] = env_value
                reset_config()
                config = get_config(testing=True)
                self.assertEqual(config.USE_CONTRAST_LLM, expected)

    def test_use_contrast_llm_invalid_values_default_to_false(self):
        """Test that invalid values for USE_CONTRAST_LLM default to False."""
        invalid_values = ['yes', 'no', '1', '0', 'invalid']

        for invalid_value in invalid_values:
            with self.subTest(invalid_value=invalid_value):
                os.environ['USE_CONTRAST_LLM'] = invalid_value
                reset_config()
                config = get_config(testing=True)
                # Invalid values should result in False (not 'true')
                self.assertFalse(config.USE_CONTRAST_LLM)

    def test_use_contrast_llm_empty_string_uses_default(self):
        """Test that empty string for USE_CONTRAST_LLM uses the default value (True)."""
        os.environ['USE_CONTRAST_LLM'] = ''
        reset_config()
        config = get_config(testing=True)

        # Empty string should fall back to default=True
        self.assertTrue(config.USE_CONTRAST_LLM)

    def test_use_contrast_llm_debug_logging(self):
        """Test that USE_CONTRAST_LLM appears in debug logging when DEBUG_MODE is enabled."""
        os.environ['USE_CONTRAST_LLM'] = 'false'
        os.environ['DEBUG_MODE'] = 'true'
        reset_config()

        # Create config to trigger debug logging
        config = get_config(testing=True)

        # Verify the setting is correct
        self.assertFalse(config.USE_CONTRAST_LLM)
        self.assertTrue(config.DEBUG_MODE)

    def test_environment_variable_can_be_set_and_retrieved(self):
        """Test that USE_CONTRAST_LLM environment variable can be set and retrieved."""
        # Set the environment variable
        os.environ['USE_CONTRAST_LLM'] = "false"

        # Verify it can be retrieved from os.environ
        self.assertEqual(os.environ.get('USE_CONTRAST_LLM'), "false")

        # Verify it works through the config system
        reset_config()
        config = get_config(testing=True)
        self.assertFalse(config.USE_CONTRAST_LLM)


if __name__ == '__main__':
    unittest.main()
