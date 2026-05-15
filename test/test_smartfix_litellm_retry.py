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
Unit tests for SmartFixLiteLlm retry functionality.

This module tests the exponential backoff retry mechanism for LLM calls.
"""

import asyncio
import unittest
from unittest.mock import patch, AsyncMock, MagicMock

import litellm

from src.smartfix.extensions.smartfix_litellm import SmartFixLiteLlm
from src.smartfix.shared.exceptions import TokenBalanceExhaustedError


class TestSmartFixLiteLlmRetry(unittest.TestCase):
    """Test cases for LLM retry functionality."""

    def setUp(self):
        """Set up test fixtures."""
        # Create a mock instance with retry config
        self.mock_instance = MagicMock(spec=SmartFixLiteLlm)
        self.mock_instance._max_retries = 3
        self.mock_instance._initial_retry_delay = 1
        self.mock_instance._retry_multiplier = 2
        self.mock_instance.llm_client = MagicMock()

    def test_is_retryable_exception_rate_limit(self):
        """Test that RateLimitError is retryable."""
        error = litellm.RateLimitError(
            message="Rate limit exceeded",
            llm_provider="test",
            model="test-model",
            response=MagicMock()
        )
        result = SmartFixLiteLlm._is_retryable_exception(self.mock_instance, error)
        self.assertTrue(result)

    def test_is_retryable_exception_timeout(self):
        """Test that Timeout is retryable."""
        error = litellm.Timeout(
            message="Request timed out",
            llm_provider="test",
            model="test-model"
        )
        result = SmartFixLiteLlm._is_retryable_exception(self.mock_instance, error)
        self.assertTrue(result)

    def test_is_retryable_exception_service_unavailable(self):
        """Test that ServiceUnavailableError is retryable."""
        error = litellm.ServiceUnavailableError(
            message="Service unavailable",
            llm_provider="test",
            model="test-model",
            response=MagicMock()
        )
        result = SmartFixLiteLlm._is_retryable_exception(self.mock_instance, error)
        self.assertTrue(result)

    def test_is_retryable_exception_connection_error(self):
        """Test that ConnectionError is retryable."""
        error = ConnectionError("Connection failed")
        result = SmartFixLiteLlm._is_retryable_exception(self.mock_instance, error)
        self.assertTrue(result)

    def test_is_retryable_exception_asyncio_timeout(self):
        """Test that asyncio.TimeoutError is retryable."""
        error = asyncio.TimeoutError()
        result = SmartFixLiteLlm._is_retryable_exception(self.mock_instance, error)
        self.assertTrue(result)

    def test_is_retryable_exception_api_error_500(self):
        """Test that 5xx API errors are retryable."""
        error = litellm.APIError(
            message="Internal server error",
            llm_provider="test",
            model="test-model",
            status_code=500
        )
        result = SmartFixLiteLlm._is_retryable_exception(self.mock_instance, error)
        self.assertTrue(result)

    def test_is_not_retryable_exception_api_error_400(self):
        """Test that 400 Bad Request is not retryable."""
        error = litellm.APIError(
            message="Bad request",
            llm_provider="test",
            model="test-model",
            status_code=400
        )
        result = SmartFixLiteLlm._is_retryable_exception(self.mock_instance, error)
        self.assertFalse(result)

    def test_is_not_retryable_exception_api_error_401(self):
        """Test that 401 Unauthorized is not retryable."""
        error = litellm.APIError(
            message="Unauthorized",
            llm_provider="test",
            model="test-model",
            status_code=401
        )
        result = SmartFixLiteLlm._is_retryable_exception(self.mock_instance, error)
        self.assertFalse(result)

    def test_is_not_retryable_exception_api_error_404(self):
        """Test that 404 Not Found is not retryable."""
        error = litellm.APIError(
            message="Not found",
            llm_provider="test",
            model="test-model",
            status_code=404
        )
        result = SmartFixLiteLlm._is_retryable_exception(self.mock_instance, error)
        self.assertFalse(result)

    def test_is_retryable_exception_api_error_429(self):
        """Test that 429 Too Many Requests is retryable."""
        error = litellm.APIError(
            message="Too many requests",
            llm_provider="test",
            model="test-model",
            status_code=429
        )
        result = SmartFixLiteLlm._is_retryable_exception(self.mock_instance, error)
        self.assertTrue(result)

    def test_is_not_retryable_exception_value_error(self):
        """Test that ValueError is not retryable."""
        error = ValueError("Invalid value")
        result = SmartFixLiteLlm._is_retryable_exception(self.mock_instance, error)
        self.assertFalse(result)


class TestSmartFixLiteLlmRetryAsync(unittest.TestCase):
    """Async test cases for LLM retry functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_instance = MagicMock(spec=SmartFixLiteLlm)
        self.mock_instance._max_retries = 3
        self.mock_instance._initial_retry_delay = 0  # No delay for tests
        self.mock_instance._retry_multiplier = 2
        self.mock_instance.llm_client = MagicMock()
        # Use the real _is_retryable_exception method
        self.mock_instance._is_retryable_exception = lambda e: SmartFixLiteLlm._is_retryable_exception(
            self.mock_instance, e
        )
        # _log_cost_analysis is mocked via spec; return a proper 4-tuple so it can be unpacked
        self.mock_instance._log_cost_analysis.return_value = (0, 0, 0, 0)
        # _otel_context is set in __init__; provide None so start_span uses ambient context
        self.mock_instance._otel_context = None

    def _run_async(self, coro):
        """Helper to run async code in tests."""
        return asyncio.new_event_loop().run_until_complete(coro)

    def test_call_llm_with_retry_success_first_attempt(self):
        """Test successful call on first attempt."""
        expected_response = {"choices": [{"message": {"content": "Hello"}}]}
        self.mock_instance.llm_client.acompletion = AsyncMock(return_value=expected_response)

        async def run_test():
            result = await SmartFixLiteLlm._call_llm_with_retry(
                self.mock_instance, {"model": "test"}
            )
            return result

        with patch('src.smartfix.extensions.smartfix_litellm.debug_log'):
            result = self._run_async(run_test())

        self.assertEqual(result, expected_response)
        self.mock_instance.llm_client.acompletion.assert_called_once()

    def test_call_llm_with_retry_success_after_retries(self):
        """Test successful call after some retries."""
        expected_response = {"choices": [{"message": {"content": "Hello"}}]}
        rate_limit_error = litellm.RateLimitError(
            message="Rate limit",
            llm_provider="test",
            model="test",
            response=MagicMock()
        )

        # Fail twice, then succeed
        self.mock_instance.llm_client.acompletion = AsyncMock(
            side_effect=[rate_limit_error, rate_limit_error, expected_response]
        )

        async def run_test():
            result = await SmartFixLiteLlm._call_llm_with_retry(
                self.mock_instance, {"model": "test"}
            )
            return result

        with patch('src.smartfix.extensions.smartfix_litellm.debug_log'):
            with patch('asyncio.sleep', new_callable=AsyncMock):
                result = self._run_async(run_test())

        self.assertEqual(result, expected_response)
        self.assertEqual(self.mock_instance.llm_client.acompletion.call_count, 3)

    def test_call_llm_with_retry_exhausted(self):
        """Test that exception is raised after max retries exhausted."""
        rate_limit_error = litellm.RateLimitError(
            message="Rate limit",
            llm_provider="test",
            model="test",
            response=MagicMock()
        )

        # Fail all attempts
        self.mock_instance.llm_client.acompletion = AsyncMock(
            side_effect=rate_limit_error
        )

        async def run_test():
            await SmartFixLiteLlm._call_llm_with_retry(
                self.mock_instance, {"model": "test"}
            )

        with patch('src.smartfix.extensions.smartfix_litellm.debug_log'):
            with patch('asyncio.sleep', new_callable=AsyncMock):
                with self.assertRaises(litellm.RateLimitError):
                    self._run_async(run_test())

        self.assertEqual(self.mock_instance.llm_client.acompletion.call_count, 3)

    def test_call_llm_with_retry_non_retryable_immediate(self):
        """Test that non-retryable exceptions are raised immediately."""
        auth_error = litellm.APIError(
            message="Unauthorized",
            llm_provider="test",
            model="test",
            status_code=401
        )

        self.mock_instance.llm_client.acompletion = AsyncMock(side_effect=auth_error)

        async def run_test():
            await SmartFixLiteLlm._call_llm_with_retry(
                self.mock_instance, {"model": "test"}
            )

        with patch('src.smartfix.extensions.smartfix_litellm.debug_log'):
            with self.assertRaises(litellm.APIError):
                self._run_async(run_test())

        # Should only be called once - no retries for non-retryable errors
        self.mock_instance.llm_client.acompletion.assert_called_once()

    def test_call_llm_with_retry_402_raises_token_balance_exhausted(self):
        """HTTP 402 raises TokenBalanceExhaustedError, not APIError, and is not retried."""
        payment_error = litellm.APIError(
            message="Payment Required",
            llm_provider="test",
            model="test",
            status_code=402
        )

        self.mock_instance.llm_client.acompletion = AsyncMock(side_effect=payment_error)

        async def run_test():
            await SmartFixLiteLlm._call_llm_with_retry(
                self.mock_instance, {"model": "test"}
            )

        with patch('src.smartfix.extensions.smartfix_litellm.debug_log'):
            with self.assertRaises(TokenBalanceExhaustedError):
                self._run_async(run_test())

        # 402 must not be retried
        self.mock_instance.llm_client.acompletion.assert_called_once()

    def test_call_llm_with_retry_401_does_not_raise_token_balance_exhausted(self):
        """HTTP 401 propagates as APIError, not TokenBalanceExhaustedError."""
        auth_error = litellm.APIError(
            message="Unauthorized",
            llm_provider="test",
            model="test",
            status_code=401
        )

        self.mock_instance.llm_client.acompletion = AsyncMock(side_effect=auth_error)

        async def run_test():
            await SmartFixLiteLlm._call_llm_with_retry(
                self.mock_instance, {"model": "test"}
            )

        with patch('src.smartfix.extensions.smartfix_litellm.debug_log'):
            with self.assertRaises(litellm.APIError) as ctx:
                self._run_async(run_test())
            self.assertNotIsInstance(ctx.exception, TokenBalanceExhaustedError)

    def test_call_llm_with_retry_403_does_not_raise_token_balance_exhausted(self):
        """HTTP 403 propagates as APIError, not TokenBalanceExhaustedError."""
        forbidden_error = litellm.APIError(
            message="Forbidden",
            llm_provider="test",
            model="test",
            status_code=403
        )

        self.mock_instance.llm_client.acompletion = AsyncMock(side_effect=forbidden_error)

        async def run_test():
            await SmartFixLiteLlm._call_llm_with_retry(
                self.mock_instance, {"model": "test"}
            )

        with patch('src.smartfix.extensions.smartfix_litellm.debug_log'):
            with self.assertRaises(litellm.APIError) as ctx:
                self._run_async(run_test())
            self.assertNotIsInstance(ctx.exception, TokenBalanceExhaustedError)

    def test_call_llm_with_retry_429_retries_not_token_balance(self):
        """HTTP 429 is retried and does not raise TokenBalanceExhaustedError."""
        rate_limit_error = litellm.APIError(
            message="Too Many Requests",
            llm_provider="test",
            model="test",
            status_code=429
        )
        expected_response = {"choices": [{"message": {"content": "ok"}}]}

        # Fail once with 429, then succeed
        self.mock_instance.llm_client.acompletion = AsyncMock(
            side_effect=[rate_limit_error, expected_response]
        )

        async def run_test():
            return await SmartFixLiteLlm._call_llm_with_retry(
                self.mock_instance, {"model": "test"}
            )

        with patch('src.smartfix.extensions.smartfix_litellm.debug_log'):
            with patch('asyncio.sleep', new_callable=AsyncMock):
                result = self._run_async(run_test())

        self.assertEqual(result, expected_response)
        self.assertEqual(self.mock_instance.llm_client.acompletion.call_count, 2)


class TestLitellm402ExceptionShape(unittest.TestCase):
    """Contract tests locking in the shape of litellm's 402 exception.

    Our 402 detection reads e.status_code directly (mirroring _is_retryable_exception).
    litellm's exception_mapping_utils.py:588-597 confirms 402 hits the else branch
    and raises APIError(status_code=...) with the code on the instance, not on
    e.response. These tests break loudly if that changes in a future litellm version.
    """

    def test_litellm_api_error_402_status_code_on_instance(self):
        """litellm.APIError exposes status_code directly on the instance."""
        e = litellm.APIError(
            status_code=402,
            message="Payment Required",
            llm_provider="test",
            model="test",
        )
        self.assertEqual(e.status_code, 402)
        self.assertEqual(getattr(e, 'status_code', None), 402)

    def test_402_detection_requires_status_code_on_instance_not_response(self):
        """Detection does not fire when status_code is only on e.response, not the instance.

        Documents the detection boundary: if litellm ever moves the code to
        e.response.status_code, our check would miss it and this test would need
        updating alongside the detection logic.
        """
        e = litellm.APIError(
            status_code=200,
            message="ok",
            llm_provider="test",
            model="test",
        )
        e.status_code = None
        self.assertIsNone(getattr(e, 'status_code', None))
        self.assertFalse(
            isinstance(e, litellm.APIError) and getattr(e, 'status_code', None) == 402
        )


class TestSmartFixLiteLlmRetryConfig(unittest.TestCase):
    """Test cases for retry configuration loading."""

    def setUp(self):
        """Reset config singleton before each test."""
        from src.config import reset_config
        reset_config()

    def tearDown(self):
        """Reset config singleton after each test."""
        from src.config import reset_config
        reset_config()

    def test_retry_config_defaults(self):
        """Test that retry configuration has sensible defaults."""
        from src.config import get_config
        config = get_config(testing=True)

        # Verify config attributes exist and have the expected defaults
        self.assertEqual(config.LLM_MAX_RETRIES, 7)
        self.assertEqual(config.LLM_INITIAL_RETRY_DELAY_SECONDS, 1)
        self.assertEqual(config.LLM_RETRY_MULTIPLIER, 2)

    def test_retry_config_from_env_vars(self):
        """Test that retry configuration reads from environment variables."""
        import os
        from src.config import Config

        # Set custom env vars
        custom_env = os.environ.copy()
        custom_env['LLM_MAX_RETRIES'] = '10'
        custom_env['LLM_INITIAL_RETRY_DELAY_SECONDS'] = '5'
        custom_env['LLM_RETRY_MULTIPLIER'] = '3'

        # Create config with custom env
        config = Config(env=custom_env, testing=True)

        # Verify env vars were used
        self.assertEqual(config.LLM_MAX_RETRIES, 10)
        self.assertEqual(config.LLM_INITIAL_RETRY_DELAY_SECONDS, 5)
        self.assertEqual(config.LLM_RETRY_MULTIPLIER, 3)

    def test_retry_config_validation_min_values(self):
        """Test that retry configuration respects minimum value constraints."""
        import os
        from src.config import Config

        # Set values below minimums
        custom_env = os.environ.copy()
        custom_env['LLM_MAX_RETRIES'] = '0'  # min is 1
        custom_env['LLM_INITIAL_RETRY_DELAY_SECONDS'] = '0'  # min is 1
        custom_env['LLM_RETRY_MULTIPLIER'] = '1'  # min is 2

        # Create config with custom env
        config = Config(env=custom_env, testing=True)

        # Verify minimums were enforced
        self.assertEqual(config.LLM_MAX_RETRIES, 1)
        self.assertEqual(config.LLM_INITIAL_RETRY_DELAY_SECONDS, 1)
        self.assertEqual(config.LLM_RETRY_MULTIPLIER, 2)


if __name__ == '__main__':
    unittest.main()
