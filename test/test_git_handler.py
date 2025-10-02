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
from unittest.mock import patch, MagicMock
import json

# Test setup imports (path is set up by conftest.py)
from src.config import get_config, reset_config
from src import git_handler
from src.coding_agents import CodingAgents  # noqa: E402


class TestGitHandler(unittest.TestCase):
    """Tests for functions in git_handler.py"""

    def setUp(self):
        """Set up test environment before each test"""
        reset_config()  # Reset the config singleton

    def tearDown(self):
        """Clean up after each test"""
        reset_config()

        # Reset any mock patchers that might be active
        # This prevents mock state from leaking between tests
        try:
            unittest.mock.patch.stopall()
        except Exception:
            pass  # Ignore errors if no patches active

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
        result = git_handler.reset_issue(issue_number, "Test Issue Title", remediation_label)

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
        result = git_handler.reset_issue(issue_number, "Test Issue Title", remediation_label)

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
        result = git_handler.reset_issue(issue_number, "Test Issue Title", remediation_label)

        # Assert
        mock_find_open_pr.assert_called_once_with(issue_number, "Test Issue Title")
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
        result = git_handler.reset_issue(issue_number, "Test Issue Title", remediation_label)

        # Assert
        mock_check_issues.assert_called_once()
        self.assertEqual(mock_run_command.call_count, 4)  # Should call run_command 4 times (view, remove label, add label, add comment)
        self.assertTrue(result)

        # Check that Claude-specific logic was executed
        mock_debug_log.assert_any_call("Claude code agent detected need to add a comment and tag @claude for reprocessing")
        mock_log.assert_any_call(f"Added new comment tagging @claude to issue #{issue_number}")

        # Verify the comment command
        comment_command_call = mock_run_command.call_args_list[3]
        comment_command = comment_command_call[0][0]

        # Verify command structure
        self.assertEqual(comment_command[0], "gh")
        self.assertEqual(comment_command[1], "issue")
        self.assertEqual(comment_command[2], "comment")
        self.assertEqual(comment_command[3], str(issue_number))
        self.assertEqual(comment_command[4], "--repo")
        self.assertEqual(comment_command[5], "mock/repo")

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
        result = git_handler.reset_issue(issue_number, "Test Issue Title", remediation_label)

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
        result = git_handler.find_open_pr_for_issue(issue_number, "Test Issue Title")

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
        result = git_handler.find_open_pr_for_issue(issue_number, "Test Issue Title")

        # Assert
        self.assertIsNone(result)
        # The modified find_open_pr_for_issue function now makes up to 3 calls to run_command
        # First for Copilot branch pattern, second for Claude branch pattern, and third for Copilot title pattern if the first two fail
        self.assertLessEqual(mock_run_command.call_count, 3)
        mock_debug_log.assert_any_call("Searching for open PR related to issue #42")
        mock_debug_log.assert_any_call("No open PRs found for issue #42 with either Copilot or Claude branch pattern")

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
        result = git_handler.find_open_pr_for_issue(issue_number, "Test Issue Title")

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

    def test_extract_issue_number_from_branch_copilot_success(self):
        """Test extracting issue number from valid copilot branch name"""
        # Test cases with valid Copilot branch names
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

    def test_extract_issue_number_from_branch_claude_success(self):
        """Test extracting issue number from valid Claude Code branch name"""
        # Test cases with valid Claude Code branch names - format: claude/issue-<issue_number>-YYYYMMDD-HHMM
        test_cases = [
            ("claude/issue-123-20250908-1723", 123),
            ("claude/issue-1-20250909-0930", 1),
            ("claude/issue-999999-20251010-0800", 999999),
            ("claude/issue-75-20250725-1212", 75),
        ]

        for branch_name, expected_issue_number in test_cases:
            with self.subTest(branch_name=branch_name):
                result = git_handler.extract_issue_number_from_branch(branch_name)
                self.assertEqual(result, expected_issue_number)

    def test_extract_issue_number_from_branch_invalid(self):
        """Test extracting issue number from invalid branch names"""
        # Test cases with invalid branch names
        invalid_branches = [
            "main",                              # Wrong branch name
            "feature/new-feature",               # Wrong branch name
            "copilot/fix-",                      # Missing issue number
            "copilot/fix-abc",                   # Non-numeric issue number
            "copilot/fix-123abc",                # Invalid format
            "copilot/fix-123-extra",             # Extra parts
            "claude/issue-",                     # Missing issue number
            "claude/issue-abc-20250908-1723",    # Non-numeric issue number
            "claude/issue-123-20250908",         # Missing time part
            "claude/issue-123-YYYYMMDD-HHMM",    # Literal date placeholder
            "claude/issue-123-20250908-172",     # Incomplete time format
            "claude/issue-123-202509081723",     # No hyphen separator
            "smartfix/remediation-123",          # Different prefix
            "",                                  # Empty string
        ]

        for branch_name in invalid_branches:
            with self.subTest(branch_name=branch_name):
                result = git_handler.extract_issue_number_from_branch(branch_name)
                self.assertIsNone(result)

    def test_extract_issue_number_from_branch_edge_cases(self):
        """Test edge cases for extracting issue number from branch name"""
        # Test edge cases
        edge_cases = [
            ("copilot/fix-2147483647", 2147483647),   # Large number (max 32-bit int) - Copilot
            ("claude/issue-2147483647-20250908-1723", 2147483647),  # Large number (max 32-bit int) - Claude
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
        result = git_handler.reset_issue(issue_number, "Test Issue Title", remediation_label)

        # Assert
        self.assertFalse(result)
        mock_check_issues.assert_called_once()
        mock_find_open_pr.assert_not_called()
        mock_log.assert_any_call("GitHub Issues are disabled for this repository. Cannot reset issue.", is_error=True)

    @patch('src.git_handler.run_command')
    @patch('src.git_handler.get_gh_env')
    @patch('src.git_handler.debug_log')
    @patch('src.git_handler.log')
    def test_get_issue_comments_success(self, mock_log, mock_debug_log, mock_get_gh_env, mock_run_command):
        """Test getting comments from an issue when successful"""
        # Setup
        issue_number = 94
        mock_get_gh_env.return_value = {'GITHUB_TOKEN': 'mock-token'}

        # Sample JSON response based on example provided
        comment_data = [
            {
                "author": {
                    "login": "claude"
                },
                "authorAssociation": "NONE",
                "body": (
                    "Claude Code is working… "
                    "<img src=\"https://github.com/user-attachments/assets/5ac382c7-e004-429b-8e35-7feb3e8f9c6f\" "
                    "width=\"14px\" height=\"14px\" style=\"vertical-align: middle; margin-left: 4px;\" />\n\n"
                    "I'll analyze this and get back to you.\n\n"
                    "[View job run](https://github.com/dougj-contrast/django_vuln/actions/runs/17774252155)"
                ),
                "createdAt": "2025-09-16T17:40:22Z",
                "id": "IC_kwDOPOy2L87ErgSF",
                "includesCreatedEdit": False,
                "isMinimized": False,
                "minimizedReason": "",
                "reactionGroups": [],
                "url": "https://github.com/dougj-contrast/django_vuln/issues/94#issuecomment-3299738757",
                "viewerDidAuthor": False
            }
        ]

        # Mock the response from gh command
        mock_run_command.return_value = json.dumps(comment_data)

        # Initialize config with testing=True
        _ = get_config(testing=True)

        # Execute
        result = git_handler.get_issue_comments(issue_number, "claude")

        # Assert
        self.assertEqual(result, comment_data)
        mock_run_command.assert_called_once()

        # Verify the command was constructed correctly
        command = mock_run_command.call_args[0][0]
        self.assertEqual(command[0:3], ["gh", "issue", "view"])
        self.assertEqual(command[3], "94")
        self.assertTrue('--json' in command)
        self.assertTrue('--jq' in command)

        # Verify the jq filter contains author.login == "claude"
        jq_index = command.index('--jq') + 1
        self.assertIn('author.login == "claude"', command[jq_index])
        self.assertIn('sort_by(.createdAt) | reverse', command[jq_index])

        mock_debug_log.assert_any_call("Getting comments for issue #94 and author: claude")
        mock_debug_log.assert_any_call("Found 1 comments on issue #94")

    @patch('src.git_handler.run_command')
    @patch('src.git_handler.get_gh_env')
    @patch('src.git_handler.debug_log')
    @patch('src.git_handler.log')
    def test_get_issue_comments_no_comments(self, mock_log, mock_debug_log, mock_get_gh_env, mock_run_command):
        """Test getting comments from an issue when no comments are found"""
        # Setup
        issue_number = 42
        mock_get_gh_env.return_value = {'GITHUB_TOKEN': 'mock-token'}

        # Mock responses for the case where no comments are found
        test_cases = ["[]", "null", ""]

        for response in test_cases:
            with self.subTest(response=response):
                mock_run_command.return_value = response

                # Initialize config with testing=True
                _ = get_config(testing=True)

                # Execute
                result = git_handler.get_issue_comments(issue_number, "claude")

                # Assert
                self.assertEqual(result, [])
                mock_debug_log.assert_any_call(f"No comments found for issue #{issue_number}")
                mock_debug_log.assert_any_call(f"Getting comments for issue #{issue_number} and author: claude")

    @patch('src.git_handler.run_command')
    @patch('src.git_handler.get_gh_env')
    @patch('src.git_handler.debug_log')
    @patch('src.git_handler.log')
    def test_get_issue_comments_json_error(self, mock_log, mock_debug_log, mock_get_gh_env, mock_run_command):
        """Test getting comments from an issue when JSON parsing error occurs"""
        # Setup
        issue_number = 42
        mock_get_gh_env.return_value = {'GITHUB_TOKEN': 'mock-token'}

        # Mock invalid JSON response
        mock_run_command.return_value = "{invalid json}"

        # Initialize config with testing=True
        _ = get_config(testing=True)

        # Execute
        result = git_handler.get_issue_comments(issue_number, "claude")

        # Assert
        self.assertEqual(result, [])
        mock_run_command.assert_called_once()
        mock_debug_log.assert_any_call(f"Getting comments for issue #{issue_number} and author: claude")
        # Use assertIn rather than assert_any_call to check for partial match
        # since the actual error message includes JSON exception details
        log_calls = [call_item[0][0] for call_item in mock_log.call_args_list if call_item[1].get('is_error', False)]
        self.assertTrue(any("Could not parse JSON output from gh issue view:" in msg for msg in log_calls))
        self.assertTrue(any("{invalid json}" in msg for msg in log_calls))

    @patch('src.git_handler.run_command')
    @patch('src.git_handler.get_gh_env')
    @patch('src.git_handler.debug_log')
    @patch('src.git_handler.log')
    def test_get_issue_comments_exception(self, mock_log, mock_debug_log, mock_get_gh_env, mock_run_command):
        """Test getting comments from an issue when an exception occurs"""
        # Setup
        issue_number = 42
        mock_get_gh_env.return_value = {'GITHUB_TOKEN': 'mock-token'}

        # Mock exception when running command
        mock_run_command.side_effect = Exception("Command failed")

        # Initialize config with testing=True
        _ = get_config(testing=True)

        # Execute
        result = git_handler.get_issue_comments(issue_number, "claude")

        # Assert
        self.assertEqual(result, [])
        mock_run_command.assert_called_once()
        mock_debug_log.assert_any_call(f"Getting comments for issue #{issue_number} and author: claude")
        mock_log.assert_any_call(f"Error getting comments for issue #{issue_number}: Command failed", is_error=True)

    @patch('src.git_handler.run_command')
    @patch('src.git_handler.get_gh_env')
    @patch('src.git_handler.log')
    @patch('src.git_handler.config')
    def test_watch_github_action_run_success(self, mock_config, mock_log, mock_get_gh_env, mock_run_command):
        """Test watching a GitHub action run that completes successfully"""
        # Setup
        run_id = 12345
        mock_get_gh_env.return_value = {'GITHUB_TOKEN': 'mock-token'}
        mock_config.GITHUB_REPOSITORY = 'mock/repo'
        mock_run_command.return_value = "Run completed successfully"  # Success case returns output

        # Initialize config with testing=True
        _ = get_config(testing=True)

        # Execute
        result = git_handler.watch_github_action_run(run_id)

        # Assert
        self.assertTrue(result)
        mock_run_command.assert_called_once()

        # Verify the command was constructed correctly
        command = mock_run_command.call_args[0][0]
        self.assertEqual(command[0:3], ["gh", "run", "watch"])
        self.assertEqual(command[3], "12345")
        self.assertEqual(command[4:6], ["--repo", "mock/repo"])
        self.assertTrue("--compact" in command)
        self.assertTrue("--exit-status" in command)
        self.assertTrue("--interval" in command)

        mock_log.assert_any_call("OK. Now watching GitHub action run #12345 until completion... This may take several minutes...")
        mock_log.assert_any_call("GitHub action run #12345 completed successfully")

    @patch('src.git_handler.run_command')
    @patch('src.git_handler.get_gh_env')
    @patch('src.git_handler.log')
    @patch('src.git_handler.config')
    def test_watch_github_action_run_failure(self, mock_config, mock_log, mock_get_gh_env, mock_run_command):
        """Test watching a GitHub action run that fails"""
        # Setup
        run_id = 12345
        mock_get_gh_env.return_value = {'GITHUB_TOKEN': 'mock-token'}
        mock_config.GITHUB_REPOSITORY = 'mock/repo'

        # Simulate failure with an exception
        mock_run_command.side_effect = Exception("Run failed with status 1")

        # Initialize config with testing=True
        _ = get_config(testing=True)

        # Execute
        result = git_handler.watch_github_action_run(run_id)

        # Assert
        self.assertFalse(result)
        mock_run_command.assert_called_once()
        mock_log.assert_any_call("OK. Now watching GitHub action run #12345 until completion... This may take several minutes...")
        mock_log.assert_any_call("GitHub action run #12345 failed with error: Run failed with status 1", is_error=True)

    @patch('src.git_handler.run_command')
    @patch('src.git_handler.get_gh_env')
    @patch('src.git_handler.log')
    @patch('src.git_handler.debug_log')
    @patch('src.git_handler.config')
    def test_get_claude_workflow_run_id_success(self, mock_config, mock_debug_log, mock_log, mock_get_gh_env, mock_run_command):
        """Test getting Claude workflow run ID when successful"""
        # Setup
        mock_config.GITHUB_REPOSITORY = 'mock/repo'
        mock_get_gh_env.return_value = {'GITHUB_TOKEN': 'mock-token'}

        # Sample response with a workflow run ID
        run_data = {"conclusion": "success",
                    "databaseId": 12345678,
                    "createdAt": "2025-09-24T19:09:32Z",
                    "event": "issues",
                    "status": "completed"}
        mock_run_command.return_value = json.dumps(run_data)

        # Execute
        result = git_handler.get_claude_workflow_run_id()

        # Assert
        self.assertEqual(result, 12345678)
        mock_run_command.assert_called_once()

        # Verify command structure
        command = mock_run_command.call_args[0][0]
        self.assertEqual(command[0:3], ["gh", "run", "list"])
        self.assertTrue("--repo" in command)
        self.assertTrue("--workflow" in command)
        self.assertTrue("--limit" in command)
        self.assertTrue("--json" in command)
        self.assertTrue("--jq" in command)

        self.assertEqual(command[command.index("--workflow") + 1], "claude.yml")
        self.assertEqual(command[command.index("--json") + 1], "databaseId,status,event,createdAt,conclusion")
        expected_jq = (
            'map(select(.event == "issues" or .event == "issue_comment") | '
            'select(.status == "in_progress") | select(.conclusion != "skipped")) | '
            'sort_by(.createdAt) | reverse | .[0]'
        )
        self.assertEqual(command[command.index("--jq") + 1], expected_jq)

        mock_debug_log.assert_any_call("Getting in-progress Claude workflow run ID")
        mock_debug_log.assert_any_call("Found in-progress Claude workflow run ID: 12345678")

    @patch('src.git_handler.run_command')
    @patch('src.git_handler.get_gh_env')
    @patch('src.git_handler.debug_log')
    @patch('src.git_handler.config')
    def test_get_claude_workflow_run_id_no_runs(self, mock_config, mock_debug_log, mock_get_gh_env, mock_run_command):
        """Test getting Claude workflow run ID when no runs exist"""
        # Setup
        mock_config.GITHUB_REPOSITORY = 'mock/repo'
        mock_get_gh_env.return_value = {'GITHUB_TOKEN': 'mock-token'}

        # Empty array response
        mock_run_command.return_value = "[]"

        # Execute
        result = git_handler.get_claude_workflow_run_id()

        # Assert
        self.assertIsNone(result)
        mock_run_command.assert_called_once()
        mock_debug_log.assert_any_call("No in-progress Claude workflow runs found")

    @patch('src.git_handler.run_command')
    @patch('src.git_handler.get_gh_env')
    @patch('src.git_handler.log')
    @patch('src.git_handler.config')
    def test_get_claude_workflow_run_id_json_error(self, mock_config, mock_log, mock_get_gh_env, mock_run_command):
        """Test getting Claude workflow run ID when JSON parsing error occurs"""
        # Setup
        mock_config.GITHUB_REPOSITORY = 'mock/repo'
        mock_get_gh_env.return_value = {'GITHUB_TOKEN': 'mock-token'}

        # Invalid JSON response
        mock_run_command.return_value = "{invalid json}"

        # Execute
        result = git_handler.get_claude_workflow_run_id()

        # Assert
        self.assertIsNone(result)
        mock_run_command.assert_called_once()

        # Check that error was logged with correct prefix
        log_calls = [call_item[0][0] for call_item in mock_log.call_args_list if call_item[1].get('is_error', False)]
        self.assertTrue(any("Could not parse JSON output from gh run list:" in msg for msg in log_calls))

    @patch('src.git_handler.run_command')
    @patch('src.git_handler.get_gh_env')
    @patch('src.git_handler.log')
    @patch('src.git_handler.config')
    def test_get_claude_workflow_run_id_exception(self, mock_config, mock_log, mock_get_gh_env, mock_run_command):
        """Test getting Claude workflow run ID when an exception occurs"""
        # Setup
        mock_config.GITHUB_REPOSITORY = 'mock/repo'
        mock_get_gh_env.return_value = {'GITHUB_TOKEN': 'mock-token'}

        # Simulate command failure
        mock_run_command.side_effect = Exception("Command failed")

        # Execute
        result = git_handler.get_claude_workflow_run_id()

        # Assert
        self.assertIsNone(result)
        mock_run_command.assert_called_once()
        mock_log.assert_any_call("Error getting in-progress Claude workflow run ID: Command failed", is_error=True)

    @patch('src.git_handler.run_command')
    @patch('src.git_handler.get_gh_env')
    @patch('src.git_handler.log')
    @patch('src.git_handler.debug_log')
    @patch('tempfile.NamedTemporaryFile')
    @patch('os.path.exists')
    @patch('os.path.getsize')
    @patch('os.remove')
    def test_create_claude_pr_success(self, mock_remove, mock_getsize, mock_exists, mock_temp_file, mock_debug_log, mock_log, mock_get_gh_env, mock_run_command):
        """Test create_claude_pr when successful"""
        # Setup mock file
        mock_file = MagicMock()
        mock_file.name = '/tmp/mock_pr_body.md'
        mock_temp_file.return_value.__enter__.return_value = mock_file

        # Mock file operations
        mock_exists.return_value = True
        mock_getsize.return_value = 1024  # 1KB file size

        # Mock PR creation
        mock_get_gh_env.return_value = {'GITHUB_TOKEN': 'mock-token'}
        # Reset any previous mocks
        mock_run_command.reset_mock()
        mock_run_command.side_effect = None
        mock_exists.reset_mock()

        # Setup run_command with a side effect function for this test
        def success_run_command_side_effect(*args, **kwargs):
            # Check if this is a PR create command
            if len(args) > 0 and isinstance(args[0], list) and len(args[0]) > 2:
                cmd_args = args[0]
                if cmd_args[0] == "gh" and cmd_args[1] == "pr" and cmd_args[2] == "create":
                    return "https://github.com/mock/repo/pull/123\n"  # PR URL with newline
            return ""

        mock_run_command.side_effect = success_run_command_side_effect

        # Need to ensure the file exists check succeeds
        mock_exists.return_value = True

        # Test data
        title = "Test Claude PR Title"
        body = "Test Claude PR body content"
        base_branch = "main"
        head_branch = "claude/fix-123-20251225-1200"

        # Mock the run_command to actually return the PR URL instead of failing
        mock_run_command.return_value = "https://github.com/mock/repo/pull/456"

        # Execute
        result = git_handler.create_claude_pr(title, body, base_branch, head_branch)

        # Assert
        self.assertEqual(result, "https://github.com/mock/repo/pull/123")

        # Verify run_command was called with correct parameters
        mock_run_command.assert_called_once()
        command_args = mock_run_command.call_args[0][0]
        self.assertEqual(command_args[0:3], ["gh", "pr", "create"])
        self.assertEqual(command_args[3:5], ["--title", "Test Claude PR Title"])
        self.assertEqual(command_args[5:7], ["--body-file", "/tmp/mock_pr_body.md"])
        self.assertEqual(command_args[7:9], ["--base", "main"])
        self.assertEqual(command_args[9:11], ["--head", "claude/fix-123-20251225-1200"])

        # Verify temp file was created and cleaned up
        mock_temp_file.assert_called_once()
        mock_file.write.assert_called_with(body)
        mock_remove.assert_called_with("/tmp/mock_pr_body.md")

        # Verify appropriate logs were created
        mock_log.assert_any_call(f"Creating Claude PR with title: '{title}'")
        mock_debug_log.assert_any_call("Successfully created Claude PR: https://github.com/mock/repo/pull/123\n")

    @patch('src.git_handler.run_command')
    @patch('src.git_handler.get_gh_env')
    @patch('src.git_handler.log')
    @patch('tempfile.NamedTemporaryFile')
    @patch('os.path.exists')
    @patch('os.path.getsize')
    @patch('os.remove')
    def test_create_claude_pr_truncates_large_body(self, mock_remove, mock_getsize, mock_exists, mock_temp_file, mock_log, mock_get_gh_env, mock_run_command):
        """Test create_claude_pr when body is too large"""
        # Setup mock file
        mock_file = MagicMock()
        mock_file.name = '/tmp/mock_pr_body.md'
        mock_temp_file.return_value.__enter__.return_value = mock_file

        # Mock file operations
        mock_exists.return_value = True

        # Reset previous mocks
        mock_run_command.reset_mock()
        mock_run_command.side_effect = None
        mock_exists.reset_mock()

        # Set up mocks for this specific test
        mock_get_gh_env.return_value = {'GITHUB_TOKEN': 'mock-token'}

        # Mock both file operations
        mock_exists.return_value = True
        mock_getsize.return_value = 40000  # Set a file size to prevent file size errors

        # Set a specific return value for this test - we need to be explicit about the test expectations
        # Avoid setting a global mock_run_command.return_value as it affects all tests
        # Instead use a side effect function
        def run_command_side_effect(*args, **kwargs):
            # Check if this is a PR create command
            if len(args) > 0 and isinstance(args[0], list) and len(args[0]) > 2:
                cmd_args = args[0]
                if cmd_args[0] == "gh" and cmd_args[1] == "pr" and cmd_args[2] == "create":
                    return "https://github.com/mock/repo/pull/456"
            return ""

        mock_run_command.side_effect = run_command_side_effect

        # Test data with large body
        title = "Test Claude PR Title"
        body = "X" * 40000  # 40KB body (over the 32KB limit)
        base_branch = "main"
        head_branch = "claude/fix-123-20251225-1200"

        # Execute
        result = git_handler.create_claude_pr(title, body, base_branch, head_branch)

        # Assert
        self.assertEqual(result, "https://github.com/mock/repo/pull/456")

        # Verify body was truncated (should be truncated to 32000 chars plus the truncation message)
        expected_truncated_body = body[:32000] + "\n\n...[Content truncated due to size limits]..."
        mock_file.write.assert_called_with(expected_truncated_body)

        # Verify warning log was created
        mock_log.assert_any_call("PR body is too large (40000 chars). Truncating to 32000 chars.", is_warning=True)

    @patch('src.git_handler.run_command')
    @patch('src.git_handler.get_gh_env')
    @patch('src.git_handler.log')
    @patch('tempfile.NamedTemporaryFile')
    @patch('os.path.exists')
    @patch('os.remove')
    def test_create_claude_pr_command_fails(self, mock_remove, mock_exists, mock_temp_file, mock_log, mock_get_gh_env, mock_run_command):
        """Test create_claude_pr when gh command fails"""
        # Setup mock file
        mock_file = MagicMock()
        mock_file.name = '/tmp/mock_pr_body.md'
        mock_temp_file.return_value.__enter__.return_value = mock_file

        # Mock file operations
        mock_exists.return_value = True

        # Mock PR creation failure
        mock_get_gh_env.return_value = {'GITHUB_TOKEN': 'mock-token'}

        # Use a side effect function that raises an exception specifically for the PR command
        def run_command_side_effect(*args, **kwargs):
            if args and len(args[0]) > 2 and args[0][0] == "gh" and args[0][1] == "pr" and args[0][2] == "create":
                # The exact error message must match what's being checked in the assertion
                raise Exception("Failed to create PR")
            return ""

        mock_run_command.side_effect = run_command_side_effect

        # Test data
        title = "Test Claude PR Title"
        body = "Test body"
        base_branch = "main"
        head_branch = "claude/fix-123-20251225-1200"

        # Execute
        result = git_handler.create_claude_pr(title, body, base_branch, head_branch)

        # Assert
        self.assertEqual(result, "")  # Should return empty string on failure

        # We no longer need this debug print - removing for cleaner test output

        # Verify error was logged - checking for partial match
        call_args_list = [call_item.args for call_item in mock_log.call_args_list if call_item.kwargs.get('is_error', False)]
        self.assertTrue(any("Error creating Claude PR:" in args[0] for args in call_args_list),
                        f"Error message not found in calls: {call_args_list}")

        # Verify cleanup was still attempted
        mock_remove.assert_called_with("/tmp/mock_pr_body.md")

    @patch('src.git_handler.run_command')
    @patch('src.git_handler.get_gh_env')
    @patch('src.git_handler.log')
    @patch('tempfile.NamedTemporaryFile')
    @patch('os.path.exists')
    @patch('os.remove')
    def test_create_claude_pr_temp_file_missing(self, mock_remove, mock_exists, mock_temp_file, mock_log, mock_get_gh_env, mock_run_command):
        """Test create_claude_pr when temp file is missing"""
        # Setup mock file
        mock_file = MagicMock()
        mock_file.name = '/tmp/mock_pr_body.md'
        mock_temp_file.return_value.__enter__.return_value = mock_file

        # Mock file operations - file doesn't exist
        mock_exists.return_value = False

        # Test data
        title = "Test Claude PR Title"
        body = "Test body"
        base_branch = "main"
        head_branch = "claude/fix-123-20251225-1200"

        # Execute
        result = git_handler.create_claude_pr(title, body, base_branch, head_branch)

        # Assert
        self.assertEqual(result, "")  # Should return empty string if file missing

        # Verify error was logged
        mock_log.assert_any_call("Error: Temporary file /tmp/mock_pr_body.md does not exist", is_error=True)

        # Verify run_command was not called
        mock_run_command.assert_not_called()

    @patch('src.git_handler.run_command')
    @patch('src.git_handler.debug_log')
    @patch('src.git_handler.log')
    @patch('src.git_handler.config')
    def test_get_latest_branch_by_pattern(self, mock_config, mock_log, mock_debug_log, mock_run_command):
        """Test getting the latest branch by pattern"""
        # Setup mock response for GraphQL API
        mock_response = json.dumps({
            "data": {
                "repository": {
                    "refs": {
                        "nodes": [
                            {
                                "name": "claude/issue-42-20250916-1234",
                                "target": {
                                    "committedDate": "2025-09-16T12:34:56Z"
                                }
                            },
                            {
                                "name": "claude/issue-42-20250915-5678",
                                "target": {
                                    "committedDate": "2025-09-15T56:78:90Z"
                                }
                            },
                            {
                                "name": "some-other-branch",
                                "target": {
                                    "committedDate": "2025-09-17T12:34:56Z"
                                }
                            }
                        ]
                    }
                }
            }
        })

        # Mock config
        mock_config.GITHUB_REPOSITORY = "mock/repo"

        # Mock the run_command response
        mock_run_command.return_value = mock_response

        # Execute
        pattern = r'^claude/issue-42-\d{8}-\d{4}$'
        result = git_handler.get_latest_branch_by_pattern(pattern)

        # Assert
        self.assertEqual(result, "claude/issue-42-20250916-1234")
        mock_debug_log.assert_any_call(f"Finding latest branch matching pattern '{pattern}'")


if __name__ == '__main__':
    unittest.main()
