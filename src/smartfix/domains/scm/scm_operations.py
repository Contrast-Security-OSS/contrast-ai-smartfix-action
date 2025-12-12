"""
Base class for SCM operations.

This module defines the ScmOperations abstract base class which serves as a contract
for implementing SCM platform-specific operations (GitHub, GitLab, BitBucket, etc.).
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple


class ScmOperations(ABC):
    """
    Abstract base class for SCM operations.

    This class defines the interface for SCM platform-specific operations
    that all platform implementations must adhere to.
    """

    @abstractmethod
    def get_gh_env(self) -> dict:
        """
        Returns environment dictionary with authentication tokens set for CLI commands.

        Returns:
            Dict[str, str]: Environment dictionary with auth tokens
        """
        pass

    @abstractmethod
    def log_copilot_assignment_error(self, issue_number: int, error: Exception, remediation_label: str) -> None:
        """
        Logs a standardized error message for agent assignment failures.

        Args:
            issue_number (int): The issue number that failed assignment
            error (Exception): The exception that occurred
            label (str): The label associated with the assignment

        Returns:
            None
        """
        pass

    @abstractmethod
    def get_pr_changed_files_count(self, pr_number: int) -> int:
        """
        Gets the number of changed files in a PR.

        Args:
            pr_number (int): The PR number

        Returns:
            int: Number of changed files
        """
        pass

    @abstractmethod
    def check_issues_enabled(self) -> bool:
        """
        Checks if issues are enabled for the current repository.

        Returns:
            bool: True if issues are enabled, False otherwise
        """
        pass

    @abstractmethod
    def generate_label_details(self, vuln_uuid: str) -> Tuple[str, str, str]:
        """
        Generates label name, description, and color for a vulnerability.

        Args:
            vuln_uuid (str): Vulnerability UUID

        Returns:
            Tuple[str, str, str]: Label name, description, and color
        """
        pass

    @abstractmethod
    def ensure_label(self, label_name: str, description: str, color: str) -> bool:
        """
        Ensures a label exists in the repository, creating it if necessary.

        Args:
            label_name (str): Label name
            description (str): Label description
            color (str): Label color in hex format without #

        Returns:
            bool: True if successful, False otherwise
        """
        pass

    @abstractmethod
    def check_pr_status_for_label(self, label_name: str) -> str:
        """
        Checks the status of PRs with a specific label.

        Args:
            label_name (str): Label name to check

        Returns:
            str: Status of the PR ('open', 'merged', 'closed', or 'none')
        """
        pass

    @abstractmethod
    def count_open_prs_with_prefix(self, label_prefix: str) -> int:
        """
        Counts open PRs with labels matching a prefix.

        Args:
            label_prefix (str): Label prefix to match

        Returns:
            int: Count of matching open PRs
        """
        pass

    @abstractmethod
    def generate_pr_title(self, vuln_title: str) -> str:
        """
        Generates a standardized PR title.

        Args:
            vuln_title (str): Vulnerability title

        Returns:
            str: Generated PR title
        """
        pass

    @abstractmethod
    def create_pr(self, title: str, body: str, remediation_id: str,
                  base_branch: str, label: str) -> str:
        """
        Creates a pull request and returns the PR URL.

        Args:
            title (str): PR title
            body (str): PR body
            remediation_id (str): Remediation ID
            base_branch (str): Base branch name
            label (str): Label to apply to the PR

        Returns:
            str: URL of the created PR
        """
        pass

    @abstractmethod
    def create_claude_pr(self, title: str, body: str,
                         base_branch: str, head_branch: str) -> str:
        """
        Creates a pull request for external agent workflow.

        Args:
            title (str): PR title
            body (str): PR body
            base_branch (str): Base branch name
            head_branch (str): Head branch name

        Returns:
            str: URL of the created PR
        """
        pass

    @abstractmethod
    def create_issue(self, title: str, body: str,
                     vuln_label: str, remediation_label: str) -> int:
        """
        Creates an issue and returns the issue number.

        Args:
            title (str): Issue title
            body (str): Issue body
            vuln_label (str): Vulnerability label
            remediation_label (str): Remediation label

        Returns:
            int: Number of the created issue
        """
        pass

    @abstractmethod
    def find_issue_with_label(self, label: str) -> int:
        """
        Finds an issue with a specific label.

        Args:
            label (str): Label to search for

        Returns:
            int: Issue number if found, 0 otherwise
        """
        pass

    @abstractmethod
    def reset_issue(self, issue_number: int, issue_title: str,
                    remediation_label: str) -> bool:
        """
        Resets an issue by removing assignees and adding a reset comment.

        Args:
            issue_number (int): Issue number
            issue_title (str): Issue title
            remediation_label (str): Remediation label

        Returns:
            bool: True if successful, False otherwise
        """
        pass

    @abstractmethod
    def find_open_pr_for_issue(self, issue_number: int, issue_title: str) -> Dict:
        """
        Finds an open PR that references a specific issue.

        Args:
            issue_number (int): Issue number
            issue_title (str): Issue title

        Returns:
            Dict: PR details if found, empty dict otherwise
        """
        pass

    @abstractmethod
    def add_labels_to_pr(self, pr_number: int, labels: List[str]) -> bool:
        """
        Adds labels to a pull request.

        Args:
            pr_number (int): PR number
            labels (List[str]): Labels to add

        Returns:
            bool: True if successful, False otherwise
        """
        pass

    @abstractmethod
    def get_issue_comments(self, issue_number: int, author: str = None) -> List[dict]:
        """
        Gets comments from an issue, optionally filtered by author.

        Args:
            issue_number (int): Issue number
            author (Optional[str]): Author to filter by

        Returns:
            List[Dict]: List of comment dictionaries
        """
        pass

    @abstractmethod
    def watch_github_action_run(self, run_id: int) -> bool:
        """
        Watches a workflow run until completion.

        Args:
            run_id (int): Workflow run ID

        Returns:
            bool: True if workflow succeeded, False otherwise
        """
        pass

    @abstractmethod
    def get_claude_workflow_run_id(self) -> int:
        """
        Gets the workflow run ID for agent workflow.

        Returns:
            int: Workflow run ID
        """
        pass

    @abstractmethod
    def extract_issue_number_from_branch(self, branch_name: str) -> Optional[int]:
        """
        Extracts the issue number from a branch name.

        Args:
            branch_name (str): The branch name to extract from

        Returns:
            Optional[int]: The issue number if found, None otherwise
        """
        pass

    @abstractmethod
    def get_latest_branch_by_pattern(self, pattern: str) -> Optional[str]:
        """
        Gets the latest branch matching a specific pattern.

        Args:
            pattern (str): The regex pattern to match branch names against

        Returns:
            Optional[str]: The latest matching branch name or None if no matches found
        """
        pass
