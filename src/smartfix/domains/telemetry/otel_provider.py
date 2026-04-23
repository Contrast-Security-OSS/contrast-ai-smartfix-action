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

Handles TracerProvider lifecycle for SmartFix.

Design notes:
- Enabled iff OTEL_EXPORTER_OTLP_ENDPOINT (or OTEL_EXPORTER_OTLP_TRACES_ENDPOINT) is set.
- OTLPSpanExporter() is constructed with explicit endpoint and headers parsed from env vars.
  This ensures the headers are used even when the action runs as a GitHub composite action,
  where step-level env vars may not propagate into all sub-steps automatically.
- Headers are parsed from OTEL_EXPORTER_OTLP_HEADERS (comma-separated key=value pairs).
- Header keys (not values) are logged to confirm auth headers are present.
- When disabled, the default SDK NoOpTracerProvider remains — all span calls are silent
  no-ops with no guards needed in callers.
- force_flush() called before shutdown() to flush the BatchSpanProcessor background thread
  before sys.exit() can kill it.
- trace.set_tracer_provider() is a one-time global; subsequent calls are silently ignored
  by the SDK. No SmartFix dependency installs a TracerProvider ahead of initialize_otel():
  ADK's OTel setup (maybe_set_otel_providers) is only called from the ADK CLI web server,
  not from the Runner API that SmartFix uses; LiteLLM's OTel integration requires explicit
  callback configuration. initialize_otel() is therefore always the first caller.
"""

import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from src.utils import log

_tracer_provider = None
_shutdown_called = False


def initialize_otel(config) -> None:
    """
    Initialise the OTel TracerProvider if an OTLP endpoint is configured.

    Reads OTEL_EXPORTER_OTLP_ENDPOINT (or the traces-specific variant). If neither
    is set, returns immediately leaving the SDK default NoOpTracerProvider in place.

    Args:
        config: Config object with VERSION, CONTRAST_ORG_ID, GITHUB_SERVER_URL,
                GITHUB_REPOSITORY attributes.
    """
    global _tracer_provider, _shutdown_called
    _shutdown_called = False

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

        # Parse headers explicitly from env so they're passed directly to the exporter.
        # This is necessary when running as a GitHub composite action where step-level
        # env vars (OTEL_EXPORTER_OTLP_HEADERS) may not propagate automatically.
        headers_raw = os.environ.get("OTEL_EXPORTER_OTLP_HEADERS", "")
        headers: dict[str, str] = {}
        if headers_raw:
            for part in headers_raw.split(","):
                if "=" in part:
                    k, v = part.split("=", 1)
                    headers[k.strip()] = v.strip()

        # When using OTEL_EXPORTER_OTLP_ENDPOINT (base URL), the SDK would normally append
        # /v1/traces. We replicate that here since we're passing the endpoint explicitly.
        # When using OTEL_EXPORTER_OTLP_TRACES_ENDPOINT, the value is already the full URL.
        exporter_endpoint = traces_endpoint if traces_endpoint else endpoint.rstrip("/") + "/v1/traces"
        exporter = OTLPSpanExporter(endpoint=exporter_endpoint, headers=headers if headers else None)
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _tracer_provider = provider
        header_keys = list(headers.keys()) if headers else []
        log(f"OTel telemetry enabled: exporting to {endpoint}, auth header keys: {header_keys}")

    except Exception as e:
        log(f"OTel initialisation failed, telemetry disabled: {e}", is_warning=True)


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
    Flush pending spans and shut down the TracerProvider.

    Calls force_flush() before shutdown() so the BatchSpanProcessor background
    thread has a chance to deliver the last batch before the process exits.
    Guards against double-invocation (called by both atexit and finally blocks).
    """
    global _shutdown_called
    if _shutdown_called:
        return
    _shutdown_called = True

    if _tracer_provider is None:
        return

    try:
        _tracer_provider.force_flush(timeout_millis=2000)
        _tracer_provider.shutdown()
    except Exception as e:
        log(f"OTel shutdown error (non-fatal): {e}", is_warning=True)
