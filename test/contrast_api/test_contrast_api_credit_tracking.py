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


class TestContrastApiCreditTrackingOrg(unittest.TestCase):
    """Test cases for org-level credit tracking (no app_id) in contrast_api module."""

    def setUp(self):
        self.sample_api_response = {
            "organizationId": "12345678-1234-1234-1234-123456789abc",
            "enabled": True,
            "maxCredits": 50,
            "creditsUsed": 7,
            "startDate": "2024-10-01T14:30:00Z",
            "endDate": "2024-11-12T14:30:00Z"
        }

    @patch('src.contrast_api.requests.get')
    def test_get_credit_tracking_org_returns_valid_response(self, mock_get):
        """Test that org-level endpoint returns properly structured CreditTrackingResponse."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps(self.sample_api_response)
        mock_response.json.return_value = self.sample_api_response
        mock_get.return_value = mock_response

        result = contrast_api.get_credit_tracking_org(
            contrast_host="test.contrastsecurity.com",
            contrast_org_id="test-org-id",
            contrast_auth_key="test-auth-key",
            contrast_api_key="test-api-key"
        )

        self.assertIsInstance(result, CreditTrackingResponse)
        self.assertTrue(result.enabled)

    @patch('src.contrast_api.requests.get')
    def test_get_credit_tracking_org_url_has_no_app_id(self, mock_get):
        """Test that the org-level endpoint URL does not include an application ID."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps(self.sample_api_response)
        mock_response.json.return_value = self.sample_api_response
        mock_get.return_value = mock_response

        contrast_api.get_credit_tracking_org(
            contrast_host="test.contrastsecurity.com",
            contrast_org_id="test-org-id",
            contrast_auth_key="test-auth-key",
            contrast_api_key="test-api-key"
        )

        called_url = mock_get.call_args[0][0]
        self.assertIn("/organizations/test-org-id/credit-tracking", called_url)
        self.assertNotIn("/applications/", called_url)

    @patch('src.contrast_api.requests.get')
    def test_get_credit_tracking_org_returns_none_on_http_error(self, mock_get):
        """Test that org-level endpoint returns None on HTTP errors."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_get.return_value = mock_response
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_response
        )

        result = contrast_api.get_credit_tracking_org(
            contrast_host="test.contrastsecurity.com",
            contrast_org_id="test-org-id",
            contrast_auth_key="test-auth-key",
            contrast_api_key="test-api-key"
        )

        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
