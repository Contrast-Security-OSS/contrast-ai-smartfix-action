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

import sys
import unittest
from unittest.mock import patch, MagicMock
import os

# Add project root to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Now import project modules (after path modification)
import requests  # noqa: E402
from src.config import reset_config, get_config  # noqa: E402
from src import contrast_api  # noqa: E402


class TestContrastApiFailureCategories(unittest.TestCase):
    """Tests for the contrast_api failure categories and notification functions"""

    def setUp(self):
        """Set up test environment before each test"""
        reset_config()
        self.config = get_config()

        # Mock environment variables
        self.env_patcher = patch.dict(os.environ, {
            'CONTRAST_HOST': 'test.contrastsecurity.com',
            'CONTRAST_ORG_ID': 'test-org-id',
            'CONTRAST_APP_ID': 'test-app-id',
            'CONTRAST_AUTHORIZATION_KEY': 'test-auth-key',
            'CONTRAST_API_KEY': 'test-api-key',
        })
        self.env_patcher.start()

    def tearDown(self):
        """Clean up after each test"""
        self.env_patcher.stop()
        reset_config()

    def test_failure_category_enum_all_values(self):
        """Test that all expected failure categories are present"""
        expected_categories = [
            "INITIAL_BUILD_FAILURE",
            "EXCEEDED_QA_ATTEMPTS",
            "QA_AGENT_FAILURE",
            "GIT_COMMAND_FAILURE",
            "AGENT_FAILURE",
            "GENERATE_PR_FAILURE",
            "GENERAL_FAILURE",
            "EXCEEDED_TIMEOUT",
            "EXCEEDED_AGENT_EVENTS",
            "INVALID_LLM_CONFIG"
        ]

        actual_categories = [category.value for category in contrast_api.FailureCategory]
        self.assertEqual(set(expected_categories), set(actual_categories))

    @patch('src.contrast_api.requests.put')
    def test_notify_remediation_failed_generate_pr_failure(self, mock_put):
        """Test notify_remediation_failed with GENERATE_PR_FAILURE category"""
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_response.raise_for_status.return_value = None
        mock_put.return_value = mock_response

        result = contrast_api.notify_remediation_failed(
            remediation_id="test-remediation-123",
            failure_category="GENERATE_PR_FAILURE",
            contrast_host="test.contrastsecurity.com",
            contrast_org_id="test-org-id",
            contrast_app_id="test-app-id",
            contrast_auth_key="test-auth-key",
            contrast_api_key="test-api-key"
        )

        self.assertTrue(result)

        # Verify the API call
        expected_url = "https://test.contrastsecurity.com/api/v4/aiml-remediation/organizations/test-org-id/applications/test-app-id/remediations/test-remediation-123/failed"
        expected_headers = {
            "Authorization": "test-auth-key",
            "API-Key": "test-api-key",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": self.config.USER_AGENT
        }
        expected_payload = {
            "failureCategory": "GENERATE_PR_FAILURE"
        }

        mock_put.assert_called_once_with(
            expected_url,
            headers=expected_headers,
            json=expected_payload
        )

    @patch('src.contrast_api.requests.put')
    def test_notify_remediation_failed_http_error(self, mock_put):
        """Test notify_remediation_failed when HTTP error occurs"""
        # Mock HTTP error response
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        # Create a proper HTTPError with response attribute
        http_error = requests.exceptions.HTTPError("HTTP Error")
        http_error.response = mock_response
        mock_response.raise_for_status.side_effect = http_error
        mock_put.return_value = mock_response

        result = contrast_api.notify_remediation_failed(
            remediation_id="test-remediation-123",
            failure_category="GENERATE_PR_FAILURE",
            contrast_host="test.contrastsecurity.com",
            contrast_org_id="test-org-id",
            contrast_app_id="test-app-id",
            contrast_auth_key="test-auth-key",
            contrast_api_key="test-api-key"
        )

        self.assertFalse(result)

    @patch('src.contrast_api.requests.put')
    def test_notify_remediation_failed_non_204_response(self, mock_put):
        """Test notify_remediation_failed when API returns non-204 status"""
        # Mock non-204 response
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"messages": ["Bad request"]}
        mock_put.return_value = mock_response

        result = contrast_api.notify_remediation_failed(
            remediation_id="test-remediation-123",
            failure_category="GENERATE_PR_FAILURE",
            contrast_host="test.contrastsecurity.com",
            contrast_org_id="test-org-id",
            contrast_app_id="test-app-id",
            contrast_auth_key="test-auth-key",
            contrast_api_key="test-api-key"
        )

        self.assertFalse(result)

    def test_normalize_host_removes_https(self):
        """Test that normalize_host properly removes https prefix"""
        result = contrast_api.normalize_host("https://test.contrastsecurity.com")
        self.assertEqual(result, "test.contrastsecurity.com")

    def test_normalize_host_removes_http(self):
        """Test that normalize_host properly removes http prefix"""
        result = contrast_api.normalize_host("http://test.contrastsecurity.com")
        self.assertEqual(result, "test.contrastsecurity.com")

    def test_normalize_host_no_prefix(self):
        """Test that normalize_host leaves host unchanged when no prefix"""
        result = contrast_api.normalize_host("test.contrastsecurity.com")
        self.assertEqual(result, "test.contrastsecurity.com")


if __name__ == '__main__':
    unittest.main()
