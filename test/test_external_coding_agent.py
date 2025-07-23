#!/usr/bin/env python
#-
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

import sys
import unittest
from unittest.mock import patch, MagicMock
import os

# Add project root to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Define test environment variables used throughout the test file
TEST_ENV_VARS = {
    'GITHUB_REPOSITORY': 'mock/repo',
    'GITHUB_TOKEN': 'mock-token',
    'BASE_BRANCH': 'main',
    'CONTRAST_HOST': 'test-host',
    'CONTRAST_ORG_ID': 'test-org',
    'CONTRAST_APP_ID': 'test-app',
    'CONTRAST_AUTHORIZATION_KEY': 'test-auth',
    'CONTRAST_API_KEY': 'test-api',
    'GITHUB_WORKSPACE': '/tmp',
    'RUN_TASK': 'generate_fix',  # This triggers the requirement for BUILD_COMMAND
    'BUILD_COMMAND': 'echo "Test build command"'  # Required when RUN_TASK=generate_fix with SMARTFIX coding agent
}

# Set environment variables before importing modules to prevent initialization errors
os.environ.update(TEST_ENV_VARS)

# Import with testing=True
from src.config import get_config, reset_config, Config
from src.external_coding_agent import ExternalCodingAgent

class TestExternalCodingAgent(unittest.TestCase):
    """Tests for the ExternalCodingAgent class"""
    
    def setUp(self):
        """Set up test environment before each test"""
        # Use the shared TEST_ENV_VARS for consistent environment setup
        self.env_patcher = patch.dict('os.environ', TEST_ENV_VARS)
        self.env_patcher.start()
        reset_config()  # Reset the config singleton
        self.config = get_config(testing=True)
        
    def tearDown(self):
        """Clean up after each test"""
        self.env_patcher.stop()
        reset_config()
    
    @patch('src.external_coding_agent.log')
    def test_constructor(self, mock_log):
        """Test that we can construct an ExternalCodingAgent object"""
        # Create an ExternalCodingAgent object
        agent = ExternalCodingAgent(self.config)
        
        # Assert that the config was set correctly
        self.assertEqual(agent.config, self.config)
        
        # Assert that log was called with the expected message
        mock_log.assert_called_once_with(f"Initialized ExternalCodingAgent")

if __name__ == '__main__':
    unittest.main()
