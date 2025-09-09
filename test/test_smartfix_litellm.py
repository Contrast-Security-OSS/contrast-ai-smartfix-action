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
Unit tests for SmartFixLiteLlm and TokenCostAccumulator classes.

This module tests the extended LiteLLM functionality including:
- Token cost accumulation and statistics gathering
- Cost calculations with cache awareness
- Public interface methods for statistics reporting
- Proper integration with LiteLLM base functionality
"""

import sys
import unittest
import json
import os
from unittest.mock import patch

# Add project root to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Now import project modules (after path modification)
from src.config import get_config  # noqa: E402

# Initialize config with testing flag
_ = get_config(testing=True)

# Import the classes under test AFTER config initialization
from src.smartfix.extensions.smartfix_litellm import SmartFixLiteLlm, TokenCostAccumulator  # noqa: E402


class TestTokenCostAccumulator(unittest.TestCase):
    """Test cases for TokenCostAccumulator class."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        self.accumulator = TokenCostAccumulator()

    def test_initialization(self):
        """Test that TokenCostAccumulator initializes with zero values."""
        self.assertEqual(self.accumulator.total_new_input_tokens, 0)
        self.assertEqual(self.accumulator.total_output_tokens, 0)
        self.assertEqual(self.accumulator.total_cache_read_tokens, 0)
        self.assertEqual(self.accumulator.total_cache_write_tokens, 0)
        self.assertEqual(self.accumulator.total_new_input_cost, 0.0)
        self.assertEqual(self.accumulator.total_cache_read_cost, 0.0)
        self.assertEqual(self.accumulator.total_cache_write_cost, 0.0)
        self.assertEqual(self.accumulator.total_output_cost, 0.0)
        self.assertEqual(self.accumulator.call_count, 0)

    def test_add_usage_single_call(self):
        """Test adding usage statistics from a single call."""
        self.accumulator.add_usage(
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=25,
            cache_write_tokens=15,
            new_input_cost=0.001,
            cache_read_cost=0.0001,
            cache_write_cost=0.0005,
            output_cost=0.002
        )

        # Verify all values are correctly stored
        self.assertEqual(self.accumulator.total_new_input_tokens, 100)
        self.assertEqual(self.accumulator.total_output_tokens, 50)
        self.assertEqual(self.accumulator.total_cache_read_tokens, 25)
        self.assertEqual(self.accumulator.total_cache_write_tokens, 15)
        self.assertEqual(self.accumulator.total_new_input_cost, 0.001)
        self.assertEqual(self.accumulator.total_cache_read_cost, 0.0001)
        self.assertEqual(self.accumulator.total_cache_write_cost, 0.0005)
        self.assertEqual(self.accumulator.total_output_cost, 0.002)
        self.assertEqual(self.accumulator.call_count, 1)

    def test_add_usage_multiple_calls(self):
        """Test adding usage statistics from multiple calls."""
        # First call
        self.accumulator.add_usage(
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=25,
            cache_write_tokens=15,
            new_input_cost=0.001,
            cache_read_cost=0.0001,
            cache_write_cost=0.0005,
            output_cost=0.002
        )

        # Second call
        self.accumulator.add_usage(
            input_tokens=75,
            output_tokens=40,
            cache_read_tokens=30,
            cache_write_tokens=20,
            new_input_cost=0.0008,
            cache_read_cost=0.0002,
            cache_write_cost=0.0006,
            output_cost=0.0015
        )

        # Verify accumulation
        self.assertEqual(self.accumulator.total_new_input_tokens, 175)
        self.assertEqual(self.accumulator.total_output_tokens, 90)
        self.assertEqual(self.accumulator.total_cache_read_tokens, 55)
        self.assertEqual(self.accumulator.total_cache_write_tokens, 35)
        self.assertEqual(self.accumulator.total_new_input_cost, 0.0018)
        # Use assertAlmostEqual for floating point comparison
        self.assertAlmostEqual(self.accumulator.total_cache_read_cost, 0.0003, places=7)
        self.assertAlmostEqual(self.accumulator.total_cache_write_cost, 0.0011, places=7)
        self.assertEqual(self.accumulator.total_output_cost, 0.0035)
        self.assertEqual(self.accumulator.call_count, 2)

    def test_total_tokens_property(self):
        """Test that total_tokens correctly sums all token types."""
        self.accumulator.add_usage(
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=25,
            cache_write_tokens=15,
            new_input_cost=0.001,
            cache_read_cost=0.0001,
            cache_write_cost=0.0005,
            output_cost=0.002
        )

        expected_total = 100 + 50 + 25 + 15
        self.assertEqual(self.accumulator.total_tokens, expected_total)

    def test_total_input_cost_property(self):
        """Test that total_input_cost correctly sums input-related costs."""
        self.accumulator.add_usage(
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=25,
            cache_write_tokens=15,
            new_input_cost=0.001,
            cache_read_cost=0.0001,
            cache_write_cost=0.0005,
            output_cost=0.002
        )

        expected_input_cost = 0.001 + 0.0001 + 0.0005
        self.assertEqual(self.accumulator.total_input_cost, expected_input_cost)

    def test_total_cost_property(self):
        """Test that total_cost correctly sums all costs."""
        self.accumulator.add_usage(
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=25,
            cache_write_tokens=15,
            new_input_cost=0.001,
            cache_read_cost=0.0001,
            cache_write_cost=0.0005,
            output_cost=0.002
        )

        expected_total_cost = 0.001 + 0.0001 + 0.0005 + 0.002
        self.assertEqual(self.accumulator.total_cost, expected_total_cost)

    def test_cache_savings_with_cache(self):
        """Test cache savings calculation when cache is used."""
        self.accumulator.add_usage(
            input_tokens=80,  # new input tokens
            output_tokens=50,
            cache_read_tokens=20,  # cached tokens read
            cache_write_tokens=10,
            new_input_cost=0.008,  # Cost for new input: 0.008/80 = 0.0001 per token
            cache_read_cost=0.0004,  # Cost for cache read: 0.0004/20 = 0.00002 per token
            cache_write_cost=0.002,
            output_cost=0.003
        )

        # Cache savings = cached_tokens * (regular_cost_per_token - cache_cost_per_token)
        # regular_cost_per_token = 0.008/80 = 0.0001
        # cache_cost_per_token = 0.0004/20 = 0.00002
        # savings = 20 * (0.0001 - 0.00002) = 20 * 0.00008 = 0.0016
        expected_savings = 0.0016
        self.assertAlmostEqual(self.accumulator.cache_savings, expected_savings, places=7)

    def test_cache_savings_no_cache(self):
        """Test cache savings when no cache is used."""
        self.accumulator.add_usage(
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=0,  # No cache
            cache_write_tokens=10,
            new_input_cost=0.001,
            cache_read_cost=0.0,
            cache_write_cost=0.0005,
            output_cost=0.002
        )

        self.assertEqual(self.accumulator.cache_savings, 0.0)

    def test_cache_savings_percentage(self):
        """Test cache savings percentage calculation."""
        self.accumulator.add_usage(
            input_tokens=80,
            output_tokens=50,
            cache_read_tokens=20,
            cache_write_tokens=10,
            new_input_cost=0.008,
            cache_read_cost=0.0004,
            cache_write_cost=0.002,
            output_cost=0.003
        )

        # From previous test: cache_savings = 0.0016
        # total_input_cost = 0.008 + 0.0004 + 0.002 = 0.0104
        # total_without_cache = 0.0104 + 0.0016 = 0.012
        # percentage = (0.0016 / 0.012) * 100 = 13.333...%
        expected_percentage = (0.0016 / 0.012) * 100
        self.assertAlmostEqual(self.accumulator.cache_savings_percentage, expected_percentage, places=2)

    def test_reset(self):
        """Test that reset clears all accumulated values."""
        # Add some usage first
        self.accumulator.add_usage(
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=25,
            cache_write_tokens=15,
            new_input_cost=0.001,
            cache_read_cost=0.0001,
            cache_write_cost=0.0005,
            output_cost=0.002
        )

        # Verify values are set
        self.assertGreater(self.accumulator.total_tokens, 0)
        self.assertGreater(self.accumulator.call_count, 0)

        # Reset and verify all values are zero
        self.accumulator.reset()
        self.assertEqual(self.accumulator.total_new_input_tokens, 0)
        self.assertEqual(self.accumulator.total_output_tokens, 0)
        self.assertEqual(self.accumulator.total_cache_read_tokens, 0)
        self.assertEqual(self.accumulator.total_cache_write_tokens, 0)
        self.assertEqual(self.accumulator.total_new_input_cost, 0.0)
        self.assertEqual(self.accumulator.total_cache_read_cost, 0.0)
        self.assertEqual(self.accumulator.total_cache_write_cost, 0.0)
        self.assertEqual(self.accumulator.total_output_cost, 0.0)
        self.assertEqual(self.accumulator.call_count, 0)


class TestSmartFixLiteLlm(unittest.TestCase):
    """Test cases for SmartFixLiteLlm class."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        # Mock LiteLlm initialization to avoid dependencies
        with patch('litellm.completion'):
            self.extended_model = SmartFixLiteLlm(model="test-model")

    def test_initialization(self):
        """Test that SmartFixLiteLlm initializes correctly."""
        self.assertEqual(self.extended_model.model, "test-model")
        self.assertIsInstance(self.extended_model.cost_accumulator, TokenCostAccumulator)

    @patch('src.smartfix.extensions.smartfix_litellm.debug_log')
    def test_gather_accumulated_stats_dict(self, mock_debug_log):
        """Test statistics dictionary generation."""
        # Add some usage to the accumulator
        self.extended_model.cost_accumulator.add_usage(
            input_tokens=150,
            output_tokens=75,
            cache_read_tokens=50,
            cache_write_tokens=25,
            new_input_cost=0.0015,
            cache_read_cost=0.0001,
            cache_write_cost=0.0008,
            output_cost=0.003
        )

        stats = self.extended_model.gather_accumulated_stats_dict()

        # Verify the statistics are correctly gathered
        self.assertEqual(stats['call_count'], 1)
        self.assertEqual(stats['token_usage']['total_tokens'], 300)  # 150 + 75 + 50 + 25
        self.assertIn('cost_analysis', stats)
        self.assertIn('averages', stats)

    @patch('src.smartfix.extensions.smartfix_litellm.debug_log')
    def test_gather_accumulated_stats_json(self, mock_debug_log):
        """Test JSON statistics generation."""
        # Add some usage to the accumulator
        self.extended_model.cost_accumulator.add_usage(
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=25,
            cache_write_tokens=15,
            new_input_cost=0.001,
            cache_read_cost=0.0001,
            cache_write_cost=0.0005,
            output_cost=0.002
        )

        json_stats = self.extended_model.gather_accumulated_stats()

        # Verify it's valid JSON
        stats_dict = json.loads(json_stats)
        self.assertEqual(stats_dict['call_count'], 1)
        self.assertIn('token_usage', stats_dict)

    @patch('src.smartfix.extensions.smartfix_litellm.debug_log')
    def test_reset_accumulated_stats(self, mock_debug_log):
        """Test that reset clears accumulated statistics."""
        # Add some usage first
        self.extended_model.cost_accumulator.add_usage(
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=25,
            cache_write_tokens=15,
            new_input_cost=0.001,
            cache_read_cost=0.0001,
            cache_write_cost=0.0005,
            output_cost=0.002
        )

        # Verify stats exist
        self.assertGreater(self.extended_model.cost_accumulator.call_count, 0)

        # Reset and verify
        self.extended_model.reset_accumulated_stats()

        # Verify reset
        self.assertEqual(self.extended_model.cost_accumulator.call_count, 0)
        self.assertEqual(self.extended_model.cost_accumulator.total_tokens, 0)
        self.assertEqual(self.extended_model.cost_accumulator.total_cost, 0.0)
        mock_debug_log.assert_called_with("Accumulated statistics have been reset.")


class TestSmartFixLiteLlmIntegration(unittest.TestCase):
    """Integration tests for SmartFixLiteLlm functionality."""

    @patch('litellm.completion')
    @patch('src.smartfix.extensions.smartfix_litellm.debug_log')
    def test_cost_accumulator_integration(self, mock_debug_log, mock_completion):
        """Test that cost accumulator integrates properly with SmartFixLiteLlm."""
        # Create a real SmartFixLiteLlm instance
        model = SmartFixLiteLlm(model="test-integration-model")

        # Verify it has a cost accumulator
        self.assertIsInstance(model.cost_accumulator, TokenCostAccumulator)

        # Add some usage manually (simulating what would happen in real usage)
        model.cost_accumulator.add_usage(
            input_tokens=200,
            output_tokens=100,
            cache_read_tokens=75,
            cache_write_tokens=50,
            new_input_cost=0.002,
            cache_read_cost=0.00015,
            cache_write_cost=0.001,
            output_cost=0.004
        )

        # Test statistics gathering
        stats = model.gather_accumulated_stats_dict()
        self.assertEqual(stats['call_count'], 1)
        self.assertEqual(stats['token_usage']['total_tokens'], 425)  # 200 + 100 + 75 + 50

        # Test JSON export
        json_stats = model.gather_accumulated_stats()
        parsed_stats = json.loads(json_stats)
        self.assertEqual(parsed_stats['call_count'], 1)

        # Test reset functionality
        model.reset_accumulated_stats()
        self.assertEqual(model.cost_accumulator.call_count, 0)


if __name__ == '__main__':
    unittest.main()
