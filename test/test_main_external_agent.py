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
import os
from unittest.mock import patch, MagicMock

# Add project root to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Define test environment variables for testing
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
    'RUN_TASK': 'generate_fix',
    'BUILD_COMMAND': 'echo "Test build command"',
    'CODING_AGENT': 'GITHUB_COPILOT'  # Use GITHUB_COPILOT as the external agent
}

# Import with testing=True after setting environment variables
with patch.dict('os.environ', TEST_ENV_VARS):
    from src.config import get_config, reset_config, Config
    from src.external_coding_agent import ExternalCodingAgent

class TestMainExternalAgent(unittest.TestCase):
    """Tests for the main.py module focusing on external coding agent integration"""
    
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

    @patch('src.contrast_api.get_vulnerability_with_prompts')
    @patch('src.contrast_api.send_telemetry_data')
    @patch('src.external_coding_agent.ExternalCodingAgent.generate_fixes')
    @patch('src.main.git_handler')
    @patch('src.main.agent_handler')
    def test_main_uses_external_agent(self, mock_agent_handler, mock_git_handler, 
                                     mock_generate_fixes, mock_send_telemetry, mock_get_vuln):
        """Test that main uses ExternalCodingAgent when CODING_AGENT is not SMARTFIX"""
        # Set up mocks
        # First call returns vulnerability data, subsequent calls return None to exit the loop
        mock_get_vuln.side_effect = [
            {
                'vulnerabilityUuid': 'test-uuid',
                'vulnerabilityTitle': 'Test Vulnerability',
                'remediationId': 'test-remediation-id',
                'fixSystemPrompt': 'system prompt',
                'fixUserPrompt': 'user prompt',
                'qaSystemPrompt': 'qa system prompt',
                'qaUserPrompt': 'qa user prompt',
                'vulnerabilityRuleName': 'test-rule'
            },
            None  # This will cause the loop to exit after processing one vulnerability
        ]
        mock_git_handler.count_open_prs_with_prefix.return_value = 0
        mock_git_handler.check_pr_status_for_label.return_value = "NOT_FOUND"
        mock_git_handler.prepare_feature_branch.return_value = None
        mock_git_handler.generate_label_details.return_value = ("test-label", "test-desc", "test-color")
        mock_generate_fixes.return_value = True  # External agent successfully generates fixes
        
        # Import and run the main function under test conditions
        from src.main import main
        
        # We need to patch sys.exit to prevent the script from actually exiting
        with patch('sys.exit'), \
             patch('src.main.run_build_command', return_value=(True, "Build success")):
            main()
        
        # Verify that the external agent's generate_fixes method was called
        mock_generate_fixes.assert_called_once()
        
        # Verify that telemetry data was sent
        mock_send_telemetry.assert_called()
        
        # Verify that the SmartFix agent (agent_handler.run_ai_fix_agent) was not called
        mock_agent_handler.run_ai_fix_agent.assert_not_called()

if __name__ == '__main__':
    unittest.main()
