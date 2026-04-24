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
OTel (OpenTelemetry) Provider Module

Handles TracerProvider and MeterProvider lifecycle for SmartFix.

Design notes:
- Enabled iff OTEL_EXPORTER_OTLP_ENDPOINT (or OTEL_EXPORTER_OTLP_TRACES_ENDPOINT) is set.
- Both OTLPSpanExporter and OTLPMetricExporter are constructed with explicit endpoint and
  headers parsed from env vars. This ensures auth headers are used even when the action runs
  as a GitHub composite action, where step-level env vars may not propagate automatically.
- Headers are parsed from OTEL_EXPORTER_OTLP_HEADERS (comma-separated key=value pairs).
- Header keys (not values) are logged to confirm auth headers are present.
- Traces export to <base_endpoint>/v1/traces, metrics to <base_endpoint>/v1/metrics.
- When disabled, the default SDK NoOpTracerProvider remains — all span and metric calls are
  silent no-ops with no guards needed in callers.
- force_flush() called before shutdown() to flush the BatchSpanProcessor background thread
  before sys.exit() can kill it.
- trace.set_tracer_provider() is a one-time global; subsequent calls are silently ignored
  by the SDK. No SmartFix dependency installs a TracerProvider ahead of initialize_otel():
  ADK's OTel setup (maybe_set_otel_providers) is only called from the ADK CLI web server,
  not from the Runner API that SmartFix uses; LiteLLM's OTel integration requires explicit
  callback configuration. initialize_otel() is therefore always the first caller.
"""

import os

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from src.utils import log

_tracer_provider = None
_meter_provider = None
_shutdown_called = False


def _parse_headers(headers_raw: str) -> dict:
    """Parse OTEL_EXPORTER_OTLP_HEADERS value (comma-separated key=value pairs) into a dict."""
    headers = {}
    if headers_raw:
        for part in headers_raw.split(","):
            if "=" in part:
                k, v = part.split("=", 1)
                headers[k.strip()] = v.strip()
    return headers


def initialize_otel(config) -> None:
    """
    Initialise the OTel TracerProvider and MeterProvider if an OTLP endpoint is configured.

    Reads OTEL_EXPORTER_OTLP_ENDPOINT (or the traces-specific variant). If neither
    is set, returns immediately leaving the SDK default NoOpTracerProvider in place.

    Also sets OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT based on
    ENABLE_FULL_TELEMETRY so that instrumentation libraries (LiteLLM, ADK) do not
    attach prompt/completion content to spans unless the operator has opted in.
    Uses setdefault so an explicit env-var override always wins.

    Args:
        config: Config object with VERSION, CONTRAST_ORG_ID, GITHUB_SERVER_URL,
                GITHUB_REPOSITORY attributes.
    """
    global _tracer_provider, _meter_provider, _shutdown_called
    _shutdown_called = False

    # Wire prompt/completion content capture to ENABLE_FULL_TELEMETRY.
    # Instrumentation libraries (LiteLLM, ADK) respect this env var — when false
    # they omit gen_ai.prompt / gen_ai.completion span attributes.
    os.environ.setdefault(
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT",
        "true" if config.ENABLE_FULL_TELEMETRY else "false"
    )

    base_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    traces_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
    endpoint = base_endpoint or traces_endpoint
    if not endpoint:
        log("OTel telemetry disabled: OTEL_EXPORTER_OTLP_ENDPOINT is not set")
        return

    try:
        resource = Resource.create({
            SERVICE_NAME: "smartfix",
            "service.version": config.VERSION,
            "vcs.repository.url.full": f"{config.GITHUB_SERVER_URL}/{config.GITHUB_REPOSITORY}",
            "vcs.repository.name": config.GITHUB_REPOSITORY.split("/")[-1],
            "vcs.owner.name": config.GITHUB_REPOSITORY.split("/")[0],
            "vcs.provider.name": "github",
        })

        # Parse headers explicitly from env so they're passed directly to the exporters.
        # This is necessary when running as a GitHub composite action where step-level
        # env vars (OTEL_EXPORTER_OTLP_HEADERS) may not propagate automatically.
        headers = _parse_headers(os.environ.get("OTEL_EXPORTER_OTLP_HEADERS", ""))
        exporter_kwargs = {"headers": headers} if headers else {}

        # When using OTEL_EXPORTER_OTLP_ENDPOINT (base URL), append signal-specific paths.
        # When using OTEL_EXPORTER_OTLP_TRACES_ENDPOINT, use as-is (already the full URL).
        base = endpoint.rstrip("/")
        traces_url = traces_endpoint if traces_endpoint else base + "/v1/traces"
        metrics_url = base + "/v1/metrics"

        # --- Traces ---
        span_exporter = OTLPSpanExporter(endpoint=traces_url, **exporter_kwargs)
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
        trace.set_tracer_provider(tracer_provider)
        _tracer_provider = tracer_provider

        # --- Metrics ---
        metric_exporter = OTLPMetricExporter(endpoint=metrics_url, **exporter_kwargs)
        reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=60000)
        meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
        metrics.set_meter_provider(meter_provider)
        _meter_provider = meter_provider

        header_keys = list(headers.keys()) if headers else []
        log(f"OTel telemetry enabled: exporting to {endpoint}, auth header keys: {header_keys}")

    except Exception as e:
        log(f"OTel initialisation failed, telemetry disabled: {e}", is_warning=True)


def get_meter(name: str):
    """
    Return an OTel Meter for the given instrumentation scope name.

    Always safe to call regardless of whether OTel is initialised — returns a
    no-op meter when the MeterProvider has not been set.

    Args:
        name: The instrumentation scope name (e.g. "smartfix.litellm").
    """
    return metrics.get_meter(name)


def start_span(name: str, context=None):
    """
    Return a context manager that starts a span with the given name.

    Always safe to call regardless of whether OTel is initialised — returns a
    no-op span when the TracerProvider has not been set.

    Args:
        name: The span name.
        context: Optional OTel context to use as the parent. When None the
                 ambient current context is used (standard behaviour). Pass an
                 explicitly captured context to pin the parent span regardless
                 of whatever spans may be active at call time.
    """
    return trace.get_tracer("smartfix").start_as_current_span(name, context=context)


def shutdown_otel() -> None:
    """
    Flush pending spans and metrics, then shut down both providers.

    Calls force_flush() before shutdown() so the BatchSpanProcessor background
    thread has a chance to deliver the last batch before the process exits.
    Guards against double-invocation (called by both atexit and finally blocks).
    """
    global _shutdown_called
    if _shutdown_called:
        return
    _shutdown_called = True

    if _tracer_provider is not None:
        try:
            _tracer_provider.force_flush(timeout_millis=2000)
            _tracer_provider.shutdown()
        except Exception as e:
            log(f"OTel trace shutdown error (non-fatal): {e}", is_warning=True)

    if _meter_provider is not None:
        try:
            _meter_provider.force_flush(timeout_millis=2000)
            _meter_provider.shutdown()
        except Exception as e:
            log(f"OTel metrics shutdown error (non-fatal): {e}", is_warning=True)
