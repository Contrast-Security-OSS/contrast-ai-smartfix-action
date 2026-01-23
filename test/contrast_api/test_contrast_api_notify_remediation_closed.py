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


class TestContrastApiNotifyRemediationClosed(unittest.TestCase):
    """Test cases for notifying remediation of PR closed in contrast_api module."""

    def setUp(self):
        """Set up test environment before each test."""
        self.mock_response = MagicMock()

    def _call_notify_remediation_pr_closed(self, **overrides):
        defaults = {
            'remediation_id': 'test-reme-d1at-ion1d',
            'contrast_host': 'test.contrastsecurity.com',
            'contrast_org_id': 'test-org-id',
            'contrast_app_id': 'test-app-id',
            'contrast_auth_key': 'test-auth-key',
            'contrast_api_key': 'test-api-key',
        }
        return contrast_api.notify_remediation_pr_closed(
            **{**defaults, **overrides})

    @patch('src.contrast_api.requests.put')
    def test_pr_closed_should_return_valid_response_object(self, mock_put):
        """Test successful API call returns True."""
        # Mock successful response
        self.mock_response.status_code = 204
        mock_put.return_value = self.mock_response

        result = self._call_notify_remediation_pr_closed()

        # Focus on behavior: what does the user get back?
        self.assertTrue(result)

    @patch('src.contrast_api.requests.put')
    def test_pr_closed_should_return_http_error_on_exception(self, mock_put):
        """Test that HTTP errors return False."""
        self.mock_response.status_code = 404
        self.mock_response.text = "Not found"
        mock_put.return_value = self.mock_response

        # raise_for_status triggers HTTPError
        http_error = requests.exceptions.HTTPError()
        http_error.response = self.mock_response
        self.mock_response.raise_for_status.side_effect = http_error

        result = self._call_notify_remediation_pr_closed()

        # Focus on behavior: what does the user get back?
        self.assertFalse(result)

        self.mock_response.status_code = 500
        self.mock_response.text = "Server error"
        mock_put.return_value = self.mock_response

        # raise_for_status triggers HTTPError
        http_error = requests.exceptions.HTTPError()
        http_error.response = self.mock_response
        self.mock_response.raise_for_status.side_effect = http_error

        result = self._call_notify_remediation_pr_closed()

        # Focus on behavior: what does the user get back?
        self.assertFalse(result)

    @patch('src.contrast_api.requests.put')
    def test_pr_closed_request_error(self, mock_put):
        """Test handling of request exceptions."""
        # Create a RequestException instance
        mock_put.side_effect = requests.exceptions.RequestException(
            "Connection error")

        result = self._call_notify_remediation_pr_closed()

        self.assertFalse(result)

    @patch('src.contrast_api.requests.put')
    def test_pr_closed_json_error(self, mock_put):
        """Test that malformed JSON results in return False."""
        self.mock_response.status_code = 200
        self.mock_response.json.side_effect = json.JSONDecodeError(
            "Expecting value", "doc", 0)
        mock_put.return_value = self.mock_response

        result = self._call_notify_remediation_pr_closed()

        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
