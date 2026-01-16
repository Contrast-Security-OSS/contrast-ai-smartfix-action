#!/usr/bin/env python3

import unittest
from unittest.mock import patch, MagicMock
import json
from src.github.github_operations import GitHubOperations
from src.smartfix.shared.failure_categories import FailureCategory


class TestGitHubOperations(unittest.TestCase):
    """Test cases for GitHubOperations class."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock the config to avoid import issues
        with patch('src.github.github_operations.get_config') as mock_config:
            mock_config.return_value = MagicMock(
                GITHUB_TOKEN="test-token",
                GITHUB_REPOSITORY="test-owner/test-repo",
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

    @patch('src.github.github_operations.error_exit')
    @patch('src.github.github_operations.log')
    @patch('src.github.github_operations.run_command')
    def test_count_open_prs_with_prefix_auth_error_401(self, mock_run_command, mock_log, mock_error_exit):
        """Test that 401 authentication errors trigger error_exit."""
        mock_run_command.side_effect = Exception("HTTP 401 unauthorized")

        self.github_ops.count_open_prs_with_prefix("smartfix-id:", "test-rem-123")

        # Should call error_exit with proper parameters
        mock_error_exit.assert_called_once_with(
            "test-rem-123",
            FailureCategory.GIT_COMMAND_FAILURE.value
        )
        # Should log the error with sanitized message
        self.assertTrue(mock_log.called)
        # Verify the log contains remediation guidance
        log_calls = [str(call) for call in mock_log.call_args_list]
        self.assertTrue(any('authentication' in str(call).lower() for call in log_calls))

    @patch('src.github.github_operations.error_exit')
    @patch('src.github.github_operations.log')
    @patch('src.github.github_operations.run_command')
    def test_count_open_prs_with_prefix_auth_error_403(self, mock_run_command, mock_log, mock_error_exit):
        """Test that 403 forbidden errors trigger error_exit."""
        mock_run_command.side_effect = Exception("HTTP 403 forbidden")

        self.github_ops.count_open_prs_with_prefix("smartfix-id:", "test-rem-456")

        mock_error_exit.assert_called_once_with(
            "test-rem-456",
            FailureCategory.GIT_COMMAND_FAILURE.value
        )
        self.assertTrue(mock_log.called)

    @patch('src.github.github_operations.error_exit')
    @patch('src.github.github_operations.log')
    @patch('src.github.github_operations.run_command')
    def test_count_open_prs_with_prefix_auth_error_unauthorized_string(self, mock_run_command, mock_log, mock_error_exit):
        """Test that 'unauthorized' string in error message triggers error_exit."""
        mock_run_command.side_effect = Exception("Request failed: unauthorized access")

        self.github_ops.count_open_prs_with_prefix("smartfix-id:", "test-rem-789")

        mock_error_exit.assert_called_once_with(
            "test-rem-789",
            FailureCategory.GIT_COMMAND_FAILURE.value
        )
        self.assertTrue(mock_log.called)

    @patch('src.github.github_operations.error_exit')
    @patch('src.github.github_operations.log')
    @patch('src.github.github_operations.run_command')
    def test_count_open_prs_with_prefix_auth_error_forbidden_string(self, mock_run_command, mock_log, mock_error_exit):
        """Test that 'forbidden' string in error message triggers error_exit."""
        mock_run_command.side_effect = Exception("Access forbidden for this resource")

        self.github_ops.count_open_prs_with_prefix("smartfix-id:", "test-rem-abc")

        mock_error_exit.assert_called_once_with(
            "test-rem-abc",
            FailureCategory.GIT_COMMAND_FAILURE.value
        )
        self.assertTrue(mock_log.called)

    @patch('src.github.github_operations.error_exit')
    @patch('src.github.github_operations.log')
    @patch('src.github.github_operations.run_command')
    def test_count_open_prs_with_prefix_rate_limit_429(self, mock_run_command, mock_log, mock_error_exit):
        """Test that 429 rate limit errors trigger error_exit."""
        mock_run_command.side_effect = Exception("HTTP 429 rate limit exceeded")

        self.github_ops.count_open_prs_with_prefix("smartfix-id:", "test-rem-rate")

        mock_error_exit.assert_called_once_with(
            "test-rem-rate",
            FailureCategory.GIT_COMMAND_FAILURE.value
        )
        # Verify rate limit specific logging
        log_calls = [str(call) for call in mock_log.call_args_list]
        self.assertTrue(any('rate limit' in str(call).lower() for call in log_calls))

    @patch('src.github.github_operations.error_exit')
    @patch('src.github.github_operations.log')
    @patch('src.github.github_operations.run_command')
    def test_count_open_prs_with_prefix_rate_limit_string(self, mock_run_command, mock_log, mock_error_exit):
        """Test that 'rate limit' string in error message triggers error_exit."""
        mock_run_command.side_effect = Exception("API rate limit exceeded, please try again later")

        self.github_ops.count_open_prs_with_prefix("smartfix-id:", "test-rem-rate2")

        mock_error_exit.assert_called_once_with(
            "test-rem-rate2",
            FailureCategory.GIT_COMMAND_FAILURE.value
        )

    @patch('src.github.github_operations.error_exit')
    @patch('src.github.github_operations.log')
    @patch('src.github.github_operations.run_command')
    def test_count_open_prs_with_prefix_generic_error_fails_closed(self, mock_run_command, mock_log, mock_error_exit):
        """Test that generic errors trigger error_exit (fail-closed behavior)."""
        mock_run_command.side_effect = Exception("Network timeout error")

        self.github_ops.count_open_prs_with_prefix("smartfix-id:", "test-rem-generic")

        # Even generic errors should fail closed
        mock_error_exit.assert_called_once_with(
            "test-rem-generic",
            FailureCategory.GIT_COMMAND_FAILURE.value
        )
        self.assertTrue(mock_log.called)

    @patch('src.github.github_operations.error_exit')
    @patch('src.github.github_operations.log')
    @patch('src.github.github_operations.run_command')
    def test_count_open_prs_with_prefix_json_decode_error(self, mock_run_command, mock_log, mock_error_exit):
        """Test that JSON decode errors trigger error_exit."""
        mock_run_command.return_value = "invalid json {{{{"

        self.github_ops.count_open_prs_with_prefix("smartfix-id:", "test-rem-json")

        mock_error_exit.assert_called_once_with(
            "test-rem-json",
            FailureCategory.GIT_COMMAND_FAILURE.value
        )
        # Verify JSON parse error is logged
        log_calls = [str(call) for call in mock_log.call_args_list]
        self.assertTrue(any('json' in str(call).lower() for call in log_calls))

    @patch('src.github.github_operations.run_command')
    def test_find_pr_by_branch_success(self, mock_run_command):
        """Test finding PR by branch name returns PRInfo."""
        mock_pr_data = [{
            "number": 123,
            "url": "https://github.com/test-owner/test-repo/pull/123",
            "title": "Fix authentication bug",
            "headRefName": "copilot/fix-auth-bug",
            "baseRefName": "main",
            "state": "OPEN"
        }]
        mock_run_command.return_value = json.dumps(mock_pr_data)

        result = self.github_ops.find_pr_by_branch("copilot/fix-auth-bug")

        self.assertIsNotNone(result)
        self.assertEqual(result["number"], 123)
        self.assertEqual(result["url"], "https://github.com/test-owner/test-repo/pull/123")
        self.assertEqual(result["title"], "Fix authentication bug")
        self.assertEqual(result["headRefName"], "copilot/fix-auth-bug")
        self.assertEqual(result["baseRefName"], "main")
        self.assertEqual(result["state"], "OPEN")

    @patch('src.github.github_operations.run_command')
    def test_find_pr_by_branch_not_found_empty_array(self, mock_run_command):
        """Test finding PR by branch when no PR exists returns None."""
        mock_run_command.return_value = "[]"

        result = self.github_ops.find_pr_by_branch("nonexistent-branch")

        self.assertIsNone(result)

    @patch('src.github.github_operations.run_command')
    def test_find_pr_by_branch_not_found_empty_output(self, mock_run_command):
        """Test finding PR by branch with empty output returns None."""
        mock_run_command.return_value = ""

        result = self.github_ops.find_pr_by_branch("another-branch")

        self.assertIsNone(result)

    @patch('src.github.github_operations.log')
    @patch('src.github.github_operations.run_command')
    def test_find_pr_by_branch_json_decode_error(self, mock_run_command, mock_log):
        """Test finding PR by branch with invalid JSON returns None."""
        mock_run_command.return_value = "invalid json {{{"

        result = self.github_ops.find_pr_by_branch("test-branch")

        self.assertIsNone(result)
        # Verify error is logged
        log_calls = [str(call) for call in mock_log.call_args_list]
        self.assertTrue(any('json' in str(call).lower() for call in log_calls))

    @patch('src.github.github_operations.run_command')
    def test_find_pr_by_branch_missing_required_fields_no_number(self, mock_run_command):
        """Test finding PR by branch with missing 'number' field returns None."""
        mock_pr_data = [{
            "url": "https://github.com/test-owner/test-repo/pull/123",
            "title": "Test PR",
            "headRefName": "test-branch",
            "baseRefName": "main",
            "state": "OPEN"
        }]
        mock_run_command.return_value = json.dumps(mock_pr_data)

        result = self.github_ops.find_pr_by_branch("test-branch")

        self.assertIsNone(result)

    @patch('src.github.github_operations.run_command')
    def test_find_pr_by_branch_missing_required_fields_no_url(self, mock_run_command):
        """Test finding PR by branch with missing 'url' field returns None."""
        mock_pr_data = [{
            "number": 123,
            "title": "Test PR",
            "headRefName": "test-branch",
            "baseRefName": "main",
            "state": "OPEN"
        }]
        mock_run_command.return_value = json.dumps(mock_pr_data)

        result = self.github_ops.find_pr_by_branch("test-branch")

        self.assertIsNone(result)

    @patch('src.github.github_operations.log')
    @patch('src.github.github_operations.run_command')
    def test_find_pr_by_branch_general_exception(self, mock_run_command, mock_log):
        """Test finding PR by branch with general exception returns None."""
        mock_run_command.side_effect = Exception("Network error occurred")

        result = self.github_ops.find_pr_by_branch("test-branch")

        self.assertIsNone(result)
        # Verify error is logged and sanitized
        log_calls = [str(call) for call in mock_log.call_args_list]
        self.assertTrue(any('error' in str(call).lower() for call in log_calls))

    @patch('src.github.github_operations.log')
    @patch('src.github.github_operations.run_command')
    def test_find_pr_by_branch_error_message_sanitized(self, mock_run_command, mock_log):
        """Test that error messages are sanitized in find_pr_by_branch."""
        mock_run_command.side_effect = Exception("Auth failed with token ghp_1234567890abcdefghijklmnopqrstuvwxyz1234")

        result = self.github_ops.find_pr_by_branch("test-branch")

        self.assertIsNone(result)
        # Verify token is NOT in the logged error message
        log_calls = [str(call) for call in mock_log.call_args_list]
        error_logs = [call for call in log_calls if 'error' in str(call).lower()]
        self.assertTrue(len(error_logs) > 0)
        # Token should be masked in all error logs
        for log_call in error_logs:
            self.assertNotIn('ghp_1234567890abcdefghijklmnopqrstuvwxyz1234', str(log_call))

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
    def test_get_copilot_workflow_metadata_success(self, mock_run_command, mock_debug_log):
        """Test getting Copilot workflow run ID and branch successfully."""
        # Mock issue update time (captures @copilot assignment)
        mock_issue_data = json.dumps({"updatedAt": "2026-01-09T14:00:00Z"})

        # Mock workflow data (workflow created after issue)
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

        # Return issue data on first call, workflow data on second call
        mock_run_command.side_effect = [mock_issue_data, mock_workflow_data]

        run_id, head_branch = self.github_ops.get_copilot_workflow_metadata(issue_number=123)

        self.assertEqual(run_id, 12345)
        self.assertEqual(head_branch, "copilot/fix-semantic-auth-bug")

    @patch('src.github.github_operations.debug_log')
    @patch('src.github.github_operations.run_command')
    def test_get_copilot_workflow_metadata_not_found(self, mock_run_command, mock_debug_log):
        """Test when no Copilot workflow run is found."""
        # Mock issue update time
        mock_issue_data = json.dumps({"updatedAt": "2026-01-09T14:00:00Z"})

        # Mock empty workflow list
        mock_workflow_data = json.dumps([])

        # Return issue data on first call, empty workflow list on second call
        mock_run_command.side_effect = [mock_issue_data, mock_workflow_data]

        run_id, head_branch = self.github_ops.get_copilot_workflow_metadata(issue_number=999)

        self.assertIsNone(run_id)
        self.assertIsNone(head_branch)

    @patch('src.github.github_operations.debug_log')
    @patch('src.github.github_operations.run_command')
    def test_get_copilot_workflow_metadata_no_head_branch(self, mock_run_command, mock_debug_log):
        """Test when workflow run exists but has no headBranch."""
        # Mock issue update time
        mock_issue_data = json.dumps({"updatedAt": "2026-01-09T14:00:00Z"})

        # Mock workflow data (workflow created after issue, but no headBranch)
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

        # Return issue data on first call, workflow data on second call
        mock_run_command.side_effect = [mock_issue_data, mock_workflow_data]

        run_id, head_branch = self.github_ops.get_copilot_workflow_metadata(issue_number=123)

        self.assertEqual(run_id, 12345)
        self.assertIsNone(head_branch)

    @patch('src.github.github_operations.debug_log')
    @patch('src.github.github_operations.run_command')
    def test_get_copilot_workflow_metadata_json_error(self, mock_run_command, mock_debug_log):
        """Test handling of JSON decode error."""
        mock_run_command.return_value = "invalid json{"

        run_id, head_branch = self.github_ops.get_copilot_workflow_metadata(issue_number=123)

        self.assertIsNone(run_id)
        self.assertIsNone(head_branch)

    @patch('src.github.github_operations.debug_log')
    @patch('src.github.github_operations.run_command')
    def test_get_copilot_workflow_metadata_command_error(self, mock_run_command, mock_debug_log):
        """Test handling of command execution error."""
        mock_run_command.side_effect = Exception("Command failed")

        run_id, head_branch = self.github_ops.get_copilot_workflow_metadata(issue_number=123)

        self.assertIsNone(run_id)
        self.assertIsNone(head_branch)

    @patch('src.github.github_operations.debug_log')
    @patch('src.github.github_operations.run_command')
    def test_get_copilot_workflow_metadata_multiple_workflows(self, mock_run_command, mock_debug_log):
        """Test that most recent workflow created after issue is selected when multiple exist."""
        # Mock issue update time (between the two workflows)
        mock_issue_data = json.dumps({"updatedAt": "2026-01-09T15:00:00Z"})

        # Mock multiple workflows - one before and one after issue creation
        mock_workflow_data = json.dumps([
            {
                "databaseId": 99999,
                "status": "completed",
                "createdAt": "2026-01-09T15:30:00Z",  # Most recent, after issue
                "headBranch": "copilot/fix-latest-issue"
            },
            {
                "databaseId": 12345,
                "status": "completed",
                "createdAt": "2026-01-09T14:00:00Z",  # Older, before issue (should be filtered out)
                "headBranch": "copilot/fix-older-issue"
            }
        ])

        # Return issue data on first call, workflow data on second call
        mock_run_command.side_effect = [mock_issue_data, mock_workflow_data]

        run_id, head_branch = self.github_ops.get_copilot_workflow_metadata(issue_number=123)

        # Should select the most recent workflow created after the issue (99999)
        self.assertEqual(run_id, 99999)
        self.assertEqual(head_branch, "copilot/fix-latest-issue")

    @patch('src.github.github_operations.debug_log')
    @patch('src.github.github_operations.run_command')
    def test_get_copilot_workflow_metadata_filters_old_workflows(self, mock_run_command, mock_debug_log):
        """Test that workflows created before the issue are filtered out.

        This test documents the bug fix for AIML-245 where workflows from unrelated
        issues were incorrectly matched when processing multiple issues concurrently.
        """
        # Mock issue update time (captures @copilot assignment)
        mock_issue_data = json.dumps({"updatedAt": "2026-01-12T22:01:25Z"})

        # Mock workflow that was created BEFORE the issue (should be filtered out)
        mock_workflow_data = json.dumps([
            {
                "databaseId": 20936246677,
                "status": "completed",
                "createdAt": "2026-01-12T21:51:46Z",  # Before issue creation
                "headBranch": "copilot/fix-different-issue",
                "conclusion": "success"
            }
        ])

        # Return issue data on first call, workflow data on second call
        mock_run_command.side_effect = [mock_issue_data, mock_workflow_data]

        run_id, head_branch = self.github_ops.get_copilot_workflow_metadata(issue_number=367)

        # Should return None because the only workflow was created before the issue
        self.assertIsNone(run_id)
        self.assertIsNone(head_branch)

    @patch('src.github.github_operations.run_command')
    def test_get_copilot_workflow_metadata_caches_timestamp(self, mock_run_command):
        """Test that issue timestamps are cached to reduce API calls."""
        # Mock issue view and workflow runs
        mock_run_command.side_effect = [
            # First call: issue view
            json.dumps({"updatedAt": "2024-01-10T12:00:00Z"}),
            # First call: workflow runs
            json.dumps([{
                "databaseId": 123,
                "status": "completed",
                "event": "issues",
                "createdAt": "2024-01-10T12:05:00Z",
                "conclusion": "success",
                "headBranch": "copilot/fix-bug"
            }])
        ]

        # First call should fetch from API
        run_id1, branch1 = self.github_ops.get_copilot_workflow_metadata(456)
        self.assertEqual(run_id1, 123)
        self.assertEqual(branch1, "copilot/fix-bug")

        # Verify issue was fetched (2 calls: issue view + workflow runs)
        self.assertEqual(mock_run_command.call_count, 2)

        # Reset mock to ensure no new calls
        mock_run_command.reset_mock()
        mock_run_command.side_effect = [
            # Second call: only workflow runs (no issue view call expected)
            json.dumps([{
                "databaseId": 124,
                "status": "completed",
                "event": "issues",
                "createdAt": "2024-01-10T12:10:00Z",
                "conclusion": "success",
                "headBranch": "copilot/fix-another-bug"
            }])
        ]

        # Second call should use cached timestamp
        run_id2, branch2 = self.github_ops.get_copilot_workflow_metadata(456)
        self.assertEqual(run_id2, 124)
        self.assertEqual(branch2, "copilot/fix-another-bug")

        # Verify only 1 call (workflow runs, no issue view)
        self.assertEqual(mock_run_command.call_count, 1)

    @patch('src.github.github_operations.run_command')
    def test_issue_timestamp_cache_survives_workflow_errors(self, mock_run_command):
        """Test that cached timestamp is used even when workflow fetch fails."""
        # First call: success
        mock_run_command.side_effect = [
            json.dumps({"updatedAt": "2024-01-10T12:00:00Z"}),
            json.dumps([{"databaseId": 123, "createdAt": "2024-01-10T12:05:00Z", "headBranch": "test"}])
        ]
        run_id1, _ = self.github_ops.get_copilot_workflow_metadata(789)
        self.assertEqual(run_id1, 123)

        # Second call: workflow fetch fails, but should still use cached timestamp
        mock_run_command.reset_mock()
        mock_run_command.side_effect = Exception("API rate limit")

        run_id2, branch2 = self.github_ops.get_copilot_workflow_metadata(789)

        # Should return None due to workflow error, but cache was used
        self.assertIsNone(run_id2)
        self.assertIsNone(branch2)
        # Verify only 1 call was made (workflow fetch failed, no issue view)
        self.assertEqual(mock_run_command.call_count, 1)

    @patch('src.github.github_operations.log')
    @patch('src.github.github_operations.error_exit')
    def test_log_copilot_assignment_error_in_testing_mode(self, mock_error_exit, mock_log):
        """Test log_copilot_assignment_error in testing mode does not exit."""
        # Config already has testing=True from setUp
        error = Exception("Copilot not found")

        self.github_ops.log_copilot_assignment_error(123, error, "smartfix-id:test-rem-123")

        # Should log but NOT call error_exit in testing mode
        self.assertTrue(mock_log.called)
        mock_error_exit.assert_not_called()

    @patch('src.github.github_operations.run_command')
    def test_watch_github_action_run_success(self, mock_run_command):
        """Test watching GitHub action run that succeeds."""
        mock_run_command.return_value = "Run completed successfully"

        result = self.github_ops.watch_github_action_run(12345)

        self.assertTrue(result)
        mock_run_command.assert_called_once()

    @patch('src.github.github_operations.run_command')
    def test_watch_github_action_run_failure(self, mock_run_command):
        """Test watching GitHub action run that fails."""
        mock_run_command.side_effect = Exception("Run failed")

        result = self.github_ops.watch_github_action_run(12345)

        self.assertFalse(result)

    @patch('src.github.github_operations.run_command')
    def test_get_claude_workflow_run_id_found(self, mock_run_command):
        """Test getting Claude workflow run ID when found."""
        mock_run_data = {
            "databaseId": 98765,
            "event": "issues",
            "status": "in_progress",
            "createdAt": "2025-01-06T10:00:00Z",
            "conclusion": None
        }
        mock_run_command.return_value = json.dumps(mock_run_data)

        result = self.github_ops.get_claude_workflow_run_id()

        self.assertEqual(result, 98765)

    @patch('src.github.github_operations.run_command')
    def test_get_claude_workflow_run_id_not_found(self, mock_run_command):
        """Test getting Claude workflow run ID when none found."""
        mock_run_command.return_value = "[]"

        result = self.github_ops.get_claude_workflow_run_id()

        self.assertIsNone(result)

    @patch('src.github.github_operations.run_command')
    def test_get_latest_branch_by_pattern_found(self, mock_run_command):
        """Test getting latest branch matching pattern when found."""
        mock_graphql_response = {
            "data": {
                "repository": {
                    "refs": {
                        "nodes": [
                            {"name": "claude/issue-123-20251211-1430", "target": {"committedDate": "2025-12-11T14:30:00Z"}},
                            {"name": "claude/issue-123-20251210-1000", "target": {"committedDate": "2025-12-10T10:00:00Z"}},
                            {"name": "main", "target": {"committedDate": "2025-12-09T12:00:00Z"}}
                        ]
                    }
                }
            }
        }
        mock_run_command.return_value = json.dumps(mock_graphql_response)

        result = self.github_ops.get_latest_branch_by_pattern(r'^claude/issue-123-')

        self.assertEqual(result, "claude/issue-123-20251211-1430")

    @patch('src.github.github_operations.run_command')
    def test_get_latest_branch_by_pattern_not_found(self, mock_run_command):
        """Test getting latest branch matching pattern when none match."""
        mock_graphql_response = {
            "data": {
                "repository": {
                    "refs": {
                        "nodes": [
                            {"name": "main", "target": {"committedDate": "2025-12-09T12:00:00Z"}},
                            {"name": "develop", "target": {"committedDate": "2025-12-08T10:00:00Z"}}
                        ]
                    }
                }
            }
        }
        mock_run_command.return_value = json.dumps(mock_graphql_response)

        result = self.github_ops.get_latest_branch_by_pattern(r'^claude/issue-999-')

        self.assertIsNone(result)

    @patch('tempfile.NamedTemporaryFile')
    @patch('os.path.exists')
    @patch('os.path.getsize')
    @patch('os.remove')
    @patch('src.github.github_operations.run_command')
    def test_create_claude_pr_success(self, mock_run_command, mock_remove, mock_getsize, mock_exists, mock_tempfile):
        """Test creating Claude PR successfully."""
        # Mock temp file
        mock_temp = MagicMock()
        mock_temp.name = "/tmp/test_pr_body.md"
        mock_temp.__enter__ = MagicMock(return_value=mock_temp)
        mock_temp.__exit__ = MagicMock(return_value=False)
        mock_tempfile.return_value = mock_temp

        # Mock file operations
        mock_exists.return_value = True
        mock_getsize.return_value = 1000

        # Mock PR creation command
        mock_run_command.return_value = "https://github.com/test/repo/pull/123"

        result = self.github_ops.create_claude_pr(
            "Fix: Test Issue",
            "This is a test PR body",
            "main",
            "claude/issue-123-20251211-1430"
        )

        self.assertEqual(result, "https://github.com/test/repo/pull/123")
        mock_remove.assert_called_once()

    @patch('tempfile.NamedTemporaryFile')
    @patch('os.path.exists')
    @patch('os.path.getsize')
    @patch('os.remove')
    @patch('subprocess.run')
    @patch('src.github.github_operations.run_command')
    def test_create_claude_pr_truncates_large_body(self, mock_run_command, mock_subprocess_run, mock_remove, mock_getsize, mock_exists, mock_tempfile):
        """Test creating Claude PR truncates body over 32000 chars."""
        # Mock temp file
        mock_temp = MagicMock()
        mock_temp.name = "/tmp/test_pr_body.md"
        mock_temp.__enter__ = MagicMock(return_value=mock_temp)
        mock_temp.__exit__ = MagicMock(return_value=False)
        mock_tempfile.return_value = mock_temp

        mock_exists.return_value = True
        mock_getsize.return_value = 1000
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="gh version 2.0.0")
        mock_run_command.return_value = "https://github.com/test/repo/pull/456"

        # Create body larger than 32000 chars
        large_body = "x" * 35000

        result = self.github_ops.create_claude_pr("Title", large_body, "main", "test-branch")

        # Check that write was called with truncated content
        written_content = "".join([call[0][0] for call in mock_temp.write.call_args_list])
        self.assertLess(len(written_content), 33000)  # Should be truncated + message
        self.assertIn("truncated", written_content.lower())
        self.assertEqual(result, "https://github.com/test/repo/pull/456")

    @patch('src.github.github_operations.run_command')
    def test_create_issue_with_issues_disabled(self, mock_run_command):
        """Test creating issue when GitHub Issues are disabled."""
        # Mock check_issues_enabled to return False
        mock_run_command.return_value = None  # This makes check_issues_enabled return False

        result = self.github_ops.create_issue(
            "Test Issue",
            "Test body",
            "contrast-vuln-id:VULN-123",
            "smartfix-id:REM-456"
        )

        self.assertIsNone(result)

    @patch('subprocess.run')
    @patch('src.github.github_operations.run_command')
    def test_create_issue_success_without_copilot(self, mock_run_command, mock_subprocess_run):
        """Test creating issue successfully without Copilot assignment (Claude Code mode)."""
        from src.smartfix.shared.coding_agents import CodingAgents

        # Set up config for CLAUDE_CODE mode
        with patch('src.github.github_operations.get_config') as mock_config:
            mock_config.return_value = MagicMock(
                GITHUB_TOKEN="test-token",
                GITHUB_REPOSITORY="test-owner/test-repo",
                testing=True,
                CODING_AGENT=CodingAgents.CLAUDE_CODE.name
            )
            github_ops = GitHubOperations()

        # Mock check_issues_enabled (first call returns True)
        # Mock ensure_label calls (two labels, check + create for each)
        # Mock create issue command
        mock_run_command.side_effect = [
            "[]",  # check_issues_enabled
            json.dumps([]),  # ensure_label for vuln (check)
            json.dumps([]),  # ensure_label for remediation (check)
            "https://github.com/test/repo/issues/789"  # create issue
        ]
        mock_subprocess_run.return_value = MagicMock(returncode=0)

        result = github_ops.create_issue(
            "Test Issue",
            "Test body",
            "contrast-vuln-id:VULN-123",
            "smartfix-id:REM-456"
        )

        self.assertEqual(result, 789)

    @patch('src.github.github_operations.run_command')
    def test_find_open_pr_for_issue_copilot_branch(self, mock_run_command):
        """Test finding open PR for issue with Copilot branch pattern."""
        mock_pr_data = [{
            "number": 456,
            "url": "https://github.com/test/repo/pull/456",
            "title": "[WIP] Fix issue",
            "headRefName": "copilot/fix-123",
            "baseRefName": "main",
            "state": "OPEN"
        }]
        mock_run_command.return_value = json.dumps(mock_pr_data)

        result = self.github_ops.find_open_pr_for_issue(123, "Test Issue")

        self.assertIsNotNone(result)
        self.assertEqual(result["number"], 456)

    @patch('src.github.github_operations.run_command')
    def test_find_open_pr_for_issue_claude_branch(self, mock_run_command):
        """Test finding open PR for issue with Claude branch pattern."""
        # First call for copilot pattern returns empty, second for claude pattern returns PR
        mock_pr_data = [{
            "number": 789,
            "url": "https://github.com/test/repo/pull/789",
            "title": "Fix: Test Issue",
            "headRefName": "claude/issue-123-20251211-1430",
            "baseRefName": "main",
            "state": "OPEN"
        }]
        mock_run_command.side_effect = ["[]", json.dumps(mock_pr_data)]

        result = self.github_ops.find_open_pr_for_issue(123, "Test Issue")

        self.assertIsNotNone(result)
        self.assertEqual(result["number"], 789)

    @patch('src.github.github_operations.run_command')
    def test_find_open_pr_for_issue_not_found(self, mock_run_command):
        """Test finding open PR for issue when none exists."""
        # All three search patterns return empty
        mock_run_command.side_effect = ["[]", "[]", "[]"]

        result = self.github_ops.find_open_pr_for_issue(999, "Nonexistent Issue")

        self.assertIsNone(result)

    @patch('src.github.github_operations.run_command')
    def test_reset_issue_with_open_pr(self, mock_run_command):
        """Test reset_issue when issue has open PR (should not reset)."""
        # Mock check_issues_enabled
        mock_run_command.return_value = "[]"

        # Mock find_open_pr_for_issue to return an open PR
        with patch.object(self.github_ops, 'find_open_pr_for_issue') as mock_find_pr:
            mock_find_pr.return_value = {
                "number": 456,
                "url": "https://github.com/test/repo/pull/456"
            }

            result = self.github_ops.reset_issue(123, "Test Issue", "smartfix-id:new-rem")

            self.assertFalse(result)

    @patch('subprocess.run')
    @patch('src.github.github_operations.run_command')
    def test_reset_issue_success_claude_mode(self, mock_run_command, mock_subprocess_run):
        """Test reset_issue successfully in Claude Code mode (adds comment)."""
        from src.smartfix.shared.coding_agents import CodingAgents

        # Set up config for CLAUDE_CODE mode
        with patch('src.github.github_operations.get_config') as mock_config:
            mock_config.return_value = MagicMock(
                GITHUB_TOKEN="test-token",
                GITHUB_REPOSITORY="test-owner/test-repo",
                testing=True,
                CODING_AGENT=CodingAgents.CLAUDE_CODE.name
            )
            github_ops = GitHubOperations()

        # Mock calls in sequence:
        # 1. check_issues_enabled
        # 2. find_open_pr_for_issue (no PR)
        # 3. get current labels
        # 4. ensure_label (check)
        # 5. add label command
        # 6. comment command
        mock_run_command.side_effect = [
            "[]",  # check_issues_enabled
            json.dumps({"labels": [{"name": "smartfix-id:old-rem"}]}),  # get labels
            "Success",  # remove old label
            json.dumps([]),  # ensure_label check
            "Success",  # add new label
            "Comment added"  # add comment
        ]
        mock_subprocess_run.return_value = MagicMock(returncode=0)

        # Mock find_open_pr_for_issue to return None (no open PR)
        with patch.object(github_ops, 'find_open_pr_for_issue') as mock_find_pr:
            mock_find_pr.return_value = None

            result = github_ops.reset_issue(123, "Test Issue", "smartfix-id:new-rem")

            self.assertTrue(result)

    @patch('tempfile.NamedTemporaryFile')
    @patch('os.path.exists')
    @patch('os.path.getsize')
    @patch('os.remove')
    @patch('subprocess.run')
    @patch('src.github.github_operations.run_command')
    def test_create_pr_success(self, mock_run_command, mock_subprocess_run, mock_remove, mock_getsize, mock_exists, mock_tempfile):
        """Test creating PR successfully."""
        # Mock temp file
        mock_temp = MagicMock()
        mock_temp.name = "/tmp/test_pr_body.md"
        mock_temp.__enter__ = MagicMock(return_value=mock_temp)
        mock_temp.__exit__ = MagicMock(return_value=False)
        mock_tempfile.return_value = mock_temp

        # Mock file operations
        mock_exists.return_value = True
        mock_getsize.return_value = 1000

        # Mock version check, PR creation
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="gh version 2.0.0")
        mock_run_command.return_value = "https://github.com/test/repo/pull/123"

        # Mock git_ops.get_branch_name
        with patch.object(self.github_ops.git_ops, 'get_branch_name') as mock_get_branch:
            mock_get_branch.return_value = "copilot/fix-issue-789"

            # Mock add_labels_to_pr
            with patch.object(self.github_ops, 'add_labels_to_pr') as mock_add_labels:
                mock_add_labels.return_value = True

                result = self.github_ops.create_pr(
                    "Fix: Test Issue",
                    "This is a test PR body",
                    "test-rem-123",
                    "main",
                    "contrast-vuln-id:VULN-123"
                )

                self.assertEqual(result, "https://github.com/test/repo/pull/123")
                mock_add_labels.assert_called_once_with(123, ["contrast-vuln-id:VULN-123"])

    @patch('tempfile.NamedTemporaryFile')
    @patch('os.path.exists')
    @patch('os.path.getsize')
    @patch('os.remove')
    @patch('subprocess.run')
    @patch('src.github.github_operations.run_command')
    def test_create_pr_truncates_large_body(self, mock_run_command, mock_subprocess_run, mock_remove, mock_getsize, mock_exists, mock_tempfile):
        """Test creating PR truncates body over 32000 chars."""
        # Mock temp file
        mock_temp = MagicMock()
        mock_temp.name = "/tmp/test_pr_body.md"
        mock_temp.__enter__ = MagicMock(return_value=mock_temp)
        mock_temp.__exit__ = MagicMock(return_value=False)
        mock_tempfile.return_value = mock_temp

        mock_exists.return_value = True
        mock_getsize.return_value = 1000
        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="gh version 2.0.0")
        mock_run_command.return_value = "https://github.com/test/repo/pull/456"

        # Mock git_ops.get_branch_name
        with patch.object(self.github_ops.git_ops, 'get_branch_name') as mock_get_branch:
            mock_get_branch.return_value = "copilot/fix-issue-999"

            with patch.object(self.github_ops, 'add_labels_to_pr'):
                # Create body larger than 32000 chars
                large_body = "x" * 35000

                result = self.github_ops.create_pr("Title", large_body, "rem-456", "main", "label1")

                # Check that write was called with truncated content
                written_content = "".join([call[0][0] for call in mock_temp.write.call_args_list])
                self.assertLess(len(written_content), 33000)  # Should be truncated + disclaimer
                self.assertIn("truncated", written_content.lower())
                self.assertEqual(result, "https://github.com/test/repo/pull/456")

    @patch('subprocess.run')
    @patch('src.github.github_operations.run_command')
    def test_ensure_label_name_too_long(self, mock_run_command, mock_subprocess_run):
        """Test ensure_label with label name exceeding 50 character limit."""
        # Label name longer than 50 chars
        long_label = "a" * 60

        result = self.github_ops.ensure_label(long_label, "Description", "ff0000")

        self.assertFalse(result)

    @patch('src.github.github_operations.run_command')
    def test_check_pr_status_for_label_merged(self, mock_run_command):
        """Test checking PR status for label (merged state)."""
        # First call (open) returns empty, second call (merged) returns PR
        mock_run_command.side_effect = [
            json.dumps([]),  # No open PRs
            json.dumps([{"number": 789}])  # Merged PR found
        ]

        result = self.github_ops.check_pr_status_for_label("test-label")

        self.assertEqual(result, "MERGED")

    @patch('src.github.github_operations.run_command')
    def test_get_issue_comments_no_comments(self, mock_run_command):
        """Test getting issue comments when none exist."""
        mock_run_command.return_value = "[]"

        result = self.github_ops.get_issue_comments(123)

        self.assertEqual(result, [])

    @patch('src.github.github_operations.run_command')
    def test_get_issue_comments_json_decode_error(self, mock_run_command):
        """Test getting issue comments with invalid JSON."""
        mock_run_command.return_value = "invalid json"

        result = self.github_ops.get_issue_comments(123)

        self.assertEqual(result, [])

    def test_extract_issue_number_from_branch_empty(self):
        """Test extracting issue number from empty branch name."""
        result = self.github_ops.extract_issue_number_from_branch("")

        self.assertIsNone(result)

    def test_extract_issue_number_from_branch_none(self):
        """Test extracting issue number from None branch name."""
        result = self.github_ops.extract_issue_number_from_branch(None)

        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
