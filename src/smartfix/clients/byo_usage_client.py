"""HTTP client for reporting BYO LLM token usage to the Contrast LLM proxy.

Usage reports are submitted via a single-thread executor so they never block
the caller. Each LLM call triggers a report_usage() call from the per-call
callback in SmartFixLiteLlm._log_cost_analysis(), which sits on the hot path
between successive LLM calls. Without background submission, a slow or
timed-out POST would delay the next LLM call.
"""

import time
import uuid
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, wait
import httpx

from src.utils import debug_log, normalize_host

DEFAULT_TIMEOUT = 5.0
MAX_RETRIES = 1
RETRY_DELAY = 1.0

SMARTFIX_FEATURE = "SMARTFIX"

# Callback type for per-LLM-call usage events.
# All parameters are keyword-only.
UsageEventCallback = Callable[
    ...,  # keyword-only args: model, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, cost_usd
    None,
]


def _sanitize_header(value: str) -> str:
    """Strip characters that could enable HTTP header injection."""
    return value.replace("\r", "").replace("\n", "").replace("\0", "").replace("\t", "")


def _build_attribution_headers(
    *,
    feature: str,
    vuln_id: str = "",
    session_id: str = "",
    repo: str = "",
    source_language: str = "",
) -> dict[str, str]:
    """Build the x-contrast-llm-* attribution headers."""
    headers: dict[str, str] = {
        "x-contrast-llm-feature": _sanitize_header(feature),
    }
    if vuln_id:
        headers["x-contrast-llm-fingerprint"] = _sanitize_header(vuln_id)
    if session_id:
        headers["x-contrast-llm-session-id"] = _sanitize_header(session_id)
    if repo:
        headers["x-contrast-llm-repo"] = _sanitize_header(repo)
    if source_language:
        headers["x-contrast-llm-source-language"] = _sanitize_header(source_language)
    return headers


class ByoUsageClient:
    """Reports token usage to the Contrast LLM proxy for BYO LLM providers.

    BYO (Bring Your Own) LLM means the customer is using their own LLM provider
    (e.g., Bedrock, Anthropic direct) instead of the Contrast-managed proxy. Token
    usage must be reported after the fact so Contrast can track consumption.
    """

    def __init__(self, contrast_host: str, api_key: str, authorization: str, org_id: str):
        host = normalize_host(contrast_host)
        self._url = f"https://{host}/api/llm-proxy/v2/organizations/{org_id}/usage"
        self._base_headers: dict[str, str] = {
            "API-Key": api_key,
            "Authorization": authorization,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        self._http = httpx.Client()
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._futures: list[Future] = []
        self._submitted = 0
        self._failed = 0

    def __repr__(self) -> str:
        return (
            f"ByoUsageClient(url={self._url!r}, "
            f"submitted={self._submitted}, failed={self._failed})"
        )

    def report_usage(
        self,
        *,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_input_tokens: int,
        cache_write_input_tokens: int,
        cost_usd: float = 0.0,
        feature: str,
        vuln_id: str,
        session_id: str,
        repo: str = "",
        source_language: str = "",
    ) -> None:
        """Submit a usage report for background delivery.

        Returns immediately. The executor thread POSTs the data to the
        /v2/usage endpoint with bounded retry. Never raises.
        """
        self._submitted += 1
        self._futures = [f for f in self._futures if not f.done()]
        body = {
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_input_tokens": cache_read_input_tokens,
            "cache_write_input_tokens": cache_write_input_tokens,
            "cost_usd": cost_usd,
        }
        attribution_headers = _build_attribution_headers(
            feature=feature,
            vuln_id=vuln_id,
            session_id=session_id,
            repo=repo,
            source_language=source_language,
        )
        future = self._executor.submit(self._post_usage, body, attribution_headers)
        self._futures.append(future)

    def shutdown(self, timeout: float = 15.0) -> None:
        """Wait for pending reports and shut down the executor.

        Blocks up to *timeout* seconds for in-flight POSTs to complete.
        Logs a warning if any reports failed or were dropped.
        """
        done, not_done = wait(self._futures, timeout=timeout)
        dropped = len(not_done)
        total_lost = self._failed + dropped
        if total_lost > 0:
            debug_log(
                f"BYO usage reporting: {total_lost} of {self._submitted} report(s) "
                f"were not delivered ({self._failed} failed, {dropped} dropped)"
            )

        self._executor.shutdown(wait=False, cancel_futures=True)
        self._http.close()

    def _post_usage(
        self, body: dict[str, object], attribution_headers: dict[str, str]
    ) -> None:
        """POST a single usage report with bounded retry.

        request_id is generated once per report and reused across retries so the
        proxy can deduplicate if the first attempt was received but the response lost.
        """
        request_id = str(uuid.uuid4())
        body = {"request_id": request_id, **body}
        headers = {**self._base_headers, **attribution_headers}

        max_attempts = MAX_RETRIES + 1
        last_error: str | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                response = self._http.post(
                    url=self._url,
                    headers=headers,
                    json=body,
                    timeout=DEFAULT_TIMEOUT,
                )
                if response.status_code < 500:
                    if response.is_success:
                        debug_log(
                            f"Reported BYO usage: request_id={request_id} model={body['model']} "
                            f"input={body['input_tokens']} output={body['output_tokens']} "
                            f"cost_usd={body['cost_usd']:.6f}"
                        )
                    else:
                        self._failed += 1
                        debug_log(
                            f"BYO usage report rejected (HTTP {response.status_code}): "
                            f"request_id={request_id}"
                        )
                    return

                last_error = f"HTTP {response.status_code}"
                debug_log(
                    f"BYO usage report returned {response.status_code}, "
                    f"attempt {attempt}/{max_attempts}"
                )
            except (
                httpx.TimeoutException,
                httpx.ConnectError,
                httpx.RequestError,
            ) as e:
                last_error = str(e)
                debug_log(
                    f"BYO usage report failed ({e}), attempt {attempt}/{max_attempts}"
                )

            if attempt < max_attempts:
                time.sleep(RETRY_DELAY)

        self._failed += 1
        debug_log(
            f"BYO usage report failed after {max_attempts} attempts: "
            f"{last_error} (request_id={request_id})"
        )
