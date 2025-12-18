#!/usr/bin/env python3
# -
# #%L
# Contrast AI SmartFix
# %%
# Copyright (C) 2025 Contrast Security, Inc.
# %%
# Contact: support@contrastsecurity.com
# License: Commercial
# NOTICE: This Software and the patented inventions embodied within may only be
# used as part of Contrast Security's commercial offerings. Even though it is
# made available through public repositories, use of this Software is subject to
# the applicable End User Licensing Agreement found at
# https://www.contrastsecurity.com/enduser-terms-0317a or as otherwise agreed
# between Contrast Security and the End User. The Software may not be reverse
# engineered, modified, repackaged, sold, redistributed or otherwise used in a
# way not consistent with the End User License Agreement.
# #L%
#

"""
Unit tests for AWS Bedrock configuration validation.

Tests the _validate_aws_bedrock_config method in config.py which prevents
cryptic IDNA encoding errors when AWS region is missing or malformed.

Related Jira: AIML-321
"""

import unittest
import os
from src.config import Config, ConfigurationError, reset_config


class TestAwsBedrockValidation(unittest.TestCase):
    """Test cases for AWS Bedrock configuration validation."""

    def setUp(self):
        """Set up test environment before each test."""
        self.original_env = os.environ.copy()
        reset_config()

    def tearDown(self):
        """Clean up after each test."""
        os.environ.clear()
        os.environ.update(self.original_env)
        reset_config()

    def _get_base_env(self):
        """Return base environment variables needed for Config initialization."""
        return {
            'GITHUB_WORKSPACE': '/tmp',
            'BUILD_COMMAND': 'echo "Mock build"',
            'GITHUB_TOKEN': 'mock-token',
            'GITHUB_REPOSITORY': 'mock/repo',
            'GITHUB_SERVER_URL': 'https://github.com',
            'BASE_BRANCH': 'main',
            'CONTRAST_HOST': 'test.contrastsecurity.com',
            'CONTRAST_ORG_ID': 'test-org-id',
            'CONTRAST_APP_ID': 'test-app-id',
            'CONTRAST_AUTHORIZATION_KEY': 'test-auth-key',
            'CONTRAST_API_KEY': 'test-api-key',
        }

    # ========================================================================
    # Tests: Validation should be SKIPPED in these scenarios
    # ========================================================================

    def test_validation_skipped_when_use_contrast_llm_true(self):
        """Validation should be skipped when USE_CONTRAST_LLM is True."""
        env = self._get_base_env()
        env['USE_CONTRAST_LLM'] = 'true'
        env['AGENT_MODEL'] = 'bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0'
        # Intentionally NOT setting AWS_REGION_NAME to verify it's not checked

        # Should NOT raise an error because USE_CONTRAST_LLM=True skips validation
        config = Config(env=env, testing=False)
        self.assertTrue(config.USE_CONTRAST_LLM)

    def test_validation_skipped_when_using_anthropic_direct(self):
        """Validation should be skipped when using Anthropic direct API (not Bedrock)."""
        env = self._get_base_env()
        env['USE_CONTRAST_LLM'] = 'false'
        env['AGENT_MODEL'] = 'anthropic/claude-sonnet-4-5-20250929'
        env['ANTHROPIC_API_KEY'] = 'test-anthropic-key'
        # Intentionally NOT setting AWS_REGION_NAME to verify it's not checked

        # Should NOT raise an error because model is not Bedrock
        config = Config(env=env, testing=False)
        self.assertEqual(config.AGENT_MODEL, 'anthropic/claude-sonnet-4-5-20250929')

    def test_validation_skipped_when_using_gemini(self):
        """Validation should be skipped when using Google Gemini."""
        env = self._get_base_env()
        env['USE_CONTRAST_LLM'] = 'false'
        env['AGENT_MODEL'] = 'gemini/gemini-2.5-pro-preview-05-06'
        env['GEMINI_API_KEY'] = 'test-gemini-key'
        # Intentionally NOT setting AWS_REGION_NAME to verify it's not checked

        # Should NOT raise an error because model is not Bedrock
        config = Config(env=env, testing=False)
        self.assertEqual(config.AGENT_MODEL, 'gemini/gemini-2.5-pro-preview-05-06')

    def test_validation_skipped_when_using_azure(self):
        """Validation should be skipped when using Azure OpenAI."""
        env = self._get_base_env()
        env['USE_CONTRAST_LLM'] = 'false'
        env['AGENT_MODEL'] = 'azure/gpt-4'
        env['AZURE_API_KEY'] = 'test-azure-key'
        env['AZURE_API_BASE'] = 'https://test.openai.azure.com'
        # Intentionally NOT setting AWS_REGION_NAME to verify it's not checked

        # Should NOT raise an error because model is not Bedrock
        config = Config(env=env, testing=False)
        self.assertEqual(config.AGENT_MODEL, 'azure/gpt-4')

    # ========================================================================
    # Tests: Missing AWS_REGION_NAME
    # ========================================================================

    def test_error_when_aws_region_missing_with_bedrock(self):
        """Should raise ConfigurationError when AWS_REGION_NAME is missing for Bedrock."""
        env = self._get_base_env()
        env['USE_CONTRAST_LLM'] = 'false'
        env['AGENT_MODEL'] = 'bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0'
        env['AWS_ACCESS_KEY_ID'] = 'test-access-key'
        env['AWS_SECRET_ACCESS_KEY'] = 'test-secret-key'
        # Intentionally NOT setting AWS_REGION

        with self.assertRaises(ConfigurationError) as context:
            Config(env=env, testing=False)

        self.assertIn('aws_region is required', str(context.exception))

    def test_error_when_aws_region_empty_with_bedrock(self):
        """Should raise ConfigurationError when AWS_REGION_NAME is empty string."""
        env = self._get_base_env()
        env['USE_CONTRAST_LLM'] = 'false'
        env['AGENT_MODEL'] = 'bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0'
        env['AWS_ACCESS_KEY_ID'] = 'test-access-key'
        env['AWS_SECRET_ACCESS_KEY'] = 'test-secret-key'
        env['AWS_REGION_NAME'] = ''

        with self.assertRaises(ConfigurationError) as context:
            Config(env=env, testing=False)

        self.assertIn('aws_region is required', str(context.exception))

    def test_error_when_aws_region_whitespace_only(self):
        """Should raise ConfigurationError when AWS_REGION_NAME is only whitespace."""
        env = self._get_base_env()
        env['USE_CONTRAST_LLM'] = 'false'
        env['AGENT_MODEL'] = 'bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0'
        env['AWS_ACCESS_KEY_ID'] = 'test-access-key'
        env['AWS_SECRET_ACCESS_KEY'] = 'test-secret-key'
        env['AWS_REGION_NAME'] = '   '

        with self.assertRaises(ConfigurationError) as context:
            Config(env=env, testing=False)

        self.assertIn('aws_region is required', str(context.exception))

    # ========================================================================
    # Tests: Invalid AWS_REGION_NAME format
    # ========================================================================

    def test_error_when_aws_region_has_invalid_format(self):
        """Should raise ConfigurationError when AWS_REGION_NAME has invalid format."""
        env = self._get_base_env()
        env['USE_CONTRAST_LLM'] = 'false'
        env['AGENT_MODEL'] = 'bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0'
        env['AWS_ACCESS_KEY_ID'] = 'test-access-key'
        env['AWS_SECRET_ACCESS_KEY'] = 'test-secret-key'
        env['AWS_REGION_NAME'] = 'invalid-region'

        with self.assertRaises(ConfigurationError) as context:
            Config(env=env, testing=False)

        self.assertIn('Invalid aws_region format', str(context.exception))
        self.assertIn('invalid-region', str(context.exception))

    def test_error_when_aws_region_has_quotes(self):
        """Should raise ConfigurationError when AWS_REGION_NAME contains quotes."""
        env = self._get_base_env()
        env['USE_CONTRAST_LLM'] = 'false'
        env['AGENT_MODEL'] = 'bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0'
        env['AWS_ACCESS_KEY_ID'] = 'test-access-key'
        env['AWS_SECRET_ACCESS_KEY'] = 'test-secret-key'
        env['AWS_REGION_NAME'] = '"us-east-1"'

        with self.assertRaises(ConfigurationError) as context:
            Config(env=env, testing=False)

        self.assertIn('Invalid aws_region format', str(context.exception))

    def test_error_when_aws_region_has_uppercase(self):
        """Should raise ConfigurationError when AWS_REGION_NAME has uppercase letters."""
        env = self._get_base_env()
        env['USE_CONTRAST_LLM'] = 'false'
        env['AGENT_MODEL'] = 'bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0'
        env['AWS_ACCESS_KEY_ID'] = 'test-access-key'
        env['AWS_SECRET_ACCESS_KEY'] = 'test-secret-key'
        env['AWS_REGION_NAME'] = 'US-EAST-1'

        with self.assertRaises(ConfigurationError) as context:
            Config(env=env, testing=False)

        self.assertIn('Invalid aws_region format', str(context.exception))

    # ========================================================================
    # Tests: Missing AWS credentials
    # ========================================================================

    def test_error_when_aws_credentials_missing_with_bedrock(self):
        """Should raise ConfigurationError when no AWS credentials provided for Bedrock."""
        env = self._get_base_env()
        env['USE_CONTRAST_LLM'] = 'false'
        env['AGENT_MODEL'] = 'bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0'
        env['AWS_REGION_NAME'] = 'us-east-1'
        # Intentionally NOT setting any AWS credentials

        with self.assertRaises(ConfigurationError) as context:
            Config(env=env, testing=False)

        self.assertIn('AWS credentials required', str(context.exception))
        self.assertIn('AWS_BEARER_TOKEN_BEDROCK', str(context.exception))
        self.assertIn('AWS_ACCESS_KEY_ID', str(context.exception))

    def test_error_when_only_access_key_provided(self):
        """Should raise ConfigurationError when only AWS_ACCESS_KEY_ID is provided."""
        env = self._get_base_env()
        env['USE_CONTRAST_LLM'] = 'false'
        env['AGENT_MODEL'] = 'bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0'
        env['AWS_REGION_NAME'] = 'us-east-1'
        env['AWS_ACCESS_KEY_ID'] = 'test-access-key'
        # Missing AWS_SECRET_ACCESS_KEY

        with self.assertRaises(ConfigurationError) as context:
            Config(env=env, testing=False)

        self.assertIn('AWS credentials required', str(context.exception))

    def test_error_when_only_secret_key_provided(self):
        """Should raise ConfigurationError when only AWS_SECRET_ACCESS_KEY is provided."""
        env = self._get_base_env()
        env['USE_CONTRAST_LLM'] = 'false'
        env['AGENT_MODEL'] = 'bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0'
        env['AWS_REGION_NAME'] = 'us-east-1'
        env['AWS_SECRET_ACCESS_KEY'] = 'test-secret-key'
        # Missing AWS_ACCESS_KEY_ID

        with self.assertRaises(ConfigurationError) as context:
            Config(env=env, testing=False)

        self.assertIn('AWS credentials required', str(context.exception))

    # ========================================================================
    # Tests: Valid configurations (should pass)
    # ========================================================================

    def test_valid_config_with_iam_credentials(self):
        """Should pass validation with valid IAM credentials."""
        env = self._get_base_env()
        env['USE_CONTRAST_LLM'] = 'false'
        env['AGENT_MODEL'] = 'bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0'
        env['AWS_REGION_NAME'] = 'us-east-1'
        env['AWS_ACCESS_KEY_ID'] = 'test-access-key'
        env['AWS_SECRET_ACCESS_KEY'] = 'test-secret-key'

        # Should NOT raise an error
        config = Config(env=env, testing=False)
        self.assertEqual(config.AGENT_MODEL, 'bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0')

    def test_valid_config_with_bearer_token(self):
        """Should pass validation with valid bearer token."""
        env = self._get_base_env()
        env['USE_CONTRAST_LLM'] = 'false'
        env['AGENT_MODEL'] = 'bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0'
        env['AWS_REGION_NAME'] = 'us-east-1'
        env['AWS_BEARER_TOKEN_BEDROCK'] = 'test-bearer-token'

        # Should NOT raise an error
        config = Config(env=env, testing=False)
        self.assertEqual(config.AGENT_MODEL, 'bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0')

    def test_valid_config_with_eu_region(self):
        """Should pass validation with eu-west-2 region."""
        env = self._get_base_env()
        env['USE_CONTRAST_LLM'] = 'false'
        env['AGENT_MODEL'] = 'bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0'
        env['AWS_REGION_NAME'] = 'eu-west-2'
        env['AWS_BEARER_TOKEN_BEDROCK'] = 'test-bearer-token'

        config = Config(env=env, testing=False)
        self.assertIsNotNone(config)

    def test_valid_config_with_ap_region(self):
        """Should pass validation with ap-southeast-1 region."""
        env = self._get_base_env()
        env['USE_CONTRAST_LLM'] = 'false'
        env['AGENT_MODEL'] = 'bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0'
        env['AWS_REGION_NAME'] = 'ap-southeast-1'
        env['AWS_BEARER_TOKEN_BEDROCK'] = 'test-bearer-token'

        config = Config(env=env, testing=False)
        self.assertIsNotNone(config)

    def test_valid_config_with_gov_region(self):
        """Should pass validation with us-gov-west-1 region."""
        env = self._get_base_env()
        env['USE_CONTRAST_LLM'] = 'false'
        env['AGENT_MODEL'] = 'bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0'
        env['AWS_REGION_NAME'] = 'us-gov-west-1'
        env['AWS_BEARER_TOKEN_BEDROCK'] = 'test-bearer-token'

        config = Config(env=env, testing=False)
        self.assertIsNotNone(config)

    def test_valid_config_with_cn_region(self):
        """Should pass validation with cn-north-1 region (China)."""
        env = self._get_base_env()
        env['USE_CONTRAST_LLM'] = 'false'
        env['AGENT_MODEL'] = 'bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0'
        env['AWS_REGION_NAME'] = 'cn-north-1'
        env['AWS_BEARER_TOKEN_BEDROCK'] = 'test-bearer-token'

        config = Config(env=env, testing=False)
        self.assertIsNotNone(config)

    def test_region_with_leading_trailing_whitespace_is_trimmed(self):
        """Should trim whitespace from AWS_REGION_NAME and validate correctly."""
        env = self._get_base_env()
        env['USE_CONTRAST_LLM'] = 'false'
        env['AGENT_MODEL'] = 'bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0'
        env['AWS_REGION_NAME'] = '  us-east-1  '  # Has whitespace
        env['AWS_BEARER_TOKEN_BEDROCK'] = 'test-bearer-token'

        # Should NOT raise an error - whitespace should be trimmed
        config = Config(env=env, testing=False)
        self.assertIsNotNone(config)


if __name__ == '__main__':
    unittest.main()
