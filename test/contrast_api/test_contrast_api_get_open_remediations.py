#!/usr/bin/env python3

import unittest
import json
from unittest.mock import patch, MagicMock
import requests

from src import contrast_api


class TestContrastApiGetOpenRemediations(unittest.TestCase):
    """Test cases for get_open_remediations in contrast_api module."""

    def _call_get_open_remediations(self, **overrides):
        defaults = {
            'contrast_host': 'test.contrastsecurity.com',
            'contrast_org_id': 'test-org-id',
            'contrast_app_id': 'test-app-id',
            'contrast_auth_key': 'test-auth-key',
            'contrast_api_key': 'test-api-key',
        }
        return contrast_api.get_open_remediations(**{**defaults, **overrides})

    @patch('src.contrast_api.requests.get')
    def test_returns_list_on_200(self, mock_get):
        """Test successful API call returns the list of open remediations."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                'remediationId': 'abc-123',
                'vulnerabilityId': 'VULN-001',
                'pullRequestNumber': 42,
                'pullRequestUrl': 'https://github.com/org/repo/pull/42',
            }
        ]
        mock_get.return_value = mock_response

        result = self._call_get_open_remediations()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['remediationId'], 'abc-123')

    @patch('src.contrast_api.requests.get')
    def test_returns_empty_list_on_200_with_no_remediations(self, mock_get):
        """Test successful API call with empty response returns empty list."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        result = self._call_get_open_remediations()

        self.assertEqual(result, [])

    @patch('src.contrast_api.requests.get')
    def test_returns_empty_list_on_non_200(self, mock_get):
        """Test non-200 status code returns empty list."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        result = self._call_get_open_remediations()

        self.assertEqual(result, [])

    @patch('src.contrast_api.requests.get')
    def test_returns_empty_list_on_request_exception(self, mock_get):
        """Test request exception returns empty list."""
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")

        result = self._call_get_open_remediations()

        self.assertEqual(result, [])

    @patch('src.contrast_api.requests.get')
    def test_returns_empty_list_on_json_decode_error(self, mock_get):
        """Test JSON decode error returns empty list."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = json.JSONDecodeError("msg", "doc", 0)
        mock_get.return_value = mock_response

        result = self._call_get_open_remediations()

        self.assertEqual(result, [])

    @patch('src.contrast_api.requests.get')
    def test_returns_empty_list_on_unexpected_exception(self, mock_get):
        """Test unexpected exception returns empty list."""
        mock_get.side_effect = RuntimeError("unexpected")

        result = self._call_get_open_remediations()

        self.assertEqual(result, [])

    @patch('src.contrast_api.requests.get')
    def test_calls_correct_url(self, mock_get):
        """Test that the correct API URL is called."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        self._call_get_open_remediations()

        args, kwargs = mock_get.call_args
        self.assertIn('/remediations/open', args[0])
        self.assertIn('test-org-id', args[0])
        self.assertIn('test-app-id', args[0])


if __name__ == '__main__':
    unittest.main()
