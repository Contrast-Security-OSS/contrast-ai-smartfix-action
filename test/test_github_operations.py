#!/usr/bin/env python3

import unittest
from unittest.mock import patch, MagicMock
import json
from src.github.github_operations import GitHubOperations


class TestGitHubOperations(unittest.TestCase):
    """Test cases for GitHubOperations class."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock the config to avoid import issues
        with patch('src.github.github_operations.get_config') as mock_config:
            mock_config.return_value = MagicMock(
                GITHUB_TOKEN="test-token",
                testing=True,
                coding_agent=None
            )
            self.github_ops = GitHubOperations()

    def test_get_gh_env(self):
        """Test getting GitHub environment."""
        result = self.github_ops.get_gh_env()
        self.assertIn("GITHUB_TOKEN", result)
        self.assertEqual(result["GITHUB_TOKEN"], "test-token")

    def test_generate_label_details(self):
        """Test label details generation."""
        vuln_uuid = "test-uuid-123"
        label_name, description, color = self.github_ops.generate_label_details(vuln_uuid)

        expected_name = "contrast-vuln-id:VULN-test-uuid-123"
        expected_desc = "Vulnerability identified by Contrast AI SmartFix"
        expected_color = "ff0000"

        self.assertEqual(label_name, expected_name)
        self.assertEqual(description, expected_desc)
        self.assertEqual(color, expected_color)

    def test_generate_pr_title(self):
        """Test PR title generation."""
        result = self.github_ops.generate_pr_title("SQL Injection vulnerability")
        expected = "Fix: SQL Injection vulnerability"
        self.assertEqual(result, expected)

    @patch('src.github.github_operations.run_command')
    def test_check_issues_enabled_true(self, mock_run_command):
        """Test checking if issues are enabled (true case)."""
        mock_run_command.return_value = "[]"  # Empty list means issues are enabled
        result = self.github_ops.check_issues_enabled()
        self.assertTrue(result)

    @patch('src.github.github_operations.run_command')
    def test_check_issues_enabled_false(self, mock_run_command):
        """Test checking if issues are enabled (false case)."""
        mock_run_command.return_value = None  # None means command failed (issues disabled)
        result = self.github_ops.check_issues_enabled()
        self.assertFalse(result)

    @patch('src.github.github_operations.run_command')
    def test_get_pr_changed_files_count_success(self, mock_run_command):
        """Test getting PR changed files count successfully."""
        mock_run_command.return_value = "5"
        result = self.github_ops.get_pr_changed_files_count(123)
        self.assertEqual(result, 5)

    @patch('src.github.github_operations.run_command')
    def test_get_pr_changed_files_count_failure(self, mock_run_command):
        """Test getting PR changed files count with failure."""
        mock_run_command.return_value = None
        result = self.github_ops.get_pr_changed_files_count(123)
        self.assertEqual(result, -1)

    @patch('src.github.github_operations.run_command')
    def test_ensure_label_exists(self, mock_run_command):
        """Test ensuring label exists when it already exists."""
        # Mock label list response showing label exists
        mock_run_command.return_value = json.dumps([
            {"name": "smartfix-id:test-uuid"},
            {"name": "other-label"}
        ])

        result = self.github_ops.ensure_label("smartfix-id:test-uuid", "Test description", "0052cc")
        self.assertTrue(result)

    @patch('subprocess.run')
    @patch('src.github.github_operations.run_command')
    def test_ensure_label_creates_new(self, mock_run_command, mock_subprocess_run):
        """Test ensuring label creates new label when it doesn't exist."""
        # First call returns empty list (no existing labels)
        mock_run_command.return_value = json.dumps([])
        # subprocess.run for label creation succeeds
        mock_subprocess_run.return_value = MagicMock(returncode=0)

        result = self.github_ops.ensure_label("new-label", "New description", "ff0000")
        self.assertTrue(result)

    @patch('src.github.github_operations.run_command')
    def test_find_issue_with_label_found(self, mock_run_command):
        """Test finding issue with label when issue exists."""
        mock_run_command.return_value = json.dumps([
            {"number": 42},
            {"number": 43}
        ])

        result = self.github_ops.find_issue_with_label("test-label")
        self.assertEqual(result, 42)  # Should return first issue number

    @patch('src.github.github_operations.run_command')
    def test_find_issue_with_label_not_found(self, mock_run_command):
        """Test finding issue with label when no issue exists."""
        mock_run_command.return_value = json.dumps([])

        result = self.github_ops.find_issue_with_label("nonexistent-label")
        self.assertIsNone(result)

    @patch('src.github.github_operations.run_command')
    def test_check_pr_status_for_label_open(self, mock_run_command):
        """Test checking PR status for label (open state)."""
        mock_run_command.return_value = json.dumps([
            {"number": 123}
        ])

        result = self.github_ops.check_pr_status_for_label("test-label")
        self.assertEqual(result, "OPEN")

    @patch('src.github.github_operations.run_command')
    def test_check_pr_status_for_label_none(self, mock_run_command):
        """Test checking PR status for label when no PR exists."""
        # Return empty for both open and merged PR checks
        mock_run_command.side_effect = [json.dumps([]), json.dumps([])]

        result = self.github_ops.check_pr_status_for_label("nonexistent-label")
        self.assertEqual(result, "NONE")

    @patch('src.github.github_operations.run_command')
    def test_count_open_prs_with_prefix(self, mock_run_command):
        """Test counting open PRs with label prefix."""
        mock_run_command.return_value = json.dumps([
            {"labels": [{"name": "smartfix-id:123"}, {"name": "bug"}]},
            {"labels": [{"name": "smartfix-id:456"}]},
            {"labels": [{"name": "enhancement"}]},
            {"labels": [{"name": "smartfix-id:789"}, {"name": "documentation"}]}
        ])

        result = self.github_ops.count_open_prs_with_prefix("smartfix-id:", "test-remediation-id")
        self.assertEqual(result, 3)  # Three PRs have smartfix-id: labels

    @patch('subprocess.run')
    @patch('src.github.github_operations.run_command')
    def test_add_labels_to_pr_success(self, mock_run_command, mock_subprocess_run):
        """Test adding labels to PR successfully."""
        # Mock ensure_label checking for existing labels
        mock_run_command.side_effect = [
            json.dumps([]),  # First label doesn't exist
            json.dumps([]),  # Second label doesn't exist
            "Success"  # Final add labels command
        ]
        mock_subprocess_run.return_value = MagicMock(returncode=0)

        result = self.github_ops.add_labels_to_pr(123, ["label1", "label2"])
        self.assertTrue(result)

    @patch('subprocess.run')
    @patch('src.github.github_operations.run_command')
    def test_add_labels_to_pr_failure(self, mock_run_command, mock_subprocess_run):
        """Test adding labels to PR with failure."""
        # Mock ensure_label succeeding (label list + create), but final add_labels failing
        mock_run_command.side_effect = [
            json.dumps([]),  # Label check for label1
            None  # Add labels command fails (raises exception)
        ]
        mock_subprocess_run.return_value = MagicMock(returncode=0)

        # The final add_labels command should raise an exception and be caught
        with patch('src.github.github_operations.run_command', side_effect=[
            json.dumps([]),  # Label check
            Exception("Failed to add labels")  # Final command fails
        ]):
            result = self.github_ops.add_labels_to_pr(123, ["label1"])
            self.assertFalse(result)

    @patch('src.github.github_operations.run_command')
    def test_get_issue_comments_all(self, mock_run_command):
        """Test getting all issue comments."""
        # jq filter returns the comments array directly (sorted by createdAt reversed)
        mock_comments = [
            {"body": "Comment 2", "author": {"login": "user2"}, "createdAt": "2025-01-02"},
            {"body": "Comment 1", "author": {"login": "user1"}, "createdAt": "2025-01-01"}
        ]
        mock_run_command.return_value = json.dumps(mock_comments)

        result = self.github_ops.get_issue_comments(123)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["body"], "Comment 2")  # Most recent first

    @patch('src.github.github_operations.run_command')
    def test_get_issue_comments_filtered(self, mock_run_command):
        """Test getting issue comments filtered by author."""
        # jq filter only returns comments from user1 (sorted by createdAt reversed)
        mock_comments = [
            {"body": "Comment 3", "author": {"login": "user1"}, "createdAt": "2025-01-03"},
            {"body": "Comment 1", "author": {"login": "user1"}, "createdAt": "2025-01-01"}
        ]
        mock_run_command.return_value = json.dumps(mock_comments)

        result = self.github_ops.get_issue_comments(123, author="user1")
        self.assertEqual(len(result), 2)  # Only comments from user1
        self.assertEqual(result[0]["body"], "Comment 3")  # Most recent first

    def test_extract_issue_number_from_branch(self):
        """Test extracting issue number from branch name (moved from test_git_operations.py)."""
        test_cases = [
            ("copilot/fix-123", 123),
            ("claude/issue-456-20251211-1430", 456),
            ("copilot/fix-789", 789),
            ("no-issue-here", None),
            ("smartfix-abc-issue", None),
            ("claude/issue-abc-20251211-1430", None),  # Invalid: non-numeric issue
        ]

        for branch_name, expected in test_cases:
            with self.subTest(branch=branch_name):
                result = self.github_ops.extract_issue_number_from_branch(branch_name)
                self.assertEqual(result, expected)

    @patch('src.github.github_operations.debug_log')
    @patch('src.github.github_operations.run_command')
    def test_get_copilot_workflow_run_id_success(self, mock_run_command, mock_debug_log):
        """Test getting Copilot workflow run ID and branch successfully."""
        mock_workflow_data = json.dumps([
            {
                "databaseId": 12345,
                "status": "completed",
                "event": "issues",
                "createdAt": "2026-01-09T15:00:00Z",
                "conclusion": "success",
                "headBranch": "copilot/fix-semantic-auth-bug"
            }
        ])
        mock_run_command.return_value = mock_workflow_data

        run_id, head_branch = self.github_ops.get_copilot_workflow_run_id(issue_number=123)

        self.assertEqual(run_id, 12345)
        self.assertEqual(head_branch, "copilot/fix-semantic-auth-bug")

    @patch('src.github.github_operations.debug_log')
    @patch('src.github.github_operations.run_command')
    def test_get_copilot_workflow_run_id_not_found(self, mock_run_command, mock_debug_log):
        """Test when no Copilot workflow run is found."""
        mock_run_command.return_value = json.dumps([])

        run_id, head_branch = self.github_ops.get_copilot_workflow_run_id(issue_number=999)

        self.assertIsNone(run_id)
        self.assertIsNone(head_branch)

    @patch('src.github.github_operations.debug_log')
    @patch('src.github.github_operations.run_command')
    def test_get_copilot_workflow_run_id_no_head_branch(self, mock_run_command, mock_debug_log):
        """Test when workflow run exists but has no headBranch."""
        mock_workflow_data = json.dumps([
            {
                "databaseId": 12345,
                "status": "completed",
                "event": "issues",
                "createdAt": "2026-01-09T15:00:00Z",
                "conclusion": "success"
                # headBranch is missing
            }
        ])
        mock_run_command.return_value = mock_workflow_data

        run_id, head_branch = self.github_ops.get_copilot_workflow_run_id(issue_number=123)

        self.assertEqual(run_id, 12345)
        self.assertIsNone(head_branch)

    @patch('src.github.github_operations.debug_log')
    @patch('src.github.github_operations.run_command')
    def test_get_copilot_workflow_run_id_json_error(self, mock_run_command, mock_debug_log):
        """Test handling of JSON decode error."""
        mock_run_command.return_value = "invalid json{"

        run_id, head_branch = self.github_ops.get_copilot_workflow_run_id(issue_number=123)

        self.assertIsNone(run_id)
        self.assertIsNone(head_branch)

    @patch('src.github.github_operations.debug_log')
    @patch('src.github.github_operations.run_command')
    def test_get_copilot_workflow_run_id_command_error(self, mock_run_command, mock_debug_log):
        """Test handling of command execution error."""
        mock_run_command.side_effect = Exception("Command failed")

        run_id, head_branch = self.github_ops.get_copilot_workflow_run_id(issue_number=123)

        self.assertIsNone(run_id)
        self.assertIsNone(head_branch)

    @patch('src.github.github_operations.debug_log')
    @patch('src.github.github_operations.run_command')
    def test_get_copilot_workflow_run_id_multiple_workflows(self, mock_run_command, mock_debug_log):
        """Test that most recent workflow is selected when multiple exist."""
        mock_workflow_data = json.dumps([
            {
                "databaseId": 99999,
                "status": "completed",
                "createdAt": "2026-01-09T15:30:00Z",  # Most recent
                "headBranch": "copilot/fix-latest-issue"
            },
            {
                "databaseId": 12345,
                "status": "completed",
                "createdAt": "2026-01-09T15:00:00Z",  # Older
                "headBranch": "copilot/fix-older-issue"
            }
        ])
        mock_run_command.return_value = mock_workflow_data

        run_id, head_branch = self.github_ops.get_copilot_workflow_run_id(issue_number=123)

        # Should select the most recent (first in list)
        self.assertEqual(run_id, 99999)
        self.assertEqual(head_branch, "copilot/fix-latest-issue")


if __name__ == '__main__':
    unittest.main()
