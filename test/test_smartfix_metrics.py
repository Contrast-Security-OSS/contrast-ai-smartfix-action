#!/usr/bin/env python
# -
# #%L
# Contrast AI SmartFix
# %%
# Copyright (C) 2026 Contrast Security, Inc.
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
Unit tests for smartfix_metrics.py.

These tests verify that:
1. Metric instruments are lazily initialised (created on first call, not at import).
2. The correct instrument type and name are created for each metric.
3. Recording helpers call record()/add() with the right attributes.
4. Errors from the underlying instrument are suppressed (never propagated).
"""

import unittest
from unittest.mock import MagicMock, patch


class TestLazyInitialisation(unittest.TestCase):
    """Instruments must not be created until the first recording call."""

    def setUp(self):
        import src.smartfix.domains.telemetry.smartfix_metrics as m
        # Reset all lazy handles to None before each test.
        m._vulnerability_duration_histogram = None
        m._pr_count_counter = None
        m._tokens_total_counter = None
        m._cache_tokens_counter = None
        m._llm_duration_histogram = None
        m._llm_retries_counter = None

    def test_instruments_are_none_before_first_call(self):
        import src.smartfix.domains.telemetry.smartfix_metrics as m
        self.assertIsNone(m._vulnerability_duration_histogram)
        self.assertIsNone(m._pr_count_counter)
        self.assertIsNone(m._tokens_total_counter)
        self.assertIsNone(m._cache_tokens_counter)
        self.assertIsNone(m._llm_duration_histogram)
        self.assertIsNone(m._llm_retries_counter)

    def test_vulnerability_duration_histogram_created_on_first_call(self):
        import src.smartfix.domains.telemetry.smartfix_metrics as m
        mock_histogram = MagicMock()
        mock_meter = MagicMock()
        mock_meter.create_histogram.return_value = mock_histogram

        with patch("src.smartfix.domains.telemetry.smartfix_metrics.otel_provider") as mock_provider:
            mock_provider.get_meter.return_value = mock_meter
            m._vulnerability_duration_histogram = None
            m.record_vulnerability_duration(1.5, "success", "sql-injection", "java", "runtime")

        mock_meter.create_histogram.assert_called_once()
        call_kwargs = mock_meter.create_histogram.call_args
        self.assertIn("smartfix.vulnerability.duration", str(call_kwargs))

    def test_pr_count_counter_created_on_first_call(self):
        import src.smartfix.domains.telemetry.smartfix_metrics as m
        mock_counter = MagicMock()
        mock_meter = MagicMock()
        mock_meter.create_counter.return_value = mock_counter

        with patch("src.smartfix.domains.telemetry.smartfix_metrics.otel_provider") as mock_provider:
            mock_provider.get_meter.return_value = mock_meter
            m._pr_count_counter = None
            m.record_pr_attempt("success", "sql-injection", "smartfix")

        mock_meter.create_counter.assert_called()
        args = str(mock_meter.create_counter.call_args_list)
        self.assertIn("smartfix.pr.count", args)

    def test_llm_duration_histogram_created_on_first_call(self):
        import src.smartfix.domains.telemetry.smartfix_metrics as m
        mock_histogram = MagicMock()
        mock_meter = MagicMock()
        mock_meter.create_histogram.return_value = mock_histogram

        with patch("src.smartfix.domains.telemetry.smartfix_metrics.otel_provider") as mock_provider:
            mock_provider.get_meter.return_value = mock_meter
            m._llm_duration_histogram = None
            m.record_llm_duration(0.5, "contrast", "contrast/claude-sonnet-4-5")

        mock_meter.create_histogram.assert_called_once()
        self.assertIn("smartfix.llm.duration", str(mock_meter.create_histogram.call_args))

    def test_llm_retries_counter_created_on_first_call(self):
        import src.smartfix.domains.telemetry.smartfix_metrics as m
        mock_counter = MagicMock()
        mock_meter = MagicMock()
        mock_meter.create_counter.return_value = mock_counter

        with patch("src.smartfix.domains.telemetry.smartfix_metrics.otel_provider") as mock_provider:
            mock_provider.get_meter.return_value = mock_meter
            m._llm_retries_counter = None
            m.record_llm_retry("contrast/claude-sonnet-4-5", "RateLimitError")

        mock_meter.create_counter.assert_called()
        self.assertIn("smartfix.llm.retries", str(mock_meter.create_counter.call_args_list))


class TestRecordVulnerabilityDuration(unittest.TestCase):

    def setUp(self):
        import src.smartfix.domains.telemetry.smartfix_metrics as m
        self.mock_histogram = MagicMock()
        m._vulnerability_duration_histogram = self.mock_histogram

    def test_records_with_correct_attributes(self):
        import src.smartfix.domains.telemetry.smartfix_metrics as m
        m.record_vulnerability_duration(2.5, "success", "sql-injection", "java", "runtime")

        self.mock_histogram.record.assert_called_once_with(2.5, {
            "outcome": "success",
            "rule_name": "sql-injection",
            "language": "java",
            "source": "runtime",
        })

    def test_uses_unknown_for_missing_language(self):
        import src.smartfix.domains.telemetry.smartfix_metrics as m
        m.record_vulnerability_duration(1.0, "failure", "xss", None, "runtime")

        call_kwargs = self.mock_histogram.record.call_args
        self.assertEqual(call_kwargs[0][1]["language"], "unknown")

    def test_suppresses_instrument_errors(self):
        import src.smartfix.domains.telemetry.smartfix_metrics as m
        self.mock_histogram.record.side_effect = RuntimeError("otel broken")
        # Must not raise.
        m.record_vulnerability_duration(1.0, "success", "sql-injection", "java", "runtime")


class TestRecordPrAttempt(unittest.TestCase):

    def setUp(self):
        import src.smartfix.domains.telemetry.smartfix_metrics as m
        self.mock_counter = MagicMock()
        m._pr_count_counter = self.mock_counter

    def test_records_success(self):
        import src.smartfix.domains.telemetry.smartfix_metrics as m
        m.record_pr_attempt("success", "sql-injection", "smartfix")

        self.mock_counter.add.assert_called_once_with(1, {
            "outcome": "success",
            "rule_name": "sql-injection",
            "coding_agent": "smartfix",
        })

    def test_records_failure(self):
        import src.smartfix.domains.telemetry.smartfix_metrics as m
        m.record_pr_attempt("failure", "xss", "github_copilot")

        self.mock_counter.add.assert_called_once_with(1, {
            "outcome": "failure",
            "rule_name": "xss",
            "coding_agent": "github_copilot",
        })

    def test_suppresses_instrument_errors(self):
        import src.smartfix.domains.telemetry.smartfix_metrics as m
        self.mock_counter.add.side_effect = RuntimeError("otel broken")
        m.record_pr_attempt("success", "sql-injection", "smartfix")


class TestRecordLlmCallTokens(unittest.TestCase):

    def setUp(self):
        import src.smartfix.domains.telemetry.smartfix_metrics as m
        self.mock_total = MagicMock()
        self.mock_cache = MagicMock()
        m._tokens_total_counter = self.mock_total
        m._cache_tokens_counter = self.mock_cache

    def test_records_input_and_output(self):
        import src.smartfix.domains.telemetry.smartfix_metrics as m
        m.record_llm_call_tokens(100, 50, 0, 0, "contrast/claude-sonnet-4-5")

        calls = self.mock_total.add.call_args_list
        self.assertEqual(len(calls), 2)
        # Input call
        self.assertEqual(calls[0][0][0], 100)
        self.assertEqual(calls[0][0][1]["gen_ai.token.type"], "input")
        # Output call
        self.assertEqual(calls[1][0][0], 50)
        self.assertEqual(calls[1][0][1]["gen_ai.token.type"], "output")

    def test_includes_cache_tokens_in_input_total(self):
        import src.smartfix.domains.telemetry.smartfix_metrics as m
        # 50 new + 30 cache_read + 20 cache_write = 100 total input
        m.record_llm_call_tokens(50, 25, 30, 20, "bedrock/claude-3-7")

        input_call = self.mock_total.add.call_args_list[0]
        self.assertEqual(input_call[0][0], 100)  # 50 + 30 + 20

    def test_records_cache_read_and_write_separately(self):
        import src.smartfix.domains.telemetry.smartfix_metrics as m
        m.record_llm_call_tokens(50, 25, 30, 20, "bedrock/claude-3-7")

        cache_calls = self.mock_cache.add.call_args_list
        token_types = {c[0][1]["gen_ai.token.type"] for c in cache_calls}
        self.assertIn("read", token_types)
        self.assertIn("write", token_types)

    def test_skips_cache_counter_when_no_cache_tokens(self):
        import src.smartfix.domains.telemetry.smartfix_metrics as m
        m.record_llm_call_tokens(100, 50, 0, 0, "contrast/claude-sonnet-4-5")

        self.mock_cache.add.assert_not_called()

    def test_suppresses_instrument_errors(self):
        import src.smartfix.domains.telemetry.smartfix_metrics as m
        self.mock_total.add.side_effect = RuntimeError("otel broken")
        m.record_llm_call_tokens(100, 50, 0, 0, "contrast/claude-sonnet-4-5")


class TestRecordLlmDuration(unittest.TestCase):

    def setUp(self):
        import src.smartfix.domains.telemetry.smartfix_metrics as m
        self.mock_histogram = MagicMock()
        m._llm_duration_histogram = self.mock_histogram

    def test_records_with_provider_and_model(self):
        import src.smartfix.domains.telemetry.smartfix_metrics as m
        m.record_llm_duration(0.75, "contrast", "contrast/claude-sonnet-4-5")

        self.mock_histogram.record.assert_called_once_with(0.75, {
            "gen_ai.provider.name": "contrast",
            "gen_ai.request.model": "contrast/claude-sonnet-4-5",
        })

    def test_suppresses_instrument_errors(self):
        import src.smartfix.domains.telemetry.smartfix_metrics as m
        self.mock_histogram.record.side_effect = RuntimeError("otel broken")
        m.record_llm_duration(0.5, "contrast", "contrast/claude-sonnet-4-5")


class TestRecordLlmRetry(unittest.TestCase):

    def setUp(self):
        import src.smartfix.domains.telemetry.smartfix_metrics as m
        self.mock_counter = MagicMock()
        m._llm_retries_counter = self.mock_counter

    def test_records_with_model_and_error_type(self):
        import src.smartfix.domains.telemetry.smartfix_metrics as m
        m.record_llm_retry("contrast/claude-sonnet-4-5", "RateLimitError")

        self.mock_counter.add.assert_called_once_with(1, {
            "gen_ai.request.model": "contrast/claude-sonnet-4-5",
            "error.type": "RateLimitError",
        })

    def test_suppresses_instrument_errors(self):
        import src.smartfix.domains.telemetry.smartfix_metrics as m
        self.mock_counter.add.side_effect = RuntimeError("otel broken")
        m.record_llm_retry("contrast/claude-sonnet-4-5", "RateLimitError")


if __name__ == "__main__":
    unittest.main()
