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

import unittest
import os
from unittest.mock import patch

# Test setup imports (path is set up by conftest.py)
from src.config import reset_config
from src.telemetry_handler import initialize_telemetry, get_telemetry_data
from src.smartfix.shared.llm_providers import LlmProvider
from src.smartfix.shared.coding_agents import CodingAgents


class TestTelemetryAttributes(unittest.TestCase):
    """Tests for the new telemetry attributes: llmProvider, agentType, and fullTelemetryEnabled"""

    def setUp(self):
        """Set up test environment before each test"""
        reset_config()

        # Set required environment variables for testing
        self.env_vars = {
            'BASE_BRANCH': 'main',
            'GITHUB_TOKEN': 'test-token',
            'GITHUB_REPOSITORY': 'test/repo',
            'GITHUB_SERVER_URL': 'https://mockhub.com',
            'CONTRAST_HOST': 'test.contrastsecurity.com',
            'CONTRAST_ORG_ID': 'test-org-id',
            'CONTRAST_APP_ID': 'test-app-id',
            'CONTRAST_AUTHORIZATION_KEY': 'test-auth-key',
            'CONTRAST_API_KEY': 'test-api-key',
            'BUILD_COMMAND': 'echo test',
            'GITHUB_WORKSPACE': '/tmp/test-workspace',
        }

    def tearDown(self):
        """Clean up after each test"""
        reset_config()

    @patch.dict(os.environ, clear=True)
    def test_llm_provider_contrast(self):
        """Test that llmProvider is set to CONTRAST when USE_CONTRAST_LLM is true"""
        test_env = {**self.env_vars, 'USE_CONTRAST_LLM': 'true', 'CODING_AGENT': 'SMARTFIX'}

        with patch.dict(os.environ, test_env):
            reset_config()
            initialize_telemetry()
            data = get_telemetry_data()

            self.assertEqual(data['configInfo']['llmProvider'], LlmProvider.CONTRAST.value)

    @patch.dict(os.environ, clear=True)
    def test_llm_provider_byollm(self):
        """Test that llmProvider is set to BYOLLM when USE_CONTRAST_LLM is false"""
        test_env = {**self.env_vars, 'USE_CONTRAST_LLM': 'false', 'CODING_AGENT': 'SMARTFIX'}

        with patch.dict(os.environ, test_env):
            reset_config()
            initialize_telemetry()
            data = get_telemetry_data()

            self.assertEqual(data['configInfo']['llmProvider'], LlmProvider.BYOLLM.value)

    @patch.dict(os.environ, clear=True)
    def test_agent_type_smartfix(self):
        """Test that agentType is set correctly for SMARTFIX agent"""
        test_env = {**self.env_vars, 'CODING_AGENT': 'SMARTFIX'}

        with patch.dict(os.environ, test_env):
            reset_config()
            initialize_telemetry()
            data = get_telemetry_data()

            self.assertEqual(data['configInfo']['agentType'], CodingAgents.SMARTFIX.value)

    @patch.dict(os.environ, clear=True)
    def test_agent_type_github_copilot(self):
        """Test that agentType is set correctly for GITHUB_COPILOT agent"""
        test_env = {**self.env_vars, 'CODING_AGENT': 'GITHUB_COPILOT'}

        with patch.dict(os.environ, test_env):
            reset_config()
            initialize_telemetry()
            data = get_telemetry_data()

            self.assertEqual(data['configInfo']['agentType'], CodingAgents.GITHUB_COPILOT.value)

    @patch.dict(os.environ, clear=True)
    def test_agent_type_claude_code(self):
        """Test that agentType is set correctly for CLAUDE_CODE agent"""
        test_env = {**self.env_vars, 'CODING_AGENT': 'CLAUDE_CODE'}

        with patch.dict(os.environ, test_env):
            reset_config()
            initialize_telemetry()
            data = get_telemetry_data()

            self.assertEqual(data['configInfo']['agentType'], CodingAgents.CLAUDE_CODE.value)

    @patch.dict(os.environ, clear=True)
    def test_full_telemetry_enabled_true(self):
        """Test that fullTelemetryEnabled is true when ENABLE_FULL_TELEMETRY is true"""
        test_env = {**self.env_vars, 'ENABLE_FULL_TELEMETRY': 'true', 'CODING_AGENT': 'SMARTFIX'}

        with patch.dict(os.environ, test_env):
            reset_config()
            initialize_telemetry()
            data = get_telemetry_data()

            self.assertEqual(data['configInfo']['fullTelemetryEnabled'], True)

    @patch.dict(os.environ, clear=True)
    def test_full_telemetry_enabled_false(self):
        """Test that fullTelemetryEnabled is false when ENABLE_FULL_TELEMETRY is false"""
        test_env = {**self.env_vars, 'ENABLE_FULL_TELEMETRY': 'false', 'CODING_AGENT': 'SMARTFIX'}

        with patch.dict(os.environ, test_env):
            reset_config()
            initialize_telemetry()
            data = get_telemetry_data()

            self.assertEqual(data['configInfo']['fullTelemetryEnabled'], False)

    @patch.dict(os.environ, clear=True)
    def test_all_attributes_present(self):
        """Test that all three new attributes are present in configInfo"""
        test_env = {**self.env_vars, 'CODING_AGENT': 'SMARTFIX'}

        with patch.dict(os.environ, test_env):
            reset_config()
            initialize_telemetry()
            data = get_telemetry_data()

            config_info = data['configInfo']
            self.assertIn('llmProvider', config_info)
            self.assertIn('agentType', config_info)
            self.assertIn('fullTelemetryEnabled', config_info)

    @patch.dict(os.environ, clear=True)
    def test_combined_scenario_contrast_smartfix_full_telemetry(self):
        """Test a complete scenario: CONTRAST + SMARTFIX + Full Telemetry"""
        test_env = {
            **self.env_vars,
            'USE_CONTRAST_LLM': 'true',
            'CODING_AGENT': 'SMARTFIX',
            'ENABLE_FULL_TELEMETRY': 'true'
        }

        with patch.dict(os.environ, test_env):
            reset_config()
            initialize_telemetry()
            data = get_telemetry_data()

            config_info = data['configInfo']
            self.assertEqual(config_info['llmProvider'], LlmProvider.CONTRAST.value)
            self.assertEqual(config_info['agentType'], CodingAgents.SMARTFIX.value)
            self.assertEqual(config_info['fullTelemetryEnabled'], True)

    @patch.dict(os.environ, clear=True)
    def test_combined_scenario_byollm_copilot_no_telemetry(self):
        """Test a complete scenario: BYOLLM + COPILOT + No Full Telemetry"""
        test_env = {
            **self.env_vars,
            'USE_CONTRAST_LLM': 'false',
            'CODING_AGENT': 'GITHUB_COPILOT',
            'ENABLE_FULL_TELEMETRY': 'false'
        }

        with patch.dict(os.environ, test_env):
            reset_config()
            initialize_telemetry()
            data = get_telemetry_data()

            config_info = data['configInfo']
            self.assertEqual(config_info['llmProvider'], LlmProvider.BYOLLM.value)
            self.assertEqual(config_info['agentType'], CodingAgents.GITHUB_COPILOT.value)
            self.assertEqual(config_info['fullTelemetryEnabled'], False)

    @patch.dict(os.environ, clear=True)
    def test_default_values(self):
        """Test that default values are set correctly when env vars are not provided"""
        test_env = {**self.env_vars}
        # Not setting USE_CONTRAST_LLM, CODING_AGENT, or ENABLE_FULL_TELEMETRY

        with patch.dict(os.environ, test_env):
            reset_config()
            initialize_telemetry()
            data = get_telemetry_data()

            config_info = data['configInfo']
            # Defaults: USE_CONTRAST_LLM=true, CODING_AGENT=SMARTFIX, ENABLE_FULL_TELEMETRY=true
            self.assertEqual(config_info['llmProvider'], LlmProvider.CONTRAST.value)
            self.assertEqual(config_info['agentType'], CodingAgents.SMARTFIX.value)
            self.assertEqual(config_info['fullTelemetryEnabled'], True)


if __name__ == '__main__':
    unittest.main()
