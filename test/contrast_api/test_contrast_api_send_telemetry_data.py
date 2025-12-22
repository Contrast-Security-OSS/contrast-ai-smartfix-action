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


class TestContrastApiSendTelemetryData(unittest.TestCase):
    """Test cases for sending telemetry data in contrast_api module."""

    @patch('src.contrast_api.requests.post')
    @patch('src.contrast_api.telemetry_handler.get_telemetry_data')
    def test_send_telemetry_data_returns_valid_response(self,
        mock_get_telemetry, mock_post):
        """Test that successful API call returns True."""
        mock_get_telemetry.return_value = {
            'additionalAttributes': {'remediationId': 'test-id'}
        }
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        result = contrast_api.send_telemetry_data()

        # Focus on behavior: what does the user get back?
        self.assertTrue(result)

    @patch('src.contrast_api.telemetry_handler.get_telemetry_data')
    def test_send_telemetry_data_missing_remediation_id(self,
        mock_get_telemetry):
        """Test that no ID short circuits to return None."""
        mock_get_telemetry.return_value = {
            'additionalAttributes': {'remediationId': None}
        }

        result = contrast_api.send_telemetry_data()

        # Focus on behavior: what does the user get back?
        self.assertIsNone(result)


    @patch('src.contrast_api.telemetry_handler.get_telemetry_data')
    @patch('src.contrast_api.config.CONTRAST_HOST', None)
    def test_send_telemetry_missing_config_returns_false(self, mock_get_telemetry):
        """Test that missing config returns False."""
        mock_get_telemetry.return_value = {
            'additionalAttributes': {'remediationId': 'test-id'}
        }

        result = contrast_api.send_telemetry_data()

        self.assertFalse(result)


    @patch('src.contrast_api.requests.post')
    @patch('src.contrast_api.telemetry_handler.get_telemetry_data')
    def test_send_telemetry_data_returns_not_found(self,
        mock_get_telemetry, mock_post):
        """Test that error API call returns False."""
        mock_get_telemetry.return_value = {
            'additionalAttributes': {'remediationId': 'test-id'}
        }
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_post.return_value = mock_response

        result = contrast_api.send_telemetry_data()

        # Focus on behavior: what does the user get back?
        self.assertFalse(result)


    @patch('src.contrast_api.requests.post')
    @patch('src.contrast_api.telemetry_handler.get_telemetry_data')
    def test_send_telemetry_data_request_error(self,
        mock_get_telemetry, mock_post):
        """Test handling of request exceptions."""
        mock_get_telemetry.return_value = {
            'additionalAttributes': {'remediationId': 'test-id'}
        }
        # Create a RequestException instance
        mock_post.side_effect = requests.exceptions.RequestException(
            "Connection error")

        result = contrast_api.send_telemetry_data()

        self.assertFalse(result)

if __name__ == '__main__':
    unittest.main()
