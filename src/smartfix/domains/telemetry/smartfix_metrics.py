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
SmartFix domain-specific OTel metrics.

All instruments are lazily initialised so that get_meter() is always called
after initialize_otel() has installed the real MeterProvider.  Module-level
creation would run before initialize_otel(), yielding a no-op meter whose
record()/add() calls are silently discarded.

Metric catalogue
----------------
Per-LLM-call (emitted from smartfix_litellm.py):
  smartfix.llm.duration   histogram(s)  per-call latency
  smartfix.llm.retries    counter       retry events
  smartfix.tokens.total   counter       input + output tokens
  smartfix.cache.tokens   counter       cache-read + cache-write tokens

Per-vulnerability (emitted from main.py):
  smartfix.vulnerability.duration  histogram(s)  end-to-end fix latency
  smartfix.pr.count                counter       PR creation attempts
"""

from src.smartfix.domains.telemetry import otel_provider

_METER_NAME = "smartfix"

# --- Lazy instrument handles ---
_vulnerability_duration_histogram = None
_pr_count_counter = None
_tokens_total_counter = None
_cache_tokens_counter = None
_llm_duration_histogram = None
_llm_retries_counter = None


# ---------------------------------------------------------------------------
# Lazy getters
# ---------------------------------------------------------------------------

def _get_vulnerability_duration_histogram():
    global _vulnerability_duration_histogram
    if _vulnerability_duration_histogram is None:
        _vulnerability_duration_histogram = otel_provider.get_meter(_METER_NAME).create_histogram(
            name="smartfix.vulnerability.duration",
            unit="s",
            description="End-to-end time to process each vulnerability fix attempt.",
        )
    return _vulnerability_duration_histogram


def _get_pr_count_counter():
    global _pr_count_counter
    if _pr_count_counter is None:
        _pr_count_counter = otel_provider.get_meter(_METER_NAME).create_counter(
            name="smartfix.pr.count",
            unit="{pr}",
            description="Number of PR creation attempts.",
        )
    return _pr_count_counter


def _get_tokens_total_counter():
    global _tokens_total_counter
    if _tokens_total_counter is None:
        _tokens_total_counter = otel_provider.get_meter(_METER_NAME).create_counter(
            name="smartfix.tokens.total",
            unit="{token}",
            description="Cumulative LLM token usage by type.",
        )
    return _tokens_total_counter


def _get_cache_tokens_counter():
    global _cache_tokens_counter
    if _cache_tokens_counter is None:
        _cache_tokens_counter = otel_provider.get_meter(_METER_NAME).create_counter(
            name="smartfix.cache.tokens",
            unit="{token}",
            description="Cumulative prompt-cache token usage by type.",
        )
    return _cache_tokens_counter


def _get_llm_duration_histogram():
    global _llm_duration_histogram
    if _llm_duration_histogram is None:
        _llm_duration_histogram = otel_provider.get_meter(_METER_NAME).create_histogram(
            name="smartfix.llm.duration",
            unit="s",
            description="Per-LLM-call round-trip latency.",
        )
    return _llm_duration_histogram


def _get_llm_retries_counter():
    global _llm_retries_counter
    if _llm_retries_counter is None:
        _llm_retries_counter = otel_provider.get_meter(_METER_NAME).create_counter(
            name="smartfix.llm.retries",
            unit="{retry}",
            description="Number of LLM call retries.",
        )
    return _llm_retries_counter


# ---------------------------------------------------------------------------
# Public recording helpers
# ---------------------------------------------------------------------------

def record_vulnerability_duration(
        elapsed_s: float, outcome: str, rule_name: str, language: str, source: str) -> None:
    """Record end-to-end vulnerability fix duration.

    Args:
        elapsed_s: Wall-clock seconds for the fix attempt.
        outcome: "success", "failure", "no_code_changed", or "pr_failed".
        rule_name: Contrast rule name (e.g. "sql-injection").
        language: Programming language detected for this app.
        source: Finding source (e.g. "runtime").
    """
    try:
        _get_vulnerability_duration_histogram().record(elapsed_s, {
            "outcome": outcome,
            "rule_name": rule_name,
            "language": language or "unknown",
            "source": source,
        })
    except Exception:
        pass


def record_pr_attempt(outcome: str, rule_name: str, coding_agent: str) -> None:
    """Record a PR creation attempt.

    Args:
        outcome: "success" or "failure".
        rule_name: Contrast rule name.
        coding_agent: Coding agent identifier (e.g. "smartfix").
    """
    try:
        _get_pr_count_counter().add(1, {
            "outcome": outcome,
            "rule_name": rule_name,
            "coding_agent": coding_agent,
        })
    except Exception:
        pass


def record_llm_call_tokens(
        input_tokens: int, output_tokens: int,
        cache_read_tokens: int, cache_write_tokens: int, model: str) -> None:
    """Record token usage for a single LLM call.

    Counters accumulate across calls, yielding per-vulnerability totals when
    queried over the duration of a fix run.

    Args:
        input_tokens: New (non-cached) input tokens.
        output_tokens: Output tokens.
        cache_read_tokens: Prompt-cache read tokens.
        cache_write_tokens: Prompt-cache write (creation) tokens.
        model: LiteLLM model string (e.g. "contrast/claude-sonnet-4-5").
    """
    try:
        total_counter = _get_tokens_total_counter()
        total_input = input_tokens + cache_read_tokens + cache_write_tokens
        total_counter.add(total_input, {"gen_ai.token.type": "input", "gen_ai.request.model": model})
        total_counter.add(output_tokens, {"gen_ai.token.type": "output", "gen_ai.request.model": model})

        if cache_read_tokens or cache_write_tokens:
            cache_counter = _get_cache_tokens_counter()
            if cache_read_tokens:
                cache_counter.add(cache_read_tokens, {"gen_ai.token.type": "read", "gen_ai.request.model": model})
            if cache_write_tokens:
                cache_counter.add(cache_write_tokens, {"gen_ai.token.type": "write", "gen_ai.request.model": model})
    except Exception:
        pass


def record_llm_duration(elapsed_s: float, provider_name: str, model: str) -> None:
    """Record per-LLM-call latency.

    Args:
        elapsed_s: Wall-clock seconds for the LLM call.
        provider_name: OTel gen_ai system value (e.g. "contrast", "aws.bedrock").
        model: LiteLLM model string.
    """
    try:
        _get_llm_duration_histogram().record(elapsed_s, {
            "gen_ai.provider.name": provider_name,
            "gen_ai.request.model": model,
        })
    except Exception:
        pass


def record_llm_retry(model: str, error_type: str) -> None:
    """Record a single LLM retry event.

    Args:
        model: LiteLLM model string.
        error_type: Exception class name (e.g. "RateLimitError").
    """
    try:
        _get_llm_retries_counter().add(1, {
            "gen_ai.request.model": model,
            "error.type": error_type,
        })
    except Exception:
        pass
