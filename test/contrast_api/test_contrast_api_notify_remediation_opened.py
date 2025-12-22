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


class TestContrastApiNotifyRemediationOpened(unittest.TestCase):
    """Test cases for notifying remediation of PR closed in contrast_api module."""

    def setUp(self):
        """Set up test environment before each test."""
        self.mock_response = MagicMock()

    def _call_notify_remediation_pr_opened(self, **overrides):
        defaults = {
            'remediation_id': 'test-reme-d1at-ion1d',
            'pr_number': '123-pr-number',
            'pr_url': 'https://pr.url.com/123-pr-number',
            'contrastProvidedLlm': True,
            'contrast_host': 'test.contrastsecurity.com',
            'contrast_org_id': 'test-org-id',
            'contrast_app_id': 'test-app-id',
            'contrast_auth_key': 'test-auth-key',
            'contrast_api_key': 'test-api-key',
        }
        return contrast_api.notify_remediation_pr_opened(
            **{**defaults, **overrides})

    @patch('src.contrast_api.requests.put')
    def test_put_pr_opened_returns_valid_response_object(self, mock_put):
        """Test successful API call returns True."""
        # Mock successful response
        self.mock_response.status_code = 200
        mock_put.return_value = self.mock_response

        result = self._call_notify_remediation_pr_opened()

        # Focus on behavior: what does the user get back?
        self.assertTrue(result)

        # 2 types of success
        self.mock_response.status_code = 204
        mock_put.return_value = self.mock_response

        result = self._call_notify_remediation_pr_opened()

        # Focus on behavior: what does the user get back?
        self.assertTrue(result)

    @patch('src.contrast_api.requests.put')
    def test_put_pr_opened_http_error_returns_false(self, mock_put):
        """Test that HTTP errors return False."""
        self.mock_response.status_code = 404
        self.mock_response.text = "Not found"
        mock_put.return_value = self.mock_response

        # raise_for_status triggers HTTPError
        http_error = requests.exceptions.HTTPError()
        http_error.response = self.mock_response
        self.mock_response.raise_for_status.side_effect = http_error

        result = self._call_notify_remediation_pr_opened()

        # Focus on behavior: what does the user get back?
        self.assertFalse(result)

        self.mock_response.status_code = 500
        self.mock_response.text = "Server error"
        mock_put.return_value = self.mock_response

        # raise_for_status triggers HTTPError
        http_error = requests.exceptions.HTTPError()
        http_error.response = self.mock_response
        self.mock_response.raise_for_status.side_effect = http_error

        result = self._call_notify_remediation_pr_opened()

        # Focus on behavior: what does the user get back?
        self.assertFalse(result)

    @patch('src.contrast_api.requests.put')
    def test_put_pr_opened_request_error(self, mock_put):
        """Test handling of request exceptions."""
        # Create a RequestException instance
        mock_put.side_effect = requests.exceptions.RequestException(
            "Connection error")

        result = self._call_notify_remediation_pr_opened()

        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
