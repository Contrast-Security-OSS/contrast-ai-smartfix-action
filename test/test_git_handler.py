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
# engineered, modified, repackaged, sold, distributed or otherwise used in a
# way not consistent with the End User License Agreement.
# #L%
#

import unittest
import unittest.mock
from unittest.mock import patch
import json

# Test setup imports (path is set up by conftest.py)
from src.config import get_config, reset_config
from src import git_handler
from src.smartfix.domains.agents import CodingAgents  # noqa: E402


class TestGitHandler(unittest.TestCase):
    """Tests for functions in git_handler.py"""

    def setUp(self):
        """Set up test environment before each test"""
        reset_config()  # Reset the config singleton

    def tearDown(self):
        """Clean up after each test"""
        reset_config()

    @patch('src.git_handler.check_issues_enabled')
    @patch('src.git_handler.run_command')
    @patch('src.git_handler.log')
    @patch('src.git_handler.debug_log')
    def test_find_issue_with_label_found(self, mock_debug_log, mock_log, mock_run_command, mock_check_issues):
        """Test finding an issue with a specific label when the issue exists"""
        # Setup
        label = "test-label"
        mock_response = json.dumps([{"number": 42, "createdAt": "2025-07-21T12:00:00Z"}])
        mock_run_command.return_value = mock_response
        mock_check_issues.return_value = True

        # Initialize config with testing=True
        _ = get_config(testing=True)

        # Execute
        result = git_handler.find_issue_with_label(label)

        # Assert
        mock_check_issues.assert_called_once()
        mock_run_command.assert_called_once()
        self.assertEqual(42, result)
        mock_debug_log.assert_any_call("Found issue #42 with label: test-label")

    @patch('src.git_handler.check_issues_enabled')
    @patch('src.git_handler.run_command')
    @patch('src.git_handler.log')
    @patch('src.git_handler.debug_log')
    def test_find_issue_with_label_not_found(self, mock_debug_log, mock_log, mock_run_command, mock_check_issues):
        """Test finding an issue with a specific label when no issue exists"""
        # Setup
        label = "test-label"
        mock_run_command.return_value = json.dumps([])
        mock_check_issues.return_value = True

        # Initialize config with testing=True
        _ = get_config(testing=True)

        # Execute
        result = git_handler.find_issue_with_label(label)

        # Assert
        mock_check_issues.assert_called_once()
        mock_run_command.assert_called_once()
        self.assertIsNone(result)
        mock_debug_log.assert_any_call("No issues found with label: test-label")

    @patch('src.git_handler.check_issues_enabled')
    @patch('src.git_handler.run_command')
    @patch('src.git_handler.log')
    def test_find_issue_with_label_error(self, mock_log, mock_run_command, mock_check_issues):
        """Test finding an issue with a specific label when an error occurs"""
        # Setup
        label = "test-label"
        mock_run_command.side_effect = Exception("Mock error")
        mock_check_issues.return_value = True

        # Initialize config with testing=True
        _ = get_config(testing=True)

        # Execute
        result = git_handler.find_issue_with_label(label)

        # Assert
        mock_check_issues.assert_called_once()
        mock_run_command.assert_called_once()
        self.assertIsNone(result)
        mock_log.assert_any_call("Error searching for GitHub issue with label: Mock error", is_error=True)

    @patch('src.git_handler.debug_log')
    @patch('src.git_handler.check_issues_enabled')
    @patch('src.git_handler.run_command')
    @patch('src.git_handler.ensure_label')
    @patch('src.git_handler.log')
    def test_create_issue_success(self, mock_log, mock_ensure_label, mock_run_command, mock_check_issues, mock_debug_log):
        """Test creating a GitHub issue when successful"""
        # Setup
        title = "Test Issue Title"
        body = "Test issue body"
        vuln_label = "contrast-vuln-id:VULN-1234"
        remediation_label = "smartfix-id:5678"

        # Mock successful issue creation with URL returned, then successful assignment
        mock_run_command.side_effect = [
            "https://github.com/mock/repo/issues/42",  # Issue creation response
            ""  # Assignment response (empty string indicates success)
        ]
        mock_ensure_label.return_value = True
        mock_check_issues.return_value = True

        # Initialize config with testing=True
        _ = get_config(testing=True)

        # Execute
        result = git_handler.create_issue(title, body, vuln_label, remediation_label)

        # Assert
        mock_check_issues.assert_called_once()
        self.assertEqual(mock_run_command.call_count, 2)  # Should call run_command twice (create + assign)
        self.assertEqual(42, result)  # Should extract issue number 42 from URL
        mock_log.assert_any_call("Successfully created issue: https://github.com/mock/repo/issues/42")
        mock_log.assert_any_call("Issue number extracted: 42")
        mock_debug_log.assert_any_call("Issue assigned to @Copilot")

    @patch('src.git_handler.check_issues_enabled')
    @patch('src.git_handler.run_command')
    @patch('src.git_handler.ensure_label')
    @patch('src.git_handler.log')
    def test_create_issue_failure(self, mock_log, mock_ensure_label, mock_run_command, mock_check_issues):
        """Test creating a GitHub issue when it fails"""
        # Setup
        title = "Test Issue Title"
        body = "Test issue body"
        vuln_label = "contrast-vuln-id:VULN-1234"
        remediation_label = "smartfix-id:5678"

        # Mock failure during issue creation
        mock_run_command.side_effect = Exception("Mock error")
        mock_ensure_label.return_value = True
        mock_check_issues.return_value = True

        # Initialize config with testing=True
        _ = get_config(testing=True)

        # Execute
        result = git_handler.create_issue(title, body, vuln_label, remediation_label)

        # Assert
        mock_check_issues.assert_called_once()
        mock_run_command.assert_called_once()
        self.assertIsNone(result)
        mock_log.assert_any_call("Failed to create GitHub issue: Mock error", is_error=True)

    @patch('src.git_handler.check_issues_enabled')
    @patch('src.git_handler.run_command')
    @patch('src.git_handler.find_open_pr_for_issue')
    @patch('src.git_handler.ensure_label')
    @patch('src.git_handler.log')
    @patch('src.git_handler.debug_log')
    @patch('src.git_handler.config')
    def test_reset_issue_success(self, mock_config, mock_debug_log, mock_log, mock_ensure_label, mock_find_open_pr, mock_run_command, mock_check_issues):
        """Test resetting a GitHub issue when successful"""
        # Setup
        issue_number = 42
        remediation_label = "smartfix-id:5678"

        # Mock that no open PR exists
        mock_find_open_pr.return_value = None
        mock_check_issues.return_value = True

        # Explicitly configure for SMARTFIX agent
        mock_config.CODING_AGENT = CodingAgents.SMARTFIX.name
        mock_config.GITHUB_REPOSITORY = 'mock/repo'

        # Mock successful issue view with labels
        mock_run_command.side_effect = [
            # First call - issue view response
            json.dumps({"labels": [{"name": "contrast-vuln-id:VULN-1234"}, {"name": "smartfix-id:OLD-REM"}]}),
            # Second call - remove label response
            "",
            # Third call - add label response
            "",
            # Fourth call - unassign response
            "",
            # Fifth call - reassign response
            ""
        ]
        mock_ensure_label.return_value = True

        # Initialize config with testing=True
        _ = get_config(testing=True)

        # Execute
        result = git_handler.reset_issue(issue_number, remediation_label)

        # Assert
        mock_check_issues.assert_called_once()
        self.assertEqual(mock_run_command.call_count, 5)  # Should call run_command 5 times
        self.assertTrue(result)
        mock_debug_log.assert_any_call("Removed existing remediation labels from issue #42")
        mock_log.assert_any_call("Added new remediation label to issue #42")
        mock_debug_log.assert_any_call("Reassigned issue #42 to @Copilot")

    @patch('src.git_handler.check_issues_enabled')
    @patch('src.git_handler.find_open_pr_for_issue')
    @patch('src.git_handler.run_command')
    @patch('src.git_handler.log')
    def test_reset_issue_failure(self, mock_log, mock_run_command, mock_find_pr, mock_check_issues):
        """Test resetting a GitHub issue when it fails"""
        # Setup
        issue_number = 42
        remediation_label = "smartfix-id:5678"
        mock_run_command.side_effect = Exception("Mock error")
        mock_find_pr.return_value = None  # No open PR exists
        mock_check_issues.return_value = True

        # Initialize config with testing=True
        _ = get_config(testing=True)

        # Execute
        result = git_handler.reset_issue(issue_number, remediation_label)

        # Assert
        mock_check_issues.assert_called_once()
        mock_run_command.assert_called_once()
        self.assertFalse(result)
        mock_log.assert_any_call("Failed to reset issue #42: Mock error", is_error=True)

    @patch('src.git_handler.find_open_pr_for_issue')
    @patch('src.git_handler.log')
    def test_reset_issue_with_open_pr(self, mock_log, mock_find_open_pr):
        """Test resetting a GitHub issue when an open PR exists"""
        # Setup
        issue_number = 42
        remediation_label = "smartfix-id:5678"

        # Mock that an open PR exists
        mock_find_open_pr.return_value = {
            "number": 123,
            "url": "https://github.com/mock/repo/pull/123",
            "title": "Fix for issue #42"
        }

        # Initialize config with testing=True
        _ = get_config(testing=True)

        # Execute
        result = git_handler.reset_issue(issue_number, remediation_label)

        # Assert
        mock_find_open_pr.assert_called_once_with(issue_number)
        self.assertFalse(result)
        mock_log.assert_any_call(
            "Cannot reset issue #42 because it has an open PR #123: https://github.com/mock/repo/pull/123",
            is_error=True
        )

    @patch('src.git_handler.check_issues_enabled')
    @patch('src.git_handler.run_command')
    @patch('src.git_handler.find_open_pr_for_issue')
    @patch('src.git_handler.ensure_label')
    @patch('src.git_handler.log')
    @patch('src.git_handler.debug_log')
    @patch('src.git_handler.config')
    def test_reset_issue_claude_code(self, mock_config, mock_debug_log, mock_log, mock_ensure_label, mock_find_open_pr, mock_run_command, mock_check_issues):
        """Test resetting a GitHub issue when using Claude Code agent"""
        # Setup
        issue_number = 42
        remediation_label = "smartfix-id:5678"

        # Mock that no open PR exists
        mock_find_open_pr.return_value = None
        mock_check_issues.return_value = True

        # Configure the mock to use CLAUDE_CODE
        mock_config.CODING_AGENT = CodingAgents.CLAUDE_CODE.name
        mock_config.GITHUB_REPOSITORY = 'mock/repo'

        # Mock successful issue view with labels and other API calls
        mock_run_command.side_effect = [
            # First call - issue view response
            json.dumps({"labels": [{"name": "contrast-vuln-id:VULN-1234"}, {"name": "smartfix-id:OLD-REM"}]}),
            # Second call - remove label response
            "",
            # Third call - add label response
            "",
            # Fourth call - comment with @claude tag
            ""
        ]
        mock_ensure_label.return_value = True

        # Execute
        result = git_handler.reset_issue(issue_number, remediation_label)

        # Assert
        mock_check_issues.assert_called_once()
        self.assertEqual(mock_run_command.call_count, 4)  # Should call run_command 4 times (view, remove label, add label, add comment)
        self.assertTrue(result)

        # Check that Claude-specific logic was executed
        mock_debug_log.assert_any_call("CLAUDE_CODE agent detected need to add a comment and tag @claude for reprocessing")
        mock_log.assert_any_call(f"Added new comment tagging @claude to issue #{issue_number}")

        # Verify the comment command
        comment_command_call = mock_run_command.call_args_list[3]
        comment_command = comment_command_call[0][0]

        # Verify command structure
        self.assertEqual(comment_command[0], "gh")
        self.assertEqual(comment_command[1], "issue")
        self.assertEqual(comment_command[2], "comment")
        self.assertEqual(comment_command[5], str(issue_number))

        # Verify comment body contains '@claude' and the remediation label
        comment_body = comment_command[-1]
        self.assertIn("@claude", comment_body)
        self.assertIn(remediation_label, comment_body)

    @patch('src.git_handler.check_issues_enabled')
    @patch('src.git_handler.run_command')
    @patch('src.git_handler.find_open_pr_for_issue')
    @patch('src.git_handler.ensure_label')
    @patch('src.git_handler.log')
    @patch('src.git_handler.config')
    def test_reset_issue_claude_code_error(self, mock_config, mock_log, mock_ensure_label, mock_find_open_pr, mock_run_command, mock_check_issues):
        """Test resetting a GitHub issue when using Claude Code agent but an error occurs"""
        # Setup
        issue_number = 42
        remediation_label = "smartfix-id:5678"

        # Mock that no open PR exists
        mock_find_open_pr.return_value = None
        mock_check_issues.return_value = True

        # Configure the mock to use CLAUDE_CODE
        mock_config.CODING_AGENT = CodingAgents.CLAUDE_CODE.name
        mock_config.GITHUB_REPOSITORY = 'mock/repo'

        # Mock successful label operations but comment command fails
        mock_run_command.side_effect = [
            # First call - issue view response
            json.dumps({"labels": [{"name": "contrast-vuln-id:VULN-1234"}, {"name": "smartfix-id:OLD-REM"}]}),
            # Second call - remove label response
            "",
            # Third call - add label response
            "",
            # Fourth call - comment command fails
            Exception("Failed to comment")
        ]
        mock_ensure_label.return_value = True

        # Execute
        result = git_handler.reset_issue(issue_number, remediation_label)

        # Assert
        mock_check_issues.assert_called_once()
        self.assertEqual(mock_run_command.call_count, 4)  # Should still call run_command 4 times
        self.assertFalse(result)  # Should return False due to the error

        # Verify error was logged
        mock_log.assert_any_call(f"Failed to reset issue #{issue_number}: Failed to comment", is_error=True)

    @patch('src.git_handler.run_command')
    @patch('src.git_handler.debug_log')
    @patch('src.git_handler.log')
    def test_find_open_pr_for_issue_found(self, mock_log, mock_debug_log, mock_run_command):
        """Test finding a PR for an issue when the PR exists"""
        # Setup
        issue_number = 42
        pr_data = [
            {
                "number": 123,
                "url": "https://github.com/mock/repo/pull/123",
                "title": "Fix bug for issue #42",
                "headRefName": "copilot/fix-42",
                "baseRefName": "main",
                "state": "OPEN"
            }
        ]
        mock_run_command.return_value = json.dumps(pr_data)

        # Initialize config with testing=True
        _ = get_config(testing=True)

        # Execute
        result = git_handler.find_open_pr_for_issue(issue_number)

        # Assert
        self.assertEqual(result, pr_data[0])
        mock_run_command.assert_called_once()
        mock_debug_log.assert_any_call("Searching for open PR related to issue #42")
        mock_log.assert_any_call("Found open PR #123 for issue #42: Fix bug for issue #42")

    @patch('src.git_handler.run_command')
    @patch('src.git_handler.debug_log')
    @patch('src.git_handler.log')
    def test_find_open_pr_for_issue_not_found(self, mock_log, mock_debug_log, mock_run_command):
        """Test finding a PR for an issue when no PR exists"""
        # Setup
        issue_number = 42
        mock_run_command.return_value = "[]"

        # Initialize config with testing=True
        _ = get_config(testing=True)

        # Execute
        result = git_handler.find_open_pr_for_issue(issue_number)

        # Assert
        self.assertIsNone(result)
        mock_run_command.assert_called_once()
        mock_debug_log.assert_any_call("Searching for open PR related to issue #42")
        mock_debug_log.assert_any_call("No open PRs found for issue #42")

    @patch('src.git_handler.debug_log')
    @patch('src.git_handler.run_command')
    @patch('src.git_handler.log')
    def test_find_open_pr_for_issue_error(self, mock_log, mock_run_command, mock_debug_log):
        """Test finding a PR for an issue when an error occurs"""
        # Setup
        issue_number = 42
        mock_run_command.side_effect = Exception("Mock error")

        # Initialize config with testing=True
        _ = get_config(testing=True)

        # Execute
        result = git_handler.find_open_pr_for_issue(issue_number)

        # Assert
        self.assertIsNone(result)
        mock_run_command.assert_called_once()
        mock_debug_log.assert_any_call("Searching for open PR related to issue #42")
        mock_log.assert_any_call("Error searching for PRs related to issue #42: Mock error", is_error=True)

    @patch('src.git_handler.config')
    @patch('src.git_handler.ensure_label')
    @patch('src.git_handler.run_command')
    @patch('src.git_handler.log')
    @patch('src.git_handler.debug_log')
    def test_add_labels_to_pr_success(self, mock_debug_log, mock_log, mock_run_command, mock_ensure_label, mock_config):
        """Test successfully adding labels to a PR"""
        # Setup
        pr_number = 123
        labels = ["contrast-vuln-id:VULN-12345", "smartfix-id:remediation-67890"]
        mock_ensure_label.return_value = True
        mock_run_command.return_value = ""  # Successful command returns empty string

        # Mock config to use test repository
        mock_config.GITHUB_REPOSITORY = "mock/repo"

        # Initialize config with testing=True
        _ = get_config(testing=True)

        # Execute
        result = git_handler.add_labels_to_pr(pr_number, labels)

        # Assert
        self.assertTrue(result)

        # Verify ensure_label was called for each label with correct parameters
        expected_ensure_calls = [
            unittest.mock.call("contrast-vuln-id:VULN-12345", "Vulnerability identified by Contrast", "ff0000"),
            unittest.mock.call("smartfix-id:remediation-67890", "Remediation ID for Contrast vulnerability", "0075ca")
        ]
        mock_ensure_label.assert_has_calls(expected_ensure_calls, any_order=True)

        # Verify run_command was called with correct gh pr edit command
        mock_run_command.assert_called_once()
        call_args = mock_run_command.call_args[0][0]  # First argument (command list)
        self.assertEqual(call_args[0:5], ["gh", "pr", "edit", "--repo", "mock/repo"])
        self.assertEqual(call_args[5], "123")
        self.assertEqual(call_args[6:8], ["--add-label", "contrast-vuln-id:VULN-12345,smartfix-id:remediation-67890"])

        mock_log.assert_any_call("Adding labels to PR #123: ['contrast-vuln-id:VULN-12345', 'smartfix-id:remediation-67890']")
        mock_log.assert_any_call("Successfully added labels to PR #123: ['contrast-vuln-id:VULN-12345', 'smartfix-id:remediation-67890']")

    def test_extract_issue_number_from_branch_success(self):
        """Test extracting issue number from valid copilot branch name"""
        # Test cases with valid branch names
        test_cases = [
            ("copilot/fix-123", 123),
            ("copilot/fix-1", 1),
            ("copilot/fix-999999", 999999),
            ("copilot/fix-42", 42),
        ]

        for branch_name, expected_issue_number in test_cases:
            with self.subTest(branch_name=branch_name):
                result = git_handler.extract_issue_number_from_branch(branch_name)
                self.assertEqual(result, expected_issue_number)

    def test_extract_issue_number_from_branch_invalid(self):
        """Test extracting issue number from invalid branch names"""
        # Test cases with invalid branch names
        invalid_branches = [
            "main",                           # Wrong branch name
            "feature/new-feature",           # Wrong branch name
            "copilot/fix-",                  # Missing issue number
            "copilot/fix-abc",               # Non-numeric issue number
            "copilot/fix-123abc",            # Invalid format
            "copilot/fix-123-extra",         # Extra parts
            "smartfix/remediation-123",      # Different prefix
            "",                              # Empty string
        ]

        for branch_name in invalid_branches:
            with self.subTest(branch_name=branch_name):
                result = git_handler.extract_issue_number_from_branch(branch_name)
                self.assertIsNone(result)

    def test_extract_issue_number_from_branch_edge_cases(self):
        """Test edge cases for extracting issue number from branch name"""
        # Test edge cases
        edge_cases = [
            ("copilot/fix-2147483647", 2147483647),  # Large number (max 32-bit int)
        ]

        for branch_name, expected_issue_number in edge_cases:
            with self.subTest(branch_name=branch_name):
                result = git_handler.extract_issue_number_from_branch(branch_name)
                self.assertEqual(result, expected_issue_number)

    @patch('src.git_handler.ensure_label')
    @patch('src.git_handler.run_command')
    @patch('src.git_handler.log')
    @patch('src.git_handler.debug_log')
    def test_add_labels_to_pr_empty_labels(self, mock_debug_log, mock_log, mock_run_command, mock_ensure_label):
        """Test adding empty labels list to a PR"""
        # Setup
        pr_number = 123
        labels = []

        # Initialize config with testing=True
        _ = get_config(testing=True)

        # Execute
        result = git_handler.add_labels_to_pr(pr_number, labels)

        # Assert
        self.assertTrue(result)
        mock_ensure_label.assert_not_called()
        mock_run_command.assert_not_called()
        mock_debug_log.assert_called_with("No labels provided to add to PR")

    @patch('src.git_handler.ensure_label')
    @patch('src.git_handler.run_command')
    @patch('src.git_handler.log')
    @patch('src.git_handler.debug_log')
    def test_add_labels_to_pr_with_custom_label(self, mock_debug_log, mock_log, mock_run_command, mock_ensure_label):
        """Test adding labels including a custom label type"""
        # Setup
        pr_number = 456
        labels = ["contrast-vuln-id:VULN-99999", "custom-label"]
        mock_ensure_label.return_value = True
        mock_run_command.return_value = ""

        # Initialize config with testing=True
        _ = get_config(testing=True)

        # Execute
        result = git_handler.add_labels_to_pr(pr_number, labels)

        # Assert
        self.assertTrue(result)

        # Verify ensure_label was called with correct parameters for different label types
        expected_ensure_calls = [
            unittest.mock.call("contrast-vuln-id:VULN-99999", "Vulnerability identified by Contrast", "ff0000"),
            unittest.mock.call("custom-label", "Label added by Contrast AI SmartFix", "cccccc")
        ]
        mock_ensure_label.assert_has_calls(expected_ensure_calls, any_order=True)

    @patch('src.git_handler.ensure_label')
    @patch('src.git_handler.run_command')
    @patch('src.git_handler.log')
    @patch('src.git_handler.debug_log')
    def test_add_labels_to_pr_command_failure(self, mock_debug_log, mock_log, mock_run_command, mock_ensure_label):
        """Test adding labels to a PR when the gh command fails"""
        # Setup
        pr_number = 789
        labels = ["test-label"]
        mock_ensure_label.return_value = True
        mock_run_command.side_effect = Exception("Command failed")

        # Initialize config with testing=True
        _ = get_config(testing=True)

        # Execute
        result = git_handler.add_labels_to_pr(pr_number, labels)

        # Assert
        self.assertFalse(result)
        mock_ensure_label.assert_called_once_with("test-label", "Label added by Contrast AI SmartFix", "cccccc")
        mock_run_command.assert_called_once()
        mock_log.assert_any_call("Adding labels to PR #789: ['test-label']")
        mock_log.assert_any_call("Failed to add labels to PR #789: Command failed", is_error=True)

    @patch('src.git_handler.run_command')
    @patch('src.git_handler.get_gh_env')
    @patch('src.git_handler.debug_log')
    def test_get_pr_changed_files_count_success(self, mock_debug_log, mock_get_gh_env, mock_run_command):
        """Test get_pr_changed_files_count when gh command succeeds"""
        from src.config import get_config

        # Setup
        mock_get_gh_env.return_value = {'GITHUB_TOKEN': 'mock-token'}
        mock_run_command.return_value = "3"

        # Initialize config with testing=True
        _ = get_config(testing=True)

        # Execute
        result = git_handler.get_pr_changed_files_count(123)

        # Assert
        self.assertEqual(result, 3)
        mock_run_command.assert_called_once_with(
            ['gh', 'pr', 'view', '123', '--json', 'changedFiles', '--jq', '.changedFiles'],
            env={'GITHUB_TOKEN': 'mock-token'},
            check=False
        )
        mock_debug_log.assert_called_with("PR 123 has 3 changed files")

    @patch('src.git_handler.run_command')
    @patch('src.git_handler.get_gh_env')
    @patch('src.git_handler.debug_log')
    def test_get_pr_changed_files_count_zero_files(self, mock_debug_log, mock_get_gh_env, mock_run_command):
        """Test get_pr_changed_files_count when PR has zero changed files"""
        from src.config import get_config

        # Setup
        mock_get_gh_env.return_value = {'GITHUB_TOKEN': 'mock-token'}
        mock_run_command.return_value = "0"

        # Initialize config with testing=True
        _ = get_config(testing=True)

        # Execute
        result = git_handler.get_pr_changed_files_count(456)

        # Assert
        self.assertEqual(result, 0)
        mock_debug_log.assert_called_with("PR 456 has 0 changed files")

    @patch('src.git_handler.run_command')
    @patch('src.git_handler.get_gh_env')
    @patch('src.git_handler.debug_log')
    def test_get_pr_changed_files_count_command_failure(self, mock_debug_log, mock_get_gh_env, mock_run_command):
        """Test get_pr_changed_files_count when gh command fails"""
        from src.config import get_config

        # Setup
        mock_get_gh_env.return_value = {'GITHUB_TOKEN': 'mock-token'}
        mock_run_command.return_value = None

        # Initialize config with testing=True
        _ = get_config(testing=True)

        # Execute
        result = git_handler.get_pr_changed_files_count(789)

        # Assert
        self.assertEqual(result, -1)
        mock_debug_log.assert_called_with("Failed to get changed files count for PR 789")

    @patch('src.git_handler.run_command')
    @patch('src.git_handler.get_gh_env')
    @patch('src.git_handler.debug_log')
    def test_get_pr_changed_files_count_invalid_response(self, mock_debug_log, mock_get_gh_env, mock_run_command):
        """Test get_pr_changed_files_count when gh returns invalid data"""
        from src.config import get_config

        # Setup
        mock_get_gh_env.return_value = {'GITHUB_TOKEN': 'mock-token'}
        mock_run_command.return_value = "invalid_number"

        # Initialize config with testing=True
        _ = get_config(testing=True)

        # Execute
        result = git_handler.get_pr_changed_files_count(101112)

        # Assert
        self.assertEqual(result, -1)
        mock_debug_log.assert_called_with("Invalid response from gh command for PR 101112: invalid_number")

    @patch('src.git_handler.run_command')
    @patch('src.git_handler.get_gh_env')
    @patch('src.git_handler.debug_log')
    def test_get_pr_changed_files_count_exception(self, mock_debug_log, mock_get_gh_env, mock_run_command):
        """Test get_pr_changed_files_count when an exception occurs"""
        from src.config import get_config

        # Setup
        mock_get_gh_env.return_value = {'GITHUB_TOKEN': 'mock-token'}
        mock_run_command.side_effect = Exception("Network error")

        # Initialize config with testing=True
        _ = get_config(testing=True)

        # Execute
        result = git_handler.get_pr_changed_files_count(131415)

        # Assert
        self.assertEqual(result, -1)
        mock_debug_log.assert_called_with("Error getting changed files count for PR 131415: Network error")

    @patch('src.git_handler.config')
    @patch('src.git_handler.run_command')
    @patch('src.git_handler.get_gh_env')
    @patch('src.git_handler.debug_log')
    def test_check_issues_enabled_success(self, mock_debug_log, mock_get_gh_env, mock_run_command, mock_config):
        """Test check_issues_enabled when Issues are enabled"""
        # Setup
        mock_config.GITHUB_REPOSITORY = 'mock/repo-for-testing'
        mock_get_gh_env.return_value = {'GITHUB_TOKEN': 'mock-token'}
        mock_run_command.return_value = "[]"  # Empty list indicates success

        # Execute
        result = git_handler.check_issues_enabled()

        # Assert
        self.assertTrue(result)
        mock_run_command.assert_called_once_with(
            ['gh', 'issue', 'list', '--repo', 'mock/repo-for-testing', '--limit', '1'],
            env={'GITHUB_TOKEN': 'mock-token'},
            check=False
        )
        mock_debug_log.assert_called_with("GitHub Issues are enabled for this repository")

    @patch('src.git_handler.run_command')
    @patch('src.git_handler.get_gh_env')
    @patch('src.git_handler.debug_log')
    def test_check_issues_enabled_disabled(self, mock_debug_log, mock_get_gh_env, mock_run_command):
        """Test check_issues_enabled when Issues are disabled"""
        from src.config import get_config

        # Setup
        mock_get_gh_env.return_value = {'GITHUB_TOKEN': 'mock-token'}
        mock_run_command.return_value = None  # None indicates command failed

        # Initialize config with testing=True
        _ = get_config(testing=True)

        # Execute
        result = git_handler.check_issues_enabled()

        # Assert
        self.assertFalse(result)
        mock_debug_log.assert_called_with("GitHub Issues appear to be disabled for this repository")

    @patch('src.git_handler.run_command')
    @patch('src.git_handler.get_gh_env')
    @patch('src.git_handler.debug_log')
    def test_check_issues_enabled_exception_issues_disabled(self, mock_debug_log, mock_get_gh_env, mock_run_command):
        """Test check_issues_enabled when exception contains 'issues are disabled'"""
        from src.config import get_config

        # Setup
        mock_get_gh_env.return_value = {'GITHUB_TOKEN': 'mock-token'}
        mock_run_command.side_effect = Exception("Issues are disabled for this repo")

        # Initialize config with testing=True
        _ = get_config(testing=True)

        # Execute
        result = git_handler.check_issues_enabled()

        # Assert
        self.assertFalse(result)
        mock_debug_log.assert_called_with("GitHub Issues are disabled for this repository")

    @patch('src.git_handler.run_command')
    @patch('src.git_handler.get_gh_env')
    @patch('src.git_handler.debug_log')
    def test_check_issues_enabled_exception_other_error(self, mock_debug_log, mock_get_gh_env, mock_run_command):
        """Test check_issues_enabled when exception is not related to disabled Issues"""
        from src.config import get_config

        # Setup
        mock_get_gh_env.return_value = {'GITHUB_TOKEN': 'mock-token'}
        mock_run_command.side_effect = Exception("Network error")

        # Initialize config with testing=True
        _ = get_config(testing=True)

        # Execute
        result = git_handler.check_issues_enabled()

        # Assert
        self.assertTrue(result)
        mock_debug_log.assert_called_with("Error checking if Issues are enabled, assuming they are: Network error")

    @patch('src.git_handler.check_issues_enabled')
    @patch('src.git_handler.run_command')
    @patch('src.git_handler.log')
    @patch('src.git_handler.debug_log')
    def test_find_issue_with_label_issues_disabled(self, mock_debug_log, mock_log, mock_run_command, mock_check_issues):
        """Test finding an issue when Issues are disabled"""
        from src.config import get_config

        # Setup
        label = "test-label"
        mock_check_issues.return_value = False

        # Initialize config with testing=True
        _ = get_config(testing=True)

        # Execute
        result = git_handler.find_issue_with_label(label)

        # Assert
        self.assertIsNone(result)
        mock_check_issues.assert_called_once()
        mock_run_command.assert_not_called()
        mock_log.assert_any_call("GitHub Issues are disabled for this repository. Cannot search for issues.", is_error=True)

    @patch('src.git_handler.check_issues_enabled')
    @patch('src.git_handler.ensure_label')
    @patch('src.git_handler.run_command')
    @patch('src.git_handler.log')
    def test_create_issue_issues_disabled(self, mock_log, mock_run_command, mock_ensure_label, mock_check_issues):
        """Test creating an issue when Issues are disabled"""
        from src.config import get_config

        # Setup
        title = "Test Issue Title"
        body = "Test issue body"
        vuln_label = "contrast-vuln-id:VULN-1234"
        remediation_label = "smartfix-id:5678"
        mock_check_issues.return_value = False

        # Initialize config with testing=True
        _ = get_config(testing=True)

        # Execute
        result = git_handler.create_issue(title, body, vuln_label, remediation_label)

        # Assert
        self.assertIsNone(result)
        mock_check_issues.assert_called_once()
        mock_ensure_label.assert_not_called()
        mock_run_command.assert_not_called()
        mock_log.assert_any_call("GitHub Issues are disabled for this repository. Cannot create issue.", is_error=True)

    @patch('src.git_handler.check_issues_enabled')
    @patch('src.git_handler.find_open_pr_for_issue')
    @patch('src.git_handler.log')
    def test_reset_issue_issues_disabled(self, mock_log, mock_find_open_pr, mock_check_issues):
        """Test resetting an issue when Issues are disabled"""
        from src.config import get_config

        # Setup
        issue_number = 42
        remediation_label = "smartfix-id:5678"
        mock_check_issues.return_value = False

        # Initialize config with testing=True
        _ = get_config(testing=True)

        # Execute
        result = git_handler.reset_issue(issue_number, remediation_label)

        # Assert
        self.assertFalse(result)
        mock_check_issues.assert_called_once()
        mock_find_open_pr.assert_not_called()
        mock_log.assert_any_call("GitHub Issues are disabled for this repository. Cannot reset issue.", is_error=True)


if __name__ == '__main__':
    unittest.main()
