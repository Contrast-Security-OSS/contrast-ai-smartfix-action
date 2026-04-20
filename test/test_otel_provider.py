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

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

import src.smartfix.domains.telemetry.otel_provider as otel_provider


def _config(**kwargs):
    defaults = dict(
        VERSION="v1.0.11",
        CONTRAST_ORG_ID="test-org",
        GITHUB_SERVER_URL="https://github.com",
        GITHUB_REPOSITORY="Contrast-Security-OSS/contrast-ai-smartfix-action",
        GITHUB_RUN_ID="12345678",
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestOtelProvider(unittest.TestCase):

    def setUp(self):
        # Reset module-level state.
        otel_provider._tracer_provider = None
        otel_provider._shutdown_called = False
        # Clear any OTel-related env vars set in previous tests.
        for var in ("OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"):
            os.environ.pop(var, None)
        # Reset global tracer provider to a clean no-op SDK provider.
        # We use a bare TracerProvider (no exporters) so spans are valid objects
        # but nothing is exported — clean slate for each test.
        trace.set_tracer_provider(TracerProvider())

    def tearDown(self):
        # Reset global provider so the real SDK TracerProvider installed by a test
        # does not bleed into subsequent tests.
        trace.set_tracer_provider(TracerProvider())
        otel_provider._tracer_provider = None
        otel_provider._shutdown_called = False

    # --- initialize_otel ---

    @patch("src.smartfix.domains.telemetry.otel_provider.OTLPSpanExporter")
    def test_initialize_sets_tracer_provider_when_endpoint_present(self, mock_exporter_cls):
        """initialize_otel() creates a real TracerProvider when endpoint env var is set."""
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "http://localhost:4318"
        mock_exporter_cls.return_value = MagicMock()

        otel_provider.initialize_otel(_config())

        self.assertIsNotNone(otel_provider._tracer_provider)

    @patch("src.smartfix.domains.telemetry.otel_provider.OTLPSpanExporter")
    def test_initialize_sets_correct_resource_attributes(self, mock_exporter_cls):
        """Resource attributes on the TracerProvider match config values."""
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "http://localhost:4318"
        mock_exporter_cls.return_value = MagicMock()
        cfg = _config()

        otel_provider.initialize_otel(cfg)

        attrs = otel_provider._tracer_provider.resource.attributes
        self.assertEqual(attrs["service.name"], "smartfix")
        self.assertEqual(attrs["service.version"], cfg.VERSION)
        self.assertEqual(
            attrs["vcs.repository.url.full"],
            f"{cfg.GITHUB_SERVER_URL}/{cfg.GITHUB_REPOSITORY}",
        )
        self.assertEqual(attrs["vcs.repository.name"], "contrast-ai-smartfix-action")
        self.assertEqual(attrs["vcs.owner.name"], "Contrast-Security-OSS")
        self.assertEqual(attrs["vcs.provider.name"], "github")

    @patch("src.smartfix.domains.telemetry.otel_provider.OTLPSpanExporter")
    def test_initialize_also_accepts_traces_specific_endpoint_var(self, mock_exporter_cls):
        """OTEL_EXPORTER_OTLP_TRACES_ENDPOINT also enables OTel."""
        os.environ["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] = "http://localhost:4318/v1/traces"
        mock_exporter_cls.return_value = MagicMock()

        otel_provider.initialize_otel(_config())

        self.assertIsNotNone(otel_provider._tracer_provider)

    def test_initialize_is_noop_when_endpoint_absent(self):
        """initialize_otel() does nothing when OTEL_EXPORTER_OTLP_ENDPOINT is not set."""
        otel_provider.initialize_otel(_config())

        # Module variable stays None — no real provider was installed.
        self.assertIsNone(otel_provider._tracer_provider)

    def test_noop_tracer_provider_still_yields_usable_tracer(self):
        """Without init, trace.get_tracer() returns a no-op tracer that works silently."""
        otel_provider.initialize_otel(_config())  # endpoint absent → no-op

        # start_span() must not raise; must be usable as a context manager.
        with otel_provider.start_span("test-span") as span:
            # The span may be a NonRecordingSpan (no-op) but must be non-None.
            self.assertIsNotNone(span)

    @patch("src.smartfix.domains.telemetry.otel_provider.OTLPSpanExporter")
    @patch("src.smartfix.domains.telemetry.otel_provider.log")
    def test_initialize_logs_warning_and_does_not_crash_on_setup_failure(
        self, mock_log, mock_exporter_cls
    ):
        """If TracerProvider setup raises, a warning is logged and no exception propagates."""
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "http://localhost:4318"
        mock_exporter_cls.side_effect = RuntimeError("simulated exporter failure")

        # Should not raise.
        otel_provider.initialize_otel(_config())

        # _tracer_provider must remain None (setup failed before set_tracer_provider).
        self.assertIsNone(otel_provider._tracer_provider)
        # log() must have been called with is_warning=True.
        called_with_warning = any(
            call.kwargs.get("is_warning") for call in mock_log.call_args_list
        )
        self.assertTrue(called_with_warning, "Expected log(is_warning=True) on setup failure")

    # --- shutdown_otel ---

    def test_shutdown_is_safe_without_provider(self):
        """shutdown_otel() does nothing gracefully when no provider is active."""
        # _tracer_provider is None (set in setUp).
        otel_provider.shutdown_otel()  # must not raise

    def test_shutdown_calls_force_flush_then_shutdown(self):
        """shutdown_otel() calls force_flush then shutdown on the provider."""
        mock_provider = MagicMock()
        otel_provider._tracer_provider = mock_provider

        otel_provider.shutdown_otel()

        mock_provider.force_flush.assert_called_once_with(timeout_millis=2000)
        mock_provider.shutdown.assert_called_once()

    def test_double_shutdown_is_safe(self):
        """Calling shutdown_otel() twice does not double-flush or raise."""
        mock_provider = MagicMock()
        otel_provider._tracer_provider = mock_provider

        otel_provider.shutdown_otel()
        otel_provider.shutdown_otel()

        # Provider methods called exactly once.
        mock_provider.force_flush.assert_called_once()
        mock_provider.shutdown.assert_called_once()

    # --- start_span ---

    @patch("src.smartfix.domains.telemetry.otel_provider.OTLPSpanExporter")
    def test_start_span_returns_context_manager_when_provider_active(self, mock_exporter_cls):
        """start_span() returns a usable context manager when OTel is initialised."""
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "http://localhost:4318"
        mock_exporter_cls.return_value = MagicMock()
        otel_provider.initialize_otel(_config())

        with otel_provider.start_span("my-span") as span:
            self.assertIsNotNone(span)

    def test_start_span_returns_context_manager_when_provider_inactive(self):
        """start_span() returns a usable context manager even without initialisation."""
        with otel_provider.start_span("my-span") as span:
            self.assertIsNotNone(span)


if __name__ == "__main__":
    unittest.main()
