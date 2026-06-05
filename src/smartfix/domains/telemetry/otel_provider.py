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
- Auth headers (Authorization, API-Key) are always derived from Contrast config credentials
  and are never overridable via environment variables. This keeps auth coupled to the Contrast
  service account and prevents accidental misconfiguration.
- Both OTLPSpanExporter and OTLPMetricExporter are constructed with explicit endpoint and
  headers passed directly. This ensures auth headers are used even when the action runs
  as a GitHub composite action, where step-level env vars may not propagate automatically.
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
from contextvars import ContextVar
from typing import Optional

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import (
    Counter,
    Histogram,
    MeterProvider,
    ObservableCounter,
    ObservableGauge,
    ObservableUpDownCounter,
    UpDownCounter,
)
from opentelemetry.sdk.metrics.export import AggregationTemporality, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

try:
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    _HTTPX_INSTRUMENTATION_AVAILABLE = True
except ImportError:
    _HTTPX_INSTRUMENTATION_AVAILABLE = False

from src.utils import log

_tracer_provider = None
_meter_provider = None
_shutdown_called = False

# Host of the most recent outbound HTTP request, captured by the httpx instrumentation
# request hook. Used to source the server.address attribute on the hand-emitted gen_ai.*
# metrics (the datalake's server_address column reads it from those metrics, and litellm
# does not expose the resolved endpoint on the response object). A ContextVar rather than a
# plain global so concurrent LLM calls in separate asyncio tasks (each with its own context
# copy) don't read each other's host. Callers clear_last_request_host() immediately before a
# request and read get_last_request_host() immediately after, so the value reflects only that
# call; defaults to None so the attribute is omitted when no request was observed.
_last_request_host: ContextVar[Optional[str]] = ContextVar("_last_request_host", default=None)

# Export metrics with DELTA aggregation temporality rather than the OTLP exporter's
# default of CUMULATIVE. The data platform team (datalake) standardised on delta: a
# cumulative series can be derived from deltas but not the other way around, and deltas
# are simpler to reason about per-run. This mirrors the SDK's standard "delta preference"
# (OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=DELTA): counters and histograms are
# delta, while up/down counters and gauges stay cumulative since deltas are meaningless
# for them. Set explicitly here rather than via the env var because this module passes
# exporter config directly, since step-level env vars may not propagate within the
# GitHub composite action environment (see the auth-header note above).
_DELTA_TEMPORALITY = {
    Counter: AggregationTemporality.DELTA,
    Histogram: AggregationTemporality.DELTA,
    ObservableCounter: AggregationTemporality.DELTA,
    UpDownCounter: AggregationTemporality.CUMULATIVE,
    ObservableUpDownCounter: AggregationTemporality.CUMULATIVE,
    ObservableGauge: AggregationTemporality.CUMULATIVE,
}


def _record_request_host(span, request) -> None:
    """httpx instrumentation request hook: record the resolved request host.

    `request` is the instrumentation's RequestInfo namedtuple
    (method, url, headers, stream, extensions); request.url is an httpx.URL whose
    .host is the server the client actually connected to. Stored in a ContextVar so
    record_llm_call_tokens()/record_llm_duration() can read it back as the gen_ai
    server.address attribute. Never raises into the HTTP path.
    """
    try:
        host = request.url.host
        if host:
            _last_request_host.set(host)
    except Exception:
        pass


async def _record_request_host_async(span, request) -> None:
    """Async variant of _record_request_host for httpx.AsyncClient.

    The httpx instrumentation only honours an async_request_hook that is a coroutine
    function, so this thin wrapper is registered for the async path (the one LiteLLM
    uses for acompletion).
    """
    _record_request_host(span, request)


def get_last_request_host() -> Optional[str]:
    """Return the host of the most recent outbound HTTP request in this context, or None.

    Intended to be called immediately after an LLM call so the value reflects that call's
    endpoint. Returns None when no request has been observed or instrumentation is disabled.
    """
    return _last_request_host.get()


def clear_last_request_host() -> None:
    """Reset the recorded request host to None.

    Call immediately before an LLM request so the subsequent get_last_request_host()
    reflects only that call. Without this, a host left over from an unrelated httpx call
    (Contrast API fetch, periodic telemetry export) could be read as the LLM's
    server.address if the LLM call short-circuits before issuing an HTTP request. Clearing
    up front makes that case degrade to None (attribute omitted) rather than a stale host.
    """
    _last_request_host.set(None)


def initialize_otel(config) -> None:
    """
    Initialise the OTel TracerProvider and MeterProvider if an OTLP endpoint is configured.

    Reads OTEL_EXPORTER_OTLP_ENDPOINT (or the traces-specific variant). If neither
    is set, returns immediately leaving the SDK default NoOpTracerProvider in place.

    Auth headers are always built from config.CONTRAST_AUTHORIZATION_KEY and
    config.CONTRAST_API_KEY — they are not read from any environment variable.

    Also sets OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT based on
    ENABLE_FULL_TELEMETRY so that instrumentation libraries (LiteLLM, ADK) do not
    attach prompt/completion content to spans unless the operator has opted in.
    Uses setdefault so an explicit env-var override always wins.

    Args:
        config: Config object with VERSION, CONTRAST_ORG_ID, GITHUB_SERVER_URL,
                GITHUB_REPOSITORY, CONTRAST_AUTHORIZATION_KEY, CONTRAST_API_KEY attributes.
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
            "contrast.org_id": config.CONTRAST_ORG_ID,
        })

        # Auth headers are always derived from Contrast credentials — not from any env var.
        # This keeps telemetry auth coupled to the Contrast service account and ensures
        # they propagate correctly within the GitHub composite action environment.
        headers = {
            "Authorization": config.CONTRAST_AUTHORIZATION_KEY,
            "API-Key": config.CONTRAST_API_KEY,
        }
        exporter_kwargs = {"headers": headers}

        # When using OTEL_EXPORTER_OTLP_ENDPOINT (base URL), append signal-specific paths.
        # When using OTEL_EXPORTER_OTLP_TRACES_ENDPOINT, use as-is (already the full URL).
        base = endpoint.rstrip("/")
        traces_url = traces_endpoint if traces_endpoint else base + "/v1/traces"
        # Derive the metrics base from the explicit base endpoint when available; otherwise
        # strip the /v1/traces signal path before appending /v1/metrics to avoid
        # constructing .../v1/traces/v1/metrics when only the traces endpoint is set.
        metrics_base = base_endpoint.rstrip("/") if base_endpoint else base.removesuffix("/v1/traces")
        metrics_url = metrics_base + "/v1/metrics"

        # --- Traces ---
        span_exporter = OTLPSpanExporter(endpoint=traces_url, **exporter_kwargs)
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
        trace.set_tracer_provider(tracer_provider)
        _tracer_provider = tracer_provider

        # --- Metrics ---
        metric_exporter = OTLPMetricExporter(
            endpoint=metrics_url, preferred_temporality=_DELTA_TEMPORALITY, **exporter_kwargs
        )
        reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=60000)
        meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
        metrics.set_meter_provider(meter_provider)
        _meter_provider = meter_provider

        # --- HTTP client auto-instrumentation ---
        # Instruments httpx (used by LiteLLM) to emit http.client.* metrics
        # (duration, request/response size) for every outbound LLM API call.
        # The request hooks additionally capture the resolved request host so callers
        # can stamp server.address onto the hand-emitted gen_ai.* metrics (see
        # _record_request_host). Both sync and async hooks are registered because LiteLLM
        # may use either httpx client depending on the code path.
        if _HTTPX_INSTRUMENTATION_AVAILABLE:
            HTTPXClientInstrumentor().instrument(
                request_hook=_record_request_host,
                async_request_hook=_record_request_host_async,
            )

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

    if _HTTPX_INSTRUMENTATION_AVAILABLE:
        try:
            HTTPXClientInstrumentor().uninstrument()
        except Exception:
            pass
