"""Tests for sanitized 409 error message handling."""

import unittest
from unittest.mock import MagicMock
from datetime import datetime, timezone, timedelta

from src.contrast_api import get_sanitized_409_message


class TestSanitized409Messages(unittest.TestCase):
    """Test cases for get_sanitized_409_message function."""

    def test_pr_limit_exceeded_not_an_error(self):
        """PR limit message should pass through and NOT be marked as error."""
        response = '{"message": "Maximum pull request limit exceeded"}'
        message, is_error = get_sanitized_409_message(response)
        self.assertEqual(message, "Maximum pull request limit exceeded")
        self.assertFalse(is_error)  # PR limit is expected, not an error

    def test_credits_exhausted_without_credit_info_is_error(self):
        """Credits exhausted without credit info shows generic credits message and IS an error."""
        response = '{"message": "Credits have been exhausted. Contact your CSM to request additional credits."}'
        message, is_error = get_sanitized_409_message(response)
        self.assertEqual(
            message,
            "Your Contrast-provided LLM credits have been exhausted. Please contact your Contrast representative for additional credits."
        )
        self.assertTrue(is_error)

    def test_credits_exhausted_with_expired_trial_is_error(self):
        """Credits exhausted with expired trial shows trial expired message and IS an error."""
        response = '{"message": "Credits have been exhausted. Contact your CSM to request additional credits."}'

        # Mock credit info with expired end_date
        credit_info = MagicMock()
        credit_info.end_date = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

        message, is_error = get_sanitized_409_message(response, credit_info)
        self.assertEqual(
            message,
            "Your Contrast-provided LLM trial has expired. Please contact your Contrast representative to renew."
        )
        self.assertTrue(is_error)

    def test_credits_exhausted_with_active_trial_is_error(self):
        """Credits exhausted with active trial shows credits exhausted message and IS an error."""
        response = '{"message": "Credits have been exhausted. Contact your CSM to request additional credits."}'

        # Mock credit info with future end_date
        credit_info = MagicMock()
        credit_info.end_date = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

        message, is_error = get_sanitized_409_message(response, credit_info)
        self.assertEqual(
            message,
            "Your Contrast-provided LLM credits have been exhausted. Please contact your Contrast representative for additional credits."
        )
        self.assertTrue(is_error)

    def test_no_credit_tracking_entry_sanitized_is_error(self):
        """Organization UUID should be stripped and IS an error."""
        response = '{"message": "No active remediation credit tracking entry found for organization: 12345678-1234-1234-1234-123456789abc"}'
        message, is_error = get_sanitized_409_message(response)
        self.assertEqual(
            message,
            "This organization is not enabled for Contrast-provided LLM. Configure your own LLM provider, or contact your Contrast representative to enable this feature."
        )
        self.assertTrue(is_error)

    def test_unknown_409_is_error(self):
        """Unknown 409 errors should show generic safe message and IS an error."""
        response = '{"message": "Some internal error with sensitive details"}'
        message, is_error = get_sanitized_409_message(response)
        self.assertEqual(
            message,
            "Unable to process request. Please try again or contact Contrast support if the issue persists."
        )
        self.assertTrue(is_error)

    def test_malformed_json_is_error(self):
        """Malformed JSON should show generic safe message and IS an error."""
        response = 'not valid json'
        message, is_error = get_sanitized_409_message(response)
        self.assertEqual(
            message,
            "Unable to process request. Please try again or contact Contrast support if the issue persists."
        )
        self.assertTrue(is_error)

    def test_empty_response_is_error(self):
        """Empty response should show generic safe message and IS an error."""
        response = ''
        message, is_error = get_sanitized_409_message(response)
        self.assertEqual(
            message,
            "Unable to process request. Please try again or contact Contrast support if the issue persists."
        )
        self.assertTrue(is_error)

    def test_credits_exhausted_with_unparseable_date_falls_through(self):
        """If end_date can't be parsed, fall through to credits exhausted message."""
        response = '{"message": "Credits have been exhausted. Contact your CSM to request additional credits."}'

        credit_info = MagicMock()
        credit_info.end_date = "not-a-valid-date"

        message, is_error = get_sanitized_409_message(response, credit_info)
        self.assertEqual(
            message,
            "Your Contrast-provided LLM credits have been exhausted. Please contact your Contrast representative for additional credits."
        )
        self.assertTrue(is_error)


if __name__ == '__main__':
    unittest.main()
