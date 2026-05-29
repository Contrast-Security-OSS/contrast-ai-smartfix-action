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

import asyncio
import unittest
import json
import os
from unittest.mock import patch, Mock, MagicMock, AsyncMock

# Test setup imports (path is set up by conftest.py)
from src.smartfix.extensions.smartfix_litellm import (
    SmartFixLiteLlm, TokenCostAccumulator, _derive_system, _extract_server_address,
)
from src.smartfix.domains.providers import CONTRAST_CLAUDE_SONNET_4_5


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


class TestDeriveSystem(unittest.TestCase):
    """Tests for the _derive_system() module-level function."""

    def test_contrast_model_returns_contrast(self):
        self.assertEqual(_derive_system("contrast/claude-3-7-sonnet"), "contrast")

    def test_contrast_claude_sonnet_4_5_returns_contrast(self):
        """Production Contrast LLM model string must report provider as 'contrast', not 'anthropic'."""
        self.assertEqual(_derive_system("contrast/claude-sonnet-4-5"), "contrast")

    def test_contrast_claude_sonnet_v2_model_id_returns_contrast(self):
        """v2 model id (bare Bedrock id, no contrast/ prefix) must still resolve to 'contrast'."""
        self.assertEqual(_derive_system(CONTRAST_CLAUDE_SONNET_4_5), "contrast")

    def test_anthropic_prefix_returns_anthropic(self):
        self.assertEqual(_derive_system("anthropic/claude-3-opus"), "anthropic")

    def test_claude_prefix_without_provider_returns_anthropic(self):
        self.assertEqual(_derive_system("claude-3-7-sonnet-20250219"), "anthropic")

    def test_bedrock_prefix_returns_aws_bedrock(self):
        self.assertEqual(_derive_system("bedrock/us.anthropic.claude-3-7-sonnet-20250219-v1:0"), "aws.bedrock")

    def test_gemini_prefix_returns_google(self):
        self.assertEqual(_derive_system("gemini/gemini-1.5-pro"), "google")

    def test_google_prefix_returns_google(self):
        self.assertEqual(_derive_system("google/gemini-2.0-flash"), "google")

    def test_azure_prefix_returns_azure(self):
        self.assertEqual(_derive_system("azure/gpt-4o"), "azure")

    def test_unknown_with_slash_returns_prefix(self):
        self.assertEqual(_derive_system("openai/gpt-4o"), "openai")

    def test_unknown_without_slash_returns_unknown(self):
        self.assertEqual(_derive_system("some-unknown-model"), "unknown")


class TestExtractServerAddress(unittest.TestCase):
    """Tests for _extract_server_address(), which sources the server.address metric attribute.

    The datalake's ai_token_usage / ai_operation_performance tables source server_address
    from the gen_ai.* metrics. We report the host of the endpoint SmartFix actually calls:
    an explicit per-call api_base, else ANTHROPIC_API_BASE (the Contrast LLM proxy / BYO
    Anthropic endpoint).
    """

    def setUp(self):
        self._saved = os.environ.get("ANTHROPIC_API_BASE")
        os.environ.pop("ANTHROPIC_API_BASE", None)

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("ANTHROPIC_API_BASE", None)
        else:
            os.environ["ANTHROPIC_API_BASE"] = self._saved

    def test_returns_host_from_explicit_api_base(self):
        self.assertEqual(
            _extract_server_address({"api_base": "https://api.anthropic.com/v1/messages"}),
            "api.anthropic.com",
        )

    def test_explicit_api_base_wins_over_env(self):
        os.environ["ANTHROPIC_API_BASE"] = "https://env.example.com"
        self.assertEqual(
            _extract_server_address({"api_base": "https://explicit.example.com/v1"}),
            "explicit.example.com",
        )

    def test_falls_back_to_anthropic_api_base_env(self):
        os.environ["ANTHROPIC_API_BASE"] = (
            "https://app.contrastsecurity.com/api/llm-proxy/v2/organizations/abc/anthropic"
        )
        self.assertEqual(_extract_server_address({}), "app.contrastsecurity.com")

    def test_strips_port_and_scheme_to_bare_host(self):
        os.environ["ANTHROPIC_API_BASE"] = "https://llm.contrastsecurity.com:8443/v1"
        self.assertEqual(_extract_server_address({}), "llm.contrastsecurity.com")

    def test_returns_none_when_no_endpoint_known(self):
        self.assertIsNone(_extract_server_address({}))


class TestGenAiMetricsServerAddress(unittest.TestCase):
    """server.address is attached to the gen_ai.* metrics when the endpoint is known."""

    def setUp(self):
        self._saved = os.environ.get("ANTHROPIC_API_BASE")
        os.environ.pop("ANTHROPIC_API_BASE", None)
        with patch('litellm.completion'):
            self.model = SmartFixLiteLlm(model="anthropic/claude-3-opus")

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("ANTHROPIC_API_BASE", None)
        else:
            os.environ["ANTHROPIC_API_BASE"] = self._saved

    def _make_mock_response(self):
        usage_cls = type("Usage", (), {
            "__bool__": lambda s: True,
            "prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150,
            "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
            "__dict__": {
                "prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150,
                "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
            },
        })
        usage = usage_cls()
        resp = Mock()
        resp.model = "claude-3-opus"
        resp.get = lambda key, default=None: usage if key == "usage" else default
        return resp

    def _run_and_capture_op_duration_attrs(self, completion_args):
        """Run a successful call and return the attrs passed to the operation.duration histogram."""
        self.model.llm_client = Mock()
        self.model.llm_client.acompletion = AsyncMock(return_value=self._make_mock_response())
        mock_hist = Mock()
        with patch('src.smartfix.extensions.smartfix_litellm.otel_provider.start_span'), \
                patch('src.smartfix.extensions.smartfix_litellm._get_operation_duration_histogram',
                      return_value=mock_hist), \
                patch('src.smartfix.extensions.smartfix_litellm._get_token_usage_histogram',
                      return_value=Mock()), \
                patch('src.smartfix.extensions.smartfix_litellm.smartfix_metrics'):
            asyncio.run(self.model._call_llm_with_retry(completion_args))
        mock_hist.record.assert_called_once()
        return mock_hist.record.call_args[0][1]

    @patch('src.smartfix.extensions.smartfix_litellm.debug_log')
    def test_server_address_attached_from_contrast_proxy_env(self, _mock_log):
        os.environ["ANTHROPIC_API_BASE"] = (
            "https://app.contrastsecurity.com/api/llm-proxy/v2/organizations/abc/anthropic"
        )
        attrs = self._run_and_capture_op_duration_attrs({"model": "anthropic/claude-3-opus"})
        self.assertEqual(attrs.get("server.address"), "app.contrastsecurity.com")

    @patch('src.smartfix.extensions.smartfix_litellm.debug_log')
    def test_server_address_omitted_when_endpoint_unknown(self, _mock_log):
        attrs = self._run_and_capture_op_duration_attrs({"model": "anthropic/claude-3-opus"})
        self.assertNotIn("server.address", attrs)


class TestLogCostAnalysisReturnValue(unittest.TestCase):
    """_log_cost_analysis() must return (input_tokens, output_tokens, cache_read, cache_write)."""

    def setUp(self):
        with patch('litellm.completion'):
            self.model = SmartFixLiteLlm(model="test-model")

    @patch('src.smartfix.extensions.smartfix_litellm.debug_log')
    def test_returns_token_tuple_from_dict_usage(self, _mock_log):
        """Returns correct 4-tuple when usage is a dict."""
        response = Mock()
        response.get = lambda key, default=None: {
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
                "cache_read_input_tokens": 20,
                "cache_creation_input_tokens": 10,
            }
        }.get(key, default)

        result = self.model._log_cost_analysis(response)

        self.assertEqual(result, (100, 50, 20, 10))

    @patch('src.smartfix.extensions.smartfix_litellm.debug_log')
    def test_returns_zeros_when_no_usage(self, _mock_log):
        """Returns (0, 0, 0, 0) when no usage data is present."""
        response = Mock()
        response.get = lambda key, default=None: default

        result = self.model._log_cost_analysis(response)

        self.assertEqual(result, (0, 0, 0, 0))


class TestCallLlmWithRetryOtelSpan(unittest.TestCase):
    """OTel span is created per attempt in _call_llm_with_retry()."""

    def setUp(self):
        with patch('litellm.completion'):
            self.model = SmartFixLiteLlm(model="anthropic/claude-3-opus")

    def _make_mock_response(self, input_tokens=100, output_tokens=50,
                            cache_read=0, cache_write=0, model_name="claude-3-opus"):
        """Build a minimal fake acompletion response."""
        usage = MagicMock()
        usage.__class__.__name__ = "Usage"
        # Make response.get("usage", {}) return the usage object
        resp = Mock()
        resp.model = model_name
        resp.get = lambda key, default=None: usage if key == "usage" else default

        usage.__bool__ = lambda self: True
        # Make isinstance(usage, dict) return False
        usage.__class__ = type("Usage", (), {
            "__bool__": lambda s: True,
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "cache_read_input_tokens": cache_read,
            "cache_creation_input_tokens": cache_write,
            "__dict__": {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "cache_read_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_write,
            }
        })
        return resp

    @patch('src.smartfix.extensions.smartfix_litellm.debug_log')
    def test_chat_span_is_created(self, _mock_log):
        """start_span('chat <model>') is called once for a successful call."""
        mock_response = self._make_mock_response()
        self.model.llm_client = Mock()
        self.model.llm_client.acompletion = AsyncMock(return_value=mock_response)

        span_names = []

        def mock_start_span(name, context=None):
            span_names.append(name)
            mock_span = Mock()
            mock_span_cm = MagicMock()
            mock_span_cm.__enter__ = Mock(return_value=mock_span)
            mock_span_cm.__exit__ = Mock(return_value=False)
            return mock_span_cm

        with patch('src.smartfix.domains.telemetry.otel_provider.start_span', side_effect=mock_start_span):
            asyncio.run(self.model._call_llm_with_retry({"model": "anthropic/claude-3-opus"}))

        self.assertEqual(span_names, ["chat anthropic/claude-3-opus"])

    @patch('src.smartfix.extensions.smartfix_litellm.debug_log')
    def test_span_has_request_attributes(self, _mock_log):
        """gen_ai.system, gen_ai.request.model, gen_ai.operation.name, contrast.smartfix.retry_attempt are set."""
        mock_response = self._make_mock_response()
        self.model.llm_client = Mock()
        self.model.llm_client.acompletion = AsyncMock(return_value=mock_response)

        captured_span = None

        def mock_start_span(name, context=None):
            nonlocal captured_span
            mock_span = Mock()
            captured_span = mock_span
            mock_span_cm = MagicMock()
            mock_span_cm.__enter__ = Mock(return_value=mock_span)
            mock_span_cm.__exit__ = Mock(return_value=False)
            return mock_span_cm

        with patch('src.smartfix.domains.telemetry.otel_provider.start_span', side_effect=mock_start_span):
            asyncio.run(self.model._call_llm_with_retry({"model": "anthropic/claude-3-opus"}))

        attrs = {call[0][0]: call[0][1] for call in captured_span.set_attribute.call_args_list}
        self.assertEqual(attrs.get("gen_ai.system"), "anthropic")
        self.assertEqual(attrs.get("gen_ai.request.model"), "anthropic/claude-3-opus")
        self.assertEqual(attrs.get("gen_ai.operation.name"), "chat")
        self.assertEqual(attrs.get("contrast.smartfix.retry_attempt"), 0)

    @patch('src.smartfix.extensions.smartfix_litellm.debug_log')
    def test_span_has_response_model_attribute(self, _mock_log):
        """gen_ai.response.model is set from the response object."""
        mock_response = self._make_mock_response(model_name="claude-3-opus-20240229")
        self.model.llm_client = Mock()
        self.model.llm_client.acompletion = AsyncMock(return_value=mock_response)

        captured_span = None

        def mock_start_span(name, context=None):
            nonlocal captured_span
            mock_span = Mock()
            captured_span = mock_span
            mock_span_cm = MagicMock()
            mock_span_cm.__enter__ = Mock(return_value=mock_span)
            mock_span_cm.__exit__ = Mock(return_value=False)
            return mock_span_cm

        with patch('src.smartfix.domains.telemetry.otel_provider.start_span', side_effect=mock_start_span):
            asyncio.run(self.model._call_llm_with_retry({"model": "anthropic/claude-3-opus"}))

        attrs = {call[0][0]: call[0][1] for call in captured_span.set_attribute.call_args_list}
        self.assertEqual(attrs.get("gen_ai.response.model"), "claude-3-opus-20240229")

    @patch('src.smartfix.extensions.smartfix_litellm.debug_log')
    @patch('src.smartfix.extensions.smartfix_litellm.log')
    def test_span_set_error_status_on_non_retryable_failure(self, _mock_log, _mock_debug):
        """Span gets ERROR status when a non-retryable exception is raised."""
        import litellm as _litellm

        non_retryable_err = _litellm.AuthenticationError(
            message="bad key", llm_provider="anthropic", model="claude-3-opus"
        )
        self.model.llm_client = Mock()
        self.model.llm_client.acompletion = AsyncMock(side_effect=non_retryable_err)

        captured_span = None

        def mock_start_span(name, context=None):
            nonlocal captured_span
            mock_span = Mock()
            captured_span = mock_span
            mock_span_cm = MagicMock()
            mock_span_cm.__enter__ = Mock(return_value=mock_span)
            mock_span_cm.__exit__ = Mock(return_value=False)
            return mock_span_cm

        with patch('src.smartfix.domains.telemetry.otel_provider.start_span', side_effect=mock_start_span):
            with self.assertRaises(Exception):
                asyncio.run(self.model._call_llm_with_retry({"model": "anthropic/claude-3-opus"}))

        captured_span.record_exception.assert_called_once()
        attrs = {call[0][0]: call[0][1] for call in captured_span.set_attribute.call_args_list}
        self.assertIn("error.type", attrs)


class TestGenerateContentAsyncDoesNotStream(unittest.TestCase):
    """Regression: SmartFixLiteLlm must not set stream on the completion call.

    The v2 Contrast LLM proxy returns HTTP 406 for streaming requests, so the
    Contrast call path must never pass stream=True (or any truthy stream value)
    into acompletion.  This test locks in the current non-streaming behaviour
    so a future refactor cannot silently regress it.
    """

    def setUp(self):
        with patch('litellm.completion'):
            self.model = SmartFixLiteLlm(model=CONTRAST_CLAUDE_SONNET_4_5)

    def _consume(self, gen):
        async def _drain():
            async for _ in gen:
                pass
        asyncio.run(_drain())

    @patch('google.adk.models.lite_llm._model_response_to_generate_content_response')
    @patch('src.smartfix.extensions.smartfix_litellm._get_completion_inputs')
    def test_completion_args_omit_stream_for_contrast_model(
        self, mock_inputs, mock_response_converter
    ):
        """generate_content_async must not insert 'stream' into completion_args."""
        # _get_completion_inputs returns (messages, tools, response_format, generation_params)
        mock_inputs.return_value = ([], None, None, None)
        mock_response_converter.return_value = Mock()

        # Capture completion_args via _call_llm_with_retry mock
        fake_response = Mock()
        fake_response.get = lambda key, default=None: default
        fake_response.model = CONTRAST_CLAUDE_SONNET_4_5
        self.model._call_llm_with_retry = AsyncMock(return_value=fake_response)

        # Skip helpers that touch llm_request internals
        self.model._maybe_append_user_content = Mock()
        self.model._ensure_system_message_for_contrast = Mock(return_value=[])
        self.model._apply_role_conversion_and_caching = Mock()
        # Provide concrete value for the parent-class attribute the method reads
        self.model._additional_args = {}

        self._consume(self.model.generate_content_async(Mock(), stream=False))

        self.model._call_llm_with_retry.assert_called_once()
        completion_args = self.model._call_llm_with_retry.call_args[0][0]
        self.assertNotIn(
            "stream", completion_args,
            "completion_args must not set 'stream'; v2 Contrast LLM proxy returns HTTP 406 on streaming"
        )


if __name__ == '__main__':
    unittest.main()
