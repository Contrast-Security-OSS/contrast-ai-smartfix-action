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
# engineered, modified, repackaged, sold, redistributed or otherwise used in a
# way not consistent with the End User License Agreement.
# #L%
#

import os
import json
import re
from typing import List
from src.utils import run_command, debug_log, log, error_exit
from src.smartfix.shared.failure_categories import FailureCategory
from src.config import get_config
from src.smartfix.shared.coding_agents import CodingAgents
from src.smartfix.domains.scm.git_operations import GitOperations
from src.smartfix.domains.scm.scm_operations import ScmOperations


class GitHubOperations(ScmOperations):
    """
    GitHub CLI operations wrapper for SmartFix GitHub functionality.

    This class handles all GitHub CLI (gh) command operations including
    issues, pull requests, labels, and GitHub Actions.
    """

    def __init__(self):
        """Initialize GitHub operations handler."""
        self.config = get_config()
        self.git_ops = GitOperations()

    def get_gh_env(self) -> dict:
        """
        Returns an environment dictionary with the GitHub token set.
        Used for GitHub CLI commands that require authentication.

        Returns:
            dict: Environment variables dictionary with GitHub token
        """
        gh_env = os.environ.copy()
        gh_env["GITHUB_TOKEN"] = self.config.GITHUB_TOKEN
        return gh_env

    def log_copilot_assignment_error(self, issue_number: int, error: Exception, remediation_label: str) -> None:
        """
        Logs a standardized error message for Copilot assignment failures and exits.

        Args:
            issue_number: The issue number that failed assignment
            error: The exception that occurred
            remediation_label: The remediation label to extract ID from
        """
        log(f"Error: Failed to assign issue #{issue_number} to @Copilot: {error}", is_error=True)
        log("This may be due to:")
        log("  - GitHub Copilot is not enabled for this repository")
        log("  - The PAT (Personal Access Token) was not created by a user with a Copilot license seat")
        log("  - @Copilot user doesn't exist in this repository")
        log("  - Insufficient permissions to assign users")
        log("  - Repository settings restricting assignments")

        # Extract remediation_id from the remediation_label (format: "smartfix-id:REMEDIATION_ID")
        remediation_id = remediation_label.replace("smartfix-id:", "") if remediation_label.startswith("smartfix-id:") else "unknown"

        # Only exit in non-testing mode
        if not self.config.testing:
            error_exit(remediation_id, FailureCategory.GIT_COMMAND_FAILURE.value)
        else:
            log("NOTE: In testing mode, not exiting on Copilot assignment failure", is_warning=True)

    def get_pr_changed_files_count(self, pr_number: int) -> int:
        """
        Get the number of changed files in a PR using GitHub CLI.

        Args:
            pr_number: The PR number to check

        Returns:
            int: Number of changed files, or -1 if there was an error
        """
        try:
            result = run_command(
                ['gh', 'pr', 'view', str(pr_number), '--json', 'changedFiles', '--jq', '.changedFiles'],
                env=self.get_gh_env(),
                check=False
            )
            if result is None:
                debug_log(f"Failed to get changed files count for PR {pr_number}")
                return -1

            # Parse the result as an integer
            try:
                count = int(result.strip())
                debug_log(f"PR {pr_number} has {count} changed files")
                return count
            except ValueError:
                debug_log(f"Invalid response from gh command for PR {pr_number}: {result}")
                return -1

        except Exception as e:
            debug_log(f"Exception while getting changed files count for PR {pr_number}: {e}")
            return -1

    def check_issues_enabled(self) -> bool:
        """
        Check if issues are enabled for the current repository.

        Returns:
            bool: True if issues are enabled, False otherwise
        """
        try:
            result = run_command(
                ['gh', 'repo', 'view', '--json', 'hasIssuesEnabled'],
                env=self.get_gh_env(),
                check=False
            )
            if result is None:
                debug_log("Failed to check if issues are enabled")
                return False

            data = json.loads(result)
            return data.get('hasIssuesEnabled', False)

        except Exception as e:
            debug_log(f"Exception while checking if issues are enabled: {e}")
            return False

    def generate_label_details(self, vuln_uuid: str) -> tuple[str, str, str]:
        """Generate label name, description, and color for a vulnerability."""
        label_name = f"smartfix-id:{vuln_uuid}"
        description = f"SmartFix remediation tracking label for {vuln_uuid}"
        color = "0052cc"  # Blue color
        return label_name, description, color

    def ensure_label(self, label_name: str, description: str, color: str) -> bool:
        """
        Ensure a label exists in the repository, creating it if necessary.

        Args:
            label_name: The name of the label
            description: The description of the label
            color: The hex color code for the label (without #)

        Returns:
            bool: True if label exists or was created successfully, False otherwise
        """
        try:
            # Check if label already exists
            result = run_command(
                ['gh', 'label', 'list', '--json', 'name'],
                env=self.get_gh_env(),
                check=False
            )
            if result is not None:
                labels = json.loads(result)
                for label in labels:
                    if label['name'] == label_name:
                        debug_log(f"Label {label_name} already exists")
                        return True

            # Create the label
            debug_log(f"Creating label: {label_name}")
            result = run_command(
                ['gh', 'label', 'create', label_name,
                 '--description', description,
                 '--color', color],
                env=self.get_gh_env(),
                check=False
            )
            if result is not None:
                debug_log(f"Successfully created label: {label_name}")
                return True
            else:
                debug_log(f"Failed to create label: {label_name}")
                return False

        except Exception as e:
            debug_log(f"Exception while ensuring label {label_name}: {e}")
            return False

    def check_pr_status_for_label(self, label_name: str) -> str:
        """
        Check the status of PRs with a specific label.

        Args:
            label_name: The label to search for

        Returns:
            str: "open", "merged", "closed", or "none" if no PR found
        """
        try:
            # Search for PRs with the specific label
            result = run_command(
                ['gh', 'pr', 'list', '--label', label_name, '--json', 'state,title,number'],
                env=self.get_gh_env(),
                check=False
            )
            if result is None:
                debug_log(f"Failed to search for PRs with label: {label_name}")
                return "none"

            prs = json.loads(result)
            if not prs:
                debug_log(f"No PRs found with label: {label_name}")
                return "none"

            # Return the state of the first PR found
            pr_state = prs[0]['state'].lower()
            debug_log(f"Found PR #{prs[0]['number']} with label {label_name}, state: {pr_state}")
            return pr_state

        except Exception as e:
            debug_log(f"Exception while checking PR status for label {label_name}: {e}")
            return "none"

    def count_open_prs_with_prefix(self, label_prefix: str) -> int:
        """
        Count open PRs with labels matching a prefix.

        Args:
            label_prefix: The label prefix to search for

        Returns:
            int: Number of open PRs with matching labels
        """
        try:
            # Get all open PRs
            result = run_command(
                ['gh', 'pr', 'list', '--state', 'open', '--json', 'labels'],
                env=self.get_gh_env(),
                check=False
            )
            if result is None:
                debug_log("Failed to get open PRs")
                return 0

            prs = json.loads(result)
            count = 0

            for pr in prs:
                for label in pr.get('labels', []):
                    if label['name'].startswith(label_prefix):
                        count += 1
                        break  # Count each PR only once

            debug_log(f"Found {count} open PRs with label prefix: {label_prefix}")
            return count

        except Exception as e:
            debug_log(f"Exception while counting open PRs with prefix {label_prefix}: {e}")
            return 0

    def generate_pr_title(self, vuln_title: str) -> str:
        """Generate a standardized PR title."""
        return f"SmartFix: {vuln_title}"

    def create_pr(self, title: str, body: str, remediation_id: str, base_branch: str, label: str) -> str:
        """
        Create a pull request and return the PR URL.

        Args:
            title: The PR title
            body: The PR body/description
            remediation_id: The remediation ID
            base_branch: The base branch to merge into
            label: The label to apply to the PR

        Returns:
            str: The PR URL if successful, empty string if failed
        """
        try:
            head_branch = self.git_ops.get_branch_name(remediation_id)
            # Create the PR
            result = run_command(
                ['gh', 'pr', 'create',
                 '--title', title,
                 '--body', body,
                 '--base', base_branch,
                 '--head', head_branch,
                 '--label', label],
                env=self.get_gh_env(),
                check=False
            )
            if result is None:
                debug_log("Failed to create PR")
                return ""

            pr_url = result.strip()
            debug_log(f"Successfully created PR: {pr_url}")
            return pr_url

        except Exception as e:
            debug_log(f"Exception while creating PR: {e}")
            return ""

    def create_claude_pr(self, title: str, body: str, base_branch: str, head_branch: str) -> str:
        """
        Create a pull request for Claude Code workflow.

        Args:
            title: The PR title
            body: The PR body/description
            base_branch: The base branch to merge into
            head_branch: The head branch to merge from

        Returns:
            str: The PR URL if successful, empty string if failed
        """
        try:
            result = run_command(
                ['gh', 'pr', 'create',
                 '--title', title,
                 '--body', body,
                 '--base', base_branch,
                 '--head', head_branch],
                env=self.get_gh_env(),
                check=False
            )
            if result is None:
                debug_log("Failed to create Claude PR")
                return ""

            pr_url = result.strip()
            debug_log(f"Successfully created Claude PR: {pr_url}")
            return pr_url

        except Exception as e:
            debug_log(f"Exception while creating Claude PR: {e}")
            return ""

    def create_issue(self, title: str, body: str, vuln_label: str, remediation_label: str) -> int:
        """
        Create a GitHub issue and return the issue number.

        Args:
            title: The issue title
            body: The issue body/description
            vuln_label: The vulnerability label
            remediation_label: The remediation tracking label

        Returns:
            int: The issue number if successful, -1 if failed
        """
        try:
            # Create the issue
            result = run_command(
                ['gh', 'issue', 'create',
                 '--title', title,
                 '--body', body,
                 '--label', vuln_label,
                 '--label', remediation_label],
                env=self.get_gh_env(),
                check=False
            )
            if result is None:
                debug_log("Failed to create issue")
                return -1

            issue_url = result.strip()
            # Extract issue number from URL
            match = re.search(r'/issues/(\d+)$', issue_url)
            if match:
                issue_number = int(match.group(1))
                debug_log(f"Successfully created issue #{issue_number}: {issue_url}")
                # Try to assign to Copilot if configured
                if self.config.coding_agent == CodingAgents.COPILOT:
                    try:
                        assign_result = run_command(
                            ['gh', 'issue', 'edit', str(issue_number),
                             '--add-assignee', '@Copilot'],
                            env=self.get_gh_env(),
                            check=False
                        )
                        if assign_result is not None:
                            debug_log(f"Successfully assigned issue #{issue_number} to @Copilot")
                        else:
                            debug_log(f"Failed to assign issue #{issue_number} to @Copilot")
                    except Exception as e:
                        self.log_copilot_assignment_error(issue_number, e, remediation_label)
                return issue_number
            else:
                debug_log(f"Could not extract issue number from URL: {issue_url}")
                return -1

        except Exception as e:
            debug_log(f"Exception while creating issue: {e}")
            return -1

    def find_issue_with_label(self, label: str) -> int:
        """
        Find an issue with a specific label.

        Args:
            label: The label to search for

        Returns:
            int: The issue number if found, -1 if not found
        """
        try:
            result = run_command(
                ['gh', 'issue', 'list', '--label', label, '--json', 'number'],
                env=self.get_gh_env(),
                check=False
            )
            if result is None:
                debug_log(f"Failed to search for issues with label: {label}")
                return -1

            issues = json.loads(result)
            if not issues:
                debug_log(f"No issues found with label: {label}")
                return -1

            issue_number = issues[0]['number']
            debug_log(f"Found issue #{issue_number} with label: {label}")
            return issue_number

        except Exception as e:
            debug_log(f"Exception while finding issue with label {label}: {e}")
            return -1

    def reset_issue(self, issue_number: int, issue_title: str, remediation_label: str) -> bool:
        """
        Reset an issue by removing assignees and adding a reset comment.

        Args:
            issue_number: The issue number to reset
            issue_title: The issue title
            remediation_label: The remediation label

        Returns:
            bool: True if reset successful, False otherwise
        """
        try:
            # Remove all assignees
            result = run_command(
                ['gh', 'issue', 'edit', str(issue_number), '--remove-assignee', '@me'],
                env=self.get_gh_env(),
                check=False
            )
            # Add a comment about the reset
            reset_comment = f"Issue #{issue_number} has been reset. Previous work may have failed or been abandoned."
            comment_result = run_command(
                ['gh', 'issue', 'comment', str(issue_number), '--body', reset_comment],
                env=self.get_gh_env(),
                check=False
            )
            if result is not None and comment_result is not None:
                debug_log(f"Successfully reset issue #{issue_number}")
                return True
            else:
                debug_log(f"Failed to reset issue #{issue_number}")
                return False

        except Exception as e:
            debug_log(f"Exception while resetting issue #{issue_number}: {e}")
            return False

    def find_open_pr_for_issue(self, issue_number: int, issue_title: str) -> dict:
        """
        Find an open PR that references a specific issue.

        Args:
            issue_number: The issue number to search for
            issue_title: The issue title

        Returns:
            dict: PR information if found, empty dict if not found
        """
        try:
            # Search for PRs that mention the issue
            result = run_command(
                ['gh', 'pr', 'list', '--state', 'open', '--json', 'number,title,body,url'],
                env=self.get_gh_env(),
                check=False
            )
            if result is None:
                debug_log("Failed to get open PRs")
                return {}

            prs = json.loads(result)
            for pr in prs:
                # Check if PR title or body references the issue
                pr_text = f"{pr['title']} {pr.get('body', '')}".lower()
                issue_text = issue_title.lower()
                if ((f"#{issue_number}" in pr_text)
                        or (f"issue {issue_number}" in pr_text)
                        or (issue_text in pr_text)):
                    debug_log(f"Found open PR #{pr['number']} for issue #{issue_number}")
                    return pr

            debug_log(f"No open PR found for issue #{issue_number}")
            return {}

        except Exception as e:
            debug_log(f"Exception while finding open PR for issue #{issue_number}: {e}")
            return {}

    def add_labels_to_pr(self, pr_number: int, labels: List[str]) -> bool:
        """
        Add labels to a pull request.

        Args:
            pr_number: The PR number
            labels: List of label names to add

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            for label in labels:
                result = run_command(
                    ['gh', 'pr', 'edit', str(pr_number), '--add-label', label],
                    env=self.get_gh_env(),
                    check=False
                )
                if result is None:
                    debug_log(f"Failed to add label {label} to PR #{pr_number}")
                    return False

            debug_log(f"Successfully added labels {labels} to PR #{pr_number}")
            return True

        except Exception as e:
            debug_log(f"Exception while adding labels to PR #{pr_number}: {e}")
            return False

    def get_issue_comments(self, issue_number: int, author: str = None) -> List[dict]:
        """
        Get comments from an issue, optionally filtered by author.

        Args:
            issue_number: The issue number
            author: Optional author to filter by

        Returns:
            List[dict]: List of comment dictionaries
        """
        try:
            result = run_command(
                ['gh', 'issue', 'view', str(issue_number), '--json', 'comments'],
                env=self.get_gh_env(),
                check=False
            )
            if result is None:
                debug_log(f"Failed to get comments for issue #{issue_number}")
                return []

            data = json.loads(result)
            comments = data.get('comments', [])

            if author:
                comments = [c for c in comments if c.get('author', {}).get('login') == author]

            debug_log(f"Retrieved {len(comments)} comments for issue #{issue_number}")
            return comments

        except Exception as e:
            debug_log(f"Exception while getting comments for issue #{issue_number}: {e}")
            return []

    def watch_github_action_run(self, run_id: int) -> bool:
        """
        Watch a GitHub Action run until completion.

        Args:
            run_id: The workflow run ID to watch

        Returns:
            bool: True if run completed successfully, False otherwise
        """
        try:
            result = run_command(
                ['gh', 'run', 'watch', str(run_id)],
                env=self.get_gh_env(),
                check=False
            )
            if result is not None:
                debug_log(f"GitHub Action run {run_id} completed")
                return True
            else:
                debug_log(f"GitHub Action run {run_id} failed or was cancelled")
                return False

        except Exception as e:
            debug_log(f"Exception while watching GitHub Action run {run_id}: {e}")
            return False

    def get_claude_workflow_run_id(self) -> int:
        """
        Get the workflow run ID for Claude Code workflow.

        Returns:
            int: The workflow run ID if found, -1 if not found
        """
        try:
            # Get recent workflow runs
            result = run_command(
                ['gh', 'run', 'list', '--limit', '10', '--json', 'databaseId,name,status'],
                env=self.get_gh_env(),
                check=False
            )
            if result is None:
                debug_log("Failed to get workflow runs")
                return -1

            runs = json.loads(result)
            for run in runs:
                if 'claude' in run.get('name', '').lower():
                    run_id = run['databaseId']
                    debug_log(f"Found Claude workflow run ID: {run_id}")
                    return run_id

            debug_log("No Claude workflow run found")
            return -1

        except Exception as e:
            debug_log(f"Exception while getting Claude workflow run ID: {e}")
            return -1
