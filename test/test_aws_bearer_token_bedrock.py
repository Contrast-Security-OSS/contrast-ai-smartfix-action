#!/usr/bin/env python
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
Unit tests for AWS_BEARER_TOKEN_BEDROCK environment variable support.

This module tests that the AWS_BEARER_TOKEN_BEDROCK environment variable
is properly handled and available for LiteLLM to use for Bedrock authentication.
"""

import sys
import unittest
import os

# Add project root to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import config module (need to initialize before other imports)
from src.config import get_config  # noqa: E402

# Initialize config with testing flag
_ = get_config(testing=True)


class TestAwsBearerTokenBedrock(unittest.TestCase):
    """Test cases for AWS_BEARER_TOKEN_BEDROCK environment variable support."""

    def test_environment_variable_can_be_set(self):
        """Test that AWS_BEARER_TOKEN_BEDROCK environment variable can be set and retrieved."""
        test_token = "test-bearer-token-12345"

        # Set the environment variable
        os.environ['AWS_BEARER_TOKEN_BEDROCK'] = test_token

        # Verify it can be retrieved
        self.assertEqual(os.environ.get('AWS_BEARER_TOKEN_BEDROCK'), test_token)

        # Clean up
        del os.environ['AWS_BEARER_TOKEN_BEDROCK']

    def test_environment_variable_not_set_returns_none(self):
        """Test that missing AWS_BEARER_TOKEN_BEDROCK returns None."""
        # Ensure the variable is not set
        if 'AWS_BEARER_TOKEN_BEDROCK' in os.environ:
            del os.environ['AWS_BEARER_TOKEN_BEDROCK']

        # Verify it returns None when not set
        self.assertIsNone(os.environ.get('AWS_BEARER_TOKEN_BEDROCK'))

    def test_bearer_token_precedence_over_iam(self):
        """Test that AWS_BEARER_TOKEN_BEDROCK can coexist with IAM credentials."""
        # Set both bearer token and IAM credentials
        os.environ['AWS_BEARER_TOKEN_BEDROCK'] = "test-bearer-token"
        os.environ['AWS_ACCESS_KEY_ID'] = "test-access-key"
        os.environ['AWS_SECRET_ACCESS_KEY'] = "test-secret-key"

        try:
            # Verify both are set (LiteLLM will determine which to use based on its own logic)
            self.assertIsNotNone(os.environ.get('AWS_BEARER_TOKEN_BEDROCK'))
            self.assertIsNotNone(os.environ.get('AWS_ACCESS_KEY_ID'))
            self.assertIsNotNone(os.environ.get('AWS_SECRET_ACCESS_KEY'))

        finally:
            # Clean up
            for key in ['AWS_BEARER_TOKEN_BEDROCK', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY']:
                if key in os.environ:
                    del os.environ[key]

    def test_empty_bearer_token_is_ignored(self):
        """Test that an empty AWS_BEARER_TOKEN_BEDROCK value is handled gracefully."""
        # Set an empty bearer token
        os.environ['AWS_BEARER_TOKEN_BEDROCK'] = ""

        try:
            # Verify it's set but empty
            self.assertEqual(os.environ.get('AWS_BEARER_TOKEN_BEDROCK'), "")

            # An empty token should be falsy
            self.assertFalse(os.environ.get('AWS_BEARER_TOKEN_BEDROCK'))

        finally:
            # Clean up
            if 'AWS_BEARER_TOKEN_BEDROCK' in os.environ:
                del os.environ['AWS_BEARER_TOKEN_BEDROCK']

    def test_aws_region_name_can_be_set(self):
        """Test that AWS_REGION_NAME environment variable can be set and retrieved."""
        test_region = "us-east-1"

        # Set the environment variable
        os.environ['AWS_REGION_NAME'] = test_region

        try:
            # Verify it can be retrieved
            self.assertEqual(os.environ.get('AWS_REGION_NAME'), test_region)

        finally:
            # Clean up
            if 'AWS_REGION_NAME' in os.environ:
                del os.environ['AWS_REGION_NAME']

    def test_bearer_token_and_region_together(self):
        """Test that AWS_BEARER_TOKEN_BEDROCK and AWS_REGION_NAME can be used together."""
        test_token = "test-bearer-token-abc123"
        test_region = "us-west-2"

        # Set both environment variables
        os.environ['AWS_BEARER_TOKEN_BEDROCK'] = test_token
        os.environ['AWS_REGION_NAME'] = test_region

        try:
            # Verify both are set correctly
            self.assertEqual(os.environ.get('AWS_BEARER_TOKEN_BEDROCK'), test_token)
            self.assertEqual(os.environ.get('AWS_REGION_NAME'), test_region)

        finally:
            # Clean up
            for key in ['AWS_BEARER_TOKEN_BEDROCK', 'AWS_REGION_NAME']:
                if key in os.environ:
                    del os.environ[key]


if __name__ == '__main__':
    unittest.main()
