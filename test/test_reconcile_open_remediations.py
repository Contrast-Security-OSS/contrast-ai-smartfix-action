#!/usr/bin/env python3

import unittest
from unittest.mock import patch, MagicMock

from src.smartfix.domains.workflow.pr_reconciliation import reconcile_open_remediations


class TestReconcileOpenRemediations(unittest.TestCase):
    """Test cases for reconcile_open_remediations function."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_config = MagicMock(
            CONTRAST_HOST='test.contrastsecurity.com',
            CONTRAST_ORG_ID='test-org-id',
            CONTRAST_APP_IDS=['test-app-id'],
            CONTRAST_AUTHORIZATION_KEY='test-auth-key',
            CONTRAST_API_KEY='test-api-key',
        )
        self.mock_github_ops = MagicMock()

    @patch('src.smartfix.domains.workflow.pr_reconciliation.contrast_api')
    def test_empty_list_makes_no_github_calls(self, mock_contrast_api):
        """Test that an empty open remediations list results in no GitHub calls."""
        mock_contrast_api.get_org_open_remediations.return_value = []

        reconcile_open_remediations(self.mock_config, self.mock_github_ops)

        self.mock_github_ops.get_pr_actual_state.assert_not_called()
        mock_contrast_api.notify_remediation_pr_merged_org.assert_not_called()
        mock_contrast_api.notify_remediation_pr_closed_org.assert_not_called()

    @patch('src.smartfix.domains.workflow.pr_reconciliation.contrast_api')
    def test_open_pr_no_action(self, mock_contrast_api):
        """Test that a remediation with an OPEN PR triggers no transition."""
        mock_contrast_api.get_org_open_remediations.return_value = [
            {'remediationId': 'rem-1', 'vulnerabilityId': 'vuln-1', 'pullRequestNumber': 42}
        ]
        self.mock_github_ops.get_pr_actual_state.return_value = 'OPEN'

        reconcile_open_remediations(self.mock_config, self.mock_github_ops)

        mock_contrast_api.notify_remediation_pr_merged_org.assert_not_called()
        mock_contrast_api.notify_remediation_pr_closed_org.assert_not_called()

    @patch('src.smartfix.domains.workflow.pr_reconciliation.contrast_api')
    def test_closed_pr_calls_notify_closed(self, mock_contrast_api):
        """Test that a CLOSED PR triggers notify_remediation_pr_closed_org."""
        mock_contrast_api.get_org_open_remediations.return_value = [
            {'remediationId': 'rem-1', 'vulnerabilityId': 'vuln-1', 'pullRequestNumber': 42}
        ]
        self.mock_github_ops.get_pr_actual_state.return_value = 'CLOSED'

        reconcile_open_remediations(self.mock_config, self.mock_github_ops)

        mock_contrast_api.notify_remediation_pr_closed_org.assert_called_once_with(
            remediation_id='rem-1',
            contrast_host='test.contrastsecurity.com',
            contrast_org_id='test-org-id',
            contrast_auth_key='test-auth-key',
            contrast_api_key='test-api-key',
        )
        mock_contrast_api.notify_remediation_pr_merged_org.assert_not_called()

    @patch('src.smartfix.domains.workflow.pr_reconciliation.contrast_api')
    def test_merged_pr_calls_notify_merged(self, mock_contrast_api):
        """Test that a MERGED PR triggers notify_remediation_pr_merged_org."""
        mock_contrast_api.get_org_open_remediations.return_value = [
            {'remediationId': 'rem-1', 'vulnerabilityId': 'vuln-1', 'pullRequestNumber': 42}
        ]
        self.mock_github_ops.get_pr_actual_state.return_value = 'MERGED'

        reconcile_open_remediations(self.mock_config, self.mock_github_ops)

        mock_contrast_api.notify_remediation_pr_merged_org.assert_called_once_with(
            remediation_id='rem-1',
            contrast_host='test.contrastsecurity.com',
            contrast_org_id='test-org-id',
            contrast_auth_key='test-auth-key',
            contrast_api_key='test-api-key',
        )
        mock_contrast_api.notify_remediation_pr_closed_org.assert_not_called()

    @patch('src.smartfix.domains.workflow.pr_reconciliation.contrast_api')
    def test_null_pr_number_skips(self, mock_contrast_api):
        """Test that a remediation with null pullRequestNumber is skipped."""
        mock_contrast_api.get_org_open_remediations.return_value = [
            {'remediationId': 'rem-1', 'vulnerabilityId': 'vuln-1', 'pullRequestNumber': None}
        ]

        reconcile_open_remediations(self.mock_config, self.mock_github_ops)

        self.mock_github_ops.get_pr_actual_state.assert_not_called()
        mock_contrast_api.notify_remediation_pr_merged_org.assert_not_called()
        mock_contrast_api.notify_remediation_pr_closed_org.assert_not_called()

    @patch('src.smartfix.domains.workflow.pr_reconciliation.contrast_api')
    def test_get_pr_actual_state_returns_none_skips(self, mock_contrast_api):
        """Test that None from get_pr_actual_state skips the remediation."""
        mock_contrast_api.get_org_open_remediations.return_value = [
            {'remediationId': 'rem-1', 'vulnerabilityId': 'vuln-1', 'pullRequestNumber': 42}
        ]
        self.mock_github_ops.get_pr_actual_state.return_value = None

        reconcile_open_remediations(self.mock_config, self.mock_github_ops)

        mock_contrast_api.notify_remediation_pr_merged_org.assert_not_called()
        mock_contrast_api.notify_remediation_pr_closed_org.assert_not_called()

    @patch('src.smartfix.domains.workflow.pr_reconciliation.contrast_api')
    def test_multiple_remediations_reconciled_independently(self, mock_contrast_api):
        """Test that multiple remediations are each reconciled independently."""
        mock_contrast_api.get_org_open_remediations.return_value = [
            {'remediationId': 'rem-1', 'vulnerabilityId': 'vuln-1', 'pullRequestNumber': 10},
            {'remediationId': 'rem-2', 'vulnerabilityId': 'vuln-2', 'pullRequestNumber': 20},
            {'remediationId': 'rem-3', 'vulnerabilityId': 'vuln-3', 'pullRequestNumber': 30},
        ]
        self.mock_github_ops.get_pr_actual_state.side_effect = ['OPEN', 'MERGED', 'CLOSED']

        reconcile_open_remediations(self.mock_config, self.mock_github_ops)

        self.assertEqual(self.mock_github_ops.get_pr_actual_state.call_count, 3)
        mock_contrast_api.notify_remediation_pr_merged_org.assert_called_once()
        mock_contrast_api.notify_remediation_pr_closed_org.assert_called_once()

    @patch('src.smartfix.domains.workflow.pr_reconciliation.contrast_api')
    def test_fetch_exception_does_not_propagate(self, mock_contrast_api):
        """Test that an exception fetching open remediations does not propagate."""
        mock_contrast_api.get_org_open_remediations.side_effect = RuntimeError("unexpected")

        # Should not raise
        reconcile_open_remediations(self.mock_config, self.mock_github_ops)

    @patch('src.smartfix.domains.workflow.pr_reconciliation.contrast_api')
    def test_per_remediation_exception_continues_to_next(self, mock_contrast_api):
        """Test that an exception on one remediation doesn't skip the rest."""
        mock_contrast_api.get_org_open_remediations.return_value = [
            {'remediationId': 'rem-1', 'vulnerabilityId': 'vuln-1', 'pullRequestNumber': 10},
            {'remediationId': 'rem-2', 'vulnerabilityId': 'vuln-2', 'pullRequestNumber': 20},
        ]
        # First call raises, second returns CLOSED
        self.mock_github_ops.get_pr_actual_state.side_effect = [RuntimeError("boom"), 'CLOSED']

        reconcile_open_remediations(self.mock_config, self.mock_github_ops)

        # Both PRs should have been checked
        self.assertEqual(self.mock_github_ops.get_pr_actual_state.call_count, 2)
        # Second remediation should still have been reconciled
        mock_contrast_api.notify_remediation_pr_closed_org.assert_called_once()

    @patch('src.smartfix.domains.workflow.pr_reconciliation.contrast_api')
    def test_get_org_open_remediations_called_with_app_ids(self, mock_contrast_api):
        """Test that get_org_open_remediations is called with app_ids from config."""
        mock_contrast_api.get_org_open_remediations.return_value = []

        reconcile_open_remediations(self.mock_config, self.mock_github_ops)

        mock_contrast_api.get_org_open_remediations.assert_called_once_with(
            contrast_host='test.contrastsecurity.com',
            contrast_org_id='test-org-id',
            app_ids=['test-app-id'],
            contrast_auth_key='test-auth-key',
            contrast_api_key='test-api-key',
        )


if __name__ == '__main__':
    unittest.main()
