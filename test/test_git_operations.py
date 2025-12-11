#!/usr/bin/env python3

import unittest
from unittest.mock import patch, MagicMock
from src.smartfix.domains.scm.git_operations import GitOperations


class TestGitOperations(unittest.TestCase):
    """Test cases for GitOperations class."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock the config to avoid requiring environment variables in tests
        patcher = patch('src.utils.get_config')
        self.mock_config = patcher.start()
        self.mock_config.return_value = MagicMock(
            BASE_BRANCH="main",
            testing=True
        )
        self.addCleanup(patcher.stop)
        self.git_ops = GitOperations()

    def test_get_branch_name(self):
        """Test branch name generation."""
        result = self.git_ops.get_branch_name("test-123")
        self.assertEqual(result, "smartfix/remediation-test-123")

    def test_generate_commit_message(self):
        """Test commit message generation."""
        result = self.git_ops.generate_commit_message("SQL Injection", "uuid-123")
        expected = "Automated fix attempt for: SQL Injection (VULN-uuid-123)"
        self.assertEqual(result, expected)

    @patch('src.smartfix.domains.scm.git_operations.run_command')
    def test_configure_git_user(self, mock_run_command):
        """Test git user configuration."""
        self.git_ops.configure_git_user()

        # Verify git config commands were called
        expected_calls = [
            unittest.mock.call(['git', 'config', '--global', 'user.email', 'action@github.com']),
            unittest.mock.call(['git', 'config', '--global', 'user.name', 'GitHub Action'])
        ]
        mock_run_command.assert_has_calls(expected_calls)

    @patch('src.smartfix.domains.scm.git_operations.run_command')
    def test_stage_changes(self, mock_run_command):
        """Test staging changes."""
        self.git_ops.stage_changes()
        mock_run_command.assert_called_once_with(['git', 'add', '.'], check=False)

    @patch('src.smartfix.domains.scm.git_operations.run_command')
    def test_check_status_with_changes(self, mock_run_command):
        """Test check_status when there are changes."""
        mock_run_command.return_value = "M  file.txt\nA  newfile.py"
        result = self.git_ops.check_status()
        self.assertTrue(result)
        mock_run_command.assert_called_once_with(['git', 'status', '--porcelain'])

    @patch('src.smartfix.domains.scm.git_operations.run_command')
    def test_check_status_no_changes(self, mock_run_command):
        """Test check_status when there are no changes."""
        mock_run_command.return_value = ""
        result = self.git_ops.check_status()
        self.assertFalse(result)

    @patch('src.smartfix.domains.scm.git_operations.run_command')
    def test_commit_changes(self, mock_run_command):
        """Test committing changes."""
        message = "Test commit message"
        self.git_ops.commit_changes(message)
        mock_run_command.assert_called_once_with(['git', 'commit', '-m', message])

    @patch('src.smartfix.domains.scm.git_operations.run_command')
    def test_get_uncommitted_changed_files(self, mock_run_command):
        """Test getting uncommitted changed files."""
        mock_run_command.return_value = "src/test.py\nsrc/new.py\nuntracked.txt"
        result = self.git_ops.get_uncommitted_changed_files()
        expected = ["src/test.py", "src/new.py", "untracked.txt"]
        self.assertEqual(result, expected)

    @patch('src.smartfix.domains.scm.git_operations.run_command')
    def test_get_last_commit_changed_files(self, mock_run_command):
        """Test getting files changed in last commit."""
        mock_run_command.return_value = "src/file1.py\nsrc/file2.js\ndocs/readme.md"
        result = self.git_ops.get_last_commit_changed_files()
        expected = ["src/file1.py", "src/file2.js", "docs/readme.md"]
        self.assertEqual(result, expected)

    @patch('src.smartfix.domains.scm.git_operations.run_command')
    def test_push_branch(self, mock_run_command):
        """Test pushing branch."""
        with patch('src.smartfix.domains.scm.git_operations.get_config') as mock_config:
            mock_config.return_value = MagicMock(
                GITHUB_TOKEN="mock-token",
                GITHUB_SERVER_URL="https://mockhub.com",
                GITHUB_REPOSITORY="mock/repo",
                BASE_BRANCH="main",
                testing=True
            )
            git_ops = GitOperations()
            branch_name = "smartfix-test-123"
            git_ops.push_branch(branch_name)
            # Should use authenticated URL with token
            mock_run_command.assert_called_once()
            call_args = mock_run_command.call_args[0][0]
            self.assertEqual(call_args[0:2], ['git', 'push'])
            self.assertIn('--set-upstream', call_args)
            self.assertIn('x-access-token:mock-token', call_args[3])

    def test_extract_issue_number_from_branch(self):
        """Test extracting issue number from branch name."""
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
                result = self.git_ops.extract_issue_number_from_branch(branch_name)
                self.assertEqual(result, expected)

    @patch('src.smartfix.domains.scm.git_operations.run_command')
    def test_cleanup_branch(self, mock_run_command):
        """Test cleaning up branch."""
        branch_name = "smartfix-test-123"
        self.git_ops.cleanup_branch(branch_name)

        expected_calls = [
            unittest.mock.call(['git', 'reset', '--hard'], check=False),
            unittest.mock.call(['git', 'checkout', 'main'], check=False),
            unittest.mock.call(['git', 'branch', '-D', branch_name], check=False)
        ]
        mock_run_command.assert_has_calls(expected_calls)


if __name__ == '__main__':
    unittest.main()
