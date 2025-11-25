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

import re
from typing import List, Optional
from src.utils import run_command, debug_log


class GitOperations:
    """
    Git operations wrapper for SmartFix SCM functionality.

    This class handles all git command operations including branch management,
    staging, committing, and status checking.
    """

    def __init__(self):
        """Initialize Git operations handler."""
        pass

    def configure_git_user(self) -> None:
        """Configure git user for commits."""
        run_command(['git', 'config', '--global', 'user.name', 'SmartFix-AI'])
        run_command(['git', 'config', '--global', 'user.email', 'support+ai@contrastsecurity.com'])

    def get_branch_name(self, remediation_id: str) -> str:
        """Generate branch name from remediation ID."""
        return f"smartfix-{remediation_id}"

    def prepare_feature_branch(self, remediation_id: str) -> None:
        """
        Prepare a feature branch for SmartFix work.

        Args:
            remediation_id: The remediation ID to use for branch naming
        """
        branch_name = self.get_branch_name(remediation_id)

        # Check if branch already exists
        result = run_command(['git', 'show-ref', '--verify', '--quiet', f'refs/heads/{branch_name}'], check=False)
        if result is not None:
            # Branch exists, check it out
            debug_log(f"Branch {branch_name} already exists, switching to it")
            run_command(['git', 'checkout', branch_name])
        else:
            # Create new branch
            debug_log(f"Creating new branch: {branch_name}")
            run_command(['git', 'checkout', '-b', branch_name])

    def stage_changes(self) -> None:
        """Stage all changes for commit."""
        debug_log("Staging changes...")
        run_command(['git', 'add', '.'])

    def check_status(self) -> bool:
        """
        Check if there are uncommitted changes.

        Returns:
            bool: True if there are changes to commit, False otherwise
        """
        result = run_command(['git', 'status', '--porcelain'], check=False)
        return result is not None and result.strip() != ""

    def generate_commit_message(self, vuln_title: str, vuln_uuid: str) -> str:
        """Generate a standardized commit message."""
        return f"SmartFix: {vuln_title}\n\nRemediation UUID: {vuln_uuid}"

    def commit_changes(self, message: str) -> None:
        """
        Commit staged changes.

        Args:
            message: The commit message to use
        """
        debug_log(f"Committing changes with message: {message}")
        run_command(['git', 'commit', '-m', message])

    def get_uncommitted_changed_files(self) -> List[str]:
        """
        Get list of uncommitted changed files.

        Returns:
            List[str]: List of file paths with uncommitted changes
        """
        result = run_command(['git', 'status', '--porcelain'], check=False)
        if result is None:
            return []

        changed_files = []
        for line in result.strip().split('\n'):
            if line.strip():
                # Extract filename from git status format (e.g., "M  file.txt", "A  file.txt")
                parts = line.strip().split(None, 1)
                if len(parts) >= 2:
                    changed_files.append(parts[1])

        return changed_files

    def get_last_commit_changed_files(self) -> List[str]:
        """
        Get list of files changed in the last commit.

        Returns:
            List[str]: List of file paths changed in the last commit
        """
        result = run_command(['git', 'diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD'], check=False)
        if result is None:
            return []

        return [line.strip() for line in result.strip().split('\n') if line.strip()]

    def amend_commit(self) -> None:
        """Amend the last commit with staged changes."""
        debug_log("Amending last commit...")
        run_command(['git', 'commit', '--amend', '--no-edit'])

    def push_branch(self, branch_name: str) -> None:
        """
        Push branch to remote repository.

        Args:
            branch_name: The branch name to push
        """
        debug_log(f"Pushing branch: {branch_name}")
        run_command(['git', 'push', 'origin', branch_name])

    def cleanup_branch(self, branch_name: str) -> None:
        """
        Clean up feature branch by switching back to main and deleting it.

        Args:
            branch_name: The branch name to clean up
        """
        debug_log(f"Cleaning up branch: {branch_name}")

        # Switch back to main branch
        run_command(['git', 'checkout', 'main'], check=False)

        # Delete local branch
        run_command(['git', 'branch', '-D', branch_name], check=False)

        # Delete remote branch
        run_command(['git', 'push', 'origin', '--delete', branch_name], check=False)

    def extract_issue_number_from_branch(self, branch_name: str) -> Optional[int]:
        """
        Extract issue number from branch name.

        Args:
            branch_name: The branch name to parse

        Returns:
            Optional[int]: The issue number if found, None otherwise
        """
        # Look for patterns like smartfix-123-issue or smartfix-issue-123
        patterns = [
            r'smartfix-(\d+)-issue',
            r'smartfix-issue-(\d+)',
            r'issue-(\d+)',
            r'(\d+)-issue'
        ]

        for pattern in patterns:
            match = re.search(pattern, branch_name)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    continue

        return None

    def get_latest_branch_by_pattern(self, pattern: str) -> Optional[str]:
        """
        Get the latest branch matching a pattern.

        Args:
            pattern: Regex pattern to match branch names

        Returns:
            Optional[str]: The latest matching branch name, or None if not found
        """
        try:
            # Get all branches
            result = run_command(['git', 'branch', '-r'], check=False)
            if result is None:
                return None

            matching_branches = []
            for line in result.strip().split('\n'):
                branch = line.strip().replace('origin/', '')
                if re.match(pattern, branch):
                    matching_branches.append(branch)

            if not matching_branches:
                return None

            # Sort branches by creation time (most recent first)
            # This is a simple approach - we could enhance with git log if needed
            matching_branches.sort(reverse=True)
            return matching_branches[0]

        except Exception as e:
            debug_log(f"Error getting latest branch by pattern {pattern}: {e}")
            return None
