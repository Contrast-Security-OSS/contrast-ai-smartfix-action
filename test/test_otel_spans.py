#!/usr/bin/env python3
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
Integration tests for OTel span structure (SS-90).

Uses InMemorySpanExporter to capture real spans and verify names, attributes,
and parent-child relationships — no network calls required.

The OTel SDK uses a Once pattern for set_tracer_provider(), so we cannot swap
the global TracerProvider between tests. Instead, each test class patches
src.otel_provider.start_span to forward calls to a private tracer backed by
an InMemorySpanExporter.  This preserves real span creation, context propagation,
and parent-child relationships without touching the global SDK state.

Span hierarchy:
  smartfix-run (root)
    fix-vulnerability (one per vulnerability)
      chat {model}  (one per LLM attempt inside _call_llm_with_retry)
"""

import asyncio
import unittest
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_span_recorder():
    """
    Return (exporter, patch_ctx) where patch_ctx is a context manager that patches
    src.otel_provider.start_span to use a private InMemorySpanExporter-backed tracer.

    Usage::

        exporter, patch_ctx = _make_span_recorder()
        with patch_ctx:
            with otel_provider.start_span("foo") as s:
                s.set_attribute("k", "v")
        spans = exporter.get_finished_spans()
    """
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("smartfix")

    patch_ctx = patch(
        "src.otel_provider.start_span",
        side_effect=lambda name: tracer.start_as_current_span(name),
    )
    return exporter, patch_ctx


def _spans_named(exporter, name):
    return [s for s in exporter.get_finished_spans() if s.name == name]


# ---------------------------------------------------------------------------
# TestSmartFixRunSpan — root span attributes
# ---------------------------------------------------------------------------

class TestSmartFixRunSpan(unittest.TestCase):
    """Verify attributes emitted on the top-level smartfix-run span."""

    def setUp(self):
        self.exporter, self.patch_ctx = _make_span_recorder()
        self.patcher = self.patch_ctx.__enter__()

    def tearDown(self):
        self.patch_ctx.__exit__(None, None, None)

    def _emit_run_span(self, session_id="run-99999", vuln_count=2):
        import src.otel_provider as otel_provider
        with otel_provider.start_span("smartfix-run") as span:
            span.set_attribute("session.id", session_id)
            span.set_attribute("contrast.smartfix.vulnerabilities_total", vuln_count)

    def test_smartfix_run_span_has_session_id(self):
        self._emit_run_span(session_id="run-12345")
        spans = _spans_named(self.exporter, "smartfix-run")
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].attributes["session.id"], "run-12345")

    def test_smartfix_run_span_has_vulnerabilities_total(self):
        self._emit_run_span(vuln_count=7)
        spans = _spans_named(self.exporter, "smartfix-run")
        self.assertEqual(spans[0].attributes["contrast.smartfix.vulnerabilities_total"], 7)

    def test_smartfix_run_span_does_not_have_files_modified(self):
        """files_modified belongs on fix-vulnerability, not on smartfix-run."""
        self._emit_run_span()
        spans = _spans_named(self.exporter, "smartfix-run")
        self.assertNotIn("contrast.smartfix.files_modified", spans[0].attributes)

    def test_smartfix_run_span_does_not_have_pr_created(self):
        """pr_created belongs on fix-vulnerability, not on smartfix-run."""
        self._emit_run_span()
        spans = _spans_named(self.exporter, "smartfix-run")
        self.assertNotIn("contrast.smartfix.pr_created", spans[0].attributes)

    def test_smartfix_run_span_does_not_have_pr_url(self):
        """pr_url belongs on fix-vulnerability, not on smartfix-run."""
        self._emit_run_span()
        spans = _spans_named(self.exporter, "smartfix-run")
        self.assertNotIn("contrast.smartfix.pr_url", spans[0].attributes)


# ---------------------------------------------------------------------------
# TestFixVulnerabilitySpan — operation span attributes
# ---------------------------------------------------------------------------

class TestFixVulnerabilitySpan(unittest.TestCase):
    """Verify attributes emitted on fix-vulnerability operation spans."""

    def setUp(self):
        self.exporter, self.patch_ctx = _make_span_recorder()
        self.patch_ctx.__enter__()

    def tearDown(self):
        self.patch_ctx.__exit__(None, None, None)

    def _emit(self, **overrides):
        import src.otel_provider as otel_provider
        attrs = dict(
            fingerprint="fp-abc123",
            source="runtime",
            rule_id="sql-injection",
            coding_agent="smartfix",
            language="java",
            fix_applied=True,
            files_modified=2,
            pr_created=True,
            pr_url="https://github.com/org/repo/pull/42",
        )
        attrs.update(overrides)
        with otel_provider.start_span("fix-vulnerability") as span:
            span.set_attribute("contrast.finding.fingerprint", attrs["fingerprint"])
            span.set_attribute("contrast.finding.source", attrs["source"])
            span.set_attribute("contrast.finding.rule_id", attrs["rule_id"])
            span.set_attribute("contrast.smartfix.coding_agent", attrs["coding_agent"])
            span.set_attribute("contrast.finding.language", attrs["language"])
            span.set_attribute("contrast.smartfix.fix_applied", attrs["fix_applied"])
            span.set_attribute("contrast.smartfix.files_modified", attrs["files_modified"])
            span.set_attribute("contrast.smartfix.pr_created", attrs["pr_created"])
            if attrs.get("pr_url"):
                span.set_attribute("contrast.smartfix.pr_url", attrs["pr_url"])

    def _span(self):
        return _spans_named(self.exporter, "fix-vulnerability")[0]

    def test_has_finding_fingerprint(self):
        self._emit(fingerprint="fp-xyz")
        self.assertEqual(self._span().attributes["contrast.finding.fingerprint"], "fp-xyz")

    def test_has_finding_source_runtime(self):
        self._emit()
        self.assertEqual(self._span().attributes["contrast.finding.source"], "runtime")

    def test_has_finding_rule_id(self):
        self._emit(rule_id="xss")
        self.assertEqual(self._span().attributes["contrast.finding.rule_id"], "xss")

    def test_has_coding_agent(self):
        self._emit(coding_agent="smartfix")
        self.assertEqual(self._span().attributes["contrast.smartfix.coding_agent"], "smartfix")

    def test_has_finding_language(self):
        self._emit(language="python")
        self.assertEqual(self._span().attributes["contrast.finding.language"], "python")

    def test_has_fix_applied(self):
        self._emit(fix_applied=True)
        self.assertTrue(self._span().attributes["contrast.smartfix.fix_applied"])

    def test_has_files_modified(self):
        self._emit(files_modified=4)
        self.assertEqual(self._span().attributes["contrast.smartfix.files_modified"], 4)

    def test_has_pr_created(self):
        self._emit(pr_created=True)
        self.assertTrue(self._span().attributes["contrast.smartfix.pr_created"])

    def test_has_pr_url(self):
        self._emit(pr_url="https://github.com/org/repo/pull/99")
        self.assertEqual(
            self._span().attributes["contrast.smartfix.pr_url"],
            "https://github.com/org/repo/pull/99",
        )

    def test_pr_url_absent_when_no_pr_created(self):
        """pr_url should not be set when no PR was created."""
        self._emit(pr_url=None)
        self.assertNotIn("contrast.smartfix.pr_url", self._span().attributes)


# ---------------------------------------------------------------------------
# TestLlmCallSpan — chat span attributes and parent-child relationship
# ---------------------------------------------------------------------------

class TestLlmCallSpan(unittest.TestCase):
    """Verify LLM call span structure, gen_ai.* attributes, and parent-child nesting."""

    def setUp(self):
        self.exporter, self.patch_ctx = _make_span_recorder()
        self.patch_ctx.__enter__()

    def tearDown(self):
        self.patch_ctx.__exit__(None, None, None)

    def test_llm_span_name_follows_chat_model_format(self):
        """Span names are 'chat {model}'."""
        import src.otel_provider as otel_provider
        model = "contrast/claude-sonnet-4-5"
        with otel_provider.start_span(f"chat {model}") as span:
            span.set_attribute("gen_ai.operation.name", "chat")

        self.assertEqual(len(_spans_named(self.exporter, f"chat {model}")), 1)

    def test_llm_span_has_gen_ai_system(self):
        import src.otel_provider as otel_provider
        model = "anthropic/claude-3-opus"
        with otel_provider.start_span(f"chat {model}") as span:
            span.set_attribute("gen_ai.system", "anthropic")
            span.set_attribute("gen_ai.request.model", model)
            span.set_attribute("gen_ai.operation.name", "chat")

        spans = _spans_named(self.exporter, f"chat {model}")
        self.assertEqual(spans[0].attributes["gen_ai.system"], "anthropic")

    def test_llm_span_has_gen_ai_request_model(self):
        import src.otel_provider as otel_provider
        model = "bedrock/anthropic.claude-3"
        with otel_provider.start_span(f"chat {model}") as span:
            span.set_attribute("gen_ai.system", "aws.bedrock")
            span.set_attribute("gen_ai.request.model", model)
            span.set_attribute("gen_ai.operation.name", "chat")

        spans = _spans_named(self.exporter, f"chat {model}")
        self.assertEqual(spans[0].attributes["gen_ai.request.model"], model)

    def test_llm_span_has_gen_ai_operation_name_chat(self):
        import src.otel_provider as otel_provider
        model = "gemini/gemini-pro"
        with otel_provider.start_span(f"chat {model}") as span:
            span.set_attribute("gen_ai.operation.name", "chat")
            span.set_attribute("gen_ai.request.model", model)

        spans = _spans_named(self.exporter, f"chat {model}")
        self.assertEqual(spans[0].attributes["gen_ai.operation.name"], "chat")

    def test_llm_span_has_gen_ai_retry_attempt(self):
        import src.otel_provider as otel_provider
        model = "test-retry-model"
        with otel_provider.start_span(f"chat {model}") as span:
            span.set_attribute("gen_ai.retry.attempt", 0)

        spans = _spans_named(self.exporter, f"chat {model}")
        self.assertEqual(spans[0].attributes["gen_ai.retry.attempt"], 0)

    def test_llm_span_has_usage_input_and_output_tokens(self):
        import src.otel_provider as otel_provider
        model = "contrast/claude-sonnet-4-5"
        with otel_provider.start_span(f"chat {model}") as span:
            span.set_attribute("gen_ai.usage.input_tokens", 120)
            span.set_attribute("gen_ai.usage.output_tokens", 60)
            span.set_attribute("gen_ai.response.model", model)

        spans = _spans_named(self.exporter, f"chat {model}")
        self.assertEqual(spans[0].attributes["gen_ai.usage.input_tokens"], 120)
        self.assertEqual(spans[0].attributes["gen_ai.usage.output_tokens"], 60)

    def test_llm_span_has_gen_ai_response_model(self):
        import src.otel_provider as otel_provider
        model = "contrast/claude-sonnet-4-5"
        with otel_provider.start_span(f"chat {model}") as span:
            span.set_attribute("gen_ai.response.model", model)

        spans = _spans_named(self.exporter, f"chat {model}")
        self.assertEqual(spans[0].attributes["gen_ai.response.model"], model)

    def test_llm_span_is_child_of_fix_vulnerability_span(self):
        """'chat model' span must be nested inside a fix-vulnerability span."""
        import src.otel_provider as otel_provider
        with otel_provider.start_span("fix-vulnerability") as op_span:
            op_span.set_attribute("contrast.finding.fingerprint", "fp-parent")
            with otel_provider.start_span("chat parent-test") as llm_span:
                llm_span.set_attribute("gen_ai.operation.name", "chat")

        finished = self.exporter.get_finished_spans()
        op_spans = [s for s in finished if s.name == "fix-vulnerability"]
        llm_spans = [s for s in finished if s.name == "chat parent-test"]

        self.assertEqual(len(op_spans), 1)
        self.assertEqual(len(llm_spans), 1)
        self.assertIsNotNone(llm_spans[0].parent)
        self.assertEqual(llm_spans[0].parent.span_id, op_spans[0].context.span_id)

    def test_call_llm_with_retry_creates_child_span_of_operation_span(self):
        """_call_llm_with_retry() emits a 'chat model' span nested under the active span."""
        import src.otel_provider as otel_provider
        from src.smartfix.extensions.smartfix_litellm import SmartFixLiteLlm

        mock_instance = MagicMock(spec=SmartFixLiteLlm)
        mock_instance._max_retries = 1
        mock_instance._initial_retry_delay = 0
        mock_instance._retry_multiplier = 2
        mock_instance._is_retryable_exception = lambda e: False
        mock_instance._log_cost_analysis.return_value = (10, 5, 0, 0)
        mock_instance.llm_client = MagicMock()

        mock_response = MagicMock()
        mock_response.model = "test-model"
        mock_instance.llm_client.acompletion = AsyncMock(return_value=mock_response)

        loop = asyncio.new_event_loop()
        try:
            with otel_provider.start_span("fix-vulnerability") as op_span:
                op_span.set_attribute("contrast.finding.fingerprint", "fp-child-test")
                loop.run_until_complete(
                    SmartFixLiteLlm._call_llm_with_retry(mock_instance, {"model": "test-model"})
                )
        finally:
            loop.close()

        finished = self.exporter.get_finished_spans()
        op_spans = [s for s in finished if s.name == "fix-vulnerability"]
        llm_spans = [s for s in finished if s.name == "chat test-model"]

        self.assertEqual(len(op_spans), 1, "Expected one fix-vulnerability span")
        self.assertEqual(len(llm_spans), 1, "Expected one chat test-model span")
        self.assertIsNotNone(llm_spans[0].parent)
        self.assertEqual(
            llm_spans[0].parent.span_id,
            op_spans[0].context.span_id,
            "chat span must be a child of fix-vulnerability span",
        )

    def test_call_llm_with_retry_sets_usage_attributes_from_log_cost_analysis(self):
        """Token counts from _log_cost_analysis() are set on the LLM span."""
        from src.smartfix.extensions.smartfix_litellm import SmartFixLiteLlm

        mock_instance = MagicMock(spec=SmartFixLiteLlm)
        mock_instance._max_retries = 1
        mock_instance._initial_retry_delay = 0
        mock_instance._retry_multiplier = 2
        mock_instance._is_retryable_exception = lambda e: False
        mock_instance._log_cost_analysis.return_value = (200, 80, 0, 0)
        mock_instance.llm_client = MagicMock()

        mock_response = MagicMock()
        mock_response.model = "usage-model"
        mock_instance.llm_client.acompletion = AsyncMock(return_value=mock_response)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(
                SmartFixLiteLlm._call_llm_with_retry(mock_instance, {"model": "usage-model"})
            )
        finally:
            loop.close()

        llm_spans = _spans_named(self.exporter, "chat usage-model")
        self.assertEqual(len(llm_spans), 1)
        self.assertEqual(llm_spans[0].attributes["gen_ai.usage.input_tokens"], 200)
        self.assertEqual(llm_spans[0].attributes["gen_ai.usage.output_tokens"], 80)


if __name__ == "__main__":
    unittest.main()
