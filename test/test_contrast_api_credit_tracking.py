#!/usr/bin/env python3
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

import unittest
import json
from unittest.mock import patch, MagicMock
import requests

from src import contrast_api
from src.smartfix.domains.workflow.credit_tracking import CreditTrackingResponse


class TestContrastApiCreditTracking(unittest.TestCase):
    """Test cases for credit tracking functionality in contrast_api module."""

    def setUp(self):
        """Set up test environment before each test."""
        self.sample_api_response = {
            "organizationId": "12345678-1234-1234-1234-123456789abc",
            "enabled": True,
            "maxCredits": 50,
            "creditsUsed": 7,
            "startDate": "2024-10-01T14:30:00Z",
            "endDate": "2024-11-12T14:30:00Z"
        }

    def tearDown(self):
        """Clean up test environment after each test."""
        # No cleanup needed since we don't modify global state
        pass

    @patch('src.contrast_api.requests.get')
    def test_get_credit_tracking_returns_valid_response_object(self, mock_get):
        """Test that successful API call returns properly structured CreditTrackingResponse."""
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps(self.sample_api_response)
        mock_response.json.return_value = self.sample_api_response
        mock_get.return_value = mock_response

        result = contrast_api.get_credit_tracking(
            contrast_host="test.contrastsecurity.com",
            contrast_org_id="test-org-id",
            contrast_app_id="test-app-id",
            contrast_auth_key="test-auth-key"
        )

        # Focus on behavior: what does the user get back?
        self.assertIsInstance(result, CreditTrackingResponse)
        self.assertEqual(result.organization_id, "12345678-1234-1234-1234-123456789abc")
        self.assertTrue(result.enabled)
        self.assertEqual(result.max_credits, 50)
        self.assertEqual(result.credits_used, 7)
        self.assertEqual(result.start_date, "2024-10-01T14:30:00Z")
        self.assertEqual(result.end_date, "2024-11-12T14:30:00Z")

    @patch('src.contrast_api.requests.get')
    def test_get_credit_tracking_returns_none_when_api_unavailable(self, mock_get):
        """Test that HTTP errors result in None return value."""
        # Mock HTTP error response
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_get.return_value = mock_response

        # Create HTTPError with response attribute
        http_error = requests.exceptions.HTTPError("404 Client Error")
        http_error.response = mock_response
        mock_response.raise_for_status.side_effect = http_error

        result = contrast_api.get_credit_tracking(
            contrast_host="test.contrastsecurity.com",
            contrast_org_id="test-org-id",
            contrast_app_id="test-app-id",
            contrast_auth_key="test-auth-key"
        )

        # Focus on user experience: what happens when API is down?
        self.assertIsNone(result)

    @patch('src.contrast_api.requests.get')
    def test_get_credit_tracking_returns_none_when_network_unavailable(self, mock_get):
        """Test that network errors result in None return value."""
        # Mock connection error
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection failed")

        result = contrast_api.get_credit_tracking(
            contrast_host="test.contrastsecurity.com",
            contrast_org_id="test-org-id",
            contrast_app_id="test-app-id",
            contrast_auth_key="test-auth-key"
        )

        # Focus on user experience: what happens when network is down?
        self.assertIsNone(result)

    @patch('src.contrast_api.requests.get')
    def test_get_credit_tracking_returns_none_when_response_malformed(self, mock_get):
        """Test that malformed JSON responses result in None return value."""
        # Mock response with invalid JSON
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Invalid JSON"
        mock_response.json.side_effect = json.JSONDecodeError("Expecting value", "doc", 0)
        mock_get.return_value = mock_response

        result = contrast_api.get_credit_tracking(
            contrast_host="test.contrastsecurity.com",
            contrast_org_id="test-org-id",
            contrast_app_id="test-app-id",
            contrast_auth_key="test-auth-key"
        )

        # Focus on robustness: what happens when API returns garbage?
        self.assertIsNone(result)

    @patch('src.contrast_api.requests.get')
    def test_get_credit_tracking_gracefully_handles_unexpected_errors(self, mock_get):
        """Test that unexpected errors are handled gracefully."""
        # Mock unexpected error
        mock_get.side_effect = Exception("Unexpected error")

        result = contrast_api.get_credit_tracking(
            contrast_host="test.contrastsecurity.com",
            contrast_org_id="test-org-id",
            contrast_app_id="test-app-id",
            contrast_auth_key="test-auth-key"
        )

        # Focus on resilience: function should not crash on unexpected errors
        self.assertIsNone(result)

    @patch('src.contrast_api.requests.get')
    def test_get_credit_tracking_returns_disabled_org_data(self, mock_get):
        """Test that disabled organizations return proper data structure."""
        disabled_response = {
            "organizationId": "87654321-4321-4321-4321-cba987654321",
            "enabled": False,
            "maxCredits": 0,
            "creditsUsed": 0,
            "startDate": "",
            "endDate": ""
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps(disabled_response)
        mock_response.json.return_value = disabled_response
        mock_get.return_value = mock_response

        result = contrast_api.get_credit_tracking(
            contrast_host="test.contrastsecurity.com",
            contrast_org_id="test-org-id",
            contrast_app_id="test-app-id",
            contrast_auth_key="test-auth-key"
        )

        # Focus on the business logic: what should a disabled org look like?
        self.assertIsInstance(result, CreditTrackingResponse)
        self.assertFalse(result.enabled)
        self.assertEqual(result.max_credits, 0)
        self.assertEqual(result.credits_used, 0)
        self.assertEqual(result.start_date, "")
        self.assertEqual(result.end_date, "")

    @patch('src.contrast_api.requests.get')
    def test_get_credit_tracking_handles_host_with_trailing_slash(self, mock_get):
        """Test that host URLs with trailing slashes are handled correctly."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps(self.sample_api_response)
        mock_response.json.return_value = self.sample_api_response
        mock_get.return_value = mock_response

        result = contrast_api.get_credit_tracking(
            contrast_host="https://app.contrastsecurity.com/",  # Note trailing slash
            contrast_org_id="test-org-id",
            contrast_app_id="test-app-id",
            contrast_auth_key="test-auth-key"
        )

        # Should still work and return valid response
        self.assertIsInstance(result, CreditTrackingResponse)

        # Verify URL was constructed without double slashes
        call_args = mock_get.call_args
        url = call_args[1]['url'] if 'url' in call_args[1] else call_args[0][0]
        self.assertNotIn("//api", url)

    @patch('src.contrast_api.requests.get')
    def test_get_credit_tracking_handles_host_without_https(self, mock_get):
        """Test that host URLs without https:// prefix are handled correctly."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps(self.sample_api_response)
        mock_response.json.return_value = self.sample_api_response
        mock_get.return_value = mock_response

        result = contrast_api.get_credit_tracking(
            contrast_host="app.contrastsecurity.com",  # No https:// prefix
            contrast_org_id="test-org-id",
            contrast_app_id="test-app-id",
            contrast_auth_key="test-auth-key"
        )

        # Should still work and return valid response
        self.assertIsInstance(result, CreditTrackingResponse)

        # Verify URL starts with https://
        call_args = mock_get.call_args
        url = call_args[1]['url'] if 'url' in call_args[1] else call_args[0][0]
        self.assertTrue(url.startswith("https://"))

    @patch('src.contrast_api.requests.get')
    def test_get_credit_tracking_uses_bearer_authorization(self, mock_get):
        """Test that API calls use proper Bearer token authorization."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps(self.sample_api_response)
        mock_response.json.return_value = self.sample_api_response
        mock_get.return_value = mock_response

        contrast_api.get_credit_tracking(
            contrast_host="test.contrastsecurity.com",
            contrast_org_id="test-org-id",
            contrast_app_id="test-app-id",
            contrast_auth_key="test-auth-key"
        )

        # Verify proper authorization header was used
        call_args = mock_get.call_args
        headers = call_args[1]['headers']
        self.assertEqual(headers['Authorization'], 'Bearer test-auth-key')


if __name__ == '__main__':
    unittest.main()
