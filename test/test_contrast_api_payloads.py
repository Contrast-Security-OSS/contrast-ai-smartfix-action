#!/usr/bin/env python3

import unittest
from unittest.mock import patch, MagicMock

from src.config import reset_config, get_config
from src import contrast_api


class TestContrastApiPayloads(unittest.TestCase):
    """Test cases for API payload structures in contrast_api module."""

    def setUp(self):
        """Set up test environment before each test."""
        reset_config()

        # Set up environment for testing
        import os
        self.env_vars = {
            'GITHUB_WORKSPACE': '/tmp',
            'BUILD_COMMAND': 'echo "Mock build"',
            'GITHUB_TOKEN': 'mock-token',
            'GITHUB_REPOSITORY': 'mock/repo',
            'BASE_BRANCH': 'main',
            'CONTRAST_HOST': 'test.contrastsecurity.com',
            'CONTRAST_ORG_ID': 'test-org-id',
            'CONTRAST_APP_ID': 'test-app-id',
            'CONTRAST_AUTHORIZATION_KEY': 'test-auth-key',
            'CONTRAST_API_KEY': 'test-api-key'
        }

        # Store original environment
        self.original_env = os.environ.copy()
        os.environ.update(self.env_vars)

        self.config = get_config(testing=True)

    def tearDown(self):
        """Clean up after each test."""
        import os
        os.environ.clear()
        os.environ.update(self.original_env)
        reset_config()

    @patch.dict('os.environ', {'USE_CONTRAST_LLM': 'true'})
    @patch('src.contrast_api.requests.post')
    def test_get_vulnerability_with_prompts_payload_includes_contrast_provided_llm_true(self, mock_post):
        """Test that get_vulnerability_with_prompts includes contrastProvidedLlm=true in payload when USE_CONTRAST_LLM is true."""
        reset_config()

        # Need to reload contrast_api module to pick up new config
        import importlib
        from src import contrast_api
        importlib.reload(contrast_api)

        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'remediationId': 'test-remediation-123',
            'vulnerabilityUuid': 'test-vuln-uuid',
            'vulnerabilityTitle': 'Test Vulnerability',
            'vulnerabilityRuleName': 'test-rule',
            'vulnerabilityStatus': 'REPORTED',
            'vulnerabilitySeverity': 'HIGH',
            'fixSystemPrompt': 'System prompt',
            'fixUserPrompt': 'User prompt',
            'qaSystemPrompt': 'QA system prompt',
            'qaUserPrompt': 'QA user prompt',
            'sessionId': 'test-session-id-123'
        }
        mock_post.return_value = mock_response

        # Call the function
        result = contrast_api.get_vulnerability_with_prompts(
            contrast_host='test.contrastsecurity.com',
            contrast_org_id='test-org-id',
            contrast_app_id='test-app-id',
            contrast_auth_key='test-auth-key',
            contrast_api_key='test-api-key',
            max_open_prs=5,
            github_repo_url='https://github.com/test/repo',
            vulnerability_severities=['HIGH', 'CRITICAL']
        )

        # Verify the function was called
        self.assertIsNotNone(result)

        # Verify the API call was made with correct payload
        mock_post.assert_called_once()
        call_args = mock_post.call_args

        # Extract the JSON payload from the call
        payload = call_args.kwargs['json']

        # Verify the payload contains the expected fields
        self.assertIn('contrastProvidedLlm', payload)
        self.assertTrue(payload['contrastProvidedLlm'])
        self.assertEqual(payload['teamserverHost'], 'https://test.contrastsecurity.com')
        self.assertEqual(payload['repoUrl'], 'https://github.com/test/repo')
        self.assertEqual(payload['maxPullRequests'], 5)
        self.assertEqual(payload['severities'], ['HIGH', 'CRITICAL'])

    @patch.dict('os.environ', {'USE_CONTRAST_LLM': 'false'})
    @patch('src.contrast_api.requests.post')
    def test_get_vulnerability_with_prompts_payload_includes_contrast_provided_llm_false(self, mock_post):
        """Test that get_vulnerability_with_prompts includes contrastProvidedLlm=false in payload when USE_CONTRAST_LLM is false."""
        reset_config()

        # Need to reload contrast_api module to pick up new config
        import importlib
        from src import contrast_api
        importlib.reload(contrast_api)

        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'remediationId': 'test-remediation-123',
            'vulnerabilityUuid': 'test-vuln-uuid',
            'vulnerabilityTitle': 'Test Vulnerability',
            'vulnerabilityRuleName': 'test-rule',
            'vulnerabilityStatus': 'REPORTED',
            'vulnerabilitySeverity': 'HIGH',
            'fixSystemPrompt': 'System prompt',
            'fixUserPrompt': 'User prompt',
            'qaSystemPrompt': 'QA system prompt',
            'qaUserPrompt': 'QA user prompt',
            'sessionId': 'test-session-id-123'
        }
        mock_post.return_value = mock_response

        # Call the function
        result = contrast_api.get_vulnerability_with_prompts(
            contrast_host='test.contrastsecurity.com',
            contrast_org_id='test-org-id',
            contrast_app_id='test-app-id',
            contrast_auth_key='test-auth-key',
            contrast_api_key='test-api-key',
            max_open_prs=5,
            github_repo_url='https://github.com/test/repo',
            vulnerability_severities=['HIGH', 'CRITICAL']
        )

        # Verify the function was called
        self.assertIsNotNone(result)

        # Verify the API call was made with correct payload
        mock_post.assert_called_once()
        call_args = mock_post.call_args

        # Extract the JSON payload from the call
        payload = call_args.kwargs['json']

        # Verify the payload contains the expected fields
        self.assertIn('contrastProvidedLlm', payload)
        self.assertFalse(payload['contrastProvidedLlm'])

    @patch('src.contrast_api.requests.post')
    def test_get_vulnerability_with_prompts_payload_structure(self, mock_post):
        """Test the complete payload structure of get_vulnerability_with_prompts."""
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'remediationId': 'test-remediation-123',
            'vulnerabilityUuid': 'test-vuln-uuid',
            'vulnerabilityTitle': 'Test Vulnerability',
            'vulnerabilityRuleName': 'test-rule',
            'vulnerabilityStatus': 'REPORTED',
            'vulnerabilitySeverity': 'HIGH',
            'fixSystemPrompt': 'System prompt',
            'fixUserPrompt': 'User prompt',
            'qaSystemPrompt': 'QA system prompt',
            'qaUserPrompt': 'QA user prompt',
            'sessionId': 'test-session-id-123'
        }
        mock_post.return_value = mock_response

        # Call the function
        result = contrast_api.get_vulnerability_with_prompts(
            contrast_host='test.contrastsecurity.com',
            contrast_org_id='test-org-id',
            contrast_app_id='test-app-id',
            contrast_auth_key='test-auth-key',
            contrast_api_key='test-api-key',
            max_open_prs=3,
            github_repo_url='https://github.com/test/repo',
            vulnerability_severities=['CRITICAL']
        )

        # Verify the function was called
        self.assertIsNotNone(result)

        # Verify the API call was made
        mock_post.assert_called_once()
        call_args = mock_post.call_args

        # Verify URL
        expected_url = 'https://test.contrastsecurity.com/api/v4/aiml-remediation/organizations/test-org-id/applications/test-app-id/prompt-details'
        self.assertEqual(call_args.args[0], expected_url)

        # Verify headers
        headers = call_args.kwargs['headers']
        self.assertEqual(headers['Authorization'], 'test-auth-key')
        self.assertEqual(headers['API-Key'], 'test-api-key')
        self.assertEqual(headers['Content-Type'], 'application/json')

        # Verify complete payload structure
        payload = call_args.kwargs['json']
        expected_payload_keys = [
            'teamserverHost', 'repoRootDir', 'repoUrl',
            'maxPullRequests', 'severities', 'contrastProvidedLlm'
        ]

        for key in expected_payload_keys:
            self.assertIn(key, payload, f"Payload missing expected key: {key}")

        # Verify payload values
        self.assertEqual(payload['teamserverHost'], 'https://test.contrastsecurity.com')
        self.assertEqual(payload['repoUrl'], 'https://github.com/test/repo')
        self.assertEqual(payload['maxPullRequests'], 3)
        self.assertEqual(payload['severities'], ['CRITICAL'])
        self.assertIsInstance(payload['contrastProvidedLlm'], bool)


if __name__ == '__main__':
    unittest.main()
