#!/usr/bin/env python3

import unittest
import os
from unittest.mock import patch
from src.config import get_config, reset_config


class TestConfigIntegration(unittest.TestCase):
    """Integration tests for configuration settings including USE_CONTRAST_LLM."""

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
            'CONTRAST_API_KEY': 'test-api-key'
        }

        os.environ.update(self.env_vars)
        reset_config()

    def tearDown(self):
        """Clean up after each test."""
        # Restore original environment
        os.environ.clear()
        os.environ.update(self.original_env)
        reset_config()

    def test_contrast_llm_true_with_agent_model_config(self):
        """Test that USE_CONTRAST_LLM=True works with agent model configuration."""
        os.environ['USE_CONTRAST_LLM'] = 'true'
        os.environ['AGENT_MODEL'] = 'bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0'
        reset_config()

        config = get_config(testing=True)

        # Both settings should be available
        self.assertTrue(config.USE_CONTRAST_LLM)
        self.assertEqual(config.AGENT_MODEL, 'bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0')

    def test_enable_anthropic_prompt_caching_default(self):
        """Test that ENABLE_ANTHROPIC_PROMPT_CACHING defaults to True."""
        reset_config()
        config = get_config(testing=True)
        self.assertTrue(config.ENABLE_ANTHROPIC_PROMPT_CACHING)

    def test_enable_anthropic_prompt_caching_false(self):
        """Test that ENABLE_ANTHROPIC_PROMPT_CACHING can be set to False."""
        os.environ['ENABLE_ANTHROPIC_PROMPT_CACHING'] = 'false'
        reset_config()
        config = get_config(testing=True)
        self.assertFalse(config.ENABLE_ANTHROPIC_PROMPT_CACHING)

    def test_enable_anthropic_prompt_caching_true(self):
        """Test that ENABLE_ANTHROPIC_PROMPT_CACHING can be explicitly set to True."""
        os.environ['ENABLE_ANTHROPIC_PROMPT_CACHING'] = 'true'
        reset_config()
        config = get_config(testing=True)
        self.assertTrue(config.ENABLE_ANTHROPIC_PROMPT_CACHING)

    def test_contrast_llm_false_requires_agent_model(self):
        """Test that USE_CONTRAST_LLM=False works when AGENT_MODEL is configured."""
        os.environ['USE_CONTRAST_LLM'] = 'false'
        os.environ['AGENT_MODEL'] = 'anthropic/claude-sonnet-4-5-20250929'
        os.environ['ANTHROPIC_API_KEY'] = 'test-key'
        reset_config()

        config = get_config(testing=True)

        # Should be configured for BYOLLM
        self.assertFalse(config.USE_CONTRAST_LLM)
        self.assertEqual(config.AGENT_MODEL, 'anthropic/claude-sonnet-4-5-20250929')

    def test_coding_agent_smartfix_with_contrast_llm(self):
        """Test that SMARTFIX coding agent works with USE_CONTRAST_LLM=True."""
        os.environ['CODING_AGENT'] = 'SMARTFIX'
        os.environ['USE_CONTRAST_LLM'] = 'true'
        reset_config()

        config = get_config(testing=True)

        # Should have SMARTFIX agent with Contrast LLM enabled
        self.assertEqual(config.CODING_AGENT, 'SMARTFIX')
        self.assertTrue(config.USE_CONTRAST_LLM)
        # Default agent model should use Contrast LLM constant
        self.assertEqual(config.AGENT_MODEL, 'contrast/claude-sonnet-4-5')

    def test_coding_agent_smartfix_with_byollm(self):
        """Test that SMARTFIX coding agent works with USE_CONTRAST_LLM=False (BYOLLM)."""
        os.environ['CODING_AGENT'] = 'SMARTFIX'
        os.environ['USE_CONTRAST_LLM'] = 'false'
        os.environ['AGENT_MODEL'] = 'anthropic/claude-sonnet-4-5-20250929'
        reset_config()

        config = get_config(testing=True)

        # Should have SMARTFIX agent with BYOLLM configured
        self.assertEqual(config.CODING_AGENT, 'SMARTFIX')
        self.assertFalse(config.USE_CONTRAST_LLM)
        self.assertEqual(config.AGENT_MODEL, 'anthropic/claude-sonnet-4-5-20250929')

    def test_debug_mode_shows_contrast_llm_setting(self):
        """Test that DEBUG_MODE includes USE_CONTRAST_LLM in logging."""
        os.environ['DEBUG_MODE'] = 'true'
        os.environ['USE_CONTRAST_LLM'] = 'false'
        reset_config()

        with patch('src.config._log_config_message') as mock_log:
            config = get_config(testing=False)  # Use testing=False to trigger debug logging

            # Verify the config values are correct
            self.assertTrue(config.DEBUG_MODE)
            self.assertFalse(config.USE_CONTRAST_LLM)

            # Check that logging was called with our setting
            log_calls = [call.args[0] for call in mock_log.call_args_list]
            contrast_llm_logged = any('Use Contrast LLM: False' in call for call in log_calls)
            self.assertTrue(contrast_llm_logged,
                            f"Expected 'Use Contrast LLM: False' in debug logs. Got: {log_calls}")

    def test_config_singleton_behavior_with_contrast_llm(self):
        """Test that config singleton properly handles USE_CONTRAST_LLM changes."""
        # First config instance
        os.environ['USE_CONTRAST_LLM'] = 'true'
        reset_config()
        config1 = get_config(testing=True)
        self.assertTrue(config1.USE_CONTRAST_LLM)

        # Reset and create new config with different value
        os.environ['USE_CONTRAST_LLM'] = 'false'
        reset_config()
        config2 = get_config(testing=True)
        self.assertFalse(config2.USE_CONTRAST_LLM)

        # Verify they're different instances due to reset
        self.assertNotEqual(id(config1), id(config2))

    def test_all_feature_flags_work_together(self):
        """Test that USE_CONTRAST_LLM works alongside other feature flags."""
        os.environ['USE_CONTRAST_LLM'] = 'true'
        os.environ['SKIP_QA_REVIEW'] = 'false'
        os.environ['SKIP_WRITING_SECURITY_TEST'] = 'true'
        os.environ['ENABLE_FULL_TELEMETRY'] = 'false'
        reset_config()

        config = get_config(testing=True)

        # Verify all feature flags are set correctly
        self.assertTrue(config.USE_CONTRAST_LLM)
        self.assertFalse(config.SKIP_QA_REVIEW)
        self.assertTrue(config.SKIP_WRITING_SECURITY_TEST)
        self.assertFalse(config.ENABLE_FULL_TELEMETRY)

    def test_config_sourced_commands_skip_validation(self):
        """Test that config-sourced commands skip allowlist validation."""
        # Set a command that would normally be blocked (dangerous pattern)
        os.environ['BUILD_COMMAND'] = 'rm -rf /tmp/test && echo "done"'
        reset_config()

        # Should not raise an error because config-sourced commands skip validation
        config = get_config(testing=True)

        # Verify the dangerous command was accepted
        self.assertEqual(config.BUILD_COMMAND, 'rm -rf /tmp/test && echo "done"')

    def test_config_sourced_commands_with_command_substitution(self):
        """Test that config-sourced commands skip validation even with command substitution."""
        # Command substitution would normally be blocked
        os.environ['BUILD_COMMAND'] = 'echo $(date) && npm test'
        reset_config()

        # Should not raise an error
        config = get_config(testing=True)
        self.assertEqual(config.BUILD_COMMAND, 'echo $(date) && npm test')

    def test_config_sourced_commands_with_piping_to_shell(self):
        """Test that config-sourced commands skip validation even with shell piping."""
        # Piping to shell would normally be blocked
        os.environ['BUILD_COMMAND'] = 'curl http://example.com/script.sh | sh'
        reset_config()

        # Should not raise an error
        config = get_config(testing=True)
        self.assertEqual(config.BUILD_COMMAND, 'curl http://example.com/script.sh | sh')

    def test_config_sourced_formatting_command_skips_validation(self):
        """Test that config-sourced FORMATTING_COMMAND also skips validation."""
        # Set a formatting command with dangerous pattern
        os.environ['FORMATTING_COMMAND'] = 'prettier --write src/ && eval "echo test"'
        reset_config()

        # Should not raise an error
        config = get_config(testing=True)
        self.assertEqual(config.FORMATTING_COMMAND, 'prettier --write src/ && eval "echo test"')

    def test_backward_compatibility_default_parameter(self):
        """Test that existing code works without passing source parameter (backward compatibility)."""
        # Use a safe command to test backward compatibility
        os.environ['BUILD_COMMAND'] = 'mvn clean test'
        reset_config()

        # Should work as before, defaulting to config source
        config = get_config(testing=True)
        self.assertEqual(config.BUILD_COMMAND, 'mvn clean test')

    def test_empty_commands_allowed_regardless_of_source(self):
        """Test that empty/None commands are allowed for both sources."""
        # Don't set BUILD_COMMAND - it should be None/empty
        if 'BUILD_COMMAND' in os.environ:
            del os.environ['BUILD_COMMAND']
        reset_config()

        # Should not raise an error
        config = get_config(testing=True)
        # BUILD_COMMAND should be None or empty string
        self.assertIn(config.BUILD_COMMAND, [None, ''])

    def test_both_build_and_format_commands_skip_validation(self):
        """Test that both BUILD_COMMAND and FORMATTING_COMMAND skip validation."""
        os.environ['BUILD_COMMAND'] = 'npm test'
        os.environ['FORMATTING_COMMAND'] = 'prettier --write .'
        reset_config()

        # Both commands should be accepted without errors
        config = get_config(testing=True)

        # Verify both commands are set correctly
        self.assertEqual(config.BUILD_COMMAND, 'npm test')
        self.assertEqual(config.FORMATTING_COMMAND, 'prettier --write .')


if __name__ == '__main__':
    unittest.main()
