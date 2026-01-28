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
Unit tests for SmartFixLlmAgent class.

This module tests the SmartFixLlmAgent functionality with focused tests on
the extension logic without complex ADK dependencies.
"""

import unittest
import json
import sys
from unittest.mock import Mock, patch, MagicMock

# Mock ADK imports before importing our modules to prevent import errors
# Create a mock LlmAgent class that can be inherited from
class MockLlmAgent:
    """Mock base class for LlmAgent to allow SmartFixLlmAgent to inherit properly."""
    def __init__(self, *args, **kwargs):
        self.name = kwargs.get('name', 'mock-agent')
        self.model = kwargs.get('model')

    @property
    def canonical_model(self):
        """Return the model, mimicking LlmAgent behavior."""
        return self.model

# Create comprehensive mock hierarchy for google.adk to prevent __init__.py import errors
mock_llm_agent_module = MagicMock()
mock_llm_agent_module.Agent = MagicMock

mock_agents_module = MagicMock()
mock_agents_module.llm_agent = mock_llm_agent_module
mock_agents_module.LlmAgent = MockLlmAgent

mock_models_module = MagicMock()
mock_models_module.lite_llm = MagicMock()
mock_models_module.lite_llm.LiteLlm = MagicMock
mock_models_module.lite_llm._get_completion_inputs = MagicMock()
mock_models_module.llm_request = MagicMock()
mock_models_module.llm_request.LlmRequest = MagicMock
mock_models_module.llm_response = MagicMock()
mock_models_module.llm_response.LlmResponse = MagicMock

mock_adk = MagicMock()
mock_adk.agents = mock_agents_module
mock_adk.models = mock_models_module

# Set up all the module mocks to prevent import errors
sys.modules['google'] = MagicMock()
sys.modules['google.adk'] = mock_adk
sys.modules['google.adk.agents'] = mock_agents_module
sys.modules['google.adk.agents.llm_agent'] = mock_llm_agent_module
sys.modules['google.adk.models'] = mock_models_module
sys.modules['google.adk.models.lite_llm'] = mock_models_module.lite_llm
sys.modules['google.adk.models.llm_request'] = mock_models_module.llm_request
sys.modules['google.adk.models.llm_response'] = mock_models_module.llm_response
sys.modules['google.genai'] = MagicMock()
sys.modules['google.genai.types'] = MagicMock()

# Test setup imports (path is set up by conftest.py)
from src.smartfix.extensions.smartfix_llm_agent import SmartFixLlmAgent  # noqa: E402
from src.smartfix.extensions.smartfix_litellm import SmartFixLiteLlm  # noqa: E402


class TestSmartFixLlmAgentFunctionality(unittest.TestCase):
    """Test cases focusing on SmartFixLlmAgent specific functionality."""

    def test_has_extended_model_true(self):
        """Test has_extended_model returns True when SmartFixLiteLlm reference exists."""
        # Test the method logic directly without full object instantiation
        agent = MagicMock()
        agent.canonical_model = Mock(spec=SmartFixLiteLlm)

        # Apply the real method to our mock
        result = SmartFixLlmAgent.has_extended_model(agent)
        self.assertTrue(result)

    def test_has_extended_model_false(self):
        """Test has_extended_model returns False when no SmartFixLiteLlm reference exists."""
        agent = MagicMock()
        agent.canonical_model = Mock()  # Not a SmartFixLiteLlm

        result = SmartFixLlmAgent.has_extended_model(agent)
        self.assertFalse(result)

    def test_get_extended_model_with_reference(self):
        """Test get_extended_model returns the canonical model when it's SmartFixLiteLlm."""
        agent = MagicMock()
        mock_extended_model = Mock(spec=SmartFixLiteLlm)
        agent.canonical_model = mock_extended_model

        # Mock has_extended_model to return True
        with patch.object(SmartFixLlmAgent, 'has_extended_model', return_value=True):
            result = SmartFixLlmAgent.get_extended_model(agent)
            self.assertIs(result, mock_extended_model)

    def test_reset_accumulated_stats_with_extended_model(self):
        """Test that reset delegates to SmartFixLiteLlm model."""
        agent = MagicMock()
        mock_extended_model = Mock(spec=SmartFixLiteLlm)

        # The real method calls get_extended_model first
        with patch.object(agent, 'get_extended_model', return_value=mock_extended_model):
            SmartFixLlmAgent.reset_accumulated_stats(agent)
            # Should delegate to the extended model's reset method
            mock_extended_model.reset_accumulated_stats.assert_called_once()


class TestSmartFixLlmAgentIntegration(unittest.TestCase):
    """Integration tests for SmartFixLlmAgent with real SmartFixLiteLlm instances."""

    @patch('litellm.completion')
    def test_extended_model_delegation_logic(self, mock_completion):
        """Test that SmartFixLlmAgent logic works with SmartFixLiteLlm."""
        # Create a real SmartFixLiteLlm instance
        extended_model = SmartFixLiteLlm(model="test-model")

        # Add some usage to the accumulator to simulate usage
        extended_model.cost_accumulator.add_usage(
            input_tokens=150,
            output_tokens=75,
            cache_read_tokens=50,
            cache_write_tokens=25,
            new_input_cost=0.0015,
            cache_read_cost=0.0001,
            cache_write_cost=0.0008,
            output_cost=0.003
        )

        # Test that the extended model has the expected methods and data
        self.assertTrue(hasattr(extended_model, 'gather_accumulated_stats_dict'))
        self.assertTrue(hasattr(extended_model, 'gather_accumulated_stats'))
        self.assertTrue(hasattr(extended_model, 'reset_accumulated_stats'))

        # Test that we can get statistics from the extended model
        stats_dict = extended_model.gather_accumulated_stats_dict()
        self.assertEqual(stats_dict['call_count'], 1)
        self.assertEqual(stats_dict['token_usage']['total_tokens'], 300)  # 150 + 75 + 50 + 25

        # Test JSON export
        json_stats = extended_model.gather_accumulated_stats()
        self.assertIsInstance(json_stats, str)
        parsed_stats = json.loads(json_stats)
        self.assertEqual(parsed_stats['call_count'], 1)

        # Test reset functionality
        extended_model.reset_accumulated_stats()
        self.assertEqual(extended_model.cost_accumulator.call_count, 0)

    @patch('litellm.completion')
    def test_model_info_functionality(self, mock_completion):
        """Test get_model_info provides correct information."""
        # Create a real SmartFixLiteLlm instance
        extended_model = SmartFixLiteLlm(model="test-model-id")

        # Create a mock agent
        agent = MagicMock()
        agent.name = "test-agent"
        agent.canonical_model = extended_model
        agent.original_extended_model = extended_model

        result = SmartFixLlmAgent.get_model_info(agent)

        self.assertEqual(result['agent_name'], "test-agent")
        self.assertEqual(result['model_name'], "test-model-id")
        self.assertEqual(result['model_type'], "SmartFixLiteLlm")
        self.assertTrue(result['is_extended'])
        self.assertTrue(result['has_stats'])
        self.assertIn('model_id', result)


if __name__ == '__main__':
    unittest.main()
