"""Tests for byo_usage_client.py module.

Tests the ByoUsageClient class including:
- Usage report submission and background delivery
- Retry behavior on server errors and network failures
- Header construction and sanitization
- Shutdown and drain behavior
"""

import unittest
from unittest.mock import patch

import httpx

from src.smartfix.clients.byo_usage_client import (
    ByoUsageClient,
    SMARTFIX_FEATURE,
    _build_attribution_headers,
    _sanitize_header,
)


SAMPLE_HOST = "app.contrastsecurity.com"
SAMPLE_API_KEY = "api-key-abc123"
SAMPLE_AUTHORIZATION = "auth-header-value"
SAMPLE_ORG_ID = "org-uuid-1234"

SAMPLE_MODEL = "bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0"
SAMPLE_INPUT_TOKENS = 1500
SAMPLE_OUTPUT_TOKENS = 300
SAMPLE_CACHE_READ = 800
SAMPLE_CACHE_WRITE = 200
SAMPLE_COST_USD = 0.004275
SAMPLE_FINGERPRINT = "vuln-uuid-5678"
SAMPLE_SESSION_ID = "remediation-uuid-9012"
SAMPLE_REPO = "acme/webapp"
SAMPLE_LANGUAGE = "java"


def _sample_usage_kwargs():
    """Return a dict of keyword arguments for report_usage()."""
    return {
        "model": SAMPLE_MODEL,
        "input_tokens": SAMPLE_INPUT_TOKENS,
        "output_tokens": SAMPLE_OUTPUT_TOKENS,
        "cache_read_input_tokens": SAMPLE_CACHE_READ,
        "cache_write_input_tokens": SAMPLE_CACHE_WRITE,
        "cost_usd": SAMPLE_COST_USD,
        "feature": SMARTFIX_FEATURE,
        "fingerprint": SAMPLE_FINGERPRINT,
        "session_id": SAMPLE_SESSION_ID,
        "repo": SAMPLE_REPO,
        "source_language": SAMPLE_LANGUAGE,
    }


def _make_client():
    return ByoUsageClient(
        contrast_host=SAMPLE_HOST,
        api_key=SAMPLE_API_KEY,
        authorization=SAMPLE_AUTHORIZATION,
        org_id=SAMPLE_ORG_ID,
    )


def _patch_debug_log(fn):
    """Decorator that patches debug_log to a no-op so tests don't need env vars."""
    return patch("src.smartfix.clients.byo_usage_client.debug_log")(fn)


class TestSanitizeHeader(unittest.TestCase):
    """Tests for the _sanitize_header helper."""

    def test_strips_crlf_and_null(self):
        # given
        dirty = "value\r\ninjected\0header\there"

        # when
        result = _sanitize_header(dirty)

        # then
        self.assertEqual(result, "valueinjectedheaderhere")

    def test_clean_value_unchanged(self):
        clean = "perfectly-normal-value"
        self.assertEqual(_sanitize_header(clean), clean)


class TestBuildAttributionHeaders(unittest.TestCase):
    """Tests for _build_attribution_headers."""

    def test_only_feature_when_optionals_empty(self):
        # given/when
        headers = _build_attribution_headers(feature=SMARTFIX_FEATURE)

        # then
        self.assertEqual(headers, {"x-contrast-llm-feature": SMARTFIX_FEATURE})

    def test_all_headers_populated(self):
        # given/when
        headers = _build_attribution_headers(
            feature=SMARTFIX_FEATURE,
            fingerprint=SAMPLE_FINGERPRINT,
            session_id=SAMPLE_SESSION_ID,
            repo=SAMPLE_REPO,
            source_language=SAMPLE_LANGUAGE,
        )

        # then
        self.assertEqual(headers["x-contrast-llm-feature"], SMARTFIX_FEATURE)
        self.assertEqual(headers["x-contrast-llm-fingerprint"], SAMPLE_FINGERPRINT)
        self.assertEqual(headers["x-contrast-llm-session-id"], SAMPLE_SESSION_ID)
        self.assertEqual(headers["x-contrast-llm-repo"], SAMPLE_REPO)
        self.assertEqual(headers["x-contrast-llm-source-language"], SAMPLE_LANGUAGE)


class TestByoUsageClientInit(unittest.TestCase):
    """Tests for ByoUsageClient construction."""

    def setUp(self):
        self.client = _make_client()

    def tearDown(self):
        self.client._http.close()
        self.client._executor.shutdown(wait=False)

    def test_url_built_from_host_and_org(self):
        expected_url = f"https://{SAMPLE_HOST}/api/llm-proxy/v2/organizations/{SAMPLE_ORG_ID}/usage"
        self.assertEqual(self.client._url, expected_url)

    def test_executor_uses_single_worker(self):
        # single worker ensures usage reports are serialized, which
        # preserves chronological ordering and avoids connection-pool contention
        self.assertEqual(self.client._executor._max_workers, 1)

    def test_repr_redacts_credentials(self):
        # when
        result = repr(self.client)

        # then - credentials must not appear in the repr
        self.assertNotIn(SAMPLE_API_KEY, result)
        self.assertNotIn(SAMPLE_AUTHORIZATION, result)
        # but operational state should be visible
        self.assertIn("ByoUsageClient", result)
        self.assertIn(SAMPLE_HOST, result)

    def test_host_with_protocol_prefix_is_normalized(self):
        # given - host has https:// prefix that normalize_host should strip
        self.client._http.close()
        self.client._executor.shutdown(wait=False)
        self.client = ByoUsageClient(
            contrast_host=f"https://{SAMPLE_HOST}",
            api_key=SAMPLE_API_KEY,
            authorization=SAMPLE_AUTHORIZATION,
            org_id=SAMPLE_ORG_ID,
        )

        # then - URL should not double the protocol
        self.assertIn(f"https://{SAMPLE_HOST}/", self.client._url)
        self.assertNotIn("https://https://", self.client._url)


class TestByoUsageClientReportUsage(unittest.TestCase):
    """Tests for ByoUsageClient.report_usage and _post_usage."""

    @_patch_debug_log
    @patch("src.smartfix.clients.byo_usage_client.httpx.Client")
    def test_successful_report(self, mock_client_cls, _mock_log):
        """
        Given a 200 response from the proxy,
        when report_usage is called and shutdown drains,
        then exactly one POST is made with the correct body and headers.
        """
        # given
        sample_response = httpx.Response(status_code=200)
        mock_http = mock_client_cls.return_value
        mock_http.post.return_value = sample_response

        client = _make_client()

        # when
        client.report_usage(**_sample_usage_kwargs())
        client.shutdown()

        # then
        mock_http.post.assert_called_once()
        _, kwargs = mock_http.post.call_args
        body = kwargs["json"]
        headers = kwargs["headers"]

        self.assertEqual(body["model"], SAMPLE_MODEL)
        self.assertEqual(body["input_tokens"], SAMPLE_INPUT_TOKENS)
        self.assertEqual(body["output_tokens"], SAMPLE_OUTPUT_TOKENS)
        self.assertEqual(body["cache_read_input_tokens"], SAMPLE_CACHE_READ)
        self.assertEqual(body["cache_write_input_tokens"], SAMPLE_CACHE_WRITE)
        self.assertEqual(body["cost_usd"], SAMPLE_COST_USD)
        self.assertIn("request_id", body)

        self.assertEqual(headers["API-Key"], SAMPLE_API_KEY)
        self.assertEqual(headers["Authorization"], SAMPLE_AUTHORIZATION)
        self.assertEqual(headers["x-contrast-llm-feature"], SMARTFIX_FEATURE)
        self.assertEqual(headers["x-contrast-llm-fingerprint"], SAMPLE_FINGERPRINT)
        self.assertEqual(headers["x-contrast-llm-session-id"], SAMPLE_SESSION_ID)
        self.assertEqual(headers["x-contrast-llm-repo"], SAMPLE_REPO)
        self.assertEqual(headers["x-contrast-llm-source-language"], SAMPLE_LANGUAGE)

    @_patch_debug_log
    @patch("src.smartfix.clients.byo_usage_client.httpx.Client")
    def test_attribution_fields_not_in_body(self, mock_client_cls, _mock_log):
        """
        Given a successful POST,
        when report_usage is called,
        then attribution fields (feature, fingerprint, etc.) appear in headers only,
        not in the POST body.
        """
        mock_http = mock_client_cls.return_value
        mock_http.post.return_value = httpx.Response(status_code=200)

        client = _make_client()
        client.report_usage(**_sample_usage_kwargs())
        client.shutdown()

        body = mock_http.post.call_args.kwargs["json"]
        for key in ("feature", "fingerprint", "session_id", "repo", "source_language"):
            self.assertNotIn(key, body)

    @_patch_debug_log
    @patch("src.smartfix.clients.byo_usage_client.httpx.Client")
    def test_retries_on_500(self, mock_client_cls, _mock_log):
        """
        Given a 500 response followed by a 200,
        when report_usage is called,
        then two POSTs are made (one retry) with the same request_id.
        """
        mock_http = mock_client_cls.return_value
        mock_http.post.side_effect = [
            httpx.Response(status_code=500),
            httpx.Response(status_code=200),
        ]

        client = _make_client()
        client.report_usage(**_sample_usage_kwargs())
        client.shutdown()

        self.assertEqual(mock_http.post.call_count, 2)

        # Both attempts should use the same request_id for deduplication
        first_body = mock_http.post.call_args_list[0].kwargs["json"]
        second_body = mock_http.post.call_args_list[1].kwargs["json"]
        self.assertEqual(first_body["request_id"], second_body["request_id"])

    @_patch_debug_log
    @patch("src.smartfix.clients.byo_usage_client.httpx.Client")
    def test_no_retry_on_4xx(self, mock_client_cls, _mock_log):
        """
        Given a 400 response,
        when report_usage is called,
        then only one POST is made (no retry for client errors).
        """
        mock_http = mock_client_cls.return_value
        mock_http.post.return_value = httpx.Response(status_code=400)

        client = _make_client()
        client.report_usage(**_sample_usage_kwargs())
        client.shutdown()

        self.assertEqual(mock_http.post.call_count, 1)

    @_patch_debug_log
    @patch("src.smartfix.clients.byo_usage_client.httpx.Client")
    def test_retries_on_timeout(self, mock_client_cls, _mock_log):
        """
        Given a timeout on the first attempt and success on the second,
        when report_usage is called,
        then two POSTs are made.
        """
        mock_http = mock_client_cls.return_value
        mock_http.post.side_effect = [
            httpx.TimeoutException("read timed out"),
            httpx.Response(status_code=200),
        ]

        client = _make_client()
        client.report_usage(**_sample_usage_kwargs())
        client.shutdown()

        self.assertEqual(mock_http.post.call_count, 2)

    @_patch_debug_log
    @patch("src.smartfix.clients.byo_usage_client.httpx.Client")
    def test_retries_on_connect_error(self, mock_client_cls, _mock_log):
        """
        Given a connection error on the first attempt and success on the second,
        when report_usage is called,
        then two POSTs are made.
        """
        mock_http = mock_client_cls.return_value
        mock_http.post.side_effect = [
            httpx.ConnectError("connection refused"),
            httpx.Response(status_code=200),
        ]

        client = _make_client()
        client.report_usage(**_sample_usage_kwargs())
        client.shutdown()

        self.assertEqual(mock_http.post.call_count, 2)

    @_patch_debug_log
    @patch("src.smartfix.clients.byo_usage_client.httpx.Client")
    def test_failed_count_after_exhausted_retries(self, mock_client_cls, _mock_log):
        """
        Given network errors on all attempts,
        when report_usage is called and shutdown drains,
        then the failure is counted.
        """
        mock_http = mock_client_cls.return_value
        mock_http.post.side_effect = httpx.ConnectError("connection refused")

        client = _make_client()
        client.report_usage(**_sample_usage_kwargs())
        client.shutdown()

        self.assertEqual(client._failed, 1)

    @_patch_debug_log
    @patch("src.smartfix.clients.byo_usage_client.httpx.Client")
    def test_failed_count_on_4xx_rejection(self, mock_client_cls, _mock_log):
        """
        Given a 400 rejection,
        when report_usage is called,
        then the failure is counted.
        """
        mock_http = mock_client_cls.return_value
        mock_http.post.return_value = httpx.Response(status_code=400)

        client = _make_client()
        client.report_usage(**_sample_usage_kwargs())
        client.shutdown()

        self.assertEqual(client._failed, 1)

    @_patch_debug_log
    @patch("src.smartfix.clients.byo_usage_client.httpx.Client")
    def test_multiple_reports_submitted_sequentially(self, mock_client_cls, _mock_log):
        """
        Given three report_usage calls,
        when shutdown drains,
        then three POSTs are made, each with a unique request_id.
        """
        mock_http = mock_client_cls.return_value
        mock_http.post.return_value = httpx.Response(status_code=200)

        client = _make_client()
        for _ in range(3):
            client.report_usage(**_sample_usage_kwargs())
        client.shutdown()

        self.assertEqual(mock_http.post.call_count, 3)
        self.assertEqual(client._submitted, 3)

        request_ids = [
            c.kwargs["json"]["request_id"] for c in mock_http.post.call_args_list
        ]
        self.assertEqual(len(set(request_ids)), 3)


class TestByoUsageClientShutdown(unittest.TestCase):
    """Tests for ByoUsageClient.shutdown."""

    @_patch_debug_log
    @patch("src.smartfix.clients.byo_usage_client.httpx.Client")
    def test_shutdown_closes_http_client(self, mock_client_cls, _mock_log):
        """
        When shutdown is called,
        then the underlying httpx client is closed.
        """
        mock_http = mock_client_cls.return_value

        client = _make_client()
        client.shutdown()

        mock_http.close.assert_called_once()

    @_patch_debug_log
    @patch("src.smartfix.clients.byo_usage_client.httpx.Client")
    def test_shutdown_with_no_reports(self, mock_client_cls, _mock_log):
        """
        Given no reports were submitted,
        when shutdown is called,
        then it completes without error and no failures are logged.
        """
        client = _make_client()
        client.shutdown()

        self.assertEqual(client._submitted, 0)
        self.assertEqual(client._failed, 0)


if __name__ == "__main__":
    unittest.main()
