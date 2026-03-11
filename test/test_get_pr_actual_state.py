#!/usr/bin/env python3

import unittest
import json
from unittest.mock import patch, MagicMock

from src.github.github_operations import GitHubOperations


class TestGetPrActualState(unittest.TestCase):
    """Test cases for GitHubOperations.get_pr_actual_state."""

    def setUp(self):
        """Set up test fixtures."""
        with patch('src.github.github_operations.get_config') as mock_config:
            mock_config.return_value = MagicMock(
                GITHUB_TOKEN="test-token",
                GITHUB_REPOSITORY="test-owner/test-repo",
                testing=True,
                coding_agent=None
            )
            self.github_ops = GitHubOperations()

    @patch('src.github.github_operations.run_command')
    def test_returns_open_for_open_pr(self, mock_run_command):
        """Test returns OPEN when PR is open."""
        mock_run_command.return_value = json.dumps({'state': 'OPEN', 'mergedAt': None})
        result = self.github_ops.get_pr_actual_state(42)
        self.assertEqual(result, 'OPEN')

    @patch('src.github.github_operations.run_command')
    def test_returns_merged_for_closed_pr_with_merged_at(self, mock_run_command):
        """Test returns MERGED when PR is closed with mergedAt set."""
        mock_run_command.return_value = json.dumps({'state': 'CLOSED', 'mergedAt': '2025-03-01T12:00:00Z'})
        result = self.github_ops.get_pr_actual_state(42)
        self.assertEqual(result, 'MERGED')

    @patch('src.github.github_operations.run_command')
    def test_returns_closed_for_closed_pr_without_merged_at(self, mock_run_command):
        """Test returns CLOSED when PR is closed without mergedAt."""
        mock_run_command.return_value = json.dumps({'state': 'CLOSED', 'mergedAt': None})
        result = self.github_ops.get_pr_actual_state(42)
        self.assertEqual(result, 'CLOSED')

    @patch('src.github.github_operations.run_command')
    def test_returns_none_when_command_fails(self, mock_run_command):
        """Test returns None when gh command fails."""
        mock_run_command.return_value = None
        result = self.github_ops.get_pr_actual_state(42)
        self.assertIsNone(result)

    @patch('src.github.github_operations.run_command')
    def test_returns_none_on_invalid_json(self, mock_run_command):
        """Test returns None when response is invalid JSON."""
        mock_run_command.return_value = "not json"
        result = self.github_ops.get_pr_actual_state(42)
        self.assertIsNone(result)

    @patch('src.github.github_operations.run_command')
    def test_returns_none_on_unexpected_state(self, mock_run_command):
        """Test returns None when PR state is unexpected."""
        mock_run_command.return_value = json.dumps({'state': 'DRAFT', 'mergedAt': None})
        result = self.github_ops.get_pr_actual_state(42)
        self.assertIsNone(result)

    @patch('src.github.github_operations.run_command')
    def test_returns_none_on_exception(self, mock_run_command):
        """Test returns None when an exception occurs."""
        mock_run_command.side_effect = RuntimeError("unexpected error")
        result = self.github_ops.get_pr_actual_state(42)
        self.assertIsNone(result)

    @patch('src.github.github_operations.run_command')
    def test_passes_repo_flag(self, mock_run_command):
        """Test that --repo flag is passed with the correct repository."""
        mock_run_command.return_value = json.dumps({'state': 'OPEN', 'mergedAt': None})
        self.github_ops.get_pr_actual_state(42)

        args = mock_run_command.call_args[0][0]
        self.assertIn('--repo', args)
        repo_index = args.index('--repo')
        self.assertEqual(args[repo_index + 1], 'test-owner/test-repo')


if __name__ == '__main__':
    unittest.main()
