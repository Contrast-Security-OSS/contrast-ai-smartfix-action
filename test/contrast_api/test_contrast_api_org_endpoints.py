#!/usr/bin/env python3
# -
# #%L
# Contrast AI SmartFix
# %%
# Copyright (C) 2026 Contrast Security, Inc.
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
Tests for org-level contrast_api methods (AIML-644).

Covers:
  - get_org_open_remediations
  - get_org_remediation_details
  - get_org_prompt_details
  - notify_remediation_pr_opened_org
  - notify_remediation_pr_closed_org
  - notify_remediation_pr_merged_org
  - notify_remediation_failed_org
  - send_telemetry_data_org
"""

import json
import unittest
from unittest.mock import patch, MagicMock

import requests

from src import contrast_api


APP_IDS = ['app-id-1', 'app-id-2']
HOST = 'test.contrastsecurity.com'
ORG_ID = 'test-org-id'
AUTH_KEY = 'test-auth-key'
API_KEY = 'test-api-key'
REMEDIATION_ID = 'rem-123'


# =============================================================================
# get_org_open_remediations
# =============================================================================

class TestGetOrgOpenRemediations(unittest.TestCase):

    def _call(self, **overrides):
        defaults = dict(
            contrast_host=HOST,
            contrast_org_id=ORG_ID,
            app_ids=APP_IDS,
            contrast_auth_key=AUTH_KEY,
            contrast_api_key=API_KEY,
        )
        return contrast_api.get_org_open_remediations(**{**defaults, **overrides})

    @patch('src.contrast_api.requests.post')
    def test_returns_list_on_200(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: [{'remediationId': REMEDIATION_ID, 'vulnerabilityId': 'v1'}]
        )
        result = self._call()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['remediationId'], REMEDIATION_ID)

    @patch('src.contrast_api.requests.post')
    def test_posts_to_org_url_without_app_id(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: [])
        self._call()
        url = mock_post.call_args[0][0]
        self.assertIn(f'/organizations/{ORG_ID}/remediations/open', url)
        self.assertNotIn('/applications/', url)

    @patch('src.contrast_api.requests.post')
    def test_sends_app_ids_in_body(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: [])
        self._call()
        payload = mock_post.call_args[1]['json']
        self.assertEqual(payload['appIds'], APP_IDS)

    @patch('src.contrast_api.requests.post')
    def test_returns_empty_list_on_non_200(self, mock_post):
        mock_post.return_value = MagicMock(status_code=500)
        self.assertEqual(self._call(), [])

    @patch('src.contrast_api.requests.post')
    def test_returns_empty_list_on_request_exception(self, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectionError('err')
        self.assertEqual(self._call(), [])

    @patch('src.contrast_api.requests.post')
    def test_returns_empty_list_on_json_error(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=MagicMock(side_effect=json.JSONDecodeError('', '', 0)))
        self.assertEqual(self._call(), [])


# =============================================================================
# get_org_remediation_details
# =============================================================================

class TestGetOrgRemediationDetails(unittest.TestCase):

    def _call(self, **overrides):
        defaults = dict(
            contrast_host=HOST,
            contrast_org_id=ORG_ID,
            app_ids=APP_IDS,
            contrast_auth_key=AUTH_KEY,
            contrast_api_key=API_KEY,
            github_repo_url='https://github.com/org/repo',
            max_pull_requests=5,
            severities=['CRITICAL', 'HIGH'],
        )
        return contrast_api.get_org_remediation_details(**{**defaults, **overrides})

    @patch('src.contrast_api.requests.post')
    def test_returns_dict_on_200(self, mock_post):
        payload = {
            'remediationId': REMEDIATION_ID,
            'vulnerabilityUuid': 'vuln-1',
            'vulnerabilityTitle': 'SQL Injection',
            'vulnerabilityRuleName': 'sql-injection',
            'vulnerabilitySeverity': 'HIGH',
            'applicationId': 'app-id-1',
            'skippedAppIds': ['app-id-2'],
        }
        mock_post.return_value = MagicMock(status_code=200, json=lambda: payload)
        result = self._call()
        self.assertEqual(result['remediationId'], REMEDIATION_ID)
        self.assertEqual(result['applicationId'], 'app-id-1')
        self.assertEqual(result['vulnerabilityRuleName'], 'sql-injection')
        self.assertEqual(result['vulnerabilitySeverity'], 'HIGH')

    @patch('src.contrast_api.requests.post')
    def test_posts_to_org_url_without_app_id(self, mock_post):
        mock_post.return_value = MagicMock(status_code=204)
        self._call()
        url = mock_post.call_args[0][0]
        self.assertIn(f'/organizations/{ORG_ID}/remediation-details', url)
        self.assertNotIn('/applications/', url)

    @patch('src.contrast_api.requests.post')
    def test_sends_app_ids_in_body(self, mock_post):
        mock_post.return_value = MagicMock(status_code=204)
        self._call()
        body = mock_post.call_args[1]['json']
        self.assertEqual(body['appIds'], APP_IDS)

    @patch('src.contrast_api.requests.post')
    def test_returns_none_on_204(self, mock_post):
        mock_post.return_value = MagicMock(status_code=204)
        self.assertIsNone(self._call())

    @patch('src.contrast_api.requests.post')
    def test_returns_none_on_request_exception(self, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectionError('err')
        self.assertIsNone(self._call())

    @patch('src.contrast_api.requests.post')
    def test_returns_none_on_unexpected_status(self, mock_post):
        mock_post.return_value = MagicMock(status_code=500, text='error')
        self.assertIsNone(self._call())

    @patch('src.contrast_api.requests.post')
    def test_returns_none_on_503(self, mock_post):
        mock_post.return_value = MagicMock(status_code=503, text='all apps inaccessible')
        self.assertIsNone(self._call())

    @patch('src.contrast_api.get_sanitized_409_message')
    @patch('src.contrast_api.requests.post')
    def test_exits_on_409_is_error(self, mock_post, mock_409):
        mock_post.return_value = MagicMock(status_code=409, text='credits exhausted')
        mock_409.return_value = ('Credits exhausted', True)
        with self.assertRaises(SystemExit):
            self._call()

    @patch('src.contrast_api.get_sanitized_409_message')
    @patch('src.contrast_api.requests.post')
    def test_returns_none_on_409_not_error(self, mock_post, mock_409):
        mock_post.return_value = MagicMock(status_code=409, text='pr limit reached')
        mock_409.return_value = ('PR limit reached', False)
        self.assertIsNone(self._call())


# =============================================================================
# get_org_prompt_details
# =============================================================================

class TestGetOrgPromptDetails(unittest.TestCase):

    def _call(self, **overrides):
        defaults = dict(
            contrast_host=HOST,
            contrast_org_id=ORG_ID,
            app_ids=APP_IDS,
            contrast_auth_key=AUTH_KEY,
            contrast_api_key=API_KEY,
            max_open_prs=5,
            github_repo_url='https://github.com/org/repo',
            vulnerability_severities=['CRITICAL', 'HIGH'],
        )
        return contrast_api.get_org_prompt_details(**{**defaults, **overrides})

    @patch('src.contrast_api.requests.post')
    def test_returns_dict_on_200(self, mock_post):
        payload = {
            'remediationId': REMEDIATION_ID, 'vulnerabilityUuid': 'vuln-1',
            'vulnerabilityTitle': 'SQL Injection', 'vulnerabilityRuleName': 'sql-injection',
            'vulnerabilityStatus': 'REPORTED', 'vulnerabilitySeverity': 'CRITICAL',
            'fixSystemPrompt': 'sys', 'fixUserPrompt': 'usr',
            'applicationId': 'app-id-1', 'skippedAppIds': ['app-id-2'],
        }
        mock_post.return_value = MagicMock(status_code=200, json=lambda: payload)
        result = self._call()
        self.assertEqual(result['remediationId'], REMEDIATION_ID)
        self.assertEqual(result['applicationId'], 'app-id-1')
        self.assertEqual(result['skippedAppIds'], ['app-id-2'])

    @patch('src.contrast_api.requests.post')
    def test_posts_to_org_url_without_app_id(self, mock_post):
        mock_post.return_value = MagicMock(status_code=204)
        self._call()
        url = mock_post.call_args[0][0]
        self.assertIn(f'/organizations/{ORG_ID}/prompt-details', url)
        self.assertNotIn('/applications/', url)

    @patch('src.contrast_api.requests.post')
    def test_sends_app_ids_in_body(self, mock_post):
        mock_post.return_value = MagicMock(status_code=204)
        self._call()
        body = mock_post.call_args[1]['json']
        self.assertEqual(body['appIds'], APP_IDS)

    @patch('src.contrast_api.requests.post')
    def test_returns_none_on_204(self, mock_post):
        mock_post.return_value = MagicMock(status_code=204)
        self.assertIsNone(self._call())

    @patch('src.contrast_api.requests.post')
    def test_returns_none_on_503(self, mock_post):
        mock_post.return_value = MagicMock(status_code=503, text='all apps inaccessible')
        self.assertIsNone(self._call())

    @patch('src.contrast_api.requests.post')
    def test_exits_on_request_exception(self, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectionError('err')
        with self.assertRaises(SystemExit):
            self._call()

    @patch('src.contrast_api.get_sanitized_409_message')
    @patch('src.contrast_api.requests.post')
    def test_exits_on_409_is_error(self, mock_post, mock_409):
        mock_post.return_value = MagicMock(status_code=409, text='credits exhausted')
        mock_409.return_value = ('Credits exhausted', True)
        with self.assertRaises(SystemExit):
            self._call()

    @patch('src.contrast_api.get_sanitized_409_message')
    @patch('src.contrast_api.requests.post')
    def test_returns_none_on_409_not_error(self, mock_post, mock_409):
        mock_post.return_value = MagicMock(status_code=409, text='pr limit reached')
        mock_409.return_value = ('PR limit reached', False)
        self.assertIsNone(self._call())

    @patch('src.contrast_api.requests.post')
    def test_exits_on_missing_required_keys(self, mock_post):
        incomplete_payload = {
            'remediationId': REMEDIATION_ID,
            # missing vulnerabilityUuid, vulnerabilityTitle, etc.
        }
        mock_post.return_value = MagicMock(status_code=200, json=lambda: incomplete_payload)
        with self.assertRaises(SystemExit):
            self._call()


# =============================================================================
# notify_remediation_pr_opened_org
# =============================================================================

class TestNotifyRemediationPrOpenedOrg(unittest.TestCase):

    def _call(self, **overrides):
        defaults = dict(
            remediation_id=REMEDIATION_ID, pr_number=42,
            pr_url='https://github.com/org/repo/pull/42',
            contrast_provided_llm=False,
            contrast_host=HOST, contrast_org_id=ORG_ID,
            contrast_auth_key=AUTH_KEY, contrast_api_key=API_KEY,
        )
        return contrast_api.notify_remediation_pr_opened_org(**{**defaults, **overrides})

    @patch('src.contrast_api.requests.put')
    def test_returns_true_on_204(self, mock_put):
        mock_put.return_value = MagicMock(status_code=204)
        mock_put.return_value.raise_for_status = MagicMock()
        self.assertTrue(self._call())

    @patch('src.contrast_api.requests.put')
    def test_url_has_no_app_id_segment(self, mock_put):
        mock_put.return_value = MagicMock(status_code=204)
        mock_put.return_value.raise_for_status = MagicMock()
        self._call()
        url = mock_put.call_args[0][0]
        self.assertIn(f'/organizations/{ORG_ID}/remediations/{REMEDIATION_ID}/open', url)
        self.assertNotIn('/applications/', url)

    @patch('src.contrast_api.requests.put')
    def test_returns_false_on_http_error(self, mock_put):
        mock_response = MagicMock(status_code=500, text='error')
        mock_put.return_value = mock_response
        mock_put.return_value.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_response)
        self.assertFalse(self._call())

    @patch('src.contrast_api.requests.put')
    def test_returns_false_on_request_exception(self, mock_put):
        mock_put.side_effect = requests.exceptions.ConnectionError('err')
        self.assertFalse(self._call())


# =============================================================================
# notify_remediation_pr_closed_org
# =============================================================================

class TestNotifyRemediationPrClosedOrg(unittest.TestCase):

    def _call(self, **overrides):
        defaults = dict(
            remediation_id=REMEDIATION_ID,
            contrast_host=HOST, contrast_org_id=ORG_ID,
            contrast_auth_key=AUTH_KEY, contrast_api_key=API_KEY,
        )
        return contrast_api.notify_remediation_pr_closed_org(**{**defaults, **overrides})

    @patch('src.contrast_api.requests.put')
    def test_returns_true_on_204(self, mock_put):
        mock_put.return_value = MagicMock(status_code=204)
        mock_put.return_value.raise_for_status = MagicMock()
        self.assertTrue(self._call())

    @patch('src.contrast_api.requests.put')
    def test_url_has_no_app_id_segment(self, mock_put):
        mock_put.return_value = MagicMock(status_code=204)
        mock_put.return_value.raise_for_status = MagicMock()
        self._call()
        url = mock_put.call_args[0][0]
        self.assertIn(f'/organizations/{ORG_ID}/remediations/{REMEDIATION_ID}/closed', url)
        self.assertNotIn('/applications/', url)

    @patch('src.contrast_api.requests.put')
    def test_returns_false_on_request_exception(self, mock_put):
        mock_put.side_effect = requests.exceptions.ConnectionError('err')
        self.assertFalse(self._call())


# =============================================================================
# notify_remediation_pr_merged_org
# =============================================================================

class TestNotifyRemediationPrMergedOrg(unittest.TestCase):

    def _call(self, **overrides):
        defaults = dict(
            remediation_id=REMEDIATION_ID,
            contrast_host=HOST, contrast_org_id=ORG_ID,
            contrast_auth_key=AUTH_KEY, contrast_api_key=API_KEY,
        )
        return contrast_api.notify_remediation_pr_merged_org(**{**defaults, **overrides})

    @patch('src.contrast_api.requests.put')
    def test_returns_true_on_204(self, mock_put):
        mock_put.return_value = MagicMock(status_code=204)
        mock_put.return_value.raise_for_status = MagicMock()
        self.assertTrue(self._call())

    @patch('src.contrast_api.requests.put')
    def test_url_has_no_app_id_segment(self, mock_put):
        mock_put.return_value = MagicMock(status_code=204)
        mock_put.return_value.raise_for_status = MagicMock()
        self._call()
        url = mock_put.call_args[0][0]
        self.assertIn(f'/organizations/{ORG_ID}/remediations/{REMEDIATION_ID}/merged', url)
        self.assertNotIn('/applications/', url)

    @patch('src.contrast_api.requests.put')
    def test_returns_false_on_request_exception(self, mock_put):
        mock_put.side_effect = requests.exceptions.ConnectionError('err')
        self.assertFalse(self._call())


# =============================================================================
# notify_remediation_failed_org
# =============================================================================

class TestNotifyRemediationFailedOrg(unittest.TestCase):

    def _call(self, **overrides):
        defaults = dict(
            remediation_id=REMEDIATION_ID,
            failure_category='GENERATE_PR_FAILURE',
            contrast_host=HOST, contrast_org_id=ORG_ID,
            contrast_auth_key=AUTH_KEY, contrast_api_key=API_KEY,
        )
        return contrast_api.notify_remediation_failed_org(**{**defaults, **overrides})

    @patch('src.contrast_api.requests.put')
    def test_returns_true_on_204(self, mock_put):
        mock_put.return_value = MagicMock(status_code=204)
        mock_put.return_value.raise_for_status = MagicMock()
        self.assertTrue(self._call())

    @patch('src.contrast_api.requests.put')
    def test_url_has_no_app_id_segment(self, mock_put):
        mock_put.return_value = MagicMock(status_code=204)
        mock_put.return_value.raise_for_status = MagicMock()
        self._call()
        url = mock_put.call_args[0][0]
        self.assertIn(f'/organizations/{ORG_ID}/remediations/{REMEDIATION_ID}/failed', url)
        self.assertNotIn('/applications/', url)

    @patch('src.contrast_api.requests.put')
    def test_sends_failure_category_in_body(self, mock_put):
        mock_put.return_value = MagicMock(status_code=204)
        mock_put.return_value.raise_for_status = MagicMock()
        self._call(failure_category='AGENT_FAILURE')
        body = mock_put.call_args[1]['json']
        self.assertEqual(body['failureCategory'], 'AGENT_FAILURE')

    @patch('src.contrast_api.requests.put')
    def test_returns_false_on_request_exception(self, mock_put):
        mock_put.side_effect = requests.exceptions.ConnectionError('err')
        self.assertFalse(self._call())


# =============================================================================
# send_telemetry_data_org
# =============================================================================

class TestSendTelemetryDataOrg(unittest.TestCase):

    def _call(self, remediation_id=REMEDIATION_ID, telemetry_data=None, **overrides):
        if telemetry_data is None:
            telemetry_data = {'event': 'test'}
        defaults = dict(
            remediation_id=remediation_id,
            telemetry_data=telemetry_data,
            contrast_host=HOST, contrast_org_id=ORG_ID,
            contrast_auth_key=AUTH_KEY, contrast_api_key=API_KEY,
        )
        return contrast_api.send_telemetry_data_org(**{**defaults, **overrides})

    @patch('src.contrast_api.requests.post')
    def test_returns_true_on_201(self, mock_post):
        mock_post.return_value = MagicMock(status_code=201)
        self.assertTrue(self._call())

    @patch('src.contrast_api.requests.post')
    def test_url_has_no_app_id_segment(self, mock_post):
        mock_post.return_value = MagicMock(status_code=201)
        self._call()
        url = mock_post.call_args[0][0]
        self.assertIn(f'/organizations/{ORG_ID}/remediations/{REMEDIATION_ID}/telemetry', url)
        self.assertNotIn('/applications/', url)

    @patch('src.contrast_api.requests.post')
    def test_returns_false_on_error_status(self, mock_post):
        mock_post.return_value = MagicMock(status_code=500, text='error')
        self.assertFalse(self._call())

    @patch('src.contrast_api.requests.post')
    def test_returns_false_on_request_exception(self, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectionError('err')
        self.assertFalse(self._call())


# =============================================================================
# FailureCategory enum
# =============================================================================

class TestFailureCategoryEnum(unittest.TestCase):

    def test_all_expected_values_present(self):
        from src.smartfix.shared.failure_categories import FailureCategory
        expected = {
            "INITIAL_BUILD_FAILURE",
            "GIT_COMMAND_FAILURE",
            "AGENT_FAILURE",
            "GENERATE_PR_FAILURE",
            "GENERAL_FAILURE",
            "EXCEEDED_TIMEOUT",
            "EXCEEDED_AGENT_EVENTS",
            "INVALID_LLM_CONFIG",
            "NO_CODE_CHANGED",
            "BUILD_VERIFICATION_FAILED",
        }
        self.assertEqual(expected, {c.value for c in FailureCategory})


if __name__ == '__main__':
    unittest.main()
